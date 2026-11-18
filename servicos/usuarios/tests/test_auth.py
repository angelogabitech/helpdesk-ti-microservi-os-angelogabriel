from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import config
from app.auth import limite
from app.usuarios.modelos import Usuario


@pytest.mark.parametrize("metodo,rota", [
    ("get", "/auth/eu"), ("get", "/usuarios"), ("get", "/usuarios/1"), ("post", "/usuarios"),
])
def test_rotas_exigem_login(cliente, metodo, rota):
    resposta = getattr(cliente, metodo)(rota)
    assert resposta.status_code == 401
    assert resposta.headers["www-authenticate"] == "Bearer"


def test_login_e_identidade_compativeis_com_monolito(cliente, contas):
    resposta = cliente.post("/auth/login", json={"email": "ANA@empresa.com", "senha": "Senha123"})
    assert resposta.status_code == 200
    dados = resposta.json()
    assert set(dados) == {"access_token", "token_type", "expira_em", "usuario"}
    assert dados["token_type"] == "bearer"
    assert dados["usuario"] == {
        "id": contas["ana"]["id"], "nome": "Ana", "email": "ana@empresa.com", "perfil": "solicitante",
    }
    assert datetime.fromisoformat(dados["expira_em"]) > datetime.now(timezone.utc)
    eu = cliente.get("/auth/eu", headers=contas["ana"]["headers"])
    assert eu.json() == dados["usuario"]
    assert resposta.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("email", ["ana@empresa.com", "inexistente@empresa.com"])
def test_credenciais_erradas_nao_revelam_existencia(cliente, contas, email):
    resposta = cliente.post("/auth/login", json={"email": email, "senha": "Errada123"})
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "E-mail ou senha inválidos."}


def test_bloqueio_nao_pode_ser_contornado_por_cabecalho_de_proxy(cliente, contas):
    for numero in range(config.LOGIN_MAX_FALHAS):
        resposta = cliente.post(
            "/auth/login", json={"email": "ana@empresa.com", "senha": "Errada123"},
            headers={"X-Forwarded-For": f"198.51.100.{numero}"},
        )
        assert resposta.status_code == 401
    resposta = cliente.post("/auth/login", json={"email": "ana@empresa.com", "senha": "Senha123"})
    assert resposta.status_code == 429


def test_bloqueio_expira_apos_janela(cliente, contas, monkeypatch):
    agora = [100.0]
    monkeypatch.setattr(limite.time, "monotonic", lambda: agora[0])
    for _ in range(config.LOGIN_MAX_FALHAS):
        cliente.post("/auth/login", json={"email": "ana@empresa.com", "senha": "Errada123"})
    agora[0] += config.LOGIN_JANELA_SEGUNDOS + 1
    assert cliente.post("/auth/login", json={"email": "ana@empresa.com", "senha": "Senha123"}).status_code == 200


@pytest.mark.parametrize("caso", [
    "adulterado", "outro_segredo", "sem_assinatura", "expirado", "emissor_incorreto", "sem_exp",
    "sub_invalido", "sub_lista", "sub_negativo",
])
def test_tokens_invalidos_sao_recusados(cliente, contas, caso):
    agora = datetime.now(timezone.utc)
    dados = {"sub": str(contas["admin"]["id"]), "iss": config.JWT_EMISSOR,
             "iat": agora, "exp": agora + timedelta(minutes=5)}
    segredo, algoritmo = config.JWT_SEGREDO, "HS256"
    if caso == "outro_segredo":
        segredo = "segredo-que-nao-pertence-ao-servico-com-32-caracteres"
    elif caso == "sem_assinatura":
        segredo, algoritmo = None, "none"
    elif caso == "expirado":
        dados.update(iat=agora - timedelta(hours=2), exp=agora - timedelta(hours=1))
    elif caso == "emissor_incorreto":
        dados["iss"] = "outra-aplicacao"
    elif caso == "sem_exp":
        dados.pop("exp")
    elif caso == "sub_invalido":
        dados["sub"] = "abc"
    elif caso == "sub_lista":
        dados["sub"] = []
    elif caso == "sub_negativo":
        dados["sub"] = "-1"
    token = jwt.encode(dados, segredo, algorithm=algoritmo)
    if caso == "adulterado":
        token += "x"
    assert cliente.get("/auth/eu", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_usuario_desativado_perde_acesso_com_token_ainda_valido(cliente, contas, sessao):
    with sessao() as db:
        db.get(Usuario, contas["ana"]["id"]).ativo = False
        db.commit()
    assert cliente.get("/auth/eu", headers=contas["ana"]["headers"]).status_code == 401
    assert cliente.post("/auth/login", json={"email": "ana@empresa.com", "senha": "Senha123"}).status_code == 401


def test_mudanca_de_perfil_vale_para_token_existente(cliente, contas, sessao):
    with sessao() as db:
        db.get(Usuario, contas["admin"]["id"]).perfil = "solicitante"
        db.commit()
    resposta = cliente.post("/usuarios", headers=contas["admin"]["headers"], json={
        "nome": "Novo", "email": "novo@empresa.com", "perfil": "admin", "senha": "Senha123",
    })
    assert resposta.status_code == 403
    assert cliente.get("/auth/eu", headers=contas["admin"]["headers"]).json()["perfil"] == "solicitante"


def test_token_de_usuario_inexistente(cliente):
    from app.auth.tokens import criar
    token, _ = criar(999, "admin")
    assert cliente.get("/auth/eu", headers={"Authorization": f"Bearer {token}"}).status_code == 401
