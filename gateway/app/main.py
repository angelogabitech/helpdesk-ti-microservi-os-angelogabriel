"""Serve a interface e encaminha as rotas da API."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from httpx import AsyncClient

from app.config import DOCS_ATIVA
from app.proxy import CHAMADOS, DESTINOS, INVENTARIO, USUARIOS, encaminhar, enviar
from app.seguranca_http import CabecalhosDeSeguranca

WEB = Path(__file__).parent / "web"
METODOS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    async with AsyncClient(follow_redirects=False, trust_env=False, timeout=None) as cliente:
        app.state.cliente_http = cliente
        yield


app = FastAPI(
    title="HelpDesk TI — Gateway", lifespan=ciclo_de_vida,
    docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False,
)
app.add_middleware(CabecalhosDeSeguranca)


@app.get("/saude")
def saude():
    return {"status": "ok", "servico": "gateway"}


@app.get("/")
def tela():
    return FileResponse(WEB / "index.html")


@app.get("/app.js")
def javascript():
    return FileResponse(WEB / "app.js", media_type="text/javascript")


@app.get("/estilo.css")
def estilo():
    return FileResponse(WEB / "estilo.css", media_type="text/css")


if DOCS_ATIVA:
    @app.get("/docs")
    def documentacao():
        return get_swagger_ui_html(openapi_url="/openapi.json", title="HelpDesk TI — API")

    @app.get("/openapi.json")
    async def esquema_api(request: Request):
        async def consultar(destino):
            try:
                url = destino.url.copy_with(raw_path=b"/openapi.json")
                resposta = await enviar(request.app.state.cliente_http, httpx.Request("GET", url))
                resposta.raise_for_status()
                documento = resposta.json()
                if isinstance(documento, dict) and isinstance(documento.get("paths"), dict):
                    return documento
            except (httpx.HTTPError, TimeoutError, ValueError):
                pass
            return None

        destinos = (USUARIOS, INVENTARIO, CHAMADOS)
        documentos = await asyncio.gather(*(consultar(destino) for destino in destinos))
        combinado = {"openapi": "3.1.0", "info": {"title": "HelpDesk TI", "version": "2.0.0"},
                     "paths": {}, "components": {}}
        indisponiveis = []
        for destino, documento in zip(destinos, documentos):
            if documento is None:
                indisponiveis.append(destino.nome)
                continue
            combinado["paths"].update(documento["paths"])
            for grupo, entradas in documento.get("components", {}).items():
                combinado["components"].setdefault(grupo, {}).update(entradas)
        if not combinado["paths"]:
            raise HTTPException(503, "Documentação dos serviços indisponível.")
        if indisponiveis:
            combinado["x-servicos-indisponiveis"] = indisponiveis
        return combinado


@app.api_route("/{prefixo}", methods=METODOS)
@app.api_route("/{prefixo}/{restante:path}", methods=METODOS)
async def api(prefixo: str, request: Request, restante: str = ""):
    destino = DESTINOS.get(prefixo)
    if destino is None:
        raise HTTPException(404, "Rota não encontrada.")
    return await encaminhar(request, destino)
