# Autenticação, API keys e autorização

> Verificado contra o código em 2026-10-07. Fonte da verdade:
> [backend/api/auth_routes.py](../../backend/api/auth_routes.py),
> [backend/api/apikey_routes.py](../../backend/api/apikey_routes.py),
> [backend/shared/auth.py](../../backend/shared/auth.py),
> [backend/shared/rate_limit.py](../../backend/shared/rate_limit.py),
> [backend/api/deps.py](../../backend/api/deps.py),
> [backend/api/admin_routes.py](../../backend/api/admin_routes.py).

## O que faz

Todo endpoint de negócio exige um usuário autenticado. Há dois mecanismos, aceitos em
qualquer endpoint protegido (dependência `get_current_active_user`):

1. **JWT** (sessão): `Authorization: Bearer <jwt>`, obtido em `/auth/login`.
2. **API key** (acesso programático): `X-API-Key: doc2md_sk_…`, criada em `/api-keys/`.

Se os dois headers vierem, **o JWT é tentado primeiro** e, se inválido, a requisição falha
com `401` (não cai para a API key).

Endpoints públicos: `GET /`, `GET /health`, `POST /auth/register`, `POST /auth/login`,
`/docs`, `/redoc`, `/openapi.json`.

## Como usar

### Usuários e sessão (`/auth`)

| Método e caminho | Corpo | Resposta |
|---|---|---|
| `POST /auth/register` | JSON `{email, username, password}` | `201` + usuário (`id, email, username, is_active, created_at`). `400` se e-mail/username já existe. |
| `POST /auth/login` | **form-urlencoded** `username` (username **ou** e-mail), `password` | `{access_token, token_type: "bearer"}` |
| `POST /auth/refresh` | header `Authorization: Bearer <jwt ainda válido>` | Novo JWT com validade renovada. API key não é aceita. |
| `GET /auth/me` | JWT ou API key | O usuário autenticado. |

```bash
curl -X POST http://localhost:8000/auth/register -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","username":"usuario","password":"<senha>"}'

TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=usuario&password=<senha>" | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/auth/me
```

O JWT é HS256, com `sub = user.id` e expiração `JWT_EXPIRATION_MINUTES` (60). O frontend
chama `/auth/refresh` como heartbeat enquanto a pessoa usa o app
([frontend/components/session-heartbeat.tsx](../../frontend/components/session-heartbeat.tsx)); parado por mais que a
expiração, a sessão cai.

Senhas são guardadas com bcrypt. Não há verificação de e-mail, troca/recuperação de senha
nem logout no servidor (o JWT vale até expirar).

### API keys (`/api-keys`)

| Método e caminho | Descrição |
|---|---|
| `POST /api-keys/` | JSON `{name, expires_in_days?}`. Devolve `api_key` **uma única vez**. |
| `GET /api-keys/` | Lista as chaves do usuário (sem o valor): `id, name, last_used_at, expires_at, is_active, created_at`. |
| `DELETE /api-keys/{key_id}` | Apaga a chave (`204`; `404` se não for do usuário). |

```bash
curl -X POST http://localhost:8000/api-keys/ -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"servidor-ci","expires_in_days":90}'
```

A chave tem o formato `doc2md_sk_<aleatório>`; só o SHA-256 é guardado
(`api_keys.key_hash`). Cada uso atualiza `last_used_at`. Chaves expiradas ou
`is_active=false` são recusadas. A página `/api-keys` do frontend usa estes endpoints.

## Rate limiting e bloqueio de login

Implementado em [rate_limit.py](../../backend/shared/rate_limit.py) com contadores no
Redis (`ratelimit:<bucket>:<identidade>`), janela fixa:

| Regra | Variável | Default |
|---|---|---|
| Tentativas de login por IP por minuto | `RATE_LIMIT_PER_MINUTE` | `10` |
| Falhas por conta antes do bloqueio | `LOGIN_MAX_FAILED_ATTEMPTS` | `5` |
| Duração do bloqueio (desde a 1ª falha) | `LOGIN_LOCKOUT_SECONDS` | `900` |
| Registros por IP por hora | `REGISTER_LIMIT_PER_HOUR` | `5` |

Excedido, a resposta é `429` com `Retry-After`. O IP considerado é o do peer direto
(`X-Forwarded-For` é ignorado — atrás de proxy, todos compartilham o IP do proxy). Username
e e-mail da mesma conta compartilham o contador de falhas. Se o Redis cair, o limitador
**falha aberto** (deixa passar e loga um aviso).

## Autorização de recursos

