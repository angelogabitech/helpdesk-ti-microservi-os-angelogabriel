"""Configuração do serviço recebida pelo ambiente."""
import math
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./inventario.db")
USUARIOS_URL = os.getenv("USUARIOS_URL", "http://127.0.0.1:8001")
USUARIOS_TIMEOUT_SEGUNDOS = float(os.getenv("USUARIOS_TIMEOUT_SEGUNDOS", "3"))
if not math.isfinite(USUARIOS_TIMEOUT_SEGUNDOS) or USUARIOS_TIMEOUT_SEGUNDOS <= 0:
    raise RuntimeError("Configure USUARIOS_TIMEOUT_SEGUNDOS com um número positivo e finito.")

JWT_SEGREDO = os.getenv("JWT_SEGREDO", "")
if len(JWT_SEGREDO.strip()) < 32:
    raise RuntimeError("Configure JWT_SEGREDO com pelo menos 32 caracteres no ambiente.")

JWT_ALGORITMO = "HS256"
JWT_EMISSOR = "helpdesk-ti"
TAMANHO_MAXIMO_REQUISICAO = 64 * 1024
DOCS_ATIVA = os.getenv("DOCS", "1") == "1"
