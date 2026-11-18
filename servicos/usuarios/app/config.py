"""Configuração exclusiva do serviço, recebida pelo ambiente."""
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./usuarios.db")

JWT_SEGREDO = os.getenv("JWT_SEGREDO", "")
if len(JWT_SEGREDO.strip()) < 32:
    raise RuntimeError("Configure JWT_SEGREDO com pelo menos 32 caracteres no ambiente.")

JWT_ALGORITMO = "HS256"
JWT_EMISSOR = "helpdesk-ti"
TOKEN_MINUTOS = int(os.getenv("TOKEN_MINUTOS", "60"))
LOGIN_MAX_FALHAS = int(os.getenv("LOGIN_MAX_FALHAS", "5"))
LOGIN_JANELA_SEGUNDOS = int(os.getenv("LOGIN_JANELA_SEGUNDOS", "300"))
TAMANHO_MAXIMO_REQUISICAO = 64 * 1024
DOCS_ATIVA = os.getenv("DOCS", "1") == "1"