- **Jobs:** só o dono acessa; ver [jobs-api.md](jobs-api.md#autorização). Negação é sempre
  `404`, nunca `403`.
- **Busca e tags:** filtradas por `user_id` do usuário autenticado.
- **Admin (`/admin/*`):** um usuário é admin se `users.is_admin` é verdadeiro **ou** se o id
  está em `ADMIN_USER_IDS` (UUIDs separados por vírgula). A regra é uma só
  (`shared/admin.py:is_effective_admin`) para as rotas admin e para o campo `is_admin` de
  `GET /auth/me` e `POST /auth/register`. Nas rotas administrativas gerais, quem não é
  admin recebe `403`. Com `IAM_MODE=enforce`
  ([spec 0014](../specs/0014-iam-nucleo-de-decisao-e-papeis-de-plataforma.md)), bindings de
  plataforma (`platform_admin`, `platform_operator`, `platform_auditor`,
  `remote_engine_user`) concedem as permissões de plataforma sem tornar ninguém admin.
  Endpoints gerais em [monitoring-and-admin.md](monitoring-and-admin.md).
- **Bindings IAM (spec 0018):** toda concessão é um `iam_binding` de uma de duas famílias
  que nunca se enxergam — `platform` (0014) e `engines` (papéis da 0009, com uma revisão de
  política como condição). Ambas se administram em **Admin → Acesso** (`/admin/access`) e por
  `/admin/iam/bindings`, cada uma com sua autoridade: bootstrap ou `iam.bindings.manage` para plataforma;
  bootstrap ou `access.grants.manage` dentro do envelope de delegação para engines. Ninguém
  concede papel a si mesmo. Escritas exigem sessão JWT; a família `engines` exige JWT também
  na leitura, então uma API key só lista bindings de plataforma. Engines ficam ligadas com
  `IAM_MODE=enforce` ou com o alias depreciado `ENGINE_ACCESS_ENABLED=true`; biblioteca,
  controle e IAM humano de engines exigem JWT e RBAC/ABAC atual, inclusive para leitura.
  `/auth/me` expõe as permissões para navegação: as de engines vêm só dos bindings
  `engines` vigentes. Veja [perfis e acesso](execution-profiles.md).
- **Usuário root ([spec 0019](../specs/0019-usuario-root-na-primeira-inicializacao.md)):** a
  primeira conta cadastrada numa instalação sem root nasce **root**: admin de emergência
  (bootstrap) do IAM, único (índice único em `users.root_slot`) e irrevogável pela aplicação
  — não pode ser desativado nem perder o admin (`409 ROOT_IMMUTABLE`), e continua admin mesmo
  com `is_admin` zerado por SQL. `GET /auth/setup` (público) diz se o root já existe e se o
  token é exigido; a tela de cadastro usa isso. Com `ENVIRONMENT=production`, o root só nasce
  com `ROOT_SETUP_TOKEN` (`403 ROOT_SETUP_TOKEN_REQUIRED` enquanto não estiver configurado;
  `403 ROOT_SETUP_TOKEN_INVALID` com token ausente ou errado). Fora de produção o token é
  opcional e, se configurado, obrigatório. Depois que o root existe, o token é ignorado;
  remova-o do ambiente. Um deploy exposto feito só com o `docker-compose.yml` base roda com
  `ENVIRONMENT=development`: configure o token nesse caso também.
- **Outros admins:** pelo shell do servidor ou do container, por e-mail ou id, nunca por
  username (que qualquer um escolhe no cadastro). Em instalações que já tinham usuários antes
  da 0019, `--root` designa o root quando ainda não há nenhum (nunca o substitui):

  ```bash
  docker compose exec api python scripts/make_admin.py --email alice@example.com
  docker compose exec api python scripts/make_admin.py --id <uuid> --yes   # sem pergunta
  docker compose exec api python scripts/make_admin.py --email alice@example.com --root
  ```

  O script mostra id, username e e-mail e pede confirmação. Ele recusa quando o e-mail
  informado é também o *username* de outra conta (alguém poderia se cadastrar com o username
  `ops@empresa.com` para ser promovido no lugar do dono desse e-mail); nesse caso, confira
  quem é quem e use `--id`.

## Configuração

| Variável | Default | Observação |
|---|---|---|
| `JWT_SECRET_KEY` | **obrigatória** | ≥ 32 caracteres; placeholders conhecidos são recusados. Gere com `openssl rand -hex 32` (ou `make ensure-jwt-secret`). A API não sobe sem ela. |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_EXPIRATION_MINUTES` | `60` | |
| `ADMIN_USER_IDS` | vazio | Ninguém é admin por padrão (além do root). |
| `ROOT_SETUP_TOKEN` | vazio | Spec 0019. Obrigatório em `production` para criar o root; opcional fora dela. Use uma vez e remova. |
| `CORS_ALLOWED_ORIGINS` | `localhost`/`127.0.0.1` nas portas 3000, 8000, 8080 | Produção deve definir a origem real do frontend. |
| `ENVIRONMENT` | `production` (o `docker-compose.yml` base define `development`; o `.prod.yml` volta a `production`) | Em `production`, erros 500 não expõem a mensagem da exceção e falhas de MySQL/Redis no startup derrubam a API. |
| `AUTH_ENABLED` | `true` | **Sem efeito**: declarada, não lida por nenhum código. Não existe modo sem autenticação. |

## Limites e lacunas conhecidas

- Um usuário desativado (`is_active=false`) recebe `400 Inactive user`, não `401/403`.
- Revogar uma API key a apaga (não há "desativar"); o campo `is_active` não tem endpoint.
- Não há escopos configuráveis por chave nas APIs de jobs. Controle, biblioteca e IAM
  humano exigem sessão JWT; bindings de engines não autorizam essas rotas por API key.
- O header `Authorization` colide com o token de provedor exigido por Google Drive/Dropbox
  (ver [sources.md](sources.md#limites-e-lacunas-conhecidas)).
