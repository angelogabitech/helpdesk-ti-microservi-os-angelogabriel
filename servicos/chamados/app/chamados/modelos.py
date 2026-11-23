from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Chamado(Base):
    __tablename__ = "chamados"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str] = mapped_column(Text)
    prioridade: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="aberto")
    solicitante_id: Mapped[int]
    tecnico_id: Mapped[int | None]
    ativo_id: Mapped[int | None]
    criado_em: Mapped[datetime] = mapped_column(DateTime)
    prazo_sla: Mapped[datetime] = mapped_column(DateTime)
    versao: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": versao}

    comentarios: Mapped[list["Comentario"]] = relationship(
        back_populates="chamado", order_by="Comentario.id", cascade="all, delete-orphan"
    )


class Comentario(Base):
    __tablename__ = "comentarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    chamado_id: Mapped[int] = mapped_column(ForeignKey("chamados.id"))
    autor_id: Mapped[int]
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime)

    chamado: Mapped[Chamado] = relationship(back_populates="comentarios")
