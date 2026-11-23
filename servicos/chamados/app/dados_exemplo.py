"""Carrega chamados de aula após consultar as APIs vizinhas via HTTP."""
import asyncio
import os

import httpx
from pydantic import TypeAdapter
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.chamados import servico
from app.chamados.esquemas import ChamadoCriar
from app.chamados.modelos import Chamado
from app.config import INVENTARIO_TIMEOUT_SEGUNDOS, INVENTARIO_URL, USUARIOS_TIMEOUT_SEGUNDOS, USUARIOS_URL
from app.database import SessionLocal
from app.integracoes import Identidade, Recurso


class AtivoExemplo(Recurso):
    patrimonio: str


async def entrar(cliente: httpx.AsyncClient, email: str, senha: str, perfil: str) -> tuple[Identidade, str]:
    async with asyncio.timeout(USUARIOS_TIMEOUT_SEGUNDOS):
        resposta = await cliente.post(f"{USUARIOS_URL}/auth/login", json={"email": email, "senha": senha})
    resposta.raise_for_status()
    dados = resposta.json()
    usuario = Identidade.model_validate(dados["usuario"])
    token = dados["access_token"]
    if usuario.perfil != perfil or not isinstance(token, str) or not token:
        raise ValueError("Conta de exemplo inválida.")
    return usuario, token


async def consultar_exemplos():
    senha = os.getenv("SENHA_EXEMPLO", "Helpdesk2026")
    async with httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=None) as cliente:
        ana, _ = await entrar(cliente, "ana@empresa.com", senha, "solicitante")
        bruno, _ = await entrar(cliente, "bruno@empresa.com", senha, "solicitante")
        carla, token = await entrar(cliente, "carla@empresa.com", senha, "tecnico")
        async with asyncio.timeout(INVENTARIO_TIMEOUT_SEGUNDOS):
            resposta = await cliente.get(f"{INVENTARIO_URL}/ativos", headers={"Authorization": f"Bearer {token}"})
        resposta.raise_for_status()
        ativos = TypeAdapter(list[AtivoExemplo]).validate_json(resposta.content)
    por_patrimonio = {ativo.patrimonio: ativo.id for ativo in ativos}
    return ana, bruno, carla, por_patrimonio["PAT-0001"], por_patrimonio["PAT-0002"]


def existem_chamados(db: Session) -> bool:
    return db.scalar(select(Chamado.id).limit(1)) is not None


def carregar() -> str:
    if os.getenv("DADOS_EXEMPLO", "1") != "1":
        return "Dados de exemplo desativados."
    with SessionLocal() as db:
        if existem_chamados(db):
            return "Banco já contém chamados."
    ana, bruno, carla, computador, impressora = asyncio.run(consultar_exemplos())
    with SessionLocal.begin() as db:
        if db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        if existem_chamados(db):
            return "Banco já contém chamados."
        chamado = servico.abrir(db, ChamadoCriar(
            titulo="Computador não liga", descricao="Apertei o botão e nada acontece.",
            prioridade="alta", ativo_id=computador,
        ), ana)
        servico.abrir(db, ChamadoCriar(
            titulo="Impressora atolando papel", descricao="Atola a cada 3 folhas.",
            prioridade="media", ativo_id=impressora,
        ), bruno)
        servico.abrir(db, ChamadoCriar(
            titulo="Acesso ao sistema de RH", descricao="Preciso de acesso para a nova estagiária.",
            prioridade="baixa",
        ), bruno)
        servico.atribuir(db, chamado, carla.id)
    return "Três chamados de exemplo cadastrados."


if __name__ == "__main__":
    try:
        print(carregar())
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
        raise SystemExit("Não foi possível consultar as contas e os ativos de exemplo. Confira Usuários e Inventário.") from None
