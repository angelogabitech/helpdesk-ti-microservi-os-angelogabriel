import asyncio
import os

os.environ["JWT_SEGREDO"] = "segredo-exclusivo-dos-testes-de-chamados"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["USUARIOS_URL"] = "http://usuarios:8000"
os.environ["INVENTARIO_URL"] = "http://inventario:8000"
os.environ["USUARIOS_TIMEOUT_SEGUNDOS"] = "3"
os.environ["INVENTARIO_TIMEOUT_SEGUNDOS"] = "3"

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database, main


@pytest.fixture
def banco(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'chamados.db').as_posix()}")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    yield engine
    engine.dispose()


@pytest.fixture
def ambiente(banco, monkeypatch):
    perfis = {1: "solicitante", 2: "tecnico", 3: "solicitante", 4: "admin", 5: "tecnico"}
    chamadas = []
    respostas = {}

    async def responder(request):
        chamadas.append(request)
        url = (request.url.host, request.url.path)
        falha = respostas.get(url)
        if falha == "timeout":
            await asyncio.sleep(20)
        if falha == "conexao":
            raise httpx.ConnectError("detalhe interno", request=request)
        if callable(falha):
            return falha(request)
        if falha is not None:
            return falha
        if url == ("usuarios", "/auth/eu"):
            import jwt
            token = request.headers["authorization"].split()[1]
            usuario_id = int(jwt.decode(token, options={"verify_signature": False})["sub"])
            if usuario_id not in perfis:
                return httpx.Response(401)
            return httpx.Response(200, json={"id": usuario_id, "perfil": perfis[usuario_id]})
        if url[0] == "usuarios" and url[1].startswith("/usuarios/"):
            usuario_id = int(url[1].split("/")[-1])
            if usuario_id in perfis:
                return httpx.Response(200, json={"id": usuario_id, "perfil": perfis[usuario_id]})
        if url == ("inventario", "/ativos/7"):
            return httpx.Response(200, json={"id": 7, "patrimonio": "PAT-0007"})
        return httpx.Response(404)

    def cliente_mock(**config):
        return httpx.AsyncClient(transport=httpx.MockTransport(responder), **config)

    monkeypatch.setattr(main, "AsyncClient", cliente_mock)
    with TestClient(main.app) as cliente:
        yield cliente, chamadas, respostas, perfis
