"""Valida o JWT e confirma a conta no serviço de Usuários."""
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field

from app.config import JWT_ALGORITMO, JWT_EMISSOR, JWT_SEGREDO
from app.integracoes import Identidade, nao_autenticado, obter_identidade

esquema = HTTPBearer(auto_error=False)


class UsuarioAtual(Identidade):
    token: str = Field(repr=False, exclude=True)


async def usuario_atual(
    request: Request,
    credenciais: HTTPAuthorizationCredentials | None = Depends(esquema),
) -> UsuarioAtual:
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

    identidade = await obter_identidade(request.app.state.cliente_http, token, usuario_id)
    return UsuarioAtual(id=identidade.id, perfil=identidade.perfil, token=token)
