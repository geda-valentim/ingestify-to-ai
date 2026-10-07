# Referência completa dos endpoints

Gerado do OpenAPI da aplicação por `scripts/generate_api_docs.py`. Não edite este arquivo à mão.

API `1.0.0`: **138 operações HTTP** e **1 WebSocket(s)**.

Base pública de desenvolvimento: `https://dev.ingestify.ai/api`. Os caminhos abaixo são relativos à base.

Guias de imagem: [PT](https://dev.ingestify.ai/pt/docs/images) / [EN](https://dev.ingestify.ai/docs/images). [Swagger](https://dev.ingestify.ai/api/docs), [OpenAPI JSON](https://dev.ingestify.ai/api/openapi.json).

## Convenções

- JWT: `Authorization: Bearer <token>`; API key: `X-API-Key: <chave>`. Com ambos, vale o JWT nas rotas de usuário.
- Rotas que exigem sessão de administrador recusam API key, inclusive junto com JWT. Hosts internos usam a identidade própria.
- Jobs exigem projeto: `project` ou `project_id`, salvo API key vinculada. `folder`/`folder_id` são opcionais e mutuamente exclusivos.
- “Obrigatório” nas tabelas representa validação estrutural; regras condicionais estão nas notas e guias.
- As respostas listadas são as declaradas no contrato. Erros de autenticação, propriedade e infraestrutura podem acrescentar 401/403/404/409/413/429/503.
- Um esquema livre `{}` não promete campos fixos; consulte a descrição e o guia da funcionalidade para respostas dinâmicas.
- Erros HTTP geralmente usam `detail` (texto, objeto ou lista de validação). Falhas globais usam `error`, `detail` e `timestamp`.
- DELETE com 204 não tem corpo. Formatos TXT/VTT/SRT/PDF e SSE não devem ser interpretados como envelopes JSON.

## Índice

| Método | Caminho | Autorização | Resumo |
| --- | --- | --- | --- |
| POST | `/auth/register` | Público | Register |
| GET | `/auth/setup` | Público | Installation setup state (public) |
| POST | `/auth/login` | Público | Login |
| POST | `/auth/refresh` | JWT | Refresh Token |
| GET | `/auth/me` | JWT ou API key | Get Current User Info |
| GET | `/api-keys/` | JWT ou API key | List Api Keys |
| POST | `/api-keys/` | JWT ou API key | Create Api Key |
| PATCH | `/api-keys/{key_id}` | JWT ou API key | Update Api Key Project |
| DELETE | `/api-keys/{key_id}` | JWT ou API key | Revoke Api Key |
| GET | `/admin/stats` | Administrador (JWT ou API key) | Get system statistics |
| GET | `/admin/jobs/stuck` | Administrador (JWT ou API key) | List stuck jobs |
| POST | `/admin/jobs/recover-stuck` | Administrador (JWT ou API key) | Manually trigger stuck job recovery |
| POST | `/admin/jobs/{job_id}/retry-all-failed` | Administrador (JWT ou API key) | Bulk retry all failed pages of a job |
| POST | `/admin/cleanup` | Administrador (JWT ou API key) | Manually trigger cleanup of old jobs |
| GET | `/admin/health/monitoring` | Administrador (JWT ou API key) | Check monitoring system health |
| GET | `/admin/broker/unacked` | Administrador (JWT ou API key) | List unacknowledged broker messages |
| POST | `/admin/broker/unacked/{delivery_tag}/requeue` | Administrador (JWT ou API key) | Requeue an orphaned broker message |
| GET | `/images/faces/capabilities` | JWT ou API key | Modelos, parâmetros e prontidão da análise facial |
| POST | `/images/faces` | JWT ou API key | Detectar rostos e analisar expressões em uma imagem base64 |
| POST | `/images/faces/upload` | JWT ou API key | Upload de imagem para detecção facial e expressões |
| POST | `/datalakes/discover` | JWT ou API key | Discover Connection |
| POST | `/datalakes/buckets` | JWT ou API key | Create Bucket |
| POST | `/datalakes/partition-preview` | JWT ou API key | Partition Preview |
| GET | `/datalakes` | JWT ou API key | List Connections |
| POST | `/datalakes` | JWT ou API key | Create Connection |
| PATCH | `/datalakes/{connection_id}` | JWT ou API key | Update Connection |
| DELETE | `/datalakes/{connection_id}` | JWT ou API key | Delete Connection |
| GET | `/datalakes/{connection_id}/buckets` | JWT ou API key | List Buckets |
| POST | `/datalakes/{connection_id}/test` | JWT ou API key | Test Connection |
| GET | `/datalakes/{connection_id}/objects` | JWT ou API key | List Objects |
| GET | `/jobs/{job_id}/datalake` | JWT ou API key | Get Delivery |
| POST | `/jobs/{job_id}/datalake/retry` | JWT ou API key | Retry Delivery |
| POST | `/images/describe` | JWT ou API key | Descrever imagem (JSON base64) |
| POST | `/images/analyze` | JWT ou API key | Executar tarefa de visão (JSON base64) |
| POST | `/images/analyze/upload` | JWT ou API key | Executar tarefa de visão (multipart) |
| POST | `/images/describe/upload` | JWT ou API key | Descrever imagem (multipart) |
| POST | `/images/ocr` | JWT ou API key | OCR de imagem (JSON base64) |
| POST | `/images/ocr/upload` | JWT ou API key | OCR de imagem (multipart) |
| GET | `/images/capabilities` | JWT ou API key | Estado do subsistema de visão |
| POST | `/images/{job_id}/cancel` | JWT ou API key | Cancelar análise composta de imagem |
| GET | `/tags` | JWT ou API key | Listar as tags do usuário |
| PUT | `/jobs/{job_id}/tags` | JWT ou API key | Definir as tags de um job |
| GET | `/admin/routing` | Administrador (JWT ou API key) | Feature routes and their backlog |
| PUT | `/admin/routing/{feature}` | Administrador (somente JWT) | Create or replace a feature's route |
| DELETE | `/admin/routing/{feature}` | Administrador (somente JWT) | Remove a route (it drains back to today's path) |
| GET | `/admin/engines/status` | Administrador (JWT ou API key) | Dispatcher, in-flight work and backlog |
| GET | `/admin/engine-adapters` | JWT | Engine adapters, their GPUs and limits |
| GET | `/admin/engines` | JWT | List engines |
| POST | `/admin/engines` | Administrador (somente JWT) | Connection |
| GET | `/admin/engines/{engine_id}` | JWT | One engine |
| GET | `/admin/gpus` | Administrador (JWT ou API key) | Physical GPUs: declared vs detected, VRAM budgeted and used |
| PUT | `/admin/engines/{engine_id}/features/{feature}` | Administrador (somente JWT) | Set how a feature runs on an engine |
| DELETE | `/admin/engines/{engine_id}/features/{feature}` | Administrador (somente JWT) | Stop running a feature on an engine |
| PUT | `/admin/engines/{engine_id}/gpus` | Administrador (somente JWT) | Declare the local engine's physical GPUs |
| POST | `/admin/engines/{engine_id}/test` | Administrador (somente JWT) | Test an engine's credentials and deployment (no GPU) |
| POST | `/admin/engines/{engine_id}/activate` | Administrador (somente JWT) | Let the dispatcher place work on an engine |
| POST | `/admin/engines/{engine_id}/pause` | Administrador (somente JWT) | Stop placing new work on an engine (work in flight finishes) |
| POST | `/admin/engines/{engine_id}/reset-health` | Administrador (somente JWT) | Forget an engine's recorded failures |
| PUT | `/admin/engines/{engine_id}/budget` | Administrador (somente JWT) | Set an engine's spending ceiling per period |
| PUT | `/admin/engines/{engine_id}/credentials` | JWT | Replace an engine's credentials (sealed, write-only) |
| DELETE | `/admin/engines/{engine_id}/credentials` | JWT | Forget an engine's credentials |
| GET | `/admin/engines/{engine_id}/benchmarks` | Administrador (JWT ou API key) | Benchmark results (gpu x E) and the learned speed per key |
| POST | `/admin/engines/{engine_id}/reconcile` | Administrador (somente JWT) | Read the provider's spend report for one engine now |
| POST | `/admin/engines/test-all` | Administrador (somente JWT) | Test every remote engine's credentials and deployment, in turn (no GPU) |
| GET | `/admin/access/me` | JWT | Me |
| GET | `/admin/execution-profiles` | JWT | Profiles |
| POST | `/admin/execution-profiles` | JWT | Create |
| GET | `/admin/execution-profiles/{id}` | JWT | Detail |
| PUT | `/admin/execution-profiles/{id}` | JWT | Metadata |
| POST | `/admin/execution-profiles/{id}/revisions` | JWT | Revision |
| POST | `/admin/execution-profiles/{id}/publish` | JWT | Publish |
| POST | `/admin/execution-profiles/{id}/archive` | JWT | Archive |
| POST | `/admin/engines/{id}/runtime-profile/bind` | JWT | Bind |
| POST | `/admin/engines/{id}/runtime-profile/import` | JWT | Import Profile |
| GET | `/admin/access/policies` | JWT | Policies |
| POST | `/admin/access/policies` | JWT | Policy Create |
| POST | `/admin/access/policies/{id}/revisions` | JWT | Policy Revise |
| GET | `/admin/access/roles` | JWT | Roles |
| GET | `/admin/access/subjects` | JWT | Subjects |
| GET | `/admin/access/grants` | JWT | Grants |
| POST | `/admin/access/grants` | JWT | Grant |
| POST | `/admin/access/grants/{id}/revoke` | JWT | Revoke |
| GET | `/admin/access/engine-attributes` | JWT | Attributes |
| PUT | `/admin/access/engine-attributes/{id}` | JWT | Classify |
| GET | `/admin/access/resources` | JWT | Resources |
| PUT | `/admin/access/resources` | JWT | Qualify |
| GET | `/admin/execution-profile-hosts` | JWT | Hosts |
| GET | `/admin/access/installation-principals` | JWT | Principals |
| POST | `/admin/access/installation-principals` | JWT | Principal Create |
| PUT | `/admin/access/installation-principals/{id}` | JWT | Principal State |
| PUT | `/admin/access/subjects/{id}/state` | JWT | Subject State |
| GET | `/iam/permissions` | JWT ou API key | The permission catalog and the managed roles |
| POST | `/iam/check` | JWT ou API key | Which platform permissions the caller holds |
| GET | `/admin/iam/bindings` | Administrador (JWT ou API key) | Platform and engines bindings |
| POST | `/admin/iam/bindings` | Administrador (somente JWT) | Grant a platform or engines role |
| POST | `/admin/iam/bindings/{binding_id}/revoke` | Administrador (somente JWT) | Revoke a platform or engines binding |
| GET | `/admin/engine-control-adapters` | JWT | Adapters |
| GET | `/admin/engines/{engine_id}/capabilities` | JWT | Caps |
| GET | `/admin/model-profiles` | JWT | Model Profiles |
| GET | `/admin/engines/{engine_id}/runtime-profile` | JWT | Get Profile |
| PUT | `/admin/engines/{engine_id}/runtime-profile` | Administrador (somente JWT) | Put Profile |
| GET | `/admin/engines/{engine_id}/runtime-status` | JWT | Status |
| POST | `/admin/engines/{engine_id}/operation-plans` | JWT | Plan |
| POST | `/admin/engines/{engine_id}/operations` | JWT | Execute |
| GET | `/admin/engine-operations` | JWT | History |
| GET | `/admin/engine-operations/{operation_id}` | JWT | Snapshot |
| GET | `/admin/engine-operations/{operation_id}/events` | JWT | Events |
| POST | `/admin/engine-operations/{operation_id}/cancel` | JWT | Cancel |
| GET | `/admin/engine-operations/{operation_id}/stream` | JWT | Stream |
| POST | `/admin/engine-operations/{operation_id}/recover` | JWT | Recover |
| POST | `/internal/engine-hosts/{host_id}/heartbeat` | X-Engine-Host-Token do host | Host Heartbeat |
| GET | `/internal/engine-hosts/{host_id}/next` | X-Engine-Host-Token do host | Host Next |
| GET | `/internal/engine-hosts/{host_id}/operations/{op_id}/check` | X-Engine-Host-Token do host | Host Check |
| POST | `/internal/engine-hosts/{host_id}/operations/{op_id}/events` | X-Engine-Host-Token do host | Host Event |
| POST | `/internal/engine-hosts/{host_id}/operations/{op_id}/result` | X-Engine-Host-Token do host | Host Result |
| GET | `/projects` | JWT ou API key | Listar projetos com contagens |
| GET | `/projects/resolve` | JWT ou API key | Um nome de projeto casa com um projeto existente? |
| GET | `/projects/{project_id}/folders/resolve` | JWT ou API key | Um nome de pasta casa com uma pasta existente do projeto? |
| POST | `/transcribe/live/sessions` | JWT ou API key | Create Session |
| GET | `/transcribe/live/sessions/{job_id}` | JWT ou API key | Session Status |
| DELETE | `/transcribe/live/sessions/{job_id}` | JWT ou API key | Cancel Session |
| POST | `/upload` | JWT ou API key | Upload e converter arquivo |
| POST | `/transcribe` | JWT ou API key | Transcrever áudio ou vídeo (STT, legendas VTT/SRT) |
| POST | `/convert` | JWT ou API key | Convert Document |
| GET | `/jobs/{job_id}` | JWT ou API key | Get Job Status |
| DELETE | `/jobs/{job_id}` | JWT ou API key | Deletar job |
| DELETE | `/jobs/{job_id}/source` | JWT ou API key | Apagar o arquivo original do job |
| GET | `/jobs/{job_id}/result` | JWT ou API key | Get Job Result |
| GET | `/jobs/{job_id}/transcript/partial` | JWT ou API key | Get Partial Transcript |
| GET | `/jobs/{job_id}/pages` | JWT ou API key | Get Job Pages |
| GET | `/jobs/{job_id}/pages/{page_number}/status` | JWT ou API key | Status de página específica por número |
| GET | `/jobs/{job_id}/pages/{page_number}/result` | JWT ou API key | Resultado de página específica por número |
| GET | `/jobs` | JWT ou API key | Listar jobs do usuário |
| GET | `/search` | JWT ou API key | Buscar jobs por conteúdo |
| POST | `/jobs/{job_id}/pages/{page_number}/retry` | JWT ou API key | Retry de página que falhou |
| GET | `/jobs/{job_id}/pages/{page_number}/pdf` | JWT ou API key | URL temporária do PDF de uma página |
| GET | `/health` | Público | Health Check |
| GET | `/` | Público | Root |

## Authentication

### POST /auth/register

Register

Autorização: **Público**. Operation ID: `register_auth_register_post`.

Register a new user

## Request Body:
```json
{
  "email": "user@example.com",
  "username": "testuser",
  "password": "Test123"
}
```

## Returns:
User object with id, email, username, is_active, created_at, is_admin

The first account of an installation without root becomes its root user
(spec 0019); see GET /auth/setup. `setup_token` is only read for that account.

## Errors:
- 400: Email or username already exists
- 403: ROOT_SETUP_TOKEN_REQUIRED / ROOT_SETUP_TOKEN_INVALID (root account only)
- 429: Too many registrations from this IP

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [UserCreate](#model-usercreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `email` | sim | string |  |  |
| `username` | sim | string | minLength=3; maxLength=50 |  |
| `password` | sim | string | minLength=8; maxLength=20 |  |
| `setup_token` | não | string / null |  | Installation setup token; only read when creating the root user |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | [UserResponse](#model-userresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /auth/setup

Installation setup state (public)

Autorização: **Público**. Operation ID: `setup_status_auth_setup_get`.

Whether this installation still needs its root user (spec 0019).

`root_pending` is true only for a brand-new installation (no users): the next
registration becomes root. An installation with users but no root keeps plain
registrations; an operator designates root with `make_admin.py --root`.
Public on purpose: the registration screen uses it to explain that the account
becomes root and whether a setup token is needed. Reveals nothing else.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [SetupStatus](#model-setupstatus) | Successful Response |

### POST /auth/login

Login

Autorização: **Público**. Operation ID: `login_auth_login_post`.

Login with username/email and password (OAuth2 compatible)

## Request Body (form-urlencoded):
- username: testuser (or email)
- password: Test123

## Returns:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

## Usage:
Use the access_token in subsequent requests:
```
Authorization: Bearer eyJ...
```

## Errors:
- 401: Invalid credentials
- 429: Too many attempts (per IP, or too many failures for this account)

Corpo obrigatório: sim.

Content-Type: `application/x-www-form-urlencoded`. Esquema: [Body_login_auth_login_post](#model-body_login_auth_login_post).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `username` | sim | string |  |  |
| `password` | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [Token](#model-token) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /auth/refresh

Refresh Token

Autorização: **JWT**. Operation ID: `refresh_token_auth_refresh_post`.

Troca um JWT ainda válido por um novo, com validade renovada.

É o "heartbeat" do frontend: enquanto a pessoa usa o app, a sessão é
renovada antes de expirar; parada por mais que `JWT_EXPIRATION_MINUTES`,
ela expira e o login é pedido de novo.

Só aceita `Authorization: Bearer <jwt>`. Uma API key não vira sessão.

## Erros:
- 401: token ausente, expirado ou inválido, ou usuário inativo

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [Token](#model-token) | Successful Response |

### GET /auth/me

Get Current User Info

Autorização: **JWT ou API key**. Operation ID: `get_current_user_info_auth_me_get`.

Get information about the currently authenticated user

## Headers Required:
```
Authorization: Bearer <token>
```
or
```
X-API-Key: <api_key>
```

## Returns:
User object with id, email, username, is_active, created_at, is_admin, and:
- `permissions`: flat list, the 0009 engine permissions plus the platform/IAM
  permissions the caller holds under the current IAM_MODE (spec 0014 CA12)
- `bootstrap`: emergency access (the is_admin column or ADMIN_USER_IDS)
- `platform_roles`: managed roles held through active bindings

## Errors:
- 401: Not authenticated or invalid token/API key

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [UserResponse](#model-userresponse) | Successful Response |

## API Keys

### GET /api-keys/

List Api Keys

Autorização: **JWT ou API key**. Operation ID: `list_api_keys_api_keys__get`.

List all API keys for the authenticated user

## Returns:
Array of API key info (without the actual key):
```json
[
  {
    "id": "uuid",
    "name": "Production Server",
    "last_used_at": "2025-10-02T12:00:00",
    "expires_at": "2025-11-01T00:00:00",
    "is_active": true,
    "created_at": "2025-10-02T00:00:00"
  }
]
```

## Note:
The actual API key is NOT returned (for security).
It's only shown once during creation.

## Errors:
- 401: Not authenticated

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | array de [APIKeyInfo](#model-apikeyinfo) | Successful Response |

### POST /api-keys/

Create Api Key

Autorização: **JWT ou API key**. Operation ID: `create_api_key_api_keys__post`.

Create a new API key for the authenticated user

## Request Body:
```json
{
  "name": "Production Server",
  "expires_in_days": 30,  // optional, null = never expires
  "project": "Transcrições automáticas"  // optional: name (get-or-add) or "project_id"
}
```

Uploads made with a key bound to a project, that do not name a project,
go to that project. A request that also sends a JWT is a JWT request and
does not use the binding.

## Returns:
```json
{
  "id": "uuid",
  "name": "Production Server",
  "api_key": "doc2md_sk_...",  // ONLY SHOWN ONCE!
  "expires_at": "2025-11-01T00:00:00",
  "created_at": "2025-10-02T00:00:00"
}
```

## Important:
- The `api_key` is shown ONLY ONCE during creation
- Save it immediately - you won't be able to see it again
- Use it in requests with header: `X-API-Key: doc2md_sk_...`

## Errors:
- 401: Not authenticated

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [APIKeyCreate](#model-apikeycreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | sim | string | minLength=1; maxLength=100 |  |
| `expires_in_days` | não | integer / null |  |  |
| `project` | não | string / null |  | Projeto vinculado, por nome (criado se não existir). Exclusivo com project_id. |
| `project_id` | não | string / null |  | Projeto vinculado, por ID. Exclusivo com project. |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | [APIKeyResponse](#model-apikeyresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### PATCH /api-keys/{key_id}

Update Api Key Project

Autorização: **JWT ou API key**. Operation ID: `update_api_key_project_api_keys__key_id__patch`.

Bind the key to a project, or unbind it (`{"project_id": null}`)

Uploads made with this key that name no project go to the bound project.
A key without a project must send `project` on every upload (422 otherwise).
Re-binding changes where new uploads go; a file already processed in another
project is processed again in the new one.

## Errors:
- 404: API key or project not found (or not yours)

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `key_id` | path | sim | string (uuid) |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [APIKeyProjectUpdate](#model-apikeyprojectupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `project_id` | sim | string / null |  | Projeto para onde vão os uploads desta key que não dizem o projeto; null desvincula. |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [APIKeyInfo](#model-apikeyinfo) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### DELETE /api-keys/{key_id}

Revoke Api Key

Autorização: **JWT ou API key**. Operation ID: `revoke_api_key_api_keys__key_id__delete`.

Revoke (delete) an API key

## Path Parameters:
- `key_id`: UUID of the API key to revoke

## Returns:
204 No Content on success

## Errors:
- 401: Not authenticated
- 404: API key not found or doesn't belong to user

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `key_id` | path | sim | string (uuid) |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 204 | — | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Admin & Monitoring

### GET /admin/stats

Get system statistics

Autorização: **Administrador (JWT ou API key)**. Operation ID: `get_stats_admin_stats_get`.

Get comprehensive system statistics for monitoring dashboard

Returns counts of jobs/pages by status, stuck jobs, etc.
Useful for building admin dashboards and monitoring tools.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |

### GET /admin/jobs/stuck

List stuck jobs

Autorização: **Administrador (JWT ou API key)**. Operation ID: `list_stuck_jobs_admin_jobs_stuck_get`.

List all jobs currently stuck in processing state

Args:
    threshold_minutes: Override default threshold (from config if not specified)
    limit: Maximum number of jobs to return

Returns:
    List of stuck jobs with details

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `threshold_minutes` | query | não | integer |  |  |
| `limit` | query | não | integer | default=100 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/jobs/recover-stuck

Manually trigger stuck job recovery

Autorização: **Administrador (JWT ou API key)**. Operation ID: `recover_stuck_jobs_admin_jobs_recover_stuck_post`.

Manually trigger the stuck job detection and recovery process

This runs the same logic as the periodic monitoring task,
but can be triggered on-demand by administrators.

Args:
    threshold_minutes: Override default threshold (from config if not specified)

Returns:
    Number of jobs/pages marked as failed

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `threshold_minutes` | query | não | integer |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/jobs/{job_id}/retry-all-failed

Bulk retry all failed pages of a job

Autorização: **Administrador (JWT ou API key)**. Operation ID: `retry_all_failed_pages_admin_jobs__job_id__retry_all_failed_post`.

Retry all failed pages of a specific job

Requeues every FAILED page still under the retry limit
(`MONITORING_MAX_RETRY_COUNT`), exactly like the per-page retry
(`POST /jobs/{job_id}/pages/{n}/retry`): the original PDF is located first,
then the pages become pending and the job processing, under the job's row
lock (the same lock the source purge takes).

Returns:
    Number of pages queued for retry

Errors:
    404: job not found
    409 `SOURCE_NOT_AVAILABLE`: the original was deleted (purge_source /
    DELETE /jobs/{id}/source); nothing was changed

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/cleanup

Manually trigger cleanup of old jobs

Autorização: **Administrador (JWT ou API key)**. Operation ID: `trigger_cleanup_admin_cleanup_post`.

Manually trigger cleanup of old completed/failed jobs from Redis

Args:
    days_old: Override default days threshold (from config if not specified)

Returns:
    Number of jobs cleaned up

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `days_old` | query | não | integer |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/health/monitoring

Check monitoring system health

Autorização: **Administrador (JWT ou API key)**. Operation ID: `monitoring_health_admin_health_monitoring_get`.

Check if the monitoring system (Celery Beat) is functioning

Returns information about scheduled tasks and their last run times

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |

### GET /admin/broker/unacked

List unacknowledged broker messages

Autorização: **Administrador (JWT ou API key)**. Operation ID: `list_broker_unacked_admin_broker_unacked_get`.

Messages the Celery broker holds as delivered but not yet acknowledged.

Each one is either a task running now or one whose worker died - the latter only
returns to its queue after CELERY_VISIBILITY_TIMEOUT_SECONDS (hours). `orphans` is
the latest check by workers.monitoring.check_broker_unacked: messages no live
worker held on two consecutive checks. Requeue one with
POST /admin/broker/unacked/{delivery_tag}/requeue.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |

### POST /admin/broker/unacked/{delivery_tag}/requeue

Requeue an orphaned broker message

Autorização: **Administrador (JWT ou API key)**. Operation ID: `requeue_broker_unacked_admin_broker_unacked__delivery_tag__requeue_post`.

Put an orphaned message back at the head of its queue, so its task runs again now
instead of after the visibility timeout.

Refused (409) unless the latest monitoring check flagged it as orphaned AND no
worker reports holding it right now - otherwise a task still running would run
twice.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `delivery_tag` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Vision

### GET /images/faces/capabilities

Modelos, parâmetros e prontidão da análise facial

Autorização: **JWT ou API key**. Operation ID: `capabilities_images_faces_capabilities_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /images/faces

Detectar rostos e analisar expressões em uma imagem base64

Autorização: **JWT ou API key**. Operation ID: `analyze_images_faces_post`.

Operações compostas exigem Idempotency-Key. Mesma chave e payload retornam o mesmo job; payload divergente retorna 409 e job excluído retorna 410. wait=false retorna 202; wait=true pode retornar 504 mantendo o job. Full sem perfil conserva v1; v2 inclui rostos e expressões.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `idempotency-key` | header | sim | string | minLength=1; maxLength=128 |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [FaceAnalyzeRequest](#model-faceanalyzerequest).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `image_base64` | sim | string |  | Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF. |
| `tags` | não | array de string / null |  | Tags do job (ex.: ["cliente-x", "nf"]). Viram minúsculas; até 20 de até 50 caracteres. |
| `filename` | não | string / null |  | Nome de identificação opcional. |
| `project` | não | string / null |  | Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a `project`). |
| `folder` | não | string / null |  | Nome da pasta no projeto (opcional, get-or-add, sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta (wait=true) e o relatório trazem `image.image_base64` null. `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada. |
| `face_options` | não | [FaceRequestOptions](#model-facerequestoptions) |  |  |
| `wait` | não | boolean | default=false |  |
| `datalake` | não | [Destination](#model-destination) / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 202 | application/json | [FaceAnalyzeResponse](#model-faceanalyzeresponse) / [ImageFullQueuedResponse](#model-imagefullqueuedresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |
| 409 | — | objeto livre | Chave utilizada com outra solicitação. |
| 410 | — | objeto livre | Job da chave excluído; envie uma chave nova. |

### POST /images/faces/upload

Upload de imagem para detecção facial e expressões

Autorização: **JWT ou API key**. Operation ID: `upload_images_faces_upload_post`.

Operações compostas exigem Idempotency-Key. Mesma chave e payload retornam o mesmo job; payload divergente retorna 409 e job excluído retorna 410. wait=false retorna 202; wait=true pode retornar 504 mantendo o job. Full sem perfil conserva v1; v2 inclui rostos e expressões.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `idempotency-key` | header | sim | string | minLength=1; maxLength=128 |  |

Corpo obrigatório: sim.

Content-Type: `multipart/form-data`. Esquema: [Body_upload_images_faces_upload_post](#model-body_upload_images_faces_upload_post).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  |  |
| `face_options` | não | string / null |  |  |
| `wait` | não | boolean | default=false |  |
| `project` | não | string / null |  |  |
| `project_id` | não | string / null |  |  |
| `folder` | não | string / null |  |  |
| `folder_id` | não | string / null |  |  |
| `tags` | não | string / null |  |  |
| `datalake` | não | string / null |  |  |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta (wait=true) e o relatório trazem `image.image_base64` null. `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada. |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 202 | application/json | [FaceAnalyzeResponse](#model-faceanalyzeresponse) / [ImageFullQueuedResponse](#model-imagefullqueuedresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |
| 409 | — | objeto livre | Chave utilizada com outra solicitação. |
| 410 | — | objeto livre | Job da chave excluído; envie uma chave nova. |

### POST /images/describe

Descrever imagem (JSON base64)

Autorização: **JWT ou API key**. Operation ID: `describe_image_images_describe_post`.

Descreve uma imagem enviada em base64 e devolve a mesma imagem de volta.

## Corpo
- `image_base64`: bytes da imagem em base64 (o prefixo `data:image/...;base64,`
  é aceito e removido)
- `filename`: nome opcional, usado no job e no storage
- `task`: `<MORE_DETAILED_CAPTION>` (padrão), `<DETAILED_CAPTION>` ou `<CAPTION>`
- `project` / `project_id` (obrigatório, salvo API key vinculada a um projeto),
  `folder` / `folder_id` (opcional): onde o job fica

## Retorno
A descrição, os metadados da imagem e o eco de `image_base64` — os bytes
exatos que você enviou, re-codificados, nunca uma re-compressão.

## Timeout
Se a inferência passar de `VISION_REQUEST_TIMEOUT_SECONDS`, a resposta é
504 com `job_id`/`poll_url`: a task continua e o resultado sai em
`/jobs/{job_id}/result`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ImageDescribeRequest](#model-imagedescriberequest).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `image_base64` | sim | string |  | Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF. |
| `tags` | não | array de string / null |  | Tags do job (ex.: ["cliente-x", "nf"]). Viram minúsculas; até 20 de até 50 caracteres. |
| `filename` | não | string / null |  | Nome de identificação opcional (usado no job e no storage). |
| `project` | não | string / null |  | Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a `project`). |
| `folder` | não | string / null |  | Nome da pasta no projeto (opcional, get-or-add, sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada. |
| `task` | não | string | default="<MORE_DETAILED_CAPTION>"; enum=["<MORE_DETAILED_CAPTION>", "<DETAILED_CAPTION>", "<CAPTION>"] | Prompt de caption do Florence-2. |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [ImageDescribeResponse](#model-imagedescriberesponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /images/analyze

Executar tarefa de visão (JSON base64)

Autorização: **JWT ou API key**. Operation ID: `analyze_image_images_analyze_post`.

Todas as tarefas do Florence integrado, descobríveis em GET /images/capabilities.

Captions/OCR/detecção/propostas não recebem entradas adicionais. Grounding,
detecção por vocabulário e segmentação por expressão exigem text_input.
Tarefas REGION_TO_* exigem region=[x_min,y_min,x_max,y_max] normalizada (0..1).
generation controla a decodificação. Parâmetros incompatíveis são rejeitados.

Por padrão retorna 202 com job_id; consulte /jobs/{job_id}/result. wait=true
retorna o resultado completo ou 504 com o mesmo job_id, sem cancelar a tarefa.
A resposta preserva output do modelo e regions em pixels da imagem original.

mode=full executa as 15famílias num único job, com entradas derivadas da
imagem. Idempotency-Key é obrigatória; full_options aceita queries (até 3),
regions (até 4), generation e deadline_seconds (até 900, incluindo fila).
Full rejeita task/text_input/region/generation na raiz. datalake opcional
recebe Destination com partitioning/partition_values. Resultado full possui
coverage/results/resolved_inputs e pode terminar partial/failed/cancelled.

Operações compostas exigem Idempotency-Key. Mesma chave e payload retornam o mesmo job; payload divergente retorna 409 e job excluído retorna 410. wait=false retorna 202; wait=true pode retornar 504 mantendo o job. Full sem perfil conserva v1; v2 inclui rostos e expressões.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `idempotency-key` | header | não | string / null |  | Obrigatória somente em mode=full; repetir mesma solicitação devolve o mesmo job. |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ImageFullAnalyzeRequest](#model-imagefullanalyzerequest) / [ImageAnalyzeRequest](#model-imageanalyzerequest).

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [ImageAnalyzeResponse](#model-imageanalyzeresponse) / [ImageFullAnalyzeResponse](#model-imagefullanalyzeresponse) / [ImageFullQueuedResponse](#model-imagefullqueuedresponse) / [JobCreatedResponse](#model-jobcreatedresponse) | Successful Response |
| 202 | application/json | [ImageFullQueuedResponse](#model-imagefullqueuedresponse) / [JobCreatedResponse](#model-jobcreatedresponse) | Accepted |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |
| 409 | — | objeto livre | Chave utilizada com outra solicitação. |
| 410 | — | objeto livre | Job da chave excluído; envie uma chave nova. |

### POST /images/analyze/upload

Executar tarefa de visão (multipart)

Autorização: **JWT ou API key**. Operation ID: `analyze_image_upload_images_analyze_upload_post`.

Mesmas tarefas/validações do JSON /images/analyze. region e generation são JSON nos campos multipart.

Para regiões, 0 representa esquerda/topo e 1 direita/base. Não aceita regiões
invertidas/vazias nem texto em tarefas que não o utilizam. Nenhum job é criado
quando as opções são inválidas. Front e integração podem consultar o catálogo
de tarefas e o schema de geração em /images/capabilities.

mode=full: header Idempotency-Key obrigatório, full_options e datalake
codificados como JSON. task, text_input, region e generation na raiz são
incompatíveis com full, mesmo quando explicitamente vazios/padrão.

Operações compostas exigem Idempotency-Key. Mesma chave e payload retornam o mesmo job; payload divergente retorna 409 e job excluído retorna 410. wait=false retorna 202; wait=true pode retornar 504 mantendo o job. Full sem perfil conserva v1; v2 inclui rostos e expressões.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `idempotency-key` | header | não | string / null |  | Obrigatória somente em mode=full (1..128 caracteres). |

Corpo obrigatório: sim.

Content-Type: `multipart/form-data`. Esquema: [Body_analyze_image_upload_images_analyze_upload_post](#model-body_analyze_image_upload_images_analyze_upload_post).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `mode` | não | string | default="single"; enum=["single", "full"] |  |
| `full_options` | não | string / null |  | JSON ImageFullOptions para mode=full |
| `datalake` | não | string / null |  | JSON Destination opcional para mode=full |
| `file` | sim | string (binary) |  | Imagem PNG, JPEG, WEBP, BMP, GIF ou TIFF |
| `task` | não | string | default="<MORE_DETAILED_CAPTION>"; enum=["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>", "<OCR>", "<OCR_WITH_REGION>", "<OD>", "<DENSE_REGION_CAPTION>", "<REGION_PROPOSAL>", "<CAPTION_TO_PHRASE_GROUNDING>", "<REFERRING_EXPRESSION_SEGMENTATION>", "<REGION_TO_SEGMENTATION>", "<OPEN_VOCABULARY_DETECTION>", "<REGION_TO_CATEGORY>", "<REGION_TO_DESCRIPTION>", "<REGION_TO_OCR>"] |  |
| `text_input` | não | string / null |  |  |
| `region` | não | string / null |  | Array JSON [x_min,y_min,x_max,y_max], normalizado entre 0 e 1. |
| `generation` | não | string / null |  | Objeto JSON conforme VisionGenerationOptions; omitido usa os padrões do worker. |
| `wait` | não | boolean | default=false | false retorna 202 com job_id; true espera pelo resultado. |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. mode=single com wait=true: a resposta ainda ecoa `image_base64` no topo (vem dos bytes desta requisição, não de uma cópia guardada). mode=full: a resposta (wait=true) e o relatório trazem `image.image_base64` null, e `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada. |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [ImageAnalyzeResponse](#model-imageanalyzeresponse) / [ImageFullAnalyzeResponse](#model-imagefullanalyzeresponse) / [ImageFullQueuedResponse](#model-imagefullqueuedresponse) / [JobCreatedResponse](#model-jobcreatedresponse) | Successful Response |
| 202 | application/json | [ImageFullQueuedResponse](#model-imagefullqueuedresponse) / [JobCreatedResponse](#model-jobcreatedresponse) | Accepted |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |
| 409 | — | objeto livre | Chave utilizada com outra solicitação. |
| 410 | — | objeto livre | Job da chave excluído; envie uma chave nova. |

### POST /images/describe/upload

Descrever imagem (multipart)

Autorização: **JWT ou API key**. Operation ID: `describe_image_upload_images_describe_upload_post`.

Igual a `POST /images/describe`, com a imagem em `multipart/form-data`.

Existe como caminho irmão porque o FastAPI não hospeda um corpo JSON e
parâmetros `File`/`Form` na mesma operação — e sniffar o content-type
produziria uma única operação ilegível no OpenAPI.

Corpo obrigatório: sim.

Content-Type: `multipart/form-data`. Esquema: [Body_describe_image_upload_images_describe_upload_post](#model-body_describe_image_upload_images_describe_upload_post).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  | Imagem (PNG, JPEG, WEBP, BMP, GIF, TIFF) |
| `task` | não | string | default="<MORE_DETAILED_CAPTION>" | <MORE_DETAILED_CAPTION>, <DETAILED_CAPTION> ou <CAPTION> |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada. |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [ImageDescribeResponse](#model-imagedescriberesponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /images/ocr

OCR de imagem (JSON base64)

Autorização: **JWT ou API key**. Operation ID: `ocr_image_images_ocr_post`.

Extrai o texto de uma imagem com `<OCR_WITH_REGION>` do Florence-2.

Devolve o texto completo e, por linha, o quadrilátero detectado
(`quad_box`, 8 valores) e o retângulo derivado (`bbox`, 4 valores), em
pixels absolutos da imagem original.

Uma imagem sem texto detectável é 200 com `text: ""` e `lines: []` — nunca
um 4xx.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ImageOcrRequest](#model-imageocrrequest).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `image_base64` | sim | string |  | Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF. |
| `tags` | não | array de string / null |  | Tags do job (ex.: ["cliente-x", "nf"]). Viram minúsculas; até 20 de até 50 caracteres. |
| `filename` | não | string / null |  | Nome de identificação opcional. |
| `project` | não | string / null |  | Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a `project`). |
| `folder` | não | string / null |  | Nome da pasta no projeto (opcional, get-or-add, sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada. |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [ImageOcrResponse](#model-imageocrresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /images/ocr/upload

OCR de imagem (multipart)

Autorização: **JWT ou API key**. Operation ID: `ocr_image_upload_images_ocr_upload_post`.

Igual a `POST /images/ocr`, com a imagem em `multipart/form-data`.

Corpo obrigatório: sim.

Content-Type: `multipart/form-data`. Esquema: [Body_ocr_image_upload_images_ocr_upload_post](#model-body_ocr_image_upload_images_ocr_upload_post).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  | Imagem (PNG, JPEG, WEBP, BMP, GIF, TIFF) |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada. |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [ImageOcrResponse](#model-imageocrresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /images/capabilities

Estado do subsistema de visão

Autorização: **JWT ou API key**. Operation ID: `vision_capabilities_images_capabilities_get`.

O que o worker de visão consegue fazer *neste* deploy.

A resposta vem do worker, não da API: a única resposta que vale alguma
coisa descreve o processo que de fato carrega o modelo, e calcular isso
aqui obrigaria a API a importar torch.

## Lê, não enfileira

A sonda **não** é uma task. Uma task de sonda ia para `settings.vision_queue`
— uma vaga só, `worker_prefetch_multiplier=1` — e portanto ficava atrás de
uma inferência de até `vision_task_timeout_seconds`. Consequência: este
endpoint respondia "nenhum worker de visão" exatamente quando havia um
worker *ocupado*, ou seja, no único momento em que alguém consulta. E, pior,
nada limitava a fila: quem batesse aqui em laço enfileirava sondas mais
rápido do que a vaga única drenava, matando a inferência de verdade com a
própria ferramenta de diagnóstico.

Agora o worker publica um heartbeat com TTL no Redis
(`workers/vision_tasks.publish_vision_heartbeat`, em uma thread daemon que
continua rodando durante a inferência) e esta rota faz um GET. Os quatro
estados ficam distinguíveis:

| estado                                  | resposta                                             |
|-----------------------------------------|------------------------------------------------------|
| nenhum worker rodando                   | `dependencies_installed=false` + `reason` de ausência |
| worker rodando e ocioso                 | o relatório do worker                                 |
| worker rodando e **ocupado**            | o relatório do worker — ocupado não é ausente         |
| worker rodando **sem as dependências**  | `dependencies_installed=false` + o `reason` do worker |

Sempre 200: uma sonda de ops não pode dar 5xx quando aquilo que ela sonda
está fora do ar.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [VisionCapabilitiesResponse](#model-visioncapabilitiesresponse) | Successful Response |

### POST /images/{job_id}/cancel

Cancelar análise composta de imagem

Autorização: **JWT ou API key**. Operation ID: `cancel_full_image_images__job_id__cancel_post`.

Cancela Full Analysis ou análise facial do próprio usuário, preservando checkpoints concluídos. Não cancela tarefas de visão single.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Datalakes

### POST /datalakes/discover

Discover Connection

Autorização: **JWT ou API key**. Operation ID: `discover_connection_datalakes_discover_post`.

Read buckets with draft settings, without creating or updating a connection.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [DiscoverConnection](#model-discoverconnection).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `provider` | sim | string | enum=["s3", "minio", "gcs", "azure"] |  |
| `config` | não | [ConnectionConfig](#model-connectionconfig) |  |  |
| `credentials` | não | object / null |  |  |
| `connection_id` | não | string / null |  |  |
| `bucket` | não | string / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /datalakes/buckets

Create Bucket

Autorização: **JWT ou API key**. Operation ID: `create_bucket_datalakes_buckets_post`.

Create storage now; saving the connection remains a separate operation.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [CreateBucket](#model-createbucket).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `provider` | sim | string | enum=["s3", "minio", "gcs", "azure"] |  |
| `config` | não | [ConnectionConfig](#model-connectionconfig) |  |  |
| `credentials` | não | object / null |  |  |
| `connection_id` | não | string / null |  |  |
| `bucket` | sim | string | minLength=3; maxLength=222 |  |
| `location` | não | string / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /datalakes/partition-preview

Partition Preview

Autorização: **JWT ou API key**. Operation ID: `partition_preview_datalakes_partition_preview_post`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [PartitionPreview](#model-partitionpreview).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `connection_id` | não | string / null |  |  |
| `partitioning` | não | [PartitionStrategy](#model-partitionstrategy) / null |  |  |
| `partition_values` | não | object | additionalProperties={"type": "string"} |  |
| `prefix` | não | string | default=""; maxLength=700 |  |
| `created_at` | não | string (date-time) / null |  |  |
| `project_id` | não | string / null |  |  |
| `folder_id` | não | string / null |  |  |
| `source_type` | não | string / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /datalakes

List Connections

Autorização: **JWT ou API key**. Operation ID: `list_connections_datalakes_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /datalakes

Create Connection

Autorização: **JWT ou API key**. Operation ID: `create_connection_datalakes_post`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ConnectionCreate](#model-connectioncreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | sim | string | minLength=1; maxLength=150 |  |
| `provider` | sim | string | enum=["s3", "minio", "gcs", "azure"] |  |
| `config` | não | [ConnectionConfig](#model-connectionconfig) |  |  |
| `credentials` | sim | object | additionalProperties={"type": "string", "format": "password", "writeOnly": true} |  |
| `enabled` | não | boolean | default=true |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### PATCH /datalakes/{connection_id}

Update Connection

Autorização: **JWT ou API key**. Operation ID: `update_connection_datalakes__connection_id__patch`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `connection_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ConnectionUpdate](#model-connectionupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | não | string / null |  |  |
| `config` | não | [ConnectionConfig](#model-connectionconfig) / null |  |  |
| `credentials` | não | object / null |  |  |
| `enabled` | não | boolean / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### DELETE /datalakes/{connection_id}

Delete Connection

Autorização: **JWT ou API key**. Operation ID: `delete_connection_datalakes__connection_id__delete`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `connection_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 204 | — | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /datalakes/{connection_id}/buckets

List Buckets

Autorização: **JWT ou API key**. Operation ID: `list_buckets_datalakes__connection_id__buckets_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `connection_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /datalakes/{connection_id}/test

Test Connection

Autorização: **JWT ou API key**. Operation ID: `test_connection_datalakes__connection_id__test_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `connection_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [TestConnection](#model-testconnection).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `bucket` | não | string / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /datalakes/{connection_id}/objects

List Objects

Autorização: **JWT ou API key**. Operation ID: `list_objects_datalakes__connection_id__objects_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `connection_id` | path | sim | string |  |  |
| `bucket` | query | sim | string |  |  |
| `prefix` | query | não | string | default="" |  |
| `limit` | query | não | integer | default=100; minimum=1; maximum=1000 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /jobs/{job_id}/datalake

Get Delivery

Autorização: **JWT ou API key**. Operation ID: `get_delivery_jobs__job_id__datalake_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /jobs/{job_id}/datalake/retry

Retry Delivery

Autorização: **JWT ou API key**. Operation ID: `retry_delivery_jobs__job_id__datalake_retry_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 202 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Tags

### GET /tags

Listar as tags do usuário

Autorização: **JWT ou API key**. Operation ID: `list_tags_tags_get`.

Todas as tags usadas nos jobs do usuário, com quantos jobs têm cada uma.

Ordenadas da mais usada para a menos usada. Serve para autocompletar e
para montar filtros; filtre a lista com `GET /jobs?tag=...`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [TagListResponse](#model-taglistresponse) | Successful Response |

### PUT /jobs/{job_id}/tags

Definir as tags de um job

Autorização: **JWT ou API key**. Operation ID: `replace_job_tags_jobs__job_id__tags_put`.

Substitui as tags do job pela lista enviada (`[]` remove todas).

As tags são normalizadas como na criação: minúsculas, sem `#`, sem repetição.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [JobTagsUpdate](#model-jobtagsupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `tags` | sim | array de string |  | A lista completa de tags do job (substitui as atuais). |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [JobTagsResponse](#model-jobtagsresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Admin - Engines

### GET /admin/routing

Feature routes and their backlog

Autorização: **Administrador (JWT ou API key)**. Operation ID: `list_routes_admin_routing_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | array de object | Successful Response |

### PUT /admin/routing/{feature}

Create or replace a feature's route

Autorização: **Administrador (somente JWT)**. Operation ID: `put_route_admin_routing__feature__put`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `feature` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [RouteUpdate](#model-routeupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `steps` | sim | array de [RouteStep](#model-routestep) | minItems=1; maxItems=10 |  |
| `on_no_engine` | não | string | default="hold"; enum=["hold", "fail"] |  |
| `fail_after_seconds` | não | integer / null |  |  |
| `max_attempts` | não | integer | default=3; minimum=1.0; maximum=10.0 |  |
| `remote_allowed_for` | não | string | default="admins"; enum=["admins", "all"] |  |
| `user_period_limit_usd` | não | number / string / null |  |  |
| `remote_data_notice` | não | string / null |  |  |
| `dispatcher_fallback` | não | string | default="local_direct"; enum=["local_direct", "hold"] |  |
| `dispatcher_down_seconds` | não | integer | default=120; minimum=30.0; maximum=3600.0 |  |
| `version` | não | integer / null |  |  |
| `current_password` | não | string / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### DELETE /admin/routing/{feature}

Remove a route (it drains back to today's path)

Autorização: **Administrador (somente JWT)**. Operation ID: `delete_route_admin_routing__feature__delete`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `feature` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 202 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/engines/status

Dispatcher, in-flight work and backlog

Autorização: **Administrador (JWT ou API key)**. Operation ID: `engines_status_admin_engines_status_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |

### GET /admin/engine-adapters

Engine adapters, their GPUs and limits

Autorização: **JWT**. Operation ID: `list_engine_adapters_admin_engine_adapters_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | array de object | Successful Response |

### GET /admin/engines

List engines

Autorização: **JWT**. Operation ID: `list_engines_admin_engines_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | array de object | Successful Response |

### GET /admin/engines/{engine_id}

One engine

Autorização: **JWT**. Operation ID: `get_engine_admin_engines__engine_id__get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/gpus

Physical GPUs: declared vs detected, VRAM budgeted and used

Autorização: **Administrador (JWT ou API key)**. Operation ID: `list_gpus_admin_gpus_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |

### PUT /admin/engines/{engine_id}/features/{feature}

Set how a feature runs on an engine

Autorização: **Administrador (somente JWT)**. Operation ID: `put_engine_feature_admin_engines__engine_id__features__feature__put`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |
| `feature` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [BindingUpdate](#model-bindingupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `gpu_type` | não | string / null |  |  |
| `gpu_ref` | não | string / null |  |  |
| `workers` | sim | integer | minimum=0.0; maximum=1000.0 |  |
| `executions_per_worker` | não | integer | default=1; minimum=1.0; maximum=64.0 |  |
| `cpu` | não | number / null |  |  |
| `vram_override_gb` | não | number / null |  |  |
| `version` | não | integer / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### DELETE /admin/engines/{engine_id}/features/{feature}

Stop running a feature on an engine

Autorização: **Administrador (somente JWT)**. Operation ID: `delete_engine_feature_admin_engines__engine_id__features__feature__delete`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |
| `feature` | path | sim | string |  |  |
| `version` | query | não | integer / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### PUT /admin/engines/{engine_id}/gpus

Declare the local engine's physical GPUs

Autorização: **Administrador (somente JWT)**. Operation ID: `put_engine_gpus_admin_engines__engine_id__gpus_put`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [GpusUpdate](#model-gpusupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `gpus` | sim | array de [LocalGpu](#model-localgpu) |  |  |
| `version` | não | integer / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engines/{engine_id}/test

Test an engine's credentials and deployment (no GPU)

Autorização: **Administrador (somente JWT)**. Operation ID: `test_engine_admin_engines__engine_id__test_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engines/{engine_id}/activate

Let the dispatcher place work on an engine

Autorização: **Administrador (somente JWT)**. Operation ID: `activate_engine_admin_engines__engine_id__activate_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Corpo obrigatório: não.

Content-Type: `application/json`. Esquema: [VersionBody](#model-versionbody) / null.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engines/{engine_id}/pause

Stop placing new work on an engine (work in flight finishes)

Autorização: **Administrador (somente JWT)**. Operation ID: `pause_engine_admin_engines__engine_id__pause_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Corpo obrigatório: não.

Content-Type: `application/json`. Esquema: [VersionBody](#model-versionbody) / null.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engines/{engine_id}/reset-health

Forget an engine's recorded failures

Autorização: **Administrador (somente JWT)**. Operation ID: `reset_engine_health_admin_engines__engine_id__reset_health_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### PUT /admin/engines/{engine_id}/budget

Set an engine's spending ceiling per period

Autorização: **Administrador (somente JWT)**. Operation ID: `put_engine_budget_admin_engines__engine_id__budget_put`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [BudgetUpdate](#model-budgetupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `limit_usd` | não | number / string / null |  |  |
| `min_remaining_usd` | não | number / string / null |  |  |
| `soft_pct` | não | integer / null |  |  |
| `period_tz` | não | string / null |  |  |
| `period_anchor_day` | não | integer / null |  |  |
| `version` | não | integer / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### PUT /admin/engines/{engine_id}/credentials

Replace an engine's credentials (sealed, write-only)

Autorização: **JWT**. Operation ID: `put_engine_credentials_admin_engines__engine_id__credentials_put`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [CredentialsUpdate](#model-credentialsupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `fields` | sim | object | additionalProperties={"type": "string"} |  |
| `current_password` | sim | string |  |  |
| `version` | não | integer / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### DELETE /admin/engines/{engine_id}/credentials

Forget an engine's credentials

Autorização: **JWT**. Operation ID: `delete_engine_credentials_admin_engines__engine_id__credentials_delete`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [CredentialsDelete](#model-credentialsdelete).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `current_password` | sim | string |  |  |
| `version` | não | integer / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/engines/{engine_id}/benchmarks

Benchmark results (gpu x E) and the learned speed per key

Autorização: **Administrador (JWT ou API key)**. Operation ID: `engine_benchmarks_admin_engines__engine_id__benchmarks_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |
| `feature` | query | não | string | default="transcription" |  |
| `limit` | query | não | integer | default=50 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engines/{engine_id}/reconcile

Read the provider's spend report for one engine now

Autorização: **Administrador (somente JWT)**. Operation ID: `reconcile_engine_admin_engines__engine_id__reconcile_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engines/test-all

Test every remote engine's credentials and deployment, in turn (no GPU)

Autorização: **Administrador (somente JWT)**. Operation ID: `test_all_engines_admin_engines_test_all_post`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |

## Admin - Engine control

### POST /admin/engines

Connection

Autorização: **Administrador (somente JWT)**. Operation ID: `connection_admin_engines_post`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [Connection](#model-connection).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `adapter_type` | sim | string |  |  |
| `display_name` | sim | string | minLength=1; maxLength=100 |  |
| `slug` | sim | string | pattern="^[a-z0-9][a-z0-9_-]{1,63}$" |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/engine-control-adapters

Adapters

Autorização: **JWT**. Operation ID: `adapters_admin_engine_control_adapters_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/engines/{engine_id}/capabilities

Caps

Autorização: **JWT**. Operation ID: `caps_admin_engines__engine_id__capabilities_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |
| `feature` | query | não | string / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/model-profiles

Model Profiles

Autorização: **JWT**. Operation ID: `model_profiles_admin_model_profiles_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/engines/{engine_id}/runtime-profile

Get Profile

Autorização: **JWT**. Operation ID: `get_profile_admin_engines__engine_id__runtime_profile_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |
| `feature` | query | não | string | default="transcription" |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### PUT /admin/engines/{engine_id}/runtime-profile

Put Profile

Autorização: **Administrador (somente JWT)**. Operation ID: `put_profile_admin_engines__engine_id__runtime_profile_put`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ProfileUpdate](#model-profileupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `feature` | sim | string |  |  |
| `version` | sim | integer | minimum=0.0 |  |
| `profile` | sim | [RuntimeSettings](#model-runtimesettings) |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/engines/{engine_id}/runtime-status

Status

Autorização: **JWT**. Operation ID: `status_admin_engines__engine_id__runtime_status_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engines/{engine_id}/operation-plans

Plan

Autorização: **JWT**. Operation ID: `plan_admin_engines__engine_id__operation_plans_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [PlanRequest](#model-planrequest).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `type` | sim | string |  |  |
| `feature` | não | string | default="transcription" |  |
| `profile_revision` | não | integer / null |  |  |
| `engine_version` | sim | integer | minimum=0.0 |  |
| `drain_timeout_seconds` | não | integer | default=900; minimum=1.0; maximum=1800.0 |  |
| `max_usd` | não | number / string | default="0" |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engines/{engine_id}/operations

Execute

Autorização: **JWT**. Operation ID: `execute_admin_engines__engine_id__operations_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | path | sim | string |  |  |
| `idempotency-key` | header | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [Execute](#model-execute).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `plan_id` | sim | string |  |  |
| `plan_hash` | sim | string |  |  |
| `confirm_paid_operation` | não | boolean | default=false |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 202 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/engine-operations

History

Autorização: **JWT**. Operation ID: `history_admin_engine_operations_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `engine_id` | query | não | string / null |  |  |
| `limit` | query | não | integer | default=50 |  |
| `before` | query | não | string / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/engine-operations/{operation_id}

Snapshot

Autorização: **JWT**. Operation ID: `snapshot_admin_engine_operations__operation_id__get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/engine-operations/{operation_id}/events

Events

Autorização: **JWT**. Operation ID: `events_admin_engine_operations__operation_id__events_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | sim | string |  |  |
| `after` | query | não | integer | default=0 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engine-operations/{operation_id}/cancel

Cancel

Autorização: **JWT**. Operation ID: `cancel_admin_engine_operations__operation_id__cancel_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/engine-operations/{operation_id}/stream

Stream

Autorização: **JWT**. Operation ID: `stream_admin_engine_operations__operation_id__stream_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | sim | string |  |  |
| `after` | query | não | integer | default=0 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engine-operations/{operation_id}/recover

Recover

Autorização: **JWT**. Operation ID: `recover_admin_engine_operations__operation_id__recover_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 202 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Admin - Execution profiles and access

### GET /admin/access/me

Me

Autorização: **JWT**. Operation ID: `me_admin_access_me_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/execution-profiles

Profiles

Autorização: **JWT**. Operation ID: `profiles_admin_execution_profiles_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /admin/execution-profiles

Create

Autorização: **JWT**. Operation ID: `create_admin_execution_profiles_post`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ProfileCreate](#model-profilecreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `settings` | sim | [RuntimeSettings](#model-runtimesettings) |  |  |
| `warm_for_seconds` | não | integer / null |  |  |
| `name` | sim | string | minLength=1; maxLength=100 |  |
| `description` | não | string | default=""; maxLength=1000 |  |
| `adapter_type` | sim | string |  |  |
| `feature` | sim | string |  |  |
| `environment` | não | string | default="development"; enum=["development", "staging", "production"] |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/execution-profiles/{id}

Detail

Autorização: **JWT**. Operation ID: `detail_admin_execution_profiles__id__get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### PUT /admin/execution-profiles/{id}

Metadata

Autorização: **JWT**. Operation ID: `metadata_admin_execution_profiles__id__put`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [MetadataUpdate](#model-metadataupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `name` | sim | string | minLength=1; maxLength=100 |  |
| `description` | não | string | default=""; maxLength=1000 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/execution-profiles/{id}/revisions

Revision

Autorização: **JWT**. Operation ID: `revision_admin_execution_profiles__id__revisions_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [RevisionCreate](#model-revisioncreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `settings` | sim | [RuntimeSettings](#model-runtimesettings) |  |  |
| `warm_for_seconds` | não | integer / null |  |  |
| `version` | sim | integer | minimum=0.0 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/execution-profiles/{id}/publish

Publish

Autorização: **JWT**. Operation ID: `publish_admin_execution_profiles__id__publish_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [Publish](#model-publish).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `revision_id` | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/execution-profiles/{id}/archive

Archive

Autorização: **JWT**. Operation ID: `archive_admin_execution_profiles__id__archive_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [Version](#model-version).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engines/{id}/runtime-profile/bind

Bind

Autorização: **JWT**. Operation ID: `bind_admin_engines__id__runtime_profile_bind_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [Bind](#model-bind).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `feature` | sim | string |  |  |
| `revision_id` | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engines/{id}/runtime-profile/import

Import Profile

Autorização: **JWT**. Operation ID: `import_profile_admin_engines__id__runtime_profile_import_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ProfileCreate](#model-profilecreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `settings` | sim | [RuntimeSettings](#model-runtimesettings) |  |  |
| `warm_for_seconds` | não | integer / null |  |  |
| `name` | sim | string | minLength=1; maxLength=100 |  |
| `description` | não | string | default=""; maxLength=1000 |  |
| `adapter_type` | sim | string |  |  |
| `feature` | sim | string |  |  |
| `environment` | não | string | default="development"; enum=["development", "staging", "production"] |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/access/policies

Policies

Autorização: **JWT**. Operation ID: `policies_admin_access_policies_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /admin/access/policies

Policy Create

Autorização: **JWT**. Operation ID: `policy_create_admin_access_policies_post`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [PolicyCreate](#model-policycreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | sim | string | minLength=1; maxLength=100 |  |
| `constraints` | sim | [Constraints](#model-constraints) |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/access/policies/{id}/revisions

Policy Revise

Autorização: **JWT**. Operation ID: `policy_revise_admin_access_policies__id__revisions_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [PolicyUpdate](#model-policyupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `constraints` | sim | [Constraints](#model-constraints) |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/access/roles

Roles

Autorização: **JWT**. Operation ID: `roles_admin_access_roles_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/access/subjects

Subjects

Autorização: **JWT**. Operation ID: `subjects_admin_access_subjects_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/access/grants

Grants

Autorização: **JWT**. Operation ID: `grants_admin_access_grants_get`.

**Depreciada**: mantida por compatibilidade; veja a rota que a substitui.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /admin/access/grants

Grant

Autorização: **JWT**. Operation ID: `grant_admin_access_grants_post`.

**Depreciada**: mantida por compatibilidade; veja a rota que a substitui.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [GrantCreate](#model-grantcreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `user_id` | sim | string |  |  |
| `role` | sim | string |  |  |
| `policy_revision_id` | sim | string |  |  |
| `permissions` | não | array de string / null |  |  |
| `expires_at` | sim | string (date-time) |  |  |
| `delegation` | não | [Delegation](#model-delegation) / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/access/grants/{id}/revoke

Revoke

Autorização: **JWT**. Operation ID: `revoke_admin_access_grants__id__revoke_post`.

**Depreciada**: mantida por compatibilidade; veja a rota que a substitui.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [Version](#model-version).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/access/engine-attributes

Attributes

Autorização: **JWT**. Operation ID: `attributes_admin_access_engine_attributes_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### PUT /admin/access/engine-attributes/{id}

Classify

Autorização: **JWT**. Operation ID: `classify_admin_access_engine_attributes__id__put`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [AttributesUpdate](#model-attributesupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `environment` | sim | string | enum=["development", "staging", "production"] |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/access/resources

Resources

Autorização: **JWT**. Operation ID: `resources_admin_access_resources_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### PUT /admin/access/resources

Qualify

Autorização: **JWT**. Operation ID: `qualify_admin_access_resources_put`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ScopeUpdate](#model-scopeupdate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `key` | sim | string | minLength=1; maxLength=200 |  |
| `version` | sim | integer | minimum=0.0 |  |
| `consumers` | sim | array de [Consumer](#model-consumer) | minItems=1; maxItems=100 |  |
| `qualified` | não | boolean | default=false |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/execution-profile-hosts

Hosts

Autorização: **JWT**. Operation ID: `hosts_admin_execution_profile_hosts_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/access/installation-principals

Principals

Autorização: **JWT**. Operation ID: `principals_admin_access_installation_principals_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /admin/access/installation-principals

Principal Create

Autorização: **JWT**. Operation ID: `principal_create_admin_access_installation_principals_post`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [PrincipalCreate](#model-principalcreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string | maxLength=36; pattern="^installation:[a-z0-9_-]{1,23}$" |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### PUT /admin/access/installation-principals/{id}

Principal State

Autorização: **JWT**. Operation ID: `principal_state_admin_access_installation_principals__id__put`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [PrincipalState](#model-principalstate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `active` | sim | boolean |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### PUT /admin/access/subjects/{id}/state

Subject State

Autorização: **JWT**. Operation ID: `subject_state_admin_access_subjects__id__state_put`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [SubjectState](#model-subjectstate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `expected_is_active` | sim | boolean |  |  |
| `expected_is_admin` | sim | boolean |  |  |
| `is_active` | sim | boolean |  |  |
| `is_admin` | sim | boolean |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## IAM

### GET /iam/permissions

The permission catalog and the managed roles

Autorização: **JWT ou API key**. Operation ID: `list_permissions_iam_permissions_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /iam/check

Which platform permissions the caller holds

Autorização: **JWT ou API key**. Operation ID: `check_permissions_iam_check_post`.

Answers for the caller only, as IAM_MODE decides it, and never audits (asking
is not exercising). Only platform/IAM permissions in this slice: a data or 0009
engine permission, or a name outside the catalog, is a 422.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: array de [PermissionCheck](#model-permissioncheck).

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | array de [PermissionCheckResult](#model-permissioncheckresult) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /admin/iam/bindings

Platform and engines bindings

Autorização: **Administrador (JWT ou API key)**. Operation ID: `list_bindings_admin_iam_bindings_get`.

Filtered per row: platform bindings for `iam.bindings.read` (as IAM_MODE
decides it); engines bindings the caller's 0009 delegation covers (bootstrap
sees them all), with `engine_access_enabled`. Newest first.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `include_inactive` | query | não | boolean | default=false |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/iam/bindings

Grant a platform or engines role

Autorização: **Administrador (somente JWT)**. Operation ID: `grant_binding_admin_iam_bindings_post`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [BindingCreate](#model-bindingcreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `subject_type` | não | string | default="user" |  |
| `subject_id` | sim | string |  |  |
| `role` | sim | string |  |  |
| `expires_at` | não | string / null |  |  |
| `permissions` | não | array de string / null |  |  |
| `condition_ref` | não | string / null |  |  |
| `delegation` | não | [Delegation](#model-delegation) / null |  |  |
| `parent_id` | não | string / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/iam/bindings/{binding_id}/revoke

Revoke a platform or engines binding

Autorização: **Administrador (somente JWT)**. Operation ID: `revoke_binding_admin_iam_bindings__binding_id__revoke_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `binding_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [BindingRevoke](#model-bindingrevoke).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Engine hosts

### POST /internal/engine-hosts/{host_id}/heartbeat

Host Heartbeat

Autorização: **X-Engine-Host-Token do host**. Operation ID: `host_heartbeat_internal_engine_hosts__host_id__heartbeat_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `host_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [HostHeartbeat](#model-hostheartbeat).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `inventory` | sim | object | additionalProperties=true |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /internal/engine-hosts/{host_id}/next

Host Next

Autorização: **X-Engine-Host-Token do host**. Operation ID: `host_next_internal_engine_hosts__host_id__next_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `host_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /internal/engine-hosts/{host_id}/operations/{op_id}/check

Host Check

Autorização: **X-Engine-Host-Token do host**. Operation ID: `host_check_internal_engine_hosts__host_id__operations__op_id__check_get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `host_id` | path | sim | string |  |  |
| `op_id` | path | sim | string |  |  |
| `generation` | query | sim | integer |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /internal/engine-hosts/{host_id}/operations/{op_id}/events

Host Event

Autorização: **X-Engine-Host-Token do host**. Operation ID: `host_event_internal_engine_hosts__host_id__operations__op_id__events_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `host_id` | path | sim | string |  |  |
| `op_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [HostEvent](#model-hostevent).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `generation` | sim | integer |  |  |
| `stage` | sim | string |  |  |
| `message` | sim | string | maxLength=8192 |  |
| `effect` | não | boolean | default=false |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /internal/engine-hosts/{host_id}/operations/{op_id}/result

Host Result

Autorização: **X-Engine-Host-Token do host**. Operation ID: `host_result_internal_engine_hosts__host_id__operations__op_id__result_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `host_id` | path | sim | string |  |  |
| `op_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [HostResult](#model-hostresult).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `generation` | sim | integer |  |  |
| `ok` | sim | boolean |  |  |
| `observed` | não | object | additionalProperties=true |  |
| `code` | não | string / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Projects

### GET /projects

Listar projetos com contagens

Autorização: **JWT ou API key**. Operation ID: `list_projects_projects_get`.

Os projetos do usuário, com contagens de jobs MAIN, os mais recentes primeiro
(`last_job_at` desc, depois nome). `?include=folders` traz as pastas de cada
projeto, com contagem.

As contagens vêm de um único `GROUP BY project_id, folder_id, status`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `include` | query | não | string / null |  | `folders` inclui as pastas de cada projeto |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [ProjectListResponse](#model-projectlistresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /projects/resolve

Um nome de projeto casa com um projeto existente?

Autorização: **JWT ou API key**. Operation ID: `resolve_project_name_projects_resolve_get`.

Diz, sem criar nada, se `name` é um projeto existente (pela regra de
normalização do backend: `reuniao` casa com "Reunião") ou se seria criado.

`{"valid": true, "match": {"id", "name"}}`, `{"valid": true, "match": null}`
ou `{"valid": false, "error": "..."}`. Sempre 200.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `name` | query | sim | string |  | O texto digitado |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [NameResolveResponse](#model-nameresolveresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /projects/{project_id}/folders/resolve

Um nome de pasta casa com uma pasta existente do projeto?

Autorização: **JWT ou API key**. Operation ID: `resolve_folder_name_projects__project_id__folders_resolve_get`.

Igual a `GET /projects/resolve`, para uma pasta do projeto. Projeto alheio: 404.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | sim | string |  |  |
| `name` | query | sim | string |  | O texto digitado |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [NameResolveResponse](#model-nameresolveresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Live transcription

### POST /transcribe/live/sessions

Create Session

Autorização: **JWT ou API key**. Operation ID: `create_session_transcribe_live_sessions_post`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [CreateSession](#model-createsession).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `project` | não | string / null |  |  |
| `project_id` | não | string / null |  |  |
| `folder` | não | string / null |  |  |
| `folder_id` | não | string / null |  |  |
| `name` | não | string | default="Transcrição ao vivo"; minLength=1; maxLength=1000 |  |
| `tags` | não | array de string |  |  |
| `language` | não | string | default="pt"; const="pt" |  |
| `audio` | não | [AudioFormat](#model-audioformat) |  |  |
| `protocol` | não | integer | default=1; enum=[1, 2] |  |
| `diarize` | não | boolean | default=false |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /transcribe/live/sessions/{job_id}

Session Status

Autorização: **JWT ou API key**. Operation ID: `session_status_transcribe_live_sessions__job_id__get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### DELETE /transcribe/live/sessions/{job_id}

Cancel Session

Autorização: **JWT ou API key**. Operation ID: `cancel_session_transcribe_live_sessions__job_id__delete`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Conversion

### POST /upload

Upload e converter arquivo

Autorização: **JWT ou API key**. Operation ID: `upload_and_convert_upload_post`.

Upload direto de arquivo para conversão

Este endpoint é dedicado exclusivamente para upload de arquivos.
Use os outros endpoints para converter de URL, Google Drive ou Dropbox.

## Parâmetros:
- `file`: Arquivo para upload
- `name`: Nome de identificação opcional (se não fornecido, usa o nome do arquivo)
- `docling_preset`: Quality/speed preset (apenas para PDFs):
  - **fast** (padrão): Conversão rápida, apenas texto (~35s/MB)
    - OCR: Desligado | Images: Desligadas | Tables: Ligadas
  - **balanced**: Velocidade moderada, extrai imagens (~70-105s/MB)
    - OCR: Desligado | Images: Ligadas | Tables: Ligadas
  - **quality**: Máxima qualidade, inclui OCR para documentos escaneados (~350s/MB)
    - OCR: Ligado | Images: Ligadas | Tables: Ligadas
- `purge_source`: Se `true`, apaga os arquivos de origem (o arquivo enviado e os
  PDFs por página) quando o job termina — `completed`, ou `failed`/`partial` depois
  das tentativas automáticas — e fica só o resultado. Veja "Arquivos de origem".

## Arquivos de origem (`purge_source`)
- O que é apagado: o arquivo enviado (MinIO `uploads/...` e cópia local) e, num
  PDF de várias páginas, os PDFs por página (`/jobs/{job_id}/pages/{n}/pdf`
  passa a responder 410 `SOURCE_PURGED`). O markdown (inteiro e por página) fica.
- Quando: ao terminar `completed`, ou `failed`/`partial` depois de esgotados os
  retries automáticos; nunca enquanto houver retry ou página na fila. Depois
  disso o retry manual de página responde 409 `SOURCE_NOT_AVAILABLE`.
- `GET /jobs/{job_id}` informa `source_available`, `source_deleted_at` e
  `source_deletable`. Para apagar depois: `DELETE /jobs/{job_id}/source`.
- Arquivo repetido no mesmo projeto: com `purge_source=true` a resposta traz o
  job existente com `duplicate: true` e ele passa a apagar a origem (na hora, se
  já terminou; `source_available` diz o resultado). Com `false`, um job existente
  cuja origem foi (ou será) apagada não é reaproveitado: um job novo é criado.

```bash
curl -X POST http://localhost:8000/upload \
  -H "X-API-Key: your-api-key" \
  -F "file=@contrato.pdf" \
  -F "project=Cliente X" \
  -F "purge_source=true"
```

## Formatos suportados
PDF, DOCX, DOC, HTML, PPTX, XLSX, RTF, ODT

## Retorno
Retorna imediatamente um `job_id` para consultar o progresso via `/jobs/{job_id}`,
e onde o job ficou (`project`, `folder`)

## Exemplos:
```bash
# Fast mode (default)
curl -X POST http://localhost:8000/upload       -H "X-API-Key: your-api-key"       -F "file=@documento.pdf"       -F "project=Cliente X"

# Quality mode with OCR
curl -X POST http://localhost:8000/upload       -H "X-API-Key: your-api-key"       -F "file=@documento_escaneado.pdf"       -F "docling_preset=quality"
```

Corpo obrigatório: sim.

Content-Type: `multipart/form-data`. Esquema: [Body_upload_and_convert_upload_post](#model-body_upload_and_convert_upload_post).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  | Arquivo para conversão (PDF, DOCX, HTML, etc.) |
| `name` | não | string / null |  | Nome de identificação (opcional, padrão: nome do arquivo) |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `docling_preset` | não | string / null | default="fast" | Quality/speed preset for PDF conversion: 'fast' (~35s/MB, text-only), 'balanced' (~70-105s/MB, with images), 'quality' (~350s/MB, with OCR) |
| `diarize` | não | boolean / null |  | Identificar falantes; omitido usa o padrão do provider |
| `min_speakers` | não | integer / null |  |  |
| `max_speakers` | não | integer / null |  |  |
| `language` | não | string / null |  | Idioma para áudio/vídeo; omitido detecta automaticamente |
| `include_word_timestamps` | não | boolean / null |  |  |
| `purge_source` | não | boolean | default=false | Se true, apaga os arquivos de origem do job — o arquivo enviado (MinIO e cópia local) e, num PDF dividido, os PDFs por página — quando o job termina: `completed`, ou `failed`/`partial` depois de esgotadas as tentativas automáticas (nunca enquanto houver retry ou página na fila). O resultado (markdown, markdown por página) fica. Depois disso o retry manual de página não é mais possível. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Arquivo repetido no mesmo projeto: com true o job existente é devolvido (`duplicate: true`) e passa a apagar a origem (na hora, se já terminou); com false um job existente cuja origem foi (ou será) apagada não é reaproveitado e um job novo é criado. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [JobCreatedResponse](#model-jobcreatedresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /transcribe

Transcrever áudio ou vídeo (STT, legendas VTT/SRT)

Autorização: **JWT ou API key**. Operation ID: `transcribe_audio_transcribe_post`.

Transcrever áudio ou vídeo para texto usando Whisper (STT)

Aceita áudio ou vídeo (só a faixa de áudio do vídeo é transcrita).
O job entra na fila própria de transcrição (`ingestify-audio`), consumida por
workers dedicados, e não disputa vaga com a conversão de documentos.

## Autenticação
Obrigatória: header `X-API-Key: <chave>` ou `Authorization: Bearer <token JWT>`.
Sem ele a resposta é 401.

Todos os formatos são gerados: Markdown, legendas WebVTT e SRT, texto puro e
JSON com segmentos. Escolha o formato em `GET /jobs/{job_id}/result?format=vtt`
(ou defina o padrão com `output_format`).

## Parâmetros:
- `file`: Arquivo de áudio ou vídeo para transcrição
- `name`: Nome de identificação opcional
- `tags`: Tags do job, separadas por vírgula (ex: `focus,aula`)
- `language`: Código de idioma ISO 639-1 (ex: 'en', 'pt', 'es'). Auto-detecta se não fornecido
- `include_timestamps`: Adicionar marcadores de tempo [MM:SS] na transcrição
- `include_word_timestamps`: Adicionar timestamps em cada palavra (mais detalhado)
- `output_format`: Formato padrão do resultado (`markdown`, `vtt`, `srt`, `txt`, `json`)
- `purge_source`: Se `true`, apaga o arquivo enviado (disco e MinIO) quando o job
  termina (com sucesso, ou com falha depois das tentativas automáticas); ficam só
  as transcrições. `GET /jobs/{job_id}` informa `source_deleted_at`. `DELETE /jobs/{job_id}` também
  apaga o arquivo de origem e as transcrições

## Projeto
Todo job pertence a um projeto: envie `project` (nome; criado se não existir) ou
`project_id`, e opcionalmente `folder`/`folder_id`. Uma API key vinculada a um
projeto dispensa o campo. Sem projeto: 422.

## Arquivo repetido
Reenviar um arquivo idêntico (mesmo SHA-256) que já tem job **não falho** no mesmo
projeto devolve esse job em vez de criar outro: as tags novas são somadas às dele e o
`output_format` enviado passa a ser o padrão do resultado. Se o job anterior
falhou, o reenvio cria um job novo; é assim que se tenta de novo.

## Formatos suportados
- Áudio: MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM, WMA, AAC
- Vídeo: MP4, M4V, MKV, MOV, AVI, WEBM, WMV, FLV, MPEG, TS, 3GP

## Limite de tamanho
- Áudio: até 50MB (MAX_AUDIO_FILE_SIZE_MB)
- Vídeo: até 500MB (MAX_VIDEO_FILE_SIZE_MB)

## Tempo limite
Definido pelo worker de transcrição (`TRANSCRIPTION_TIMEOUT_SECONDS`, padrão 3h),
independente do `CONVERSION_TIMEOUT_SECONDS` dos documentos. Um job que estoura o
tempo falha sem novas tentativas automáticas.

## Retorno
Retorna imediatamente um `job_id` para consultar o progresso via `/jobs/{job_id}`

## Erros
- 401: sem autenticação
- 413: arquivo acima do limite
- 422: formato não suportado, `output_format` inválido ou `tags` inválidas
- 503: transcrição desabilitada ou workers indisponíveis

## Exemplos:
```bash
curl -X POST http://localhost:8080/transcribe \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "file=@meeting.mp3" \
  -F "project=Reuniões" \
  -F "language=pt" \
  -F "include_timestamps=true"
```

Vídeo com legenda SRT como padrão, tags e descarte do arquivo ao terminar:
```bash
curl -X POST http://localhost:8080/transcribe \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@aula.mp4" \
  -F "language=pt" \
  -F "output_format=srt" \
  -F "tags=focus,aula" \
  -F "purge_source=true"
```

## Resultado
Consulte o status em `/jobs/{job_id}` até `completed` e busque o resultado:
- `GET /jobs/{job_id}/result`: JSON com markdown e metadados (idioma, duração, device)
- `GET /jobs/{job_id}/result?format=vtt`: legenda WebVTT (`text/vtt`)
- `?format=srt`, `?format=txt`, `?format=json`: SRT, texto puro, segmentos

Corpo obrigatório: sim.

Content-Type: `multipart/form-data`. Esquema: [Body_transcribe_audio_transcribe_post](#model-body_transcribe_audio_transcribe_post).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  | Arquivo de áudio (MP3, WAV, M4A, FLAC, OGG...) ou vídeo (MP4, MKV, MOV, WEBM, AVI...) |
| `name` | não | string / null |  | Nome de identificação (opcional, padrão: nome do arquivo) |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `language` | não | string / null |  | Código do idioma (ex: 'en', 'pt'). Auto-detectar se não fornecido |
| `include_timestamps` | não | boolean | default=true | Incluir marcadores de tempo na transcrição |
| `include_word_timestamps` | não | boolean | default=false | Incluir timestamps em nível de palavra (mais detalhado) |
| `output_format` | não | string | default="markdown" | Formato padrão do resultado em /jobs/{job_id}/result: markdown, vtt, srt, txt ou json |
| `purge_source` | não | boolean | default=false | Apagar o áudio/vídeo enviado quando a transcrição terminar (com sucesso, ou com falha depois das tentativas automáticas); guarda só o texto |
| `diarize` | não | boolean / null |  | Identificar falantes; omitido usa o padrão do provider |
| `min_speakers` | não | integer / null |  |  |
| `max_speakers` | não | integer / null |  |  |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [JobCreatedResponse](#model-jobcreatedresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /convert

Convert Document

Autorização: **JWT ou API key**. Operation ID: `convert_document_convert_post`.

Conversão de documentos para Markdown

## Opções de uso:

### 1. Upload de arquivo (multipart/form-data)
- `source_type`: "file"
- `file`: Selecione o arquivo para upload
- `source`: Deixe vazio

### 2. URL pública
- `source_type`: "url"
- `source`: "https://example.com/document.pdf"
- `file`: Deixe vazio

### 3. Google Drive
- `source_type`: "gdrive"
- `source`: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms" (file ID)
- header `X-Source-Token`: "ya29.a0AfH6SMB..." (OAuth2 token do Google)
- `file`: Deixe vazio

### 4. Dropbox
- `source_type`: "dropbox"
- `source`: "/documents/report.pdf" (path do arquivo)
- header `X-Source-Token`: "sl.B1a2c3..." (access token do Dropbox)

O header `Authorization` autentica no Ingestify e nunca é repassado ao
provedor nem colocado na mensagem do Celery (S-01).
- `file`: Deixe vazio

## Projeto (obrigatório) e pasta
`project` (nome; criado se não existir) ou `project_id`, e opcionalmente
`folder`/`folder_id`. Uma API key vinculada a um projeto dispensa o campo
(só sem JWT). Sem projeto: 422. Um arquivo repetido só é reaproveitado
dentro do mesmo projeto.

## Arquivos de origem (`purge_source`)
Com `purge_source=true` os arquivos de origem (o enviado, ou o baixado da URL,
e os PDFs por página) são apagados quando o job termina: `completed`, ou
`failed`/`partial` depois das tentativas automáticas. O resultado fica. Mesmas
regras de `/upload` (inclusive para arquivo repetido).
Para apagar depois: `DELETE /jobs/{job_id}/source`

## Formatos suportados
PDF, DOCX, DOC, HTML, PPTX, XLSX, RTF, ODT

## Retorno
Retorna imediatamente um `job_id` para consultar o progresso via `/jobs/{job_id}`

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `authorization` | header | não | string / null |  | Autenticação do Ingestify ('Bearer {jwt}'). Nunca é repassada a provedores externos. |
| `X-Source-Token` | header | não | string / null |  | Token OAuth/acesso do provedor (obrigatório para gdrive e dropbox). Não vai na mensagem do Celery: o worker o lê de uma chave Redis com TTL e a apaga após o download. |

Corpo obrigatório: sim.

Content-Type: `multipart/form-data`. Esquema: [Body_convert_document_convert_post](#model-body_convert_document_convert_post).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `source_type` | sim | string |  | Tipo de fonte: 'file' (upload), 'url' (URL pública), 'gdrive' (Google Drive), 'dropbox' (Dropbox) |
| `source` | não | string / null |  | URL, file_id (Google Drive) ou path (Dropbox). Deixe vazio para upload de arquivo |
| `file` | não | string (binary) / null |  | Arquivo para upload direto (use quando source_type='file') |
| `name` | não | string / null |  | Nome de identificação opcional (padrão: nome do arquivo ou URL) |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `diarize` | não | boolean / null |  | Identificar falantes; omitido usa o padrão do provider |
| `min_speakers` | não | integer / null |  |  |
| `max_speakers` | não | integer / null |  |  |
| `language` | não | string / null |  | Idioma para áudio/vídeo; omitido detecta automaticamente |
| `include_word_timestamps` | não | boolean / null |  |  |
| `purge_source` | não | boolean | default=false | Se true, apaga os arquivos de origem do job — o arquivo enviado (MinIO e cópia local) e, num PDF dividido, os PDFs por página — quando o job termina: `completed`, ou `failed`/`partial` depois de esgotadas as tentativas automáticas (nunca enquanto houver retry ou página na fila). O resultado (markdown, markdown por página) fica. Depois disso o retry manual de página não é mais possível. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Arquivo repetido no mesmo projeto: com true o job existente é devolvido (`duplicate: true`) e passa a apagar a origem (na hora, se já terminou); com false um job existente cuja origem foi (ou será) apagada não é reaproveitado e um job novo é criado. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [JobCreatedResponse](#model-jobcreatedresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /jobs/{job_id}

Get Job Status

Autorização: **JWT ou API key**. Operation ID: `get_job_status_jobs__job_id__get`.

Consultar status de qualquer tipo de job (main, split, page, merge)

## Pagination for pages list:
- `page_limit`: Maximum number of pages to return (default: all pages)
- `page_offset`: Number of pages to skip (default: 0)

Example: GET /jobs/{job_id}?page_limit=50&page_offset=0

## Permissões:
- Apenas o dono do job (verificado no MySQL) pode consultá-lo.
  Jobs de outros usuários retornam 404.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `page_limit` | query | não | integer / null |  |  |
| `page_offset` | query | não | integer | default=0 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [JobStatusResponse](#model-jobstatusresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### DELETE /jobs/{job_id}

Deletar job

Autorização: **JWT ou API key**. Operation ID: `delete_job_jobs__job_id__delete`.

Deletar job e todos os seus dados associados

Remove completamente um job do sistema, incluindo:
- Metadados do MySQL (job e pages)
- Conteúdo do Elasticsearch (markdown)
- Status temporário do Redis
- O arquivo original (documento, áudio ou vídeo) no MinIO e as cópias locais
- Para transcrições: as transcrições guardadas no MinIO

**Atenção:** Esta operação é irreversível!

## Para jobs MAIN com páginas:
- Deleta o job principal
- Deleta todos os jobs filhos (split, pages, merge)
- Deleta todos os registros de páginas
- Remove todo o conteúdo markdown

## Permissões:
- Apenas o dono do job (verificado no MySQL) pode deletá-lo

## Retorno:
- 200: Job deletado com sucesso
- 404: Job não encontrado (também retornado quando o job pertence a outro
  usuário, para não expor a existência do recurso)

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### DELETE /jobs/{job_id}/source

Apagar o arquivo original do job

Autorização: **JWT ou API key**. Operation ID: `delete_job_source_jobs__job_id__source_delete`.

Apaga os arquivos de origem de um job — o arquivo enviado (documento, áudio
ou vídeo) e os PDFs por página de um PDF dividido — mantendo o job e o
resultado (markdown, markdown por página, transcrições).

Remove os objetos no MinIO (`uploads/...` ou `audio/...`, e `pages/{job_id}/`)
e as cópias locais, e grava quando isso aconteceu. Depois disso
`GET /jobs/{job_id}` responde `source_available: false` e `source_deleted_at`,
`GET /jobs/{job_id}/pages/{n}/pdf` responde 410 `SOURCE_PURGED` e o retry de
página responde 409 `SOURCE_NOT_AVAILABLE`.

Job de imagem (`/images/*`): apaga toda cópia guardada da imagem original — a
cópia local de processamento, o original e a prévia normalizada da análise
completa/facial (`images/{job_id}/source` e `images/{job_id}/preview/` no bucket
de resultados) e a imagem embutida no resultado guardado (`image.image_base64`
passa a null); o resultado da inferência fica.

Para apagar automaticamente quando o job terminar, envie `purge_source=true` em
`/upload`, `/convert`, `/transcribe` ou em qualquer rota `/images/*`.

## Retorno
- 200: `{"job_id": "...", "source_deleted": true, "source_deleted_at": "..."}`
- 404: job inexistente, de outro usuário, ou sem arquivos de origem
- 409: `{"code": "JOB_STILL_PROCESSING"}`: o job ainda está na fila ou em processamento,
  espera um retry automático, ou tem página na fila/em processamento (retry de página)
- 503: `{"code": "SOURCE_DELETE_FAILED"}`: o armazenamento recusou; o que não foi
  apagado continua referenciado (chamar de novo termina)

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [SourceDeletedResponse](#model-sourcedeletedresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /jobs/{job_id}/result

Get Job Result

Autorização: **JWT ou API key**. Operation ID: `get_job_result_jobs__job_id__result_get`.

Recuperar resultado de qualquer tipo de job (main ou page individual)

## Permissões:
- Apenas o dono do job (verificado no MySQL) pode acessar o resultado.
  Jobs de outros usuários retornam 404.

Para jobs de transcrição (/transcribe), `?format=vtt|srt|txt|json` retorna o
arquivo no formato pedido (ex.: legenda WebVTT com `Content-Type: text/vtt`).

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `format` | query | não | string / null |  | Para transcrições: markdown (JSON padrão), vtt, srt, txt ou json. Sem este parâmetro vale o output_format escolhido no /transcribe. |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [JobResultResponse](#model-jobresultresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |
| 202 | — | objeto livre | Análise composta em andamento; consulte poll_url/result_url. |

### GET /jobs/{job_id}/transcript/partial

Get Partial Transcript

Autorização: **JWT ou API key**. Operation ID: `get_partial_transcript_jobs__job_id__transcript_partial_get`.

Texto de uma transcrição enquanto ela acontece

Retorna os segmentos já transcritos a partir de `since`, e em `next` o valor de
`since` para a próxima consulta - assim cada consulta traz só o texto novo.
Só o provider faster-whisper transcreve em segmentos; com os providers da OpenAI
a lista fica vazia até o fim. Quando o job termina a lista também fica vazia:
o texto completo passa a estar em `GET /jobs/{job_id}/result`.

## Permissões:
- Apenas o dono do job (verificado no MySQL) pode consultá-lo.
  Jobs de outros usuários retornam 404.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `since` | query | não | integer | default=0; minimum=0 | Índice do primeiro segmento a retornar (o `next` da consulta anterior) |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [PartialTranscriptResponse](#model-partialtranscriptresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /jobs/{job_id}/pages

Get Job Pages

Autorização: **JWT ou API key**. Operation ID: `get_job_pages_jobs__job_id__pages_get`.

Obter progresso detalhado por página com job_id de cada página (para PDFs)

## Permissões:
- Apenas o dono do job (verificado no MySQL) pode consultar as páginas.
  Jobs de outros usuários retornam 404.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [JobPagesResponse](#model-jobpagesresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /jobs/{job_id}/pages/{page_number}/status

Status de página específica por número

Autorização: **JWT ou API key**. Operation ID: `get_page_status_by_number_jobs__job_id__pages__page_number__status_get`.

Consulta o status de uma página específica usando o número da página

## Parâmetros:
- `job_id`: ID do job principal
- `page_number`: Número da página (1, 2, 3, ...)

## Retorno:
Status da página específica

## Exemplo:
```
GET /jobs/550e8400-e29b-41d4-a716-446655440000/pages/5/status
```

Retorna o status da página 5 do job especificado.

## Permissões:
- Apenas o dono do job (verificado no MySQL) pode consultar a página.
  Jobs de outros usuários retornam 404.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `page_number` | path | sim | integer |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /jobs/{job_id}/pages/{page_number}/result

Resultado de página específica por número

Autorização: **JWT ou API key**. Operation ID: `get_page_result_by_number_jobs__job_id__pages__page_number__result_get`.

Recupera o resultado (markdown) de uma página específica usando o número da página

## Parâmetros:
- `job_id`: ID do job principal
- `page_number`: Número da página (1, 2, 3, ...)

## Retorno:
Markdown da página específica

## Exemplo:
```
GET /jobs/550e8400-e29b-41d4-a716-446655440000/pages/5/result
```

Retorna o markdown da página 5 do job especificado.

## Vantagem:
Não precisa conhecer o `page_job_id` - basta usar o job principal + número da página!

## Permissões:
- Apenas o dono do job (verificado no MySQL) pode acessar o resultado.
  Jobs de outros usuários retornam 404.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `page_number` | path | sim | integer |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /jobs

Listar jobs do usuário

Autorização: **JWT ou API key**. Operation ID: `list_jobs_jobs_get`.

Lista os jobs do usuário autenticado, do mais recente para o mais antigo.

A lista vem do MySQL (fonte da verdade); o Redis só complementa o status e
o progresso ao vivo dos jobs em andamento.

## Parâmetros:
- `limit`: Máximo de jobs (padrão: 50, máximo: 100)
- `offset`: Quantos pular (paginação)
- `status`: queued, processing, completed, failed ou cancelled
- `tag`: Filtra por tag; `?tag=a&tag=b` exige as duas
- `q`: Texto no nome do job ou do arquivo
- `kind`: `document`, `transcription` ou `image`
- `project_id`: só jobs do projeto (projeto alheio: 404)
- `folder_id`: só jobs da pasta (pasta alheia: 404), ou `root` com `project_id`
  para os jobs sem pasta. Sem `project_id`, o projeto é o da pasta.
- `job_type`: `main` (padrão) ou `all`

## Retorno:
`{total, limit, offset, jobs, counts}`. `total` é o total filtrado antes da
paginação; `counts` traz quantos jobs há em cada status com os demais
filtros aplicados (para montar os filtros da interface). Cada job traz
`project: {id, name}` e `folder: {id, name} | null`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `limit` | query | não | integer | default=50 |  |
| `offset` | query | não | integer | default=0 |  |
| `status` | query | não | string / null |  |  |
| `job_type` | query | não | string | default="main" |  |
| `tag` | query | não | array de string / null |  | Só jobs com esta tag. Repita para exigir várias (E). |
| `q` | query | não | string / null |  | Busca no nome e no nome do arquivo (não no conteúdo; para isso use /search). |
| `kind` | query | não | string / null |  | document, transcription ou image |
| `project_id` | query | não | string / null |  | Só jobs deste projeto. |
| `folder_id` | query | não | string / null |  | Só jobs desta pasta, ou `root` para os jobs do projeto que não estão em pasta nenhuma (`root` exige `project_id`). |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /search

Buscar jobs por conteúdo

Autorização: **JWT ou API key**. Operation ID: `search_jobs_search_get`.

Buscar jobs por conteúdo do markdown usando Elasticsearch

## Parâmetros:
- `query`: Texto a buscar no conteúdo dos documentos
- `limit`: Número máximo de resultados (padrão: 10, máximo: 100)

## Retorno:
Lista de jobs que contêm o texto buscado no conteúdo convertido

## Exemplos:
- `/search?query=relatório financeiro` - Busca jobs contendo "relatório financeiro"
- `/search?query=invoice&limit=20` - Busca jobs contendo "invoice", até 20 resultados

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `query` | query | sim | string |  |  |
| `limit` | query | não | integer | default=10 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /jobs/{job_id}/pages/{page_number}/retry

Retry de página que falhou

Autorização: **JWT ou API key**. Operation ID: `retry_failed_page_jobs__job_id__pages__page_number__retry_post`.

Tenta reprocessar uma página que falhou

## Parâmetros:
- `job_id`: ID do job principal
- `page_number`: Número da página que falhou

## Retorno:
Novo job_id da página em retry

## Exemplo:
```
POST /jobs/550e8400-e29b-41d4-a716-446655440000/pages/5/retry
```

Reprocessa a página 5 do job especificado.

## Permissões:
- Apenas o dono do job (verificado no MySQL) pode reprocessar a página.
  Jobs de outros usuários retornam 404.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `page_number` | path | sim | integer |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /jobs/{job_id}/pages/{page_number}/pdf

URL temporária do PDF de uma página

Autorização: **JWT ou API key**. Operation ID: `get_page_pdf_jobs__job_id__pages__page_number__pdf_get`.

Devolve uma **URL pré-assinada de curta duração** para o PDF de uma página.

## Autenticação
Obrigatória. Só o dono do job (verificado no MySQL) recebe a URL; jobs de
outros usuários retornam 404, igual aos demais endpoints de job.

Este endpoint já foi público e redirecionava (307) para uma URL pública do
MinIO — quem tivesse um UUID de job lia o PDF de qualquer usuário. Agora o
bucket é privado e o acesso é sempre por URL assinada com TTL curto.

## Parâmetros:
- `job_id`: ID do job principal
- `page_number`: Número da página (1-indexed)

## Retorno (JSON, não é mais um redirect):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "page_number": 5,
  "url": "http://127.0.0.1:9000/ingestify-pages/pages/<job_id>/page_0005.pdf?X-Amz-...",
  "expires_in": 900,
  "expires_at": "2026-08-26T12:15:00+00:00"
}
```

- `url`: URL assinada, para ser buscada **diretamente** pelo navegador. Não
  aceita header `Authorization` (e não precisa dele).
- `expires_in`: validade em segundos a partir de agora.
- `expires_at`: instante de expiração em UTC (ISO-8601). O cliente deve
  pedir uma URL nova depois disso em vez de reutilizar a antiga.

Um redirect não serviria: o header `Authorization` do chamador não sobrevive
ao salto para o MinIO, e o cliente precisa saber quando a URL expira.

## Atenção
A query string faz parte da assinatura — acrescentar qualquer parâmetro
(`?t=<timestamp>`, por exemplo) invalida a URL e gera 403 no MinIO.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `page_number` | path | sim | integer |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /health

Health Check

Autorização: **Público**. Operation ID: `health_check_health_get`.

Health check endpoint

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [HealthCheckResponse](#model-healthcheckresponse) | Successful Response |

## General

### GET /

Root

Autorização: **Público**. Operation ID: `root__get`.

Root endpoint

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

## WebSocket

### WS /transcribe/live/sessions/{job_id}/stream

Ticket descartável obtido em POST /transcribe/live/sessions; primeiro frame JSON {"type":"authenticate","protocol":1,"ticket":"..."}. A versão deve corresponder à sessão; não envie credenciais na URL.

Protocolos 1 e 2 usam PCM s16le, 16 kHz, mono e cabeçalho little-endian seq:uint32/offset_samples:uint64. Protocolo 2 exige diarize=true e os gates de qualificação de diarização; consulte o guia de live. Controle finish/cancel em JSON.

Protocolo completo: [captura ao vivo](features/live-transcription.md).

## Modelos

<a id="model-apikeycreate"></a>

### APIKeyCreate

Schema for creating API key

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | sim | string | minLength=1; maxLength=100 |  |
| `expires_in_days` | não | integer / null |  |  |
| `project` | não | string / null |  | Projeto vinculado, por nome (criado se não existir). Exclusivo com project_id. |
| `project_id` | não | string / null |  | Projeto vinculado, por ID. Exclusivo com project. |

Esquema JSON completo:

```json
{
  "properties": {
    "name": {
      "type": "string",
      "maxLength": 100,
      "minLength": 1,
      "title": "Name",
      "example": "Production Server"
    },
    "expires_in_days": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 365.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Expires In Days",
      "example": 30
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Projeto vinculado, por nome (criado se não existir). Exclusivo com project_id."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "Projeto vinculado, por ID. Exclusivo com project."
    }
  },
  "type": "object",
  "required": [
    "name"
  ],
  "title": "APIKeyCreate",
  "description": "Schema for creating API key"
}
```

<a id="model-apikeyinfo"></a>

### APIKeyInfo

Schema for listing API keys (without the actual key)

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string (uuid) |  |  |
| `name` | sim | string |  |  |
| `last_used_at` | não | string (date-time) / null |  |  |
| `expires_at` | não | string (date-time) / null |  |  |
| `is_active` | sim | boolean |  |  |
| `created_at` | sim | string (date-time) |  |  |
| `project` | não | [ProjectRef](#model-projectref) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "last_used_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Last Used At"
    },
    "expires_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Expires At"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "project": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/ProjectRef"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "is_active",
    "created_at"
  ],
  "title": "APIKeyInfo",
  "description": "Schema for listing API keys (without the actual key)"
}
```

<a id="model-apikeyprojectupdate"></a>

### APIKeyProjectUpdate

PATCH /api-keys/{key_id}: bind the key to a project, or unbind it with null.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `project_id` | sim | string / null |  | Projeto para onde vão os uploads desta key que não dizem o projeto; null desvincula. |

Esquema JSON completo:

```json
{
  "properties": {
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "Projeto para onde vão os uploads desta key que não dizem o projeto; null desvincula."
    }
  },
  "type": "object",
  "required": [
    "project_id"
  ],
  "title": "APIKeyProjectUpdate",
  "description": "PATCH /api-keys/{key_id}: bind the key to a project, or unbind it with null."
}
```

<a id="model-apikeyresponse"></a>

### APIKeyResponse

Schema for API key response (after creation)

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string (uuid) |  |  |
| `name` | sim | string |  |  |
| `api_key` | sim | string |  |  |
| `expires_at` | não | string (date-time) / null |  |  |
| `created_at` | sim | string (date-time) |  |  |
| `project` | não | [ProjectRef](#model-projectref) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "api_key": {
      "type": "string",
      "title": "Api Key"
    },
    "expires_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Expires At"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "project": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/ProjectRef"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "api_key",
    "created_at"
  ],
  "title": "APIKeyResponse",
  "description": "Schema for API key response (after creation)"
}
```

<a id="model-alignmentmetadata"></a>

### AlignmentMetadata

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `status` | sim | string | enum=["completed", "unavailable"] |  |
| `model` | não | string / null |  |  |
| `revision` | não | string / null |  |  |
| `device` | não | string / null |  |  |
| `reason` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "status": {
      "type": "string",
      "enum": [
        "completed",
        "unavailable"
      ],
      "title": "Status"
    },
    "model": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Model"
    },
    "revision": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Revision"
    },
    "device": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Device"
    },
    "reason": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason"
    }
  },
  "type": "object",
  "required": [
    "status"
  ],
  "title": "AlignmentMetadata"
}
```

<a id="model-attributesupdate"></a>

### AttributesUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `environment` | sim | string | enum=["development", "staging", "production"] |  |

Esquema JSON completo:

```json
{
  "properties": {
    "version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Version"
    },
    "environment": {
      "type": "string",
      "enum": [
        "development",
        "staging",
        "production"
      ],
      "title": "Environment"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "version",
    "environment"
  ],
  "title": "AttributesUpdate"
}
```

<a id="model-audioformat"></a>

### AudioFormat

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `encoding` | não | string | default="pcm_s16le"; const="pcm_s16le" |  |
| `sample_rate` | não | integer | default=16000; const=16000 |  |
| `channels` | não | integer | default=1; const=1 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "encoding": {
      "type": "string",
      "const": "pcm_s16le",
      "title": "Encoding",
      "default": "pcm_s16le"
    },
    "sample_rate": {
      "type": "integer",
      "const": 16000,
      "title": "Sample Rate",
      "default": 16000
    },
    "channels": {
      "type": "integer",
      "const": 1,
      "title": "Channels",
      "default": 1
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "AudioFormat"
}
```

<a id="model-bind"></a>

### Bind

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `feature` | sim | string |  |  |
| `revision_id` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Version"
    },
    "feature": {
      "type": "string",
      "title": "Feature"
    },
    "revision_id": {
      "type": "string",
      "title": "Revision Id"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "version",
    "feature",
    "revision_id"
  ],
  "title": "Bind"
}
```

<a id="model-bindingcreate"></a>

### BindingCreate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `subject_type` | não | string | default="user" |  |
| `subject_id` | sim | string |  |  |
| `role` | sim | string |  |  |
| `expires_at` | não | string / null |  |  |
| `permissions` | não | array de string / null |  |  |
| `condition_ref` | não | string / null |  |  |
| `delegation` | não | [Delegation](#model-delegation) / null |  |  |
| `parent_id` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "subject_type": {
      "type": "string",
      "title": "Subject Type",
      "default": "user"
    },
    "subject_id": {
      "type": "string",
      "title": "Subject Id"
    },
    "role": {
      "type": "string",
      "title": "Role"
    },
    "expires_at": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Expires At",
      "examples": [
        "2027-01-31T00:00:00Z"
      ]
    },
    "permissions": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array",
          "maxItems": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Permissions"
    },
    "condition_ref": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Condition Ref"
    },
    "delegation": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/Delegation"
        },
        {
          "type": "null"
        }
      ]
    },
    "parent_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Parent Id"
    }
  },
  "type": "object",
  "required": [
    "subject_id",
    "role"
  ],
  "title": "BindingCreate"
}
```

<a id="model-bindingrevoke"></a>

### BindingRevoke

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "version": {
      "type": "integer",
      "title": "Version"
    }
  },
  "type": "object",
  "required": [
    "version"
  ],
  "title": "BindingRevoke"
}
```

<a id="model-bindingupdate"></a>

### BindingUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `gpu_type` | não | string / null |  |  |
| `gpu_ref` | não | string / null |  |  |
| `workers` | sim | integer | minimum=0.0; maximum=1000.0 |  |
| `executions_per_worker` | não | integer | default=1; minimum=1.0; maximum=64.0 |  |
| `cpu` | não | number / null |  |  |
| `vram_override_gb` | não | number / null |  |  |
| `version` | não | integer / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "gpu_type": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Gpu Type"
    },
    "gpu_ref": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Gpu Ref"
    },
    "workers": {
      "type": "integer",
      "maximum": 1000.0,
      "minimum": 0.0,
      "title": "Workers"
    },
    "executions_per_worker": {
      "type": "integer",
      "maximum": 64.0,
      "minimum": 1.0,
      "title": "Executions Per Worker",
      "default": 1
    },
    "cpu": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 64.0,
          "exclusiveMinimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Cpu"
    },
    "vram_override_gb": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 200.0,
          "exclusiveMinimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Vram Override Gb"
    },
    "version": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Version"
    }
  },
  "type": "object",
  "required": [
    "workers"
  ],
  "title": "BindingUpdate"
}
```

<a id="model-body_analyze_image_upload_images_analyze_upload_post"></a>

### Body_analyze_image_upload_images_analyze_upload_post

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `mode` | não | string | default="single"; enum=["single", "full"] |  |
| `full_options` | não | string / null |  | JSON ImageFullOptions para mode=full |
| `datalake` | não | string / null |  | JSON Destination opcional para mode=full |
| `file` | sim | string (binary) |  | Imagem PNG, JPEG, WEBP, BMP, GIF ou TIFF |
| `task` | não | string | default="<MORE_DETAILED_CAPTION>"; enum=["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>", "<OCR>", "<OCR_WITH_REGION>", "<OD>", "<DENSE_REGION_CAPTION>", "<REGION_PROPOSAL>", "<CAPTION_TO_PHRASE_GROUNDING>", "<REFERRING_EXPRESSION_SEGMENTATION>", "<REGION_TO_SEGMENTATION>", "<OPEN_VOCABULARY_DETECTION>", "<REGION_TO_CATEGORY>", "<REGION_TO_DESCRIPTION>", "<REGION_TO_OCR>"] |  |
| `text_input` | não | string / null |  |  |
| `region` | não | string / null |  | Array JSON [x_min,y_min,x_max,y_max], normalizado entre 0 e 1. |
| `generation` | não | string / null |  | Objeto JSON conforme VisionGenerationOptions; omitido usa os padrões do worker. |
| `wait` | não | boolean | default=false | false retorna 202 com job_id; true espera pelo resultado. |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. mode=single com wait=true: a resposta ainda ecoa `image_base64` no topo (vem dos bytes desta requisição, não de uma cópia guardada). mode=full: a resposta (wait=true) e o relatório trazem `image.image_base64` null, e `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada. |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Esquema JSON completo:

```json
{
  "properties": {
    "mode": {
      "type": "string",
      "enum": [
        "single",
        "full"
      ],
      "title": "Mode",
      "default": "single"
    },
    "full_options": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Full Options",
      "description": "JSON ImageFullOptions para mode=full"
    },
    "datalake": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake",
      "description": "JSON Destination opcional para mode=full"
    },
    "file": {
      "type": "string",
      "format": "binary",
      "title": "File",
      "description": "Imagem PNG, JPEG, WEBP, BMP, GIF ou TIFF"
    },
    "task": {
      "type": "string",
      "enum": [
        "<CAPTION>",
        "<DETAILED_CAPTION>",
        "<MORE_DETAILED_CAPTION>",
        "<OCR>",
        "<OCR_WITH_REGION>",
        "<OD>",
        "<DENSE_REGION_CAPTION>",
        "<REGION_PROPOSAL>",
        "<CAPTION_TO_PHRASE_GROUNDING>",
        "<REFERRING_EXPRESSION_SEGMENTATION>",
        "<REGION_TO_SEGMENTATION>",
        "<OPEN_VOCABULARY_DETECTION>",
        "<REGION_TO_CATEGORY>",
        "<REGION_TO_DESCRIPTION>",
        "<REGION_TO_OCR>"
      ],
      "title": "Task",
      "default": "<MORE_DETAILED_CAPTION>"
    },
    "text_input": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 2000
        },
        {
          "type": "null"
        }
      ],
      "title": "Text Input"
    },
    "region": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Region",
      "description": "Array JSON [x_min,y_min,x_max,y_max], normalizado entre 0 e 1."
    },
    "generation": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Generation",
      "description": "Objeto JSON conforme VisionGenerationOptions; omitido usa os padrões do worker."
    },
    "wait": {
      "type": "boolean",
      "title": "Wait",
      "description": "false retorna 202 com job_id; true espera pelo resultado.",
      "default": false
    },
    "tags": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente."
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. mode=single com wait=true: a resposta ainda ecoa `image_base64` no topo (vem dos bytes desta requisição, não de uma cópia guardada). mode=full: a resposta (wait=true) e o relatório trazem `image.image_base64` null, e `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada.",
      "default": false
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a 'project'; nunca cria)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto (alternativa a 'folder')."
    }
  },
  "type": "object",
  "required": [
    "file"
  ],
  "title": "Body_analyze_image_upload_images_analyze_upload_post"
}
```

<a id="model-body_convert_document_convert_post"></a>

### Body_convert_document_convert_post

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `source_type` | sim | string |  | Tipo de fonte: 'file' (upload), 'url' (URL pública), 'gdrive' (Google Drive), 'dropbox' (Dropbox) |
| `source` | não | string / null |  | URL, file_id (Google Drive) ou path (Dropbox). Deixe vazio para upload de arquivo |
| `file` | não | string (binary) / null |  | Arquivo para upload direto (use quando source_type='file') |
| `name` | não | string / null |  | Nome de identificação opcional (padrão: nome do arquivo ou URL) |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `diarize` | não | boolean / null |  | Identificar falantes; omitido usa o padrão do provider |
| `min_speakers` | não | integer / null |  |  |
| `max_speakers` | não | integer / null |  |  |
| `language` | não | string / null |  | Idioma para áudio/vídeo; omitido detecta automaticamente |
| `include_word_timestamps` | não | boolean / null |  |  |
| `purge_source` | não | boolean | default=false | Se true, apaga os arquivos de origem do job — o arquivo enviado (MinIO e cópia local) e, num PDF dividido, os PDFs por página — quando o job termina: `completed`, ou `failed`/`partial` depois de esgotadas as tentativas automáticas (nunca enquanto houver retry ou página na fila). O resultado (markdown, markdown por página) fica. Depois disso o retry manual de página não é mais possível. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Arquivo repetido no mesmo projeto: com true o job existente é devolvido (`duplicate: true`) e passa a apagar a origem (na hora, se já terminou); com false um job existente cuja origem foi (ou será) apagada não é reaproveitado e um job novo é criado. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Esquema JSON completo:

```json
{
  "properties": {
    "source_type": {
      "type": "string",
      "title": "Source Type",
      "description": "Tipo de fonte: 'file' (upload), 'url' (URL pública), 'gdrive' (Google Drive), 'dropbox' (Dropbox)"
    },
    "source": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source",
      "description": "URL, file_id (Google Drive) ou path (Dropbox). Deixe vazio para upload de arquivo"
    },
    "file": {
      "anyOf": [
        {
          "type": "string",
          "format": "binary"
        },
        {
          "type": "null"
        }
      ],
      "title": "File",
      "description": "Arquivo para upload direto (use quando source_type='file')"
    },
    "name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Name",
      "description": "Nome de identificação opcional (padrão: nome do arquivo ou URL)"
    },
    "tags": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente."
    },
    "diarize": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Diarize",
      "description": "Identificar falantes; omitido usa o padrão do provider"
    },
    "min_speakers": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 20.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Min Speakers"
    },
    "max_speakers": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 20.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Max Speakers"
    },
    "language": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Language",
      "description": "Idioma para áudio/vídeo; omitido detecta automaticamente"
    },
    "include_word_timestamps": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Include Word Timestamps"
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga os arquivos de origem do job — o arquivo enviado (MinIO e cópia local) e, num PDF dividido, os PDFs por página — quando o job termina: `completed`, ou `failed`/`partial` depois de esgotadas as tentativas automáticas (nunca enquanto houver retry ou página na fila). O resultado (markdown, markdown por página) fica. Depois disso o retry manual de página não é mais possível. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Arquivo repetido no mesmo projeto: com true o job existente é devolvido (`duplicate: true`) e passa a apagar a origem (na hora, se já terminou); com false um job existente cuja origem foi (ou será) apagada não é reaproveitado e um job novo é criado. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source",
      "default": false
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a 'project'; nunca cria)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto (alternativa a 'folder')."
    }
  },
  "type": "object",
  "required": [
    "source_type"
  ],
  "title": "Body_convert_document_convert_post"
}
```

<a id="model-body_describe_image_upload_images_describe_upload_post"></a>

### Body_describe_image_upload_images_describe_upload_post

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  | Imagem (PNG, JPEG, WEBP, BMP, GIF, TIFF) |
| `task` | não | string | default="<MORE_DETAILED_CAPTION>" | <MORE_DETAILED_CAPTION>, <DETAILED_CAPTION> ou <CAPTION> |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada. |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Esquema JSON completo:

```json
{
  "properties": {
    "file": {
      "type": "string",
      "format": "binary",
      "title": "File",
      "description": "Imagem (PNG, JPEG, WEBP, BMP, GIF, TIFF)"
    },
    "task": {
      "type": "string",
      "title": "Task",
      "description": "<MORE_DETAILED_CAPTION>, <DETAILED_CAPTION> ou <CAPTION>",
      "default": "<MORE_DETAILED_CAPTION>"
    },
    "tags": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente."
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada.",
      "default": false
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a 'project'; nunca cria)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto (alternativa a 'folder')."
    }
  },
  "type": "object",
  "required": [
    "file"
  ],
  "title": "Body_describe_image_upload_images_describe_upload_post"
}
```

<a id="model-body_login_auth_login_post"></a>

### Body_login_auth_login_post

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `username` | sim | string |  |  |
| `password` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "username": {
      "type": "string",
      "title": "Username"
    },
    "password": {
      "type": "string",
      "title": "Password"
    }
  },
  "type": "object",
  "required": [
    "username",
    "password"
  ],
  "title": "Body_login_auth_login_post"
}
```

<a id="model-body_ocr_image_upload_images_ocr_upload_post"></a>

### Body_ocr_image_upload_images_ocr_upload_post

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  | Imagem (PNG, JPEG, WEBP, BMP, GIF, TIFF) |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada. |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Esquema JSON completo:

```json
{
  "properties": {
    "file": {
      "type": "string",
      "format": "binary",
      "title": "File",
      "description": "Imagem (PNG, JPEG, WEBP, BMP, GIF, TIFF)"
    },
    "tags": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente."
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada.",
      "default": false
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a 'project'; nunca cria)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto (alternativa a 'folder')."
    }
  },
  "type": "object",
  "required": [
    "file"
  ],
  "title": "Body_ocr_image_upload_images_ocr_upload_post"
}
```

<a id="model-body_transcribe_audio_transcribe_post"></a>

### Body_transcribe_audio_transcribe_post

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  | Arquivo de áudio (MP3, WAV, M4A, FLAC, OGG...) ou vídeo (MP4, MKV, MOV, WEBM, AVI...) |
| `name` | não | string / null |  | Nome de identificação (opcional, padrão: nome do arquivo) |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `language` | não | string / null |  | Código do idioma (ex: 'en', 'pt'). Auto-detectar se não fornecido |
| `include_timestamps` | não | boolean | default=true | Incluir marcadores de tempo na transcrição |
| `include_word_timestamps` | não | boolean | default=false | Incluir timestamps em nível de palavra (mais detalhado) |
| `output_format` | não | string | default="markdown" | Formato padrão do resultado em /jobs/{job_id}/result: markdown, vtt, srt, txt ou json |
| `purge_source` | não | boolean | default=false | Apagar o áudio/vídeo enviado quando a transcrição terminar (com sucesso, ou com falha depois das tentativas automáticas); guarda só o texto |
| `diarize` | não | boolean / null |  | Identificar falantes; omitido usa o padrão do provider |
| `min_speakers` | não | integer / null |  |  |
| `max_speakers` | não | integer / null |  |  |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Esquema JSON completo:

```json
{
  "properties": {
    "file": {
      "type": "string",
      "format": "binary",
      "title": "File",
      "description": "Arquivo de áudio (MP3, WAV, M4A, FLAC, OGG...) ou vídeo (MP4, MKV, MOV, WEBM, AVI...)"
    },
    "name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Name",
      "description": "Nome de identificação (opcional, padrão: nome do arquivo)"
    },
    "tags": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente."
    },
    "language": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Language",
      "description": "Código do idioma (ex: 'en', 'pt'). Auto-detectar se não fornecido"
    },
    "include_timestamps": {
      "type": "boolean",
      "title": "Include Timestamps",
      "description": "Incluir marcadores de tempo na transcrição",
      "default": true
    },
    "include_word_timestamps": {
      "type": "boolean",
      "title": "Include Word Timestamps",
      "description": "Incluir timestamps em nível de palavra (mais detalhado)",
      "default": false
    },
    "output_format": {
      "type": "string",
      "title": "Output Format",
      "description": "Formato padrão do resultado em /jobs/{job_id}/result: markdown, vtt, srt, txt ou json",
      "default": "markdown"
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Apagar o áudio/vídeo enviado quando a transcrição terminar (com sucesso, ou com falha depois das tentativas automáticas); guarda só o texto",
      "default": false
    },
    "diarize": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Diarize",
      "description": "Identificar falantes; omitido usa o padrão do provider"
    },
    "min_speakers": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 20.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Min Speakers"
    },
    "max_speakers": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 20.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Max Speakers"
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a 'project'; nunca cria)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto (alternativa a 'folder')."
    }
  },
  "type": "object",
  "required": [
    "file"
  ],
  "title": "Body_transcribe_audio_transcribe_post"
}
```

<a id="model-body_upload_and_convert_upload_post"></a>

### Body_upload_and_convert_upload_post

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  | Arquivo para conversão (PDF, DOCX, HTML, etc.) |
| `name` | não | string / null |  | Nome de identificação (opcional, padrão: nome do arquivo) |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `docling_preset` | não | string / null | default="fast" | Quality/speed preset for PDF conversion: 'fast' (~35s/MB, text-only), 'balanced' (~70-105s/MB, with images), 'quality' (~350s/MB, with OCR) |
| `diarize` | não | boolean / null |  | Identificar falantes; omitido usa o padrão do provider |
| `min_speakers` | não | integer / null |  |  |
| `max_speakers` | não | integer / null |  |  |
| `language` | não | string / null |  | Idioma para áudio/vídeo; omitido detecta automaticamente |
| `include_word_timestamps` | não | boolean / null |  |  |
| `purge_source` | não | boolean | default=false | Se true, apaga os arquivos de origem do job — o arquivo enviado (MinIO e cópia local) e, num PDF dividido, os PDFs por página — quando o job termina: `completed`, ou `failed`/`partial` depois de esgotadas as tentativas automáticas (nunca enquanto houver retry ou página na fila). O resultado (markdown, markdown por página) fica. Depois disso o retry manual de página não é mais possível. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Arquivo repetido no mesmo projeto: com true o job existente é devolvido (`duplicate: true`) e passa a apagar a origem (na hora, se já terminou); com false um job existente cuja origem foi (ou será) apagada não é reaproveitado e um job novo é criado. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |

Esquema JSON completo:

```json
{
  "properties": {
    "file": {
      "type": "string",
      "format": "binary",
      "title": "File",
      "description": "Arquivo para conversão (PDF, DOCX, HTML, etc.)"
    },
    "name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Name",
      "description": "Nome de identificação (opcional, padrão: nome do arquivo)"
    },
    "tags": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente."
    },
    "docling_preset": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Docling Preset",
      "description": "Quality/speed preset for PDF conversion: 'fast' (~35s/MB, text-only), 'balanced' (~70-105s/MB, with images), 'quality' (~350s/MB, with OCR)",
      "default": "fast"
    },
    "diarize": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Diarize",
      "description": "Identificar falantes; omitido usa o padrão do provider"
    },
    "min_speakers": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 20.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Min Speakers"
    },
    "max_speakers": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 20.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Max Speakers"
    },
    "language": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Language",
      "description": "Idioma para áudio/vídeo; omitido detecta automaticamente"
    },
    "include_word_timestamps": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Include Word Timestamps"
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga os arquivos de origem do job — o arquivo enviado (MinIO e cópia local) e, num PDF dividido, os PDFs por página — quando o job termina: `completed`, ou `failed`/`partial` depois de esgotadas as tentativas automáticas (nunca enquanto houver retry ou página na fila). O resultado (markdown, markdown por página) fica. Depois disso o retry manual de página não é mais possível. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Arquivo repetido no mesmo projeto: com true o job existente é devolvido (`duplicate: true`) e passa a apagar a origem (na hora, se já terminou); com false um job existente cuja origem foi (ou será) apagada não é reaproveitado e um job novo é criado. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source",
      "default": false
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a 'project'; nunca cria)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto (alternativa a 'folder')."
    }
  },
  "type": "object",
  "required": [
    "file"
  ],
  "title": "Body_upload_and_convert_upload_post"
}
```

<a id="model-body_upload_images_faces_upload_post"></a>

### Body_upload_images_faces_upload_post

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  |  |
| `face_options` | não | string / null |  |  |
| `wait` | não | boolean | default=false |  |
| `project` | não | string / null |  |  |
| `project_id` | não | string / null |  |  |
| `folder` | não | string / null |  |  |
| `folder_id` | não | string / null |  |  |
| `tags` | não | string / null |  |  |
| `datalake` | não | string / null |  |  |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta (wait=true) e o relatório trazem `image.image_base64` null. `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada. |

Esquema JSON completo:

```json
{
  "properties": {
    "file": {
      "type": "string",
      "format": "binary",
      "title": "File"
    },
    "face_options": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Face Options"
    },
    "wait": {
      "type": "boolean",
      "title": "Wait",
      "default": false
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project"
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id"
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder"
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id"
    },
    "tags": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags"
    },
    "datalake": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake"
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta (wait=true) e o relatório trazem `image.image_base64` null. `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada.",
      "default": false
    }
  },
  "type": "object",
  "required": [
    "file"
  ],
  "title": "Body_upload_images_faces_upload_post"
}
```

<a id="model-budgetupdate"></a>

### BudgetUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `limit_usd` | não | number / string / null |  |  |
| `min_remaining_usd` | não | number / string / null |  |  |
| `soft_pct` | não | integer / null |  |  |
| `period_tz` | não | string / null |  |  |
| `period_anchor_day` | não | integer / null |  |  |
| `version` | não | integer / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "limit_usd": {
      "anyOf": [
        {
          "type": "number",
          "exclusiveMinimum": 0.0
        },
        {
          "type": "string",
          "pattern": "^(?!^[-+.]*$)[+-]?0*(?:\\d{0,6}|(?=[\\d.]{1,13}0*$)\\d{0,6}\\.\\d{0,6}0*$)"
        },
        {
          "type": "null"
        }
      ],
      "title": "Limit Usd"
    },
    "min_remaining_usd": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "string",
          "pattern": "^(?!^[-+.]*$)[+-]?0*(?:\\d{0,6}|(?=[\\d.]{1,13}0*$)\\d{0,6}\\.\\d{0,6}0*$)"
        },
        {
          "type": "null"
        }
      ],
      "title": "Min Remaining Usd"
    },
    "soft_pct": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 100.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Soft Pct"
    },
    "period_tz": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 64
        },
        {
          "type": "null"
        }
      ],
      "title": "Period Tz"
    },
    "period_anchor_day": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 28.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Period Anchor Day"
    },
    "version": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Version"
    }
  },
  "type": "object",
  "title": "BudgetUpdate"
}
```

<a id="model-childjobs"></a>

### ChildJobs

Jobs filhos de um job principal

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `split_job_id` | não | string (uuid) / null |  |  |
| `page_job_ids` | não | array de string (uuid) / null |  |  |
| `merge_job_id` | não | string (uuid) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "split_job_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Split Job Id"
    },
    "page_job_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string",
            "format": "uuid"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Page Job Ids"
    },
    "merge_job_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Merge Job Id"
    }
  },
  "type": "object",
  "title": "ChildJobs",
  "description": "Jobs filhos de um job principal"
}
```

<a id="model-connection"></a>

### Connection

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `adapter_type` | sim | string |  |  |
| `display_name` | sim | string | minLength=1; maxLength=100 |  |
| `slug` | sim | string | pattern="^[a-z0-9][a-z0-9_-]{1,63}$" |  |

Esquema JSON completo:

```json
{
  "properties": {
    "adapter_type": {
      "type": "string",
      "title": "Adapter Type"
    },
    "display_name": {
      "type": "string",
      "maxLength": 100,
      "minLength": 1,
      "title": "Display Name"
    },
    "slug": {
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9_-]{1,63}$",
      "title": "Slug"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "adapter_type",
    "display_name",
    "slug"
  ],
  "title": "Connection"
}
```

<a id="model-connectionconfig"></a>

### ConnectionConfig

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `endpoint` | não | string / null |  |  |
| `region` | não | string / null |  |  |
| `project_id` | não | string / null |  |  |
| `buckets` | não | array de string | maxItems=100 |  |
| `default_bucket` | não | string / null |  |  |
| `default_prefix` | não | string | default=""; maxLength=700 |  |
| `partitioning` | não | [PartitionStrategy](#model-partitionstrategy) / null |  |  |
| `default_partition_values` | não | object | additionalProperties={"type": "string"} | Valores personalizados padrão. Também preserva contexto sem criar partições, como agent_id. |

Esquema JSON completo:

```json
{
  "properties": {
    "endpoint": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Endpoint"
    },
    "region": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Region"
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id"
    },
    "buckets": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "maxItems": 100,
      "title": "Buckets"
    },
    "default_bucket": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Default Bucket"
    },
    "default_prefix": {
      "type": "string",
      "maxLength": 700,
      "title": "Default Prefix",
      "default": ""
    },
    "partitioning": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/PartitionStrategy"
        },
        {
          "type": "null"
        }
      ]
    },
    "default_partition_values": {
      "additionalProperties": {
        "type": "string"
      },
      "type": "object",
      "title": "Default Partition Values",
      "description": "Valores personalizados padrão. Também preserva contexto sem criar partições, como agent_id."
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "ConnectionConfig"
}
```

<a id="model-connectioncreate"></a>

### ConnectionCreate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | sim | string | minLength=1; maxLength=150 |  |
| `provider` | sim | string | enum=["s3", "minio", "gcs", "azure"] |  |
| `config` | não | [ConnectionConfig](#model-connectionconfig) |  |  |
| `credentials` | sim | object | additionalProperties={"type": "string", "format": "password", "writeOnly": true} |  |
| `enabled` | não | boolean | default=true |  |

Esquema JSON completo:

```json
{
  "properties": {
    "name": {
      "type": "string",
      "maxLength": 150,
      "minLength": 1,
      "title": "Name"
    },
    "provider": {
      "type": "string",
      "enum": [
        "s3",
        "minio",
        "gcs",
        "azure"
      ],
      "title": "Provider"
    },
    "config": {
      "$ref": "#/components/schemas/ConnectionConfig"
    },
    "credentials": {
      "additionalProperties": {
        "type": "string",
        "format": "password",
        "writeOnly": true
      },
      "type": "object",
      "title": "Credentials"
    },
    "enabled": {
      "type": "boolean",
      "title": "Enabled",
      "default": true
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "name",
    "provider",
    "credentials"
  ],
  "title": "ConnectionCreate"
}
```

<a id="model-connectionupdate"></a>

### ConnectionUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | não | string / null |  |  |
| `config` | não | [ConnectionConfig](#model-connectionconfig) / null |  |  |
| `credentials` | não | object / null |  |  |
| `enabled` | não | boolean / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 150,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Name"
    },
    "config": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/ConnectionConfig"
        },
        {
          "type": "null"
        }
      ]
    },
    "credentials": {
      "anyOf": [
        {
          "additionalProperties": {
            "type": "string",
            "format": "password",
            "writeOnly": true
          },
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Credentials"
    },
    "enabled": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Enabled"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "ConnectionUpdate"
}
```

<a id="model-constraints"></a>

### Constraints

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_ids` | não | array de string | maxItems=200 |  |
| `profile_ids` | não | array de string / null |  |  |
| `adapters` | não | array de string | maxItems=100 |  |
| `features` | não | array de string | maxItems=100 |  |
| `environments` | não | array de string |  |  |
| `host_ids` | não | array de string / null |  |  |
| `gpu_uuids` | não | array de string / null |  |  |
| `model_ids` | não | array de string / null |  |  |
| `max_replicas` | não | integer | default=0; minimum=0.0; maximum=100.0 |  |
| `max_concurrency` | não | integer | default=1; minimum=1.0; maximum=100.0 |  |
| `max_cpu` | não | number | default=1; maximum=256.0; exclusiveMinimum=0.0 |  |
| `max_memory_mb` | não | integer | default=256; minimum=256.0; maximum=262144.0 |  |
| `max_warm_seconds` | não | integer | default=0; minimum=0.0; maximum=86400.0 |  |
| `max_usd` | não | number / string | default="0" |  |

Esquema JSON completo:

```json
{
  "properties": {
    "engine_ids": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "maxItems": 200,
      "title": "Engine Ids"
    },
    "profile_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array",
          "maxItems": 200
        },
        {
          "type": "null"
        }
      ],
      "title": "Profile Ids"
    },
    "adapters": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "maxItems": 100,
      "title": "Adapters"
    },
    "features": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "maxItems": 100,
      "title": "Features"
    },
    "environments": {
      "items": {
        "type": "string",
        "enum": [
          "development",
          "staging",
          "production"
        ]
      },
      "type": "array",
      "title": "Environments"
    },
    "host_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array",
          "maxItems": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Host Ids"
    },
    "gpu_uuids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array",
          "maxItems": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Gpu Uuids"
    },
    "model_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array",
          "maxItems": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Model Ids"
    },
    "max_replicas": {
      "type": "integer",
      "maximum": 100.0,
      "minimum": 0.0,
      "title": "Max Replicas",
      "default": 0
    },
    "max_concurrency": {
      "type": "integer",
      "maximum": 100.0,
      "minimum": 1.0,
      "title": "Max Concurrency",
      "default": 1
    },
    "max_cpu": {
      "type": "number",
      "maximum": 256.0,
      "exclusiveMinimum": 0.0,
      "title": "Max Cpu",
      "default": 1
    },
    "max_memory_mb": {
      "type": "integer",
      "maximum": 262144.0,
      "minimum": 256.0,
      "title": "Max Memory Mb",
      "default": 256
    },
    "max_warm_seconds": {
      "type": "integer",
      "maximum": 86400.0,
      "minimum": 0.0,
      "title": "Max Warm Seconds",
      "default": 0
    },
    "max_usd": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 1000.0,
          "minimum": 0.0
        },
        {
          "type": "string",
          "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$"
        }
      ],
      "title": "Max Usd",
      "default": "0"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "Constraints"
}
```

<a id="model-consumer"></a>

### Consumer

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_id` | sim | string |  |  |
| `feature` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "engine_id": {
      "type": "string",
      "title": "Engine Id"
    },
    "feature": {
      "type": "string",
      "title": "Feature"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "engine_id",
    "feature"
  ],
  "title": "Consumer"
}
```

<a id="model-controlbinding"></a>

### ControlBinding

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `gpu_type` | não | string / null |  |  |
| `gpu_ref` | não | string / null |  |  |
| `workers` | sim | integer | minimum=0.0; maximum=1000.0 |  |
| `executions_per_worker` | não | integer | default=1; minimum=1.0; maximum=64.0 |  |
| `cpu` | não | number / null |  |  |
| `vram_override_gb` | não | number / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "gpu_type": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Gpu Type"
    },
    "gpu_ref": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Gpu Ref"
    },
    "workers": {
      "type": "integer",
      "maximum": 1000.0,
      "minimum": 0.0,
      "title": "Workers"
    },
    "executions_per_worker": {
      "type": "integer",
      "maximum": 64.0,
      "minimum": 1.0,
      "title": "Executions Per Worker",
      "default": 1
    },
    "cpu": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 64.0,
          "exclusiveMinimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Cpu"
    },
    "vram_override_gb": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 200.0,
          "exclusiveMinimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Vram Override Gb"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "workers"
  ],
  "title": "ControlBinding"
}
```

<a id="model-conversionresult"></a>

### ConversionResult

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `markdown` | sim | string |  |  |
| `metadata` | sim | [DocumentMetadata](#model-documentmetadata) |  |  |
| `image` | não | [ImageJobResult](#model-imagejobresult) / [ImageFullAnalysisResult](#model-imagefullanalysisresult) / [ImageFullV2Result](#model-imagefullv2result) / [FaceAnalysisResult](#model-faceanalysisresult) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "markdown": {
      "type": "string",
      "title": "Markdown"
    },
    "metadata": {
      "$ref": "#/components/schemas/DocumentMetadata"
    },
    "image": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/ImageJobResult"
        },
        {
          "$ref": "#/components/schemas/ImageFullAnalysisResult"
        },
        {
          "$ref": "#/components/schemas/ImageFullV2Result"
        },
        {
          "$ref": "#/components/schemas/FaceAnalysisResult"
        },
        {
          "type": "null"
        }
      ],
      "title": "Image"
    }
  },
  "type": "object",
  "required": [
    "markdown",
    "metadata"
  ],
  "title": "ConversionResult"
}
```

<a id="model-createbucket"></a>

### CreateBucket

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `provider` | sim | string | enum=["s3", "minio", "gcs", "azure"] |  |
| `config` | não | [ConnectionConfig](#model-connectionconfig) |  |  |
| `credentials` | não | object / null |  |  |
| `connection_id` | não | string / null |  |  |
| `bucket` | sim | string | minLength=3; maxLength=222 |  |
| `location` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "provider": {
      "type": "string",
      "enum": [
        "s3",
        "minio",
        "gcs",
        "azure"
      ],
      "title": "Provider"
    },
    "config": {
      "$ref": "#/components/schemas/ConnectionConfig"
    },
    "credentials": {
      "anyOf": [
        {
          "additionalProperties": {
            "type": "string",
            "format": "password",
            "writeOnly": true
          },
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Credentials"
    },
    "connection_id": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 36
        },
        {
          "type": "null"
        }
      ],
      "title": "Connection Id"
    },
    "bucket": {
      "type": "string",
      "maxLength": 222,
      "minLength": 3,
      "title": "Bucket"
    },
    "location": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 100,
          "minLength": 1,
          "pattern": "^[a-zA-Z0-9-]+$"
        },
        {
          "type": "null"
        }
      ],
      "title": "Location"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "provider",
    "bucket"
  ],
  "title": "CreateBucket"
}
```

<a id="model-createsession"></a>

### CreateSession

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `project` | não | string / null |  |  |
| `project_id` | não | string / null |  |  |
| `folder` | não | string / null |  |  |
| `folder_id` | não | string / null |  |  |
| `name` | não | string | default="Transcrição ao vivo"; minLength=1; maxLength=1000 |  |
| `tags` | não | array de string |  |  |
| `language` | não | string | default="pt"; const="pt" |  |
| `audio` | não | [AudioFormat](#model-audioformat) |  |  |
| `protocol` | não | integer | default=1; enum=[1, 2] |  |
| `diarize` | não | boolean | default=false |  |

Esquema JSON completo:

```json
{
  "properties": {
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project"
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id"
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder"
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id"
    },
    "name": {
      "type": "string",
      "maxLength": 1000,
      "minLength": 1,
      "title": "Name",
      "default": "Transcrição ao vivo"
    },
    "tags": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Tags"
    },
    "language": {
      "type": "string",
      "const": "pt",
      "title": "Language",
      "default": "pt"
    },
    "audio": {
      "$ref": "#/components/schemas/AudioFormat"
    },
    "protocol": {
      "type": "integer",
      "enum": [
        1,
        2
      ],
      "title": "Protocol",
      "default": 1
    },
    "diarize": {
      "type": "boolean",
      "title": "Diarize",
      "default": false
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "CreateSession"
}
```

<a id="model-credentialsdelete"></a>

### CredentialsDelete

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `current_password` | sim | string |  |  |
| `version` | não | integer / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "current_password": {
      "type": "string",
      "title": "Current Password"
    },
    "version": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Version"
    }
  },
  "type": "object",
  "required": [
    "current_password"
  ],
  "title": "CredentialsDelete"
}
```

<a id="model-credentialsupdate"></a>

### CredentialsUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `fields` | sim | object | additionalProperties={"type": "string"} |  |
| `current_password` | sim | string |  |  |
| `version` | não | integer / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "fields": {
      "additionalProperties": {
        "type": "string"
      },
      "type": "object",
      "title": "Fields"
    },
    "current_password": {
      "type": "string",
      "title": "Current Password"
    },
    "version": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Version"
    }
  },
  "type": "object",
  "required": [
    "fields",
    "current_password"
  ],
  "title": "CredentialsUpdate"
}
```

<a id="model-delegation"></a>

### Delegation

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `permissions` | sim | array de string | maxItems=100 |  |
| `constraints` | sim | [Constraints](#model-constraints) |  |  |
| `max_grant_seconds` | não | integer | default=3600; minimum=60.0; maximum=31536000.0 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "permissions": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "maxItems": 100,
      "title": "Permissions"
    },
    "constraints": {
      "$ref": "#/components/schemas/Constraints"
    },
    "max_grant_seconds": {
      "type": "integer",
      "maximum": 31536000.0,
      "minimum": 60.0,
      "title": "Max Grant Seconds",
      "default": 3600
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "permissions",
    "constraints"
  ],
  "title": "Delegation"
}
```

<a id="model-destination"></a>

### Destination

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `connection_id` | sim | string | minLength=1; maxLength=36 |  |
| `bucket` | sim | string | minLength=1; maxLength=255 |  |
| `prefix` | não | string | default=""; maxLength=700 |  |
| `partitioning` | não | [PartitionStrategy](#model-partitionstrategy) / null |  | Estratégia desta solicitação. Ausência herda a conexão; mode=none desativa partições. |
| `partition_values` | não | object | additionalProperties={"type": "string"} | Valores personalizados por job, como client_id, conversation_id e agent_id. Somente chaves da estratégia criam diretórios; todos os valores ficam congelados e, com analytics=jsonl, preservados em partition_values_json. Sobrescrevem os padrões da conexão. |

Esquema JSON completo:

```json
{
  "properties": {
    "connection_id": {
      "type": "string",
      "maxLength": 36,
      "minLength": 1,
      "title": "Connection Id"
    },
    "bucket": {
      "type": "string",
      "maxLength": 255,
      "minLength": 1,
      "title": "Bucket"
    },
    "prefix": {
      "type": "string",
      "maxLength": 700,
      "title": "Prefix",
      "default": ""
    },
    "partitioning": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/PartitionStrategy"
        },
        {
          "type": "null"
        }
      ],
      "description": "Estratégia desta solicitação. Ausência herda a conexão; mode=none desativa partições."
    },
    "partition_values": {
      "additionalProperties": {
        "type": "string"
      },
      "type": "object",
      "title": "Partition Values",
      "description": "Valores personalizados por job, como client_id, conversation_id e agent_id. Somente chaves da estratégia criam diretórios; todos os valores ficam congelados e, com analytics=jsonl, preservados em partition_values_json. Sobrescrevem os padrões da conexão."
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "connection_id",
    "bucket"
  ],
  "title": "Destination"
}
```

<a id="model-diarizationmetadata"></a>

### DiarizationMetadata

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `status` | sim | string | enum=["completed", "disabled"] |  |
| `speaker_count` | não | integer / null |  |  |
| `engine` | não | string / null |  |  |
| `model` | não | string / null |  |  |
| `revision` | não | objeto livre / null |  |  |
| `turns` | não | array de [DiarizationTurn](#model-diarizationturn) | default=[] |  |
| `generation` | não | integer / null |  |  |
| `provenance` | não | object / null |  |  |
| `analysis_status` | não | string / null |  |  |
| `reason_code` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "status": {
      "type": "string",
      "enum": [
        "completed",
        "disabled"
      ],
      "title": "Status"
    },
    "speaker_count": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Speaker Count"
    },
    "engine": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Engine"
    },
    "model": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Model"
    },
    "revision": {
      "anyOf": [
        {},
        {
          "type": "null"
        }
      ],
      "title": "Revision"
    },
    "turns": {
      "items": {
        "$ref": "#/components/schemas/DiarizationTurn"
      },
      "type": "array",
      "title": "Turns",
      "default": []
    },
    "generation": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Generation"
    },
    "provenance": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Provenance"
    },
    "analysis_status": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Analysis Status"
    },
    "reason_code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason Code"
    }
  },
  "type": "object",
  "required": [
    "status"
  ],
  "title": "DiarizationMetadata"
}
```

<a id="model-diarizationturn"></a>

### DiarizationTurn

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `start` | sim | number |  |  |
| `end` | sim | number |  |  |
| `speaker_id` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "start": {
      "type": "number",
      "title": "Start"
    },
    "end": {
      "type": "number",
      "title": "End"
    },
    "speaker_id": {
      "type": "string",
      "title": "Speaker Id"
    }
  },
  "type": "object",
  "required": [
    "start",
    "end",
    "speaker_id"
  ],
  "title": "DiarizationTurn"
}
```

