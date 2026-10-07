# Autenticação, API keys e autorização

> Contratos dos endpoints revisados em 2026-10-06. Campos, modelos e autorização:
> [referência completa da API](../api-reference.md). As datas abaixo também registram revisões da implementação/operação.

> Verificado contra o código em 2026-10-04. Fonte da verdade:
> [backend/api/auth_routes.py](../../backend/api/auth_routes.py),
> [backend/api/apikey_routes.py](../../backend/api/apikey_routes.py),
> [backend/shared/auth.py](../../backend/shared/auth.py),
> [backend/shared/rate_limit.py](../../backend/shared/rate_limit.py),
> [backend/api/deps.py](../../backend/api/deps.py),
> [backend/api/admin_routes.py](../../backend/api/admin_routes.py).

## O que faz

As rotas de usuário exigem autenticação. A dependência `get_current_active_user`
aceita os dois mecanismos abaixo; refresh exige JWT, sessões administrativas de
engines exigem JWT sem API key, e hosts internos usam uma identidade própria:

1. **JWT** (sessão): `Authorization: Bearer <jwt>`, obtido em `/auth/login`.
2. **API key** (acesso programático): `X-API-Key: doc2md_sk_…`, criada em `/api-keys/`.

Se os dois headers vierem, **o JWT é tentado primeiro** e, se inválido, a requisição falha
com `401` (não cai para a API key).

Endpoints públicos: `GET /`, `GET /health`, `GET /auth/registration-settings`, `POST /auth/register`, `POST /auth/login`,
`/docs`, `/redoc`, `/openapi.json`.

## Como usar

### Usuários e sessão (`/auth`)

| Método e caminho | Corpo | Resposta |
|---|---|---|
| `POST /auth/register` | JSON `{email, username, password}` | `201` + usuário (`id, email, username, is_active, created_at`). `400` se e-mail/username já existe; `403` se o cadastro está fechado. |
| `GET /auth/registration-settings` | Nenhum (público) | `{signup_enabled: boolean}`, sem cache HTTP. |
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

### Habilitar ou desabilitar novos cadastros

Em **Admin → Settings → Allow signups**, um administrador pode abrir ou fechar
o cadastro. A mudança é salva imediatamente no banco (`platform_settings`) e
vale para todas as instâncias da API, inclusive após reiniciar. O padrão é
**habilitado**, preservando instalações existentes e o cadastro do primeiro usuário.
Somente a disponibilidade do cadastro é exposta na consulta pública.

- `GET /admin/settings`: consulta a configuração; exige administrador.
- `PATCH /admin/settings` com `{"signup_enabled": false}` fecha o cadastro;
  `true` reabre. Aceita somente booleanos JSON e recusa campos desconhecidos.
- Com o cadastro fechado, `POST /auth/register` retorna `403`, inclusive quando
  chamado diretamente ou por um administrador. Login, sessões e contas existentes
  continuam funcionando.
- O login oculta o link de cadastro e `/register` mostra uma mensagem de cadastro
  fechado. As páginas consultam a política ao abrir, ao recuperar foco e a cada
  30 segundos; a API sempre verifica a política atual ao receber um cadastro.
- Se a consulta falhar, o frontend não libera o formulário. Uma falha no banco
  também não faz a API liberar cadastros.

A tabela nova é criada pelo `init_db()` existente no startup da API, sem alterar
tabelas de usuários ou jobs. Não é necessário executar a cadeia Alembic em instalações
que não são geridas por ela. A política só muda quando um administrador a salva.

### API keys (`/api-keys`)

| Método e caminho | Descrição |
|---|---|
| `POST /api-keys/` | JSON `{name, expires_in_days?, project?, project_id?}`. Expiração de 1–365 dias, ou `null`; projeto por nome ou ID são exclusivos. Devolve `api_key` **uma única vez**. |
| `GET /api-keys/` | Lista direta das chaves do usuário (sem o valor): `id, name, last_used_at, expires_at, is_active, created_at, project`. |
| `PATCH /api-keys/{key_id}` | JSON `{project_id: "<id>"}` altera o projeto vinculado; `{project_id: null}` desvincula. O campo é obrigatório. |
| `DELETE /api-keys/{key_id}` | Apaga a chave (`204`; `404` se não for do usuário). |

```bash
curl -X POST http://localhost:8000/api-keys/ -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"servidor-ci","expires_in_days":90}'
```

A chave tem o formato `doc2md_sk_<aleatório>`; só o SHA-256 é guardado
(`api_keys.key_hash`). Cada uso atualiza `last_used_at`. Chaves expiradas ou
`is_active=false` são recusadas. A página `/api-keys` do frontend usa estes endpoints.

Uma key vinculada permite criar jobs sem enviar projeto, desde que a chamada
use somente `X-API-Key`. Projeto explícito prevalece sobre o vínculo; JWT junto
com a key ignora o vínculo. Keys não concedem acesso a recursos de outro usuário.
Sessões admin de engines/roteamento exigem JWT e recusam keys, mesmo junto com
JWT. Os hosts internos usam `X-Engine-Host-Token`, não uma key de usuário.
O [catálogo completo](../api-reference.md) indica o acesso de cada operação.

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
  admin recebe `403`. Compute pode conceder acesso por grants quando
  `ENGINE_ACCESS_ENABLED=true`: biblioteca, controle e IAM humano exigem JWT e
  RBAC/ABAC atual, inclusive para leitura; uma API key não transmite esses papéis.
  `/auth/me` expõe as permissões para navegação. Veja [perfis e acesso](execution-profiles.md).
  Endpoints gerais em
  [monitoring-and-admin.md](monitoring-and-admin.md).
- **Primeiro admin:** pelo shell do servidor ou do container, por e-mail ou id, nunca por
  username (que qualquer um escolhe no cadastro):

  ```bash
  docker compose exec api python scripts/make_admin.py --email alice@example.com
  docker compose exec api python scripts/make_admin.py --id <uuid> --yes   # sem pergunta
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
| `ADMIN_USER_IDS` | vazio | Ninguém é admin por padrão. |
| `CORS_ALLOWED_ORIGINS` | `localhost`/`127.0.0.1` nas portas 3000, 8000, 8080 | Produção deve definir a origem real do frontend. |
| `ENVIRONMENT` | `production` (o `docker-compose.yml` base define `development`; o `.prod.yml` volta a `production`) | Em `production`, erros 500 não expõem a mensagem da exceção e falhas de MySQL/Redis no startup derrubam a API. |
| `AUTH_ENABLED` | `true` | **Sem efeito**: declarada, não lida por nenhum código. Não existe modo sem autenticação. |

## Limites e lacunas conhecidas

- Um usuário desativado (`is_active=false`) recebe `400 Inactive user`, não `401/403`.
- Revogar uma API key a apaga (não há "desativar"); o campo `is_active` não tem endpoint.
- Não há escopos configuráveis por chave nas APIs de jobs. Controle, biblioteca e IAM
  humano exigem sessão JWT; grants Compute não autorizam essas rotas por API key.
- O header `Authorization` colide com o token de provedor exigido por Google Drive/Dropbox
  (ver [sources.md](sources.md#limites-e-lacunas-conhecidas)).
