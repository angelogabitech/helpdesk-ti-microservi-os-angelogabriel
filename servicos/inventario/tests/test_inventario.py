from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.config import JWT_EMISSOR, JWT_SEGREDO
from app.inventario.repositorio import listar
from app.main import app
from app import database, identidade

ATIVO = {"patrimonio": "PAT-NOVO", "tipo": "notebook", "descricao": "Notebook de teste", "setor": "TI"}


def autorizar(segredo=JWT_SEGREDO, algoritmo="HS256", **campos):
    agora = datetime.now(timezone.utc)
    dados = {"sub": "7", "iss": JWT_EMISSOR, "iat": agora,
             "exp": agora + timedelta(minutes=10), "perfil": "admin"}
    dados.update(campos)
    token = jwt.encode(dados, segredo, algorithm=algoritmo)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("perfil", ["tecnico", "admin"])
def test_cria_lista_filtra_e_consulta_ativos(ambiente, perfil):
    cliente, respostas, chamadas = ambiente
    respostas["perfil"] = perfil
    headers = autorizar()
    criacao = cliente.post("/ativos", json=ATIVO, headers=headers)
    assert criacao.status_code == 201
    ativo = criacao.json()
    assert ativo == {"id": ativo["id"], **ATIVO}
    assert cliente.get(f"/ativos/{ativo['id']}", headers=headers).json() == ativo
    assert cliente.get("/ativos", params={"setor": "TI"}, headers=headers).json() == [ativo]
    assert cliente.get("/ativos", params={"setor": "RH"}, headers=headers).json() == []
    assert cliente.get("/ativos/999", headers=headers).status_code == 404
    assert len(chamadas) == 5
    assert all(
        chamada.method == "GET" and chamada.url.path == "/auth/eu"
        and chamada.headers["authorization"] == headers["Authorization"]
        for chamada in chamadas
    )


def test_perfil_atual_prevalece_sobre_jwt_e_cabecalhos(ambiente):
    cliente, respostas, _ = ambiente
    respostas["perfil"] = "solicitante"
    headers = {**autorizar(), "X-User-Role": "admin"}
    assert cliente.get("/ativos", headers=headers).status_code == 200
    assert cliente.post("/ativos", json=ATIVO, headers=headers).status_code == 403
    assert cliente.get("/ativos", headers=headers).json() == []
    respostas["perfil"] = "tecnico"
    assert cliente.post("/ativos", json=ATIVO, headers=headers).status_code == 201


def test_recusa_duplicado_campos_extras_e_filtro_longo(ambiente):
    cliente, _, _ = ambiente
    headers = autorizar()
    assert cliente.post("/ativos", json=ATIVO, headers=headers).status_code == 201
    assert cliente.post("/ativos", json=ATIVO, headers=headers).status_code == 422
    assert cliente.post("/ativos", json={**ATIVO, "id": 20}, headers=headers).status_code == 422
    assert cliente.get("/ativos", params={"setor": "x" * 81}, headers=headers).status_code == 422
    assert len(cliente.get("/ativos", headers=headers).json()) == 1


@pytest.mark.parametrize("caso", ["ausente", "adulterado", "expirado", "outro_emissor", "sem_assinatura", "sub_invalido"])
def test_token_invalido_e_recusado_sem_chamar_usuarios(ambiente, caso):
    cliente, _, chamadas = ambiente
    if caso == "ausente":
        headers = {}
    elif caso == "adulterado":
        headers = autorizar()
        headers["Authorization"] += ".extra"
    elif caso == "expirado":
        headers = autorizar(exp=datetime.now(timezone.utc) - timedelta(minutes=1))
    elif caso == "outro_emissor":
        headers = autorizar(iss="outro-servico")
    elif caso == "sem_assinatura":
        headers = autorizar(segredo=None, algoritmo="none")
    else:
        headers = autorizar(sub="-7")
    resposta = cliente.get("/ativos", headers=headers)
    assert resposta.status_code == 401
    assert resposta.headers["www-authenticate"] == "Bearer"
    assert chamadas == []


@pytest.mark.parametrize("falha", ["timeout", "pendente", "conexao", 503, 302, "json", "id", "perfil", 401])
def test_falha_na_identidade_bloqueia_escrita_mas_preserva_saude(ambiente, monkeypatch, falha):
    cliente, respostas, chamadas = ambiente
    respostas["falha"] = falha
    if falha == "perfil":
        respostas["perfil"] = "superadmin"
    if falha == "pendente":
        monkeypatch.setattr(identidade, "USUARIOS_TIMEOUT_SEGUNDOS", 0.05)
    resposta = cliente.post("/ativos", json=ATIVO, headers=autorizar())
    if falha == 401:
        assert resposta.status_code == 401
        assert resposta.headers["www-authenticate"] == "Bearer"
    else:
        assert resposta.status_code == 503
        assert resposta.json() == {"detail": "Serviço de Usuários indisponível."}
    assert len(chamadas) == 1
    assert cliente.get("/saude").json() == {"status": "ok", "servico": "inventario"}
    assert len(chamadas) == 1
    with database.SessionLocal() as db:
        assert listar(db) == []


def test_banco_exclusivo_e_exemplos_persistem_sem_duplicar(banco, monkeypatch):
    monkeypatch.setenv("DADOS_EXEMPLO", "1")
    for _ in range(2):
        with TestClient(app) as cliente:
            assert cliente.get("/saude").status_code == 200
            assert inspect(banco).get_table_names() == ["ativos"]
            with database.SessionLocal() as db:
                assert [ativo.patrimonio for ativo in listar(db)] == ["PAT-0001", "PAT-0002", "PAT-0003"]


def test_limite_do_corpo_antes_da_consulta_de_identidade(ambiente):
    cliente, _, chamadas = ambiente
    resposta = cliente.post("/ativos", headers=autorizar(), content=b"x" * 65537)
    assert resposta.status_code == 413
    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert chamadas == []