<a id="model-discoverconnection"></a>

### DiscoverConnection

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `provider` | sim | string | enum=["s3", "minio", "gcs", "azure"] |  |
| `config` | não | [ConnectionConfig](#model-connectionconfig) |  |  |
| `credentials` | não | object / null |  |  |
| `connection_id` | não | string / null |  |  |
| `bucket` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "provider": {
      "type": "string",
      "enum": [
        "s3",
        "minio",
        "gcs",
        "azure"
      ],
      "title": "Provider"
    },
    "config": {
      "$ref": "#/components/schemas/ConnectionConfig"
    },
    "credentials": {
      "anyOf": [
        {
          "additionalProperties": {
            "type": "string",
            "format": "password",
            "writeOnly": true
          },
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Credentials"
    },
    "connection_id": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 36
        },
        {
          "type": "null"
        }
      ],
      "title": "Connection Id"
    },
    "bucket": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Bucket"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "provider"
  ],
  "title": "DiscoverConnection"
}
```

<a id="model-documentmetadata"></a>

### DocumentMetadata

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `pages` | não | integer / null |  |  |
| `words` | não | integer / null |  |  |
| `format` | sim | string |  |  |
| `size_bytes` | sim | integer |  |  |
| `title` | não | string / null |  |  |
| `author` | não | string / null |  |  |
| `language` | não | string / null |  |  |
| `duration` | não | number / null |  |  |
| `device` | não | string / null |  |  |
| `available_formats` | não | array de string / null |  |  |
| `schema_version` | não | integer / null |  |  |
| `speakers` | não | array de [TranscriptSpeaker](#model-transcriptspeaker) / null |  |  |
| `diarization` | não | [DiarizationMetadata](#model-diarizationmetadata) / null |  |  |
| `alignment` | não | [AlignmentMetadata](#model-alignmentmetadata) / null |  |  |
| `provenance` | não | object / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "pages": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Pages"
    },
    "words": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Words"
    },
    "format": {
      "type": "string",
      "title": "Format"
    },
    "size_bytes": {
      "type": "integer",
      "title": "Size Bytes"
    },
    "title": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Title"
    },
    "author": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Author"
    },
    "language": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Language"
    },
    "duration": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "title": "Duration"
    },
    "device": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Device"
    },
    "available_formats": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Available Formats"
    },
    "schema_version": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Schema Version"
    },
    "speakers": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/TranscriptSpeaker"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Speakers"
    },
    "diarization": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DiarizationMetadata"
        },
        {
          "type": "null"
        }
      ]
    },
    "alignment": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/AlignmentMetadata"
        },
        {
          "type": "null"
        }
      ]
    },
    "provenance": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Provenance"
    }
  },
  "type": "object",
  "required": [
    "format",
    "size_bytes"
  ],
  "title": "DocumentMetadata"
}
```

