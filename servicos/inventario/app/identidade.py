"""Valida o JWT localmente e confirma a identidade na API de Usuários."""
import asyncio
from typing import Literal

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, PositiveInt

from app.config import JWT_ALGORITMO, JWT_EMISSOR, JWT_SEGREDO, USUARIOS_TIMEOUT_SEGUNDOS

esquema = HTTPBearer(auto_error=False)


class Identidade(BaseModel):
    model_config = ConfigDict(strict=True)

    id: PositiveInt
    perfil: Literal["solicitante", "tecnico", "admin"]


def nao_autenticado() -> HTTPException:
    return HTTPException(401, "Faça login para continuar.", headers={"WWW-Authenticate": "Bearer"})


async def usuario_atual(
    request: Request,
    credenciais: HTTPAuthorizationCredentials | None = Depends(esquema),
) -> Identidade:
    if credenciais is None:
        raise nao_autenticado()

    token = credenciais.credentials
    try:
        dados = jwt.decode(
            token, JWT_SEGREDO, algorithms=[JWT_ALGORITMO], issuer=JWT_EMISSOR,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
        usuario_id = int(dados["sub"])
        if usuario_id <= 0:
            raise ValueError("Identificador inválido.")
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError) as erro:
        raise nao_autenticado() from erro

    cliente: httpx.AsyncClient = request.app.state.cliente_usuarios
    try:
        # O prazo inclui a resolução DNS, além da conexão e leitura.
        async with asyncio.timeout(USUARIOS_TIMEOUT_SEGUNDOS):
            resposta = await cliente.get("/auth/eu", headers={"Authorization": f"Bearer {token}"})
        if resposta.status_code == 401:
            raise nao_autenticado()
        if resposta.status_code != 200:
            raise ValueError("Resposta inesperada de Usuários.")
        identidade = Identidade.model_validate_json(resposta.content)
        if identidade.id != usuario_id:
            raise ValueError("Identidade divergente.")
    except (httpx.HTTPError, TimeoutError, ValueError) as erro:
        raise HTTPException(503, "Serviço de Usuários indisponível.") from erro
    return identidade


def exigir_perfil(*perfis: str):
    def verificar(usuario: Identidade = Depends(usuario_atual)) -> None:
        if usuario.perfil not in perfis:
            raise HTTPException(403, "Você não tem permissão para esta ação.")

    return verificar
