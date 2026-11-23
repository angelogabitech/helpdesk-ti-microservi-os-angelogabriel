"""Configuração do serviço recebida pelo ambiente."""
import math
import os


def ler_timeout(variavel: str) -> float:
    valor = float(os.getenv(variavel, "3"))
    if not math.isfinite(valor) or valor <= 0:
        raise RuntimeError(f"Configure {variavel} com um número positivo e finito.")
    return valor


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chamados.db")
USUARIOS_URL = os.getenv("USUARIOS_URL", "http://127.0.0.1:8001").rstrip("/")
INVENTARIO_URL = os.getenv("INVENTARIO_URL", "http://127.0.0.1:8002").rstrip("/")
USUARIOS_TIMEOUT_SEGUNDOS = ler_timeout("USUARIOS_TIMEOUT_SEGUNDOS")
INVENTARIO_TIMEOUT_SEGUNDOS = ler_timeout("INVENTARIO_TIMEOUT_SEGUNDOS")

JWT_SEGREDO = os.getenv("JWT_SEGREDO", "")
if len(JWT_SEGREDO.strip()) < 32:
    raise RuntimeError("Configure JWT_SEGREDO com pelo menos 32 caracteres no ambiente.")

JWT_ALGORITMO = "HS256"
JWT_EMISSOR = "helpdesk-ti"
TAMANHO_MAXIMO_REQUISICAO = 64 * 1024
DOCS_ATIVA = os.getenv("DOCS", "1") == "1"