<a id="model-execute"></a>

### Execute

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `plan_id` | sim | string |  |  |
| `plan_hash` | sim | string |  |  |
| `confirm_paid_operation` | não | boolean | default=false |  |

Esquema JSON completo:

```json
{
  "properties": {
    "plan_id": {
      "type": "string",
      "title": "Plan Id"
    },
    "plan_hash": {
      "type": "string",
      "title": "Plan Hash"
    },
    "confirm_paid_operation": {
      "type": "boolean",
      "title": "Confirm Paid Operation",
      "default": false
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "plan_id",
    "plan_hash"
  ],
  "title": "Execute"
}
```

<a id="model-faceanalysisresult"></a>

### FaceAnalysisResult

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `detection` | sim | object | additionalProperties=true |  |
| `faces` | não | array de [FaceRecord](#model-facerecord) |  |  |
| `models` | não | array de [FaceModelInfo](#model-facemodelinfo) |  |  |
| `request` | sim | object | additionalProperties=true |  |
| `coverage` | sim | object | additionalProperties=true |  |
| `steps` | sim | array de [FaceStepResult](#model-facestepresult) |  |  |
| `operation` | não | string | default="face_analysis"; const="face_analysis" |  |
| `schema_version` | não | string | default="face-result-v1"; const="face-result-v1" |  |
| `profile` | não | string | default="image-faces-v1"; const="image-faces-v1" |  |
| `analysis_status` | sim | string | enum=["completed", "partial", "failed", "cancelled"] |  |
| `width` | sim | integer |  |  |
| `height` | sim | integer |  |  |
| `image_base64` | não | string / null |  |  |
| `image_mime_type` | não | string | default="image/png" |  |
| `duration_ms` | não | integer | default=0 |  |
| `calls_started` | não | integer | default=0 |  |
| `calls_by_provider` | não | object | additionalProperties={"type": "integer"} |  |
| `reason_code` | não | string / null |  |  |
| `source_sha256` | não | string | default="" |  |
| `frame_policy` | não | string | default="first_frame" |  |

Esquema JSON completo:

```json
{
  "properties": {
    "detection": {
      "additionalProperties": true,
      "type": "object",
      "title": "Detection"
    },
    "faces": {
      "items": {
        "$ref": "#/components/schemas/FaceRecord"
      },
      "type": "array",
      "title": "Faces"
    },
    "models": {
      "items": {
        "$ref": "#/components/schemas/FaceModelInfo"
      },
      "type": "array",
      "title": "Models"
    },
    "request": {
      "additionalProperties": true,
      "type": "object",
      "title": "Request"
    },
    "coverage": {
      "additionalProperties": true,
      "type": "object",
      "title": "Coverage"
    },
    "steps": {
      "items": {
        "$ref": "#/components/schemas/FaceStepResult"
      },
      "type": "array",
      "title": "Steps"
    },
    "operation": {
      "type": "string",
      "const": "face_analysis",
      "title": "Operation",
      "default": "face_analysis"
    },
    "schema_version": {
      "type": "string",
      "const": "face-result-v1",
      "title": "Schema Version",
      "default": "face-result-v1"
    },
    "profile": {
      "type": "string",
      "const": "image-faces-v1",
      "title": "Profile",
      "default": "image-faces-v1"
    },
    "analysis_status": {
      "type": "string",
      "enum": [
        "completed",
        "partial",
        "failed",
        "cancelled"
      ],
      "title": "Analysis Status"
    },
    "width": {
      "type": "integer",
      "title": "Width"
    },
    "height": {
      "type": "integer",
      "title": "Height"
    },
    "image_base64": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Image Base64"
    },
    "image_mime_type": {
      "type": "string",
      "title": "Image Mime Type",
      "default": "image/png"
    },
    "duration_ms": {
      "type": "integer",
      "title": "Duration Ms",
      "default": 0
    },
    "calls_started": {
      "type": "integer",
      "title": "Calls Started",
      "default": 0
    },
    "calls_by_provider": {
      "additionalProperties": {
        "type": "integer"
      },
      "type": "object",
      "title": "Calls By Provider"
    },
    "reason_code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason Code"
    },
    "source_sha256": {
      "type": "string",
      "title": "Source Sha256",
      "default": ""
    },
    "frame_policy": {
      "type": "string",
      "title": "Frame Policy",
      "default": "first_frame"
    }
  },
  "type": "object",
  "required": [
    "detection",
    "request",
    "coverage",
    "steps",
    "analysis_status",
    "width",
    "height"
  ],
  "title": "FaceAnalysisResult"
}
```

<a id="model-faceanalyzerequest"></a>

### FaceAnalyzeRequest

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `image_base64` | sim | string |  | Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF. |
| `tags` | não | array de string / null |  | Tags do job (ex.: ["cliente-x", "nf"]). Viram minúsculas; até 20 de até 50 caracteres. |
| `filename` | não | string / null |  | Nome de identificação opcional. |
| `project` | não | string / null |  | Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a `project`). |
| `folder` | não | string / null |  | Nome da pasta no projeto (opcional, get-or-add, sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta (wait=true) e o relatório trazem `image.image_base64` null. `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada. |
| `face_options` | não | [FaceRequestOptions](#model-facerequestoptions) |  |  |
| `wait` | não | boolean | default=false |  |
| `datalake` | não | [Destination](#model-destination) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "image_base64": {
      "type": "string",
      "title": "Image Base64",
      "description": "Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF."
    },
    "tags": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags do job (ex.: [\"cliente-x\", \"nf\"]). Viram minúsculas; até 20 de até 50 caracteres."
    },
    "filename": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Filename",
      "description": "Nome de identificação opcional."
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a `project`)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta no projeto (opcional, get-or-add, sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto."
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta (wait=true) e o relatório trazem `image.image_base64` null. `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada.",
      "default": false
    },
    "face_options": {
      "$ref": "#/components/schemas/FaceRequestOptions"
    },
    "wait": {
      "type": "boolean",
      "title": "Wait",
      "default": false
    },
    "datalake": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/Destination"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "image_base64"
  ],
  "title": "FaceAnalyzeRequest"
}
```

<a id="model-faceanalyzeresponse"></a>

### FaceAnalyzeResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string |  |  |
| `status` | sim | string |  |  |
| `markdown` | sim | string |  |  |
| `image` | sim | [FaceAnalysisResult](#model-faceanalysisresult) |  |  |
| `attempt` | não | integer / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "title": "Job Id"
    },
    "status": {
      "type": "string",
      "title": "Status"
    },
    "markdown": {
      "type": "string",
      "title": "Markdown"
    },
    "image": {
      "$ref": "#/components/schemas/FaceAnalysisResult"
    },
    "attempt": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Attempt"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "status",
    "markdown",
    "image"
  ],
  "title": "FaceAnalyzeResponse"
}
```

