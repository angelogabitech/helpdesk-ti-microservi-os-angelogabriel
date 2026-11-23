from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app import database, integracoes
from app.chamados.modelos import Chamado
from app.config import JWT_EMISSOR, JWT_SEGREDO
from app.notificacoes import servico as notificacoes


def autorizar(usuario=1, **alteracoes):
    agora = datetime.now(timezone.utc)
    campos = {"iss": JWT_EMISSOR, "sub": str(usuario), "iat": agora,
              "exp": agora + timedelta(minutes=5), "perfil": "admin", **alteracoes}
    token = jwt.encode(campos, JWT_SEGREDO, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def abrir(cliente, usuario=1, **alteracoes):
    dados = {"titulo": "PC não liga", "descricao": "Nada acontece", "prioridade": "alta", **alteracoes}
    return cliente.post("/chamados", json=dados, headers=autorizar(usuario))


def avisos(cliente, usuario=1):
    resposta = cliente.get("/notificacoes", headers=autorizar(usuario))
    assert resposta.status_code == 200
    return [aviso["tipo"] for aviso in resposta.json()]


@pytest.mark.parametrize("prioridade,horas", [("critica", 4), ("alta", 8), ("media", 24), ("baixa", 72)])
def test_sla_e_abertura_com_equipamento(ambiente, prioridade, horas):
    cliente, chamadas, _, _ = ambiente
    resposta = abrir(cliente, ativo_id=7, prioridade=prioridade)
    assert resposta.status_code == 201
    dados = resposta.json()
    assert dados["ativo_id"] == 7 and dados["solicitante_id"] == 1
    assert dados["status"] == "aberto" and dados["comentarios"] == []
    assert datetime.fromisoformat(dados["prazo_sla"]) - datetime.fromisoformat(dados["criado_em"]) == timedelta(hours=horas)
    assert [(r.url.host, r.url.path) for r in chamadas] == [("usuarios", "/auth/eu"), ("inventario", "/ativos/7")]
    assert chamadas[0].headers["authorization"] == chamadas[1].headers["authorization"]
    assert avisos(cliente) == ["ChamadoAberto"]


def test_fluxo_completo_com_permissoes_e_notificacoes(ambiente):
    cliente, chamadas, _, _ = ambiente
    cid = abrir(cliente).json()["id"]
    rota = f"/chamados/{cid}"
    tec, ana = autorizar(2), autorizar()
    assert cliente.patch(rota + "/status", headers=tec, json={"status": "em_atendimento"}).status_code == 422
    assert cliente.patch(rota + "/atribuir", headers=ana, json={"tecnico_id": 2}).status_code == 403
    chamadas.clear()
    atribuicao = cliente.patch(rota + "/atribuir", headers=tec, json={"tecnico_id": 2})
    assert atribuicao.json()["status"] == "em_atendimento"
    assert [r.url.path for r in chamadas] == ["/auth/eu", "/usuarios/2"]
    assert all(r.headers["authorization"] == tec["Authorization"] for r in chamadas)
    comentario = cliente.post(rota + "/comentarios", headers=tec, json={"texto": "Verificando a fonte"})
    assert comentario.status_code == 201 and comentario.json()["autor_id"] == 2
    assert cliente.get(rota, headers=ana).json()["comentarios"] == [comentario.json()]
    assert cliente.patch(rota + "/status", headers=tec, json={"status": "resolvido"}).status_code == 200
    assert cliente.patch(rota + "/status", headers=ana, json={"status": "em_atendimento"}).status_code == 200
    assert cliente.patch(rota + "/status", headers=tec, json={"status": "resolvido"}).status_code == 200
    assert cliente.patch(rota + "/status", headers=ana, json={"status": "fechado"}).json()["status"] == "fechado"
    assert cliente.post(rota + "/comentarios", headers=tec, json={"texto": "Teste"}).status_code == 422
    assert avisos(cliente, 2) == ["ChamadoAtribuido"]
    assert avisos(cliente, 1) == ["ChamadoAberto", "ChamadoResolvido", "ChamadoResolvido"]
    assert avisos(cliente, 3) == []


def test_privacidade_filtro_painel_e_sla_vencido(ambiente):
    cliente, _, _, _ = ambiente
    cid = abrir(cliente).json()["id"]
    outro = abrir(cliente, 3).json()["id"]
    with database.SessionLocal.begin() as db:
        db.get(Chamado, cid).prazo_sla = datetime.now() - timedelta(minutes=1)
    headers = autorizar()
    assert cliente.get(f"/chamados/{outro}", headers=headers).status_code == 404
    assert [c["id"] for c in cliente.get("/chamados", headers=headers).json()] == [cid]
    assert cliente.get("/chamados", params={"status": "fechado"}, headers=headers).json() == []
    assert cliente.get("/chamados/painel", headers=headers).json() == {
        "total": 1, "por_status": {"aberto": 1}, "atrasados": 1,
    }
    assert cliente.get("/chamados/painel", headers=autorizar(2)).json()["total"] == 2


@pytest.mark.parametrize("tecnico,status", [(999, 404), (1, 422)])
def test_tecnico_ausente_ou_perfil_invalido(ambiente, tecnico, status):
    cliente, _, _, _ = ambiente
    cid = abrir(cliente).json()["id"]
    rota = f"/chamados/{cid}"
    assert cliente.patch(rota + "/atribuir", headers=autorizar(2), json={"tecnico_id": tecnico}).status_code == status
    assert cliente.get(rota, headers=autorizar()).json()["tecnico_id"] is None
    assert avisos(cliente, 2) == []


def test_ativo_inexistente(ambiente):
    cliente, _, _, _ = ambiente
    assert abrir(cliente, ativo_id=999).status_code == 404
    assert cliente.get("/chamados", headers=autorizar()).json() == []


@pytest.mark.parametrize("falha", ["timeout", "conexao", "resposta_invalida"])
def test_falha_inventario_isola_abertura_com_equipamento(ambiente, monkeypatch, falha):
    cliente, _, respostas, _ = ambiente
    monkeypatch.setattr(integracoes, "INVENTARIO_TIMEOUT_SEGUNDOS", 0.08)
    respostas["inventario", "/ativos/7"] = (
        httpx.Response(200, json={"id": 99}) if falha == "resposta_invalida" else falha
    )
    resposta = abrir(cliente, ativo_id=7)
    assert resposta.status_code == 503
    assert resposta.json() == {"detail": "Serviço de Inventário indisponível."}
    assert cliente.get("/chamados", headers=autorizar()).json() == []
    assert avisos(cliente) == []
    assert abrir(cliente).status_code == 201
    assert cliente.get("/chamados/painel", headers=autorizar()).json()["total"] == 1


def test_falha_usuarios_na_atribuicao_preserva_estado(ambiente):
    cliente, _, respostas, _ = ambiente
    cid = abrir(cliente).json()["id"]
    respostas["usuarios", "/usuarios/2"] = httpx.Response(503)
    rota = f"/chamados/{cid}"
    resposta = cliente.patch(rota + "/atribuir", headers=autorizar(2), json={"tecnico_id": 2})
    assert resposta.status_code == 503 and resposta.json() == {"detail": "Serviço de Usuários indisponível."}
    chamado = cliente.get(rota, headers=autorizar()).json()
    assert chamado["status"] == "aberto" and chamado["tecnico_id"] is None
    assert avisos(cliente, 2) == []


def test_usuarios_indisponivel_mantem_saude_publica(ambiente):
    cliente, _, respostas, _ = ambiente
    respostas["usuarios", "/auth/eu"] = "conexao"
    assert cliente.get("/chamados", headers=autorizar()).status_code == 503
    assert cliente.get("/saude").json() == {"status": "ok", "servico": "chamados"}


def test_token_invalido_perfil_atual_e_campos_extras(ambiente):
    cliente, chamadas, _, perfis = ambiente
    assert cliente.get("/notificacoes").status_code == 401
    assert cliente.get("/chamados", headers=autorizar(exp=datetime.now(timezone.utc))).status_code == 401
    assert chamadas == []
    assert cliente.get("/chamados", headers=autorizar(6)).status_code == 401
    assert abrir(cliente, solicitante_id=2).status_code == 422
    cid = abrir(cliente).json()["id"]
    assert cliente.post(f"/chamados/{cid}/comentarios", headers=autorizar(2),
                        json={"texto": "comentário", "autor_id": 1}).status_code == 422
    perfis[2] = "solicitante"
    assert cliente.patch(f"/chamados/{cid}/atribuir", headers=autorizar(2), json={"tecnico_id": 5}).status_code == 403


def test_banco_exclusivo_e_chave_interna(ambiente, banco):
    cliente, _, _, _ = ambiente
    assert cliente.get("/saude").status_code == 200
    esquema = inspect(banco)
    assert esquema.get_table_names() == ["chamados", "comentarios", "notificacoes"]
    assert not esquema.get_foreign_keys("chamados")
    assert [chave["referred_table"] for chave in esquema.get_foreign_keys("comentarios")] == ["chamados"]
    assert not esquema.get_foreign_keys("notificacoes")


def test_falha_na_notificacao_reverte_chamado(ambiente, monkeypatch):
    cliente, _, _, _ = ambiente

    def falhar(*args):
        raise IntegrityError("detalhe interno", {}, ValueError())

    monkeypatch.setattr(notificacoes, "notificar", falhar)
    assert abrir(cliente).status_code == 409
    with database.SessionLocal() as db:
        assert db.scalars(select(Chamado)).all() == []


def test_atribuicao_concorrente_preserva_alteracao_e_nao_notifica(ambiente):
    cliente, _, respostas, _ = ambiente
    cid = abrir(cliente).json()["id"]

    def alterar_antes_de_responder(_):
        with database.SessionLocal.begin() as db:
            chamado = db.get(Chamado, cid)
            chamado.tecnico_id = 5
            chamado.status = "em_atendimento"
        return httpx.Response(200, json={"id": 2, "perfil": "tecnico"})

    respostas["usuarios", "/usuarios/2"] = alterar_antes_de_responder
    rota = f"/chamados/{cid}"
    resposta = cliente.patch(rota + "/atribuir", headers=autorizar(2), json={"tecnico_id": 2})
    assert resposta.status_code == 409
    assert cliente.get(rota, headers=autorizar()).json()["tecnico_id"] == 5
    assert avisos(cliente, 2) == []
