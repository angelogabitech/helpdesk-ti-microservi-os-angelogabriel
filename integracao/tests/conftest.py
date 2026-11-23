import ipaddress
import os
import secrets
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[2]
SERVICOS = ("gateway", "usuarios", "inventario", "chamados")


def docker(*argumentos, ambiente=None, prazo=60):
    resultado = subprocess.run(
        ["docker", *argumentos], cwd=RAIZ, env=ambiente, timeout=prazo,
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if resultado.returncode:
        raise RuntimeError(f"Falha em Docker (código {resultado.returncode}):\n{resultado.stderr}\n{resultado.stdout}")
    return resultado.stdout.strip()


def rede_disponivel():
    redes = docker("network", "ls", "-q").splitlines()
    subredes = docker("network", "inspect", "--format", "{{range .IPAM.Config}}{{println .Subnet}}{{end}}", *redes)
    ocupadas = [
        ipaddress.ip_network(linha, strict=False) for linha in subredes.splitlines()
        if "/" in linha and ":" not in linha
    ]
    for _ in range(40):
        rede = ipaddress.ip_network(f"10.254.{secrets.randbelow(256)}.{secrets.randbelow(16) * 16}/28")
        if not any(rede.overlaps(ocupada) for ocupada in ocupadas):
            return rede
    raise RuntimeError("Não foi encontrada uma sub-rede livre para o projeto Docker de teste.")


@dataclass(frozen=True)
class Ambiente:
    projeto: str
    arquivo_env: Path
    variaveis: dict = field(repr=False)
    segredo: str = field(repr=False)
    senha: str = field(repr=False)

    def compose(self, *argumentos, prazo=60):
        return docker(
            "compose", "--env-file", str(self.arquivo_env),
            "-f", str(RAIZ / "docker-compose.yml"), "-f", str(RAIZ / "integracao" / "compose.testes.yml"),
            "-p", self.projeto, *argumentos, ambiente=self.variaveis, prazo=prazo,
        )

    def container(self, servico):
        return self.compose("ps", "-q", servico)

    @contextmanager
    def indisponivel(self, servico):
        self.compose("stop", servico)
        try:
            yield
        finally:
            self.compose("start", servico)
            limite = time.monotonic() + 35
            cid = self.container(servico)
            while time.monotonic() < limite:
                if docker("inspect", "--format", "{{.State.Health.Status}}", cid) == "healthy":
                    break
                time.sleep(1)
            else:
                raise RuntimeError(f"{servico} não recuperou a saúde após o reinício.")


@pytest.fixture(scope="session")
def ambiente():
    senha, segredo = "Teste7-" + secrets.token_hex(12), secrets.token_urlsafe(48)
    rede = rede_disponivel()
    with TemporaryDirectory(prefix="helpdesk-integracao-") as pasta:
        arquivo_env = Path(pasta) / ".env"
        valores = {
            "HELPDESK_TESTE_ENV": arquivo_env.as_posix(),
            "JWT_SEGREDO": segredo, "SENHA_EXEMPLO": senha, "DADOS_EXEMPLO": "1", "DOCS": "1",
            "LOGIN_MAX_FALHAS": "5", "LOGIN_JANELA_SEGUNDOS": "300", "TOKEN_MINUTOS": "60",
            "USUARIOS_TIMEOUT_SEGUNDOS": "2", "INVENTARIO_TIMEOUT_SEGUNDOS": "2", "GATEWAY_TIMEOUT_SEGUNDOS": "5",
            "GATEWAY_SUBREDE_INTERNA": str(rede), "GATEWAY_IP_INTERNO": str(rede.network_address + 2),
            "GATEWAY_FAIXA_INTERNA": str(list(rede.subnets(new_prefix=29))[1]),
        }
        arquivo_env.write_text("\n".join(f"{nome}={valor}" for nome, valor in valores.items()) + "\n", encoding="utf-8")
        projeto = Ambiente(
            f"helpdesk-integracao-{secrets.token_hex(5)}", arquivo_env, {**os.environ, **valores}, segredo, senha,
        )
        try:
            try:
                projeto.compose("up", "-d", "--build", "--wait", "--wait-timeout", "75", *SERVICOS, prazo=360)
            except (RuntimeError, subprocess.TimeoutExpired):
                print(projeto.compose("logs", "--tail", "35"))
                raise
            yield projeto
        finally:
            projeto.compose("down", "--volumes", "--timeout", "5")


@pytest.fixture(scope="session")
def api(ambiente):
    endereco = ambiente.compose("port", "gateway", "8000")
    with httpx.Client(base_url=f"http://{endereco}", timeout=10, trust_env=False) as cliente:
        yield cliente


def autenticar(api, email, senha):
    resposta = api.post("/auth/login", json={"email": email, "senha": senha})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    cabecalhos = {"Authorization": f"Bearer {dados['access_token']}"}
    return dados["usuario"]["id"], cabecalhos


@pytest.fixture(scope="session")
def contas(api, ambiente):
    return {
        nome: autenticar(api, f"{nome}@empresa.com", ambiente.senha)
        for nome in ("admin", "ana", "carla")
    }


@pytest.fixture(scope="session")
def ativo_id(api, contas):
    resposta = api.get("/ativos", headers=contas["carla"][1])
    assert resposta.status_code == 200, resposta.text
    return resposta.json()[0]["id"]