<a id="model-facemodelinfo"></a>

### FaceModelInfo

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `operation` | sim | string |  |  |
| `provider` | sim | string |  |  |
| `model_id` | sim | string |  |  |
| `revision` | sim | string |  |  |
| `sha256` | sim | string |  |  |
| `runtime` | sim | string |  |  |
| `runtime_version` | sim | string |  |  |
| `device` | não | string | default="cpu"; const="cpu" |  |
| `license` | sim | string |  |  |
| `license_url` | sim | string |  |  |
| `additional_license_urls` | não | array de string |  |  |
| `source_url` | sim | string |  |  |
| `preprocessing` | não | object | additionalProperties=true |  |
| `labels` | não | array de string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "operation": {
      "type": "string",
      "title": "Operation"
    },
    "provider": {
      "type": "string",
      "title": "Provider"
    },
    "model_id": {
      "type": "string",
      "title": "Model Id"
    },
    "revision": {
      "type": "string",
      "title": "Revision"
    },
    "sha256": {
      "type": "string",
      "title": "Sha256"
    },
    "runtime": {
      "type": "string",
      "title": "Runtime"
    },
    "runtime_version": {
      "type": "string",
      "title": "Runtime Version"
    },
    "device": {
      "type": "string",
      "const": "cpu",
      "title": "Device",
      "default": "cpu"
    },
    "license": {
      "type": "string",
      "title": "License"
    },
    "license_url": {
      "type": "string",
      "title": "License Url"
    },
    "additional_license_urls": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Additional License Urls"
    },
    "source_url": {
      "type": "string",
      "title": "Source Url"
    },
    "preprocessing": {
      "additionalProperties": true,
      "type": "object",
      "title": "Preprocessing"
    },
    "labels": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Labels"
    }
  },
  "type": "object",
  "required": [
    "operation",
    "provider",
    "model_id",
    "revision",
    "sha256",
    "runtime",
    "runtime_version",
    "license",
    "license_url",
    "source_url"
  ],
  "title": "FaceModelInfo"
}
```

<a id="model-facerecord"></a>

### FaceRecord

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `face_id` | sim | string |  |  |
| `bbox` | sim | array de number | minItems=4; maxItems=4 |  |
| `bbox_normalized` | sim | array de number | minItems=4; maxItems=4 |  |
| `detection_confidence` | sim | number | minimum=0.0; maximum=1.0 |  |
| `keypoints` | não | array de object |  |  |
| `crop` | sim | array de integer | minItems=4; maxItems=4 |  |
| `movements` | não | object | additionalProperties=true |  |
| `expression` | não | object | additionalProperties=true |  |

Esquema JSON completo:

```json
{
  "properties": {
    "face_id": {
      "type": "string",
      "title": "Face Id"
    },
    "bbox": {
      "items": {
        "type": "number"
      },
      "type": "array",
      "maxItems": 4,
      "minItems": 4,
      "title": "Bbox"
    },
    "bbox_normalized": {
      "items": {
        "type": "number"
      },
      "type": "array",
      "maxItems": 4,
      "minItems": 4,
      "title": "Bbox Normalized"
    },
    "detection_confidence": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Detection Confidence"
    },
    "keypoints": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "type": "array",
      "title": "Keypoints"
    },
    "crop": {
      "items": {
        "type": "integer"
      },
      "type": "array",
      "maxItems": 4,
      "minItems": 4,
      "title": "Crop"
    },
    "movements": {
      "additionalProperties": true,
      "type": "object",
      "title": "Movements"
    },
    "expression": {
      "additionalProperties": true,
      "type": "object",
      "title": "Expression"
    }
  },
  "type": "object",
  "required": [
    "face_id",
    "bbox",
    "bbox_normalized",
    "detection_confidence",
    "crop"
  ],
  "title": "FaceRecord"
}
```

<a id="model-facerequestoptions"></a>

### FaceRequestOptions

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `mode` | não | string | default="expressions"; enum=["detection", "expressions"] |  |
| `max_faces` | não | integer | default=5; minimum=1.0; maximum=10.0 |  |
| `min_detection_confidence` | não | number | default=0.5; minimum=0.0; maximum=1.0 |  |
| `min_suppression_threshold` | não | number | default=0.3; minimum=0.0; maximum=1.0 |  |
| `min_face_presence_confidence` | não | number | default=0.5; minimum=0.0; maximum=1.0 |  |
| `min_expression_score` | não | number | default=0.5; minimum=0.0; maximum=1.0 |  |
| `deadline_seconds` | não | integer | default=300; minimum=1.0; maximum=300.0 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "mode": {
      "type": "string",
      "enum": [
        "detection",
        "expressions"
      ],
      "title": "Mode",
      "default": "expressions"
    },
    "max_faces": {
      "type": "integer",
      "maximum": 10.0,
      "minimum": 1.0,
      "title": "Max Faces",
      "default": 5
    },
    "min_detection_confidence": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Min Detection Confidence",
      "default": 0.5
    },
    "min_suppression_threshold": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Min Suppression Threshold",
      "default": 0.3
    },
    "min_face_presence_confidence": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Min Face Presence Confidence",
      "default": 0.5
    },
    "min_expression_score": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Min Expression Score",
      "default": 0.5
    },
    "deadline_seconds": {
      "type": "integer",
      "maximum": 300.0,
      "minimum": 1.0,
      "title": "Deadline Seconds",
      "default": 300
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "FaceRequestOptions"
}
```

