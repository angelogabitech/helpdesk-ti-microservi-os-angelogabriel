"""Carrega os equipamentos de exemplo no banco de Inventário."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.inventario.modelos import Ativo


def carregar(db: Session) -> None:
    if db.scalar(select(Ativo.id).limit(1)) is not None:
        return
    db.add_all([
        Ativo(patrimonio="PAT-0001", tipo="computador", descricao="Desktop Dell OptiPlex", setor="Financeiro"),
        Ativo(patrimonio="PAT-0002", tipo="impressora", descricao="Impressora HP LaserJet", setor="RH"),
        Ativo(patrimonio="PAT-0003", tipo="notebook", descricao="Notebook Lenovo ThinkPad", setor="TI"),
    ])
    db.commit()
