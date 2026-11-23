import os

os.environ["DOCS"] = "1"
os.environ["USUARIOS_URL"] = "http://usuarios-proxy:8000"
os.environ["INVENTARIO_URL"] = "http://inventario:8000"
os.environ["CHAMADOS_URL"] = "http://chamados:8000"

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def ambiente(monkeypatch):
    chamadas = []
    respostas = {}

    async def responder(requisicao):
        chamadas.append(requisicao)
        resposta = respostas.get(requisicao.url.path)
        if callable(resposta):
            return await resposta(requisicao)
        if resposta is not None:
            return resposta
        return httpx.Response(200, json={"host": requisicao.url.host})

    def cliente_mock(**config):
        return httpx.AsyncClient(transport=httpx.MockTransport(responder), **config)

    monkeypatch.setattr(main, "AsyncClient", cliente_mock)
    with TestClient(main.app, client=("192.0.2.10", 12345), follow_redirects=False) as cliente:
        yield cliente, chamadas, respostas