<a id="model-facestepresult"></a>

### FaceStepResult

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `kind` | não | string | default="face"; const="face" |  |
| `step_id` | sim | string |  |  |
| `operation` | sim | string | enum=["face_detection", "face_movements", "face_expression_classification"] |  |
| `face_id` | não | string / null |  |  |
| `input` | não | object | additionalProperties=true |  |
| `status` | sim | string | enum=["pending", "running", "succeeded", "failed", "skipped", "not_applicable"] |  |
| `reason_code` | não | string / null |  |  |
| `output` | não | object | additionalProperties=true |  |
| `attempts` | não | integer | default=0 |  |
| `duration_ms` | não | integer | default=0 |  |
| `truncated` | não | boolean | default=false |  |

Esquema JSON completo:

```json
{
  "properties": {
    "kind": {
      "type": "string",
      "const": "face",
      "title": "Kind",
      "default": "face"
    },
    "step_id": {
      "type": "string",
      "title": "Step Id"
    },
    "operation": {
      "type": "string",
      "enum": [
        "face_detection",
        "face_movements",
        "face_expression_classification"
      ],
      "title": "Operation"
    },
    "face_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Face Id"
    },
    "input": {
      "additionalProperties": true,
      "type": "object",
      "title": "Input"
    },
    "status": {
      "type": "string",
      "enum": [
        "pending",
        "running",
        "succeeded",
        "failed",
        "skipped",
        "not_applicable"
      ],
      "title": "Status"
    },
    "reason_code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason Code"
    },
    "output": {
      "additionalProperties": true,
      "type": "object",
      "title": "Output"
    },
    "attempts": {
      "type": "integer",
      "title": "Attempts",
      "default": 0
    },
    "duration_ms": {
      "type": "integer",
      "title": "Duration Ms",
      "default": 0
    },
    "truncated": {
      "type": "boolean",
      "title": "Truncated",
      "default": false
    }
  },
  "type": "object",
  "required": [
    "step_id",
    "operation",
    "status"
  ],
  "title": "FaceStepResult"
}
```

<a id="model-facialblock"></a>

### FacialBlock

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `detection` | sim | object | additionalProperties=true |  |
| `faces` | não | array de [FaceRecord](#model-facerecord) |  |  |
| `models` | não | array de [FaceModelInfo](#model-facemodelinfo) |  |  |
| `request` | sim | object | additionalProperties=true |  |
| `coverage` | sim | object | additionalProperties=true |  |
| `steps` | sim | array de [FaceStepResult](#model-facestepresult) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "detection": {
      "additionalProperties": true,
      "type": "object",
      "title": "Detection"
    },
    "faces": {
      "items": {
        "$ref": "#/components/schemas/FaceRecord"
      },
      "type": "array",
      "title": "Faces"
    },
    "models": {
      "items": {
        "$ref": "#/components/schemas/FaceModelInfo"
      },
      "type": "array",
      "title": "Models"
    },
    "request": {
      "additionalProperties": true,
      "type": "object",
      "title": "Request"
    },
    "coverage": {
      "additionalProperties": true,
      "type": "object",
      "title": "Coverage"
    },
    "steps": {
      "items": {
        "$ref": "#/components/schemas/FaceStepResult"
      },
      "type": "array",
      "title": "Steps"
    }
  },
  "type": "object",
  "required": [
    "detection",
    "request",
    "coverage",
    "steps"
  ],
  "title": "FacialBlock"
}
```

<a id="model-florencev2stepresult"></a>

### FlorenceV2StepResult

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `step_id` | sim | string |  |  |
| `task` | sim | string | enum=["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>", "<OCR>", "<OCR_WITH_REGION>", "<OD>", "<DENSE_REGION_CAPTION>", "<REGION_PROPOSAL>", "<CAPTION_TO_PHRASE_GROUNDING>", "<REFERRING_EXPRESSION_SEGMENTATION>", "<REGION_TO_SEGMENTATION>", "<OPEN_VOCABULARY_DETECTION>", "<REGION_TO_CATEGORY>", "<REGION_TO_DESCRIPTION>", "<REGION_TO_OCR>"] |  |
| `input` | não | object | additionalProperties=true |  |
| `status` | sim | string | enum=["pending", "running", "succeeded", "failed", "skipped", "not_applicable"] |  |
| `reason_code` | não | string / null |  |  |
| `text` | não | string | default="" |  |
| `output` | não | object / string | default="" |  |
| `regions` | não | array de [ImageRegion](#model-imageregion) |  |  |
| `lines` | não | array de [OcrLine](#model-ocrline) |  |  |
| `duration_ms` | não | integer | default=0 |  |
| `truncated` | não | boolean | default=false |  |
| `generation_metadata` | não | object | additionalProperties=true |  |
| `attempts` | não | integer | default=0 |  |
| `kind` | não | string | default="florence"; const="florence" |  |

Esquema JSON completo:

```json
{
  "properties": {
    "step_id": {
      "type": "string",
      "title": "Step Id"
    },
    "task": {
      "type": "string",
      "enum": [
        "<CAPTION>",
        "<DETAILED_CAPTION>",
        "<MORE_DETAILED_CAPTION>",
        "<OCR>",
        "<OCR_WITH_REGION>",
        "<OD>",
        "<DENSE_REGION_CAPTION>",
        "<REGION_PROPOSAL>",
        "<CAPTION_TO_PHRASE_GROUNDING>",
        "<REFERRING_EXPRESSION_SEGMENTATION>",
        "<REGION_TO_SEGMENTATION>",
        "<OPEN_VOCABULARY_DETECTION>",
        "<REGION_TO_CATEGORY>",
        "<REGION_TO_DESCRIPTION>",
        "<REGION_TO_OCR>"
      ],
      "title": "Task"
    },
    "input": {
      "additionalProperties": true,
      "type": "object",
      "title": "Input"
    },
    "status": {
      "type": "string",
      "enum": [
        "pending",
        "running",
        "succeeded",
        "failed",
        "skipped",
        "not_applicable"
      ],
      "title": "Status"
    },
    "reason_code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason Code"
    },
    "text": {
      "type": "string",
      "title": "Text",
      "default": ""
    },
    "output": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "string"
        }
      ],
      "title": "Output",
      "default": ""
    },
    "regions": {
      "items": {
        "$ref": "#/components/schemas/ImageRegion"
      },
      "type": "array",
      "title": "Regions"
    },
    "lines": {
      "items": {
        "$ref": "#/components/schemas/OcrLine"
      },
      "type": "array",
      "title": "Lines"
    },
    "duration_ms": {
      "type": "integer",
      "title": "Duration Ms",
      "default": 0
    },
    "truncated": {
      "type": "boolean",
      "title": "Truncated",
      "default": false
    },
    "generation_metadata": {
      "additionalProperties": true,
      "type": "object",
      "title": "Generation Metadata"
    },
    "attempts": {
      "type": "integer",
      "title": "Attempts",
      "default": 0
    },
    "kind": {
      "type": "string",
      "const": "florence",
      "title": "Kind",
      "default": "florence"
    }
  },
  "type": "object",
  "required": [
    "step_id",
    "task",
    "status"
  ],
  "title": "FlorenceV2StepResult"
}
```

<a id="model-folderref"></a>

### FolderRef

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string |  |  |
| `name` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name"
  ],
  "title": "FolderRef"
}
```

<a id="model-fullfaceoptions"></a>

### FullFaceOptions

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `mode` | não | string | default="expressions"; const="expressions" |  |
| `max_faces` | não | integer | default=5; minimum=1.0; maximum=5.0 |  |
| `min_detection_confidence` | não | number | default=0.5; minimum=0.0; maximum=1.0 |  |
| `min_suppression_threshold` | não | number | default=0.3; minimum=0.0; maximum=1.0 |  |
| `min_face_presence_confidence` | não | number | default=0.5; minimum=0.0; maximum=1.0 |  |
| `min_expression_score` | não | number | default=0.5; minimum=0.0; maximum=1.0 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "mode": {
      "type": "string",
      "const": "expressions",
      "title": "Mode",
      "default": "expressions"
    },
    "max_faces": {
      "type": "integer",
      "maximum": 5.0,
      "minimum": 1.0,
      "title": "Max Faces",
      "default": 5
    },
    "min_detection_confidence": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Min Detection Confidence",
      "default": 0.5
    },
    "min_suppression_threshold": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Min Suppression Threshold",
      "default": 0.3
    },
    "min_face_presence_confidence": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Min Face Presence Confidence",
      "default": 0.5
    },
    "min_expression_score": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Min Expression Score",
      "default": 0.5
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "FullFaceOptions"
}
```

<a id="model-gpusupdate"></a>

### GpusUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `gpus` | sim | array de [LocalGpu](#model-localgpu) |  |  |
| `version` | não | integer / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "gpus": {
      "items": {
        "$ref": "#/components/schemas/LocalGpu"
      },
      "type": "array",
      "title": "Gpus"
    },
    "version": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Version"
    }
  },
  "type": "object",
  "required": [
    "gpus"
  ],
  "title": "GpusUpdate"
}
```

<a id="model-grantcreate"></a>

### GrantCreate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `user_id` | sim | string |  |  |
| `role` | sim | string |  |  |
| `policy_revision_id` | sim | string |  |  |
| `permissions` | não | array de string / null |  |  |
| `expires_at` | sim | string (date-time) |  |  |
| `delegation` | não | [Delegation](#model-delegation) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "user_id": {
      "type": "string",
      "title": "User Id"
    },
    "role": {
      "type": "string",
      "title": "Role"
    },
    "policy_revision_id": {
      "type": "string",
      "title": "Policy Revision Id"
    },
    "permissions": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array",
          "maxItems": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Permissions"
    },
    "expires_at": {
      "type": "string",
      "format": "date-time",
      "title": "Expires At"
    },
    "delegation": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/Delegation"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "user_id",
    "role",
    "policy_revision_id",
    "expires_at"
  ],
  "title": "GrantCreate"
}
```

<a id="model-httpvalidationerror"></a>

### HTTPValidationError

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `detail` | não | array de [ValidationError](#model-validationerror) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "detail": {
      "items": {
        "$ref": "#/components/schemas/ValidationError"
      },
      "type": "array",
      "title": "Detail"
    }
  },
  "type": "object",
  "title": "HTTPValidationError"
}
```

<a id="model-healthcheckresponse"></a>

### HealthCheckResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `status` | sim | string | enum=["healthy", "degraded", "unhealthy"] |  |
| `version` | não | string | default="1.0.0" |  |
| `redis` | sim | boolean |  |  |
| `workers` | sim | object | additionalProperties=true |  |
| `timestamp` | sim | string (date-time) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "status": {
      "type": "string",
      "enum": [
        "healthy",
        "degraded",
        "unhealthy"
      ],
      "title": "Status"
    },
    "version": {
      "type": "string",
      "title": "Version",
      "default": "1.0.0"
    },
    "redis": {
      "type": "boolean",
      "title": "Redis"
    },
    "workers": {
      "additionalProperties": true,
      "type": "object",
      "title": "Workers"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "title": "Timestamp"
    }
  },
  "type": "object",
  "required": [
    "status",
    "redis",
    "workers",
    "timestamp"
  ],
  "title": "HealthCheckResponse"
}
```

<a id="model-hostevent"></a>

### HostEvent

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `generation` | sim | integer |  |  |
| `stage` | sim | string |  |  |
| `message` | sim | string | maxLength=8192 |  |
| `effect` | não | boolean | default=false |  |

Esquema JSON completo:

```json
{
  "properties": {
    "generation": {
      "type": "integer",
      "title": "Generation"
    },
    "stage": {
      "type": "string",
      "title": "Stage"
    },
    "message": {
      "type": "string",
      "maxLength": 8192,
      "title": "Message"
    },
    "effect": {
      "type": "boolean",
      "title": "Effect",
      "default": false
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "generation",
    "stage",
    "message"
  ],
  "title": "HostEvent"
}
```

<a id="model-hostheartbeat"></a>

### HostHeartbeat

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `inventory` | sim | object | additionalProperties=true |  |

Esquema JSON completo:

```json
{
  "properties": {
    "inventory": {
      "additionalProperties": true,
      "type": "object",
      "title": "Inventory"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "inventory"
  ],
  "title": "HostHeartbeat"
}
```

<a id="model-hostresult"></a>

### HostResult

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `generation` | sim | integer |  |  |
| `ok` | sim | boolean |  |  |
| `observed` | não | object | additionalProperties=true |  |
| `code` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "generation": {
      "type": "integer",
      "title": "Generation"
    },
    "ok": {
      "type": "boolean",
      "title": "Ok"
    },
    "observed": {
      "additionalProperties": true,
      "type": "object",
      "title": "Observed"
    },
    "code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Code"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "generation",
    "ok"
  ],
  "title": "HostResult"
}
```

<a id="model-imageanalyzeoptions"></a>

### ImageAnalyzeOptions

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `task` | não | string | default="<MORE_DETAILED_CAPTION>"; enum=["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>", "<OCR>", "<OCR_WITH_REGION>", "<OD>", "<DENSE_REGION_CAPTION>", "<REGION_PROPOSAL>", "<CAPTION_TO_PHRASE_GROUNDING>", "<REFERRING_EXPRESSION_SEGMENTATION>", "<REGION_TO_SEGMENTATION>", "<OPEN_VOCABULARY_DETECTION>", "<REGION_TO_CATEGORY>", "<REGION_TO_DESCRIPTION>", "<REGION_TO_OCR>"] |  |
| `text_input` | não | string / null | default=null | Frase/descrição/objetos nas tarefas que recebem texto. |
| `region` | não | array de number / null | default=null | Região normalizada [x_min,y_min,x_max,y_max], valores entre 0 e 1. |
| `generation` | não | [VisionGenerationOptions](#model-visiongenerationoptions) |  |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "task": {
      "default": "<MORE_DETAILED_CAPTION>",
      "enum": [
        "<CAPTION>",
        "<DETAILED_CAPTION>",
        "<MORE_DETAILED_CAPTION>",
        "<OCR>",
        "<OCR_WITH_REGION>",
        "<OD>",
        "<DENSE_REGION_CAPTION>",
        "<REGION_PROPOSAL>",
        "<CAPTION_TO_PHRASE_GROUNDING>",
        "<REFERRING_EXPRESSION_SEGMENTATION>",
        "<REGION_TO_SEGMENTATION>",
        "<OPEN_VOCABULARY_DETECTION>",
        "<REGION_TO_CATEGORY>",
        "<REGION_TO_DESCRIPTION>",
        "<REGION_TO_OCR>"
      ],
      "title": "Task",
      "type": "string",
      "x-task-catalog": [
        {
          "input": "none",
          "label": "Descrição breve",
          "output": "text",
          "task": "<CAPTION>"
        },
        {
          "input": "none",
          "label": "Descrição detalhada",
          "output": "text",
          "task": "<DETAILED_CAPTION>"
        },
        {
          "input": "none",
          "label": "Descrição muito detalhada",
          "output": "text",
          "task": "<MORE_DETAILED_CAPTION>"
        },
        {
          "input": "none",
          "label": "Extrair texto",
          "output": "text",
          "task": "<OCR>"
        },
        {
          "input": "none",
          "label": "Extrair texto com regiões",
          "output": "ocr",
          "task": "<OCR_WITH_REGION>"
        },
        {
          "input": "none",
          "label": "Detectar objetos",
          "output": "boxes",
          "task": "<OD>"
        },
        {
          "input": "none",
          "label": "Descrever regiões",
          "output": "boxes",
          "task": "<DENSE_REGION_CAPTION>"
        },
        {
          "input": "none",
          "label": "Propor regiões",
          "output": "boxes",
          "task": "<REGION_PROPOSAL>"
        },
        {
          "input": "text",
          "label": "Localizar frases na imagem",
          "output": "boxes",
          "task": "<CAPTION_TO_PHRASE_GROUNDING>"
        },
        {
          "input": "text",
          "label": "Segmentar por descrição",
          "output": "polygons",
          "task": "<REFERRING_EXPRESSION_SEGMENTATION>"
        },
        {
          "input": "region",
          "label": "Segmentar uma região",
          "output": "polygons",
          "task": "<REGION_TO_SEGMENTATION>"
        },
        {
          "input": "text",
          "label": "Detectar objetos por texto",
          "output": "mixed",
          "task": "<OPEN_VOCABULARY_DETECTION>"
        },
        {
          "input": "region",
          "label": "Classificar uma região",
          "output": "text",
          "task": "<REGION_TO_CATEGORY>"
        },
        {
          "input": "region",
          "label": "Descrever uma região",
          "output": "text",
          "task": "<REGION_TO_DESCRIPTION>"
        },
        {
          "input": "region",
          "label": "Extrair texto de uma região",
          "output": "text",
          "task": "<REGION_TO_OCR>"
        }
      ]
    },
    "text_input": {
      "anyOf": [
        {
          "maxLength": 2000,
          "minLength": 1,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Frase/descrição/objetos nas tarefas que recebem texto.",
      "title": "Text Input"
    },
    "region": {
      "anyOf": [
        {
          "items": {
            "type": "number"
          },
          "maxItems": 4,
          "minItems": 4,
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Região normalizada [x_min,y_min,x_max,y_max], valores entre 0 e 1.",
      "title": "Region"
    },
    "generation": {
      "$ref": "#/components/schemas/VisionGenerationOptions"
    }
  },
  "title": "ImageAnalyzeOptions",
  "type": "object"
}
```

<a id="model-imageanalyzerequest"></a>

### ImageAnalyzeRequest

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `task` | não | string | default="<MORE_DETAILED_CAPTION>"; enum=["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>", "<OCR>", "<OCR_WITH_REGION>", "<OD>", "<DENSE_REGION_CAPTION>", "<REGION_PROPOSAL>", "<CAPTION_TO_PHRASE_GROUNDING>", "<REFERRING_EXPRESSION_SEGMENTATION>", "<REGION_TO_SEGMENTATION>", "<OPEN_VOCABULARY_DETECTION>", "<REGION_TO_CATEGORY>", "<REGION_TO_DESCRIPTION>", "<REGION_TO_OCR>"] |  |
| `text_input` | não | string / null |  | Frase/descrição/objetos nas tarefas que recebem texto. |
| `region` | não | array de number / null |  | Região normalizada [x_min,y_min,x_max,y_max], valores entre 0 e 1. |
| `generation` | não | [VisionGenerationOptions](#model-visiongenerationoptions) |  |  |
| `image_base64` | sim | string |  | Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF. |
| `tags` | não | array de string / null |  | Tags do job (ex.: ["cliente-x", "nf"]). Viram minúsculas; até 20 de até 50 caracteres. |
| `filename` | não | string / null |  | Nome de identificação opcional. |
| `project` | não | string / null |  | Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a `project`). |
| `folder` | não | string / null |  | Nome da pasta no projeto (opcional, get-or-add, sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. mode=single com wait=true: a resposta ainda ecoa `image_base64` no topo (vem dos bytes desta requisição, não de uma cópia guardada). mode=full: a resposta (wait=true) e o relatório trazem `image.image_base64` null, e `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada. |
| `mode` | não | string | default="single"; const="single" |  |
| `wait` | não | boolean | default=false | false cria um job e retorna 202; true espera pelo resultado (sujeito ao timeout de visão). |

Esquema JSON completo:

```json
{
  "properties": {
    "task": {
      "type": "string",
      "enum": [
        "<CAPTION>",
        "<DETAILED_CAPTION>",
        "<MORE_DETAILED_CAPTION>",
        "<OCR>",
        "<OCR_WITH_REGION>",
        "<OD>",
        "<DENSE_REGION_CAPTION>",
        "<REGION_PROPOSAL>",
        "<CAPTION_TO_PHRASE_GROUNDING>",
        "<REFERRING_EXPRESSION_SEGMENTATION>",
        "<REGION_TO_SEGMENTATION>",
        "<OPEN_VOCABULARY_DETECTION>",
        "<REGION_TO_CATEGORY>",
        "<REGION_TO_DESCRIPTION>",
        "<REGION_TO_OCR>"
      ],
      "title": "Task",
      "default": "<MORE_DETAILED_CAPTION>",
      "x-task-catalog": [
        {
          "input": "none",
          "label": "Descrição breve",
          "output": "text",
          "task": "<CAPTION>"
        },
        {
          "input": "none",
          "label": "Descrição detalhada",
          "output": "text",
          "task": "<DETAILED_CAPTION>"
        },
        {
          "input": "none",
          "label": "Descrição muito detalhada",
          "output": "text",
          "task": "<MORE_DETAILED_CAPTION>"
        },
        {
          "input": "none",
          "label": "Extrair texto",
          "output": "text",
          "task": "<OCR>"
        },
        {
          "input": "none",
          "label": "Extrair texto com regiões",
          "output": "ocr",
          "task": "<OCR_WITH_REGION>"
        },
        {
          "input": "none",
          "label": "Detectar objetos",
          "output": "boxes",
          "task": "<OD>"
        },
        {
          "input": "none",
          "label": "Descrever regiões",
          "output": "boxes",
          "task": "<DENSE_REGION_CAPTION>"
        },
        {
          "input": "none",
          "label": "Propor regiões",
          "output": "boxes",
          "task": "<REGION_PROPOSAL>"
        },
        {
          "input": "text",
          "label": "Localizar frases na imagem",
          "output": "boxes",
          "task": "<CAPTION_TO_PHRASE_GROUNDING>"
        },
        {
          "input": "text",
          "label": "Segmentar por descrição",
          "output": "polygons",
          "task": "<REFERRING_EXPRESSION_SEGMENTATION>"
        },
        {
          "input": "region",
          "label": "Segmentar uma região",
          "output": "polygons",
          "task": "<REGION_TO_SEGMENTATION>"
        },
        {
          "input": "text",
          "label": "Detectar objetos por texto",
          "output": "mixed",
          "task": "<OPEN_VOCABULARY_DETECTION>"
        },
        {
          "input": "region",
          "label": "Classificar uma região",
          "output": "text",
          "task": "<REGION_TO_CATEGORY>"
        },
        {
          "input": "region",
          "label": "Descrever uma região",
          "output": "text",
          "task": "<REGION_TO_DESCRIPTION>"
        },
        {
          "input": "region",
          "label": "Extrair texto de uma região",
          "output": "text",
          "task": "<REGION_TO_OCR>"
        }
      ]
    },
    "text_input": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 2000,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Text Input",
      "description": "Frase/descrição/objetos nas tarefas que recebem texto."
    },
    "region": {
      "anyOf": [
        {
          "items": {
            "type": "number"
          },
          "type": "array",
          "maxItems": 4,
          "minItems": 4
        },
        {
          "type": "null"
        }
      ],
      "title": "Region",
      "description": "Região normalizada [x_min,y_min,x_max,y_max], valores entre 0 e 1."
    },
    "generation": {
      "$ref": "#/components/schemas/VisionGenerationOptions"
    },
    "image_base64": {
      "type": "string",
      "title": "Image Base64",
      "description": "Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF."
    },
    "tags": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags do job (ex.: [\"cliente-x\", \"nf\"]). Viram minúsculas; até 20 de até 50 caracteres."
    },
    "filename": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Filename",
      "description": "Nome de identificação opcional."
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a `project`)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta no projeto (opcional, get-or-add, sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto."
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. mode=single com wait=true: a resposta ainda ecoa `image_base64` no topo (vem dos bytes desta requisição, não de uma cópia guardada). mode=full: a resposta (wait=true) e o relatório trazem `image.image_base64` null, e `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada.",
      "default": false
    },
    "mode": {
      "type": "string",
      "const": "single",
      "title": "Mode",
      "default": "single"
    },
    "wait": {
      "type": "boolean",
      "title": "Wait",
      "description": "false cria um job e retorna 202; true espera pelo resultado (sujeito ao timeout de visão).",
      "default": false
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "image_base64"
  ],
  "title": "ImageAnalyzeRequest"
}
```

<a id="model-imageanalyzeresponse"></a>

### ImageAnalyzeResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string |  |  |
| `status` | sim | string | const="completed" |  |
| `image_base64` | sim | string |  |  |
| `image_mime_type` | sim | string |  |  |
| `image_bytes` | sim | integer |  |  |
| `image_sha256` | sim | string |  |  |
| `width` | sim | integer |  |  |
| `height` | sim | integer |  |  |
| `model` | sim | [VisionModelInfo](#model-visionmodelinfo) |  |  |
| `duration_ms` | sim | integer |  |  |
| `project` | não | [UploadProjectInfo](#model-uploadprojectinfo) / null |  |  |
| `folder` | não | [UploadFolderInfo](#model-uploadfolderinfo) / null |  |  |
| `task` | sim | string | enum=["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>", "<OCR>", "<OCR_WITH_REGION>", "<OD>", "<DENSE_REGION_CAPTION>", "<REGION_PROPOSAL>", "<CAPTION_TO_PHRASE_GROUNDING>", "<REFERRING_EXPRESSION_SEGMENTATION>", "<REGION_TO_SEGMENTATION>", "<OPEN_VOCABULARY_DETECTION>", "<REGION_TO_CATEGORY>", "<REGION_TO_DESCRIPTION>", "<REGION_TO_OCR>"] |  |
| `text` | sim | string |  |  |
| `output` | sim | object / string |  |  |
| `regions` | sim | array de [ImageRegion](#model-imageregion) |  |  |
| `request` | sim | [ImageAnalyzeOptions](#model-imageanalyzeoptions) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "title": "Job Id"
    },
    "status": {
      "type": "string",
      "const": "completed",
      "title": "Status"
    },
    "image_base64": {
      "type": "string",
      "title": "Image Base64"
    },
    "image_mime_type": {
      "type": "string",
      "title": "Image Mime Type"
    },
    "image_bytes": {
      "type": "integer",
      "title": "Image Bytes"
    },
    "image_sha256": {
      "type": "string",
      "title": "Image Sha256"
    },
    "width": {
      "type": "integer",
      "title": "Width"
    },
    "height": {
      "type": "integer",
      "title": "Height"
    },
    "model": {
      "$ref": "#/components/schemas/VisionModelInfo"
    },
    "duration_ms": {
      "type": "integer",
      "title": "Duration Ms"
    },
    "project": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/UploadProjectInfo"
        },
        {
          "type": "null"
        }
      ]
    },
    "folder": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/UploadFolderInfo"
        },
        {
          "type": "null"
        }
      ]
    },
    "task": {
      "type": "string",
      "enum": [
        "<CAPTION>",
        "<DETAILED_CAPTION>",
        "<MORE_DETAILED_CAPTION>",
        "<OCR>",
        "<OCR_WITH_REGION>",
        "<OD>",
        "<DENSE_REGION_CAPTION>",
        "<REGION_PROPOSAL>",
        "<CAPTION_TO_PHRASE_GROUNDING>",
        "<REFERRING_EXPRESSION_SEGMENTATION>",
        "<REGION_TO_SEGMENTATION>",
        "<OPEN_VOCABULARY_DETECTION>",
        "<REGION_TO_CATEGORY>",
        "<REGION_TO_DESCRIPTION>",
        "<REGION_TO_OCR>"
      ],
      "title": "Task"
    },
    "text": {
      "type": "string",
      "title": "Text"
    },
    "output": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "string"
        }
      ],
      "title": "Output"
    },
    "regions": {
      "items": {
        "$ref": "#/components/schemas/ImageRegion"
      },
      "type": "array",
      "title": "Regions"
    },
    "request": {
      "$ref": "#/components/schemas/ImageAnalyzeOptions"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "status",
    "image_base64",
    "image_mime_type",
    "image_bytes",
    "image_sha256",
    "width",
    "height",
    "model",
    "duration_ms",
    "task",
    "text",
    "output",
    "regions",
    "request"
  ],
  "title": "ImageAnalyzeResponse"
}
```

<a id="model-imagedescriberequest"></a>

### ImageDescribeRequest

Corpo JSON de `POST /images/describe`.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `image_base64` | sim | string |  | Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF. |
| `tags` | não | array de string / null |  | Tags do job (ex.: ["cliente-x", "nf"]). Viram minúsculas; até 20 de até 50 caracteres. |
| `filename` | não | string / null |  | Nome de identificação opcional (usado no job e no storage). |
| `project` | não | string / null |  | Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a `project`). |
| `folder` | não | string / null |  | Nome da pasta no projeto (opcional, get-or-add, sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada. |
| `task` | não | string | default="<MORE_DETAILED_CAPTION>"; enum=["<MORE_DETAILED_CAPTION>", "<DETAILED_CAPTION>", "<CAPTION>"] | Prompt de caption do Florence-2. |

Esquema JSON completo:

```json
{
  "properties": {
    "image_base64": {
      "type": "string",
      "title": "Image Base64",
      "description": "Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF."
    },
    "tags": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags do job (ex.: [\"cliente-x\", \"nf\"]). Viram minúsculas; até 20 de até 50 caracteres."
    },
    "filename": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Filename",
      "description": "Nome de identificação opcional (usado no job e no storage)."
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a `project`)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta no projeto (opcional, get-or-add, sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto."
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada.",
      "default": false
    },
    "task": {
      "type": "string",
      "enum": [
        "<MORE_DETAILED_CAPTION>",
        "<DETAILED_CAPTION>",
        "<CAPTION>"
      ],
      "title": "Task",
      "description": "Prompt de caption do Florence-2.",
      "default": "<MORE_DETAILED_CAPTION>"
    }
  },
  "type": "object",
  "required": [
    "image_base64"
  ],
  "title": "ImageDescribeRequest",
  "description": "Corpo JSON de `POST /images/describe`."
}
```

<a id="model-imagedescriberesponse"></a>

### ImageDescribeResponse

Resposta de `POST /images/describe` e `/images/describe/upload`.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string |  |  |
| `status` | sim | string | const="completed" |  |
| `image_base64` | sim | string |  |  |
| `image_mime_type` | sim | string |  |  |
| `image_bytes` | sim | integer |  |  |
| `image_sha256` | sim | string |  |  |
| `width` | sim | integer |  |  |
| `height` | sim | integer |  |  |
| `model` | sim | [VisionModelInfo](#model-visionmodelinfo) |  |  |
| `duration_ms` | sim | integer |  |  |
| `project` | não | [UploadProjectInfo](#model-uploadprojectinfo) / null |  |  |
| `folder` | não | [UploadFolderInfo](#model-uploadfolderinfo) / null |  |  |
| `description` | sim | string |  |  |
| `task` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "title": "Job Id"
    },
    "status": {
      "type": "string",
      "const": "completed",
      "title": "Status"
    },
    "image_base64": {
      "type": "string",
      "title": "Image Base64"
    },
    "image_mime_type": {
      "type": "string",
      "title": "Image Mime Type"
    },
    "image_bytes": {
      "type": "integer",
      "title": "Image Bytes"
    },
    "image_sha256": {
      "type": "string",
      "title": "Image Sha256"
    },
    "width": {
      "type": "integer",
      "title": "Width"
    },
    "height": {
      "type": "integer",
      "title": "Height"
    },
    "model": {
      "$ref": "#/components/schemas/VisionModelInfo"
    },
    "duration_ms": {
      "type": "integer",
      "title": "Duration Ms"
    },
    "project": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/UploadProjectInfo"
        },
        {
          "type": "null"
        }
      ]
    },
    "folder": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/UploadFolderInfo"
        },
        {
          "type": "null"
        }
      ]
    },
    "description": {
      "type": "string",
      "title": "Description"
    },
    "task": {
      "type": "string",
      "title": "Task"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "status",
    "image_base64",
    "image_mime_type",
    "image_bytes",
    "image_sha256",
    "width",
    "height",
    "model",
    "duration_ms",
    "description",
    "task"
  ],
  "title": "ImageDescribeResponse",
  "description": "Resposta de `POST /images/describe` e `/images/describe/upload`."
}
```

<a id="model-imagefullanalysisresult"></a>

### ImageFullAnalysisResult

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `operation` | sim | string | const="full_analysis" |  |
| `schema_version` | não | string | default="image-full-result-v1"; const="image-full-result-v1" |  |
| `profile` | não | string | default="image-full-v1"; const="image-full-v1" |  |
| `analysis_status` | sim | string | enum=["completed", "partial", "failed", "cancelled"] |  |
| `task` | não | string | default="full" |  |
| `task_label` | não | string | default="Full Analysis" |  |
| `image_base64` | não | string / null |  |  |
| `image_mime_type` | não | string | default="image/png" |  |
| `width` | sim | integer |  |  |
| `height` | sim | integer |  |  |
| `model` | sim | [VisionModelInfo](#model-visionmodelinfo) |  |  |
| `duration_ms` | sim | integer |  |  |
| `description` | não | string | default="" |  |
| `text` | não | string | default="" |  |
| `lines` | não | array de [OcrLine](#model-ocrline) |  |  |
| `regions` | não | array de [ImageRegion](#model-imageregion) |  |  |
| `request` | não | object / null |  |  |
| `coverage` | sim | object | additionalProperties=true |  |
| `resolved_inputs` | não | object | additionalProperties=true |  |
| `results` | sim | array de [ImageFullStepResult](#model-imagefullstepresult) |  |  |
| `calls_started` | não | integer | default=0 |  |
| `reason_code` | não | string / null |  |  |
| `source_sha256` | não | string | default="" |  |
| `frame_policy` | não | string | default="first_frame" |  |

Esquema JSON completo:

```json
{
  "properties": {
    "operation": {
      "type": "string",
      "const": "full_analysis",
      "title": "Operation"
    },
    "schema_version": {
      "type": "string",
      "const": "image-full-result-v1",
      "title": "Schema Version",
      "default": "image-full-result-v1"
    },
    "profile": {
      "type": "string",
      "const": "image-full-v1",
      "title": "Profile",
      "default": "image-full-v1"
    },
    "analysis_status": {
      "type": "string",
      "enum": [
        "completed",
        "partial",
        "failed",
        "cancelled"
      ],
      "title": "Analysis Status"
    },
    "task": {
      "type": "string",
      "title": "Task",
      "default": "full"
    },
    "task_label": {
      "type": "string",
      "title": "Task Label",
      "default": "Full Analysis"
    },
    "image_base64": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Image Base64"
    },
    "image_mime_type": {
      "type": "string",
      "title": "Image Mime Type",
      "default": "image/png"
    },
    "width": {
      "type": "integer",
      "title": "Width"
    },
    "height": {
      "type": "integer",
      "title": "Height"
    },
    "model": {
      "$ref": "#/components/schemas/VisionModelInfo"
    },
    "duration_ms": {
      "type": "integer",
      "title": "Duration Ms"
    },
    "description": {
      "type": "string",
      "title": "Description",
      "default": ""
    },
    "text": {
      "type": "string",
      "title": "Text",
      "default": ""
    },
    "lines": {
      "items": {
        "$ref": "#/components/schemas/OcrLine"
      },
      "type": "array",
      "title": "Lines"
    },
    "regions": {
      "items": {
        "$ref": "#/components/schemas/ImageRegion"
      },
      "type": "array",
      "title": "Regions"
    },
    "request": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Request"
    },
    "coverage": {
      "additionalProperties": true,
      "type": "object",
      "title": "Coverage"
    },
    "resolved_inputs": {
      "additionalProperties": true,
      "type": "object",
      "title": "Resolved Inputs"
    },
    "results": {
      "items": {
        "$ref": "#/components/schemas/ImageFullStepResult"
      },
      "type": "array",
      "title": "Results"
    },
    "calls_started": {
      "type": "integer",
      "title": "Calls Started",
      "default": 0
    },
    "reason_code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason Code"
    },
    "source_sha256": {
      "type": "string",
      "title": "Source Sha256",
      "default": ""
    },
    "frame_policy": {
      "type": "string",
      "title": "Frame Policy",
      "default": "first_frame"
    }
  },
  "type": "object",
  "required": [
    "operation",
    "analysis_status",
    "width",
    "height",
    "model",
    "duration_ms",
    "coverage",
    "results"
  ],
  "title": "ImageFullAnalysisResult"
}
```

<a id="model-imagefullanalyzerequest"></a>

### ImageFullAnalyzeRequest

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `image_base64` | sim | string |  | Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF. |
| `tags` | não | array de string / null |  | Tags do job (ex.: ["cliente-x", "nf"]). Viram minúsculas; até 20 de até 50 caracteres. |
| `filename` | não | string / null |  | Nome de identificação opcional. |
| `project` | não | string / null |  | Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a `project`). |
| `folder` | não | string / null |  | Nome da pasta no projeto (opcional, get-or-add, sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. mode=single com wait=true: a resposta ainda ecoa `image_base64` no topo (vem dos bytes desta requisição, não de uma cópia guardada). mode=full: a resposta (wait=true) e o relatório trazem `image.image_base64` null, e `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada. |
| `mode` | sim | string | const="full" |  |
| `full_options` | não | [ImageFullOptions](#model-imagefulloptions) |  |  |
| `wait` | não | boolean | default=false |  |
| `datalake` | não | [Destination](#model-destination) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "image_base64": {
      "type": "string",
      "title": "Image Base64",
      "description": "Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF."
    },
    "tags": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags do job (ex.: [\"cliente-x\", \"nf\"]). Viram minúsculas; até 20 de até 50 caracteres."
    },
    "filename": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Filename",
      "description": "Nome de identificação opcional."
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a `project`)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta no projeto (opcional, get-or-add, sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto."
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. mode=single com wait=true: a resposta ainda ecoa `image_base64` no topo (vem dos bytes desta requisição, não de uma cópia guardada). mode=full: a resposta (wait=true) e o relatório trazem `image.image_base64` null, e `purge_source` não faz parte da Idempotency-Key: repetir a chave com outro purge_source devolve a tentativa existente, sem mudar nada.",
      "default": false
    },
    "mode": {
      "type": "string",
      "const": "full",
      "title": "Mode"
    },
    "full_options": {
      "$ref": "#/components/schemas/ImageFullOptions"
    },
    "wait": {
      "type": "boolean",
      "title": "Wait",
      "default": false
    },
    "datalake": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/Destination"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "image_base64",
    "mode"
  ],
  "title": "ImageFullAnalyzeRequest"
}
```

<a id="model-imagefullanalyzeresponse"></a>

### ImageFullAnalyzeResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string |  |  |
| `status` | sim | string |  |  |
| `markdown` | sim | string |  |  |
| `image` | sim | [ImageFullAnalysisResult](#model-imagefullanalysisresult) / [ImageFullV2Result](#model-imagefullv2result) |  |  |
| `attempt` | não | integer / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "title": "Job Id"
    },
    "status": {
      "type": "string",
      "title": "Status"
    },
    "markdown": {
      "type": "string",
      "title": "Markdown"
    },
    "image": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/ImageFullAnalysisResult"
        },
        {
          "$ref": "#/components/schemas/ImageFullV2Result"
        }
      ],
      "title": "Image"
    },
    "attempt": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Attempt"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "status",
    "markdown",
    "image"
  ],
  "title": "ImageFullAnalyzeResponse"
}
```

<a id="model-imagefulloptions"></a>

### ImageFullOptions

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `profile` | não | string | default="image-full-v1"; enum=["image-full-v1", "image-full-v2"] |  |
| `faces` | não | [FullFaceOptions](#model-fullfaceoptions) / null |  |  |
| `queries` | não | array de string / null |  |  |
| `regions` | não | array de array de number / null |  |  |
| `generation` | não | [VisionGenerationOptions](#model-visiongenerationoptions) |  |  |
| `deadline_seconds` | não | integer | default=900; minimum=1.0; maximum=900.0 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "profile": {
      "type": "string",
      "enum": [
        "image-full-v1",
        "image-full-v2"
      ],
      "title": "Profile",
      "default": "image-full-v1"
    },
    "faces": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/FullFaceOptions"
        },
        {
          "type": "null"
        }
      ]
    },
    "queries": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array",
          "maxItems": 3,
          "minItems": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Queries"
    },
    "regions": {
      "anyOf": [
        {
          "items": {
            "items": {
              "type": "number"
            },
            "type": "array"
          },
          "type": "array",
          "maxItems": 4,
          "minItems": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Regions"
    },
    "generation": {
      "$ref": "#/components/schemas/VisionGenerationOptions"
    },
    "deadline_seconds": {
      "type": "integer",
      "maximum": 900.0,
      "minimum": 1.0,
      "title": "Deadline Seconds",
      "default": 900
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "ImageFullOptions"
}
```

<a id="model-imagefullqueuedresponse"></a>

### ImageFullQueuedResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string (uuid) |  |  |
| `status` | sim | [JobStatus](#model-jobstatus) |  |  |
| `created_at` | sim | string (date-time) |  |  |
| `message` | sim | string |  |  |
| `project` | não | [UploadProjectInfo](#model-uploadprojectinfo) / null |  |  |
| `folder` | não | [UploadFolderInfo](#model-uploadfolderinfo) / null |  |  |
| `duplicate` | não | boolean | default=false |  |
| `source_available` | não | boolean / null |  |  |
| `poll_url` | sim | string |  |  |
| `result_url` | sim | string |  |  |
| `attempt` | não | integer | default=1 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "format": "uuid",
      "title": "Job Id"
    },
    "status": {
      "$ref": "#/components/schemas/JobStatus"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "message": {
      "type": "string",
      "title": "Message"
    },
    "project": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/UploadProjectInfo"
        },
        {
          "type": "null"
        }
      ]
    },
    "folder": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/UploadFolderInfo"
        },
        {
          "type": "null"
        }
      ]
    },
    "duplicate": {
      "type": "boolean",
      "title": "Duplicate",
      "default": false
    },
    "source_available": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Available"
    },
    "poll_url": {
      "type": "string",
      "title": "Poll Url"
    },
    "result_url": {
      "type": "string",
      "title": "Result Url"
    },
    "attempt": {
      "type": "integer",
      "title": "Attempt",
      "default": 1
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "status",
    "created_at",
    "message",
    "poll_url",
    "result_url"
  ],
  "title": "ImageFullQueuedResponse"
}
```

<a id="model-imagefullstepresult"></a>

### ImageFullStepResult

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `step_id` | sim | string |  |  |
| `task` | sim | string | enum=["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>", "<OCR>", "<OCR_WITH_REGION>", "<OD>", "<DENSE_REGION_CAPTION>", "<REGION_PROPOSAL>", "<CAPTION_TO_PHRASE_GROUNDING>", "<REFERRING_EXPRESSION_SEGMENTATION>", "<REGION_TO_SEGMENTATION>", "<OPEN_VOCABULARY_DETECTION>", "<REGION_TO_CATEGORY>", "<REGION_TO_DESCRIPTION>", "<REGION_TO_OCR>"] |  |
| `input` | não | object | additionalProperties=true |  |
| `status` | sim | string | enum=["pending", "running", "succeeded", "failed", "skipped", "not_applicable"] |  |
| `reason_code` | não | string / null |  |  |
| `text` | não | string | default="" |  |
| `output` | não | object / string | default="" |  |
| `regions` | não | array de [ImageRegion](#model-imageregion) |  |  |
| `lines` | não | array de [OcrLine](#model-ocrline) |  |  |
| `duration_ms` | não | integer | default=0 |  |
| `truncated` | não | boolean | default=false |  |
| `generation_metadata` | não | object | additionalProperties=true |  |
| `attempts` | não | integer | default=0 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "step_id": {
      "type": "string",
      "title": "Step Id"
    },
    "task": {
      "type": "string",
      "enum": [
        "<CAPTION>",
        "<DETAILED_CAPTION>",
        "<MORE_DETAILED_CAPTION>",
        "<OCR>",
        "<OCR_WITH_REGION>",
        "<OD>",
        "<DENSE_REGION_CAPTION>",
        "<REGION_PROPOSAL>",
        "<CAPTION_TO_PHRASE_GROUNDING>",
        "<REFERRING_EXPRESSION_SEGMENTATION>",
        "<REGION_TO_SEGMENTATION>",
        "<OPEN_VOCABULARY_DETECTION>",
        "<REGION_TO_CATEGORY>",
        "<REGION_TO_DESCRIPTION>",
        "<REGION_TO_OCR>"
      ],
      "title": "Task"
    },
    "input": {
      "additionalProperties": true,
      "type": "object",
      "title": "Input"
    },
    "status": {
      "type": "string",
      "enum": [
        "pending",
        "running",
        "succeeded",
        "failed",
        "skipped",
        "not_applicable"
      ],
      "title": "Status"
    },
    "reason_code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason Code"
    },
    "text": {
      "type": "string",
      "title": "Text",
      "default": ""
    },
    "output": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "string"
        }
      ],
      "title": "Output",
      "default": ""
    },
    "regions": {
      "items": {
        "$ref": "#/components/schemas/ImageRegion"
      },
      "type": "array",
      "title": "Regions"
    },
    "lines": {
      "items": {
        "$ref": "#/components/schemas/OcrLine"
      },
      "type": "array",
      "title": "Lines"
    },
    "duration_ms": {
      "type": "integer",
      "title": "Duration Ms",
      "default": 0
    },
    "truncated": {
      "type": "boolean",
      "title": "Truncated",
      "default": false
    },
    "generation_metadata": {
      "additionalProperties": true,
      "type": "object",
      "title": "Generation Metadata"
    },
    "attempts": {
      "type": "integer",
      "title": "Attempts",
      "default": 0
    }
  },
  "type": "object",
  "required": [
    "step_id",
    "task",
    "status"
  ],
  "title": "ImageFullStepResult"
}
```

<a id="model-imagefullv2result"></a>

### ImageFullV2Result

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `operation` | sim | string | const="full_analysis" |  |
| `schema_version` | não | string | default="image-full-result-v2"; const="image-full-result-v2" |  |
| `profile` | não | string | default="image-full-v2"; const="image-full-v2" |  |
| `analysis_status` | sim | string | enum=["completed", "partial", "failed", "cancelled"] |  |
| `task` | não | string | default="full" |  |
| `task_label` | não | string | default="Full Analysis" |  |
| `image_base64` | não | string / null |  |  |
| `image_mime_type` | não | string | default="image/png" |  |
| `width` | sim | integer |  |  |
| `height` | sim | integer |  |  |
| `model` | sim | [VisionModelInfo](#model-visionmodelinfo) |  |  |
| `duration_ms` | sim | integer |  |  |
| `description` | não | string | default="" |  |
| `text` | não | string | default="" |  |
| `lines` | não | array de [OcrLine](#model-ocrline) |  |  |
| `regions` | não | array de [ImageRegion](#model-imageregion) |  |  |
| `request` | não | object / null |  |  |
| `coverage` | sim | object | additionalProperties=true |  |
| `resolved_inputs` | não | object | additionalProperties=true |  |
| `results` | sim | array de [FlorenceV2StepResult](#model-florencev2stepresult) / [FaceStepResult](#model-facestepresult) |  |  |
| `calls_started` | não | integer | default=0 |  |
| `reason_code` | não | string / null |  |  |
| `source_sha256` | não | string | default="" |  |
| `frame_policy` | não | string | default="first_frame" |  |
| `models` | sim | array de [FaceModelInfo](#model-facemodelinfo) / object |  |  |
| `faces` | sim | [FacialBlock](#model-facialblock) |  |  |
| `calls_by_provider` | não | object | additionalProperties={"type": "integer"} |  |

Esquema JSON completo:

```json
{
  "properties": {
    "operation": {
      "type": "string",
      "const": "full_analysis",
      "title": "Operation"
    },
    "schema_version": {
      "type": "string",
      "const": "image-full-result-v2",
      "title": "Schema Version",
      "default": "image-full-result-v2"
    },
    "profile": {
      "type": "string",
      "const": "image-full-v2",
      "title": "Profile",
      "default": "image-full-v2"
    },
    "analysis_status": {
      "type": "string",
      "enum": [
        "completed",
        "partial",
        "failed",
        "cancelled"
      ],
      "title": "Analysis Status"
    },
    "task": {
      "type": "string",
      "title": "Task",
      "default": "full"
    },
    "task_label": {
      "type": "string",
      "title": "Task Label",
      "default": "Full Analysis"
    },
    "image_base64": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Image Base64"
    },
    "image_mime_type": {
      "type": "string",
      "title": "Image Mime Type",
      "default": "image/png"
    },
    "width": {
      "type": "integer",
      "title": "Width"
    },
    "height": {
      "type": "integer",
      "title": "Height"
    },
    "model": {
      "$ref": "#/components/schemas/VisionModelInfo"
    },
    "duration_ms": {
      "type": "integer",
      "title": "Duration Ms"
    },
    "description": {
      "type": "string",
      "title": "Description",
      "default": ""
    },
    "text": {
      "type": "string",
      "title": "Text",
      "default": ""
    },
    "lines": {
      "items": {
        "$ref": "#/components/schemas/OcrLine"
      },
      "type": "array",
      "title": "Lines"
    },
    "regions": {
      "items": {
        "$ref": "#/components/schemas/ImageRegion"
      },
      "type": "array",
      "title": "Regions"
    },
    "request": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Request"
    },
    "coverage": {
      "additionalProperties": true,
      "type": "object",
      "title": "Coverage"
    },
    "resolved_inputs": {
      "additionalProperties": true,
      "type": "object",
      "title": "Resolved Inputs"
    },
    "results": {
      "items": {
        "oneOf": [
          {
            "$ref": "#/components/schemas/FlorenceV2StepResult"
          },
          {
            "$ref": "#/components/schemas/FaceStepResult"
          }
        ],
        "discriminator": {
          "propertyName": "kind",
          "mapping": {
            "face": "#/components/schemas/FaceStepResult",
            "florence": "#/components/schemas/FlorenceV2StepResult"
          }
        }
      },
      "type": "array",
      "title": "Results"
    },
    "calls_started": {
      "type": "integer",
      "title": "Calls Started",
      "default": 0
    },
    "reason_code": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason Code"
    },
    "source_sha256": {
      "type": "string",
      "title": "Source Sha256",
      "default": ""
    },
    "frame_policy": {
      "type": "string",
      "title": "Frame Policy",
      "default": "first_frame"
    },
    "models": {
      "items": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/FaceModelInfo"
          },
          {
            "additionalProperties": true,
            "type": "object"
          }
        ]
      },
      "type": "array",
      "title": "Models"
    },
    "faces": {
      "$ref": "#/components/schemas/FacialBlock"
    },
    "calls_by_provider": {
      "additionalProperties": {
        "type": "integer"
      },
      "type": "object",
      "title": "Calls By Provider"
    }
  },
  "type": "object",
  "required": [
    "operation",
    "analysis_status",
    "width",
    "height",
    "model",
    "duration_ms",
    "coverage",
    "results",
    "models",
    "faces"
  ],
  "title": "ImageFullV2Result"
}
```

<a id="model-imagejobresult"></a>

### ImageJobResult

Persisted vision output, including the operation selected at upload.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `operation` | sim | string | enum=["describe", "ocr", "analyze"] |  |
| `task` | sim | string |  |  |
| `task_label` | não | string / null |  |  |
| `image_base64` | não | string / null |  |  |
| `image_mime_type` | não | string / null |  |  |
| `width` | sim | integer |  |  |
| `height` | sim | integer |  |  |
| `description` | não | string / null |  |  |
| `text` | não | string / null |  |  |
| `lines` | não | array de [OcrLine](#model-ocrline) | default=[] |  |
| `model` | sim | [VisionModelInfo](#model-visionmodelinfo) |  |  |
| `duration_ms` | sim | integer |  |  |
| `output` | não | object / string / null |  |  |
| `regions` | não | array de [ImageRegion](#model-imageregion) | default=[] |  |
| `request` | não | [ImageAnalyzeOptions](#model-imageanalyzeoptions) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "describe",
        "ocr",
        "analyze"
      ],
      "title": "Operation"
    },
    "task": {
      "type": "string",
      "title": "Task"
    },
    "task_label": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Task Label"
    },
    "image_base64": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Image Base64"
    },
    "image_mime_type": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Image Mime Type"
    },
    "width": {
      "type": "integer",
      "title": "Width"
    },
    "height": {
      "type": "integer",
      "title": "Height"
    },
    "description": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Description"
    },
    "text": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Text"
    },
    "lines": {
      "items": {
        "$ref": "#/components/schemas/OcrLine"
      },
      "type": "array",
      "title": "Lines",
      "default": []
    },
    "model": {
      "$ref": "#/components/schemas/VisionModelInfo"
    },
    "duration_ms": {
      "type": "integer",
      "title": "Duration Ms"
    },
    "output": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Output"
    },
    "regions": {
      "items": {
        "$ref": "#/components/schemas/ImageRegion"
      },
      "type": "array",
      "title": "Regions",
      "default": []
    },
    "request": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/ImageAnalyzeOptions"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "type": "object",
  "required": [
    "operation",
    "task",
    "width",
    "height",
    "model",
    "duration_ms"
  ],
  "title": "ImageJobResult",
  "description": "Persisted vision output, including the operation selected at upload."
}
```

