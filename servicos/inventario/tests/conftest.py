import asyncio
import os

os.environ["JWT_SEGREDO"] = "segredo-exclusivo-dos-testes-do-inventario"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["USUARIOS_URL"] = "http://usuarios:8000"

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database, main


@pytest.fixture
def banco(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'inventario.db').as_posix()}")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setenv("DADOS_EXEMPLO", "0")
    yield engine
    engine.dispose()


@pytest.fixture
def ambiente(banco, monkeypatch):
    respostas = {"perfil": "tecnico", "falha": None}
    chamadas = []

    async def responder(request):
        chamadas.append(request)
        falha = respostas["falha"]
        if falha == "timeout":
            raise httpx.ReadTimeout("detalhe interno", request=request)
        if falha == "pendente":
            await asyncio.sleep(10)
        if falha == "conexao":
            raise httpx.ConnectError("detalhe interno", request=request)
        if isinstance(falha, int):
            return httpx.Response(falha, text="detalhe interno")
        if falha == "json":
            return httpx.Response(200, text="detalhe interno")
        if falha == "id":
            return httpx.Response(200, json={"id": 99, "perfil": "tecnico"})
        return httpx.Response(200, json={"id": 7, "nome": "Carla", "perfil": respostas["perfil"]})

    def cliente_mock(**config):
        return httpx.AsyncClient(transport=httpx.MockTransport(responder), **config)

    monkeypatch.setattr(main, "AsyncClient", cliente_mock)
    with TestClient(main.app) as cliente:
        yield cliente, respostas, chamadas
