"""API de Inventário com banco exclusivo e autenticação via Usuários."""
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import dados_exemplo, database
from app.config import DOCS_ATIVA, USUARIOS_TIMEOUT_SEGUNDOS, USUARIOS_URL
from app.erros import NaoEncontrado, RegraDeNegocio
from app.inventario.rotas import router
from app.seguranca_http import CabecalhosDeSeguranca


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    try:
        database.Base.metadata.create_all(database.engine)
        if os.getenv("DADOS_EXEMPLO", "1") == "1":
            with database.SessionLocal() as db:
                dados_exemplo.carregar(db)
        async with AsyncClient(
            base_url=USUARIOS_URL,
            timeout=USUARIOS_TIMEOUT_SEGUNDOS,
            follow_redirects=False,
            trust_env=False,
        ) as cliente:
            app.state.cliente_usuarios = cliente
            yield
    finally:
        database.engine.dispose()


app = FastAPI(
    title="HelpDesk TI — Serviço de Inventário",
    version="1.0.0",
    lifespan=ciclo_de_vida,
    docs_url="/docs" if DOCS_ATIVA else None,
    redoc_url=None,
    openapi_url="/openapi.json" if DOCS_ATIVA else None,
)
app.add_middleware(CabecalhosDeSeguranca)
app.include_router(router)


@app.exception_handler(NaoEncontrado)
def tratar_nao_encontrado(request: Request, erro: NaoEncontrado):
    return JSONResponse(status_code=404, content={"detail": str(erro)})


@app.exception_handler(RegraDeNegocio)
def tratar_regra(request: Request, erro: RegraDeNegocio):
    return JSONResponse(status_code=422, content={"detail": str(erro)})


@app.exception_handler(IntegrityError)
def tratar_conflito(request: Request, erro: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "O registro conflita com outro já existente."})


@app.exception_handler(SQLAlchemyError)
def tratar_banco(request: Request, erro: SQLAlchemyError):
    return JSONResponse(status_code=503, content={"detail": "Banco de inventário indisponível."})


@app.get("/saude", tags=["Saúde"])
def saude(db: Session = Depends(database.get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "servico": "inventario"}
