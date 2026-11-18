"""Exemplos locais: este serviço cria somente usuários no seu próprio banco."""
import os

from sqlalchemy.orm import Session

from app.usuarios import servico
from app.usuarios.esquemas import UsuarioCriar


def carregar(db: Session) -> None:
    # Preserva a regra do monólito: inicialização somente com a tabela vazia.
    if servico.listar(db):
        return
    senha = os.getenv("SENHA_EXEMPLO", "Helpdesk2026")
    for nome, email, perfil in (
        ("Admin TI", "admin@empresa.com", "admin"),
        ("Ana Souza", "ana@empresa.com", "solicitante"),
        ("Bruno Lima", "bruno@empresa.com", "solicitante"),
        ("Carla Dias", "carla@empresa.com", "tecnico"),
        ("Diego Rocha", "diego@empresa.com", "tecnico"),
    ):
        servico.criar(db, UsuarioCriar(nome=nome, email=email, perfil=perfil, senha=senha))
