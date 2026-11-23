import json
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from conftest import SERVICOS, autenticar, docker


def dados_chamado(**alteracoes):
    return {"titulo": "Computador não liga", "descricao": "Validando o fluxo", "prioridade": "alta", **alteracoes}


def abrir(api, auth, **alteracoes):
    resposta = api.post("/chamados", headers=auth, json=dados_chamado(**alteracoes))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_gateway_interface_swagger_portas_e_bancos(api, ambiente):
    tela = api.get("/")
    assert tela.status_code == 200
    assert 'src="/app.js"' in tela.text
    assert "script-src 'self'" in tela.headers["content-security-policy"]
    assert tela.headers["x-frame-options"] == "DENY"
    assert tela.headers["x-content-type-options"] == "nosniff"
    assert api.get("/app.js").status_code == 200
    assert api.get("/estilo.css").status_code == 200
    assert api.get("/docs").status_code == 200
    paths = api.get("/openapi.json").json()["paths"]
    assert {"/auth/login", "/usuarios", "/ativos", "/chamados", "/notificacoes"} <= paths.keys()

    for servico in SERVICOS:
        cid = ambiente.container(servico)
        portas = json.loads(docker("inspect", "--format", "{{json .HostConfig.PortBindings}}", cid))
        volumes = json.loads(docker("inspect", "--format", "{{json .Mounts}}", cid))
        montagens = [volume for volume in volumes if volume["Type"] == "volume"]
        if servico == "gateway":
            assert set(portas) == {"8000/tcp"}
            assert portas["8000/tcp"][0]["HostIp"] == "127.0.0.1"
            assert not montagens
        else:
            assert not portas
            assert [(v["Name"], v["Destination"]) for v in montagens] == [
                (f"{ambiente.projeto}_dados_{servico}", "/dados"),
            ]


def test_rotas_exigem_token_pelo_gateway_e_na_rede_interna(api, ambiente):
    for rota in ("/auth/eu", "/usuarios", "/ativos", "/chamados", "/notificacoes"):
        resposta = api.get(rota)
        assert resposta.status_code == 401, rota
        assert resposta.headers["www-authenticate"] == "Bearer"

    # A consulta parte do gateway e usa o endereço interno de cada serviço.
    codigo = """
import httpx
for destino in ('usuarios:8000/usuarios', 'inventario:8000/ativos', 'chamados:8000/chamados'):
    resposta = httpx.get('http://' + destino, timeout=5, trust_env=False)
    assert resposta.status_code == 401, (destino, resposta.status_code)
    assert resposta.headers['www-authenticate'] == 'Bearer'
"""
    ambiente.compose("exec", "-T", "gateway", "python", "-c", codigo)


@pytest.mark.parametrize("caso", ["adulterado", "expirado", "sem_assinatura", "outro_segredo"])
def test_servicos_rejeitam_tokens_invalidos(api, ambiente, contas, caso):
    usuario_id, auth = contas["carla"]
    agora = datetime.now(timezone.utc)
    claims = {
        "sub": str(usuario_id), "perfil": "tecnico", "iss": "helpdesk-ti",
        "iat": agora - timedelta(minutes=10), "exp": agora + timedelta(minutes=5),
    }
    if caso == "adulterado":
        token = auth["Authorization"].split()[1] + ".invalido"
    elif caso == "expirado":
        claims["exp"] = agora - timedelta(minutes=1)
        token = jwt.encode(claims, ambiente.segredo, algorithm="HS256")
    elif caso == "sem_assinatura":
        token = jwt.encode(claims, None, algorithm="none")
    else:
        token = jwt.encode(claims, "chave-alternativa-exclusiva-dos-testes", algorithm="HS256")

    for rota in ("/auth/eu", "/ativos", "/chamados"):
        resposta = api.get(rota, headers={"Authorization": f"Bearer {token}"})
        assert resposta.status_code == 401, (caso, rota, resposta.status_code)


def test_fluxo_sla_perfis_privacidade_e_notificacoes(api, contas, ativo_id):
    ana_id, ana = contas["ana"]
    carla_id, carla = contas["carla"]
    chamado = abrir(api, ana, ativo_id=ativo_id, titulo="Chamado de integração")
    rota = f"/chamados/{chamado['id']}"
    assert chamado["solicitante_id"] == ana_id and chamado["status"] == "aberto"
    prazo = datetime.fromisoformat(chamado["prazo_sla"]) - datetime.fromisoformat(chamado["criado_em"])
    assert prazo == timedelta(hours=8)

    da_carla = abrir(api, carla, titulo="Chamado privado da técnica")
    assert api.get(f"/chamados/{da_carla['id']}", headers=ana).status_code == 404
    assert da_carla["id"] not in {c["id"] for c in api.get("/chamados", headers=ana).json()}
    dados_ativo = {"patrimonio": "PAT-INT", "tipo": "notebook", "descricao": "Exemplo", "setor": "TI"}
    assert api.post("/ativos", headers=ana, json=dados_ativo).status_code == 403
    assert api.post("/chamados", headers=ana, json=dados_chamado(solicitante_id=carla_id)).status_code == 422
    assert api.patch(f"{rota}/atribuir", headers=ana, json={"tecnico_id": carla_id}).status_code == 403
    assert api.patch(f"{rota}/status", headers=carla, json={"status": "fechado"}).status_code == 422

    atribuicao = api.patch(f"{rota}/atribuir", headers=carla, json={"tecnico_id": carla_id})
    assert atribuicao.status_code == 200 and atribuicao.json()["status"] == "em_atendimento"
    assert api.post(f"{rota}/comentarios", headers=carla, json={"texto": "Teste", "autor_id": ana_id}).status_code == 422
    comentario = api.post(f"{rota}/comentarios", headers=carla, json={"texto": "Atendimento realizado"})
    assert comentario.status_code == 201 and comentario.json()["autor_id"] == carla_id
    assert api.patch(f"{rota}/status", headers=carla, json={"status": "resolvido"}).json()["status"] == "resolvido"
    assert api.patch(f"{rota}/status", headers=ana, json={"status": "fechado"}).json()["status"] == "fechado"
    assert api.get(rota, headers=ana).json()["comentarios"] == [comentario.json()]
    painel = api.get("/chamados/painel", headers=ana).json()
    assert painel["por_status"]["fechado"] >= 1
    notificacoes = api.get("/notificacoes", headers=ana).json()
    assert all(n["destinatario_id"] == ana_id for n in notificacoes)
    assert {"ChamadoAberto", "ChamadoResolvido"} <= {n["tipo"] for n in notificacoes}
    assert "ChamadoAtribuido" in {n["tipo"] for n in api.get("/notificacoes", headers=carla).json()}