<a id="model-imageocrrequest"></a>

### ImageOcrRequest

Corpo JSON de `POST /images/ocr`.

Sem campo `task`: OCR é sempre `<OCR_WITH_REGION>`, não é escolha do
chamador.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `image_base64` | sim | string |  | Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF. |
| `tags` | não | array de string / null |  | Tags do job (ex.: ["cliente-x", "nf"]). Viram minúsculas; até 20 de até 50 caracteres. |
| `filename` | não | string / null |  | Nome de identificação opcional. |
| `project` | não | string / null |  | Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a `project`). |
| `folder` | não | string / null |  | Nome da pasta no projeto (opcional, get-or-add, sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto. |
| `purge_source` | não | boolean | default=false | Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada. |

Esquema JSON completo:

```json
{
  "properties": {
    "image_base64": {
      "type": "string",
      "title": "Image Base64",
      "description": "Imagem em base64. Um prefixo `data:image/png;base64,` é aceito e removido. Formatos: PNG, JPEG, WEBP, BMP, GIF, TIFF."
    },
    "tags": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Tags",
      "description": "Tags do job (ex.: [\"cliente-x\", \"nf\"]). Viram minúsculas; até 20 de até 50 caracteres."
    },
    "filename": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Filename",
      "description": "Nome de identificação opcional."
    },
    "project": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project",
      "description": "Nome do projeto (get-or-add). Obrigatório, a menos que a API key esteja vinculada a um projeto."
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id",
      "description": "ID de um projeto existente (alternativa a `project`)."
    },
    "folder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder",
      "description": "Nome da pasta no projeto (opcional, get-or-add, sem '/')."
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id",
      "description": "ID de uma pasta existente do projeto."
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "description": "Se true, apaga todas as cópias guardadas da imagem original enviada quando o job termina: `completed`, ou `failed`/`partial`/`cancelled` (as rotas de imagem não têm retry automático). Apaga a cópia local de processamento, o original e a cópia normalizada (prévia em tamanho real) da análise completa/facial no armazenamento, e a imagem embutida no resultado guardado (`image.image_base64` do resultado fica null). O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. GET /jobs/{job_id} informa `source_available` e `source_deleted_at`. Padrão false (mantém). Para apagar depois: DELETE /jobs/{job_id}/source. A resposta síncrona ainda ecoa `image_base64` no topo: vem dos bytes desta requisição, não de uma cópia guardada.",
      "default": false
    }
  },
  "type": "object",
  "required": [
    "image_base64"
  ],
  "title": "ImageOcrRequest",
  "description": "Corpo JSON de `POST /images/ocr`.\n\nSem campo `task`: OCR é sempre `<OCR_WITH_REGION>`, não é escolha do\nchamador."
}
```

<a id="model-imageocrresponse"></a>

### ImageOcrResponse

Resposta de `POST /images/ocr` e `/images/ocr/upload`.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string |  |  |
| `status` | sim | string | const="completed" |  |
| `image_base64` | sim | string |  |  |
| `image_mime_type` | sim | string |  |  |
| `image_bytes` | sim | integer |  |  |
| `image_sha256` | sim | string |  |  |
| `width` | sim | integer |  |  |
| `height` | sim | integer |  |  |
| `model` | sim | [VisionModelInfo](#model-visionmodelinfo) |  |  |
| `duration_ms` | sim | integer |  |  |
| `project` | não | [UploadProjectInfo](#model-uploadprojectinfo) / null |  |  |
| `folder` | não | [UploadFolderInfo](#model-uploadfolderinfo) / null |  |  |
| `text` | sim | string |  |  |
| `lines` | sim | array de [OcrLine](#model-ocrline) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "title": "Job Id"
    },
    "status": {
      "type": "string",
      "const": "completed",
      "title": "Status"
    },
    "image_base64": {
      "type": "string",
      "title": "Image Base64"
    },
    "image_mime_type": {
      "type": "string",
      "title": "Image Mime Type"
    },
    "image_bytes": {
      "type": "integer",
      "title": "Image Bytes"
    },
    "image_sha256": {
      "type": "string",
      "title": "Image Sha256"
    },
    "width": {
      "type": "integer",
      "title": "Width"
    },
    "height": {
      "type": "integer",
      "title": "Height"
    },
    "model": {
      "$ref": "#/components/schemas/VisionModelInfo"
    },
    "duration_ms": {
      "type": "integer",
      "title": "Duration Ms"
    },
    "project": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/UploadProjectInfo"
        },
        {
          "type": "null"
        }
      ]
    },
    "folder": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/UploadFolderInfo"
        },
        {
          "type": "null"
        }
      ]
    },
    "text": {
      "type": "string",
      "title": "Text"
    },
    "lines": {
      "items": {
        "$ref": "#/components/schemas/OcrLine"
      },
      "type": "array",
      "title": "Lines"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "status",
    "image_base64",
    "image_mime_type",
    "image_bytes",
    "image_sha256",
    "width",
    "height",
    "model",
    "duration_ms",
    "text",
    "lines"
  ],
  "title": "ImageOcrResponse",
  "description": "Resposta de `POST /images/ocr` e `/images/ocr/upload`."
}
```

<a id="model-imageregion"></a>

### ImageRegion

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `label` | não | string | default="" |  |
| `score` | não | number / null |  |  |
| `bbox` | não | array de number / null |  |  |
| `quad_box` | não | array de number / null |  |  |
| `polygons` | não | array de array de number | default=[] |  |

Esquema JSON completo:

```json
{
  "properties": {
    "label": {
      "type": "string",
      "title": "Label",
      "default": ""
    },
    "score": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "title": "Score"
    },
    "bbox": {
      "anyOf": [
        {
          "items": {
            "type": "number"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Bbox"
    },
    "quad_box": {
      "anyOf": [
        {
          "items": {
            "type": "number"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Quad Box"
    },
    "polygons": {
      "items": {
        "items": {
          "type": "number"
        },
        "type": "array"
      },
      "type": "array",
      "title": "Polygons",
      "default": []
    }
  },
  "type": "object",
  "title": "ImageRegion"
}
```

<a id="model-jobcreatedresponse"></a>

### JobCreatedResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string (uuid) |  |  |
| `status` | sim | string | const="queued" |  |
| `created_at` | sim | string (date-time) |  |  |
| `message` | sim | string |  |  |
| `project` | não | [UploadProjectInfo](#model-uploadprojectinfo) / null |  |  |
| `folder` | não | [UploadFolderInfo](#model-uploadfolderinfo) / null |  |  |
| `duplicate` | não | boolean | default=false |  |
| `source_available` | não | boolean / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "format": "uuid",
      "title": "Job Id"
    },
    "status": {
      "type": "string",
      "const": "queued",
      "title": "Status"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "message": {
      "type": "string",
      "title": "Message"
    },
    "project": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/UploadProjectInfo"
        },
        {
          "type": "null"
        }
      ]
    },
    "folder": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/UploadFolderInfo"
        },
        {
          "type": "null"
        }
      ]
    },
    "duplicate": {
      "type": "boolean",
      "title": "Duplicate",
      "default": false
    },
    "source_available": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Available"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "status",
    "created_at",
    "message"
  ],
  "title": "JobCreatedResponse"
}
```

<a id="model-jobengine"></a>

### JobEngine

Onde um job roteado roda: no servidor (local) ou numa conta de nuvem (cloud)

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `kind` | sim | string | enum=["local", "cloud"] |  |

Esquema JSON completo:

```json
{
  "properties": {
    "kind": {
      "type": "string",
      "enum": [
        "local",
        "cloud"
      ],
      "title": "Kind"
    }
  },
  "type": "object",
  "required": [
    "kind"
  ],
  "title": "JobEngine",
  "description": "Onde um job roteado roda: no servidor (local) ou numa conta de nuvem (cloud)"
}
```

<a id="model-jobpagesresponse"></a>

### JobPagesResponse

Detalhes de progresso por página

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string (uuid) |  |  |
| `total_pages` | sim | integer |  |  |
| `pages_completed` | sim | integer |  |  |
| `pages_failed` | sim | integer |  |  |
| `pages` | sim | array de [PageJobInfo](#model-pagejobinfo) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "format": "uuid",
      "title": "Job Id"
    },
    "total_pages": {
      "type": "integer",
      "title": "Total Pages"
    },
    "pages_completed": {
      "type": "integer",
      "title": "Pages Completed"
    },
    "pages_failed": {
      "type": "integer",
      "title": "Pages Failed"
    },
    "pages": {
      "items": {
        "$ref": "#/components/schemas/PageJobInfo"
      },
      "type": "array",
      "title": "Pages"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "total_pages",
    "pages_completed",
    "pages_failed",
    "pages"
  ],
  "title": "JobPagesResponse",
  "description": "Detalhes de progresso por página"
}
```

<a id="model-jobresultresponse"></a>

### JobResultResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string (uuid) |  |  |
| `type` | sim | [JobType](#model-jobtype) |  |  |
| `status` | sim | [JobStatus](#model-jobstatus) |  |  |
| `result` | sim | [ConversionResult](#model-conversionresult) |  |  |
| `completed_at` | sim | string (date-time) |  |  |
| `page_number` | não | integer / null |  |  |
| `parent_job_id` | não | string (uuid) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "format": "uuid",
      "title": "Job Id"
    },
    "type": {
      "$ref": "#/components/schemas/JobType"
    },
    "status": {
      "$ref": "#/components/schemas/JobStatus"
    },
    "result": {
      "$ref": "#/components/schemas/ConversionResult"
    },
    "completed_at": {
      "type": "string",
      "format": "date-time",
      "title": "Completed At"
    },
    "page_number": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Page Number"
    },
    "parent_job_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Parent Job Id"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "type",
    "status",
    "result",
    "completed_at"
  ],
  "title": "JobResultResponse"
}
```

<a id="model-jobstatus"></a>

### JobStatus

Estados possíveis de um job

Esquema JSON completo:

```json
{
  "type": "string",
  "enum": [
    "pending",
    "queued",
    "processing",
    "partial",
    "completed",
    "failed",
    "cancelled"
  ],
  "title": "JobStatus",
  "description": "Estados possíveis de um job"
}
```

<a id="model-jobstatusresponse"></a>

### JobStatusResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string (uuid) |  |  |
| `type` | sim | [JobType](#model-jobtype) |  |  |
| `status` | sim | [JobStatus](#model-jobstatus) |  |  |
| `progress` | sim | integer | minimum=0.0; maximum=100.0 |  |
| `created_at` | sim | string (date-time) |  |  |
| `started_at` | não | string (date-time) / null |  |  |
| `completed_at` | não | string (date-time) / null |  |  |
| `error` | não | string / null |  |  |
| `name` | não | string / null |  |  |
| `tags` | não | array de string | default=[] |  |
| `source_available` | não | boolean | default=false |  |
| `source_deleted_at` | não | string (date-time) / null |  |  |
| `source_deletable` | não | boolean | default=false |  |
| `project` | não | [ProjectRef](#model-projectref) / null |  |  |
| `folder` | não | [FolderRef](#model-folderref) / null |  |  |
| `parent_job_id` | não | string (uuid) / null |  |  |
| `total_pages` | não | integer / null |  |  |
| `pages_completed` | não | integer / null |  |  |
| `pages_failed` | não | integer / null |  |  |
| `pages` | não | array de [PageJobInfo](#model-pagejobinfo) / null |  |  |
| `child_jobs` | não | [ChildJobs](#model-childjobs) / null |  |  |
| `page_number` | não | integer / null |  |  |
| `transcribed_seconds` | não | number / null |  |  |
| `media_duration` | não | number / null |  |  |
| `phase` | não | string / null |  |  |
| `kind` | não | string / null |  |  |
| `configuration` | não | object / null |  |  |
| `image_analysis` | não | object / null |  |  |
| `datalake` | não | object / null |  |  |
| `engine` | não | [JobEngine](#model-jobengine) / null |  |  |
| `queue_reason` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "format": "uuid",
      "title": "Job Id"
    },
    "type": {
      "$ref": "#/components/schemas/JobType"
    },
    "status": {
      "$ref": "#/components/schemas/JobStatus"
    },
    "progress": {
      "type": "integer",
      "maximum": 100.0,
      "minimum": 0.0,
      "title": "Progress"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "started_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Started At"
    },
    "completed_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Completed At"
    },
    "error": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Error"
    },
    "name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Name"
    },
    "tags": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Tags",
      "default": []
    },
    "source_available": {
      "type": "boolean",
      "title": "Source Available",
      "default": false
    },
    "source_deleted_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Deleted At"
    },
    "source_deletable": {
      "type": "boolean",
      "title": "Source Deletable",
      "default": false
    },
    "project": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/ProjectRef"
        },
        {
          "type": "null"
        }
      ]
    },
    "folder": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/FolderRef"
        },
        {
          "type": "null"
        }
      ]
    },
    "parent_job_id": {
      "anyOf": [
        {
          "type": "string",
          "format": "uuid"
        },
        {
          "type": "null"
        }
      ],
      "title": "Parent Job Id"
    },
    "total_pages": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Total Pages"
    },
    "pages_completed": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Pages Completed"
    },
    "pages_failed": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Pages Failed"
    },
    "pages": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/PageJobInfo"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Pages"
    },
    "child_jobs": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/ChildJobs"
        },
        {
          "type": "null"
        }
      ]
    },
    "page_number": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Page Number"
    },
    "transcribed_seconds": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "title": "Transcribed Seconds"
    },
    "media_duration": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "title": "Media Duration"
    },
    "phase": {
      "anyOf": [
        {
          "type": "string",
          "enum": [
            "transcribing",
            "aligning",
            "diarizing",
            "saving"
          ]
        },
        {
          "type": "null"
        }
      ],
      "title": "Phase"
    },
    "kind": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Kind"
    },
    "configuration": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Configuration"
    },
    "image_analysis": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Image Analysis"
    },
    "datalake": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake"
    },
    "engine": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/JobEngine"
        },
        {
          "type": "null"
        }
      ]
    },
    "queue_reason": {
      "anyOf": [
        {
          "type": "string",
          "enum": [
            "in_queue",
            "starting"
          ]
        },
        {
          "type": "null"
        }
      ],
      "title": "Queue Reason"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "type",
    "status",
    "progress",
    "created_at"
  ],
  "title": "JobStatusResponse"
}
```

<a id="model-jobtagsresponse"></a>

### JobTagsResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string |  |  |
| `tags` | sim | array de string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "title": "Job Id"
    },
    "tags": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Tags"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "tags"
  ],
  "title": "JobTagsResponse"
}
```

<a id="model-jobtagsupdate"></a>

### JobTagsUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `tags` | sim | array de string |  | A lista completa de tags do job (substitui as atuais). |

Esquema JSON completo:

```json
{
  "properties": {
    "tags": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Tags",
      "description": "A lista completa de tags do job (substitui as atuais)."
    }
  },
  "type": "object",
  "required": [
    "tags"
  ],
  "title": "JobTagsUpdate"
}
```

<a id="model-jobtype"></a>

### JobType

Tipos de jobs no sistema

Esquema JSON completo:

```json
{
  "type": "string",
  "enum": [
    "main",
    "split",
    "page",
    "merge",
    "download",
    "crawler"
  ],
  "title": "JobType",
  "description": "Tipos de jobs no sistema"
}
```

<a id="model-localgpu"></a>

### LocalGpu

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `ref` | sim | string | pattern="^[a-z0-9][a-z0-9_-]*$" |  |
| `name` | não | string | default="" |  |
| `uuid` | não | string / null |  |  |
| `vram_gb` | sim | number | maximum=1000.0; exclusiveMinimum=0.0 |  |
| `vram_reserve_gb` | não | number | default=1.0; minimum=0.0 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "ref": {
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9_-]*$",
      "title": "Ref"
    },
    "name": {
      "type": "string",
      "title": "Name",
      "default": ""
    },
    "uuid": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Uuid"
    },
    "vram_gb": {
      "type": "number",
      "maximum": 1000.0,
      "exclusiveMinimum": 0.0,
      "title": "Vram Gb"
    },
    "vram_reserve_gb": {
      "type": "number",
      "minimum": 0.0,
      "title": "Vram Reserve Gb",
      "default": 1.0
    }
  },
  "type": "object",
  "required": [
    "ref",
    "vram_gb"
  ],
  "title": "LocalGpu"
}
```

<a id="model-metadataupdate"></a>

### MetadataUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `name` | sim | string | minLength=1; maxLength=100 |  |
| `description` | não | string | default=""; maxLength=1000 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Version"
    },
    "name": {
      "type": "string",
      "maxLength": 100,
      "minLength": 1,
      "title": "Name"
    },
    "description": {
      "type": "string",
      "maxLength": 1000,
      "title": "Description",
      "default": ""
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "version",
    "name"
  ],
  "title": "MetadataUpdate"
}
```

<a id="model-nameresolveresponse"></a>

### NameResolveResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `valid` | sim | boolean |  |  |
| `match` | não | [ProjectRef](#model-projectref) / null |  | The existing project/folder, or null if it would be created |
| `error` | não | string / null |  | Why the name is not acceptable (valid=false) |

Esquema JSON completo:

```json
{
  "properties": {
    "valid": {
      "type": "boolean",
      "title": "Valid"
    },
    "match": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/ProjectRef"
        },
        {
          "type": "null"
        }
      ],
      "description": "The existing project/folder, or null if it would be created"
    },
    "error": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Error",
      "description": "Why the name is not acceptable (valid=false)"
    }
  },
  "type": "object",
  "required": [
    "valid"
  ],
  "title": "NameResolveResponse"
}
```

<a id="model-ocrline"></a>

### OcrLine

Uma linha detectada pelo `<OCR_WITH_REGION>` do Florence-2.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `text` | sim | string |  |  |
| `quad_box` | sim | array de number |  | 8 valores: x1,y1,x2,y2,x3,y3,x4,y4 (pixels da imagem original). |
| `bbox` | sim | array de number |  | 4 valores derivados do quad_box: x_min,y_min,x_max,y_max. |

Esquema JSON completo:

```json
{
  "properties": {
    "text": {
      "type": "string",
      "title": "Text"
    },
    "quad_box": {
      "items": {
        "type": "number"
      },
      "type": "array",
      "title": "Quad Box",
      "description": "8 valores: x1,y1,x2,y2,x3,y3,x4,y4 (pixels da imagem original)."
    },
    "bbox": {
      "items": {
        "type": "number"
      },
      "type": "array",
      "title": "Bbox",
      "description": "4 valores derivados do quad_box: x_min,y_min,x_max,y_max."
    }
  },
  "type": "object",
  "required": [
    "text",
    "quad_box",
    "bbox"
  ],
  "title": "OcrLine",
  "description": "Uma linha detectada pelo `<OCR_WITH_REGION>` do Florence-2."
}
```

<a id="model-pagejobinfo"></a>

### PageJobInfo

Informação de um page job

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `page_number` | sim | integer |  |  |
| `job_id` | não | string / null |  |  |
| `status` | sim | [JobStatus](#model-jobstatus) |  |  |
| `url` | sim | string |  |  |
| `error_message` | não | string / null |  |  |
| `retry_count` | não | integer | default=0 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "page_number": {
      "type": "integer",
      "title": "Page Number"
    },
    "job_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Job Id"
    },
    "status": {
      "$ref": "#/components/schemas/JobStatus"
    },
    "url": {
      "type": "string",
      "title": "Url"
    },
    "error_message": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Error Message"
    },
    "retry_count": {
      "type": "integer",
      "title": "Retry Count",
      "default": 0
    }
  },
  "type": "object",
  "required": [
    "page_number",
    "status",
    "url"
  ],
  "title": "PageJobInfo",
  "description": "Informação de um page job"
}
```

<a id="model-partialtranscriptresponse"></a>

### PartialTranscriptResponse

Texto de uma transcrição em andamento, a partir do segmento `since`

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string (uuid) |  |  |
| `status` | sim | [JobStatus](#model-jobstatus) |  |  |
| `segments` | sim | array de [TranscriptSegment](#model-transcriptsegment) |  |  |
| `next` | sim | integer |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "format": "uuid",
      "title": "Job Id"
    },
    "status": {
      "$ref": "#/components/schemas/JobStatus"
    },
    "segments": {
      "items": {
        "$ref": "#/components/schemas/TranscriptSegment"
      },
      "type": "array",
      "title": "Segments"
    },
    "next": {
      "type": "integer",
      "title": "Next"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "status",
    "segments",
    "next"
  ],
  "title": "PartialTranscriptResponse",
  "description": "Texto de uma transcrição em andamento, a partir do segmento `since`"
}
```

<a id="model-partitionfield"></a>

### PartitionField

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `field` | sim | string | enum=["date", "year", "month", "day", "hour", "project_id", "folder_id", "source_type", "custom"] |  |
| `key` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "field": {
      "type": "string",
      "enum": [
        "date",
        "year",
        "month",
        "day",
        "hour",
        "project_id",
        "folder_id",
        "source_type",
        "custom"
      ],
      "title": "Field"
    },
    "key": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 32,
          "pattern": "^[a-z][a-z0-9_]*$"
        },
        {
          "type": "null"
        }
      ],
      "title": "Key"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "field"
  ],
  "title": "PartitionField"
}
```

<a id="model-partitionpreview"></a>

### PartitionPreview

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `connection_id` | não | string / null |  |  |
| `partitioning` | não | [PartitionStrategy](#model-partitionstrategy) / null |  |  |
| `partition_values` | não | object | additionalProperties={"type": "string"} |  |
| `prefix` | não | string | default=""; maxLength=700 |  |
| `created_at` | não | string (date-time) / null |  |  |
| `project_id` | não | string / null |  |  |
| `folder_id` | não | string / null |  |  |
| `source_type` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "connection_id": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 36
        },
        {
          "type": "null"
        }
      ],
      "title": "Connection Id"
    },
    "partitioning": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/PartitionStrategy"
        },
        {
          "type": "null"
        }
      ]
    },
    "partition_values": {
      "additionalProperties": {
        "type": "string"
      },
      "type": "object",
      "title": "Partition Values"
    },
    "prefix": {
      "type": "string",
      "maxLength": 700,
      "title": "Prefix",
      "default": ""
    },
    "created_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Created At"
    },
    "project_id": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 36
        },
        {
          "type": "null"
        }
      ],
      "title": "Project Id"
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 36
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id"
    },
    "source_type": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 50
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Type"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "PartitionPreview"
}
```

<a id="model-partitionstrategy"></a>

### PartitionStrategy

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `mode` | não | string | default="none"; enum=["none", "date", "project_date", "custom"] |  |
| `fields` | não | array de [PartitionField](#model-partitionfield) | maxItems=8 |  |
| `granularity` | não | string | default="day"; enum=["month", "day", "hour"] |  |
| `timezone` | não | string | default="UTC"; maxLength=100 |  |
| `missing` | não | string | default="fallback"; enum=["fallback", "require"] |  |
| `fallback` | não | string | default="_unassigned"; minLength=1; maxLength=128 |  |
| `analytics` | não | string | default="none"; enum=["none", "jsonl"] |  |

Esquema JSON completo:

```json
{
  "properties": {
    "mode": {
      "type": "string",
      "enum": [
        "none",
        "date",
        "project_date",
        "custom"
      ],
      "title": "Mode",
      "default": "none"
    },
    "fields": {
      "items": {
        "$ref": "#/components/schemas/PartitionField"
      },
      "type": "array",
      "maxItems": 8,
      "title": "Fields"
    },
    "granularity": {
      "type": "string",
      "enum": [
        "month",
        "day",
        "hour"
      ],
      "title": "Granularity",
      "default": "day"
    },
    "timezone": {
      "type": "string",
      "maxLength": 100,
      "title": "Timezone",
      "default": "UTC"
    },
    "missing": {
      "type": "string",
      "enum": [
        "fallback",
        "require"
      ],
      "title": "Missing",
      "default": "fallback"
    },
    "fallback": {
      "type": "string",
      "maxLength": 128,
      "minLength": 1,
      "title": "Fallback",
      "default": "_unassigned"
    },
    "analytics": {
      "type": "string",
      "enum": [
        "none",
        "jsonl"
      ],
      "title": "Analytics",
      "default": "none"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "PartitionStrategy"
}
```

<a id="model-permissioncheck"></a>

### PermissionCheck

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `permission` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "permission": {
      "type": "string",
      "title": "Permission"
    }
  },
  "type": "object",
  "required": [
    "permission"
  ],
  "title": "PermissionCheck"
}
```

<a id="model-permissioncheckresult"></a>

### PermissionCheckResult

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `permission` | sim | string |  |  |
| `allowed` | sim | boolean |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "permission": {
      "type": "string",
      "title": "Permission"
    },
    "allowed": {
      "type": "boolean",
      "title": "Allowed"
    }
  },
  "type": "object",
  "required": [
    "permission",
    "allowed"
  ],
  "title": "PermissionCheckResult"
}
```

<a id="model-planrequest"></a>

### PlanRequest

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `type` | sim | string |  |  |
| `feature` | não | string | default="transcription" |  |
| `profile_revision` | não | integer / null |  |  |
| `engine_version` | sim | integer | minimum=0.0 |  |
| `drain_timeout_seconds` | não | integer | default=900; minimum=1.0; maximum=1800.0 |  |
| `max_usd` | não | number / string | default="0" |  |

Esquema JSON completo:

```json
{
  "properties": {
    "type": {
      "type": "string",
      "title": "Type"
    },
    "feature": {
      "type": "string",
      "title": "Feature",
      "default": "transcription"
    },
    "profile_revision": {
      "anyOf": [
        {
          "type": "integer",
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Profile Revision"
    },
    "engine_version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Engine Version"
    },
    "drain_timeout_seconds": {
      "type": "integer",
      "maximum": 1800.0,
      "minimum": 1.0,
      "title": "Drain Timeout Seconds",
      "default": 900
    },
    "max_usd": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 1000.0,
          "minimum": 0.0
        },
        {
          "type": "string",
          "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$"
        }
      ],
      "title": "Max Usd",
      "default": "0"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "type",
    "engine_version"
  ],
  "title": "PlanRequest"
}
```

<a id="model-policycreate"></a>

### PolicyCreate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | sim | string | minLength=1; maxLength=100 |  |
| `constraints` | sim | [Constraints](#model-constraints) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "name": {
      "type": "string",
      "maxLength": 100,
      "minLength": 1,
      "title": "Name"
    },
    "constraints": {
      "$ref": "#/components/schemas/Constraints"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "name",
    "constraints"
  ],
  "title": "PolicyCreate"
}
```

<a id="model-policyupdate"></a>

### PolicyUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `constraints` | sim | [Constraints](#model-constraints) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Version"
    },
    "constraints": {
      "$ref": "#/components/schemas/Constraints"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "version",
    "constraints"
  ],
  "title": "PolicyUpdate"
}
```

<a id="model-principalcreate"></a>

### PrincipalCreate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string | maxLength=36; pattern="^installation:[a-z0-9_-]{1,23}$" |  |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "maxLength": 36,
      "pattern": "^installation:[a-z0-9_-]{1,23}$",
      "title": "Id"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "id"
  ],
  "title": "PrincipalCreate"
}
```

<a id="model-principalstate"></a>

### PrincipalState

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `active` | sim | boolean |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Version"
    },
    "active": {
      "type": "boolean",
      "title": "Active"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "version",
    "active"
  ],
  "title": "PrincipalState"
}
```

<a id="model-profilecreate"></a>

### ProfileCreate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `settings` | sim | [RuntimeSettings](#model-runtimesettings) |  |  |
| `warm_for_seconds` | não | integer / null |  |  |
| `name` | sim | string | minLength=1; maxLength=100 |  |
| `description` | não | string | default=""; maxLength=1000 |  |
| `adapter_type` | sim | string |  |  |
| `feature` | sim | string |  |  |
| `environment` | não | string | default="development"; enum=["development", "staging", "production"] |  |

Esquema JSON completo:

```json
{
  "properties": {
    "settings": {
      "$ref": "#/components/schemas/RuntimeSettings"
    },
    "warm_for_seconds": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 86400.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Warm For Seconds"
    },
    "name": {
      "type": "string",
      "maxLength": 100,
      "minLength": 1,
      "title": "Name"
    },
    "description": {
      "type": "string",
      "maxLength": 1000,
      "title": "Description",
      "default": ""
    },
    "adapter_type": {
      "type": "string",
      "title": "Adapter Type"
    },
    "feature": {
      "type": "string",
      "title": "Feature"
    },
    "environment": {
      "type": "string",
      "enum": [
        "development",
        "staging",
        "production"
      ],
      "title": "Environment",
      "default": "development"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "settings",
    "name",
    "adapter_type",
    "feature"
  ],
  "title": "ProfileCreate"
}
```

<a id="model-profileupdate"></a>

### ProfileUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `feature` | sim | string |  |  |
| `version` | sim | integer | minimum=0.0 |  |
| `profile` | sim | [RuntimeSettings](#model-runtimesettings) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "feature": {
      "type": "string",
      "title": "Feature"
    },
    "version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Version"
    },
    "profile": {
      "$ref": "#/components/schemas/RuntimeSettings"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "feature",
    "version",
    "profile"
  ],
  "title": "ProfileUpdate"
}
```

<a id="model-projectfoldersummary"></a>

### ProjectFolderSummary

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string |  |  |
| `name` | sim | string |  |  |
| `job_count` | sim | integer |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "job_count": {
      "type": "integer",
      "title": "Job Count"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "job_count"
  ],
  "title": "ProjectFolderSummary"
}
```

<a id="model-projectlimits"></a>

### ProjectLimits

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `max_projects` | sim | integer |  |  |
| `max_folders_per_project` | sim | integer |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "max_projects": {
      "type": "integer",
      "title": "Max Projects"
    },
    "max_folders_per_project": {
      "type": "integer",
      "title": "Max Folders Per Project"
    }
  },
  "type": "object",
  "required": [
    "max_projects",
    "max_folders_per_project"
  ],
  "title": "ProjectLimits"
}
```

<a id="model-projectlistresponse"></a>

### ProjectListResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `projects` | sim | array de [ProjectSummary](#model-projectsummary) |  |  |
| `limits` | sim | [ProjectLimits](#model-projectlimits) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "projects": {
      "items": {
        "$ref": "#/components/schemas/ProjectSummary"
      },
      "type": "array",
      "title": "Projects"
    },
    "limits": {
      "$ref": "#/components/schemas/ProjectLimits"
    }
  },
  "type": "object",
  "required": [
    "projects",
    "limits"
  ],
  "title": "ProjectListResponse"
}
```

<a id="model-projectref"></a>

### ProjectRef

A project as other resources point at it.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string |  |  |
| `name` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name"
  ],
  "title": "ProjectRef",
  "description": "A project as other resources point at it."
}
```

<a id="model-projectsummary"></a>

### ProjectSummary

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string |  |  |
| `name` | sim | string |  |  |
| `description` | não | string / null |  |  |
| `archived` | sim | boolean |  |  |
| `job_count` | sim | integer |  |  |
| `root_job_count` | sim | integer |  | Jobs of the project that are in no folder |
| `failed_count` | sim | integer |  |  |
| `active_count` | sim | integer |  | Jobs queued or processing |
| `last_job_at` | não | string (date-time) / null |  |  |
| `api_keys` | sim | array de [ProjectRef](#model-projectref) |  | API keys bound to this project |
| `folders` | não | array de [ProjectFolderSummary](#model-projectfoldersummary) / null |  | Only with ?include=folders |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "description": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Description"
    },
    "archived": {
      "type": "boolean",
      "title": "Archived"
    },
    "job_count": {
      "type": "integer",
      "title": "Job Count"
    },
    "root_job_count": {
      "type": "integer",
      "title": "Root Job Count",
      "description": "Jobs of the project that are in no folder"
    },
    "failed_count": {
      "type": "integer",
      "title": "Failed Count"
    },
    "active_count": {
      "type": "integer",
      "title": "Active Count",
      "description": "Jobs queued or processing"
    },
    "last_job_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Last Job At"
    },
    "api_keys": {
      "items": {
        "$ref": "#/components/schemas/ProjectRef"
      },
      "type": "array",
      "title": "Api Keys",
      "description": "API keys bound to this project"
    },
    "folders": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/ProjectFolderSummary"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Folders",
      "description": "Only with ?include=folders"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "archived",
    "job_count",
    "root_job_count",
    "failed_count",
    "active_count",
    "api_keys"
  ],
  "title": "ProjectSummary"
}
```

<a id="model-publish"></a>

### Publish

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |
| `revision_id` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Version"
    },
    "revision_id": {
      "type": "string",
      "title": "Revision Id"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "version",
    "revision_id"
  ],
  "title": "Publish"
}
```

<a id="model-revisioncreate"></a>

### RevisionCreate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `settings` | sim | [RuntimeSettings](#model-runtimesettings) |  |  |
| `warm_for_seconds` | não | integer / null |  |  |
| `version` | sim | integer | minimum=0.0 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "settings": {
      "$ref": "#/components/schemas/RuntimeSettings"
    },
    "warm_for_seconds": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 86400.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Warm For Seconds"
    },
    "version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Version"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "settings",
    "version"
  ],
  "title": "RevisionCreate"
}
```

<a id="model-routestep"></a>

### RouteStep

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `position` | não | integer / null |  |  |
| `engine_ids` | sim | array de string | minItems=1; maxItems=20 |  |
| `group_strategy` | não | string | default="priority"; enum=["priority", "fill_first"] |  |
| `scale_out_after_seconds` | não | integer / null |  |  |
| `when` | não | [When](#model-when) / null |  |  |
| `spend_cap` | não | [SpendCap](#model-spendcap) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "position": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Position"
    },
    "engine_ids": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "maxItems": 20,
      "minItems": 1,
      "title": "Engine Ids"
    },
    "group_strategy": {
      "type": "string",
      "enum": [
        "priority",
        "fill_first"
      ],
      "title": "Group Strategy",
      "default": "priority"
    },
    "scale_out_after_seconds": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 86400.0,
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Scale Out After Seconds"
    },
    "when": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/When"
        },
        {
          "type": "null"
        }
      ]
    },
    "spend_cap": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/SpendCap"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "type": "object",
  "required": [
    "engine_ids"
  ],
  "title": "RouteStep"
}
```

<a id="model-routeupdate"></a>

### RouteUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `steps` | sim | array de [RouteStep](#model-routestep) | minItems=1; maxItems=10 |  |
| `on_no_engine` | não | string | default="hold"; enum=["hold", "fail"] |  |
| `fail_after_seconds` | não | integer / null |  |  |
| `max_attempts` | não | integer | default=3; minimum=1.0; maximum=10.0 |  |
| `remote_allowed_for` | não | string | default="admins"; enum=["admins", "all"] |  |
| `user_period_limit_usd` | não | number / string / null |  |  |
| `remote_data_notice` | não | string / null |  |  |
| `dispatcher_fallback` | não | string | default="local_direct"; enum=["local_direct", "hold"] |  |
| `dispatcher_down_seconds` | não | integer | default=120; minimum=30.0; maximum=3600.0 |  |
| `version` | não | integer / null |  |  |
| `current_password` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "steps": {
      "items": {
        "$ref": "#/components/schemas/RouteStep"
      },
      "type": "array",
      "maxItems": 10,
      "minItems": 1,
      "title": "Steps"
    },
    "on_no_engine": {
      "type": "string",
      "enum": [
        "hold",
        "fail"
      ],
      "title": "On No Engine",
      "default": "hold"
    },
    "fail_after_seconds": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 2592000.0,
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Fail After Seconds"
    },
    "max_attempts": {
      "type": "integer",
      "maximum": 10.0,
      "minimum": 1.0,
      "title": "Max Attempts",
      "default": 3
    },
    "remote_allowed_for": {
      "type": "string",
      "enum": [
        "admins",
        "all"
      ],
      "title": "Remote Allowed For",
      "default": "admins"
    },
    "user_period_limit_usd": {
      "anyOf": [
        {
          "type": "number",
          "minimum": 0.0
        },
        {
          "type": "string",
          "pattern": "^(?!^[-+.]*$)[+-]?0*(?:\\d{0,6}|(?=[\\d.]{1,13}0*$)\\d{0,6}\\.\\d{0,6}0*$)"
        },
        {
          "type": "null"
        }
      ],
      "title": "User Period Limit Usd"
    },
    "remote_data_notice": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 2000
        },
        {
          "type": "null"
        }
      ],
      "title": "Remote Data Notice"
    },
    "dispatcher_fallback": {
      "type": "string",
      "enum": [
        "local_direct",
        "hold"
      ],
      "title": "Dispatcher Fallback",
      "default": "local_direct"
    },
    "dispatcher_down_seconds": {
      "type": "integer",
      "maximum": 3600.0,
      "minimum": 30.0,
      "title": "Dispatcher Down Seconds",
      "default": 120
    },
    "version": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Version"
    },
    "current_password": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Current Password"
    }
  },
  "type": "object",
  "required": [
    "steps"
  ],
  "title": "RouteUpdate"
}
```

<a id="model-runtimesettings"></a>

### RuntimeSettings

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `adapter_version` | não | integer | default=1; minimum=1.0; maximum=1.0 |  |
| `schema_version` | não | integer | default=1; minimum=1.0; maximum=1.0 |  |
| `binding` | sim | [ControlBinding](#model-controlbinding) |  |  |
| `model_profile_id` | sim | string |  |  |
| `desired_replicas` | não | integer | default=1; minimum=0.0; maximum=100.0 |  |
| `max_replicas` | não | integer | default=1; minimum=0.0; maximum=100.0 |  |
| `min_ready_replicas` | não | integer | default=0; minimum=0.0; maximum=100.0 |  |
| `idle_timeout_seconds` | não | integer | default=60; minimum=2.0; maximum=3600.0 |  |
| `memory_mb` | não | integer / null |  |  |
| `warmup_mode` | não | string | default="on_start"; enum=["on_start", "manual"] |  |
| `warm_until` | não | string (date-time) / null |  |  |
| `provider_settings` | não | object | additionalProperties=true |  |

Esquema JSON completo:

```json
{
  "properties": {
    "adapter_version": {
      "type": "integer",
      "maximum": 1.0,
      "minimum": 1.0,
      "title": "Adapter Version",
      "default": 1
    },
    "schema_version": {
      "type": "integer",
      "maximum": 1.0,
      "minimum": 1.0,
      "title": "Schema Version",
      "default": 1
    },
    "binding": {
      "$ref": "#/components/schemas/ControlBinding"
    },
    "model_profile_id": {
      "type": "string",
      "title": "Model Profile Id"
    },
    "desired_replicas": {
      "type": "integer",
      "maximum": 100.0,
      "minimum": 0.0,
      "title": "Desired Replicas",
      "default": 1
    },
    "max_replicas": {
      "type": "integer",
      "maximum": 100.0,
      "minimum": 0.0,
      "title": "Max Replicas",
      "default": 1
    },
    "min_ready_replicas": {
      "type": "integer",
      "maximum": 100.0,
      "minimum": 0.0,
      "title": "Min Ready Replicas",
      "default": 0
    },
    "idle_timeout_seconds": {
      "type": "integer",
      "maximum": 3600.0,
      "minimum": 2.0,
      "title": "Idle Timeout Seconds",
      "default": 60
    },
    "memory_mb": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 262144.0,
          "minimum": 256.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Memory Mb"
    },
    "warmup_mode": {
      "type": "string",
      "enum": [
        "on_start",
        "manual"
      ],
      "title": "Warmup Mode",
      "default": "on_start"
    },
    "warm_until": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Warm Until"
    },
    "provider_settings": {
      "additionalProperties": true,
      "type": "object",
      "title": "Provider Settings"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "binding",
    "model_profile_id"
  ],
  "title": "RuntimeSettings"
}
```

<a id="model-scopeupdate"></a>

### ScopeUpdate

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `key` | sim | string | minLength=1; maxLength=200 |  |
| `version` | sim | integer | minimum=0.0 |  |
| `consumers` | sim | array de [Consumer](#model-consumer) | minItems=1; maxItems=100 |  |
| `qualified` | não | boolean | default=false |  |

Esquema JSON completo:

```json
{
  "properties": {
    "key": {
      "type": "string",
      "maxLength": 200,
      "minLength": 1,
      "title": "Key"
    },
    "version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Version"
    },
    "consumers": {
      "items": {
        "$ref": "#/components/schemas/Consumer"
      },
      "type": "array",
      "maxItems": 100,
      "minItems": 1,
      "title": "Consumers"
    },
    "qualified": {
      "type": "boolean",
      "title": "Qualified",
      "default": false
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "key",
    "version",
    "consumers"
  ],
  "title": "ScopeUpdate"
}
```

<a id="model-setupstatus"></a>

### SetupStatus

Whether the installation still needs its root user (spec 0019)

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `root_exists` | sim | boolean |  |  |
| `root_pending` | sim | boolean |  |  |
| `setup_token_required` | sim | boolean |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "root_exists": {
      "type": "boolean",
      "title": "Root Exists"
    },
    "root_pending": {
      "type": "boolean",
      "title": "Root Pending"
    },
    "setup_token_required": {
      "type": "boolean",
      "title": "Setup Token Required"
    }
  },
  "type": "object",
  "required": [
    "root_exists",
    "root_pending",
    "setup_token_required"
  ],
  "title": "SetupStatus",
  "description": "Whether the installation still needs its root user (spec 0019)"
}
```

<a id="model-sourcedeletedresponse"></a>

### SourceDeletedResponse

Resposta de DELETE /jobs/{job_id}/source

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `job_id` | sim | string |  |  |
| `source_deleted` | sim | boolean |  |  |
| `source_deleted_at` | não | string (date-time) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "job_id": {
      "type": "string",
      "title": "Job Id"
    },
    "source_deleted": {
      "type": "boolean",
      "title": "Source Deleted"
    },
    "source_deleted_at": {
      "anyOf": [
        {
          "type": "string",
          "format": "date-time"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Deleted At"
    }
  },
  "type": "object",
  "required": [
    "job_id",
    "source_deleted"
  ],
  "title": "SourceDeletedResponse",
  "description": "Resposta de DELETE /jobs/{job_id}/source"
}
```

<a id="model-spendcap"></a>

### SpendCap

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `usd` | sim | number / string |  |  |
| `window` | sim | string | enum=["day", "period"] |  |

Esquema JSON completo:

```json
{
  "properties": {
    "usd": {
      "anyOf": [
        {
          "type": "number",
          "exclusiveMinimum": 0.0
        },
        {
          "type": "string",
          "pattern": "^(?!^[-+.]*$)[+-]?0*(?:\\d{0,6}|(?=[\\d.]{1,13}0*$)\\d{0,6}\\.\\d{0,6}0*$)"
        }
      ],
      "title": "Usd"
    },
    "window": {
      "type": "string",
      "enum": [
        "day",
        "period"
      ],
      "title": "Window"
    }
  },
  "type": "object",
  "required": [
    "usd",
    "window"
  ],
  "title": "SpendCap"
}
```

<a id="model-subjectstate"></a>

### SubjectState

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `expected_is_active` | sim | boolean |  |  |
| `expected_is_admin` | sim | boolean |  |  |
| `is_active` | sim | boolean |  |  |
| `is_admin` | sim | boolean |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "expected_is_active": {
      "type": "boolean",
      "title": "Expected Is Active"
    },
    "expected_is_admin": {
      "type": "boolean",
      "title": "Expected Is Admin"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "is_admin": {
      "type": "boolean",
      "title": "Is Admin"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "expected_is_active",
    "expected_is_admin",
    "is_active",
    "is_admin"
  ],
  "title": "SubjectState"
}
```

<a id="model-tagcount"></a>

### TagCount

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `tag` | sim | string |  |  |
| `count` | sim | integer |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "tag": {
      "type": "string",
      "title": "Tag"
    },
    "count": {
      "type": "integer",
      "title": "Count"
    }
  },
  "type": "object",
  "required": [
    "tag",
    "count"
  ],
  "title": "TagCount"
}
```

<a id="model-taglistresponse"></a>

### TagListResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `tags` | sim | array de [TagCount](#model-tagcount) |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "tags": {
      "items": {
        "$ref": "#/components/schemas/TagCount"
      },
      "type": "array",
      "title": "Tags"
    }
  },
  "type": "object",
  "required": [
    "tags"
  ],
  "title": "TagListResponse"
}
```

<a id="model-testconnection"></a>

### TestConnection

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `bucket` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "bucket": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 255
        },
        {
          "type": "null"
        }
      ],
      "title": "Bucket"
    }
  },
  "type": "object",
  "title": "TestConnection"
}
```

<a id="model-token"></a>

### Token

Schema for JWT token response

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `access_token` | sim | string |  |  |
| `token_type` | não | string | default="bearer" |  |

Esquema JSON completo:

```json
{
  "properties": {
    "access_token": {
      "type": "string",
      "title": "Access Token"
    },
    "token_type": {
      "type": "string",
      "title": "Token Type",
      "default": "bearer"
    }
  },
  "type": "object",
  "required": [
    "access_token"
  ],
  "title": "Token",
  "description": "Schema for JWT token response"
}
```

<a id="model-transcriptsegment"></a>

### TranscriptSegment

Trecho transcrito, com início e fim em segundos da mídia

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `start` | sim | number |  |  |
| `end` | sim | number |  |  |
| `text` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "start": {
      "type": "number",
      "title": "Start"
    },
    "end": {
      "type": "number",
      "title": "End"
    },
    "text": {
      "type": "string",
      "title": "Text"
    }
  },
  "type": "object",
  "required": [
    "start",
    "end",
    "text"
  ],
  "title": "TranscriptSegment",
  "description": "Trecho transcrito, com início e fim em segundos da mídia"
}
```

<a id="model-transcriptspeaker"></a>

### TranscriptSpeaker

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string |  |  |
| `label` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "title": "Id"
    },
    "label": {
      "type": "string",
      "title": "Label"
    }
  },
  "type": "object",
  "required": [
    "id",
    "label"
  ],
  "title": "TranscriptSpeaker"
}
```

<a id="model-uploadfolderinfo"></a>

### UploadFolderInfo

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string |  |  |
| `name` | sim | string |  |  |
| `created` | sim | boolean |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "created": {
      "type": "boolean",
      "title": "Created"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "created"
  ],
  "title": "UploadFolderInfo"
}
```

<a id="model-uploadprojectinfo"></a>

### UploadProjectInfo

Where an upload went (spec 0004): the project and how it was chosen.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string |  |  |
| `name` | sim | string |  |  |
| `created` | sim | boolean |  | true when this upload created the project (get-or-add) |
| `source` | sim | string | enum=["request", "api_key", "fallback"] | request: named in the request; api_key: the key's bound project; fallback: UPLOAD_FALLBACK_PROJECT (emergency valve) |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "title": "Id"
    },
    "name": {
      "type": "string",
      "title": "Name"
    },
    "created": {
      "type": "boolean",
      "title": "Created",
      "description": "true when this upload created the project (get-or-add)"
    },
    "source": {
      "type": "string",
      "enum": [
        "request",
        "api_key",
        "fallback"
      ],
      "title": "Source",
      "description": "request: named in the request; api_key: the key's bound project; fallback: UPLOAD_FALLBACK_PROJECT (emergency valve)"
    }
  },
  "type": "object",
  "required": [
    "id",
    "name",
    "created",
    "source"
  ],
  "title": "UploadProjectInfo",
  "description": "Where an upload went (spec 0004): the project and how it was chosen."
}
```

<a id="model-usercreate"></a>

### UserCreate

Schema for user registration

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `email` | sim | string |  |  |
| `username` | sim | string | minLength=3; maxLength=50 |  |
| `password` | sim | string | minLength=8; maxLength=20 |  |
| `setup_token` | não | string / null |  | Installation setup token; only read when creating the root user |

Esquema JSON completo:

```json
{
  "properties": {
    "email": {
      "type": "string",
      "title": "Email",
      "example": "user@example.com"
    },
    "username": {
      "type": "string",
      "maxLength": 50,
      "minLength": 3,
      "title": "Username",
      "example": "testuser"
    },
    "password": {
      "type": "string",
      "maxLength": 20,
      "minLength": 8,
      "title": "Password",
      "example": "SecurePass123"
    },
    "setup_token": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 256
        },
        {
          "type": "null"
        }
      ],
      "title": "Setup Token",
      "description": "Installation setup token; only read when creating the root user"
    }
  },
  "type": "object",
  "required": [
    "email",
    "username",
    "password"
  ],
  "title": "UserCreate",
  "description": "Schema for user registration"
}
```

<a id="model-userresponse"></a>

### UserResponse

Schema for user response

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `id` | sim | string (uuid) |  |  |
| `email` | sim | string |  |  |
| `username` | sim | string |  |  |
| `is_active` | sim | boolean |  |  |
| `created_at` | sim | string (date-time) |  |  |
| `is_admin` | não | boolean | default=false |  |
| `is_root` | não | boolean | default=false |  |
| `permissions` | não | array de string | default=[] |  |
| `engine_access_enabled` | não | boolean | default=false |  |
| `bootstrap` | não | boolean | default=false |  |
| `platform_roles` | não | array de string | default=[] |  |

Esquema JSON completo:

```json
{
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "title": "Id"
    },
    "email": {
      "type": "string",
      "title": "Email"
    },
    "username": {
      "type": "string",
      "title": "Username"
    },
    "is_active": {
      "type": "boolean",
      "title": "Is Active"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "title": "Created At"
    },
    "is_admin": {
      "type": "boolean",
      "title": "Is Admin",
      "default": false
    },
    "is_root": {
      "type": "boolean",
      "title": "Is Root",
      "default": false
    },
    "permissions": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Permissions",
      "default": []
    },
    "engine_access_enabled": {
      "type": "boolean",
      "title": "Engine Access Enabled",
      "default": false
    },
    "bootstrap": {
      "type": "boolean",
      "title": "Bootstrap",
      "default": false
    },
    "platform_roles": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Platform Roles",
      "default": []
    }
  },
  "type": "object",
  "required": [
    "id",
    "email",
    "username",
    "is_active",
    "created_at"
  ],
  "title": "UserResponse",
  "description": "Schema for user response"
}
```

<a id="model-validationerror"></a>

### ValidationError

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `loc` | sim | array de string / integer |  |  |
| `msg` | sim | string |  |  |
| `type` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "loc": {
      "items": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "integer"
          }
        ]
      },
      "type": "array",
      "title": "Location"
    },
    "msg": {
      "type": "string",
      "title": "Message"
    },
    "type": {
      "type": "string",
      "title": "Error Type"
    }
  },
  "type": "object",
  "required": [
    "loc",
    "msg",
    "type"
  ],
  "title": "ValidationError"
}
```

<a id="model-version"></a>

### Version

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | sim | integer | minimum=0.0 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "version": {
      "type": "integer",
      "minimum": 0.0,
      "title": "Version"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "version"
  ],
  "title": "Version"
}
```

<a id="model-versionbody"></a>

### VersionBody

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `version` | não | integer / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "version": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Version"
    }
  },
  "type": "object",
  "title": "VersionBody"
}
```

<a id="model-visioncapabilitiesresponse"></a>

### VisionCapabilitiesResponse

Resposta de `GET /images/capabilities`.

Respondida pelo worker de visão, não pela API: a única resposta que vale
alguma coisa descreve o processo que realmente carrega o modelo.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `enabled` | sim | boolean |  |  |
| `provider` | sim | string |  |  |
| `model_id` | sim | string |  |  |
| `revision` | sim | string |  |  |
| `device_requested` | sim | string |  |  |
| `device_resolved` | sim | string |  |  |
| `torch_available` | sim | boolean |  |  |
| `cuda_available` | sim | boolean |  |  |
| `cuda_device_name` | não | string / null |  |  |
| `dependencies_installed` | sim | boolean |  |  |
| `model_downloaded` | sim | boolean |  |  |
| `model_loaded` | sim | boolean |  |  |
| `trust_remote_code` | sim | boolean |  |  |
| `reason` | não | string / null |  |  |
| `max_image_size_mb` | não | integer | default=10 |  |
| `caption_tasks` | não | array de string | default=["<MORE_DETAILED_CAPTION>", "<DETAILED_CAPTION>", "<CAPTION>"] |  |
| `default_caption_task` | não | string | default="<MORE_DETAILED_CAPTION>" |  |
| `tasks` | não | array de [VisionTaskInfo](#model-visiontaskinfo) |  |  |
| `generation_schema` | não | object | additionalProperties=true |  |
| `generation_defaults` | não | object | additionalProperties=true |  |
| `analysis_modes` | não | array de string | default=["single", "full"] |  |
| `full_profiles` | não | array de object |  |  |
| `faces` | não | object / null |  |  |
| `full_profile` | não | string | default="image-full-v1" |  |
| `full_limits` | não | object | default={"max_queries": 3, "max_regions": 4, "max_calls": 32, "deadline_seconds": 900}; additionalProperties=true |  |

Esquema JSON completo:

```json
{
  "properties": {
    "enabled": {
      "type": "boolean",
      "title": "Enabled"
    },
    "provider": {
      "type": "string",
      "title": "Provider"
    },
    "model_id": {
      "type": "string",
      "title": "Model Id"
    },
    "revision": {
      "type": "string",
      "title": "Revision"
    },
    "device_requested": {
      "type": "string",
      "title": "Device Requested"
    },
    "device_resolved": {
      "type": "string",
      "title": "Device Resolved"
    },
    "torch_available": {
      "type": "boolean",
      "title": "Torch Available"
    },
    "cuda_available": {
      "type": "boolean",
      "title": "Cuda Available"
    },
    "cuda_device_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Cuda Device Name"
    },
    "dependencies_installed": {
      "type": "boolean",
      "title": "Dependencies Installed"
    },
    "model_downloaded": {
      "type": "boolean",
      "title": "Model Downloaded"
    },
    "model_loaded": {
      "type": "boolean",
      "title": "Model Loaded"
    },
    "trust_remote_code": {
      "type": "boolean",
      "title": "Trust Remote Code"
    },
    "reason": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Reason"
    },
    "max_image_size_mb": {
      "type": "integer",
      "title": "Max Image Size Mb",
      "default": 10
    },
    "caption_tasks": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Caption Tasks",
      "default": [
        "<MORE_DETAILED_CAPTION>",
        "<DETAILED_CAPTION>",
        "<CAPTION>"
      ]
    },
    "default_caption_task": {
      "type": "string",
      "title": "Default Caption Task",
      "default": "<MORE_DETAILED_CAPTION>"
    },
    "tasks": {
      "items": {
        "$ref": "#/components/schemas/VisionTaskInfo"
      },
      "type": "array",
      "title": "Tasks"
    },
    "generation_schema": {
      "additionalProperties": true,
      "type": "object",
      "title": "Generation Schema"
    },
    "generation_defaults": {
      "additionalProperties": true,
      "type": "object",
      "title": "Generation Defaults"
    },
    "analysis_modes": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Analysis Modes",
      "default": [
        "single",
        "full"
      ]
    },
    "full_profiles": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "type": "array",
      "title": "Full Profiles"
    },
    "faces": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Faces"
    },
    "full_profile": {
      "type": "string",
      "title": "Full Profile",
      "default": "image-full-v1"
    },
    "full_limits": {
      "additionalProperties": true,
      "type": "object",
      "title": "Full Limits",
      "default": {
        "max_queries": 3,
        "max_regions": 4,
        "max_calls": 32,
        "deadline_seconds": 900
      }
    }
  },
  "type": "object",
  "required": [
    "enabled",
    "provider",
    "model_id",
    "revision",
    "device_requested",
    "device_resolved",
    "torch_available",
    "cuda_available",
    "dependencies_installed",
    "model_downloaded",
    "model_loaded",
    "trust_remote_code"
  ],
  "title": "VisionCapabilitiesResponse",
  "description": "Resposta de `GET /images/capabilities`.\n\nRespondida pelo worker de visão, não pela API: a única resposta que vale\nalguma coisa descreve o processo que realmente carrega o modelo."
}
```

<a id="model-visiongenerationoptions"></a>

### VisionGenerationOptions

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `max_new_tokens` | não | integer / null | default=null | Limite de tokens gerados (contexto do checkpoint integrado: 1024); omitido usa a configuração do worker. |
| `num_beams` | não | integer / null | default=null | Número de candidatos na busca; omitido usa a configuração do worker. |
| `do_sample` | não | boolean | default=false | Amostrar o próximo token em vez de usar busca determinística. |
| `temperature` | não | number | default=1.0; maximum=2; exclusiveMinimum=0 | Variação da amostragem; utilizada quando do_sample=true. |
| `top_p` | não | number | default=1.0; maximum=1; exclusiveMinimum=0 | Fração acumulada de probabilidade na amostragem. |
| `top_k` | não | integer | default=50; minimum=0; maximum=100 | Quantidade de candidatos na amostragem; zero não limita. |
| `repetition_penalty` | não | number | default=1.0; minimum=0.5; maximum=3 | Penalidade de tokens repetidos. |
| `length_penalty` | não | number | default=1.0; minimum=-2; maximum=2 | Preferência por sequências longas na busca por beams. |
| `no_repeat_ngram_size` | não | integer | default=0; minimum=0; maximum=20 | Impedir repetição de sequências deste tamanho; zero desativa. |
| `early_stopping` | não | boolean / string | default=false | Critério de parada da busca por beams. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "max_new_tokens": {
      "anyOf": [
        {
          "maximum": 1024,
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Limite de tokens gerados (contexto do checkpoint integrado: 1024); omitido usa a configuração do worker.",
      "title": "Max New Tokens"
    },
    "num_beams": {
      "anyOf": [
        {
          "maximum": 8,
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Número de candidatos na busca; omitido usa a configuração do worker.",
      "title": "Num Beams"
    },
    "do_sample": {
      "default": false,
      "description": "Amostrar o próximo token em vez de usar busca determinística.",
      "title": "Do Sample",
      "type": "boolean"
    },
    "temperature": {
      "default": 1.0,
      "description": "Variação da amostragem; utilizada quando do_sample=true.",
      "exclusiveMinimum": 0,
      "maximum": 2,
      "title": "Temperature",
      "type": "number"
    },
    "top_p": {
      "default": 1.0,
      "description": "Fração acumulada de probabilidade na amostragem.",
      "exclusiveMinimum": 0,
      "maximum": 1,
      "title": "Top P",
      "type": "number"
    },
    "top_k": {
      "default": 50,
      "description": "Quantidade de candidatos na amostragem; zero não limita.",
      "maximum": 100,
      "minimum": 0,
      "title": "Top K",
      "type": "integer"
    },
    "repetition_penalty": {
      "default": 1.0,
      "description": "Penalidade de tokens repetidos.",
      "maximum": 3,
      "minimum": 0.5,
      "title": "Repetition Penalty",
      "type": "number"
    },
    "length_penalty": {
      "default": 1.0,
      "description": "Preferência por sequências longas na busca por beams.",
      "maximum": 2,
      "minimum": -2,
      "title": "Length Penalty",
      "type": "number"
    },
    "no_repeat_ngram_size": {
      "default": 0,
      "description": "Impedir repetição de sequências deste tamanho; zero desativa.",
      "maximum": 20,
      "minimum": 0,
      "title": "No Repeat Ngram Size",
      "type": "integer"
    },
    "early_stopping": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "const": "never",
          "type": "string"
        }
      ],
      "default": false,
      "description": "Critério de parada da busca por beams.",
      "title": "Early Stopping"
    }
  },
  "title": "VisionGenerationOptions",
  "type": "object"
}
```

<a id="model-visionmodelinfo"></a>

### VisionModelInfo

Qual modelo, em qual revisão e em qual device produziu esta resposta.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `model_id` | sim | string |  |  |
| `revision` | sim | string |  |  |
| `device` | sim | string |  |  |
| `dtype` | sim | string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "model_id": {
      "type": "string",
      "title": "Model Id"
    },
    "revision": {
      "type": "string",
      "title": "Revision"
    },
    "device": {
      "type": "string",
      "title": "Device"
    },
    "dtype": {
      "type": "string",
      "title": "Dtype"
    }
  },
  "type": "object",
  "required": [
    "model_id",
    "revision",
    "device",
    "dtype"
  ],
  "title": "VisionModelInfo",
  "description": "Qual modelo, em qual revisão e em qual device produziu esta resposta."
}
```

<a id="model-visiontaskinfo"></a>

### VisionTaskInfo

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `task` | sim | string | enum=["<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>", "<OCR>", "<OCR_WITH_REGION>", "<OD>", "<DENSE_REGION_CAPTION>", "<REGION_PROPOSAL>", "<CAPTION_TO_PHRASE_GROUNDING>", "<REFERRING_EXPRESSION_SEGMENTATION>", "<REGION_TO_SEGMENTATION>", "<OPEN_VOCABULARY_DETECTION>", "<REGION_TO_CATEGORY>", "<REGION_TO_DESCRIPTION>", "<REGION_TO_OCR>"] |  |
| `label` | sim | string |  |  |
| `output` | sim | string | enum=["text", "ocr", "boxes", "polygons", "mixed"] |  |
| `input` | sim | string | enum=["none", "text", "region"] |  |

Esquema JSON completo:

```json
{
  "properties": {
    "task": {
      "type": "string",
      "enum": [
        "<CAPTION>",
        "<DETAILED_CAPTION>",
        "<MORE_DETAILED_CAPTION>",
        "<OCR>",
        "<OCR_WITH_REGION>",
        "<OD>",
        "<DENSE_REGION_CAPTION>",
        "<REGION_PROPOSAL>",
        "<CAPTION_TO_PHRASE_GROUNDING>",
        "<REFERRING_EXPRESSION_SEGMENTATION>",
        "<REGION_TO_SEGMENTATION>",
        "<OPEN_VOCABULARY_DETECTION>",
        "<REGION_TO_CATEGORY>",
        "<REGION_TO_DESCRIPTION>",
        "<REGION_TO_OCR>"
      ],
      "title": "Task"
    },
    "label": {
      "type": "string",
      "title": "Label"
    },
    "output": {
      "type": "string",
      "enum": [
        "text",
        "ocr",
        "boxes",
        "polygons",
        "mixed"
      ],
      "title": "Output"
    },
    "input": {
      "type": "string",
      "enum": [
        "none",
        "text",
        "region"
      ],
      "title": "Input"
    }
  },
  "type": "object",
  "required": [
    "task",
    "label",
    "output",
    "input"
  ],
  "title": "VisionTaskInfo"
}
```

<a id="model-when"></a>

### When

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `min_wait_seconds` | não | integer / null |  |  |
| `min_backlog` | não | integer / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "min_wait_seconds": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 604800.0,
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Min Wait Seconds"
    },
    "min_backlog": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 100000.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Min Backlog"
    }
  },
  "type": "object",
  "title": "When"
}
```
