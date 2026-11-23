"""Erros das operações de inventário."""


class NaoEncontrado(Exception):
    """O ativo solicitado não existe."""


class RegraDeNegocio(Exception):
    """A operação viola uma regra do inventário."""
