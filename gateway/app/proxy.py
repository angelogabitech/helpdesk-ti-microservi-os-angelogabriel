"""Encaminha as rotas da API aos destinos fixos do Compose."""
import asyncio
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from fastapi import HTTPException, Request
from starlette.datastructures import Headers
from starlette.responses import Response

from app.config import CHAMADOS_URL, GATEWAY_TIMEOUT_SEGUNDOS, INVENTARIO_URL, USUARIOS_URL


@dataclass(frozen=True)
class Destino:
    nome: str
    url: httpx.URL


USUARIOS = Destino("Usuários", httpx.URL(USUARIOS_URL))
INVENTARIO = Destino("Inventário", httpx.URL(INVENTARIO_URL))
CHAMADOS = Destino("Chamados", httpx.URL(CHAMADOS_URL))
DESTINOS = {
    "auth": USUARIOS, "usuarios": USUARIOS, "ativos": INVENTARIO,
    "chamados": CHAMADOS, "notificacoes": CHAMADOS,
}

CABECALHOS_ENTRADA = {
    "authorization", "content-type", "accept", "accept-language", "if-none-match", "if-modified-since",
}
CABECALHOS_SAIDA = {
    "content-type", "content-language", "cache-control", "www-authenticate", "allow", "retry-after",
    "location", "etag", "last-modified", "vary",
}


def selecionar_cabecalhos(cabecalhos: Headers | httpx.Headers, permitidos: set[str]) -> dict[str, str]:
    conexao = {nome.strip().lower() for nome in cabecalhos.get("connection", "").split(",")}
    return {nome: cabecalhos[nome] for nome in permitidos - conexao if nome in cabecalhos}


async def enviar(cliente: httpx.AsyncClient, requisicao: httpx.Request) -> httpx.Response:
    # Inclui a resolução DNS e a leitura do corpo no mesmo prazo.
    async with asyncio.timeout(GATEWAY_TIMEOUT_SEGUNDOS):
        return await cliente.send(requisicao)


async def encaminhar(request: Request, destino: Destino) -> Response:
    escopo = request.scope
    caminho = escopo.get("raw_path") or quote(escopo["path"], safe="/").encode("ascii")
    query = escopo["query_string"]
    url = destino.url.copy_with(raw_path=caminho + (b"?" + query if query else b""))
    cabecalhos = selecionar_cabecalhos(request.headers, CABECALHOS_ENTRADA)
    cabecalhos["accept-encoding"] = "identity"
    if destino == USUARIOS and request.client:
        # A origem vem da conexão com o gateway. Cabeçalhos do cliente não são copiados.
        cabecalhos["x-forwarded-for"] = request.client.host

    corpo = await request.body()
    requisicao = httpx.Request(request.method, url, headers=cabecalhos, content=corpo)
    try:
        resposta = await enviar(request.app.state.cliente_http, requisicao)
    except (httpx.HTTPError, TimeoutError) as erro:
        raise HTTPException(503, f"Serviço de {destino.nome} indisponível.") from erro

    saida = selecionar_cabecalhos(resposta.headers, CABECALHOS_SAIDA)
    local = saida.get("location")
    if local:
        redirecionamento = url.join(local)
        if redirecionamento.netloc == destino.url.netloc:
            # Mantém redirecionamentos da API no endereço público do gateway.
            saida["location"] = redirecionamento.raw_path.decode("ascii")
    return Response(content=resposta.content, status_code=resposta.status_code, headers=saida)