def test_perfil_atual_e_conta_desativada_valem_com_token_existente(api, ambiente, contas, ativo_id):
    resposta = api.post("/usuarios", headers=contas["admin"][1], json={
        "nome": "Técnico temporário", "email": "temporario@empresa.com", "perfil": "tecnico", "senha": ambiente.senha,
    })
    assert resposta.status_code == 201, resposta.text
    uid, auth = autenticar(api, "temporario@empresa.com", ambiente.senha)
    chamado = abrir(api, auth, titulo="Chamado do técnico temporário")
    rota = f"/chamados/{chamado['id']}/atribuir"
    assert api.patch(rota, headers=auth, json={"tecnico_id": uid}).status_code == 200

    # O sistema não expõe edição de contas. Ajusta somente o SQLite descartável
    # de Usuários para verificar o estado vigente sem emitir um token novo.
    codigo = """
import sqlite3
import sys
with sqlite3.connect('/dados/usuarios.db') as banco:
    resultado = banco.execute('UPDATE usuarios SET perfil = ?, ativo = ? WHERE id = ?',
                              ('solicitante', int(sys.argv[2]), int(sys.argv[1])))
    assert resultado.rowcount == 1
"""
    ambiente.compose("exec", "-T", "usuarios", "python", "-c", codigo, str(uid), "1")
    assert api.patch(rota, headers=auth, json={"tecnico_id": contas["carla"][0]}).status_code == 403
    dados = {"patrimonio": "PAT-PERFIL", "tipo": "notebook", "descricao": "Exemplo", "setor": "TI"}
    assert api.post("/ativos", headers=auth, json=dados).status_code == 403
    assert api.get(f"/ativos/{ativo_id}", headers=auth).status_code == 200

    ambiente.compose("exec", "-T", "usuarios", "python", "-c", codigo, str(uid), "0")
    for rota in ("/auth/eu", "/ativos", "/chamados"):
        assert api.get(rota, headers=auth).status_code == 401, rota


def test_gateway_limita_corpo_fragmentado_e_api_preserva_texto(api, contas):
    auth = contas["ana"][1]
    conteudo = iter([b"x" * 40000, b"x" * 30000])
    assert api.post("/chamados", headers=auth, content=conteudo).status_code == 413
    texto = '<strong data-demo="1">Com aspas e &</strong>'
    dado = abrir(api, auth, titulo=texto)
    assert api.get(f"/chamados/{dado['id']}", headers=auth).json()["titulo"] == texto


def test_ip_enviado_pelo_cliente_nao_reinicia_bloqueio_de_login(api):
    for tentativa in range(6):
        resposta = api.post("/auth/login", headers={"X-Forwarded-For": f"192.0.2.{tentativa + 1}"}, json={
            "email": "nao-existe@empresa.com", "senha": "Incorreta123",
        })
        assert resposta.status_code == (429 if tentativa == 5 else 401)


def test_inventario_parado_restringe_apenas_operacoes_dependentes(api, ambiente, contas, ativo_id):
    auth = contas["carla"][1]
    with ambiente.indisponivel("inventario"):
        assert api.get("/usuarios", headers=auth).status_code == 200
        assert api.get("/chamados", headers=auth).status_code == 200
        painel = api.get("/chamados/painel", headers=auth).json()
        avisos = api.get("/notificacoes", headers=auth).json()
        inicio = time.monotonic()
        resposta = api.post("/chamados", headers=auth, json=dados_chamado(ativo_id=ativo_id))
        assert resposta.status_code == 503
        assert resposta.json() == {"detail": "Serviço de Inventário indisponível."}
        assert time.monotonic() - inicio < 6
        assert api.get("/chamados/painel", headers=auth).json() == painel
        assert api.get("/notificacoes", headers=auth).json() == avisos
        assert abrir(api, auth, titulo="Sem equipamento durante a falha")["ativo_id"] is None

    assert api.get("/ativos", headers=auth).status_code == 200
    assert abrir(api, auth, ativo_id=ativo_id)["ativo_id"] == ativo_id


def test_usuarios_parado_bloqueia_autenticacao_sem_derrubar_gateway(api, ambiente, contas):
    auth = contas["carla"][1]
    with ambiente.indisponivel("usuarios"):
        for rota in ("/chamados", "/ativos"):
            resposta = api.get(rota, headers=auth)
            assert resposta.status_code == 503
            assert resposta.json() == {"detail": "Serviço de Usuários indisponível."}
        assert api.get("/saude").json() == {"status": "ok", "servico": "gateway"}
        assert api.get("/").status_code == 200
    assert api.get("/chamados", headers=auth).status_code == 200
