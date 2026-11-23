from anyio import from_thread
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.chamados import servico
from app.chamados.esquemas import (
    Atribuicao, ChamadoCriar, ChamadoSaida, ComentarioCriar, ComentarioSaida, MudancaStatus, Painel, Status,
)
from app.database import get_db
from app.identidade import UsuarioAtual, usuario_atual
from app.integracoes import validar_ativo, validar_tecnico

router = APIRouter(prefix="/chamados", tags=["Chamados"])


@router.post("", response_model=ChamadoSaida, status_code=201)
def abrir_chamado(
    dados: ChamadoCriar, request: Request, usuario: UsuarioAtual = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    if dados.ativo_id is not None:
        from_thread.run(validar_ativo, request.app.state.cliente_http, usuario.token, dados.ativo_id)
    with db.begin():
        return servico.abrir(db, dados, usuario)


@router.get("", response_model=list[ChamadoSaida])
def listar_chamados(status: Status | None = None, tecnico_id: int | None = None,
                    usuario: UsuarioAtual = Depends(usuario_atual), db: Session = Depends(get_db)):
    return servico.listar(db, usuario, status, tecnico_id)


@router.get("/painel", response_model=Painel)
def painel(usuario: UsuarioAtual = Depends(usuario_atual), db: Session = Depends(get_db)):
    return servico.painel(db, usuario)


@router.get("/{chamado_id}", response_model=ChamadoSaida)
def obter_chamado(chamado_id: int, usuario: UsuarioAtual = Depends(usuario_atual), db: Session = Depends(get_db)):
    return servico.obter(db, chamado_id, usuario)


@router.patch("/{chamado_id}/atribuir", response_model=ChamadoSaida)
def atribuir_chamado(
    chamado_id: int, dados: Atribuicao, request: Request, usuario: UsuarioAtual = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    with db.begin():
        chamado = servico.preparar_atribuicao(db, chamado_id, usuario)
        from_thread.run(validar_tecnico, request.app.state.cliente_http, usuario.token, dados.tecnico_id)
        return servico.atribuir(db, chamado, dados.tecnico_id)


@router.patch("/{chamado_id}/status", response_model=ChamadoSaida)
def mudar_status(chamado_id: int, dados: MudancaStatus, usuario: UsuarioAtual = Depends(usuario_atual),
                 db: Session = Depends(get_db)):
    with db.begin():
        return servico.mudar_status(db, chamado_id, dados.status, usuario)


@router.post("/{chamado_id}/comentarios", response_model=ComentarioSaida, status_code=201)
def comentar(chamado_id: int, dados: ComentarioCriar, usuario: UsuarioAtual = Depends(usuario_atual),
             db: Session = Depends(get_db)):
    with db.begin():
        return servico.comentar(db, chamado_id, dados, usuario)
