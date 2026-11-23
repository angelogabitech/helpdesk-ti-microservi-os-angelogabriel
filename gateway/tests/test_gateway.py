import asyncio
import gzip

import httpx
import pytest

from app import proxy


@pytest.mark.parametrize("rota,host", [
    ("/auth/login", "usuarios-proxy"), ("/auth/eu", "usuarios-proxy"),
    ("/usuarios", "usuarios-proxy"), ("/usuarios/4", "usuarios-proxy"),
    ("/ativos", "inventario"), ("/ativos/7", "inventario"),
    ("/chamados/painel", "chamados"), ("/chamados/1/atribuir", "chamados"),
    ("/notificacoes", "chamados"),
])
def test_encaminha_somente_para_o_servico_da_rota(ambiente, rota, host):
    cliente, chamadas, _ = ambiente
    assert cliente.get(rota).json() == {"host": host}
    assert chamadas[-1].url.path == rota


def test_preserva_metodo_corpo_query_resposta_e_auth(ambiente):
    cliente, chamadas, respostas = ambiente
    respostas["/chamados/1/status"] = httpx.Response(
        422, headers={"Retry-After": "12", "Connection": "ETag", "ETag": "interno"},
        json={"detail": "Transição inválida."},
    )
    corpo = b'{"status":"fechado"}'
    resposta = cliente.patch(
        "/chamados/1/status?a=1&a=2&setor=T%C3%A9cnico",
        content=corpo, headers={"Content-Type": "application/json", "Authorization": "Bearer teste"},
    )
    assert resposta.status_code == 422
    assert resposta.json() == {"detail": "Transição inválida."}
    assert resposta.headers["retry-after"] == "12"
    assert resposta.headers["cache-control"] == "no-store"
    assert "etag" not in resposta.headers
    chamada = chamadas[-1]
    assert chamada.method == "PATCH" and chamada.content == corpo
    assert chamada.url.query == b"a=1&a=2&setor=T%C3%A9cnico"
    assert chamada.headers["content-type"] == "application/json"
    assert chamada.headers["authorization"] == "Bearer teste"


def test_recria_ip_do_cliente_e_filtra_cabecalhos_de_conexao(ambiente):
    cliente, chamadas, _ = ambiente
    cliente.post("/auth/login", headers={
        "X-Forwarded-For": "198.51.100.7", "Forwarded": "for=198.51.100.7",
        "X-Forwarded-Host": "outro", "Connection": "Accept", "Accept": "*/*",
        "Authorization": "Bearer teste",
    })
    headers = chamadas[-1].headers
    assert headers["x-forwarded-for"] == "192.0.2.10"
    assert headers["host"] == "usuarios-proxy:8000"
    assert headers["authorization"] == "Bearer teste"
    assert not {"forwarded", "x-forwarded-host", "connection", "accept"} & set(headers)


def test_preserva_desafio_bearer_e_redirecionamento_fica_no_gateway(ambiente):
    cliente, _, respostas = ambiente
    respostas["/usuarios"] = httpx.Response(401, headers={"WWW-Authenticate": "Bearer"})
    assert cliente.get("/usuarios").headers["www-authenticate"] == "Bearer"
    respostas["/usuarios/"] = httpx.Response(307, headers={"Location": "http://usuarios-proxy:8000/usuarios?perfil=tecnico"})
    resposta = cliente.get("/usuarios/")
    assert resposta.status_code == 307
    assert resposta.headers["location"] == "/usuarios?perfil=tecnico"


def test_resposta_comprimida_mantem_corpo_e_tamanho_corretos(ambiente):
    cliente, _, respostas = ambiente
    corpo = b'{"detail":"servico ocupado"}'
    respostas["/ativos"] = httpx.Response(
        503, content=gzip.compress(corpo), headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
    )
    resposta = cliente.get("/ativos")
    assert resposta.status_code == 503
    assert resposta.content == corpo
    assert int(resposta.headers["content-length"]) == len(corpo)
    assert "content-encoding" not in resposta.headers


@pytest.mark.parametrize("falha", ["timeout", "conexao"])
def test_falha_de_um_servico_preserva_os_outros(ambiente, monkeypatch, falha):
    cliente, _, respostas = ambiente
    monkeypatch.setattr(proxy, "GATEWAY_TIMEOUT_SEGUNDOS", 0.05)

    async def indisponivel(requisicao):
        if falha == "timeout":
            await asyncio.sleep(10)
        raise httpx.ConnectError("detalhe interno", request=requisicao)

    respostas["/ativos"] = indisponivel
    resposta = cliente.get("/ativos")
    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "Serviço de Inventário indisponível."}
    assert cliente.get("/chamados").status_code == 200
    assert cliente.get("/saude").json() == {"status": "ok", "servico": "gateway"}


@pytest.mark.parametrize("tamanho,fragmentado", [(65537, False), (65537, True)])
def test_limite_do_corpo_independe_de_content_length(ambiente, tamanho, fragmentado):
    cliente, chamadas, _ = ambiente
    corpo = b"x" * tamanho
    conteudo = iter([corpo[:40000], corpo[40000:]]) if fragmentado else corpo
    resposta = cliente.post("/chamados", content=conteudo)
    assert resposta.status_code == 413
    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert chamadas == []


def test_interface_e_arquivos_estaticos(ambiente):
    cliente, chamadas, _ = ambiente
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert resposta.headers["x-frame-options"] == "DENY"
    assert "script-src 'self'" in resposta.headers["content-security-policy"]
    assert 'src="/app.js"' in resposta.text and 'href="/estilo.css"' in resposta.text
    script = cliente.get("/app.js")
    assert 'const API = ""' in script.text and "const esc =" in script.text
    assert script.headers["content-type"].startswith("text/javascript")
    assert cliente.get("/estilo.css").headers["content-type"].startswith("text/css")
    assert cliente.get("/nao-existe").status_code == 404
    assert chamadas == []


def test_swagger_reune_esquemas_e_funciona_com_disponibilidade_parcial(ambiente):
    cliente, chamadas, respostas = ambiente

    async def esquema(requisicao):
        if requisicao.url.host == "inventario":
            return httpx.Response(503)
        caminho = "/usuarios" if requisicao.url.host == "usuarios-proxy" else "/chamados"
        return httpx.Response(200, json={"paths": {caminho: {}}, "components": {"schemas": {"Comum": {}}}})

    respostas["/openapi.json"] = esquema
    docs = cliente.get("/docs")
    assert docs.status_code == 200 and "/openapi.json" in docs.text
    dados = cliente.get("/openapi.json").json()
    assert set(dados["paths"]) == {"/usuarios", "/chamados"}
    assert dados["x-servicos-indisponiveis"] == ["Inventário"]
    assert dados["components"]["schemas"] == {"Comum": {}}
    assert len(chamadas) == 3
