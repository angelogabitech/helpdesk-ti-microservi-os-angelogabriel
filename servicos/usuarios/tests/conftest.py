"""Cada teste usa um banco temporário; nenhum segredo real é carregado."""
import os

os.environ["JWT_SEGREDO"] = "segredo-exclusivo-dos-testes-com-mais-de-32-caracteres"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DADOS_EXEMPLO"] = "0"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database
from app.auth import limite
from app.main import app
from app.usuarios import servico
from app.usuarios.esquemas import UsuarioCriar

SENHA = "Senha123"


@pytest.fixture
def sessao(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'usuarios.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", fabrica)
    monkeypatch.setenv("DADOS_EXEMPLO", "0")
    limite.limpar_tudo()
    yield fabrica
    engine.dispose()
    limite.limpar_tudo()


@pytest.fixture
def cliente(sessao):
    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture
def contas(cliente, sessao):
    resultado = {}
    with sessao() as db:
        for apelido, nome, perfil in (
            ("admin", "Admin", "admin"),
            ("ana", "Ana", "solicitante"),
            ("carla", "Carla", "tecnico"),
        ):
            usuario = servico.criar(db, UsuarioCriar(
                nome=nome, email=f"{apelido}@empresa.com", perfil=perfil, senha=SENHA,
            ))
            resultado[apelido] = {"id": usuario.id}
    for apelido in resultado:
        resposta = cliente.post("/auth/login", json={"email": f"{apelido}@empresa.com", "senha": SENHA})
        assert resposta.status_code == 200
        resultado[apelido]["headers"] = {"Authorization": f"Bearer {resposta.json()['access_token']}"}
    return resultado
