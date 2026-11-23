"""Acesso a dados do módulo de chamados (uso interno do módulo)."""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.chamados.modelos import Chamado, Comentario


def salvar(db: Session, chamado: Chamado) -> Chamado:
    db.add(chamado)
    db.flush()
    return chamado


def salvar_comentario(db: Session, comentario: Comentario) -> Comentario:
    db.add(comentario)
    db.flush()
    return comentario


def buscar_por_id(db: Session, chamado_id: int) -> Chamado | None:
    return db.get(Chamado, chamado_id)


def listar(db: Session, status: str | None = None, tecnico_id: int | None = None,
           solicitante_id: int | None = None, *, incluir_comentarios: bool = True) -> list[Chamado]:
    consulta = select(Chamado).order_by(Chamado.id)
    if incluir_comentarios:
        consulta = consulta.options(selectinload(Chamado.comentarios))
    if solicitante_id:
        consulta = consulta.where(Chamado.solicitante_id == solicitante_id)
    if status:
        consulta = consulta.where(Chamado.status == status)
    if tecnico_id:
        consulta = consulta.where(Chamado.tecnico_id == tecnico_id)
    return list(db.scalars(consulta))
