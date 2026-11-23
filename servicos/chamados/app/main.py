"""API de Chamados, comentários e notificações."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app import database
from app.chamados.rotas import router as chamados_router
from app.config import DOCS_ATIVA
from app.erros import ErroDeIntegracao, NaoEncontrado, RegraDeNegocio, SemPermissao
from app.notificacoes.rotas import router as notificacoes_router
from app.seguranca_http import CabecalhosDeSeguranca


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    try:
        database.Base.metadata.create_all(database.engine)
        async with AsyncClient(follow_redirects=False, trust_env=False, timeout=None) as cliente:
            app.state.cliente_http = cliente
            yield
    finally:
        database.engine.dispose()


app = FastAPI(
    title="HelpDesk TI — Serviço de Chamados", version="1.0.0", lifespan=ciclo_de_vida,
    docs_url="/docs" if DOCS_ATIVA else None, redoc_url=None,
    openapi_url="/openapi.json" if DOCS_ATIVA else None,
)
app.add_middleware(CabecalhosDeSeguranca)
app.include_router(chamados_router)
app.include_router(notificacoes_router)


@app.exception_handler(NaoEncontrado)
def tratar_nao_encontrado(request: Request, erro: NaoEncontrado):
    return JSONResponse(status_code=404, content={"detail": str(erro)})


@app.exception_handler(RegraDeNegocio)
def tratar_regra(request: Request, erro: RegraDeNegocio):
    return JSONResponse(status_code=422, content={"detail": str(erro)})


@app.exception_handler(SemPermissao)
def tratar_sem_permissao(request: Request, erro: SemPermissao):
    return JSONResponse(status_code=403, content={"detail": str(erro)})


@app.exception_handler(ErroDeIntegracao)
def tratar_integracao(request: Request, erro: ErroDeIntegracao):
    return JSONResponse(status_code=503, content={"detail": str(erro)})


@app.exception_handler(IntegrityError)
def tratar_integridade(request: Request, erro: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "O registro conflita com outro já existente."})


@app.exception_handler(StaleDataError)
def tratar_concorrencia(request: Request, erro: StaleDataError):
    return JSONResponse(status_code=409, content={"detail": "O chamado foi alterado. Atualize e tente novamente."})


@app.exception_handler(SQLAlchemyError)
def tratar_banco(request: Request, erro: SQLAlchemyError):
    return JSONResponse(status_code=503, content={"detail": "Banco de chamados indisponível."})


@app.get("/saude", tags=["Saúde"])
def saude(db: Session = Depends(database.get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "servico": "chamados"}
