import pytest

from app.auth.senhas import conferir
from app.usuarios.modelos import Usuario


def novo_usuario(**alteracoes):
    return {"nome": "Davi", "email": "davi@empresa.com", "perfil": "tecnico", "senha": "Forte1234", **alteracoes}


def test_admin_cria_usuario_com_senha_hash_e_login_funcional(cliente, contas, sessao):
    resposta = cliente.post("/usuarios", headers=contas["admin"]["headers"], json=novo_usuario())
    assert resposta.status_code == 201
    assert set(resposta.json()) == {"id", "nome", "email", "perfil"}
    with sessao() as db:
        usuario = db.get(Usuario, resposta.json()["id"])
        assert usuario.senha_hash.startswith("scrypt$")
        assert "Forte1234" not in usuario.senha_hash
        assert conferir("Forte1234", usuario.senha_hash)
    assert cliente.post("/auth/login", json={"email": "davi@empresa.com", "senha": "Forte1234"}).status_code == 200


@pytest.mark.parametrize("quem", ["ana", "carla"])
def test_apenas_admin_pode_criar_usuario(cliente, contas, quem):
    assert cliente.post("/usuarios", headers=contas[quem]["headers"], json=novo_usuario()).status_code == 403


def test_email_repetido_ignora_maiusculas(cliente, contas):
    resposta = cliente.post("/usuarios", headers=contas["admin"]["headers"], json=novo_usuario(email="ANA@empresa.com"))
    assert resposta.status_code == 422


def test_listagem_publica_filtro_e_consulta_individual(cliente, contas):
    headers = contas["ana"]["headers"]
    usuarios = cliente.get("/usuarios", headers=headers).json()
    assert len(usuarios) == 3
    assert all(set(usuario) == {"id", "nome", "perfil"} for usuario in usuarios)
    tecnicos = cliente.get("/usuarios", params={"perfil": "tecnico"}, headers=headers).json()
    assert tecnicos == [{"id": contas["carla"]["id"], "nome": "Carla", "perfil": "tecnico"}]
    assert cliente.get(f"/usuarios/{contas['carla']['id']}", headers=headers).json() == tecnicos[0]
    assert cliente.get("/usuarios/999", headers=headers).status_code == 404


@pytest.mark.parametrize("alteracoes", [
    {"senha": "abcdefgh"}, {"senha": "12345678"}, {"senha": "a1"}, {"senha": "a1" * 65},
    {"perfil": "superadmin"}, {"nome": "x" * 121}, {"email": "invalido"}, {"ativo": True},
])
def test_validacao_e_campos_extras(cliente, contas, alteracoes):
    resposta = cliente.post("/usuarios", headers=contas["admin"]["headers"], json=novo_usuario(**alteracoes))
    assert resposta.status_code == 422


def test_login_recusa_campos_extras(cliente, contas):
    assert cliente.post("/auth/login", json={
        "email": "ana@empresa.com", "senha": "Senha123", "perfil": "admin",
    }).status_code == 422


def test_senhas_iguais_tem_sais_diferentes(cliente, contas, sessao):
    with sessao() as db:
        ana = db.get(Usuario, contas["ana"]["id"])
        carla = db.get(Usuario, contas["carla"]["id"])
        assert ana.senha_hash != carla.senha_hash
