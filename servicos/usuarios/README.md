# Serviço de Usuários e autenticação — etapa 3

Primeiro serviço extraído do HelpDesk TI. É um projeto FastAPI independente, com dependências, Dockerfile, testes e banco próprios. Não importa o código do monólito nem os módulos de Inventário, Chamados ou Notificações.

O serviço usa seu próprio banco. Na configuração padrão, o gateway encaminha `/auth` e `/usuarios` para esta API.

## Estrutura

```text
servicos/usuarios/
├── .dockerignore
├── Dockerfile
├── README.md
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── dados_exemplo.py
│   ├── erros.py
│   ├── main.py
│   ├── seguranca_http.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── dependencias.py
│   │   ├── limite.py
│   │   ├── rotas.py
│   │   ├── senhas.py
│   │   └── tokens.py
│   └── usuarios/
│       ├── __init__.py
│       ├── esquemas.py
│       ├── modelos.py
│       ├── repositorio.py
│       ├── rotas.py
│       └── servico.py
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_servico.py
    └── test_usuarios.py
```

`main.py` reúne somente autenticação e usuários. `database.py` define a conexão exclusiva. `dados_exemplo.py` cria apenas as cinco contas de aula, com a mesma senha configurável do monólito e sem duplicação no reinício. Cada subpasta mantém a organização de rotas, validação, regras e acesso aos dados da aplicação original.

## Executar isoladamente com Docker Compose

Na raiz do repositório, configure `JWT_SEGREDO` no `.env` com pelo menos 32 caracteres. O serviço recusa a inicialização se o segredo estiver ausente ou for curto; não gera uma chave aleatória. Não é necessário alterar o valor que você já gerou.

```powershell
docker compose up -d --build usuarios
docker compose ps usuarios
docker compose logs --tail 50 usuarios
```

O comando acima inicia somente Usuários. O build usa a pasta deste projeto e o banco fica em `/dados/usuarios.db`, no volume `dados_usuarios`.

O serviço não publica portas para o computador. Para consultar a saúde pela rede local do contêiner:

```powershell
docker compose exec -T usuarios python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=3).read().decode())"
```

Resposta esperada: `{"status":"ok","servico":"usuarios"}`. A imagem também tem um healthcheck que executa essa consulta.

Para parar somente este serviço:

```powershell
docker compose stop usuarios
```

Para testar o build fora do Compose:

```powershell
docker build -t helpdesk-usuarios:etapa3 ./servicos/usuarios
```

O contêiner roda sem root, com capacidades removidas e filesystem somente leitura no Compose, exceto o volume de banco e o diretório temporário. No Compose principal, o Uvicorn aceita cabeçalhos de proxy apenas do IP privado do gateway. O bloqueio de login usa e-mail e endereço de conexão e permanece em memória, adequado a uma única instância.

## Executar localmente sem Docker

Os comandos abaixo começam na raiz e usam um ambiente virtual local:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r servicos/usuarios/requirements-dev.txt
Set-Location servicos/usuarios
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --env-file ../../.env --host 127.0.0.1 --port 8001 --no-proxy-headers
```

A API fica em `http://localhost:8001` e a documentação em `http://localhost:8001/docs`, quando `DOCS=1`. O banco padrão desta execução é `servicos/usuarios/usuarios.db`. Se definir `DATABASE_URL` no ambiente, use um banco exclusivo deste serviço.

Sem o Compose, o carregamento do `.env` é solicitado explicitamente por `--env-file`. As contas de exemplo são criadas somente quando `DADOS_EXEMPLO=1` e a tabela está vazia. Com `DADOS_EXEMPLO=0`, o banco inicia sem contas: a criação de um primeiro administrador fora do modo didático exige um procedimento de provisionamento separado.

## Contratos da API

| Método | Rota | Acesso |
|---|---|---|
| GET | `/saude` | Público; consulta também a conexão do banco |
| POST | `/auth/login` | Público; e-mail e senha no JSON |
| GET | `/auth/eu` | Usuário ativo autenticado; inclui perfil atual |
| POST | `/usuarios` | Somente administrador |
| GET | `/usuarios` | Autenticado; lista sem e-mails; filtro opcional `perfil` |
| GET | `/usuarios/{id}` | Autenticado; resposta pública sem e-mail |

`/auth/login` mantém `access_token`, `token_type`, `expira_em` e `usuario`. O JWT usa HS256 e o emissor `helpdesk-ti`, compatíveis com o monólito. Cada requisição autenticada consulta o próprio banco para confirmar que a conta ainda existe, está ativa e mantém a permissão necessária. Tokens não substituem a confirmação do perfil atual.

Erros mantêm o formato `{"detail":"mensagem"}`: 401 para autenticação inválida, 403 para falta de permissão, 404 para usuário ausente, 422 para regra ou entrada inválida, 429 para excesso de tentativas e 503 para indisponibilidade do banco. Conflitos de integridade retornam 409 sem detalhes internos.

## Testes e validação

Na pasta `servicos/usuarios`, com as dependências instaladas:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -q
```

Os testes usam um segredo exclusivo de testes e um banco temporário por caso, sem ler o `.env` ou modificar bancos reais. Cobrem login, bloqueio, JWT, permissões, perfil atualizado, conta desativada, privacidade, validações, corpo limitado a 64 KB inclusive sem `Content-Length`, saúde, banco exclusivo, exemplos e persistência após reinício.

A suíte original continua sendo executada separadamente, na raiz:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

No GitHub Actions, os jobs do monólito e de Usuários são separados. O job de Usuários também audita suas dependências e faz o build independente da imagem.

## Arquivos envolvidos nesta etapa

- Criados: todos os arquivos desta pasta, listados na estrutura acima.
- Alterado `docker-compose.yml`: perfil opcional `etapa3`, serviço `usuarios` e volume exclusivo.
- Alterado `.github/workflows/testes.yml`: job independente de testes, auditoria e build.
- Alterado `.github/dependabot.yml`: acompanhamento das dependências e da imagem base deste projeto.
- Alterados `README.md` e `PLANO_EXECUCAO.md`: situação da migração, instruções e validações.
- Corrigida a localização do monólito: `app/`, `Dockerfile` e dependências voltaram à raiz para corresponder aos caminhos dos testes e do Compose.

As etapas de Inventário, Chamados e gateway ainda serão implementadas. Este serviço independente é a entrega da etapa 3.
