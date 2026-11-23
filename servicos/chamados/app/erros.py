"""Erros das operações de Chamados."""


class NaoEncontrado(Exception):
    """O recurso solicitado não existe ou não pode ser visto pelo usuário."""


class RegraDeNegocio(Exception):
    """A operação viola uma regra de atendimento."""


class SemPermissao(Exception):
    """O usuário autenticado não pode realizar a operação."""


class ErroDeIntegracao(Exception):
    """Um serviço necessário está indisponível ou retornou dados inválidos."""
