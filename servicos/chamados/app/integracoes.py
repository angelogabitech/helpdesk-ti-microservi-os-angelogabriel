"""Consultas HTTP às APIs de Usuários e Inventário."""
import asyncio
from typing import Literal, TypeVar

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, PositiveInt, ValidationError

from app.config import INVENTARIO_TIMEOUT_SEGUNDOS, INVENTARIO_URL, USUARIOS_TIMEOUT_SEGUNDOS, USUARIOS_URL
from app.erros import ErroDeIntegracao, NaoEncontrado, RegraDeNegocio


class Recurso(BaseModel):
    model_config = ConfigDict(strict=True)

    id: PositiveInt


class Identidade(Recurso):
    perfil: Literal["solicitante", "tecnico", "admin"]


Modelo = TypeVar("Modelo", bound=Recurso)


def nao_autenticado() -> HTTPException:
    return HTTPException(401, "Faça login para continuar.", headers={"WWW-Authenticate": "Bearer"})


async def consultar(
    cliente: httpx.AsyncClient, url: str, timeout: float, servico: str, token: str,
    modelo: type[Modelo], *, id_esperado: int, mensagem_ausente: str | None = None,
) -> Modelo:
    falha = f"Serviço de {servico} indisponível."
    try:
        # O prazo engloba DNS, conexão e leitura do corpo.
        async with asyncio.timeout(timeout):
            resposta = await cliente.get(url, headers={"Authorization": f"Bearer {token}"})
    except (httpx.HTTPError, TimeoutError, ValueError) as erro:
        raise ErroDeIntegracao(falha) from erro
    if resposta.status_code == 401:
        raise nao_autenticado()
    if resposta.status_code == 404 and mensagem_ausente is not None:
        raise NaoEncontrado(mensagem_ausente)
    if resposta.status_code != 200:
        raise ErroDeIntegracao(falha)
    try:
        recurso = modelo.model_validate_json(resposta.content)
    except ValidationError as erro:
        raise ErroDeIntegracao(falha) from erro
    if recurso.id != id_esperado:
        raise ErroDeIntegracao(falha)
    return recurso


async def obter_identidade(cliente: httpx.AsyncClient, token: str, usuario_id: int) -> Identidade:
    return await consultar(
        cliente, f"{USUARIOS_URL}/auth/eu", USUARIOS_TIMEOUT_SEGUNDOS, "Usuários",
        token, Identidade, id_esperado=usuario_id,
    )


async def validar_tecnico(cliente: httpx.AsyncClient, token: str, tecnico_id: int) -> None:
    tecnico = await consultar(
        cliente, f"{USUARIOS_URL}/usuarios/{tecnico_id}", USUARIOS_TIMEOUT_SEGUNDOS, "Usuários",
        token, Identidade, id_esperado=tecnico_id, mensagem_ausente=f"Usuário {tecnico_id} não encontrado.",
    )
    if tecnico.perfil != "tecnico":
        raise RegraDeNegocio(f"Usuário {tecnico_id} não é técnico.")


async def validar_ativo(cliente: httpx.AsyncClient, token: str, ativo_id: int) -> None:
    await consultar(
        cliente, f"{INVENTARIO_URL}/ativos/{ativo_id}", INVENTARIO_TIMEOUT_SEGUNDOS, "Inventário",
        token, Recurso, id_esperado=ativo_id, mensagem_ausente=f"Ativo {ativo_id} não encontrado.",
    )
