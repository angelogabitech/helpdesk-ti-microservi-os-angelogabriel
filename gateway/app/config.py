"""Configuração do gateway fornecida pelo ambiente."""
import math
import os

USUARIOS_URL = os.getenv("USUARIOS_URL", "http://usuarios:8000")
INVENTARIO_URL = os.getenv("INVENTARIO_URL", "http://inventario:8000")
CHAMADOS_URL = os.getenv("CHAMADOS_URL", "http://chamados:8000")
GATEWAY_TIMEOUT_SEGUNDOS = float(os.getenv("GATEWAY_TIMEOUT_SEGUNDOS", "8"))
if not math.isfinite(GATEWAY_TIMEOUT_SEGUNDOS) or GATEWAY_TIMEOUT_SEGUNDOS <= 0:
    raise RuntimeError("Configure GATEWAY_TIMEOUT_SEGUNDOS com um número positivo e finito.")

TAMANHO_MAXIMO_REQUISICAO = 64 * 1024
DOCS_ATIVA = os.getenv("DOCS", "1") == "1"
