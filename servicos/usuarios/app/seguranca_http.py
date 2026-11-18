"""Cabeçalhos e limite de corpo, inclusive quando não há Content-Length."""
from collections import deque

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import TAMANHO_MAXIMO_REQUISICAO

CSP_API = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
CSP_DOCS = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; frame-ancestors 'none'; base-uri 'none'"
)


class CabecalhosDeSeguranca:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)

        async def enviar_seguro(message: Message):
            if message["type"] == "http.response.start":
                saida = MutableHeaders(scope=message)
                docs = scope["path"] in ("/docs", "/openapi.json")
                saida["Content-Security-Policy"] = CSP_DOCS if docs else CSP_API
                saida["X-Content-Type-Options"] = "nosniff"
                saida["X-Frame-Options"] = "DENY"
                saida["Referrer-Policy"] = "no-referrer"
                saida["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                saida["Cross-Origin-Opener-Policy"] = "same-origin"
                if headers.get("authorization") or scope["path"].startswith("/auth/"):
                    saida["Cache-Control"] = "no-store"
            await send(message)

        async def recusar():
            resposta = JSONResponse(status_code=413, content={"detail": "Requisição grande demais."})
            await resposta(scope, receive, enviar_seguro)

        tamanho = headers.get("content-length")
        if tamanho is not None and (not tamanho.isdigit() or int(tamanho) > TAMANHO_MAXIMO_REQUISICAO):
            await recusar()
            return

        mensagens: deque[Message] = deque()
        total = 0
        while True:
            mensagem = await receive()
            if mensagem["type"] == "http.disconnect":
                return
            total += len(mensagem.get("body", b""))
            if total > TAMANHO_MAXIMO_REQUISICAO:
                await recusar()
                return
            mensagens.append(mensagem)
            if not mensagem.get("more_body", False):
                break

        async def receber_corpo() -> Message:
            return mensagens.popleft() if mensagens else await receive()

        await self.app(scope, receber_corpo, enviar_seguro)
