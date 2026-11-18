import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError, OperationalError

from app import database
from app.main import app


def test_saude_publica_e_banco_exclusivo(cliente):
    resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "servico": "usuarios"}
    assert inspect(database.engine).get_table_names() == ["usuarios"]


@pytest.mark.parametrize("erro,status", [
    (OperationalError("detalhes-internos", {}, Exception("banco secreto")), 503),
    (IntegrityError("detalhes-internos", {}, Exception("banco secreto")), 409),
])
def test_erros_de_banco_nao_vazam_detalhes(cliente, monkeypatch, erro, status):
    class SessaoComFalha:
        def execute(self, *args):
            raise erro

    def obter_sessao_com_falha():
        yield SessaoComFalha()

    app.dependency_overrides[database.get_db] = obter_sessao_com_falha
    try:
        resposta = cliente.get("/saude")
        assert resposta.status_code == status
        assert "detalhes-internos" not in resposta.text
        assert "banco secreto" not in resposta.text
    finally:
        app.dependency_overrides.clear()


def test_dados_exemplo_idempotentes_e_token_valido_apos_reinicio(sessao, monkeypatch):
    monkeypatch.setenv("DADOS_EXEMPLO", "1")
    monkeypatch.setenv("SENHA_EXEMPLO", "Exemplo123")
    with TestClient(app) as primeiro:
        login = primeiro.post("/auth/login", json={"email": "carla@empresa.com", "senha": "Exemplo123"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        usuarios = primeiro.get("/usuarios", headers=headers).json()
        assert len(usuarios) == 5
    with TestClient(app) as segundo:
        assert segundo.get("/auth/eu", headers=headers).status_code == 200
        assert segundo.get("/usuarios", headers=headers).json() == usuarios


def test_exemplos_desativados_nao_criam_usuarios(cliente, sessao):
    from app.usuarios.servico import listar
    with sessao() as db:
        assert listar(db) == []


@pytest.mark.parametrize("segredo", [None, "curto", " " * 40])
def test_configuracao_exige_segredo_explicito(segredo):
    ambiente = os.environ.copy()
    ambiente.pop("JWT_SEGREDO", None)
    if segredo is not None:
        ambiente["JWT_SEGREDO"] = segredo
    resultado = subprocess.run(
        [sys.executable, "-c", "import app.config"],
        cwd=Path(__file__).resolve().parents[1], env=ambiente,
        capture_output=True, text=True, timeout=15,
    )
    assert resultado.returncode != 0
    assert "Configure JWT_SEGREDO" in resultado.stderr


@pytest.mark.parametrize("com_tamanho", [True, False])
def test_limite_64kb_com_e_sem_content_length(cliente, com_tamanho):
    corpo = b"x" * (64 * 1024 + 1)
    conteudo = corpo if com_tamanho else iter([corpo[:40000], corpo[40000:]])
    resposta = cliente.post("/auth/login", content=conteudo)
    assert resposta.status_code == 413
    assert resposta.headers["x-content-type-options"] == "nosniff"


def test_cabecalhos_de_seguranca(cliente):
    resposta = cliente.get("/saude")
    assert "script-src 'self'" in resposta.headers["content-security-policy"]
    assert resposta.headers["x-frame-options"] == "DENY"
    assert resposta.headers["x-content-type-options"] == "nosniff"


def test_nao_expoe_rotas_de_outros_dominios(cliente):
    for rota in ("/ativos", "/chamados", "/notificacoes", "/"):
        assert cliente.get(rota).status_code == 404
