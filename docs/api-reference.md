# Referência completa dos endpoints

Gerado do OpenAPI da aplicação por `scripts/generate_api_docs.py`. Não edite este arquivo à mão.

API `1.0.0`: **149 operações HTTP** e **1 WebSocket(s)**.

Base pública de desenvolvimento: `https://dev.ingestify.ai/api`. Os caminhos abaixo são relativos à base.

Guia publicado: [PT](https://dev.ingestify.ai/pt/docs/api-reference) / [EN](https://dev.ingestify.ai/docs/api-reference). [Swagger](https://dev.ingestify.ai/api/docs), [OpenAPI JSON](https://dev.ingestify.ai/api/openapi.json).

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
| POST | `/auth/login` | Público | Login |
| POST | `/auth/refresh` | JWT | Refresh Token |
| GET | `/auth/me` | JWT ou API key | Get Current User Info |
| GET | `/auth/registration-settings` | Público | Registration Settings |
| GET | `/admin/settings` | Administrador (JWT ou API key) | Read Settings |
| PATCH | `/admin/settings` | Administrador (JWT ou API key) | Update Settings |
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
| POST | `/projects` | JWT ou API key | Create Project |
| GET | `/projects/resolve` | JWT ou API key | Um nome de projeto casa com um projeto existente? |
| GET | `/projects/{project_id}/folders/resolve` | JWT ou API key | Um nome de pasta casa com uma pasta existente do projeto? |
| PATCH | `/projects/{project_id}` | JWT ou API key | Update Project |
| DELETE | `/projects/{project_id}` | JWT ou API key | Delete Project |
| POST | `/projects/{project_id}/folders` | JWT ou API key | Create Folder |
| PATCH | `/folders/{folder_id}` | JWT ou API key | Update Folder |
| DELETE | `/folders/{folder_id}` | JWT ou API key | Delete Folder |
| PATCH | `/jobs/{job_id}/location` | JWT ou API key | Move Job |
| POST | `/jobs/move` | JWT ou API key | Move Batch |
| GET | `/transcribe/live/sessions/capabilities` | JWT ou API key | Get Live Capabilities |
| POST | `/transcribe/live/sessions` | JWT ou API key | Create Session |
| GET | `/transcribe/live/sessions/{job_id}` | JWT ou API key | Session Status |
| DELETE | `/transcribe/live/sessions/{job_id}` | JWT ou API key | Cancel Session |
| POST | `/datalakes/discover` | JWT ou API key | Discover Connection |
| POST | `/datalakes/buckets` | JWT ou API key | Create Bucket |
| POST | `/datalakes/partition-preview` | JWT ou API key | Partition Preview |
| GET | `/datalakes` | JWT ou API key | List Connections |
| POST | `/datalakes` | JWT ou API key | Create Connection |
| PATCH | `/datalakes/{connection_id}` | JWT ou API key | Update Connection |
| DELETE | `/datalakes/{connection_id}` | JWT ou API key | Delete Connection |
| GET | `/datalakes/{connection_id}/buckets` | JWT ou API key | List Buckets |
| POST | `/datalakes/import` | JWT ou API key | Import Object |
| POST | `/datalakes/{connection_id}/test` | JWT ou API key | Test Connection |
| GET | `/datalakes/{connection_id}/objects` | JWT ou API key | List Objects |
| GET | `/jobs/{job_id}/datalake` | JWT ou API key | Get Delivery |
| POST | `/jobs/{job_id}/datalake/retry` | JWT ou API key | Retry Delivery |
| GET | `/documents/capabilities` | JWT ou API key | Controles e exportações do Docling |
| POST | `/upload` | JWT ou API key | Upload e converter arquivo |
| GET | `/audio/capabilities` | JWT ou API key | Capacidades e parâmetros do modelo de áudio configurado |
| POST | `/transcribe` | JWT ou API key | Transcrever áudio ou vídeo (STT, legendas VTT/SRT) |
| POST | `/convert` | JWT ou API key | Convert Document |
| GET | `/jobs/{job_id}` | JWT ou API key | Get Job Status |
| DELETE | `/jobs/{job_id}` | JWT ou API key | Deletar job |
| GET | `/jobs/{job_id}/result` | JWT ou API key | Get Job Result |
| GET | `/jobs/{job_id}/assets/{name}` | JWT ou API key | Imagem privada do documento |
| GET | `/jobs/{job_id}/pages/{page_number}/assets/{name}` | JWT ou API key | Imagem privada de uma página |
| GET | `/jobs/{job_id}/transcript/partial` | JWT ou API key | Get Partial Transcript |
| GET | `/jobs/{job_id}/pages` | JWT ou API key | Get Job Pages |
| GET | `/jobs/{job_id}/pages/{page_number}/status` | JWT ou API key | Status de página específica por número |
| GET | `/jobs/{job_id}/pages/{page_number}/result` | JWT ou API key | Resultado de página específica por número |
| GET | `/jobs` | JWT ou API key | Listar jobs do usuário |
| GET | `/search` | JWT ou API key | Buscar jobs por conteúdo |
| POST | `/jobs/{job_id}/pages/{page_number}/retry` | JWT ou API key | Retry de página que falhou |
| GET | `/jobs/{job_id}/pages/{page_number}/pdf` | JWT ou API key | URL temporária do PDF de uma página |
| GET | `/jobs/{job_id}/pages/{page_number}/pdf/content` | JWT ou API key | Prévia autenticada do PDF de uma página |
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

## Errors:
- 400: Email or username already exists
- 403: New account registration is disabled by an administrator
- 429: Too many registrations from this IP

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [UserCreate](#model-usercreate).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `email` | sim | string |  |  |
| `username` | sim | string | minLength=3; maxLength=50 |  |
| `password` | sim | string | minLength=8; maxLength=20 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 201 | application/json | [UserResponse](#model-userresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

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
User object with id, email, username, is_active, created_at

## Errors:
- 401: Not authenticated or invalid token/API key

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [UserResponse](#model-userresponse) | Successful Response |

## Platform settings

### GET /auth/registration-settings

Registration Settings

Autorização: **Público**. Operation ID: `registration_settings_auth_registration_settings_get`.

Only the public registration policy; never exposes internal configuration.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [RegistrationSettings](#model-registrationsettings) | Successful Response |

### GET /admin/settings

Read Settings

Autorização: **Administrador (JWT ou API key)**. Operation ID: `read_settings_admin_settings_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [RegistrationSettings](#model-registrationsettings) | Successful Response |

### PATCH /admin/settings

Update Settings

Autorização: **Administrador (JWT ou API key)**. Operation ID: `update_settings_admin_settings_patch`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [RegistrationSettings](#model-registrationsettings).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `signup_enabled` | sim | boolean |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [RegistrationSettings](#model-registrationsettings) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

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

Retorna uma lista direta de chaves, sem o segredo, incluindo o vínculo project.

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

Retorna a chave completa apenas nesta criação. project ou project_id são opcionais e mutuamente exclusivos. O vínculo é usado em novos jobs autenticados somente pela API key, sem projeto explícito.

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

project_id é obrigatório: ID de projeto próprio altera o vínculo; null remove o vínculo.

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

This is useful when multiple pages failed due to temporary issues
and you want to retry them all at once instead of individually.

Args:
    job_id: The job ID whose failed pages should be retried

Returns:
    Number of pages queued for retry

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
| `face_options` | não | [FaceRequestOptions](#model-facerequestoptions) |  |  |
| `wait` | não | boolean | default=false |  |
| `datalake` | não | [Destination](#model-destination) / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 202 | application/json | [FaceAnalyzeResponse](#model-faceanalyzeresponse) / [ImageFullQueuedResponse](#model-imagefullqueuedresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /images/faces/upload

Upload de imagem para detecção facial e expressões

Autorização: **JWT ou API key**. Operation ID: `upload_images_faces_upload_post`.

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

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 202 | application/json | [FaceAnalyzeResponse](#model-faceanalyzeresponse) / [ImageFullQueuedResponse](#model-imagefullqueuedresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

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

mode=single (padrão) executa uma tarefa; mode=full compõe as 15 famílias, exige Idempotency-Key e aceita full_options/datalake. Mesma chave+payload retorna o mesmo job; divergência 409; job excluído 410. Full retorna 202 por padrão e resultados partial/failed/cancelled continuam consultáveis.

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
| 409 | — | objeto livre | Full: Idempotency-Key utilizada com outra solicitação. |
| 410 | — | objeto livre | Full: job desta chave foi excluído; envie uma chave nova. |

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

Mesmas regras de /images/analyze; full_options e datalake são campos JSON. mode=full rejeita presença explícita dos campos single task/text_input/region/generation.

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
| 409 | — | objeto livre | Full: Idempotency-Key utilizada com outra solicitação. |
| 410 | — | objeto livre | Full: job desta chave foi excluído; envie uma chave nova. |

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

Somente Full Analysis do dono. Pedido idempotente: 202 em andamento; 200 terminal. Checkpoints já concluídos são preservados; não cancela tarefas single.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |
| 202 | — | objeto livre | Cancelamento solicitado, aguardando persistência dos checkpoints. |

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | array de object | Successful Response |

### GET /admin/engines

List engines

Autorização: **JWT**. Operation ID: `list_engines_admin_engines_get`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | array de object | Successful Response |

### GET /admin/engines/{engine_id}

One engine

Autorização: **JWT**. Operation ID: `get_engine_admin_engines__engine_id__get`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | object | Successful Response |

## Admin - Engine control

### POST /admin/engines

Connection

Autorização: **Administrador (somente JWT)**. Operation ID: `connection_admin_engines_post`.

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/engines/{engine_id}/capabilities

Caps

Autorização: **JWT**. Operation ID: `caps_admin_engines__engine_id__capabilities_get`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/engines/{engine_id}/runtime-profile

Get Profile

Autorização: **JWT**. Operation ID: `get_profile_admin_engines__engine_id__runtime_profile_get`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT de administrador. API keys são recusadas, inclusive quando enviadas junto com o JWT.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Exige header Idempotency-Key e plan_id/plan_hash de um plano válido. confirm_paid_operation=true confirma custos quando o plano exige; retorna 202.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

SSE: text/event-stream, cursor after, eventos operation com id=seq. A conexão termina em até 60 segundos ou ao concluir; reconecte com o último seq. JWT revalidado a cada poll.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | sim | string |  |  |
| `after` | query | não | integer | default=0 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | text/event-stream | string | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /admin/engine-operations/{operation_id}/recover

Recover

Autorização: **JWT**. Operation ID: `recover_admin_engine_operations__operation_id__recover_post`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/execution-profiles

Profiles

Autorização: **JWT**. Operation ID: `profiles_admin_execution_profiles_get`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /admin/execution-profiles

Create

Autorização: **JWT**. Operation ID: `create_admin_execution_profiles_post`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /admin/access/policies

Policy Create

Autorização: **JWT**. Operation ID: `policy_create_admin_access_policies_post`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/access/subjects

Subjects

Autorização: **JWT**. Operation ID: `subjects_admin_access_subjects_get`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/access/grants

Grants

Autorização: **JWT**. Operation ID: `grants_admin_access_grants_get`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /admin/access/grants

Grant

Autorização: **JWT**. Operation ID: `grant_admin_access_grants_post`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### PUT /admin/access/engine-attributes/{id}

Classify

Autorização: **JWT**. Operation ID: `classify_admin_access_engine_attributes__id__put`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### PUT /admin/access/resources

Qualify

Autorização: **JWT**. Operation ID: `qualify_admin_access_resources_put`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### GET /admin/access/installation-principals

Principals

Autorização: **JWT**. Operation ID: `principals_admin_access_installation_principals_get`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |

### POST /admin/access/installation-principals

Principal Create

Autorização: **JWT**. Operation ID: `principal_create_admin_access_installation_principals_post`.

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

Exige sessão JWT; API keys são recusadas, inclusive junto com JWT. O servidor valida papéis e escopos RBAC/ABAC atuais. Biblioteca e IAM dependem de ENGINE_ACCESS_ENABLED. Recursos fora do escopo não são expostos; configuração, planos e execução mantêm seus gates próprios.

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

## Engine hosts

### POST /internal/engine-hosts/{host_id}/heartbeat

Host Heartbeat

Autorização: **X-Engine-Host-Token do host**. Operation ID: `host_heartbeat_internal_engine_hosts__host_id__heartbeat_post`.

Exige X-Engine-Host-Token correspondente ao host_id. Depende de ENGINE_CONTROL_ENABLED; retorna 503 quando desabilitado.

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

Exige X-Engine-Host-Token correspondente ao host_id. Depende de ENGINE_CONTROL_ENABLED; retorna 503 quando desabilitado.

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

Exige X-Engine-Host-Token correspondente ao host_id. Depende de ENGINE_CONTROL_ENABLED; retorna 503 quando desabilitado.

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

Exige X-Engine-Host-Token correspondente ao host_id. Depende de ENGINE_CONTROL_ENABLED; retorna 503 quando desabilitado.

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

Exige X-Engine-Host-Token correspondente ao host_id. Depende de ENGINE_CONTROL_ENABLED; retorna 503 quando desabilitado.

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

### POST /projects

Create Project

Autorização: **JWT ou API key**. Operation ID: `create_project_projects_post`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [NameBody](#model-namebody).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | sim | string | minLength=1; maxLength=100 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Recurso equivalente já existente (get-or-add). |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |
| 201 | application/json | objeto livre | Recurso criado (get-or-add). |

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

### PATCH /projects/{project_id}

Update Project

Autorização: **JWT ou API key**. Operation ID: `update_project_projects__project_id__patch`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ProjectPatch](#model-projectpatch).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | não | string / null |  |  |
| `description` | não | string / null |  |  |
| `archived` | não | boolean / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### DELETE /projects/{project_id}

Delete Project

Autorização: **JWT ou API key**. Operation ID: `delete_project_projects__project_id__delete`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 204 | — | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /projects/{project_id}/folders

Create Folder

Autorização: **JWT ou API key**. Operation ID: `create_folder_projects__project_id__folders_post`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [NameBody](#model-namebody).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | sim | string | minLength=1; maxLength=100 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Recurso equivalente já existente (get-or-add). |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |
| 201 | application/json | objeto livre | Recurso criado (get-or-add). |

### PATCH /folders/{folder_id}

Update Folder

Autorização: **JWT ou API key**. Operation ID: `update_folder_folders__folder_id__patch`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `folder_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [NameBody](#model-namebody).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | sim | string | minLength=1; maxLength=100 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### DELETE /folders/{folder_id}

Delete Folder

Autorização: **JWT ou API key**. Operation ID: `delete_folder_folders__folder_id__delete`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `folder_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 204 | — | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### PATCH /jobs/{job_id}/location

Move Job

Autorização: **JWT ou API key**. Operation ID: `move_job_jobs__job_id__location_patch`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [LocationBody](#model-locationbody).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `project_id` | sim | string | minLength=1; maxLength=36 |  |
| `folder_id` | não | string / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### POST /jobs/move

Move Batch

Autorização: **JWT ou API key**. Operation ID: `move_batch_jobs_move_post`.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [MoveBody](#model-movebody).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `project_id` | sim | string | minLength=1; maxLength=36 |  |
| `folder_id` | não | string / null |  |  |
| `job_ids` | sim | array de string | minItems=1; maxItems=100 |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Live transcription

### GET /transcribe/live/sessions/capabilities

Get Live Capabilities

Autorização: **JWT ou API key**. Operation ID: `get_live_capabilities_transcribe_live_sessions_capabilities_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [LiveCapabilities](#model-livecapabilities) | Successful Response |

### POST /transcribe/live/sessions

Create Session

Autorização: **JWT ou API key**. Operation ID: `create_session_transcribe_live_sessions_post`.

JSON, projeto obrigatório salvo API key vinculada. datalake aceita partitioning e partition_values. Retorna ticket descartável com validade de 60 segundos e URL WebSocket. Live depende da configuração, prontidão do worker e capacidade.

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
| `language` | não | string | default="pt"; pattern="^[a-z]{2,3}$" |  |
| `options` | não | [LiveOptions](#model-liveoptions) |  |  |
| `audio` | não | [AudioFormat](#model-audioformat) |  |  |
| `datalake` | não | [Destination](#model-destination) / null |  |  |

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

## Datalakes

### POST /datalakes/discover

Discover Connection

Autorização: **JWT ou API key**. Operation ID: `discover_connection_datalakes_discover_post`.

Read buckets with draft settings, without creating or updating a connection.

Lista/verifica buckets sem salvar a conexão; aceita credenciais do rascunho ou connection_id do próprio usuário.

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

Cria o bucket/container imediatamente; cancelar o wizard não remove esse recurso. Retorna 409 para nome existente, 403 para permissão insuficiente, 502 se a criação não puder ser confirmada.

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

Prévia autenticada sem acessar storage. Ausência de partitioning herda a conexão. missing=require sem valor retorna 422. A data usa created_at do job no fuso configurado.

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

Quando config é enviada, substitui toda a configuração; preserve endpoint, região, buckets e padrões. Omitir credentials mantém as credenciais atuais. O provedor não muda.

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

### POST /datalakes/import

Import Object

Autorização: **JWT ou API key**. Operation ID: `import_object_datalakes_import_post`.

connection_id/bucket/key identificam a origem; datalake, se enviado, identifica o destino. Origem e destino podem ser conexões distintas. Retorna 202 e enfileira conversão ou transcrição conforme o arquivo. conversion_options tipado configura documentos; audio_options tipado configura áudio/vídeo com as mesmas operações/controles de /transcribe. Opções incompatíveis são rejeitadas antes do download.

Corpo obrigatório: sim.

Content-Type: `application/json`. Esquema: [ImportObject](#model-importobject).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `connection_id` | sim | string | minLength=1; maxLength=36 |  |
| `bucket` | sim | string | minLength=1; maxLength=255 |  |
| `key` | sim | string | minLength=1; maxLength=1024 |  |
| `project` | não | string / null |  |  |
| `project_id` | não | string / null |  |  |
| `folder` | não | string / null |  |  |
| `folder_id` | não | string / null |  |  |
| `name` | não | string / null |  |  |
| `tags` | não | array de string |  |  |
| `docling_preset` | não | string | default="fast" |  |
| `conversion_options` | não | [DocumentOptions](#model-documentoptions) / null |  |  |
| `audio_options` | não | [AudioConversionOptions](#model-audioconversionoptions) / null |  |  |
| `datalake` | não | [Destination](#model-destination) / null |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 202 | application/json | objeto livre | Successful Response |
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

Entrega independente do processamento: pending/exporting/completed/failed. destination inclui partitioning, partition_values, partitions, resolved_path, dataset_path, schema_path e objects.

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

Repete somente a entrega do resultado preservado; não executa inferência. Usa estratégia, valores e caminhos congelados. Entregas concluídas não são regravadas automaticamente.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 202 | application/json | objeto livre | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

## Conversion

### GET /documents/capabilities

Controles e exportações do Docling

Autorização: **JWT ou API key**. Operation ID: `get_document_capabilities_documents_capabilities_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [DocumentCapabilities](#model-documentcapabilities) | Successful Response |

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

Multipart: file obrigatório; project/project_id obrigatório salvo API key vinculada. docling_preset padrão fast. Áudio/vídeo sem controles Docling usa os padrões de /transcribe; controles Docling em mídia retornam 422. Destino datalake explícito cria novo job e desativa reaproveitamento por checksum.

Corpo obrigatório: sim.

Content-Type: `multipart/form-data`. Esquema: [Body_upload_and_convert_upload_post](#model-body_upload_and_convert_upload_post).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `file` | sim | string (binary) |  | Arquivo para conversão (PDF, DOCX, HTML, etc.) |
| `name` | não | string / null |  | Nome de identificação (opcional, padrão: nome do arquivo) |
| `tags` | não | string / null |  | Tags separadas por vírgula (ex.: 'cliente-x, reunião'). Viram minúsculas; até 20 tags de até 50 caracteres. Enviar um arquivo repetido adiciona as tags ao job existente. |
| `docling_preset` | não | string / null | default="fast" | Quality/speed preset for PDF conversion: 'fast' (~35s/MB, text-only), 'balanced' (~70-105s/MB, with images), 'quality' (~350s/MB, with OCR) |
| `conversion_options` | não | string / null |  | JSON DocumentOptions: pipeline, formats, export_options e limites de conversão. |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |
| `datalake_connection_id` | não | string / null |  |  |
| `datalake_bucket` | não | string / null |  |  |
| `datalake_prefix` | não | string | default="" |  |
| `datalake_partitioning` | não | string / null |  | JSON da estratégia por solicitação; omitir herda a conexão. Ex.: {"mode":"custom","fields":[{"field":"custom","key":"client_id"}],"missing":"require","analytics":"jsonl"} |
| `datalake_partition_values` | não | string / null |  | JSON de valores por job. Chaves fora da estratégia preservam contexto no dataset sem criar diretórios. Ex.: {"client_id":"client-42","conversation_id":"chat-7","agent_id":"support-agent"} |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [JobCreatedResponse](#model-jobcreatedresponse) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /audio/capabilities

Capacidades e parâmetros do modelo de áudio configurado

Autorização: **JWT ou API key**. Operation ID: `get_audio_capabilities_audio_capabilities_get`.

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [AudioCapabilitiesResponse](#model-audiocapabilitiesresponse) | Successful Response |

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
  termina com sucesso; ficam só as transcrições. `DELETE /jobs/{job_id}` também
  apaga o arquivo de origem e as transcrições

## Projeto
Todo job pertence a um projeto: envie `project` (nome; criado se não existir) ou
`project_id`, e opcionalmente `folder`/`folder_id`. Uma API key vinculada a um
projeto dispensa o campo. Sem projeto: 422.

## Arquivo repetido
Reenviar arquivo idêntico (mesmo SHA-256) no mesmo projeto reaproveita somente
um job com a mesma configuração salva: provider/modelo, operação, decodificação,
timestamps, formato e retenção. Tags novas são somadas. Configuração diferente,
job falho ou legado sem configuração comprovável cria outro job.

## Controles do modelo
`decoding_options` é um objeto JSON serializado conforme AudioDecodingOptions.
Consulte GET /audio/capabilities para parâmetros aceitos pelo provider atual,
tarefas, padrões e limites. Parâmetros de outro provider retornam 422 antes
de criar o job. Turbo não suporta tradução; modelos aptos traduzem para inglês.
`operation=detect_language` identifica idioma sem produzir transcrição;
`operation=inspect` retorna metadados da faixa de áudio sem inferência.
A configuração fica em GET /jobs/{job_id}.configuration; o JSON do resultado
preserva as métricas e probabilidades disponibilizadas pelo provider.

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

Multipart. Todos os formatos são produzidos; output_format escolhe o padrão de leitura. Destino datalake explícito preserva valores por conversa e cria novo job. conversation_id não é chave de idempotência.

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
| `operation` | não | string | default="transcribe"; enum=["transcribe", "detect_language", "inspect"] | Transcrever/traduzir, detectar idioma ou inspecionar metadados do arquivo. |
| `decoding_options` | não | string / null |  | JSON AudioDecodingOptions. Controles aceitos e limites: GET /audio/capabilities. |
| `output_format` | não | string | default="markdown" | Formato padrão do resultado em /jobs/{job_id}/result: markdown, vtt, srt, txt ou json |
| `purge_source` | não | boolean | default=false | Apagar o áudio/vídeo enviado assim que a transcrição terminar (guarda só o texto) |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |
| `datalake_connection_id` | não | string / null |  |  |
| `datalake_bucket` | não | string / null |  |  |
| `datalake_prefix` | não | string | default="" |  |
| `datalake_partitioning` | não | string / null |  | JSON da estratégia por solicitação; omitir herda a conexão. Ex.: {"mode":"custom","fields":[{"field":"custom","key":"client_id"}],"missing":"require","analytics":"jsonl"} |
| `datalake_partition_values` | não | string / null |  | JSON de valores por job. Chaves fora da estratégia preservam contexto no dataset sem criar diretórios. Ex.: {"client_id":"client-42","conversation_id":"chat-7","agent_id":"support-agent"} |

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

## Formatos suportados
PDF, DOCX, DOC, HTML, PPTX, XLSX, RTF, ODT

## Retorno
Retorna imediatamente um `job_id` para consultar o progresso via `/jobs/{job_id}`

Multipart, não JSON. source_type=file exige file; url/gdrive/dropbox exigem source. gdrive/dropbox também exigem X-Source-Token. docling_preset e conversion_options são propagados em todas as fontes. audio_options (JSON AudioConversionOptions) escolhe áudio/vídeo, com controles validados por provider e fila própria. Extensão de mídia conhecida sem opções usa os padrões de áudio. Controles Docling não são ignorados quando a fonte revela mídia. Não combine audio_options e conversion_options. Aceita destino datalake e particionamento.

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
| `docling_preset` | não | string / null | default="fast" | Preset Docling: fast, balanced ou quality. |
| `conversion_options` | não | string / null |  | JSON DocumentOptions: pipeline, formats, export_options e limites de conversão. |
| `audio_options` | não | string / null |  | JSON AudioConversionOptions para processar áudio/vídeo de qualquer fonte. Incompatível com conversion_options. |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |
| `datalake_connection_id` | não | string / null |  |  |
| `datalake_bucket` | não | string / null |  |  |
| `datalake_prefix` | não | string | default="" |  |
| `datalake_partitioning` | não | string / null |  | JSON da estratégia por solicitação; omitir herda a conexão. Ex.: {"mode":"custom","fields":[{"field":"custom","key":"client_id"}],"missing":"require","analytics":"jsonl"} |
| `datalake_partition_values` | não | string / null |  | JSON de valores por job. Chaves fora da estratégia preservam contexto no dataset sem criar diretórios. Ex.: {"client_id":"client-42","conversation_id":"chat-7","agent_id":"support-agent"} |

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
- Para transcrições: o áudio/vídeo enviado e as transcrições guardadas no MinIO

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

### GET /jobs/{job_id}/result

Get Job Result

Autorização: **JWT ou API key**. Operation ID: `get_job_result_jobs__job_id__result_get`.

Recuperar resultado de qualquer tipo de job (main ou page individual)

## Permissões:
- Apenas o dono do job (verificado no MySQL) pode acessar o resultado.
  Jobs de outros usuários retornam 404.

Para jobs de transcrição (/transcribe), `?format=vtt|srt|txt|json` retorna o
arquivo no formato pedido (ex.: legenda WebVTT com `Content-Type: text/vtt`).

Para transcrições, format=markdown retorna o envelope JSON com result.markdown e metadata; vtt/srt/txt/json retornam o arquivo bruto. Sem format, vale o output_format original do job. Documentos: format=markdown retorna envelope JSON; demais exportações solicitadas retornam arquivo bruto. Sem format vale output_format. Configuração e exportações são duráveis. Job não concluído: 400; falho: 500; sem resultado: 404.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `format` | query | não | string / null |  | Para transcrições: markdown (JSON padrão), vtt, srt, txt ou json. Sem este parâmetro vale o output_format escolhido no /transcribe. |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/json | [JobResultResponse](#model-jobresultresponse) / object | Successful Response |
| 200 | text/vtt | string | Successful Response |
| 200 | application/x-subrip | string | Successful Response |
| 200 | text/plain | string | Successful Response |
| 200 | text/html | string | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |
| 202 | — | objeto livre | Full Analysis ainda em andamento, com poll_url/result_url. |

### GET /jobs/{job_id}/assets/{name}

Imagem privada do documento

Autorização: **JWT ou API key**. Operation ID: `document_asset_jobs__job_id__assets__name__get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `name` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | image/png | string (binary) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /jobs/{job_id}/pages/{page_number}/assets/{name}

Imagem privada de uma página

Autorização: **JWT ou API key**. Operation ID: `page_document_asset_jobs__job_id__pages__page_number__assets__name__get`.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `page_number` | path | sim | integer |  |  |
| `name` | path | sim | string |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | image/png | string (binary) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

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
| `format` | query | não | string / null |  | Formato Docling solicitado no upload; markdown retorna envelope JSON. |

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

Retorna objeto {total, limit, offset, jobs, counts}, não uma lista direta. tag é repetível e combina filtros com E. folder_id=root exige project_id.

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
- `preview_url`: prévia servida pela própria API, exige `Authorization`.
  Funciona em HTTPS mesmo quando o MinIO só tem endereço de rede local.
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

### GET /jobs/{job_id}/pages/{page_number}/pdf/content

Prévia autenticada do PDF de uma página

Autorização: **JWT ou API key**. Operation ID: `get_page_pdf_content_jobs__job_id__pages__page_number__pdf_content_get`.

Stream a split PDF through the API, including during conversion.

The browser sends Authorization to the API. Storage stays on the internal
network, so HTTPS previews work without a public MinIO endpoint or CORS.

Parâmetros:

| Nome | Local | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | sim | string |  |  |
| `page_number` | path | sim | integer |  |  |

Respostas declaradas:

| Status | Content-Type | Esquema | Descrição |
| --- | --- | --- | --- |
| 200 | application/pdf | string (binary) | Successful Response |
| 422 | application/json | [HTTPValidationError](#model-httpvalidationerror) | Validation Error |

### GET /health

Health Check

Autorização: **Público**. Operation ID: `health_check_health_get`.

Run blocking Redis/Elasticsearch/Celery probes in FastAPI's thread pool.

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

Ticket descartável obtido em POST /transcribe/live/sessions; primeiro frame JSON {"type":"authenticate","protocol":1,"ticket":"..."}. Não envie credenciais na URL.

Após session.ready, áudio binário PCM s16le, 16 kHz, mono, frames de 200 ms com cabeçalho little-endian de 12 bytes (seq:uint32, offset_samples:uint64). Eventos transcript.partial/final e session.progress/completed; finish/cancel em JSON. Sem retomada da sessão desconectada.

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

<a id="model-audiocapabilitiesresponse"></a>

### AudioCapabilitiesResponse

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `enabled` | sim | boolean |  |  |
| `provider` | sim | string |  |  |
| `model` | sim | string |  |  |
| `tasks` | sim | array de string |  |  |
| `operations` | não | array de string | default=["transcribe", "detect_language", "inspect"] |  |
| `formats` | não | array de string | default=["markdown", "vtt", "srt", "txt", "json"] |  |
| `max_audio_size_mb` | sim | integer |  |  |
| `max_video_size_mb` | sim | integer |  |  |
| `parameters_schema` | sim | object | additionalProperties=true |  |
| `restrictions` | sim | array de string |  |  |
| `workers_running` | não | boolean / null |  | Heartbeat de workers; não representa vaga livre. A fila continua aceitando jobs quando pausada. |
| `execution_reason` | não | string / null |  |  |

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
    "model": {
      "type": "string",
      "title": "Model"
    },
    "tasks": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Tasks"
    },
    "operations": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Operations",
      "default": [
        "transcribe",
        "detect_language",
        "inspect"
      ]
    },
    "formats": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Formats",
      "default": [
        "markdown",
        "vtt",
        "srt",
        "txt",
        "json"
      ]
    },
    "max_audio_size_mb": {
      "type": "integer",
      "title": "Max Audio Size Mb"
    },
    "max_video_size_mb": {
      "type": "integer",
      "title": "Max Video Size Mb"
    },
    "parameters_schema": {
      "additionalProperties": true,
      "type": "object",
      "title": "Parameters Schema"
    },
    "restrictions": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Restrictions"
    },
    "workers_running": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Workers Running",
      "description": "Heartbeat de workers; não representa vaga livre. A fila continua aceitando jobs quando pausada."
    },
    "execution_reason": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Execution Reason"
    }
  },
  "type": "object",
  "required": [
    "enabled",
    "provider",
    "model",
    "tasks",
    "max_audio_size_mb",
    "max_video_size_mb",
    "parameters_schema",
    "restrictions"
  ],
  "title": "AudioCapabilitiesResponse"
}
```

<a id="model-audioconversionoptions"></a>

### AudioConversionOptions

The same audio controls for uploads, external sources and bucket imports.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `operation` | não | string | default="transcribe"; enum=["transcribe", "detect_language", "inspect"] |  |
| `decoding` | não | [AudioDecodingOptions](#model-audiodecodingoptions) |  |  |
| `include_timestamps` | não | boolean | default=true |  |
| `include_word_timestamps` | não | boolean | default=false |  |
| `output_format` | não | string | default="markdown"; enum=["markdown", "vtt", "srt", "txt", "json"] |  |
| `purge_source` | não | boolean | default=false |  |

Esquema JSON completo:

```json
{
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "transcribe",
        "detect_language",
        "inspect"
      ],
      "title": "Operation",
      "default": "transcribe"
    },
    "decoding": {
      "$ref": "#/components/schemas/AudioDecodingOptions"
    },
    "include_timestamps": {
      "type": "boolean",
      "title": "Include Timestamps",
      "default": true
    },
    "include_word_timestamps": {
      "type": "boolean",
      "title": "Include Word Timestamps",
      "default": false
    },
    "output_format": {
      "type": "string",
      "enum": [
        "markdown",
        "vtt",
        "srt",
        "txt",
        "json"
      ],
      "title": "Output Format",
      "default": "markdown"
    },
    "purge_source": {
      "type": "boolean",
      "title": "Purge Source",
      "default": false
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "AudioConversionOptions",
  "description": "The same audio controls for uploads, external sources and bucket imports."
}
```

<a id="model-audiodecodingoptions"></a>

### AudioDecodingOptions

Controles públicos dos providers. Consulte /audio/capabilities antes de enviar.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `task` | não | string | default="transcribe"; enum=["transcribe", "translate"] |  |
| `language` | não | string / null | default=null | Idioma da gravação; omitido detecta automaticamente. |
| `log_progress` | não | boolean | default=false |  |
| `beam_size` | não | integer / null | default=5 |  |
| `best_of` | não | integer / null | default=5 |  |
| `patience` | não | number / null | default=1 |  |
| `length_penalty` | não | number / null | default=1 |  |
| `repetition_penalty` | não | number | default=1; maximum=5; exclusiveMinimum=0 |  |
| `no_repeat_ngram_size` | não | integer | default=0; minimum=0; maximum=100 |  |
| `temperature` | não | number / array de number | default=0.0 |  |
| `compression_ratio_threshold` | não | number / null | default=2.4 |  |
| `log_prob_threshold` | não | number / null | default=-1.0 |  |
| `logprob_threshold` | não | number / null | default=-1.0 | Nome do controle no provider openai-whisper. |
| `no_speech_threshold` | não | number / null | default=0.6 |  |
| `condition_on_previous_text` | não | boolean | default=true |  |
| `prompt_reset_on_temperature` | não | number | default=0.5; minimum=0; maximum=1 |  |
| `initial_prompt` | não | string / array de integer / null | default=null | Contexto textual; tokens numéricos somente no faster-whisper. |
| `carry_initial_prompt` | não | boolean | default=false |  |
| `prompt` | não | string / array de integer / null | default=null |  |
| `prefix` | não | string / array de integer / null | default=null |  |
| `suppress_blank` | não | boolean | default=true |  |
| `suppress_tokens` | não | string / array de integer | maxLength=10000 |  |
| `without_timestamps` | não | boolean | default=false |  |
| `max_initial_timestamp` | não | number | default=1; minimum=0; maximum=30 |  |
| `prepend_punctuations` | não | string | default="\"'“¿([{-" |  |
| `append_punctuations` | não | string | default="\"'.。,，!！?？:：”)]}、" |  |
| `multilingual` | não | boolean | default=false |  |
| `vad_filter` | não | boolean | default=true |  |
| `vad_parameters` | não | [VadParameters](#model-vadparameters) / null |  |  |
| `max_new_tokens` | não | integer / null | default=null |  |
| `sample_len` | não | integer / null | default=null |  |
| `chunk_length` | não | integer / null | default=null |  |
| `clip_timestamps` | não | string / array de number | default="0" |  |
| `hallucination_silence_threshold` | não | number / null | default=null |  |
| `hotwords` | não | string / null | default=null |  |
| `language_detection_threshold` | não | number / null | default=0.5 |  |
| `language_detection_segments` | não | integer | default=1; minimum=1; maximum=100 |  |
| `fp16` | não | boolean | default=true |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Controles públicos dos providers. Consulte /audio/capabilities antes de enviar.",
  "properties": {
    "task": {
      "default": "transcribe",
      "enum": [
        "transcribe",
        "translate"
      ],
      "title": "Task",
      "type": "string"
    },
    "language": {
      "anyOf": [
        {
          "pattern": "^[a-z]{2,3}$",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Idioma da gravação; omitido detecta automaticamente.",
      "title": "Language"
    },
    "log_progress": {
      "default": false,
      "title": "Log Progress",
      "type": "boolean"
    },
    "beam_size": {
      "anyOf": [
        {
          "maximum": 20,
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": 5,
      "title": "Beam Size"
    },
    "best_of": {
      "anyOf": [
        {
          "maximum": 20,
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": 5,
      "title": "Best Of"
    },
    "patience": {
      "anyOf": [
        {
          "exclusiveMinimum": 0,
          "maximum": 10,
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": 1,
      "title": "Patience"
    },
    "length_penalty": {
      "anyOf": [
        {
          "maximum": 2,
          "minimum": 0,
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": 1,
      "title": "Length Penalty"
    },
    "repetition_penalty": {
      "default": 1,
      "exclusiveMinimum": 0,
      "maximum": 5,
      "title": "Repetition Penalty",
      "type": "number"
    },
    "no_repeat_ngram_size": {
      "default": 0,
      "maximum": 100,
      "minimum": 0,
      "title": "No Repeat Ngram Size",
      "type": "integer"
    },
    "temperature": {
      "anyOf": [
        {
          "maximum": 1,
          "minimum": 0,
          "type": "number"
        },
        {
          "items": {
            "maximum": 1,
            "minimum": 0,
            "type": "number"
          },
          "maxItems": 100,
          "minItems": 1,
          "type": "array"
        }
      ],
      "default": 0.0,
      "title": "Temperature"
    },
    "compression_ratio_threshold": {
      "anyOf": [
        {
          "exclusiveMinimum": 0,
          "maximum": 1000000000.0,
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": 2.4,
      "title": "Compression Ratio Threshold"
    },
    "log_prob_threshold": {
      "anyOf": [
        {
          "maximum": 1000000000.0,
          "minimum": -1000000000.0,
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": -1.0,
      "title": "Log Prob Threshold"
    },
    "logprob_threshold": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": -1.0,
      "description": "Nome do controle no provider openai-whisper.",
      "title": "Logprob Threshold"
    },
    "no_speech_threshold": {
      "anyOf": [
        {
          "maximum": 1,
          "minimum": 0,
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": 0.6,
      "title": "No Speech Threshold"
    },
    "condition_on_previous_text": {
      "default": true,
      "title": "Condition On Previous Text",
      "type": "boolean"
    },
    "prompt_reset_on_temperature": {
      "default": 0.5,
      "maximum": 1,
      "minimum": 0,
      "title": "Prompt Reset On Temperature",
      "type": "number"
    },
    "initial_prompt": {
      "anyOf": [
        {
          "maxLength": 10000,
          "type": "string"
        },
        {
          "items": {
            "minimum": 0,
            "type": "integer"
          },
          "maxItems": 10000,
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Contexto textual; tokens numéricos somente no faster-whisper.",
      "title": "Initial Prompt"
    },
    "carry_initial_prompt": {
      "default": false,
      "title": "Carry Initial Prompt",
      "type": "boolean"
    },
    "prompt": {
      "anyOf": [
        {
          "maxLength": 10000,
          "type": "string"
        },
        {
          "items": {
            "minimum": 0,
            "type": "integer"
          },
          "maxItems": 10000,
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Prompt"
    },
    "prefix": {
      "anyOf": [
        {
          "maxLength": 10000,
          "type": "string"
        },
        {
          "items": {
            "minimum": 0,
            "type": "integer"
          },
          "maxItems": 10000,
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Prefix"
    },
    "suppress_blank": {
      "default": true,
      "title": "Suppress Blank",
      "type": "boolean"
    },
    "suppress_tokens": {
      "anyOf": [
        {
          "maxLength": 10000,
          "type": "string"
        },
        {
          "items": {
            "minimum": -1,
            "type": "integer"
          },
          "type": "array"
        }
      ],
      "maxLength": 10000,
      "title": "Suppress Tokens"
    },
    "without_timestamps": {
      "default": false,
      "title": "Without Timestamps",
      "type": "boolean"
    },
    "max_initial_timestamp": {
      "default": 1,
      "maximum": 30,
      "minimum": 0,
      "title": "Max Initial Timestamp",
      "type": "number"
    },
    "prepend_punctuations": {
      "default": "\"'“¿([{-",
      "title": "Prepend Punctuations",
      "type": "string"
    },
    "append_punctuations": {
      "default": "\"'.。,，!！?？:：”)]}、",
      "title": "Append Punctuations",
      "type": "string"
    },
    "multilingual": {
      "default": false,
      "title": "Multilingual",
      "type": "boolean"
    },
    "vad_filter": {
      "default": true,
      "title": "Vad Filter",
      "type": "boolean"
    },
    "vad_parameters": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/VadParameters"
        },
        {
          "type": "null"
        }
      ]
    },
    "max_new_tokens": {
      "anyOf": [
        {
          "maximum": 448,
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Max New Tokens"
    },
    "sample_len": {
      "anyOf": [
        {
          "maximum": 448,
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Sample Len"
    },
    "chunk_length": {
      "anyOf": [
        {
          "maximum": 30,
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Chunk Length"
    },
    "clip_timestamps": {
      "anyOf": [
        {
          "maxLength": 10000,
          "type": "string"
        },
        {
          "items": {
            "maximum": 1000000000.0,
            "minimum": 0,
            "type": "number"
          },
          "maxItems": 10000,
          "minItems": 1,
          "type": "array"
        }
      ],
      "default": "0",
      "title": "Clip Timestamps"
    },
    "hallucination_silence_threshold": {
      "anyOf": [
        {
          "exclusiveMinimum": 0,
          "maximum": 1000000000.0,
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Hallucination Silence Threshold"
    },
    "hotwords": {
      "anyOf": [
        {
          "maxLength": 10000,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Hotwords"
    },
    "language_detection_threshold": {
      "anyOf": [
        {
          "maximum": 1,
          "minimum": 0,
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": 0.5,
      "title": "Language Detection Threshold"
    },
    "language_detection_segments": {
      "default": 1,
      "maximum": 100,
      "minimum": 1,
      "title": "Language Detection Segments",
      "type": "integer"
    },
    "fp16": {
      "default": true,
      "title": "Fp16",
      "type": "boolean"
    }
  },
  "title": "AudioDecodingOptions",
  "type": "object"
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
| `docling_preset` | não | string / null | default="fast" | Preset Docling: fast, balanced ou quality. |
| `conversion_options` | não | string / null |  | JSON DocumentOptions: pipeline, formats, export_options e limites de conversão. |
| `audio_options` | não | string / null |  | JSON AudioConversionOptions para processar áudio/vídeo de qualquer fonte. Incompatível com conversion_options. |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |
| `datalake_connection_id` | não | string / null |  |  |
| `datalake_bucket` | não | string / null |  |  |
| `datalake_prefix` | não | string | default="" |  |
| `datalake_partitioning` | não | string / null |  | JSON da estratégia por solicitação; omitir herda a conexão. Ex.: {"mode":"custom","fields":[{"field":"custom","key":"client_id"}],"missing":"require","analytics":"jsonl"} |
| `datalake_partition_values` | não | string / null |  | JSON de valores por job. Chaves fora da estratégia preservam contexto no dataset sem criar diretórios. Ex.: {"client_id":"client-42","conversation_id":"chat-7","agent_id":"support-agent"} |

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
      "description": "Preset Docling: fast, balanced ou quality.",
      "default": "fast"
    },
    "conversion_options": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Conversion Options",
      "description": "JSON DocumentOptions: pipeline, formats, export_options e limites de conversão.",
      "x-options-schema": {
        "additionalProperties": false,
        "properties": {
          "pipeline": {
            "additionalProperties": true,
            "description": "Controles PdfPipelineOptions. Opções explícitas substituem o preset.",
            "title": "Pipeline",
            "type": "object",
            "x-options-schema": {
              "$defs": {
                "AcceleratorDevice": {
                  "description": "Devices to run model inference",
                  "enum": [
                    "auto",
                    "cpu",
                    "cuda",
                    "mps",
                    "xpu"
                  ],
                  "title": "AcceleratorDevice",
                  "type": "string"
                },
                "AcceleratorOptions": {
                  "additionalProperties": false,
                  "description": "Hardware acceleration configuration for model inference.\n\nCan be configured via environment variables with DOCLING_ prefix.",
                  "properties": {
                    "cuda_use_flash_attention2": {
                      "default": false,
                      "description": "Enable Flash Attention 2 optimization for CUDA devices. Provides significant speedup and memory reduction for transformer models on compatible NVIDIA GPUs (Ampere or newer). Requires flash-attn package installation. Can be set via DOCLING_CUDA_USE_FLASH_ATTENTION2 environment variable.",
                      "title": "Cuda Use Flash Attention2",
                      "type": "boolean"
                    },
                    "device": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "$ref": "#/$defs/AcceleratorDevice"
                        }
                      ],
                      "default": "auto",
                      "description": "Hardware device for model inference. Options: `auto` (automatic detection), `cpu` (CPU only), `cuda` (NVIDIA GPU), `cuda:N` (specific GPU), `mps` (Apple Silicon), `xpu` (Intel GPU). Auto mode selects the best available device. Can be set via DOCLING_DEVICE environment variable.",
                      "title": "Device"
                    },
                    "num_threads": {
                      "default": 4,
                      "description": "Number of CPU threads to use for model inference. Higher values can improve throughput on multi-core systems but may increase memory usage. Can be set via DOCLING_NUM_THREADS or OMP_NUM_THREADS environment variables. Recommended: number of physical CPU cores.",
                      "title": "Num Threads",
                      "type": "integer"
                    }
                  },
                  "title": "AcceleratorOptions",
                  "type": "object"
                },
                "ApiKserveV2ImageClassificationEngineOptions": {
                  "additionalProperties": false,
                  "description": "Runtime configuration for remote KServe v2 inference.",
                  "properties": {
                    "engine_type": {
                      "const": "api_kserve_v2",
                      "default": "api_kserve_v2",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "grpc_max_message_bytes": {
                      "default": 67108864,
                      "description": "Max send/receive gRPC message size in bytes.",
                      "minimum": 1,
                      "title": "Grpc Max Message Bytes",
                      "type": "integer"
                    },
                    "grpc_metadata": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "description": "Optional gRPC metadata for authentication/routing when transport='grpc'. No HTTP headers are reused in gRPC mode.",
                      "title": "Grpc Metadata",
                      "type": "object"
                    },
                    "grpc_use_binary_data": {
                      "default": true,
                      "description": "Whether to request/expect binary tensor payloads on gRPC output tensors. Set to False for servers that do not support binary_data output parameters.",
                      "title": "Grpc Use Binary Data",
                      "type": "boolean"
                    },
                    "grpc_use_tls": {
                      "default": false,
                      "description": "Whether to use TLS for the gRPC channel. When omitted, plain-text h2c is used.",
                      "title": "Grpc Use Tls",
                      "type": "boolean"
                    },
                    "headers": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "description": "Optional HTTP headers for authentication/routing when transport='http'.",
                      "title": "Headers",
                      "type": "object"
                    },
                    "model_name": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Remote model name registered in the KServe v2 endpoint. If omitted, a repo_id-derived default is used.",
                      "title": "Model Name"
                    },
                    "model_version": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Optional model version. If omitted, the server default is used.",
                      "title": "Model Version"
                    },
                    "request_parameters": {
                      "additionalProperties": true,
                      "description": "Optional top-level KServe v2 infer request parameters.",
                      "title": "Request Parameters",
                      "type": "object"
                    },
                    "timeout": {
                      "default": 60.0,
                      "description": "Per-request timeout in seconds for both HTTP and gRPC calls.",
                      "title": "Timeout",
                      "type": "number"
                    },
                    "top_k": {
                      "anyOf": [
                        {
                          "minimum": 1,
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Maximum number of classes to return. If None, all classes are returned.",
                      "title": "Top K"
                    },
                    "transport": {
                      "default": "grpc",
                      "description": "Transport protocol for KServe v2 calls. Use 'grpc' for binary tensor payloads (default), or 'http' for JSON REST.",
                      "enum": [
                        "grpc",
                        "http"
                      ],
                      "title": "Transport",
                      "type": "string"
                    },
                    "url": {
                      "description": "Endpoint URL for KServe v2 transport. For transport='http', use http(s)://host[:port] or plain host:port. For transport='grpc', use plain host:port.",
                      "title": "Url",
                      "type": "string"
                    }
                  },
                  "required": [
                    "url"
                  ],
                  "title": "ApiKserveV2ImageClassificationEngineOptions",
                  "type": "object"
                },
                "ApiModelConfig": {
                  "description": "API-specific model configuration.\n\nFor API engines, configuration is simpler - just params to send.",
                  "properties": {
                    "params": {
                      "additionalProperties": true,
                      "description": "API parameters (model name, max_tokens, etc.)",
                      "title": "Params",
                      "type": "object"
                    }
                  },
                  "title": "ApiModelConfig",
                  "type": "object"
                },
                "ApiVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Options for API-based VLM services.\n\nSupports multiple API variants:\n- Generic OpenAI-compatible API\n- Ollama\n- LM Studio\n- OpenAI",
                  "properties": {
                    "concurrency": {
                      "default": 1,
                      "description": "Number of concurrent requests",
                      "title": "Concurrency",
                      "type": "integer"
                    },
                    "engine_type": {
                      "const": "api",
                      "default": "api",
                      "description": "API variant to use",
                      "type": "string"
                    },
                    "headers": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "description": "HTTP headers for authentication",
                      "title": "Headers",
                      "type": "object"
                    },
                    "params": {
                      "additionalProperties": true,
                      "description": "Additional API parameters (model, max_tokens, etc.)",
                      "title": "Params",
                      "type": "object"
                    },
                    "timeout": {
                      "default": 60.0,
                      "description": "Request timeout in seconds",
                      "title": "Timeout",
                      "type": "number"
                    },
                    "url": {
                      "default": "http://localhost:11434/v1/chat/completions",
                      "description": "API endpoint URL",
                      "format": "uri",
                      "minLength": 1,
                      "title": "Url",
                      "type": "string"
                    }
                  },
                  "title": "ApiVlmEngineOptions",
                  "type": "object"
                },
                "AutoInlineVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Options for auto-selecting the best local inference engine.\n\nAutomatically selects the best available local engine based on:\n- Platform (macOS -> MLX, Linux/Windows -> Transformers/VLLM)\n- Available hardware (CUDA, MPS, CPU)\n- Model support",
                  "properties": {
                    "engine_type": {
                      "const": "auto_inline",
                      "default": "auto_inline",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "prefer_vllm": {
                      "default": false,
                      "description": "Prefer VLLM over Transformers when both are available on CUDA",
                      "title": "Prefer Vllm",
                      "type": "boolean"
                    }
                  },
                  "title": "AutoInlineVlmEngineOptions",
                  "type": "object"
                },
                "BaseImageClassificationEngineOptions": {
                  "description": "Base configuration shared across image-classification engines.",
                  "properties": {
                    "engine_type": {
                      "$ref": "#/$defs/ImageClassificationEngineType",
                      "description": "Type of inference engine to use"
                    },
                    "top_k": {
                      "anyOf": [
                        {
                          "minimum": 1,
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Maximum number of classes to return. If None, all classes are returned.",
                      "title": "Top K"
                    }
                  },
                  "required": [
                    "engine_type"
                  ],
                  "title": "BaseImageClassificationEngineOptions",
                  "type": "object"
                },
                "BaseLayoutOptions": {
                  "description": "Base options for document layout analysis models.\n\nLayout analysis detects the structural regions of a document page\n(text blocks, tables, figures, headers, etc.) and assigns content\ncells to those regions. This base class provides the shared controls\nfor empty-cluster retention and cell-assignment skipping.\n\nSee Also:\n    `LayoutOptions`: Default layout model configuration (Heron).\n    `LayoutObjectDetectionOptions`: Object-detection runtime layout\n        with preset support.",
                  "properties": {
                    "keep_empty_clusters": {
                      "default": false,
                      "description": "Retain empty clusters in layout analysis results. When False, clusters without content are removed. Enable for debugging or when empty regions are semantically important.",
                      "title": "Keep Empty Clusters",
                      "type": "boolean"
                    },
                    "skip_cell_assignment": {
                      "default": false,
                      "description": "Skip assignment of cells to table structures during layout analysis. When True, cells are detected but not associated with tables. Use for performance optimization when table structure is not needed.",
                      "title": "Skip Cell Assignment",
                      "type": "boolean"
                    }
                  },
                  "title": "BaseLayoutOptions",
                  "type": "object"
                },
                "BaseTableStructureOptions": {
                  "description": "Base options for table structure extraction models.\n\nServes as the abstract base for all table structure backends. Concrete\nimplementations (e.g., `TableStructureOptions` for TableFormer) inherit\nfrom this class and register their own `kind` discriminator.\n\nSee Also:\n    `TableStructureOptions`: Default TableFormer-based implementation.",
                  "properties": {},
                  "title": "BaseTableStructureOptions",
                  "type": "object"
                },
                "BaseVlmEngineOptions": {
                  "description": "Base configuration for VLM inference engines.\n\nEngine options are independent of model specifications and prompts.\nThey only control how the inference is executed.",
                  "properties": {
                    "engine_type": {
                      "$ref": "#/$defs/VlmEngineType",
                      "description": "Type of inference engine to use"
                    }
                  },
                  "required": [
                    "engine_type"
                  ],
                  "title": "BaseVlmEngineOptions",
                  "type": "object"
                },
                "ChartExtractionModelKind": {
                  "enum": [
                    "granite-vision",
                    "granite-vision-v4"
                  ],
                  "title": "ChartExtractionModelKind",
                  "type": "string"
                },
                "ChartExtractionModelOptions": {
                  "additionalProperties": false,
                  "properties": {
                    "chart2code": {
                      "default": false,
                      "title": "Chart2Code",
                      "type": "boolean"
                    },
                    "chart2csv": {
                      "default": true,
                      "title": "Chart2Csv",
                      "type": "boolean"
                    },
                    "chart2summary": {
                      "default": false,
                      "title": "Chart2Summary",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "chart_extraction",
                      "default": "chart_extraction",
                      "title": "Kind",
                      "type": "string"
                    },
                    "model": {
                      "$ref": "#/$defs/ChartExtractionModelKind",
                      "default": "granite-vision-v4"
                    }
                  },
                  "title": "ChartExtractionModelOptions",
                  "type": "object"
                },
                "CodeFormulaVlmOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for VLM-based code and formula extraction.\n\nThis stage uses vision-language models to extract code blocks and\nmathematical formulas from document images. Supports preset-based\nconfiguration via StagePresetMixin.\n\nExamples:\n    # Use CodeFormulaV2 preset\n    options = CodeFormulaVlmOptions.from_preset(\"codeformulav2\")\n\n    # Use Granite Docling preset\n    options = CodeFormulaVlmOptions.from_preset(\"granite_docling\")",
                  "properties": {
                    "engine_options": {
                      "anyOf": [
                        {
                          "$ref": "#/$defs/ApiVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/AutoInlineVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/MlxVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/TransformersVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/VllmVlmEngineOptions"
                        }
                      ],
                      "description": "Runtime configuration (transformers, mlx, api, etc.)"
                    },
                    "extract_code": {
                      "default": true,
                      "description": "Extract code blocks",
                      "title": "Extract Code",
                      "type": "boolean"
                    },
                    "extract_formulas": {
                      "default": true,
                      "description": "Extract mathematical formulas",
                      "title": "Extract Formulas",
                      "type": "boolean"
                    },
                    "max_size": {
                      "anyOf": [
                        {
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Maximum image dimension (width or height)",
                      "title": "Max Size"
                    },
                    "model_spec": {
                      "$ref": "#/$defs/VlmModelSpec",
                      "description": "Model specification with runtime-specific overrides"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Image scaling factor for preprocessing",
                      "title": "Scale",
                      "type": "number"
                    }
                  },
                  "required": [
                    "engine_options",
                    "model_spec"
                  ],
                  "title": "CodeFormulaVlmOptions",
                  "type": "object"
                },
                "DocumentPictureClassifierOptions": {
                  "additionalProperties": false,
                  "description": "Options for configuring the DocumentPictureClassifier stage.",
                  "properties": {
                    "engine_options": {
                      "anyOf": [
                        {
                          "$ref": "#/$defs/ApiKserveV2ImageClassificationEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/OnnxRuntimeImageClassificationEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/TransformersImageClassificationEngineOptions"
                        }
                      ],
                      "description": "Runtime configuration for the image-classification engine."
                    },
                    "kind": {
                      "const": "document_picture_classifier",
                      "default": "document_picture_classifier",
                      "title": "Engine",
                      "type": "string"
                    },
                    "model_spec": {
                      "$ref": "#/$defs/ImageClassificationModelSpec",
                      "description": "Image-classification model specification for picture classification."
                    }
                  },
                  "required": [
                    "engine_options"
                  ],
                  "title": "DocumentPictureClassifierOptions",
                  "type": "object"
                },
                "EasyOcrOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for EasyOCR engine.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "confidence_threshold": {
                      "default": 0.5,
                      "description": "Minimum confidence score for text recognition. Text with confidence below this threshold is filtered out. Range: 0.0-1.0. Lower values include more text but may reduce accuracy.",
                      "title": "Confidence Threshold",
                      "type": "number"
                    },
                    "download_enabled": {
                      "default": true,
                      "description": "Allow automatic download of EasyOCR models on first use. Disable for offline environments where models must be pre-installed.",
                      "title": "Download Enabled",
                      "type": "boolean"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "easyocr",
                      "default": "easyocr",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "fr",
                        "de",
                        "es",
                        "en"
                      ],
                      "description": "List of language codes for OCR. EasyOCR supports 80+ languages. Use ISO 639-1 codes (e.g., `en`, `fr`, `de`). Multiple languages can be specified for multilingual documents.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "model_storage_directory": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Directory path for storing downloaded EasyOCR models. If None, uses default EasyOCR cache location. Useful for offline environments or custom model management.",
                      "title": "Model Storage Directory"
                    },
                    "recog_network": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "default": "standard",
                      "description": "Recognition network architecture to use. Options: `standard` (default, balanced), `craft` (higher accuracy). Different networks may perform better on specific document types.",
                      "title": "Recog Network"
                    },
                    "suppress_mps_warnings": {
                      "default": true,
                      "description": "Suppress Metal Performance Shaders (MPS) warnings on macOS. Reduces console noise when using Apple Silicon GPUs with EasyOCR.",
                      "title": "Suppress Mps Warnings",
                      "type": "boolean"
                    },
                    "use_gpu": {
                      "anyOf": [
                        {
                          "type": "boolean"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Enable GPU acceleration for EasyOCR. If None, automatically detects and uses GPU if available. Set to False to force CPU-only processing.",
                      "title": "Use Gpu"
                    }
                  },
                  "title": "EasyOcrOptions",
                  "type": "object"
                },
                "EngineModelConfig": {
                  "description": "Engine-specific model configuration.\n\nAllows overriding model settings for specific engines.\nFor example, MLX might use a different repo_id than Transformers.",
                  "properties": {
                    "extra_config": {
                      "additionalProperties": true,
                      "description": "Additional engine-specific configuration",
                      "title": "Extra Config",
                      "type": "object"
                    },
                    "repo_id": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Override model repository ID for this engine",
                      "title": "Repo Id"
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
                      "description": "Override model revision for this engine",
                      "title": "Revision"
                    },
                    "torch_dtype": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Override torch dtype for this engine (e.g., 'bfloat16')",
                      "title": "Torch Dtype"
                    }
                  },
                  "title": "EngineModelConfig",
                  "type": "object"
                },
                "ImageClassificationEngineType": {
                  "description": "Supported inference engine types for image-classification models.",
                  "enum": [
                    "onnxruntime",
                    "transformers",
                    "api_kserve_v2"
                  ],
                  "title": "ImageClassificationEngineType",
                  "type": "string"
                },
                "ImageClassificationModelSpec": {
                  "description": "Specification for an image-classification model.",
                  "properties": {
                    "engine_overrides": {
                      "additionalProperties": {
                        "$ref": "#/$defs/EngineModelConfig"
                      },
                      "description": "Engine-specific configuration overrides",
                      "propertyNames": {
                        "$ref": "#/$defs/ImageClassificationEngineType"
                      },
                      "title": "Engine Overrides",
                      "type": "object"
                    },
                    "name": {
                      "description": "Human-readable model name",
                      "title": "Name",
                      "type": "string"
                    },
                    "repo_id": {
                      "description": "Default HuggingFace repository ID",
                      "title": "Repo Id",
                      "type": "string"
                    },
                    "revision": {
                      "default": "main",
                      "description": "Default model revision",
                      "title": "Revision",
                      "type": "string"
                    }
                  },
                  "required": [
                    "name",
                    "repo_id"
                  ],
                  "title": "ImageClassificationModelSpec",
                  "type": "object"
                },
                "KserveV2OcrOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for KServe v2-based OCR (e.g., Triton Inference Server).\n\nThis OCR engine connects to a remote KServe v2-compatible inference server\n(such as Triton) to perform OCR via gRPC or HTTP. It combines standard OCR\noptions with KServe v2 connection settings inherited from KserveV2OptionsMixin.\n\nThe engine handles custom preprocessing (RGB conversion, transpose, batching)\nto match the expected input format of typical OCR models deployed on KServe v2\nendpoints.\n\nSee Also:\n    `KserveV2OptionsMixin`: Provides all KServe v2 connection configuration.\n    `RapidOcrOptions`: Local OCR engine for comparison.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "grpc_max_message_bytes": {
                      "default": 67108864,
                      "description": "Max send/receive gRPC message size in bytes.",
                      "minimum": 1,
                      "title": "Grpc Max Message Bytes",
                      "type": "integer"
                    },
                    "grpc_metadata": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "description": "Optional gRPC metadata for authentication/routing when transport='grpc'. No HTTP headers are reused in gRPC mode.",
                      "title": "Grpc Metadata",
                      "type": "object"
                    },
                    "grpc_use_binary_data": {
                      "default": true,
                      "description": "Whether to request/expect binary tensor payloads on gRPC output tensors. Set to False for servers that do not support binary_data output parameters.",
                      "title": "Grpc Use Binary Data",
                      "type": "boolean"
                    },
                    "grpc_use_tls": {
                      "default": false,
                      "description": "Whether to use TLS for the gRPC channel. When omitted, plain-text h2c is used.",
                      "title": "Grpc Use Tls",
                      "type": "boolean"
                    },
                    "headers": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "description": "Optional HTTP headers for authentication/routing when transport='http'.",
                      "title": "Headers",
                      "type": "object"
                    },
                    "kind": {
                      "const": "kserve_v2_ocr",
                      "default": "kserve_v2_ocr",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "english",
                        "chinese"
                      ],
                      "description": "List of OCR languages. Note: Language selection depends on the deployed model. This parameter is passed to the server but may not be used by all models.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "model_name": {
                      "default": "ocr",
                      "description": "Remote model name registered in the KServe v2 endpoint.",
                      "title": "Model Name",
                      "type": "string"
                    },
                    "model_version": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Optional model version. If omitted, the server default is used.",
                      "title": "Model Version"
                    },
                    "request_parameters": {
                      "additionalProperties": true,
                      "description": "Optional top-level KServe v2 infer request parameters.",
                      "title": "Request Parameters",
                      "type": "object"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Image scale multiplier for OCR processing. Higher values increase resolution for better text recognition. Default 2.0 converts 72 DPI to 144 DPI.",
                      "exclusiveMinimum": 0.0,
                      "title": "Scale",
                      "type": "number"
                    },
                    "timeout": {
                      "default": 60.0,
                      "description": "Per-request timeout in seconds for both HTTP and gRPC calls.",
                      "title": "Timeout",
                      "type": "number"
                    },
                    "transport": {
                      "default": "grpc",
                      "description": "Transport protocol for KServe v2 calls. Use 'grpc' for binary tensor payloads (default), or 'http' for JSON REST.",
                      "enum": [
                        "grpc",
                        "http"
                      ],
                      "title": "Transport",
                      "type": "string"
                    },
                    "url": {
                      "description": "Endpoint URL for KServe v2 transport. For transport='http', use http(s)://host[:port] or plain host:port. For transport='grpc', use plain host:port.",
                      "title": "Url",
                      "type": "string"
                    }
                  },
                  "required": [
                    "url"
                  ],
                  "title": "KserveV2OcrOptions",
                  "type": "object"
                },
                "LayoutModelConfig": {
                  "description": "Configuration for document layout analysis models from HuggingFace.",
                  "properties": {
                    "model_path": {
                      "description": "Relative path within the repository to model artifacts. Empty string indicates artifacts are in the repository root. Used for repositories with multiple models or nested structures.",
                      "title": "Model Path",
                      "type": "string"
                    },
                    "name": {
                      "description": "Human-readable name identifier for the layout model. Used for logging, debugging, and model selection.",
                      "examples": [
                        "docling_layout_heron",
                        "docling_layout_egret_large"
                      ],
                      "title": "Name",
                      "type": "string"
                    },
                    "repo_id": {
                      "description": "HuggingFace repository ID where the model is hosted. Used to download model weights and configuration files from HuggingFace Hub.",
                      "examples": [
                        "docling-project/docling-layout-heron",
                        "docling-project/docling-layout-egret-large"
                      ],
                      "title": "Repo Id",
                      "type": "string"
                    },
                    "revision": {
                      "description": "Git revision (branch, tag, or commit hash) of the model repository to use. Allows pinning to specific model versions for reproducibility.",
                      "examples": [
                        "main",
                        "v1.0.0"
                      ],
                      "title": "Revision",
                      "type": "string"
                    },
                    "supported_devices": {
                      "default": [
                        "cpu",
                        "cuda",
                        "mps",
                        "xpu"
                      ],
                      "description": "List of hardware accelerators supported by this model. The model can only run on devices in this list.",
                      "items": {
                        "$ref": "#/$defs/AcceleratorDevice"
                      },
                      "title": "Supported Devices",
                      "type": "array"
                    }
                  },
                  "required": [
                    "name",
                    "repo_id",
                    "revision",
                    "model_path"
                  ],
                  "title": "LayoutModelConfig",
                  "type": "object"
                },
                "LayoutOptions": {
                  "additionalProperties": false,
                  "description": "Options for layout processing using Docling's built-in layout model.\n\nProvides configuration for the default layout analysis path, including\nmodel selection (e.g., Heron, Egret variants) and orphan cluster\ncreation for elements not assigned to any detected structure.\n\nNotes:\n    The default model is ``DOCLING_LAYOUT_HERON``. For higher accuracy\n    on complex documents, consider ``DOCLING_LAYOUT_EGRET_LARGE`` or\n    ``DOCLING_LAYOUT_EGRET_XLARGE``.",
                  "properties": {
                    "create_orphan_clusters": {
                      "default": true,
                      "description": "Create clusters for orphaned elements not assigned to any structure. When True, isolated text or elements are grouped into their own clusters. Recommended for complete document coverage.",
                      "title": "Create Orphan Clusters",
                      "type": "boolean"
                    },
                    "keep_empty_clusters": {
                      "default": false,
                      "description": "Retain empty clusters in layout analysis results. When False, clusters without content are removed. Enable for debugging or when empty regions are semantically important.",
                      "title": "Keep Empty Clusters",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "docling_layout_default",
                      "default": "docling_layout_default",
                      "title": "Engine",
                      "type": "string"
                    },
                    "model_spec": {
                      "$ref": "#/$defs/LayoutModelConfig",
                      "default": {
                        "model_path": "",
                        "name": "docling_layout_heron",
                        "repo_id": "docling-project/docling-layout-heron",
                        "revision": "main",
                        "supported_devices": [
                          "cpu",
                          "cuda",
                          "mps",
                          "xpu"
                        ]
                      },
                      "description": "Layout model configuration specifying which model to use for document layout analysis. Options include DOCLING_LAYOUT_HERON (default, balanced), DOCLING_LAYOUT_EGRET_* (higher accuracy), etc."
                    },
                    "skip_cell_assignment": {
                      "default": false,
                      "description": "Skip assignment of cells to table structures during layout analysis. When True, cells are detected but not associated with tables. Use for performance optimization when table structure is not needed.",
                      "title": "Skip Cell Assignment",
                      "type": "boolean"
                    }
                  },
                  "title": "LayoutOptions",
                  "type": "object"
                },
                "MlxVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Options for Apple MLX inference engine (Apple Silicon only).",
                  "properties": {
                    "engine_type": {
                      "const": "mlx",
                      "default": "mlx",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "trust_remote_code": {
                      "default": false,
                      "description": "Allow execution of custom code from model repo",
                      "title": "Trust Remote Code",
                      "type": "boolean"
                    }
                  },
                  "title": "MlxVlmEngineOptions",
                  "type": "object"
                },
                "OcrAutoOptions": {
                  "additionalProperties": false,
                  "description": "Automatic OCR engine selection based on system availability.\n\nWhen this option is used, Docling probes the runtime environment at\npipeline initialization and selects the best available OCR engine\n(e.g., EasyOCR if GPU is present, Tesseract otherwise). Language\nsettings are deferred to the chosen engine's defaults.\n\nNotes:\n    The `lang` field is intentionally defaulted to an empty list.\n    To control language selection, specify an explicit OCR engine\n    option class instead.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "auto",
                      "default": "auto",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [],
                      "description": "The automatic OCR engine will use the default values of the engine. Please specify the engine explicitly to change the language selection.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    }
                  },
                  "title": "OcrAutoOptions",
                  "type": "object"
                },
                "OcrMacOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for native macOS OCR using Vision framework.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "framework": {
                      "default": "vision",
                      "description": "macOS framework to use for OCR. Currently supports `vision` (Apple Vision framework). Future versions may support additional frameworks.",
                      "title": "Framework",
                      "type": "string"
                    },
                    "kind": {
                      "const": "ocrmac",
                      "default": "ocrmac",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "fr-FR",
                        "de-DE",
                        "es-ES",
                        "en-US"
                      ],
                      "description": "List of language locale codes for macOS OCR. Use format `language-REGION` (e.g., `en-US`, `fr-FR`). Leverages native macOS Vision framework for OCR on Apple platforms.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "recognition": {
                      "default": "accurate",
                      "description": "Recognition accuracy level. Options: `accurate` (higher quality, slower) or `fast` (lower quality, faster). Choose based on speed vs. accuracy requirements.",
                      "title": "Recognition",
                      "type": "string"
                    }
                  },
                  "title": "OcrMacOptions",
                  "type": "object"
                },
                "OcrOptions": {
                  "description": "Base configuration for Optical Character Recognition engines.\n\nDefines the common interface shared by all OCR engine implementations.\nSubclasses provide engine-specific parameters while inheriting the shared\nlanguage selection, full-page OCR toggle, and bitmap area threshold.\n\nSee Also:\n    `OcrAutoOptions`: Automatic engine selection based on availability.\n    `EasyOcrOptions`, `TesseractCliOcrOptions`, `TesseractOcrOptions`,\n    `RapidOcrOptions`, `OcrMacOptions`: Engine-specific configurations.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "lang": {
                      "description": "List of OCR languages to use. The format must match the values of the OCR engine of choice.",
                      "examples": [
                        [
                          "deu",
                          "eng"
                        ]
                      ],
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    }
                  },
                  "required": [
                    "lang"
                  ],
                  "title": "OcrOptions",
                  "type": "object"
                },
                "OnnxRuntimeImageClassificationEngineOptions": {
                  "additionalProperties": false,
                  "description": "Runtime configuration for ONNX Runtime based image-classification models.",
                  "properties": {
                    "engine_type": {
                      "const": "onnxruntime",
                      "default": "onnxruntime",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "graph_optimization_level": {
                      "default": 99,
                      "description": "ONNX Runtime graph optimization level. Accepts onnxruntime.GraphOptimizationLevel int values: 0 (ORT_DISABLE_ALL), 1 (ORT_ENABLE_BASIC), 2 (ORT_ENABLE_EXTENDED), 99 (ORT_ENABLE_ALL). Default enables all optimizations including layout optimizations.",
                      "title": "Graph Optimization Level",
                      "type": "integer"
                    },
                    "model_filename": {
                      "default": "model.onnx",
                      "description": "Filename of the ONNX export inside the model repository",
                      "title": "Model Filename",
                      "type": "string"
                    },
                    "providers": {
                      "description": "Ordered list of ONNX Runtime execution providers to try",
                      "items": {
                        "type": "string"
                      },
                      "title": "Providers",
                      "type": "array"
                    },
                    "top_k": {
                      "anyOf": [
                        {
                          "minimum": 1,
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Maximum number of classes to return. If None, all classes are returned.",
                      "title": "Top K"
                    }
                  },
                  "title": "OnnxRuntimeImageClassificationEngineOptions",
                  "type": "object"
                },
                "PictureClassificationLabel": {
                  "description": "PictureClassificationLabel.",
                  "enum": [
                    "bar_chart",
                    "box_plot",
                    "flow_chart",
                    "line_chart",
                    "pie_chart",
                    "scatter_plot",
                    "table",
                    "other_chart",
                    "full_page_image",
                    "page_thumbnail",
                    "photograph",
                    "chemistry_structure",
                    "bar_code",
                    "icon",
                    "logo",
                    "qr_code",
                    "signature",
                    "stamp",
                    "engineering_drawing",
                    "screenshot_from_computer",
                    "screenshot_from_manual",
                    "geographical_map",
                    "topographical_map",
                    "calendar",
                    "crossword_puzzle",
                    "music",
                    "other",
                    "cad_drawing",
                    "electrical_diagram",
                    "map",
                    "heatmap",
                    "chemistry_markush_structure",
                    "chemistry_molecular_structure",
                    "natural_image",
                    "picture_group",
                    "remote_sensing",
                    "scatter_chart",
                    "screenshot",
                    "stacked_bar_chart",
                    "stratigraphic_chart"
                  ],
                  "title": "PictureClassificationLabel",
                  "type": "string"
                },
                "PictureDescriptionApiOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for API-based picture description services.\n\nSends images to an OpenAI-compatible chat completions endpoint for\ndescription generation. Supports custom headers for authentication,\nconfigurable timeouts, and concurrent request control.\n\nNotes:\n    Requires ``enable_remote_services=True`` on the parent pipeline\n    options to permit external API calls.",
                  "properties": {
                    "batch_size": {
                      "default": 8,
                      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
                      "minimum": 1,
                      "title": "Batch Size",
                      "type": "integer"
                    },
                    "classification_allow": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
                      "title": "Classification Allow"
                    },
                    "classification_deny": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
                      "title": "Classification Deny"
                    },
                    "classification_min_confidence": {
                      "default": 0.0,
                      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
                      "title": "Classification Min Confidence",
                      "type": "number"
                    },
                    "concurrency": {
                      "default": 1,
                      "description": "Number of concurrent API requests allowed. Higher values improve throughput but may hit API rate limits. Adjust based on API service quotas and network capacity.",
                      "title": "Concurrency",
                      "type": "integer"
                    },
                    "headers": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "default": {},
                      "description": "HTTP headers to include in API requests. Use for authentication or custom headers required by your API service.",
                      "examples": [
                        {
                          "Authorization": "Bearer TOKEN"
                        }
                      ],
                      "title": "Headers",
                      "type": "object"
                    },
                    "kind": {
                      "const": "api",
                      "default": "api",
                      "title": "Engine",
                      "type": "string"
                    },
                    "params": {
                      "additionalProperties": true,
                      "default": {},
                      "description": "Additional query parameters to include in API requests. Service-specific parameters for customizing API behavior beyond standard options.",
                      "title": "Params",
                      "type": "object"
                    },
                    "picture_area_threshold": {
                      "default": 0.05,
                      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
                      "title": "Picture Area Threshold",
                      "type": "number"
                    },
                    "prompt": {
                      "default": "Describe this image in a few sentences.",
                      "description": "Prompt template sent to the vision model for image description. Customize to guide the model's output style, detail level, or focus.",
                      "examples": [
                        "Provide a technical description of this diagram"
                      ],
                      "title": "Prompt",
                      "type": "string"
                    },
                    "provenance": {
                      "default": "",
                      "description": "Provenance information to track the source or method of picture descriptions. Used for metadata and auditing purposes in the output document.",
                      "title": "Provenance",
                      "type": "string"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
                      "exclusiveMinimum": 0,
                      "title": "Scale",
                      "type": "number"
                    },
                    "timeout": {
                      "default": 20.0,
                      "description": "Maximum time in seconds to wait for API response before timing out. Increase for slow networks or complex image descriptions. Recommended: 10-60 seconds.",
                      "title": "Timeout",
                      "type": "number"
                    },
                    "url": {
                      "default": "http://localhost:8000/v1/chat/completions",
                      "description": "API endpoint URL for picture description service. Must be OpenAI-compatible chat completions endpoint. Default points to local server; update for cloud services or custom deployments.",
                      "format": "uri",
                      "minLength": 1,
                      "title": "Url",
                      "type": "string"
                    }
                  },
                  "title": "PictureDescriptionApiOptions",
                  "type": "object"
                },
                "PictureDescriptionBaseOptions": {
                  "description": "Base configuration for picture description models.\n\nProvides shared parameters for all picture description backends,\nincluding batch processing, image scaling, area thresholds, and\nclassification-based filtering (allow/deny lists). Concrete\nimplementations supply the actual model integration.\n\nSee Also:\n    `PictureDescriptionApiOptions`: OpenAI-compatible API backend.\n    `PictureDescriptionVlmOptions`: Legacy HuggingFace Transformers\n        backend.\n    `PictureDescriptionVlmEngineOptions`: New runtime-based backend\n        with preset support (recommended).",
                  "properties": {
                    "batch_size": {
                      "default": 8,
                      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
                      "minimum": 1,
                      "title": "Batch Size",
                      "type": "integer"
                    },
                    "classification_allow": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
                      "title": "Classification Allow"
                    },
                    "classification_deny": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
                      "title": "Classification Deny"
                    },
                    "classification_min_confidence": {
                      "default": 0.0,
                      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
                      "title": "Classification Min Confidence",
                      "type": "number"
                    },
                    "picture_area_threshold": {
                      "default": 0.05,
                      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
                      "title": "Picture Area Threshold",
                      "type": "number"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
                      "exclusiveMinimum": 0,
                      "title": "Scale",
                      "type": "number"
                    }
                  },
                  "title": "PictureDescriptionBaseOptions",
                  "type": "object"
                },
                "PictureDescriptionVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for VLM runtime-based picture description.\n\nThis is the new implementation that uses the pluggable runtime system with preset support.\nSupports all runtime types (Transformers, MLX, API, etc.) through the unified runtime interface.\n\nUse `from_preset()` to create instances from registered presets.\n\nExamples:\n    # Use preset with default runtime\n    options = PictureDescriptionVlmEngineOptions.from_preset(\"smolvlm\")\n\n    # Use preset with runtime override\n    from docling.datamodel.vlm_engine_options import MlxVlmEngineOptions, VlmEngineType\n    options = PictureDescriptionVlmEngineOptions.from_preset(\n        \"smolvlm\",\n        engine_options=MlxVlmEngineOptions(engine_type=VlmEngineType.MLX)\n    )",
                  "properties": {
                    "batch_size": {
                      "default": 8,
                      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
                      "minimum": 1,
                      "title": "Batch Size",
                      "type": "integer"
                    },
                    "classification_allow": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
                      "title": "Classification Allow"
                    },
                    "classification_deny": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
                      "title": "Classification Deny"
                    },
                    "classification_min_confidence": {
                      "default": 0.0,
                      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
                      "title": "Classification Min Confidence",
                      "type": "number"
                    },
                    "engine_options": {
                      "anyOf": [
                        {
                          "$ref": "#/$defs/ApiVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/AutoInlineVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/MlxVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/TransformersVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/VllmVlmEngineOptions"
                        }
                      ],
                      "description": "Runtime configuration (transformers, mlx, api, etc.)"
                    },
                    "generation_config": {
                      "additionalProperties": true,
                      "default": {
                        "do_sample": false,
                        "max_new_tokens": 200
                      },
                      "description": "Generation configuration for text generation. Controls output length, sampling strategy, temperature, etc.",
                      "title": "Generation Config",
                      "type": "object"
                    },
                    "kind": {
                      "const": "picture_description_vlm_engine",
                      "default": "picture_description_vlm_engine",
                      "title": "Engine",
                      "type": "string"
                    },
                    "model_spec": {
                      "$ref": "#/$defs/VlmModelSpec",
                      "description": "Model specification with runtime-specific overrides"
                    },
                    "picture_area_threshold": {
                      "default": 0.05,
                      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
                      "title": "Picture Area Threshold",
                      "type": "number"
                    },
                    "prompt": {
                      "default": "Describe this image in a few sentences.",
                      "description": "Prompt template for the vision model. Customize to control description style, detail level, or focus.",
                      "examples": [
                        "What is shown in this image?",
                        "Provide a detailed technical description"
                      ],
                      "title": "Prompt",
                      "type": "string"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
                      "exclusiveMinimum": 0,
                      "title": "Scale",
                      "type": "number"
                    }
                  },
                  "required": [
                    "engine_options",
                    "model_spec"
                  ],
                  "title": "PictureDescriptionVlmEngineOptions",
                  "type": "object"
                },
                "PictureDescriptionVlmOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for inline vision-language models for picture description.\n\nThis is the legacy implementation that uses direct HuggingFace Transformers integration.\nFor the new runtime-based system with preset support, use PictureDescriptionVlmEngineOptions.",
                  "properties": {
                    "batch_size": {
                      "default": 8,
                      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
                      "minimum": 1,
                      "title": "Batch Size",
                      "type": "integer"
                    },
                    "classification_allow": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
                      "title": "Classification Allow"
                    },
                    "classification_deny": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
                      "title": "Classification Deny"
                    },
                    "classification_min_confidence": {
                      "default": 0.0,
                      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
                      "title": "Classification Min Confidence",
                      "type": "number"
                    },
                    "generation_config": {
                      "additionalProperties": true,
                      "default": {
                        "do_sample": false,
                        "max_new_tokens": 200
                      },
                      "description": "HuggingFace generation configuration for text generation. Controls output length, sampling strategy, temperature, etc. See: https://huggingface.co/docs/transformers/en/main_classes/text_generation#transformers.GenerationConfig",
                      "title": "Generation Config",
                      "type": "object"
                    },
                    "kind": {
                      "const": "vlm",
                      "default": "vlm",
                      "title": "Engine",
                      "type": "string"
                    },
                    "padding_side": {
                      "default": "left",
                      "description": "Tokenizer padding side used for batched generation. Defaults to left to preserve the legacy behavior, but can be overridden for models that require right padding.",
                      "enum": [
                        "left",
                        "right"
                      ],
                      "title": "Padding Side",
                      "type": "string"
                    },
                    "picture_area_threshold": {
                      "default": 0.05,
                      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
                      "title": "Picture Area Threshold",
                      "type": "number"
                    },
                    "prompt": {
                      "default": "Describe this image in a few sentences.",
                      "description": "Prompt template for the vision model. Customize to control description style, detail level, or focus.",
                      "examples": [
                        "What is shown in this image?",
                        "Provide a detailed technical description"
                      ],
                      "title": "Prompt",
                      "type": "string"
                    },
                    "repo_id": {
                      "description": "HuggingFace model repository ID for the vision-language model. Must be a model capable of image-to-text generation for picture descriptions.",
                      "examples": [
                        "HuggingFaceTB/SmolVLM-256M-Instruct",
                        "ibm-granite/granite-vision-3.3-2b"
                      ],
                      "title": "Repo Id",
                      "type": "string"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
                      "exclusiveMinimum": 0,
                      "title": "Scale",
                      "type": "number"
                    }
                  },
                  "required": [
                    "repo_id"
                  ],
                  "title": "PictureDescriptionVlmOptions",
                  "type": "object"
                },
                "RapidOcrOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for RapidOCR engine with multiple backend support.\n\nSee Also:\n    - https://rapidai.github.io/RapidOCRDocs/install_usage/api/RapidOCR/\n    - https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/#__tabbed_3_4",
                  "properties": {
                    "backend": {
                      "default": "onnxruntime",
                      "description": "Inference backend for RapidOCR. Options: `onnxruntime` (default, cross-platform), `openvino` (Intel), `paddle` (PaddlePaddle), `torch` (PyTorch). Choose based on your hardware and available libraries.",
                      "enum": [
                        "onnxruntime",
                        "openvino",
                        "paddle",
                        "torch"
                      ],
                      "title": "Backend",
                      "type": "string"
                    },
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "cls_model_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Custom path to text classification model. If None, uses default RapidOCR model.",
                      "title": "Cls Model Path"
                    },
                    "det_model_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Custom path to text detection model. If None, uses default RapidOCR model.",
                      "title": "Det Model Path"
                    },
                    "font_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Custom path to font file for text rendering in visualization.",
                      "title": "Font Path"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "rapidocr",
                      "default": "rapidocr",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "english",
                        "chinese"
                      ],
                      "description": "List of OCR languages. Note: RapidOCR does not currently support language selection; this parameter is reserved for future compatibility. See RapidOCR documentation for supported languages.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "print_verbose": {
                      "default": false,
                      "description": "Enable verbose logging output from RapidOCR for debugging purposes.",
                      "title": "Print Verbose",
                      "type": "boolean"
                    },
                    "rapidocr_params": {
                      "additionalProperties": true,
                      "default": {},
                      "description": "Additional parameters to pass through to RapidOCR engine. Use this to override or extend default RapidOCR configuration with engine-specific options.",
                      "title": "Rapidocr Params",
                      "type": "object"
                    },
                    "rec_font_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "deprecated": true,
                      "description": "Deprecated. Use font_path instead.",
                      "title": "Rec Font Path"
                    },
                    "rec_keys_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Custom path to recognition keys file. If None, uses default RapidOCR keys.",
                      "title": "Rec Keys Path"
                    },
                    "rec_model_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Custom path to text recognition model. If None, uses default RapidOCR model.",
                      "title": "Rec Model Path"
                    },
                    "text_score": {
                      "default": 0.5,
                      "description": "Minimum confidence score for text detection. Text regions with scores below this threshold are filtered out. Range: 0.0-1.0. Lower values detect more text but may include false positives.",
                      "title": "Text Score",
                      "type": "number"
                    },
                    "use_cls": {
                      "anyOf": [
                        {
                          "type": "boolean"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Enable text direction classification stage. If None, uses RapidOCR default behavior.",
                      "title": "Use Cls"
                    },
                    "use_det": {
                      "anyOf": [
                        {
                          "type": "boolean"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Enable text detection stage. If None, uses RapidOCR default behavior.",
                      "title": "Use Det"
                    },
                    "use_rec": {
                      "anyOf": [
                        {
                          "type": "boolean"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Enable text recognition stage. If None, uses RapidOCR default behavior.",
                      "title": "Use Rec"
                    }
                  },
                  "title": "RapidOcrOptions",
                  "type": "object"
                },
                "ResponseFormat": {
                  "enum": [
                    "doctags",
                    "markdown",
                    "deepseekocr_markdown",
                    "html",
                    "otsl",
                    "plaintext"
                  ],
                  "title": "ResponseFormat",
                  "type": "string"
                },
                "TableFormerMode": {
                  "description": "Operating modes for TableFormer table structure extraction model.\n\nControls the trade-off between processing speed and extraction accuracy.\nChoose based on your performance requirements and document complexity.\n\nAttributes:\n    FAST: Fast mode prioritizes speed over precision. Suitable for simple tables or high-volume\n        processing.\n    ACCURATE: Accurate mode provides higher quality results with slower processing. Recommended for complex\n        tables and production use.",
                  "enum": [
                    "fast",
                    "accurate"
                  ],
                  "title": "TableFormerMode",
                  "type": "string"
                },
                "TableStructureOptions": {
                  "additionalProperties": false,
                  "description": "Options for the table structure (TableFormer V1).",
                  "properties": {
                    "do_cell_matching": {
                      "default": true,
                      "description": "Enable cell matching to align detected table cells with their content. When enabled, the model attempts to match table structure predictions with actual cell content for improved accuracy.",
                      "title": "Do Cell Matching",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "docling_tableformer",
                      "default": "docling_tableformer",
                      "title": "Engine",
                      "type": "string"
                    },
                    "mode": {
                      "$ref": "#/$defs/TableFormerMode",
                      "default": "accurate",
                      "description": "Table structure extraction mode. `accurate` provides higher quality results with slower processing, while `fast` prioritizes speed over precision. Recommended: `accurate` for production use."
                    }
                  },
                  "title": "TableStructureOptions",
                  "type": "object"
                },
                "TesseractCliOcrOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for Tesseract OCR via command-line interface.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "tesseract",
                      "default": "tesseract",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "fra",
                        "deu",
                        "spa",
                        "eng"
                      ],
                      "description": "List of Tesseract language codes. Use 3-letter ISO 639-2 codes (e.g., `eng`, `fra`, `deu`). Multiple languages enable multilingual OCR. Requires corresponding Tesseract language data files.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Path to Tesseract data directory containing language files. If None, uses Tesseract's default TESSDATA_PREFIX location.",
                      "title": "Path"
                    },
                    "psm": {
                      "anyOf": [
                        {
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Page Segmentation Mode for Tesseract. Values 0-13 control how Tesseract segments the page. Common values: 3 (auto), 6 (uniform block), 11 (sparse text). If None, uses Tesseract default.",
                      "title": "Psm"
                    },
                    "tesseract_cmd": {
                      "default": "tesseract",
                      "description": "Command or path to Tesseract executable. Use `tesseract` if in system PATH, or provide full path for custom installations (e.g., `/usr/local/bin/tesseract`).",
                      "title": "Tesseract Cmd",
                      "type": "string"
                    }
                  },
                  "title": "TesseractCliOcrOptions",
                  "type": "object"
                },
                "TesseractOcrOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for Tesseract OCR via Python bindings (tesserocr).",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "tesserocr",
                      "default": "tesserocr",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "fra",
                        "deu",
                        "spa",
                        "eng"
                      ],
                      "description": "List of Tesseract language codes. Use 3-letter ISO 639-2 codes (e.g., `eng`, `fra`, `deu`). Multiple languages enable multilingual OCR. Requires corresponding Tesseract language data files.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Path to Tesseract data directory containing language files. If None, uses Tesseract's default TESSDATA_PREFIX location.",
                      "title": "Path"
                    },
                    "psm": {
                      "anyOf": [
                        {
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Page Segmentation Mode for Tesseract. Values 0-13 control how Tesseract segments the page. Common values: 3 (auto), 6 (uniform block), 11 (sparse text). If None, uses Tesseract default.",
                      "title": "Psm"
                    }
                  },
                  "title": "TesseractOcrOptions",
                  "type": "object"
                },
                "TransformersImageClassificationEngineOptions": {
                  "additionalProperties": false,
                  "description": "Runtime configuration for Transformers-based image-classification models.",
                  "properties": {
                    "compile_model": {
                      "description": "Whether to compile the model with torch.compile() for better performance.",
                      "title": "Compile Model",
                      "type": "boolean"
                    },
                    "engine_type": {
                      "const": "transformers",
                      "default": "transformers",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "top_k": {
                      "anyOf": [
                        {
                          "minimum": 1,
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Maximum number of classes to return. If None, all classes are returned.",
                      "title": "Top K"
                    },
                    "torch_dtype": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "PyTorch dtype for model inference (e.g., 'float32', 'float16', 'bfloat16')",
                      "title": "Torch Dtype"
                    }
                  },
                  "title": "TransformersImageClassificationEngineOptions",
                  "type": "object"
                },
                "TransformersVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Options for HuggingFace Transformers inference engine.",
                  "properties": {
                    "compile_model": {
                      "description": "Whether to compile the model with torch.compile() for better performance.",
                      "title": "Compile Model",
                      "type": "boolean"
                    },
                    "device": {
                      "anyOf": [
                        {
                          "$ref": "#/$defs/AcceleratorDevice"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Device to use (auto-detected if None)"
                    },
                    "engine_type": {
                      "const": "transformers",
                      "default": "transformers",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "llm_int8_threshold": {
                      "default": 6.0,
                      "description": "Threshold for LLM.int8() quantization",
                      "title": "Llm Int8 Threshold",
                      "type": "number"
                    },
                    "load_in_8bit": {
                      "default": true,
                      "description": "Load model in 8-bit precision using bitsandbytes",
                      "title": "Load In 8Bit",
                      "type": "boolean"
                    },
                    "quantized": {
                      "default": false,
                      "description": "Whether the model is pre-quantized",
                      "title": "Quantized",
                      "type": "boolean"
                    },
                    "torch_dtype": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "PyTorch dtype (e.g., 'float16', 'bfloat16')",
                      "title": "Torch Dtype"
                    },
                    "trust_remote_code": {
                      "default": false,
                      "description": "Allow execution of custom code from model repo",
                      "title": "Trust Remote Code",
                      "type": "boolean"
                    },
                    "use_kv_cache": {
                      "default": true,
                      "description": "Enable key-value caching for attention",
                      "title": "Use Kv Cache",
                      "type": "boolean"
                    }
                  },
                  "title": "TransformersVlmEngineOptions",
                  "type": "object"
                },
                "VllmCudaGraphMode": {
                  "description": "CUDA graph capture mode for the vLLM v1 engine.\n\nControls whether and how vLLM captures CUDA graphs to speed up inference.\nCUDA graphs reduce kernel-launch overhead by replaying a recorded sequence\nof CUDA operations instead of launching each kernel individually.\n\nNONE:\n    Disable CUDA graphs entirely; everything runs in eager mode.\n    Fastest startup, lowest steady-state throughput.\n    Best for short-lived processes, notebooks, and debugging.\n\nFULL:\n    Capture the entire forward pass as one monolithic CUDA graph.\n    Maximum graph coverage but requires very static execution shapes;\n    may fail with some models or dynamic workloads.\n\nPIECEWISE:\n    Capture segments of the model (e.g. transformer blocks) as multiple\n    smaller graphs between selected ops.  Handles dynamic shapes better\n    than FULL while still accelerating most of the forward pass.\n\nFULL_AND_PIECEWISE:\n    Hybrid mode (default in many vLLM versions): FULL graphs for\n    decode-only batches; PIECEWISE graphs for prefill and mixed\n    prefill+decode batches.  Usually the best throughput option for\n    typical LLM serving workloads.\n\nFULL_DECODE_ONLY:\n    FULL CUDA graphs only for decode batches; prefill and mixed batches\n    run in eager mode.  Dramatically reduces graph-capture time and\n    memory footprint compared to FULL_AND_PIECEWISE while still\n    accelerating token generation.",
                  "enum": [
                    "NONE",
                    "FULL",
                    "PIECEWISE",
                    "FULL_AND_PIECEWISE",
                    "FULL_DECODE_ONLY"
                  ],
                  "title": "VllmCudaGraphMode",
                  "type": "string"
                },
                "VllmVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Options for vLLM inference engine (high-throughput serving).",
                  "properties": {
                    "cudagraph_mode": {
                      "$ref": "#/$defs/VllmCudaGraphMode",
                      "default": "PIECEWISE",
                      "description": "CUDA graph capture mode (vLLM v1 engine only). See VllmCudaGraphMode for the available options and their trade-offs."
                    },
                    "device": {
                      "anyOf": [
                        {
                          "$ref": "#/$defs/AcceleratorDevice"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Device to use (auto-detected if None)"
                    },
                    "engine_type": {
                      "const": "vllm",
                      "default": "vllm",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "gpu_memory_utilization": {
                      "default": 0.9,
                      "description": "Fraction of GPU memory to use",
                      "title": "Gpu Memory Utilization",
                      "type": "number"
                    },
                    "tensor_parallel_size": {
                      "default": 1,
                      "description": "Number of GPUs for tensor parallelism",
                      "title": "Tensor Parallel Size",
                      "type": "integer"
                    },
                    "trust_remote_code": {
                      "default": false,
                      "description": "Allow execution of custom code from model repo",
                      "title": "Trust Remote Code",
                      "type": "boolean"
                    }
                  },
                  "title": "VllmVlmEngineOptions",
                  "type": "object"
                },
                "VlmEngineType": {
                  "description": "Types of VLM inference engines available.",
                  "enum": [
                    "transformers",
                    "mlx",
                    "vllm",
                    "api",
                    "api_ollama",
                    "api_lmstudio",
                    "api_openai",
                    "auto_inline"
                  ],
                  "title": "VlmEngineType",
                  "type": "string"
                },
                "VlmModelSpec": {
                  "description": "Specification for a VLM model.\n\nThis defines the model configuration that is independent of the engine.\nIt includes:\n- Default model repository ID\n- Prompt template\n- Response format\n- Engine-specific overrides",
                  "properties": {
                    "api_overrides": {
                      "additionalProperties": {
                        "$ref": "#/$defs/ApiModelConfig"
                      },
                      "description": "API-specific configuration overrides",
                      "propertyNames": {
                        "$ref": "#/$defs/VlmEngineType"
                      },
                      "title": "Api Overrides",
                      "type": "object"
                    },
                    "default_repo_id": {
                      "description": "Default HuggingFace repository ID",
                      "title": "Default Repo Id",
                      "type": "string"
                    },
                    "engine_overrides": {
                      "additionalProperties": {
                        "$ref": "#/$defs/EngineModelConfig"
                      },
                      "description": "Engine-specific configuration overrides",
                      "propertyNames": {
                        "$ref": "#/$defs/VlmEngineType"
                      },
                      "title": "Engine Overrides",
                      "type": "object"
                    },
                    "max_new_tokens": {
                      "default": 4096,
                      "description": "Maximum number of new tokens to generate",
                      "title": "Max New Tokens",
                      "type": "integer"
                    },
                    "name": {
                      "description": "Human-readable model name",
                      "title": "Name",
                      "type": "string"
                    },
                    "prompt": {
                      "description": "Prompt template for this model",
                      "title": "Prompt",
                      "type": "string"
                    },
                    "response_format": {
                      "$ref": "#/$defs/ResponseFormat",
                      "description": "Expected response format from the model"
                    },
                    "revision": {
                      "default": "main",
                      "description": "Default model revision",
                      "title": "Revision",
                      "type": "string"
                    },
                    "stop_strings": {
                      "description": "Stop strings for generation",
                      "items": {
                        "type": "string"
                      },
                      "title": "Stop Strings",
                      "type": "array"
                    },
                    "supported_engines": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/VlmEngineType"
                          },
                          "type": "array",
                          "uniqueItems": true
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Set of supported engines (None = all supported)",
                      "title": "Supported Engines"
                    },
                    "trust_remote_code": {
                      "default": false,
                      "description": "Whether to trust remote code for this model",
                      "title": "Trust Remote Code",
                      "type": "boolean"
                    }
                  },
                  "required": [
                    "name",
                    "default_repo_id",
                    "prompt",
                    "response_format"
                  ],
                  "title": "VlmModelSpec",
                  "type": "object"
                }
              },
              "additionalProperties": false,
              "description": "Configuration options for the PDF document processing pipeline.\n\nNotes:\n    - Enabling multiple features (OCR, table structure, formulas) increases the processing time significantly.\n        Enable only necessary features for your use case.\n    - For production systems processing large document volumes, implement a timeout protection (for instance, 90-120\n        seconds via `document_timeout` parameter).\n    - OCR requires a system installation of engines (Tesseract, EasyOCR). Verify the installation before enabling\n        OCR via `do_ocr=True`.\n    - RapidOCR has known issues with read-only filesystems (e.g., Databricks). Consider Tesseract or alternative\n        backends for distributed systems.\n\nSee Also:\n    - `examples/pipeline_options_advanced.py`: Comprehensive configuration examples.",
              "properties": {
                "accelerator_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/AcceleratorOptions"
                    }
                  ],
                  "default": {
                    "cuda_use_flash_attention2": false,
                    "device": "auto",
                    "num_threads": 4
                  },
                  "description": "Hardware acceleration configuration for model inference. Controls GPU device selection, memory management, and execution optimization settings for layout, OCR, and table structure models."
                },
                "allow_external_plugins": {
                  "default": false,
                  "description": "Allow loading external third-party plugins for OCR, layout, table structure, or picture description models. Enables custom model implementations via plugin system. Disabled by default for security.",
                  "examples": [
                    false
                  ],
                  "title": "Allow External Plugins",
                  "type": "boolean"
                },
                "artifacts_path": {
                  "anyOf": [
                    {
                      "format": "path",
                      "type": "string"
                    },
                    {
                      "type": "string"
                    },
                    {
                      "type": "null"
                    }
                  ],
                  "description": "Local directory containing pre-downloaded model artifacts (weights, configs). If None, models are fetched from remote sources on first use. Use `docling-tools models download` to pre-fetch artifacts for offline operation or faster initialization.",
                  "examples": [
                    "./artifacts",
                    "/tmp/docling_outputs"
                  ],
                  "title": "Artifacts Path"
                },
                "batch_polling_interval_seconds": {
                  "default": 0.5,
                  "description": "Polling interval in seconds for batch collection in threaded pipeline stages. Each stage waits up to this duration to accumulate items before processing. Lower values reduce latency but may decrease batching efficiency. Only used by `StandardPdfPipeline` (threaded mode).",
                  "title": "Batch Polling Interval Seconds",
                  "type": "number"
                },
                "chart_extraction_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/ChartExtractionModelOptions"
                    }
                  ],
                  "default": {
                    "chart2code": false,
                    "chart2csv": true,
                    "chart2summary": false,
                    "kind": "chart_extraction",
                    "model": "granite-vision-v4"
                  },
                  "description": "Configuration for the chart extraction model, including which model variant to use and which output formats to generate (CSV, code, summary)."
                },
                "code_formula_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/CodeFormulaVlmOptions"
                    }
                  ],
                  "default": {
                    "engine_options": {
                      "engine_type": "auto_inline"
                    },
                    "extract_code": true,
                    "extract_formulas": true,
                    "model_spec": {
                      "api_overrides": {},
                      "default_repo_id": "docling-project/CodeFormulaV2",
                      "engine_overrides": {
                        "transformers": {
                          "extra_config": {
                            "extra_generation_config": {
                              "skip_special_tokens": false
                            },
                            "torch_dtype": "bfloat16",
                            "transformers_model_type": "automodel-imagetexttotext"
                          }
                        }
                      },
                      "max_new_tokens": 4096,
                      "name": "CodeFormulaV2",
                      "prompt": "",
                      "response_format": "plaintext",
                      "revision": "main",
                      "stop_strings": [
                        "</doctag>",
                        "<end_of_utterance>"
                      ],
                      "trust_remote_code": false
                    },
                    "scale": 2.0
                  },
                  "description": "Configuration for code and formula extraction using VLM. Uses new preset system (recommended). Default: 'default' preset. Only applicable when `do_code_enrichment=True` or `do_formula_enrichment=True`. Example: CodeFormulaVlmOptions.from_preset('granite_vision')"
                },
                "do_chart_extraction": {
                  "default": false,
                  "description": "Enable chart data extraction to convert bar, pie, and line charts into structured tabular data. Automatically enables picture classification. Only applicable when `do_chart_extraction=True`.",
                  "title": "Do Chart Extraction",
                  "type": "boolean"
                },
                "do_code_enrichment": {
                  "default": false,
                  "description": "Enable specialized processing for code blocks. Applies code-aware OCR and formatting to improve accuracy of programming language snippets, terminal output, and structured code content.",
                  "title": "Do Code Enrichment",
                  "type": "boolean"
                },
                "do_formula_enrichment": {
                  "default": false,
                  "description": "Enable mathematical formula recognition and LaTeX conversion. Uses specialized models to detect and extract mathematical expressions, converting them to LaTeX format for accurate representation.",
                  "title": "Do Formula Enrichment",
                  "type": "boolean"
                },
                "do_ocr": {
                  "default": true,
                  "description": "Enable Optical Character Recognition for scanned or image-based PDFs. Replaces or supplements programmatic text extraction with OCR-detected text. Required for scanned documents with no embedded text layer. Note: OCR significantly increases processing time.",
                  "title": "Do Ocr",
                  "type": "boolean"
                },
                "do_picture_classification": {
                  "default": false,
                  "description": "Enable picture classification to categorize images by type (photo, diagram, chart, etc.). Useful for downstream processing that requires image type awareness.",
                  "title": "Do Picture Classification",
                  "type": "boolean"
                },
                "do_picture_description": {
                  "default": false,
                  "description": "Enable automatic generation of textual descriptions for pictures using vision-language models. Descriptions are added to the document for accessibility and searchability.",
                  "title": "Do Picture Description",
                  "type": "boolean"
                },
                "do_table_structure": {
                  "default": true,
                  "description": "Enable table structure extraction and reconstruction. Detects table regions, extracts cell content with row/column relationships, and reconstructs the logical table structure for downstream processing.",
                  "title": "Do Table Structure",
                  "type": "boolean"
                },
                "document_timeout": {
                  "anyOf": [
                    {
                      "type": "number"
                    },
                    {
                      "type": "null"
                    }
                  ],
                  "description": "Maximum processing time in seconds before aborting document conversion. When exceeded, the pipeline stops processing and returns partial results with PARTIAL_SUCCESS status. If None, no timeout is enforced. Recommended: 90-120 seconds for production systems.",
                  "examples": [
                    10.0,
                    20.0
                  ],
                  "title": "Document Timeout"
                },
                "enable_remote_services": {
                  "default": false,
                  "description": "Allow pipeline to call external APIs or cloud services during processing. Required for API-based picture description models. Disabled by default for security and offline operation.",
                  "examples": [
                    false
                  ],
                  "title": "Enable Remote Services",
                  "type": "boolean"
                },
                "force_backend_text": {
                  "default": false,
                  "description": "Force use of PDF backend's native text extraction instead of layout model predictions. When enabled, bypasses the layout model's text detection and uses the embedded text from the PDF file directly. Useful for PDFs with reliable programmatic text layers.",
                  "title": "Force Backend Text",
                  "type": "boolean"
                },
                "generate_page_images": {
                  "default": false,
                  "description": "Generate rendered page images during extraction. Creates PNG representations of each page for visual preview, validation, or downstream image-based machine learning tasks.",
                  "title": "Generate Page Images",
                  "type": "boolean"
                },
                "generate_parsed_pages": {
                  "default": false,
                  "description": "Retain intermediate parsed page representations after processing. When enabled, keeps detailed page-level parsing data structures for debugging or advanced post-processing. Increases memory usage. Automatically disabled after document assembly unless explicitly enabled.",
                  "title": "Generate Parsed Pages",
                  "type": "boolean"
                },
                "generate_picture_images": {
                  "default": false,
                  "description": "Extract and save embedded images from the PDF. Exports individual images (figures, photos, diagrams, charts) found in the document as separate image files for downstream use.",
                  "title": "Generate Picture Images",
                  "type": "boolean"
                },
                "generate_table_images": {
                  "default": false,
                  "deprecated": true,
                  "title": "Generate Table Images",
                  "type": "boolean"
                },
                "images_scale": {
                  "default": 1.0,
                  "description": "Scaling factor for generated images. Higher values produce higher resolution but increase processing time and storage requirements. Recommended values: 1.0 (standard quality), 2.0 (high resolution), 0.5 (lower resolution for previews).",
                  "title": "Images Scale",
                  "type": "number"
                },
                "layout_batch_size": {
                  "default": 4,
                  "description": "Batch size for layout analysis stage in threaded pipeline. Pages are grouped and processed together by the layout model. Higher values improve throughput but increase memory usage. Only used by `StandardPdfPipeline` (threaded mode).",
                  "title": "Layout Batch Size",
                  "type": "integer"
                },
                "layout_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/LayoutOptions"
                    }
                  ],
                  "default": {
                    "create_orphan_clusters": true,
                    "keep_empty_clusters": false,
                    "kind": "docling_layout_default",
                    "model_spec": {
                      "model_path": "",
                      "name": "docling_layout_heron",
                      "repo_id": "docling-project/docling-layout-heron",
                      "revision": "main",
                      "supported_devices": [
                        "cpu",
                        "cuda",
                        "mps",
                        "xpu"
                      ]
                    },
                    "skip_cell_assignment": false
                  },
                  "description": "Configuration for document layout analysis model. Controls layout detection behavior including cluster creation for orphaned elements, cell assignment to table structures, and handling of empty regions. Specifies which layout model to use (default: Heron)."
                },
                "ocr_batch_size": {
                  "default": 4,
                  "description": "Batch size for OCR processing stage in threaded pipeline. Pages are grouped and processed together to improve throughput. Higher values increase GPU/CPU utilization but require more memory. Only used by `StandardPdfPipeline` (threaded mode).",
                  "title": "Ocr Batch Size",
                  "type": "integer"
                },
                "ocr_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/EasyOcrOptions"
                    },
                    {
                      "$ref": "#/$defs/KserveV2OcrOptions"
                    },
                    {
                      "$ref": "#/$defs/OcrAutoOptions"
                    },
                    {
                      "$ref": "#/$defs/OcrMacOptions"
                    },
                    {
                      "$ref": "#/$defs/RapidOcrOptions"
                    },
                    {
                      "$ref": "#/$defs/TesseractCliOcrOptions"
                    },
                    {
                      "$ref": "#/$defs/TesseractOcrOptions"
                    }
                  ],
                  "default": {
                    "bitmap_area_threshold": 0.05,
                    "force_full_page_ocr": false,
                    "kind": "auto",
                    "lang": []
                  },
                  "description": "Configuration for OCR engine. Specifies which OCR engine to use (Tesseract, EasyOCR, RapidOCR, etc.) and engine-specific settings. Only applicable when `do_ocr=True`."
                },
                "picture_classification_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/DocumentPictureClassifierOptions"
                    }
                  ],
                  "default": {
                    "engine_options": {
                      "engine_type": "transformers"
                    },
                    "kind": "document_picture_classifier",
                    "model_spec": {
                      "engine_overrides": {},
                      "name": "document_figure_classifier_v2",
                      "repo_id": "docling-project/DocumentFigureClassifier-v2.5",
                      "revision": "main"
                    }
                  },
                  "description": "Configuration for picture classification model/runtime. Supports selecting transformers, onnxruntime, or remote api_kserve_v2 inference engines."
                },
                "picture_description_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/PictureDescriptionApiOptions"
                    },
                    {
                      "$ref": "#/$defs/PictureDescriptionVlmEngineOptions"
                    },
                    {
                      "$ref": "#/$defs/PictureDescriptionVlmOptions"
                    }
                  ],
                  "default": {
                    "batch_size": 8,
                    "classification_min_confidence": 0.0,
                    "engine_options": {
                      "engine_type": "auto_inline"
                    },
                    "generation_config": {
                      "do_sample": false,
                      "max_new_tokens": 200
                    },
                    "kind": "picture_description_vlm_engine",
                    "model_spec": {
                      "api_overrides": {
                        "api_lmstudio": {
                          "params": {
                            "model": "smolvlm-256m-instruct"
                          }
                        }
                      },
                      "default_repo_id": "HuggingFaceTB/SmolVLM-256M-Instruct",
                      "engine_overrides": {
                        "mlx": {
                          "extra_config": {},
                          "repo_id": "moot20/SmolVLM-256M-Instruct-MLX"
                        },
                        "transformers": {
                          "extra_config": {
                            "transformers_model_type": "automodel-imagetexttotext"
                          },
                          "torch_dtype": "bfloat16"
                        }
                      },
                      "max_new_tokens": 4096,
                      "name": "SmolVLM-256M-Instruct",
                      "prompt": "Describe this image in a few sentences.",
                      "response_format": "plaintext",
                      "revision": "main",
                      "stop_strings": [],
                      "trust_remote_code": false
                    },
                    "picture_area_threshold": 0.05,
                    "prompt": "Describe this image in a few sentences.",
                    "scale": 2.0
                  },
                  "description": "Configuration for picture description model. Uses new preset system (recommended). Default: 'smolvlm' preset. Only applicable when `do_picture_description=True`. Example: PictureDescriptionVlmOptions.from_preset('granite_vision')"
                },
                "queue_max_size": {
                  "default": 100,
                  "description": "Maximum queue size for inter-stage communication in threaded pipeline. Limits the number of items buffered between processing stages to prevent memory overflow. When full, upstream stages block until space is available. Only used by `StandardPdfPipeline` (threaded mode).",
                  "title": "Queue Max Size",
                  "type": "integer"
                },
                "table_batch_size": {
                  "default": 4,
                  "description": "Batch size for table structure extraction stage in threaded pipeline. Tables from multiple pages are processed together. Higher values improve throughput but increase memory usage. Only used by `StandardPdfPipeline` (threaded mode).",
                  "title": "Table Batch Size",
                  "type": "integer"
                },
                "table_structure_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/TableStructureOptions"
                    }
                  ],
                  "default": {
                    "do_cell_matching": true,
                    "kind": "docling_tableformer",
                    "mode": "accurate"
                  },
                  "description": "Configuration for table structure extraction. Controls table detection accuracy, cell matching behavior, and table formatting. Only applicable when `do_table_structure=True`."
                }
              },
              "title": "PdfPipelineOptions",
              "type": "object"
            }
          },
          "formats": {
            "items": {
              "enum": [
                "markdown",
                "json",
                "html",
                "txt",
                "doclang",
                "doctags",
                "document_tokens",
                "element_tree",
                "vtt"
              ],
              "type": "string"
            },
            "maxItems": 9,
            "minItems": 1,
            "title": "Formats",
            "type": "array"
          },
          "output_format": {
            "default": "markdown",
            "enum": [
              "markdown",
              "json",
              "html",
              "txt",
              "doclang",
              "doctags",
              "document_tokens",
              "element_tree",
              "vtt"
            ],
            "title": "Output Format",
            "type": "string"
          },
          "export_options": {
            "additionalProperties": {
              "additionalProperties": true,
              "type": "object"
            },
            "description": "Parâmetros nativos por formato; caminhos de imagens são geridos pelo servidor.",
            "title": "Export Options",
            "type": "object"
          },
          "page_range": {
            "anyOf": [
              {
                "maxItems": 2,
                "minItems": 2,
                "prefixItems": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "integer"
                  }
                ],
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "description": "Primeira/última página inclusivas, numeradas a partir de 1.",
            "title": "Page Range"
          },
          "max_num_pages": {
            "anyOf": [
              {
                "minimum": 1,
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Max Num Pages"
          },
          "max_file_size": {
            "anyOf": [
              {
                "minimum": 1,
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "description": "Limite da conversão em bytes, adicional ao limite de upload do serviço.",
            "title": "Max File Size"
          },
          "raises_on_error": {
            "default": true,
            "title": "Raises On Error",
            "type": "boolean"
          }
        },
        "title": "DocumentOptions",
        "type": "object"
      }
    },
    "audio_options": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Audio Options",
      "description": "JSON AudioConversionOptions para processar áudio/vídeo de qualquer fonte. Incompatível com conversion_options.",
      "x-options-schema": {
        "$defs": {
          "AudioDecodingOptions": {
            "additionalProperties": false,
            "description": "Controles públicos dos providers. Consulte /audio/capabilities antes de enviar.",
            "properties": {
              "task": {
                "default": "transcribe",
                "enum": [
                  "transcribe",
                  "translate"
                ],
                "title": "Task",
                "type": "string"
              },
              "language": {
                "anyOf": [
                  {
                    "pattern": "^[a-z]{2,3}$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "description": "Idioma da gravação; omitido detecta automaticamente.",
                "title": "Language"
              },
              "log_progress": {
                "default": false,
                "title": "Log Progress",
                "type": "boolean"
              },
              "beam_size": {
                "anyOf": [
                  {
                    "maximum": 20,
                    "minimum": 1,
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": 5,
                "title": "Beam Size"
              },
              "best_of": {
                "anyOf": [
                  {
                    "maximum": 20,
                    "minimum": 1,
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": 5,
                "title": "Best Of"
              },
              "patience": {
                "anyOf": [
                  {
                    "exclusiveMinimum": 0,
                    "maximum": 10,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": 1,
                "title": "Patience"
              },
              "length_penalty": {
                "anyOf": [
                  {
                    "maximum": 2,
                    "minimum": 0,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": 1,
                "title": "Length Penalty"
              },
              "repetition_penalty": {
                "default": 1,
                "exclusiveMinimum": 0,
                "maximum": 5,
                "title": "Repetition Penalty",
                "type": "number"
              },
              "no_repeat_ngram_size": {
                "default": 0,
                "maximum": 100,
                "minimum": 0,
                "title": "No Repeat Ngram Size",
                "type": "integer"
              },
              "temperature": {
                "anyOf": [
                  {
                    "maximum": 1,
                    "minimum": 0,
                    "type": "number"
                  },
                  {
                    "items": {
                      "maximum": 1,
                      "minimum": 0,
                      "type": "number"
                    },
                    "maxItems": 100,
                    "minItems": 1,
                    "type": "array"
                  }
                ],
                "default": 0.0,
                "title": "Temperature"
              },
              "compression_ratio_threshold": {
                "anyOf": [
                  {
                    "exclusiveMinimum": 0,
                    "maximum": 1000000000.0,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": 2.4,
                "title": "Compression Ratio Threshold"
              },
              "log_prob_threshold": {
                "anyOf": [
                  {
                    "maximum": 1000000000.0,
                    "minimum": -1000000000.0,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": -1.0,
                "title": "Log Prob Threshold"
              },
              "logprob_threshold": {
                "anyOf": [
                  {
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": -1.0,
                "description": "Nome do controle no provider openai-whisper.",
                "title": "Logprob Threshold"
              },
              "no_speech_threshold": {
                "anyOf": [
                  {
                    "maximum": 1,
                    "minimum": 0,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": 0.6,
                "title": "No Speech Threshold"
              },
              "condition_on_previous_text": {
                "default": true,
                "title": "Condition On Previous Text",
                "type": "boolean"
              },
              "prompt_reset_on_temperature": {
                "default": 0.5,
                "maximum": 1,
                "minimum": 0,
                "title": "Prompt Reset On Temperature",
                "type": "number"
              },
              "initial_prompt": {
                "anyOf": [
                  {
                    "maxLength": 10000,
                    "type": "string"
                  },
                  {
                    "items": {
                      "minimum": 0,
                      "type": "integer"
                    },
                    "maxItems": 10000,
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "description": "Contexto textual; tokens numéricos somente no faster-whisper.",
                "title": "Initial Prompt"
              },
              "carry_initial_prompt": {
                "default": false,
                "title": "Carry Initial Prompt",
                "type": "boolean"
              },
              "prompt": {
                "anyOf": [
                  {
                    "maxLength": 10000,
                    "type": "string"
                  },
                  {
                    "items": {
                      "minimum": 0,
                      "type": "integer"
                    },
                    "maxItems": 10000,
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "title": "Prompt"
              },
              "prefix": {
                "anyOf": [
                  {
                    "maxLength": 10000,
                    "type": "string"
                  },
                  {
                    "items": {
                      "minimum": 0,
                      "type": "integer"
                    },
                    "maxItems": 10000,
                    "type": "array"
                  },
                  {
                    "type": "null"
                  }
                ],
                "title": "Prefix"
              },
              "suppress_blank": {
                "default": true,
                "title": "Suppress Blank",
                "type": "boolean"
              },
              "suppress_tokens": {
                "anyOf": [
                  {
                    "maxLength": 10000,
                    "type": "string"
                  },
                  {
                    "items": {
                      "minimum": -1,
                      "type": "integer"
                    },
                    "type": "array"
                  }
                ],
                "maxLength": 10000,
                "title": "Suppress Tokens"
              },
              "without_timestamps": {
                "default": false,
                "title": "Without Timestamps",
                "type": "boolean"
              },
              "max_initial_timestamp": {
                "default": 1,
                "maximum": 30,
                "minimum": 0,
                "title": "Max Initial Timestamp",
                "type": "number"
              },
              "prepend_punctuations": {
                "default": "\"'“¿([{-",
                "title": "Prepend Punctuations",
                "type": "string"
              },
              "append_punctuations": {
                "default": "\"'.。,，!！?？:：”)]}、",
                "title": "Append Punctuations",
                "type": "string"
              },
              "multilingual": {
                "default": false,
                "title": "Multilingual",
                "type": "boolean"
              },
              "vad_filter": {
                "default": true,
                "title": "Vad Filter",
                "type": "boolean"
              },
              "vad_parameters": {
                "anyOf": [
                  {
                    "$ref": "#/$defs/VadParameters"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "max_new_tokens": {
                "anyOf": [
                  {
                    "maximum": 448,
                    "minimum": 1,
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "title": "Max New Tokens"
              },
              "sample_len": {
                "anyOf": [
                  {
                    "maximum": 448,
                    "minimum": 1,
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "title": "Sample Len"
              },
              "chunk_length": {
                "anyOf": [
                  {
                    "maximum": 30,
                    "minimum": 1,
                    "type": "integer"
                  },
                  {
                    "type": "null"
                  }
                ],
                "title": "Chunk Length"
              },
              "clip_timestamps": {
                "anyOf": [
                  {
                    "maxLength": 10000,
                    "type": "string"
                  },
                  {
                    "items": {
                      "maximum": 1000000000.0,
                      "minimum": 0,
                      "type": "number"
                    },
                    "maxItems": 10000,
                    "minItems": 1,
                    "type": "array"
                  }
                ],
                "default": "0",
                "title": "Clip Timestamps"
              },
              "hallucination_silence_threshold": {
                "anyOf": [
                  {
                    "exclusiveMinimum": 0,
                    "maximum": 1000000000.0,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "title": "Hallucination Silence Threshold"
              },
              "hotwords": {
                "anyOf": [
                  {
                    "maxLength": 10000,
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ],
                "title": "Hotwords"
              },
              "language_detection_threshold": {
                "anyOf": [
                  {
                    "maximum": 1,
                    "minimum": 0,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "default": 0.5,
                "title": "Language Detection Threshold"
              },
              "language_detection_segments": {
                "default": 1,
                "maximum": 100,
                "minimum": 1,
                "title": "Language Detection Segments",
                "type": "integer"
              },
              "fp16": {
                "default": true,
                "title": "Fp16",
                "type": "boolean"
              }
            },
            "title": "AudioDecodingOptions",
            "type": "object"
          },
          "VadParameters": {
            "additionalProperties": false,
            "properties": {
              "threshold": {
                "default": 0.5,
                "maximum": 1,
                "minimum": 0,
                "title": "Threshold",
                "type": "number"
              },
              "neg_threshold": {
                "anyOf": [
                  {
                    "maximum": 1,
                    "minimum": 0,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "title": "Neg Threshold"
              },
              "min_speech_duration_ms": {
                "default": 0,
                "maximum": 1000000000,
                "minimum": 0,
                "title": "Min Speech Duration Ms",
                "type": "integer"
              },
              "max_speech_duration_s": {
                "anyOf": [
                  {
                    "exclusiveMinimum": 0,
                    "maximum": 1000000000.0,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "description": "Omitir para duração ilimitada.",
                "title": "Max Speech Duration S"
              },
              "min_silence_duration_ms": {
                "default": 500,
                "maximum": 1000000000,
                "minimum": 0,
                "title": "Min Silence Duration Ms",
                "type": "integer"
              },
              "speech_pad_ms": {
                "default": 400,
                "maximum": 1000000000,
                "minimum": 0,
                "title": "Speech Pad Ms",
                "type": "integer"
              }
            },
            "title": "VadParameters",
            "type": "object"
          }
        },
        "additionalProperties": false,
        "description": "The same audio controls for uploads, external sources and bucket imports.",
        "properties": {
          "operation": {
            "default": "transcribe",
            "enum": [
              "transcribe",
              "detect_language",
              "inspect"
            ],
            "title": "Operation",
            "type": "string"
          },
          "decoding": {
            "$ref": "#/$defs/AudioDecodingOptions"
          },
          "include_timestamps": {
            "default": true,
            "title": "Include Timestamps",
            "type": "boolean"
          },
          "include_word_timestamps": {
            "default": false,
            "title": "Include Word Timestamps",
            "type": "boolean"
          },
          "output_format": {
            "default": "markdown",
            "enum": [
              "markdown",
              "vtt",
              "srt",
              "txt",
              "json"
            ],
            "title": "Output Format",
            "type": "string"
          },
          "purge_source": {
            "default": false,
            "title": "Purge Source",
            "type": "boolean"
          }
        },
        "title": "AudioConversionOptions",
        "type": "object"
      }
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
    },
    "datalake_connection_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Connection Id"
    },
    "datalake_bucket": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Bucket"
    },
    "datalake_prefix": {
      "type": "string",
      "title": "Datalake Prefix",
      "default": ""
    },
    "datalake_partitioning": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Partitioning",
      "description": "JSON da estratégia por solicitação; omitir herda a conexão. Ex.: {\"mode\":\"custom\",\"fields\":[{\"field\":\"custom\",\"key\":\"client_id\"}],\"missing\":\"require\",\"analytics\":\"jsonl\"}"
    },
    "datalake_partition_values": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Partition Values",
      "description": "JSON de valores por job. Chaves fora da estratégia preservam contexto no dataset sem criar diretórios. Ex.: {\"client_id\":\"client-42\",\"conversation_id\":\"chat-7\",\"agent_id\":\"support-agent\"}"
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
| `operation` | não | string | default="transcribe"; enum=["transcribe", "detect_language", "inspect"] | Transcrever/traduzir, detectar idioma ou inspecionar metadados do arquivo. |
| `decoding_options` | não | string / null |  | JSON AudioDecodingOptions. Controles aceitos e limites: GET /audio/capabilities. |
| `output_format` | não | string | default="markdown" | Formato padrão do resultado em /jobs/{job_id}/result: markdown, vtt, srt, txt ou json |
| `purge_source` | não | boolean | default=false | Apagar o áudio/vídeo enviado assim que a transcrição terminar (guarda só o texto) |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |
| `datalake_connection_id` | não | string / null |  |  |
| `datalake_bucket` | não | string / null |  |  |
| `datalake_prefix` | não | string | default="" |  |
| `datalake_partitioning` | não | string / null |  | JSON da estratégia por solicitação; omitir herda a conexão. Ex.: {"mode":"custom","fields":[{"field":"custom","key":"client_id"}],"missing":"require","analytics":"jsonl"} |
| `datalake_partition_values` | não | string / null |  | JSON de valores por job. Chaves fora da estratégia preservam contexto no dataset sem criar diretórios. Ex.: {"client_id":"client-42","conversation_id":"chat-7","agent_id":"support-agent"} |

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
    "operation": {
      "type": "string",
      "enum": [
        "transcribe",
        "detect_language",
        "inspect"
      ],
      "title": "Operation",
      "description": "Transcrever/traduzir, detectar idioma ou inspecionar metadados do arquivo.",
      "default": "transcribe"
    },
    "decoding_options": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Decoding Options",
      "description": "JSON AudioDecodingOptions. Controles aceitos e limites: GET /audio/capabilities.",
      "x-options-schema": {
        "$defs": {
          "VadParameters": {
            "additionalProperties": false,
            "properties": {
              "threshold": {
                "default": 0.5,
                "maximum": 1,
                "minimum": 0,
                "title": "Threshold",
                "type": "number"
              },
              "neg_threshold": {
                "anyOf": [
                  {
                    "maximum": 1,
                    "minimum": 0,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "title": "Neg Threshold"
              },
              "min_speech_duration_ms": {
                "default": 0,
                "maximum": 1000000000,
                "minimum": 0,
                "title": "Min Speech Duration Ms",
                "type": "integer"
              },
              "max_speech_duration_s": {
                "anyOf": [
                  {
                    "exclusiveMinimum": 0,
                    "maximum": 1000000000.0,
                    "type": "number"
                  },
                  {
                    "type": "null"
                  }
                ],
                "description": "Omitir para duração ilimitada.",
                "title": "Max Speech Duration S"
              },
              "min_silence_duration_ms": {
                "default": 500,
                "maximum": 1000000000,
                "minimum": 0,
                "title": "Min Silence Duration Ms",
                "type": "integer"
              },
              "speech_pad_ms": {
                "default": 400,
                "maximum": 1000000000,
                "minimum": 0,
                "title": "Speech Pad Ms",
                "type": "integer"
              }
            },
            "title": "VadParameters",
            "type": "object"
          }
        },
        "additionalProperties": false,
        "description": "Controles públicos dos providers. Consulte /audio/capabilities antes de enviar.",
        "properties": {
          "task": {
            "default": "transcribe",
            "enum": [
              "transcribe",
              "translate"
            ],
            "title": "Task",
            "type": "string"
          },
          "language": {
            "anyOf": [
              {
                "pattern": "^[a-z]{2,3}$",
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "description": "Idioma da gravação; omitido detecta automaticamente.",
            "title": "Language"
          },
          "log_progress": {
            "default": false,
            "title": "Log Progress",
            "type": "boolean"
          },
          "beam_size": {
            "anyOf": [
              {
                "maximum": 20,
                "minimum": 1,
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "default": 5,
            "title": "Beam Size"
          },
          "best_of": {
            "anyOf": [
              {
                "maximum": 20,
                "minimum": 1,
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "default": 5,
            "title": "Best Of"
          },
          "patience": {
            "anyOf": [
              {
                "exclusiveMinimum": 0,
                "maximum": 10,
                "type": "number"
              },
              {
                "type": "null"
              }
            ],
            "default": 1,
            "title": "Patience"
          },
          "length_penalty": {
            "anyOf": [
              {
                "maximum": 2,
                "minimum": 0,
                "type": "number"
              },
              {
                "type": "null"
              }
            ],
            "default": 1,
            "title": "Length Penalty"
          },
          "repetition_penalty": {
            "default": 1,
            "exclusiveMinimum": 0,
            "maximum": 5,
            "title": "Repetition Penalty",
            "type": "number"
          },
          "no_repeat_ngram_size": {
            "default": 0,
            "maximum": 100,
            "minimum": 0,
            "title": "No Repeat Ngram Size",
            "type": "integer"
          },
          "temperature": {
            "anyOf": [
              {
                "maximum": 1,
                "minimum": 0,
                "type": "number"
              },
              {
                "items": {
                  "maximum": 1,
                  "minimum": 0,
                  "type": "number"
                },
                "maxItems": 100,
                "minItems": 1,
                "type": "array"
              }
            ],
            "default": 0.0,
            "title": "Temperature"
          },
          "compression_ratio_threshold": {
            "anyOf": [
              {
                "exclusiveMinimum": 0,
                "maximum": 1000000000.0,
                "type": "number"
              },
              {
                "type": "null"
              }
            ],
            "default": 2.4,
            "title": "Compression Ratio Threshold"
          },
          "log_prob_threshold": {
            "anyOf": [
              {
                "maximum": 1000000000.0,
                "minimum": -1000000000.0,
                "type": "number"
              },
              {
                "type": "null"
              }
            ],
            "default": -1.0,
            "title": "Log Prob Threshold"
          },
          "logprob_threshold": {
            "anyOf": [
              {
                "type": "number"
              },
              {
                "type": "null"
              }
            ],
            "default": -1.0,
            "description": "Nome do controle no provider openai-whisper.",
            "title": "Logprob Threshold"
          },
          "no_speech_threshold": {
            "anyOf": [
              {
                "maximum": 1,
                "minimum": 0,
                "type": "number"
              },
              {
                "type": "null"
              }
            ],
            "default": 0.6,
            "title": "No Speech Threshold"
          },
          "condition_on_previous_text": {
            "default": true,
            "title": "Condition On Previous Text",
            "type": "boolean"
          },
          "prompt_reset_on_temperature": {
            "default": 0.5,
            "maximum": 1,
            "minimum": 0,
            "title": "Prompt Reset On Temperature",
            "type": "number"
          },
          "initial_prompt": {
            "anyOf": [
              {
                "maxLength": 10000,
                "type": "string"
              },
              {
                "items": {
                  "minimum": 0,
                  "type": "integer"
                },
                "maxItems": 10000,
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "description": "Contexto textual; tokens numéricos somente no faster-whisper.",
            "title": "Initial Prompt"
          },
          "carry_initial_prompt": {
            "default": false,
            "title": "Carry Initial Prompt",
            "type": "boolean"
          },
          "prompt": {
            "anyOf": [
              {
                "maxLength": 10000,
                "type": "string"
              },
              {
                "items": {
                  "minimum": 0,
                  "type": "integer"
                },
                "maxItems": 10000,
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Prompt"
          },
          "prefix": {
            "anyOf": [
              {
                "maxLength": 10000,
                "type": "string"
              },
              {
                "items": {
                  "minimum": 0,
                  "type": "integer"
                },
                "maxItems": 10000,
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Prefix"
          },
          "suppress_blank": {
            "default": true,
            "title": "Suppress Blank",
            "type": "boolean"
          },
          "suppress_tokens": {
            "anyOf": [
              {
                "maxLength": 10000,
                "type": "string"
              },
              {
                "items": {
                  "minimum": -1,
                  "type": "integer"
                },
                "type": "array"
              }
            ],
            "maxLength": 10000,
            "title": "Suppress Tokens"
          },
          "without_timestamps": {
            "default": false,
            "title": "Without Timestamps",
            "type": "boolean"
          },
          "max_initial_timestamp": {
            "default": 1,
            "maximum": 30,
            "minimum": 0,
            "title": "Max Initial Timestamp",
            "type": "number"
          },
          "prepend_punctuations": {
            "default": "\"'“¿([{-",
            "title": "Prepend Punctuations",
            "type": "string"
          },
          "append_punctuations": {
            "default": "\"'.。,，!！?？:：”)]}、",
            "title": "Append Punctuations",
            "type": "string"
          },
          "multilingual": {
            "default": false,
            "title": "Multilingual",
            "type": "boolean"
          },
          "vad_filter": {
            "default": true,
            "title": "Vad Filter",
            "type": "boolean"
          },
          "vad_parameters": {
            "anyOf": [
              {
                "$ref": "#/$defs/VadParameters"
              },
              {
                "type": "null"
              }
            ]
          },
          "max_new_tokens": {
            "anyOf": [
              {
                "maximum": 448,
                "minimum": 1,
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Max New Tokens"
          },
          "sample_len": {
            "anyOf": [
              {
                "maximum": 448,
                "minimum": 1,
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Sample Len"
          },
          "chunk_length": {
            "anyOf": [
              {
                "maximum": 30,
                "minimum": 1,
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Chunk Length"
          },
          "clip_timestamps": {
            "anyOf": [
              {
                "maxLength": 10000,
                "type": "string"
              },
              {
                "items": {
                  "maximum": 1000000000.0,
                  "minimum": 0,
                  "type": "number"
                },
                "maxItems": 10000,
                "minItems": 1,
                "type": "array"
              }
            ],
            "default": "0",
            "title": "Clip Timestamps"
          },
          "hallucination_silence_threshold": {
            "anyOf": [
              {
                "exclusiveMinimum": 0,
                "maximum": 1000000000.0,
                "type": "number"
              },
              {
                "type": "null"
              }
            ],
            "title": "Hallucination Silence Threshold"
          },
          "hotwords": {
            "anyOf": [
              {
                "maxLength": 10000,
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Hotwords"
          },
          "language_detection_threshold": {
            "anyOf": [
              {
                "maximum": 1,
                "minimum": 0,
                "type": "number"
              },
              {
                "type": "null"
              }
            ],
            "default": 0.5,
            "title": "Language Detection Threshold"
          },
          "language_detection_segments": {
            "default": 1,
            "maximum": 100,
            "minimum": 1,
            "title": "Language Detection Segments",
            "type": "integer"
          },
          "fp16": {
            "default": true,
            "title": "Fp16",
            "type": "boolean"
          }
        },
        "title": "AudioDecodingOptions",
        "type": "object"
      }
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
      "description": "Apagar o áudio/vídeo enviado assim que a transcrição terminar (guarda só o texto)",
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
    },
    "datalake_connection_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Connection Id"
    },
    "datalake_bucket": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Bucket"
    },
    "datalake_prefix": {
      "type": "string",
      "title": "Datalake Prefix",
      "default": ""
    },
    "datalake_partitioning": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Partitioning",
      "description": "JSON da estratégia por solicitação; omitir herda a conexão. Ex.: {\"mode\":\"custom\",\"fields\":[{\"field\":\"custom\",\"key\":\"client_id\"}],\"missing\":\"require\",\"analytics\":\"jsonl\"}"
    },
    "datalake_partition_values": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Partition Values",
      "description": "JSON de valores por job. Chaves fora da estratégia preservam contexto no dataset sem criar diretórios. Ex.: {\"client_id\":\"client-42\",\"conversation_id\":\"chat-7\",\"agent_id\":\"support-agent\"}"
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
| `conversion_options` | não | string / null |  | JSON DocumentOptions: pipeline, formats, export_options e limites de conversão. |
| `project` | não | string / null |  | Nome do projeto (obrigatório, a menos que a API key esteja vinculada a um projeto). É criado se não existir; grafias equivalentes ('Reunião', ' reuniao ') são o mesmo projeto. |
| `project_id` | não | string / null |  | ID de um projeto existente (alternativa a 'project'; nunca cria). |
| `folder` | não | string / null |  | Nome da pasta dentro do projeto (opcional; criada se não existir; sem '/'). |
| `folder_id` | não | string / null |  | ID de uma pasta existente do projeto (alternativa a 'folder'). |
| `datalake_connection_id` | não | string / null |  |  |
| `datalake_bucket` | não | string / null |  |  |
| `datalake_prefix` | não | string | default="" |  |
| `datalake_partitioning` | não | string / null |  | JSON da estratégia por solicitação; omitir herda a conexão. Ex.: {"mode":"custom","fields":[{"field":"custom","key":"client_id"}],"missing":"require","analytics":"jsonl"} |
| `datalake_partition_values` | não | string / null |  | JSON de valores por job. Chaves fora da estratégia preservam contexto no dataset sem criar diretórios. Ex.: {"client_id":"client-42","conversation_id":"chat-7","agent_id":"support-agent"} |

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
    "conversion_options": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Conversion Options",
      "description": "JSON DocumentOptions: pipeline, formats, export_options e limites de conversão.",
      "x-options-schema": {
        "additionalProperties": false,
        "properties": {
          "pipeline": {
            "additionalProperties": true,
            "description": "Controles PdfPipelineOptions. Opções explícitas substituem o preset.",
            "title": "Pipeline",
            "type": "object",
            "x-options-schema": {
              "$defs": {
                "AcceleratorDevice": {
                  "description": "Devices to run model inference",
                  "enum": [
                    "auto",
                    "cpu",
                    "cuda",
                    "mps",
                    "xpu"
                  ],
                  "title": "AcceleratorDevice",
                  "type": "string"
                },
                "AcceleratorOptions": {
                  "additionalProperties": false,
                  "description": "Hardware acceleration configuration for model inference.\n\nCan be configured via environment variables with DOCLING_ prefix.",
                  "properties": {
                    "cuda_use_flash_attention2": {
                      "default": false,
                      "description": "Enable Flash Attention 2 optimization for CUDA devices. Provides significant speedup and memory reduction for transformer models on compatible NVIDIA GPUs (Ampere or newer). Requires flash-attn package installation. Can be set via DOCLING_CUDA_USE_FLASH_ATTENTION2 environment variable.",
                      "title": "Cuda Use Flash Attention2",
                      "type": "boolean"
                    },
                    "device": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "$ref": "#/$defs/AcceleratorDevice"
                        }
                      ],
                      "default": "auto",
                      "description": "Hardware device for model inference. Options: `auto` (automatic detection), `cpu` (CPU only), `cuda` (NVIDIA GPU), `cuda:N` (specific GPU), `mps` (Apple Silicon), `xpu` (Intel GPU). Auto mode selects the best available device. Can be set via DOCLING_DEVICE environment variable.",
                      "title": "Device"
                    },
                    "num_threads": {
                      "default": 4,
                      "description": "Number of CPU threads to use for model inference. Higher values can improve throughput on multi-core systems but may increase memory usage. Can be set via DOCLING_NUM_THREADS or OMP_NUM_THREADS environment variables. Recommended: number of physical CPU cores.",
                      "title": "Num Threads",
                      "type": "integer"
                    }
                  },
                  "title": "AcceleratorOptions",
                  "type": "object"
                },
                "ApiKserveV2ImageClassificationEngineOptions": {
                  "additionalProperties": false,
                  "description": "Runtime configuration for remote KServe v2 inference.",
                  "properties": {
                    "engine_type": {
                      "const": "api_kserve_v2",
                      "default": "api_kserve_v2",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "grpc_max_message_bytes": {
                      "default": 67108864,
                      "description": "Max send/receive gRPC message size in bytes.",
                      "minimum": 1,
                      "title": "Grpc Max Message Bytes",
                      "type": "integer"
                    },
                    "grpc_metadata": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "description": "Optional gRPC metadata for authentication/routing when transport='grpc'. No HTTP headers are reused in gRPC mode.",
                      "title": "Grpc Metadata",
                      "type": "object"
                    },
                    "grpc_use_binary_data": {
                      "default": true,
                      "description": "Whether to request/expect binary tensor payloads on gRPC output tensors. Set to False for servers that do not support binary_data output parameters.",
                      "title": "Grpc Use Binary Data",
                      "type": "boolean"
                    },
                    "grpc_use_tls": {
                      "default": false,
                      "description": "Whether to use TLS for the gRPC channel. When omitted, plain-text h2c is used.",
                      "title": "Grpc Use Tls",
                      "type": "boolean"
                    },
                    "headers": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "description": "Optional HTTP headers for authentication/routing when transport='http'.",
                      "title": "Headers",
                      "type": "object"
                    },
                    "model_name": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Remote model name registered in the KServe v2 endpoint. If omitted, a repo_id-derived default is used.",
                      "title": "Model Name"
                    },
                    "model_version": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Optional model version. If omitted, the server default is used.",
                      "title": "Model Version"
                    },
                    "request_parameters": {
                      "additionalProperties": true,
                      "description": "Optional top-level KServe v2 infer request parameters.",
                      "title": "Request Parameters",
                      "type": "object"
                    },
                    "timeout": {
                      "default": 60.0,
                      "description": "Per-request timeout in seconds for both HTTP and gRPC calls.",
                      "title": "Timeout",
                      "type": "number"
                    },
                    "top_k": {
                      "anyOf": [
                        {
                          "minimum": 1,
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Maximum number of classes to return. If None, all classes are returned.",
                      "title": "Top K"
                    },
                    "transport": {
                      "default": "grpc",
                      "description": "Transport protocol for KServe v2 calls. Use 'grpc' for binary tensor payloads (default), or 'http' for JSON REST.",
                      "enum": [
                        "grpc",
                        "http"
                      ],
                      "title": "Transport",
                      "type": "string"
                    },
                    "url": {
                      "description": "Endpoint URL for KServe v2 transport. For transport='http', use http(s)://host[:port] or plain host:port. For transport='grpc', use plain host:port.",
                      "title": "Url",
                      "type": "string"
                    }
                  },
                  "required": [
                    "url"
                  ],
                  "title": "ApiKserveV2ImageClassificationEngineOptions",
                  "type": "object"
                },
                "ApiModelConfig": {
                  "description": "API-specific model configuration.\n\nFor API engines, configuration is simpler - just params to send.",
                  "properties": {
                    "params": {
                      "additionalProperties": true,
                      "description": "API parameters (model name, max_tokens, etc.)",
                      "title": "Params",
                      "type": "object"
                    }
                  },
                  "title": "ApiModelConfig",
                  "type": "object"
                },
                "ApiVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Options for API-based VLM services.\n\nSupports multiple API variants:\n- Generic OpenAI-compatible API\n- Ollama\n- LM Studio\n- OpenAI",
                  "properties": {
                    "concurrency": {
                      "default": 1,
                      "description": "Number of concurrent requests",
                      "title": "Concurrency",
                      "type": "integer"
                    },
                    "engine_type": {
                      "const": "api",
                      "default": "api",
                      "description": "API variant to use",
                      "type": "string"
                    },
                    "headers": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "description": "HTTP headers for authentication",
                      "title": "Headers",
                      "type": "object"
                    },
                    "params": {
                      "additionalProperties": true,
                      "description": "Additional API parameters (model, max_tokens, etc.)",
                      "title": "Params",
                      "type": "object"
                    },
                    "timeout": {
                      "default": 60.0,
                      "description": "Request timeout in seconds",
                      "title": "Timeout",
                      "type": "number"
                    },
                    "url": {
                      "default": "http://localhost:11434/v1/chat/completions",
                      "description": "API endpoint URL",
                      "format": "uri",
                      "minLength": 1,
                      "title": "Url",
                      "type": "string"
                    }
                  },
                  "title": "ApiVlmEngineOptions",
                  "type": "object"
                },
                "AutoInlineVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Options for auto-selecting the best local inference engine.\n\nAutomatically selects the best available local engine based on:\n- Platform (macOS -> MLX, Linux/Windows -> Transformers/VLLM)\n- Available hardware (CUDA, MPS, CPU)\n- Model support",
                  "properties": {
                    "engine_type": {
                      "const": "auto_inline",
                      "default": "auto_inline",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "prefer_vllm": {
                      "default": false,
                      "description": "Prefer VLLM over Transformers when both are available on CUDA",
                      "title": "Prefer Vllm",
                      "type": "boolean"
                    }
                  },
                  "title": "AutoInlineVlmEngineOptions",
                  "type": "object"
                },
                "BaseImageClassificationEngineOptions": {
                  "description": "Base configuration shared across image-classification engines.",
                  "properties": {
                    "engine_type": {
                      "$ref": "#/$defs/ImageClassificationEngineType",
                      "description": "Type of inference engine to use"
                    },
                    "top_k": {
                      "anyOf": [
                        {
                          "minimum": 1,
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Maximum number of classes to return. If None, all classes are returned.",
                      "title": "Top K"
                    }
                  },
                  "required": [
                    "engine_type"
                  ],
                  "title": "BaseImageClassificationEngineOptions",
                  "type": "object"
                },
                "BaseLayoutOptions": {
                  "description": "Base options for document layout analysis models.\n\nLayout analysis detects the structural regions of a document page\n(text blocks, tables, figures, headers, etc.) and assigns content\ncells to those regions. This base class provides the shared controls\nfor empty-cluster retention and cell-assignment skipping.\n\nSee Also:\n    `LayoutOptions`: Default layout model configuration (Heron).\n    `LayoutObjectDetectionOptions`: Object-detection runtime layout\n        with preset support.",
                  "properties": {
                    "keep_empty_clusters": {
                      "default": false,
                      "description": "Retain empty clusters in layout analysis results. When False, clusters without content are removed. Enable for debugging or when empty regions are semantically important.",
                      "title": "Keep Empty Clusters",
                      "type": "boolean"
                    },
                    "skip_cell_assignment": {
                      "default": false,
                      "description": "Skip assignment of cells to table structures during layout analysis. When True, cells are detected but not associated with tables. Use for performance optimization when table structure is not needed.",
                      "title": "Skip Cell Assignment",
                      "type": "boolean"
                    }
                  },
                  "title": "BaseLayoutOptions",
                  "type": "object"
                },
                "BaseTableStructureOptions": {
                  "description": "Base options for table structure extraction models.\n\nServes as the abstract base for all table structure backends. Concrete\nimplementations (e.g., `TableStructureOptions` for TableFormer) inherit\nfrom this class and register their own `kind` discriminator.\n\nSee Also:\n    `TableStructureOptions`: Default TableFormer-based implementation.",
                  "properties": {},
                  "title": "BaseTableStructureOptions",
                  "type": "object"
                },
                "BaseVlmEngineOptions": {
                  "description": "Base configuration for VLM inference engines.\n\nEngine options are independent of model specifications and prompts.\nThey only control how the inference is executed.",
                  "properties": {
                    "engine_type": {
                      "$ref": "#/$defs/VlmEngineType",
                      "description": "Type of inference engine to use"
                    }
                  },
                  "required": [
                    "engine_type"
                  ],
                  "title": "BaseVlmEngineOptions",
                  "type": "object"
                },
                "ChartExtractionModelKind": {
                  "enum": [
                    "granite-vision",
                    "granite-vision-v4"
                  ],
                  "title": "ChartExtractionModelKind",
                  "type": "string"
                },
                "ChartExtractionModelOptions": {
                  "additionalProperties": false,
                  "properties": {
                    "chart2code": {
                      "default": false,
                      "title": "Chart2Code",
                      "type": "boolean"
                    },
                    "chart2csv": {
                      "default": true,
                      "title": "Chart2Csv",
                      "type": "boolean"
                    },
                    "chart2summary": {
                      "default": false,
                      "title": "Chart2Summary",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "chart_extraction",
                      "default": "chart_extraction",
                      "title": "Kind",
                      "type": "string"
                    },
                    "model": {
                      "$ref": "#/$defs/ChartExtractionModelKind",
                      "default": "granite-vision-v4"
                    }
                  },
                  "title": "ChartExtractionModelOptions",
                  "type": "object"
                },
                "CodeFormulaVlmOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for VLM-based code and formula extraction.\n\nThis stage uses vision-language models to extract code blocks and\nmathematical formulas from document images. Supports preset-based\nconfiguration via StagePresetMixin.\n\nExamples:\n    # Use CodeFormulaV2 preset\n    options = CodeFormulaVlmOptions.from_preset(\"codeformulav2\")\n\n    # Use Granite Docling preset\n    options = CodeFormulaVlmOptions.from_preset(\"granite_docling\")",
                  "properties": {
                    "engine_options": {
                      "anyOf": [
                        {
                          "$ref": "#/$defs/ApiVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/AutoInlineVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/MlxVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/TransformersVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/VllmVlmEngineOptions"
                        }
                      ],
                      "description": "Runtime configuration (transformers, mlx, api, etc.)"
                    },
                    "extract_code": {
                      "default": true,
                      "description": "Extract code blocks",
                      "title": "Extract Code",
                      "type": "boolean"
                    },
                    "extract_formulas": {
                      "default": true,
                      "description": "Extract mathematical formulas",
                      "title": "Extract Formulas",
                      "type": "boolean"
                    },
                    "max_size": {
                      "anyOf": [
                        {
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Maximum image dimension (width or height)",
                      "title": "Max Size"
                    },
                    "model_spec": {
                      "$ref": "#/$defs/VlmModelSpec",
                      "description": "Model specification with runtime-specific overrides"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Image scaling factor for preprocessing",
                      "title": "Scale",
                      "type": "number"
                    }
                  },
                  "required": [
                    "engine_options",
                    "model_spec"
                  ],
                  "title": "CodeFormulaVlmOptions",
                  "type": "object"
                },
                "DocumentPictureClassifierOptions": {
                  "additionalProperties": false,
                  "description": "Options for configuring the DocumentPictureClassifier stage.",
                  "properties": {
                    "engine_options": {
                      "anyOf": [
                        {
                          "$ref": "#/$defs/ApiKserveV2ImageClassificationEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/OnnxRuntimeImageClassificationEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/TransformersImageClassificationEngineOptions"
                        }
                      ],
                      "description": "Runtime configuration for the image-classification engine."
                    },
                    "kind": {
                      "const": "document_picture_classifier",
                      "default": "document_picture_classifier",
                      "title": "Engine",
                      "type": "string"
                    },
                    "model_spec": {
                      "$ref": "#/$defs/ImageClassificationModelSpec",
                      "description": "Image-classification model specification for picture classification."
                    }
                  },
                  "required": [
                    "engine_options"
                  ],
                  "title": "DocumentPictureClassifierOptions",
                  "type": "object"
                },
                "EasyOcrOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for EasyOCR engine.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "confidence_threshold": {
                      "default": 0.5,
                      "description": "Minimum confidence score for text recognition. Text with confidence below this threshold is filtered out. Range: 0.0-1.0. Lower values include more text but may reduce accuracy.",
                      "title": "Confidence Threshold",
                      "type": "number"
                    },
                    "download_enabled": {
                      "default": true,
                      "description": "Allow automatic download of EasyOCR models on first use. Disable for offline environments where models must be pre-installed.",
                      "title": "Download Enabled",
                      "type": "boolean"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "easyocr",
                      "default": "easyocr",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "fr",
                        "de",
                        "es",
                        "en"
                      ],
                      "description": "List of language codes for OCR. EasyOCR supports 80+ languages. Use ISO 639-1 codes (e.g., `en`, `fr`, `de`). Multiple languages can be specified for multilingual documents.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "model_storage_directory": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Directory path for storing downloaded EasyOCR models. If None, uses default EasyOCR cache location. Useful for offline environments or custom model management.",
                      "title": "Model Storage Directory"
                    },
                    "recog_network": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "default": "standard",
                      "description": "Recognition network architecture to use. Options: `standard` (default, balanced), `craft` (higher accuracy). Different networks may perform better on specific document types.",
                      "title": "Recog Network"
                    },
                    "suppress_mps_warnings": {
                      "default": true,
                      "description": "Suppress Metal Performance Shaders (MPS) warnings on macOS. Reduces console noise when using Apple Silicon GPUs with EasyOCR.",
                      "title": "Suppress Mps Warnings",
                      "type": "boolean"
                    },
                    "use_gpu": {
                      "anyOf": [
                        {
                          "type": "boolean"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Enable GPU acceleration for EasyOCR. If None, automatically detects and uses GPU if available. Set to False to force CPU-only processing.",
                      "title": "Use Gpu"
                    }
                  },
                  "title": "EasyOcrOptions",
                  "type": "object"
                },
                "EngineModelConfig": {
                  "description": "Engine-specific model configuration.\n\nAllows overriding model settings for specific engines.\nFor example, MLX might use a different repo_id than Transformers.",
                  "properties": {
                    "extra_config": {
                      "additionalProperties": true,
                      "description": "Additional engine-specific configuration",
                      "title": "Extra Config",
                      "type": "object"
                    },
                    "repo_id": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Override model repository ID for this engine",
                      "title": "Repo Id"
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
                      "description": "Override model revision for this engine",
                      "title": "Revision"
                    },
                    "torch_dtype": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Override torch dtype for this engine (e.g., 'bfloat16')",
                      "title": "Torch Dtype"
                    }
                  },
                  "title": "EngineModelConfig",
                  "type": "object"
                },
                "ImageClassificationEngineType": {
                  "description": "Supported inference engine types for image-classification models.",
                  "enum": [
                    "onnxruntime",
                    "transformers",
                    "api_kserve_v2"
                  ],
                  "title": "ImageClassificationEngineType",
                  "type": "string"
                },
                "ImageClassificationModelSpec": {
                  "description": "Specification for an image-classification model.",
                  "properties": {
                    "engine_overrides": {
                      "additionalProperties": {
                        "$ref": "#/$defs/EngineModelConfig"
                      },
                      "description": "Engine-specific configuration overrides",
                      "propertyNames": {
                        "$ref": "#/$defs/ImageClassificationEngineType"
                      },
                      "title": "Engine Overrides",
                      "type": "object"
                    },
                    "name": {
                      "description": "Human-readable model name",
                      "title": "Name",
                      "type": "string"
                    },
                    "repo_id": {
                      "description": "Default HuggingFace repository ID",
                      "title": "Repo Id",
                      "type": "string"
                    },
                    "revision": {
                      "default": "main",
                      "description": "Default model revision",
                      "title": "Revision",
                      "type": "string"
                    }
                  },
                  "required": [
                    "name",
                    "repo_id"
                  ],
                  "title": "ImageClassificationModelSpec",
                  "type": "object"
                },
                "KserveV2OcrOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for KServe v2-based OCR (e.g., Triton Inference Server).\n\nThis OCR engine connects to a remote KServe v2-compatible inference server\n(such as Triton) to perform OCR via gRPC or HTTP. It combines standard OCR\noptions with KServe v2 connection settings inherited from KserveV2OptionsMixin.\n\nThe engine handles custom preprocessing (RGB conversion, transpose, batching)\nto match the expected input format of typical OCR models deployed on KServe v2\nendpoints.\n\nSee Also:\n    `KserveV2OptionsMixin`: Provides all KServe v2 connection configuration.\n    `RapidOcrOptions`: Local OCR engine for comparison.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "grpc_max_message_bytes": {
                      "default": 67108864,
                      "description": "Max send/receive gRPC message size in bytes.",
                      "minimum": 1,
                      "title": "Grpc Max Message Bytes",
                      "type": "integer"
                    },
                    "grpc_metadata": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "description": "Optional gRPC metadata for authentication/routing when transport='grpc'. No HTTP headers are reused in gRPC mode.",
                      "title": "Grpc Metadata",
                      "type": "object"
                    },
                    "grpc_use_binary_data": {
                      "default": true,
                      "description": "Whether to request/expect binary tensor payloads on gRPC output tensors. Set to False for servers that do not support binary_data output parameters.",
                      "title": "Grpc Use Binary Data",
                      "type": "boolean"
                    },
                    "grpc_use_tls": {
                      "default": false,
                      "description": "Whether to use TLS for the gRPC channel. When omitted, plain-text h2c is used.",
                      "title": "Grpc Use Tls",
                      "type": "boolean"
                    },
                    "headers": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "description": "Optional HTTP headers for authentication/routing when transport='http'.",
                      "title": "Headers",
                      "type": "object"
                    },
                    "kind": {
                      "const": "kserve_v2_ocr",
                      "default": "kserve_v2_ocr",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "english",
                        "chinese"
                      ],
                      "description": "List of OCR languages. Note: Language selection depends on the deployed model. This parameter is passed to the server but may not be used by all models.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "model_name": {
                      "default": "ocr",
                      "description": "Remote model name registered in the KServe v2 endpoint.",
                      "title": "Model Name",
                      "type": "string"
                    },
                    "model_version": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Optional model version. If omitted, the server default is used.",
                      "title": "Model Version"
                    },
                    "request_parameters": {
                      "additionalProperties": true,
                      "description": "Optional top-level KServe v2 infer request parameters.",
                      "title": "Request Parameters",
                      "type": "object"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Image scale multiplier for OCR processing. Higher values increase resolution for better text recognition. Default 2.0 converts 72 DPI to 144 DPI.",
                      "exclusiveMinimum": 0.0,
                      "title": "Scale",
                      "type": "number"
                    },
                    "timeout": {
                      "default": 60.0,
                      "description": "Per-request timeout in seconds for both HTTP and gRPC calls.",
                      "title": "Timeout",
                      "type": "number"
                    },
                    "transport": {
                      "default": "grpc",
                      "description": "Transport protocol for KServe v2 calls. Use 'grpc' for binary tensor payloads (default), or 'http' for JSON REST.",
                      "enum": [
                        "grpc",
                        "http"
                      ],
                      "title": "Transport",
                      "type": "string"
                    },
                    "url": {
                      "description": "Endpoint URL for KServe v2 transport. For transport='http', use http(s)://host[:port] or plain host:port. For transport='grpc', use plain host:port.",
                      "title": "Url",
                      "type": "string"
                    }
                  },
                  "required": [
                    "url"
                  ],
                  "title": "KserveV2OcrOptions",
                  "type": "object"
                },
                "LayoutModelConfig": {
                  "description": "Configuration for document layout analysis models from HuggingFace.",
                  "properties": {
                    "model_path": {
                      "description": "Relative path within the repository to model artifacts. Empty string indicates artifacts are in the repository root. Used for repositories with multiple models or nested structures.",
                      "title": "Model Path",
                      "type": "string"
                    },
                    "name": {
                      "description": "Human-readable name identifier for the layout model. Used for logging, debugging, and model selection.",
                      "examples": [
                        "docling_layout_heron",
                        "docling_layout_egret_large"
                      ],
                      "title": "Name",
                      "type": "string"
                    },
                    "repo_id": {
                      "description": "HuggingFace repository ID where the model is hosted. Used to download model weights and configuration files from HuggingFace Hub.",
                      "examples": [
                        "docling-project/docling-layout-heron",
                        "docling-project/docling-layout-egret-large"
                      ],
                      "title": "Repo Id",
                      "type": "string"
                    },
                    "revision": {
                      "description": "Git revision (branch, tag, or commit hash) of the model repository to use. Allows pinning to specific model versions for reproducibility.",
                      "examples": [
                        "main",
                        "v1.0.0"
                      ],
                      "title": "Revision",
                      "type": "string"
                    },
                    "supported_devices": {
                      "default": [
                        "cpu",
                        "cuda",
                        "mps",
                        "xpu"
                      ],
                      "description": "List of hardware accelerators supported by this model. The model can only run on devices in this list.",
                      "items": {
                        "$ref": "#/$defs/AcceleratorDevice"
                      },
                      "title": "Supported Devices",
                      "type": "array"
                    }
                  },
                  "required": [
                    "name",
                    "repo_id",
                    "revision",
                    "model_path"
                  ],
                  "title": "LayoutModelConfig",
                  "type": "object"
                },
                "LayoutOptions": {
                  "additionalProperties": false,
                  "description": "Options for layout processing using Docling's built-in layout model.\n\nProvides configuration for the default layout analysis path, including\nmodel selection (e.g., Heron, Egret variants) and orphan cluster\ncreation for elements not assigned to any detected structure.\n\nNotes:\n    The default model is ``DOCLING_LAYOUT_HERON``. For higher accuracy\n    on complex documents, consider ``DOCLING_LAYOUT_EGRET_LARGE`` or\n    ``DOCLING_LAYOUT_EGRET_XLARGE``.",
                  "properties": {
                    "create_orphan_clusters": {
                      "default": true,
                      "description": "Create clusters for orphaned elements not assigned to any structure. When True, isolated text or elements are grouped into their own clusters. Recommended for complete document coverage.",
                      "title": "Create Orphan Clusters",
                      "type": "boolean"
                    },
                    "keep_empty_clusters": {
                      "default": false,
                      "description": "Retain empty clusters in layout analysis results. When False, clusters without content are removed. Enable for debugging or when empty regions are semantically important.",
                      "title": "Keep Empty Clusters",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "docling_layout_default",
                      "default": "docling_layout_default",
                      "title": "Engine",
                      "type": "string"
                    },
                    "model_spec": {
                      "$ref": "#/$defs/LayoutModelConfig",
                      "default": {
                        "model_path": "",
                        "name": "docling_layout_heron",
                        "repo_id": "docling-project/docling-layout-heron",
                        "revision": "main",
                        "supported_devices": [
                          "cpu",
                          "cuda",
                          "mps",
                          "xpu"
                        ]
                      },
                      "description": "Layout model configuration specifying which model to use for document layout analysis. Options include DOCLING_LAYOUT_HERON (default, balanced), DOCLING_LAYOUT_EGRET_* (higher accuracy), etc."
                    },
                    "skip_cell_assignment": {
                      "default": false,
                      "description": "Skip assignment of cells to table structures during layout analysis. When True, cells are detected but not associated with tables. Use for performance optimization when table structure is not needed.",
                      "title": "Skip Cell Assignment",
                      "type": "boolean"
                    }
                  },
                  "title": "LayoutOptions",
                  "type": "object"
                },
                "MlxVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Options for Apple MLX inference engine (Apple Silicon only).",
                  "properties": {
                    "engine_type": {
                      "const": "mlx",
                      "default": "mlx",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "trust_remote_code": {
                      "default": false,
                      "description": "Allow execution of custom code from model repo",
                      "title": "Trust Remote Code",
                      "type": "boolean"
                    }
                  },
                  "title": "MlxVlmEngineOptions",
                  "type": "object"
                },
                "OcrAutoOptions": {
                  "additionalProperties": false,
                  "description": "Automatic OCR engine selection based on system availability.\n\nWhen this option is used, Docling probes the runtime environment at\npipeline initialization and selects the best available OCR engine\n(e.g., EasyOCR if GPU is present, Tesseract otherwise). Language\nsettings are deferred to the chosen engine's defaults.\n\nNotes:\n    The `lang` field is intentionally defaulted to an empty list.\n    To control language selection, specify an explicit OCR engine\n    option class instead.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "auto",
                      "default": "auto",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [],
                      "description": "The automatic OCR engine will use the default values of the engine. Please specify the engine explicitly to change the language selection.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    }
                  },
                  "title": "OcrAutoOptions",
                  "type": "object"
                },
                "OcrMacOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for native macOS OCR using Vision framework.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "framework": {
                      "default": "vision",
                      "description": "macOS framework to use for OCR. Currently supports `vision` (Apple Vision framework). Future versions may support additional frameworks.",
                      "title": "Framework",
                      "type": "string"
                    },
                    "kind": {
                      "const": "ocrmac",
                      "default": "ocrmac",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "fr-FR",
                        "de-DE",
                        "es-ES",
                        "en-US"
                      ],
                      "description": "List of language locale codes for macOS OCR. Use format `language-REGION` (e.g., `en-US`, `fr-FR`). Leverages native macOS Vision framework for OCR on Apple platforms.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "recognition": {
                      "default": "accurate",
                      "description": "Recognition accuracy level. Options: `accurate` (higher quality, slower) or `fast` (lower quality, faster). Choose based on speed vs. accuracy requirements.",
                      "title": "Recognition",
                      "type": "string"
                    }
                  },
                  "title": "OcrMacOptions",
                  "type": "object"
                },
                "OcrOptions": {
                  "description": "Base configuration for Optical Character Recognition engines.\n\nDefines the common interface shared by all OCR engine implementations.\nSubclasses provide engine-specific parameters while inheriting the shared\nlanguage selection, full-page OCR toggle, and bitmap area threshold.\n\nSee Also:\n    `OcrAutoOptions`: Automatic engine selection based on availability.\n    `EasyOcrOptions`, `TesseractCliOcrOptions`, `TesseractOcrOptions`,\n    `RapidOcrOptions`, `OcrMacOptions`: Engine-specific configurations.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "lang": {
                      "description": "List of OCR languages to use. The format must match the values of the OCR engine of choice.",
                      "examples": [
                        [
                          "deu",
                          "eng"
                        ]
                      ],
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    }
                  },
                  "required": [
                    "lang"
                  ],
                  "title": "OcrOptions",
                  "type": "object"
                },
                "OnnxRuntimeImageClassificationEngineOptions": {
                  "additionalProperties": false,
                  "description": "Runtime configuration for ONNX Runtime based image-classification models.",
                  "properties": {
                    "engine_type": {
                      "const": "onnxruntime",
                      "default": "onnxruntime",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "graph_optimization_level": {
                      "default": 99,
                      "description": "ONNX Runtime graph optimization level. Accepts onnxruntime.GraphOptimizationLevel int values: 0 (ORT_DISABLE_ALL), 1 (ORT_ENABLE_BASIC), 2 (ORT_ENABLE_EXTENDED), 99 (ORT_ENABLE_ALL). Default enables all optimizations including layout optimizations.",
                      "title": "Graph Optimization Level",
                      "type": "integer"
                    },
                    "model_filename": {
                      "default": "model.onnx",
                      "description": "Filename of the ONNX export inside the model repository",
                      "title": "Model Filename",
                      "type": "string"
                    },
                    "providers": {
                      "description": "Ordered list of ONNX Runtime execution providers to try",
                      "items": {
                        "type": "string"
                      },
                      "title": "Providers",
                      "type": "array"
                    },
                    "top_k": {
                      "anyOf": [
                        {
                          "minimum": 1,
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Maximum number of classes to return. If None, all classes are returned.",
                      "title": "Top K"
                    }
                  },
                  "title": "OnnxRuntimeImageClassificationEngineOptions",
                  "type": "object"
                },
                "PictureClassificationLabel": {
                  "description": "PictureClassificationLabel.",
                  "enum": [
                    "bar_chart",
                    "box_plot",
                    "flow_chart",
                    "line_chart",
                    "pie_chart",
                    "scatter_plot",
                    "table",
                    "other_chart",
                    "full_page_image",
                    "page_thumbnail",
                    "photograph",
                    "chemistry_structure",
                    "bar_code",
                    "icon",
                    "logo",
                    "qr_code",
                    "signature",
                    "stamp",
                    "engineering_drawing",
                    "screenshot_from_computer",
                    "screenshot_from_manual",
                    "geographical_map",
                    "topographical_map",
                    "calendar",
                    "crossword_puzzle",
                    "music",
                    "other",
                    "cad_drawing",
                    "electrical_diagram",
                    "map",
                    "heatmap",
                    "chemistry_markush_structure",
                    "chemistry_molecular_structure",
                    "natural_image",
                    "picture_group",
                    "remote_sensing",
                    "scatter_chart",
                    "screenshot",
                    "stacked_bar_chart",
                    "stratigraphic_chart"
                  ],
                  "title": "PictureClassificationLabel",
                  "type": "string"
                },
                "PictureDescriptionApiOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for API-based picture description services.\n\nSends images to an OpenAI-compatible chat completions endpoint for\ndescription generation. Supports custom headers for authentication,\nconfigurable timeouts, and concurrent request control.\n\nNotes:\n    Requires ``enable_remote_services=True`` on the parent pipeline\n    options to permit external API calls.",
                  "properties": {
                    "batch_size": {
                      "default": 8,
                      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
                      "minimum": 1,
                      "title": "Batch Size",
                      "type": "integer"
                    },
                    "classification_allow": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
                      "title": "Classification Allow"
                    },
                    "classification_deny": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
                      "title": "Classification Deny"
                    },
                    "classification_min_confidence": {
                      "default": 0.0,
                      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
                      "title": "Classification Min Confidence",
                      "type": "number"
                    },
                    "concurrency": {
                      "default": 1,
                      "description": "Number of concurrent API requests allowed. Higher values improve throughput but may hit API rate limits. Adjust based on API service quotas and network capacity.",
                      "title": "Concurrency",
                      "type": "integer"
                    },
                    "headers": {
                      "additionalProperties": {
                        "type": "string"
                      },
                      "default": {},
                      "description": "HTTP headers to include in API requests. Use for authentication or custom headers required by your API service.",
                      "examples": [
                        {
                          "Authorization": "Bearer TOKEN"
                        }
                      ],
                      "title": "Headers",
                      "type": "object"
                    },
                    "kind": {
                      "const": "api",
                      "default": "api",
                      "title": "Engine",
                      "type": "string"
                    },
                    "params": {
                      "additionalProperties": true,
                      "default": {},
                      "description": "Additional query parameters to include in API requests. Service-specific parameters for customizing API behavior beyond standard options.",
                      "title": "Params",
                      "type": "object"
                    },
                    "picture_area_threshold": {
                      "default": 0.05,
                      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
                      "title": "Picture Area Threshold",
                      "type": "number"
                    },
                    "prompt": {
                      "default": "Describe this image in a few sentences.",
                      "description": "Prompt template sent to the vision model for image description. Customize to guide the model's output style, detail level, or focus.",
                      "examples": [
                        "Provide a technical description of this diagram"
                      ],
                      "title": "Prompt",
                      "type": "string"
                    },
                    "provenance": {
                      "default": "",
                      "description": "Provenance information to track the source or method of picture descriptions. Used for metadata and auditing purposes in the output document.",
                      "title": "Provenance",
                      "type": "string"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
                      "exclusiveMinimum": 0,
                      "title": "Scale",
                      "type": "number"
                    },
                    "timeout": {
                      "default": 20.0,
                      "description": "Maximum time in seconds to wait for API response before timing out. Increase for slow networks or complex image descriptions. Recommended: 10-60 seconds.",
                      "title": "Timeout",
                      "type": "number"
                    },
                    "url": {
                      "default": "http://localhost:8000/v1/chat/completions",
                      "description": "API endpoint URL for picture description service. Must be OpenAI-compatible chat completions endpoint. Default points to local server; update for cloud services or custom deployments.",
                      "format": "uri",
                      "minLength": 1,
                      "title": "Url",
                      "type": "string"
                    }
                  },
                  "title": "PictureDescriptionApiOptions",
                  "type": "object"
                },
                "PictureDescriptionBaseOptions": {
                  "description": "Base configuration for picture description models.\n\nProvides shared parameters for all picture description backends,\nincluding batch processing, image scaling, area thresholds, and\nclassification-based filtering (allow/deny lists). Concrete\nimplementations supply the actual model integration.\n\nSee Also:\n    `PictureDescriptionApiOptions`: OpenAI-compatible API backend.\n    `PictureDescriptionVlmOptions`: Legacy HuggingFace Transformers\n        backend.\n    `PictureDescriptionVlmEngineOptions`: New runtime-based backend\n        with preset support (recommended).",
                  "properties": {
                    "batch_size": {
                      "default": 8,
                      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
                      "minimum": 1,
                      "title": "Batch Size",
                      "type": "integer"
                    },
                    "classification_allow": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
                      "title": "Classification Allow"
                    },
                    "classification_deny": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
                      "title": "Classification Deny"
                    },
                    "classification_min_confidence": {
                      "default": 0.0,
                      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
                      "title": "Classification Min Confidence",
                      "type": "number"
                    },
                    "picture_area_threshold": {
                      "default": 0.05,
                      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
                      "title": "Picture Area Threshold",
                      "type": "number"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
                      "exclusiveMinimum": 0,
                      "title": "Scale",
                      "type": "number"
                    }
                  },
                  "title": "PictureDescriptionBaseOptions",
                  "type": "object"
                },
                "PictureDescriptionVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for VLM runtime-based picture description.\n\nThis is the new implementation that uses the pluggable runtime system with preset support.\nSupports all runtime types (Transformers, MLX, API, etc.) through the unified runtime interface.\n\nUse `from_preset()` to create instances from registered presets.\n\nExamples:\n    # Use preset with default runtime\n    options = PictureDescriptionVlmEngineOptions.from_preset(\"smolvlm\")\n\n    # Use preset with runtime override\n    from docling.datamodel.vlm_engine_options import MlxVlmEngineOptions, VlmEngineType\n    options = PictureDescriptionVlmEngineOptions.from_preset(\n        \"smolvlm\",\n        engine_options=MlxVlmEngineOptions(engine_type=VlmEngineType.MLX)\n    )",
                  "properties": {
                    "batch_size": {
                      "default": 8,
                      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
                      "minimum": 1,
                      "title": "Batch Size",
                      "type": "integer"
                    },
                    "classification_allow": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
                      "title": "Classification Allow"
                    },
                    "classification_deny": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
                      "title": "Classification Deny"
                    },
                    "classification_min_confidence": {
                      "default": 0.0,
                      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
                      "title": "Classification Min Confidence",
                      "type": "number"
                    },
                    "engine_options": {
                      "anyOf": [
                        {
                          "$ref": "#/$defs/ApiVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/AutoInlineVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/MlxVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/TransformersVlmEngineOptions"
                        },
                        {
                          "$ref": "#/$defs/VllmVlmEngineOptions"
                        }
                      ],
                      "description": "Runtime configuration (transformers, mlx, api, etc.)"
                    },
                    "generation_config": {
                      "additionalProperties": true,
                      "default": {
                        "do_sample": false,
                        "max_new_tokens": 200
                      },
                      "description": "Generation configuration for text generation. Controls output length, sampling strategy, temperature, etc.",
                      "title": "Generation Config",
                      "type": "object"
                    },
                    "kind": {
                      "const": "picture_description_vlm_engine",
                      "default": "picture_description_vlm_engine",
                      "title": "Engine",
                      "type": "string"
                    },
                    "model_spec": {
                      "$ref": "#/$defs/VlmModelSpec",
                      "description": "Model specification with runtime-specific overrides"
                    },
                    "picture_area_threshold": {
                      "default": 0.05,
                      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
                      "title": "Picture Area Threshold",
                      "type": "number"
                    },
                    "prompt": {
                      "default": "Describe this image in a few sentences.",
                      "description": "Prompt template for the vision model. Customize to control description style, detail level, or focus.",
                      "examples": [
                        "What is shown in this image?",
                        "Provide a detailed technical description"
                      ],
                      "title": "Prompt",
                      "type": "string"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
                      "exclusiveMinimum": 0,
                      "title": "Scale",
                      "type": "number"
                    }
                  },
                  "required": [
                    "engine_options",
                    "model_spec"
                  ],
                  "title": "PictureDescriptionVlmEngineOptions",
                  "type": "object"
                },
                "PictureDescriptionVlmOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for inline vision-language models for picture description.\n\nThis is the legacy implementation that uses direct HuggingFace Transformers integration.\nFor the new runtime-based system with preset support, use PictureDescriptionVlmEngineOptions.",
                  "properties": {
                    "batch_size": {
                      "default": 8,
                      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
                      "minimum": 1,
                      "title": "Batch Size",
                      "type": "integer"
                    },
                    "classification_allow": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
                      "title": "Classification Allow"
                    },
                    "classification_deny": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/PictureClassificationLabel"
                          },
                          "type": "array"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
                      "title": "Classification Deny"
                    },
                    "classification_min_confidence": {
                      "default": 0.0,
                      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
                      "title": "Classification Min Confidence",
                      "type": "number"
                    },
                    "generation_config": {
                      "additionalProperties": true,
                      "default": {
                        "do_sample": false,
                        "max_new_tokens": 200
                      },
                      "description": "HuggingFace generation configuration for text generation. Controls output length, sampling strategy, temperature, etc. See: https://huggingface.co/docs/transformers/en/main_classes/text_generation#transformers.GenerationConfig",
                      "title": "Generation Config",
                      "type": "object"
                    },
                    "kind": {
                      "const": "vlm",
                      "default": "vlm",
                      "title": "Engine",
                      "type": "string"
                    },
                    "padding_side": {
                      "default": "left",
                      "description": "Tokenizer padding side used for batched generation. Defaults to left to preserve the legacy behavior, but can be overridden for models that require right padding.",
                      "enum": [
                        "left",
                        "right"
                      ],
                      "title": "Padding Side",
                      "type": "string"
                    },
                    "picture_area_threshold": {
                      "default": 0.05,
                      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
                      "title": "Picture Area Threshold",
                      "type": "number"
                    },
                    "prompt": {
                      "default": "Describe this image in a few sentences.",
                      "description": "Prompt template for the vision model. Customize to control description style, detail level, or focus.",
                      "examples": [
                        "What is shown in this image?",
                        "Provide a detailed technical description"
                      ],
                      "title": "Prompt",
                      "type": "string"
                    },
                    "repo_id": {
                      "description": "HuggingFace model repository ID for the vision-language model. Must be a model capable of image-to-text generation for picture descriptions.",
                      "examples": [
                        "HuggingFaceTB/SmolVLM-256M-Instruct",
                        "ibm-granite/granite-vision-3.3-2b"
                      ],
                      "title": "Repo Id",
                      "type": "string"
                    },
                    "scale": {
                      "default": 2.0,
                      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
                      "exclusiveMinimum": 0,
                      "title": "Scale",
                      "type": "number"
                    }
                  },
                  "required": [
                    "repo_id"
                  ],
                  "title": "PictureDescriptionVlmOptions",
                  "type": "object"
                },
                "RapidOcrOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for RapidOCR engine with multiple backend support.\n\nSee Also:\n    - https://rapidai.github.io/RapidOCRDocs/install_usage/api/RapidOCR/\n    - https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/#__tabbed_3_4",
                  "properties": {
                    "backend": {
                      "default": "onnxruntime",
                      "description": "Inference backend for RapidOCR. Options: `onnxruntime` (default, cross-platform), `openvino` (Intel), `paddle` (PaddlePaddle), `torch` (PyTorch). Choose based on your hardware and available libraries.",
                      "enum": [
                        "onnxruntime",
                        "openvino",
                        "paddle",
                        "torch"
                      ],
                      "title": "Backend",
                      "type": "string"
                    },
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "cls_model_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Custom path to text classification model. If None, uses default RapidOCR model.",
                      "title": "Cls Model Path"
                    },
                    "det_model_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Custom path to text detection model. If None, uses default RapidOCR model.",
                      "title": "Det Model Path"
                    },
                    "font_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Custom path to font file for text rendering in visualization.",
                      "title": "Font Path"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "rapidocr",
                      "default": "rapidocr",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "english",
                        "chinese"
                      ],
                      "description": "List of OCR languages. Note: RapidOCR does not currently support language selection; this parameter is reserved for future compatibility. See RapidOCR documentation for supported languages.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "print_verbose": {
                      "default": false,
                      "description": "Enable verbose logging output from RapidOCR for debugging purposes.",
                      "title": "Print Verbose",
                      "type": "boolean"
                    },
                    "rapidocr_params": {
                      "additionalProperties": true,
                      "default": {},
                      "description": "Additional parameters to pass through to RapidOCR engine. Use this to override or extend default RapidOCR configuration with engine-specific options.",
                      "title": "Rapidocr Params",
                      "type": "object"
                    },
                    "rec_font_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "deprecated": true,
                      "description": "Deprecated. Use font_path instead.",
                      "title": "Rec Font Path"
                    },
                    "rec_keys_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Custom path to recognition keys file. If None, uses default RapidOCR keys.",
                      "title": "Rec Keys Path"
                    },
                    "rec_model_path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Custom path to text recognition model. If None, uses default RapidOCR model.",
                      "title": "Rec Model Path"
                    },
                    "text_score": {
                      "default": 0.5,
                      "description": "Minimum confidence score for text detection. Text regions with scores below this threshold are filtered out. Range: 0.0-1.0. Lower values detect more text but may include false positives.",
                      "title": "Text Score",
                      "type": "number"
                    },
                    "use_cls": {
                      "anyOf": [
                        {
                          "type": "boolean"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Enable text direction classification stage. If None, uses RapidOCR default behavior.",
                      "title": "Use Cls"
                    },
                    "use_det": {
                      "anyOf": [
                        {
                          "type": "boolean"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Enable text detection stage. If None, uses RapidOCR default behavior.",
                      "title": "Use Det"
                    },
                    "use_rec": {
                      "anyOf": [
                        {
                          "type": "boolean"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Enable text recognition stage. If None, uses RapidOCR default behavior.",
                      "title": "Use Rec"
                    }
                  },
                  "title": "RapidOcrOptions",
                  "type": "object"
                },
                "ResponseFormat": {
                  "enum": [
                    "doctags",
                    "markdown",
                    "deepseekocr_markdown",
                    "html",
                    "otsl",
                    "plaintext"
                  ],
                  "title": "ResponseFormat",
                  "type": "string"
                },
                "TableFormerMode": {
                  "description": "Operating modes for TableFormer table structure extraction model.\n\nControls the trade-off between processing speed and extraction accuracy.\nChoose based on your performance requirements and document complexity.\n\nAttributes:\n    FAST: Fast mode prioritizes speed over precision. Suitable for simple tables or high-volume\n        processing.\n    ACCURATE: Accurate mode provides higher quality results with slower processing. Recommended for complex\n        tables and production use.",
                  "enum": [
                    "fast",
                    "accurate"
                  ],
                  "title": "TableFormerMode",
                  "type": "string"
                },
                "TableStructureOptions": {
                  "additionalProperties": false,
                  "description": "Options for the table structure (TableFormer V1).",
                  "properties": {
                    "do_cell_matching": {
                      "default": true,
                      "description": "Enable cell matching to align detected table cells with their content. When enabled, the model attempts to match table structure predictions with actual cell content for improved accuracy.",
                      "title": "Do Cell Matching",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "docling_tableformer",
                      "default": "docling_tableformer",
                      "title": "Engine",
                      "type": "string"
                    },
                    "mode": {
                      "$ref": "#/$defs/TableFormerMode",
                      "default": "accurate",
                      "description": "Table structure extraction mode. `accurate` provides higher quality results with slower processing, while `fast` prioritizes speed over precision. Recommended: `accurate` for production use."
                    }
                  },
                  "title": "TableStructureOptions",
                  "type": "object"
                },
                "TesseractCliOcrOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for Tesseract OCR via command-line interface.",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "tesseract",
                      "default": "tesseract",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "fra",
                        "deu",
                        "spa",
                        "eng"
                      ],
                      "description": "List of Tesseract language codes. Use 3-letter ISO 639-2 codes (e.g., `eng`, `fra`, `deu`). Multiple languages enable multilingual OCR. Requires corresponding Tesseract language data files.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Path to Tesseract data directory containing language files. If None, uses Tesseract's default TESSDATA_PREFIX location.",
                      "title": "Path"
                    },
                    "psm": {
                      "anyOf": [
                        {
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Page Segmentation Mode for Tesseract. Values 0-13 control how Tesseract segments the page. Common values: 3 (auto), 6 (uniform block), 11 (sparse text). If None, uses Tesseract default.",
                      "title": "Psm"
                    },
                    "tesseract_cmd": {
                      "default": "tesseract",
                      "description": "Command or path to Tesseract executable. Use `tesseract` if in system PATH, or provide full path for custom installations (e.g., `/usr/local/bin/tesseract`).",
                      "title": "Tesseract Cmd",
                      "type": "string"
                    }
                  },
                  "title": "TesseractCliOcrOptions",
                  "type": "object"
                },
                "TesseractOcrOptions": {
                  "additionalProperties": false,
                  "description": "Configuration for Tesseract OCR via Python bindings (tesserocr).",
                  "properties": {
                    "bitmap_area_threshold": {
                      "default": 0.05,
                      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
                      "examples": [
                        0.05,
                        0.1
                      ],
                      "title": "Bitmap Area Threshold",
                      "type": "number"
                    },
                    "force_full_page_ocr": {
                      "default": false,
                      "description": "If enabled, a full-page OCR is always applied.",
                      "examples": [
                        false
                      ],
                      "title": "Force Full Page Ocr",
                      "type": "boolean"
                    },
                    "kind": {
                      "const": "tesserocr",
                      "default": "tesserocr",
                      "title": "Engine",
                      "type": "string"
                    },
                    "lang": {
                      "default": [
                        "fra",
                        "deu",
                        "spa",
                        "eng"
                      ],
                      "description": "List of Tesseract language codes. Use 3-letter ISO 639-2 codes (e.g., `eng`, `fra`, `deu`). Multiple languages enable multilingual OCR. Requires corresponding Tesseract language data files.",
                      "items": {
                        "type": "string"
                      },
                      "title": "Lang",
                      "type": "array"
                    },
                    "path": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Path to Tesseract data directory containing language files. If None, uses Tesseract's default TESSDATA_PREFIX location.",
                      "title": "Path"
                    },
                    "psm": {
                      "anyOf": [
                        {
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Page Segmentation Mode for Tesseract. Values 0-13 control how Tesseract segments the page. Common values: 3 (auto), 6 (uniform block), 11 (sparse text). If None, uses Tesseract default.",
                      "title": "Psm"
                    }
                  },
                  "title": "TesseractOcrOptions",
                  "type": "object"
                },
                "TransformersImageClassificationEngineOptions": {
                  "additionalProperties": false,
                  "description": "Runtime configuration for Transformers-based image-classification models.",
                  "properties": {
                    "compile_model": {
                      "description": "Whether to compile the model with torch.compile() for better performance.",
                      "title": "Compile Model",
                      "type": "boolean"
                    },
                    "engine_type": {
                      "const": "transformers",
                      "default": "transformers",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "top_k": {
                      "anyOf": [
                        {
                          "minimum": 1,
                          "type": "integer"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Maximum number of classes to return. If None, all classes are returned.",
                      "title": "Top K"
                    },
                    "torch_dtype": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "PyTorch dtype for model inference (e.g., 'float32', 'float16', 'bfloat16')",
                      "title": "Torch Dtype"
                    }
                  },
                  "title": "TransformersImageClassificationEngineOptions",
                  "type": "object"
                },
                "TransformersVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Options for HuggingFace Transformers inference engine.",
                  "properties": {
                    "compile_model": {
                      "description": "Whether to compile the model with torch.compile() for better performance.",
                      "title": "Compile Model",
                      "type": "boolean"
                    },
                    "device": {
                      "anyOf": [
                        {
                          "$ref": "#/$defs/AcceleratorDevice"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Device to use (auto-detected if None)"
                    },
                    "engine_type": {
                      "const": "transformers",
                      "default": "transformers",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "llm_int8_threshold": {
                      "default": 6.0,
                      "description": "Threshold for LLM.int8() quantization",
                      "title": "Llm Int8 Threshold",
                      "type": "number"
                    },
                    "load_in_8bit": {
                      "default": true,
                      "description": "Load model in 8-bit precision using bitsandbytes",
                      "title": "Load In 8Bit",
                      "type": "boolean"
                    },
                    "quantized": {
                      "default": false,
                      "description": "Whether the model is pre-quantized",
                      "title": "Quantized",
                      "type": "boolean"
                    },
                    "torch_dtype": {
                      "anyOf": [
                        {
                          "type": "string"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "PyTorch dtype (e.g., 'float16', 'bfloat16')",
                      "title": "Torch Dtype"
                    },
                    "trust_remote_code": {
                      "default": false,
                      "description": "Allow execution of custom code from model repo",
                      "title": "Trust Remote Code",
                      "type": "boolean"
                    },
                    "use_kv_cache": {
                      "default": true,
                      "description": "Enable key-value caching for attention",
                      "title": "Use Kv Cache",
                      "type": "boolean"
                    }
                  },
                  "title": "TransformersVlmEngineOptions",
                  "type": "object"
                },
                "VllmCudaGraphMode": {
                  "description": "CUDA graph capture mode for the vLLM v1 engine.\n\nControls whether and how vLLM captures CUDA graphs to speed up inference.\nCUDA graphs reduce kernel-launch overhead by replaying a recorded sequence\nof CUDA operations instead of launching each kernel individually.\n\nNONE:\n    Disable CUDA graphs entirely; everything runs in eager mode.\n    Fastest startup, lowest steady-state throughput.\n    Best for short-lived processes, notebooks, and debugging.\n\nFULL:\n    Capture the entire forward pass as one monolithic CUDA graph.\n    Maximum graph coverage but requires very static execution shapes;\n    may fail with some models or dynamic workloads.\n\nPIECEWISE:\n    Capture segments of the model (e.g. transformer blocks) as multiple\n    smaller graphs between selected ops.  Handles dynamic shapes better\n    than FULL while still accelerating most of the forward pass.\n\nFULL_AND_PIECEWISE:\n    Hybrid mode (default in many vLLM versions): FULL graphs for\n    decode-only batches; PIECEWISE graphs for prefill and mixed\n    prefill+decode batches.  Usually the best throughput option for\n    typical LLM serving workloads.\n\nFULL_DECODE_ONLY:\n    FULL CUDA graphs only for decode batches; prefill and mixed batches\n    run in eager mode.  Dramatically reduces graph-capture time and\n    memory footprint compared to FULL_AND_PIECEWISE while still\n    accelerating token generation.",
                  "enum": [
                    "NONE",
                    "FULL",
                    "PIECEWISE",
                    "FULL_AND_PIECEWISE",
                    "FULL_DECODE_ONLY"
                  ],
                  "title": "VllmCudaGraphMode",
                  "type": "string"
                },
                "VllmVlmEngineOptions": {
                  "additionalProperties": false,
                  "description": "Options for vLLM inference engine (high-throughput serving).",
                  "properties": {
                    "cudagraph_mode": {
                      "$ref": "#/$defs/VllmCudaGraphMode",
                      "default": "PIECEWISE",
                      "description": "CUDA graph capture mode (vLLM v1 engine only). See VllmCudaGraphMode for the available options and their trade-offs."
                    },
                    "device": {
                      "anyOf": [
                        {
                          "$ref": "#/$defs/AcceleratorDevice"
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Device to use (auto-detected if None)"
                    },
                    "engine_type": {
                      "const": "vllm",
                      "default": "vllm",
                      "title": "Engine Type",
                      "type": "string"
                    },
                    "gpu_memory_utilization": {
                      "default": 0.9,
                      "description": "Fraction of GPU memory to use",
                      "title": "Gpu Memory Utilization",
                      "type": "number"
                    },
                    "tensor_parallel_size": {
                      "default": 1,
                      "description": "Number of GPUs for tensor parallelism",
                      "title": "Tensor Parallel Size",
                      "type": "integer"
                    },
                    "trust_remote_code": {
                      "default": false,
                      "description": "Allow execution of custom code from model repo",
                      "title": "Trust Remote Code",
                      "type": "boolean"
                    }
                  },
                  "title": "VllmVlmEngineOptions",
                  "type": "object"
                },
                "VlmEngineType": {
                  "description": "Types of VLM inference engines available.",
                  "enum": [
                    "transformers",
                    "mlx",
                    "vllm",
                    "api",
                    "api_ollama",
                    "api_lmstudio",
                    "api_openai",
                    "auto_inline"
                  ],
                  "title": "VlmEngineType",
                  "type": "string"
                },
                "VlmModelSpec": {
                  "description": "Specification for a VLM model.\n\nThis defines the model configuration that is independent of the engine.\nIt includes:\n- Default model repository ID\n- Prompt template\n- Response format\n- Engine-specific overrides",
                  "properties": {
                    "api_overrides": {
                      "additionalProperties": {
                        "$ref": "#/$defs/ApiModelConfig"
                      },
                      "description": "API-specific configuration overrides",
                      "propertyNames": {
                        "$ref": "#/$defs/VlmEngineType"
                      },
                      "title": "Api Overrides",
                      "type": "object"
                    },
                    "default_repo_id": {
                      "description": "Default HuggingFace repository ID",
                      "title": "Default Repo Id",
                      "type": "string"
                    },
                    "engine_overrides": {
                      "additionalProperties": {
                        "$ref": "#/$defs/EngineModelConfig"
                      },
                      "description": "Engine-specific configuration overrides",
                      "propertyNames": {
                        "$ref": "#/$defs/VlmEngineType"
                      },
                      "title": "Engine Overrides",
                      "type": "object"
                    },
                    "max_new_tokens": {
                      "default": 4096,
                      "description": "Maximum number of new tokens to generate",
                      "title": "Max New Tokens",
                      "type": "integer"
                    },
                    "name": {
                      "description": "Human-readable model name",
                      "title": "Name",
                      "type": "string"
                    },
                    "prompt": {
                      "description": "Prompt template for this model",
                      "title": "Prompt",
                      "type": "string"
                    },
                    "response_format": {
                      "$ref": "#/$defs/ResponseFormat",
                      "description": "Expected response format from the model"
                    },
                    "revision": {
                      "default": "main",
                      "description": "Default model revision",
                      "title": "Revision",
                      "type": "string"
                    },
                    "stop_strings": {
                      "description": "Stop strings for generation",
                      "items": {
                        "type": "string"
                      },
                      "title": "Stop Strings",
                      "type": "array"
                    },
                    "supported_engines": {
                      "anyOf": [
                        {
                          "items": {
                            "$ref": "#/$defs/VlmEngineType"
                          },
                          "type": "array",
                          "uniqueItems": true
                        },
                        {
                          "type": "null"
                        }
                      ],
                      "description": "Set of supported engines (None = all supported)",
                      "title": "Supported Engines"
                    },
                    "trust_remote_code": {
                      "default": false,
                      "description": "Whether to trust remote code for this model",
                      "title": "Trust Remote Code",
                      "type": "boolean"
                    }
                  },
                  "required": [
                    "name",
                    "default_repo_id",
                    "prompt",
                    "response_format"
                  ],
                  "title": "VlmModelSpec",
                  "type": "object"
                }
              },
              "additionalProperties": false,
              "description": "Configuration options for the PDF document processing pipeline.\n\nNotes:\n    - Enabling multiple features (OCR, table structure, formulas) increases the processing time significantly.\n        Enable only necessary features for your use case.\n    - For production systems processing large document volumes, implement a timeout protection (for instance, 90-120\n        seconds via `document_timeout` parameter).\n    - OCR requires a system installation of engines (Tesseract, EasyOCR). Verify the installation before enabling\n        OCR via `do_ocr=True`.\n    - RapidOCR has known issues with read-only filesystems (e.g., Databricks). Consider Tesseract or alternative\n        backends for distributed systems.\n\nSee Also:\n    - `examples/pipeline_options_advanced.py`: Comprehensive configuration examples.",
              "properties": {
                "accelerator_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/AcceleratorOptions"
                    }
                  ],
                  "default": {
                    "cuda_use_flash_attention2": false,
                    "device": "auto",
                    "num_threads": 4
                  },
                  "description": "Hardware acceleration configuration for model inference. Controls GPU device selection, memory management, and execution optimization settings for layout, OCR, and table structure models."
                },
                "allow_external_plugins": {
                  "default": false,
                  "description": "Allow loading external third-party plugins for OCR, layout, table structure, or picture description models. Enables custom model implementations via plugin system. Disabled by default for security.",
                  "examples": [
                    false
                  ],
                  "title": "Allow External Plugins",
                  "type": "boolean"
                },
                "artifacts_path": {
                  "anyOf": [
                    {
                      "format": "path",
                      "type": "string"
                    },
                    {
                      "type": "string"
                    },
                    {
                      "type": "null"
                    }
                  ],
                  "description": "Local directory containing pre-downloaded model artifacts (weights, configs). If None, models are fetched from remote sources on first use. Use `docling-tools models download` to pre-fetch artifacts for offline operation or faster initialization.",
                  "examples": [
                    "./artifacts",
                    "/tmp/docling_outputs"
                  ],
                  "title": "Artifacts Path"
                },
                "batch_polling_interval_seconds": {
                  "default": 0.5,
                  "description": "Polling interval in seconds for batch collection in threaded pipeline stages. Each stage waits up to this duration to accumulate items before processing. Lower values reduce latency but may decrease batching efficiency. Only used by `StandardPdfPipeline` (threaded mode).",
                  "title": "Batch Polling Interval Seconds",
                  "type": "number"
                },
                "chart_extraction_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/ChartExtractionModelOptions"
                    }
                  ],
                  "default": {
                    "chart2code": false,
                    "chart2csv": true,
                    "chart2summary": false,
                    "kind": "chart_extraction",
                    "model": "granite-vision-v4"
                  },
                  "description": "Configuration for the chart extraction model, including which model variant to use and which output formats to generate (CSV, code, summary)."
                },
                "code_formula_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/CodeFormulaVlmOptions"
                    }
                  ],
                  "default": {
                    "engine_options": {
                      "engine_type": "auto_inline"
                    },
                    "extract_code": true,
                    "extract_formulas": true,
                    "model_spec": {
                      "api_overrides": {},
                      "default_repo_id": "docling-project/CodeFormulaV2",
                      "engine_overrides": {
                        "transformers": {
                          "extra_config": {
                            "extra_generation_config": {
                              "skip_special_tokens": false
                            },
                            "torch_dtype": "bfloat16",
                            "transformers_model_type": "automodel-imagetexttotext"
                          }
                        }
                      },
                      "max_new_tokens": 4096,
                      "name": "CodeFormulaV2",
                      "prompt": "",
                      "response_format": "plaintext",
                      "revision": "main",
                      "stop_strings": [
                        "</doctag>",
                        "<end_of_utterance>"
                      ],
                      "trust_remote_code": false
                    },
                    "scale": 2.0
                  },
                  "description": "Configuration for code and formula extraction using VLM. Uses new preset system (recommended). Default: 'default' preset. Only applicable when `do_code_enrichment=True` or `do_formula_enrichment=True`. Example: CodeFormulaVlmOptions.from_preset('granite_vision')"
                },
                "do_chart_extraction": {
                  "default": false,
                  "description": "Enable chart data extraction to convert bar, pie, and line charts into structured tabular data. Automatically enables picture classification. Only applicable when `do_chart_extraction=True`.",
                  "title": "Do Chart Extraction",
                  "type": "boolean"
                },
                "do_code_enrichment": {
                  "default": false,
                  "description": "Enable specialized processing for code blocks. Applies code-aware OCR and formatting to improve accuracy of programming language snippets, terminal output, and structured code content.",
                  "title": "Do Code Enrichment",
                  "type": "boolean"
                },
                "do_formula_enrichment": {
                  "default": false,
                  "description": "Enable mathematical formula recognition and LaTeX conversion. Uses specialized models to detect and extract mathematical expressions, converting them to LaTeX format for accurate representation.",
                  "title": "Do Formula Enrichment",
                  "type": "boolean"
                },
                "do_ocr": {
                  "default": true,
                  "description": "Enable Optical Character Recognition for scanned or image-based PDFs. Replaces or supplements programmatic text extraction with OCR-detected text. Required for scanned documents with no embedded text layer. Note: OCR significantly increases processing time.",
                  "title": "Do Ocr",
                  "type": "boolean"
                },
                "do_picture_classification": {
                  "default": false,
                  "description": "Enable picture classification to categorize images by type (photo, diagram, chart, etc.). Useful for downstream processing that requires image type awareness.",
                  "title": "Do Picture Classification",
                  "type": "boolean"
                },
                "do_picture_description": {
                  "default": false,
                  "description": "Enable automatic generation of textual descriptions for pictures using vision-language models. Descriptions are added to the document for accessibility and searchability.",
                  "title": "Do Picture Description",
                  "type": "boolean"
                },
                "do_table_structure": {
                  "default": true,
                  "description": "Enable table structure extraction and reconstruction. Detects table regions, extracts cell content with row/column relationships, and reconstructs the logical table structure for downstream processing.",
                  "title": "Do Table Structure",
                  "type": "boolean"
                },
                "document_timeout": {
                  "anyOf": [
                    {
                      "type": "number"
                    },
                    {
                      "type": "null"
                    }
                  ],
                  "description": "Maximum processing time in seconds before aborting document conversion. When exceeded, the pipeline stops processing and returns partial results with PARTIAL_SUCCESS status. If None, no timeout is enforced. Recommended: 90-120 seconds for production systems.",
                  "examples": [
                    10.0,
                    20.0
                  ],
                  "title": "Document Timeout"
                },
                "enable_remote_services": {
                  "default": false,
                  "description": "Allow pipeline to call external APIs or cloud services during processing. Required for API-based picture description models. Disabled by default for security and offline operation.",
                  "examples": [
                    false
                  ],
                  "title": "Enable Remote Services",
                  "type": "boolean"
                },
                "force_backend_text": {
                  "default": false,
                  "description": "Force use of PDF backend's native text extraction instead of layout model predictions. When enabled, bypasses the layout model's text detection and uses the embedded text from the PDF file directly. Useful for PDFs with reliable programmatic text layers.",
                  "title": "Force Backend Text",
                  "type": "boolean"
                },
                "generate_page_images": {
                  "default": false,
                  "description": "Generate rendered page images during extraction. Creates PNG representations of each page for visual preview, validation, or downstream image-based machine learning tasks.",
                  "title": "Generate Page Images",
                  "type": "boolean"
                },
                "generate_parsed_pages": {
                  "default": false,
                  "description": "Retain intermediate parsed page representations after processing. When enabled, keeps detailed page-level parsing data structures for debugging or advanced post-processing. Increases memory usage. Automatically disabled after document assembly unless explicitly enabled.",
                  "title": "Generate Parsed Pages",
                  "type": "boolean"
                },
                "generate_picture_images": {
                  "default": false,
                  "description": "Extract and save embedded images from the PDF. Exports individual images (figures, photos, diagrams, charts) found in the document as separate image files for downstream use.",
                  "title": "Generate Picture Images",
                  "type": "boolean"
                },
                "generate_table_images": {
                  "default": false,
                  "deprecated": true,
                  "title": "Generate Table Images",
                  "type": "boolean"
                },
                "images_scale": {
                  "default": 1.0,
                  "description": "Scaling factor for generated images. Higher values produce higher resolution but increase processing time and storage requirements. Recommended values: 1.0 (standard quality), 2.0 (high resolution), 0.5 (lower resolution for previews).",
                  "title": "Images Scale",
                  "type": "number"
                },
                "layout_batch_size": {
                  "default": 4,
                  "description": "Batch size for layout analysis stage in threaded pipeline. Pages are grouped and processed together by the layout model. Higher values improve throughput but increase memory usage. Only used by `StandardPdfPipeline` (threaded mode).",
                  "title": "Layout Batch Size",
                  "type": "integer"
                },
                "layout_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/LayoutOptions"
                    }
                  ],
                  "default": {
                    "create_orphan_clusters": true,
                    "keep_empty_clusters": false,
                    "kind": "docling_layout_default",
                    "model_spec": {
                      "model_path": "",
                      "name": "docling_layout_heron",
                      "repo_id": "docling-project/docling-layout-heron",
                      "revision": "main",
                      "supported_devices": [
                        "cpu",
                        "cuda",
                        "mps",
                        "xpu"
                      ]
                    },
                    "skip_cell_assignment": false
                  },
                  "description": "Configuration for document layout analysis model. Controls layout detection behavior including cluster creation for orphaned elements, cell assignment to table structures, and handling of empty regions. Specifies which layout model to use (default: Heron)."
                },
                "ocr_batch_size": {
                  "default": 4,
                  "description": "Batch size for OCR processing stage in threaded pipeline. Pages are grouped and processed together to improve throughput. Higher values increase GPU/CPU utilization but require more memory. Only used by `StandardPdfPipeline` (threaded mode).",
                  "title": "Ocr Batch Size",
                  "type": "integer"
                },
                "ocr_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/EasyOcrOptions"
                    },
                    {
                      "$ref": "#/$defs/KserveV2OcrOptions"
                    },
                    {
                      "$ref": "#/$defs/OcrAutoOptions"
                    },
                    {
                      "$ref": "#/$defs/OcrMacOptions"
                    },
                    {
                      "$ref": "#/$defs/RapidOcrOptions"
                    },
                    {
                      "$ref": "#/$defs/TesseractCliOcrOptions"
                    },
                    {
                      "$ref": "#/$defs/TesseractOcrOptions"
                    }
                  ],
                  "default": {
                    "bitmap_area_threshold": 0.05,
                    "force_full_page_ocr": false,
                    "kind": "auto",
                    "lang": []
                  },
                  "description": "Configuration for OCR engine. Specifies which OCR engine to use (Tesseract, EasyOCR, RapidOCR, etc.) and engine-specific settings. Only applicable when `do_ocr=True`."
                },
                "picture_classification_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/DocumentPictureClassifierOptions"
                    }
                  ],
                  "default": {
                    "engine_options": {
                      "engine_type": "transformers"
                    },
                    "kind": "document_picture_classifier",
                    "model_spec": {
                      "engine_overrides": {},
                      "name": "document_figure_classifier_v2",
                      "repo_id": "docling-project/DocumentFigureClassifier-v2.5",
                      "revision": "main"
                    }
                  },
                  "description": "Configuration for picture classification model/runtime. Supports selecting transformers, onnxruntime, or remote api_kserve_v2 inference engines."
                },
                "picture_description_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/PictureDescriptionApiOptions"
                    },
                    {
                      "$ref": "#/$defs/PictureDescriptionVlmEngineOptions"
                    },
                    {
                      "$ref": "#/$defs/PictureDescriptionVlmOptions"
                    }
                  ],
                  "default": {
                    "batch_size": 8,
                    "classification_min_confidence": 0.0,
                    "engine_options": {
                      "engine_type": "auto_inline"
                    },
                    "generation_config": {
                      "do_sample": false,
                      "max_new_tokens": 200
                    },
                    "kind": "picture_description_vlm_engine",
                    "model_spec": {
                      "api_overrides": {
                        "api_lmstudio": {
                          "params": {
                            "model": "smolvlm-256m-instruct"
                          }
                        }
                      },
                      "default_repo_id": "HuggingFaceTB/SmolVLM-256M-Instruct",
                      "engine_overrides": {
                        "mlx": {
                          "extra_config": {},
                          "repo_id": "moot20/SmolVLM-256M-Instruct-MLX"
                        },
                        "transformers": {
                          "extra_config": {
                            "transformers_model_type": "automodel-imagetexttotext"
                          },
                          "torch_dtype": "bfloat16"
                        }
                      },
                      "max_new_tokens": 4096,
                      "name": "SmolVLM-256M-Instruct",
                      "prompt": "Describe this image in a few sentences.",
                      "response_format": "plaintext",
                      "revision": "main",
                      "stop_strings": [],
                      "trust_remote_code": false
                    },
                    "picture_area_threshold": 0.05,
                    "prompt": "Describe this image in a few sentences.",
                    "scale": 2.0
                  },
                  "description": "Configuration for picture description model. Uses new preset system (recommended). Default: 'smolvlm' preset. Only applicable when `do_picture_description=True`. Example: PictureDescriptionVlmOptions.from_preset('granite_vision')"
                },
                "queue_max_size": {
                  "default": 100,
                  "description": "Maximum queue size for inter-stage communication in threaded pipeline. Limits the number of items buffered between processing stages to prevent memory overflow. When full, upstream stages block until space is available. Only used by `StandardPdfPipeline` (threaded mode).",
                  "title": "Queue Max Size",
                  "type": "integer"
                },
                "table_batch_size": {
                  "default": 4,
                  "description": "Batch size for table structure extraction stage in threaded pipeline. Tables from multiple pages are processed together. Higher values improve throughput but increase memory usage. Only used by `StandardPdfPipeline` (threaded mode).",
                  "title": "Table Batch Size",
                  "type": "integer"
                },
                "table_structure_options": {
                  "anyOf": [
                    {
                      "$ref": "#/$defs/TableStructureOptions"
                    }
                  ],
                  "default": {
                    "do_cell_matching": true,
                    "kind": "docling_tableformer",
                    "mode": "accurate"
                  },
                  "description": "Configuration for table structure extraction. Controls table detection accuracy, cell matching behavior, and table formatting. Only applicable when `do_table_structure=True`."
                }
              },
              "title": "PdfPipelineOptions",
              "type": "object"
            }
          },
          "formats": {
            "items": {
              "enum": [
                "markdown",
                "json",
                "html",
                "txt",
                "doclang",
                "doctags",
                "document_tokens",
                "element_tree",
                "vtt"
              ],
              "type": "string"
            },
            "maxItems": 9,
            "minItems": 1,
            "title": "Formats",
            "type": "array"
          },
          "output_format": {
            "default": "markdown",
            "enum": [
              "markdown",
              "json",
              "html",
              "txt",
              "doclang",
              "doctags",
              "document_tokens",
              "element_tree",
              "vtt"
            ],
            "title": "Output Format",
            "type": "string"
          },
          "export_options": {
            "additionalProperties": {
              "additionalProperties": true,
              "type": "object"
            },
            "description": "Parâmetros nativos por formato; caminhos de imagens são geridos pelo servidor.",
            "title": "Export Options",
            "type": "object"
          },
          "page_range": {
            "anyOf": [
              {
                "maxItems": 2,
                "minItems": 2,
                "prefixItems": [
                  {
                    "type": "integer"
                  },
                  {
                    "type": "integer"
                  }
                ],
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "description": "Primeira/última página inclusivas, numeradas a partir de 1.",
            "title": "Page Range"
          },
          "max_num_pages": {
            "anyOf": [
              {
                "minimum": 1,
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Max Num Pages"
          },
          "max_file_size": {
            "anyOf": [
              {
                "minimum": 1,
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "description": "Limite da conversão em bytes, adicional ao limite de upload do serviço.",
            "title": "Max File Size"
          },
          "raises_on_error": {
            "default": true,
            "title": "Raises On Error",
            "type": "boolean"
          }
        },
        "title": "DocumentOptions",
        "type": "object"
      }
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
    },
    "datalake_connection_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Connection Id"
    },
    "datalake_bucket": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Bucket"
    },
    "datalake_prefix": {
      "type": "string",
      "title": "Datalake Prefix",
      "default": ""
    },
    "datalake_partitioning": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Partitioning",
      "description": "JSON da estratégia por solicitação; omitir herda a conexão. Ex.: {\"mode\":\"custom\",\"fields\":[{\"field\":\"custom\",\"key\":\"client_id\"}],\"missing\":\"require\",\"analytics\":\"jsonl\"}"
    },
    "datalake_partition_values": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Datalake Partition Values",
      "description": "JSON de valores por job. Chaves fora da estratégia preservam contexto no dataset sem criar diretórios. Ex.: {\"client_id\":\"client-42\",\"conversation_id\":\"chat-7\",\"agent_id\":\"support-agent\"}"
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
| `exports` | não | object / null |  |  |
| `assets` | não | array de object / null |  |  |

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
    },
    "exports": {
      "anyOf": [
        {
          "additionalProperties": {
            "type": "string"
          },
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "title": "Exports"
    },
    "assets": {
      "anyOf": [
        {
          "items": {
            "additionalProperties": true,
            "type": "object"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Assets"
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
| `language` | não | string | default="pt"; pattern="^[a-z]{2,3}$" |  |
| `options` | não | [LiveOptions](#model-liveoptions) |  |  |
| `audio` | não | [AudioFormat](#model-audioformat) |  |  |
| `datalake` | não | [Destination](#model-destination) / null |  |  |

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
      "pattern": "^[a-z]{2,3}$",
      "title": "Language",
      "default": "pt"
    },
    "options": {
      "$ref": "#/components/schemas/LiveOptions"
    },
    "audio": {
      "$ref": "#/components/schemas/AudioFormat"
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

<a id="model-doclingacceleratordevice"></a>

### DoclingAcceleratorDevice

Devices to run model inference

Esquema JSON completo:

```json
{
  "description": "Devices to run model inference",
  "enum": [
    "auto",
    "cpu",
    "cuda",
    "mps",
    "xpu"
  ],
  "title": "AcceleratorDevice",
  "type": "string"
}
```

<a id="model-doclingacceleratoroptions"></a>

### DoclingAcceleratorOptions

Hardware acceleration configuration for model inference.

Can be configured via environment variables with DOCLING_ prefix.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `cuda_use_flash_attention2` | não | boolean | default=false | Enable Flash Attention 2 optimization for CUDA devices. Provides significant speedup and memory reduction for transformer models on compatible NVIDIA GPUs (Ampere or newer). Requires flash-attn package installation. Can be set via DOCLING_CUDA_USE_FLASH_ATTENTION2 environment variable. |
| `device` | não | string / [DoclingAcceleratorDevice](#model-doclingacceleratordevice) | default="auto" | Hardware device for model inference. Options: `auto` (automatic detection), `cpu` (CPU only), `cuda` (NVIDIA GPU), `cuda:N` (specific GPU), `mps` (Apple Silicon), `xpu` (Intel GPU). Auto mode selects the best available device. Can be set via DOCLING_DEVICE environment variable. |
| `num_threads` | não | integer | default=4 | Number of CPU threads to use for model inference. Higher values can improve throughput on multi-core systems but may increase memory usage. Can be set via DOCLING_NUM_THREADS or OMP_NUM_THREADS environment variables. Recommended: number of physical CPU cores. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Hardware acceleration configuration for model inference.\n\nCan be configured via environment variables with DOCLING_ prefix.",
  "properties": {
    "cuda_use_flash_attention2": {
      "default": false,
      "description": "Enable Flash Attention 2 optimization for CUDA devices. Provides significant speedup and memory reduction for transformer models on compatible NVIDIA GPUs (Ampere or newer). Requires flash-attn package installation. Can be set via DOCLING_CUDA_USE_FLASH_ATTENTION2 environment variable.",
      "title": "Cuda Use Flash Attention2",
      "type": "boolean"
    },
    "device": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "$ref": "#/components/schemas/DoclingAcceleratorDevice"
        }
      ],
      "default": "auto",
      "description": "Hardware device for model inference. Options: `auto` (automatic detection), `cpu` (CPU only), `cuda` (NVIDIA GPU), `cuda:N` (specific GPU), `mps` (Apple Silicon), `xpu` (Intel GPU). Auto mode selects the best available device. Can be set via DOCLING_DEVICE environment variable.",
      "title": "Device"
    },
    "num_threads": {
      "default": 4,
      "description": "Number of CPU threads to use for model inference. Higher values can improve throughput on multi-core systems but may increase memory usage. Can be set via DOCLING_NUM_THREADS or OMP_NUM_THREADS environment variables. Recommended: number of physical CPU cores.",
      "title": "Num Threads",
      "type": "integer"
    }
  },
  "title": "AcceleratorOptions",
  "type": "object"
}
```

<a id="model-doclingapikservev2imageclassificationengineoptions"></a>

### DoclingApiKserveV2ImageClassificationEngineOptions

Runtime configuration for remote KServe v2 inference.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_type` | não | string | default="api_kserve_v2"; const="api_kserve_v2" |  |
| `grpc_max_message_bytes` | não | integer | default=67108864; minimum=1 | Max send/receive gRPC message size in bytes. |
| `grpc_metadata` | não | object | additionalProperties={"type": "string"} | Optional gRPC metadata for authentication/routing when transport='grpc'. No HTTP headers are reused in gRPC mode. |
| `grpc_use_binary_data` | não | boolean | default=true | Whether to request/expect binary tensor payloads on gRPC output tensors. Set to False for servers that do not support binary_data output parameters. |
| `grpc_use_tls` | não | boolean | default=false | Whether to use TLS for the gRPC channel. When omitted, plain-text h2c is used. |
| `headers` | não | object | additionalProperties={"type": "string"} | Optional HTTP headers for authentication/routing when transport='http'. |
| `model_name` | não | string / null | default=null | Remote model name registered in the KServe v2 endpoint. If omitted, a repo_id-derived default is used. |
| `model_version` | não | string / null | default=null | Optional model version. If omitted, the server default is used. |
| `request_parameters` | não | object | additionalProperties=true | Optional top-level KServe v2 infer request parameters. |
| `timeout` | não | number | default=60.0 | Per-request timeout in seconds for both HTTP and gRPC calls. |
| `top_k` | não | integer / null | default=null | Maximum number of classes to return. If None, all classes are returned. |
| `transport` | não | string | default="grpc"; enum=["grpc", "http"] | Transport protocol for KServe v2 calls. Use 'grpc' for binary tensor payloads (default), or 'http' for JSON REST. |
| `url` | sim | string |  | Endpoint URL for KServe v2 transport. For transport='http', use http(s)://host[:port] or plain host:port. For transport='grpc', use plain host:port. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Runtime configuration for remote KServe v2 inference.",
  "properties": {
    "engine_type": {
      "const": "api_kserve_v2",
      "default": "api_kserve_v2",
      "title": "Engine Type",
      "type": "string"
    },
    "grpc_max_message_bytes": {
      "default": 67108864,
      "description": "Max send/receive gRPC message size in bytes.",
      "minimum": 1,
      "title": "Grpc Max Message Bytes",
      "type": "integer"
    },
    "grpc_metadata": {
      "additionalProperties": {
        "type": "string"
      },
      "description": "Optional gRPC metadata for authentication/routing when transport='grpc'. No HTTP headers are reused in gRPC mode.",
      "title": "Grpc Metadata",
      "type": "object"
    },
    "grpc_use_binary_data": {
      "default": true,
      "description": "Whether to request/expect binary tensor payloads on gRPC output tensors. Set to False for servers that do not support binary_data output parameters.",
      "title": "Grpc Use Binary Data",
      "type": "boolean"
    },
    "grpc_use_tls": {
      "default": false,
      "description": "Whether to use TLS for the gRPC channel. When omitted, plain-text h2c is used.",
      "title": "Grpc Use Tls",
      "type": "boolean"
    },
    "headers": {
      "additionalProperties": {
        "type": "string"
      },
      "description": "Optional HTTP headers for authentication/routing when transport='http'.",
      "title": "Headers",
      "type": "object"
    },
    "model_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Remote model name registered in the KServe v2 endpoint. If omitted, a repo_id-derived default is used.",
      "title": "Model Name"
    },
    "model_version": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional model version. If omitted, the server default is used.",
      "title": "Model Version"
    },
    "request_parameters": {
      "additionalProperties": true,
      "description": "Optional top-level KServe v2 infer request parameters.",
      "title": "Request Parameters",
      "type": "object"
    },
    "timeout": {
      "default": 60.0,
      "description": "Per-request timeout in seconds for both HTTP and gRPC calls.",
      "title": "Timeout",
      "type": "number"
    },
    "top_k": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Maximum number of classes to return. If None, all classes are returned.",
      "title": "Top K"
    },
    "transport": {
      "default": "grpc",
      "description": "Transport protocol for KServe v2 calls. Use 'grpc' for binary tensor payloads (default), or 'http' for JSON REST.",
      "enum": [
        "grpc",
        "http"
      ],
      "title": "Transport",
      "type": "string"
    },
    "url": {
      "description": "Endpoint URL for KServe v2 transport. For transport='http', use http(s)://host[:port] or plain host:port. For transport='grpc', use plain host:port.",
      "title": "Url",
      "type": "string"
    }
  },
  "required": [
    "url"
  ],
  "title": "ApiKserveV2ImageClassificationEngineOptions",
  "type": "object",
  "x-unavailable-reason": "Serviços remotos desabilitados no servidor"
}
```

<a id="model-doclingapimodelconfig"></a>

### DoclingApiModelConfig

API-specific model configuration.

For API engines, configuration is simpler - just params to send.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `params` | não | object | additionalProperties=true | API parameters (model name, max_tokens, etc.) |

Esquema JSON completo:

```json
{
  "description": "API-specific model configuration.\n\nFor API engines, configuration is simpler - just params to send.",
  "properties": {
    "params": {
      "additionalProperties": true,
      "description": "API parameters (model name, max_tokens, etc.)",
      "title": "Params",
      "type": "object"
    }
  },
  "title": "ApiModelConfig",
  "type": "object"
}
```

<a id="model-doclingapivlmengineoptions"></a>

### DoclingApiVlmEngineOptions

Options for API-based VLM services.

Supports multiple API variants:
- Generic OpenAI-compatible API
- Ollama
- LM Studio
- OpenAI

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `concurrency` | não | integer | default=1 | Number of concurrent requests |
| `engine_type` | não | string | default="api"; const="api" | API variant to use |
| `headers` | não | object | additionalProperties={"type": "string"} | HTTP headers for authentication |
| `params` | não | object | additionalProperties=true | Additional API parameters (model, max_tokens, etc.) |
| `timeout` | não | number | default=60.0 | Request timeout in seconds |
| `url` | não | string (uri) | default="http://localhost:11434/v1/chat/completions"; minLength=1 | API endpoint URL |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Options for API-based VLM services.\n\nSupports multiple API variants:\n- Generic OpenAI-compatible API\n- Ollama\n- LM Studio\n- OpenAI",
  "properties": {
    "concurrency": {
      "default": 1,
      "description": "Number of concurrent requests",
      "title": "Concurrency",
      "type": "integer"
    },
    "engine_type": {
      "const": "api",
      "default": "api",
      "description": "API variant to use",
      "type": "string"
    },
    "headers": {
      "additionalProperties": {
        "type": "string"
      },
      "description": "HTTP headers for authentication",
      "title": "Headers",
      "type": "object"
    },
    "params": {
      "additionalProperties": true,
      "description": "Additional API parameters (model, max_tokens, etc.)",
      "title": "Params",
      "type": "object"
    },
    "timeout": {
      "default": 60.0,
      "description": "Request timeout in seconds",
      "title": "Timeout",
      "type": "number"
    },
    "url": {
      "default": "http://localhost:11434/v1/chat/completions",
      "description": "API endpoint URL",
      "format": "uri",
      "minLength": 1,
      "title": "Url",
      "type": "string"
    }
  },
  "title": "ApiVlmEngineOptions",
  "type": "object",
  "x-unavailable-reason": "Serviços remotos desabilitados no servidor"
}
```

<a id="model-doclingautoinlinevlmengineoptions"></a>

### DoclingAutoInlineVlmEngineOptions

Options for auto-selecting the best local inference engine.

Automatically selects the best available local engine based on:
- Platform (macOS -> MLX, Linux/Windows -> Transformers/VLLM)
- Available hardware (CUDA, MPS, CPU)
- Model support

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_type` | não | string | default="auto_inline"; const="auto_inline" |  |
| `prefer_vllm` | não | boolean | default=false | Prefer VLLM over Transformers when both are available on CUDA |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Options for auto-selecting the best local inference engine.\n\nAutomatically selects the best available local engine based on:\n- Platform (macOS -> MLX, Linux/Windows -> Transformers/VLLM)\n- Available hardware (CUDA, MPS, CPU)\n- Model support",
  "properties": {
    "engine_type": {
      "const": "auto_inline",
      "default": "auto_inline",
      "title": "Engine Type",
      "type": "string"
    },
    "prefer_vllm": {
      "default": false,
      "description": "Prefer VLLM over Transformers when both are available on CUDA",
      "title": "Prefer Vllm",
      "type": "boolean"
    }
  },
  "title": "AutoInlineVlmEngineOptions",
  "type": "object"
}
```

<a id="model-doclingbaseimageclassificationengineoptions"></a>

### DoclingBaseImageClassificationEngineOptions

Base configuration shared across image-classification engines.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_type` | sim | [DoclingImageClassificationEngineType](#model-doclingimageclassificationenginetype) |  | Type of inference engine to use |
| `top_k` | não | integer / null | default=null | Maximum number of classes to return. If None, all classes are returned. |

Esquema JSON completo:

```json
{
  "description": "Base configuration shared across image-classification engines.",
  "properties": {
    "engine_type": {
      "$ref": "#/components/schemas/DoclingImageClassificationEngineType",
      "description": "Type of inference engine to use"
    },
    "top_k": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Maximum number of classes to return. If None, all classes are returned.",
      "title": "Top K"
    }
  },
  "required": [
    "engine_type"
  ],
  "title": "BaseImageClassificationEngineOptions",
  "type": "object"
}
```

<a id="model-doclingbaselayoutoptions"></a>

### DoclingBaseLayoutOptions

Base options for document layout analysis models.

Layout analysis detects the structural regions of a document page
(text blocks, tables, figures, headers, etc.) and assigns content
cells to those regions. This base class provides the shared controls
for empty-cluster retention and cell-assignment skipping.

See Also:
    `LayoutOptions`: Default layout model configuration (Heron).
    `LayoutObjectDetectionOptions`: Object-detection runtime layout
        with preset support.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `keep_empty_clusters` | não | boolean | default=false | Retain empty clusters in layout analysis results. When False, clusters without content are removed. Enable for debugging or when empty regions are semantically important. |
| `skip_cell_assignment` | não | boolean | default=false | Skip assignment of cells to table structures during layout analysis. When True, cells are detected but not associated with tables. Use for performance optimization when table structure is not needed. |

Esquema JSON completo:

```json
{
  "description": "Base options for document layout analysis models.\n\nLayout analysis detects the structural regions of a document page\n(text blocks, tables, figures, headers, etc.) and assigns content\ncells to those regions. This base class provides the shared controls\nfor empty-cluster retention and cell-assignment skipping.\n\nSee Also:\n    `LayoutOptions`: Default layout model configuration (Heron).\n    `LayoutObjectDetectionOptions`: Object-detection runtime layout\n        with preset support.",
  "properties": {
    "keep_empty_clusters": {
      "default": false,
      "description": "Retain empty clusters in layout analysis results. When False, clusters without content are removed. Enable for debugging or when empty regions are semantically important.",
      "title": "Keep Empty Clusters",
      "type": "boolean"
    },
    "skip_cell_assignment": {
      "default": false,
      "description": "Skip assignment of cells to table structures during layout analysis. When True, cells are detected but not associated with tables. Use for performance optimization when table structure is not needed.",
      "title": "Skip Cell Assignment",
      "type": "boolean"
    }
  },
  "title": "BaseLayoutOptions",
  "type": "object"
}
```

<a id="model-doclingbasetablestructureoptions"></a>

### DoclingBaseTableStructureOptions

Base options for table structure extraction models.

Serves as the abstract base for all table structure backends. Concrete
implementations (e.g., `TableStructureOptions` for TableFormer) inherit
from this class and register their own `kind` discriminator.

See Also:
    `TableStructureOptions`: Default TableFormer-based implementation.

Esquema JSON completo:

```json
{
  "description": "Base options for table structure extraction models.\n\nServes as the abstract base for all table structure backends. Concrete\nimplementations (e.g., `TableStructureOptions` for TableFormer) inherit\nfrom this class and register their own `kind` discriminator.\n\nSee Also:\n    `TableStructureOptions`: Default TableFormer-based implementation.",
  "properties": {},
  "title": "BaseTableStructureOptions",
  "type": "object"
}
```

<a id="model-doclingbasevlmengineoptions"></a>

### DoclingBaseVlmEngineOptions

Base configuration for VLM inference engines.

Engine options are independent of model specifications and prompts.
They only control how the inference is executed.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_type` | sim | [DoclingVlmEngineType](#model-doclingvlmenginetype) |  | Type of inference engine to use |

Esquema JSON completo:

```json
{
  "description": "Base configuration for VLM inference engines.\n\nEngine options are independent of model specifications and prompts.\nThey only control how the inference is executed.",
  "properties": {
    "engine_type": {
      "$ref": "#/components/schemas/DoclingVlmEngineType",
      "description": "Type of inference engine to use"
    }
  },
  "required": [
    "engine_type"
  ],
  "title": "BaseVlmEngineOptions",
  "type": "object"
}
```

<a id="model-doclingcaptionplacement"></a>

### DoclingCaptionPlacement

Placement of captions relative to the item they caption.

Esquema JSON completo:

```json
{
  "description": "Placement of captions relative to the item they caption.",
  "enum": [
    "standard",
    "layout"
  ],
  "title": "CaptionPlacement",
  "type": "string"
}
```

<a id="model-doclingchartextractionmodelkind"></a>

### DoclingChartExtractionModelKind

Esquema JSON completo:

```json
{
  "enum": [
    "granite-vision",
    "granite-vision-v4"
  ],
  "title": "ChartExtractionModelKind",
  "type": "string"
}
```

<a id="model-doclingchartextractionmodeloptions"></a>

### DoclingChartExtractionModelOptions

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `chart2code` | não | boolean | default=false |  |
| `chart2csv` | não | boolean | default=true |  |
| `chart2summary` | não | boolean | default=false |  |
| `kind` | não | string | default="chart_extraction"; const="chart_extraction" |  |
| `model` | não | [DoclingChartExtractionModelKind](#model-doclingchartextractionmodelkind) | default="granite-vision-v4" |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "chart2code": {
      "default": false,
      "title": "Chart2Code",
      "type": "boolean"
    },
    "chart2csv": {
      "default": true,
      "title": "Chart2Csv",
      "type": "boolean"
    },
    "chart2summary": {
      "default": false,
      "title": "Chart2Summary",
      "type": "boolean"
    },
    "kind": {
      "const": "chart_extraction",
      "default": "chart_extraction",
      "title": "Kind",
      "type": "string"
    },
    "model": {
      "$ref": "#/components/schemas/DoclingChartExtractionModelKind",
      "default": "granite-vision-v4"
    }
  },
  "title": "ChartExtractionModelOptions",
  "type": "object"
}
```

<a id="model-doclingcodeformulavlmoptions"></a>

### DoclingCodeFormulaVlmOptions

Configuration for VLM-based code and formula extraction.

This stage uses vision-language models to extract code blocks and
mathematical formulas from document images. Supports preset-based
configuration via StagePresetMixin.

Examples:
    # Use CodeFormulaV2 preset
    options = CodeFormulaVlmOptions.from_preset("codeformulav2")

    # Use Granite Docling preset
    options = CodeFormulaVlmOptions.from_preset("granite_docling")

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_options` | sim | [DoclingApiVlmEngineOptions](#model-doclingapivlmengineoptions) / [DoclingAutoInlineVlmEngineOptions](#model-doclingautoinlinevlmengineoptions) / [DoclingMlxVlmEngineOptions](#model-doclingmlxvlmengineoptions) / [DoclingTransformersVlmEngineOptions](#model-doclingtransformersvlmengineoptions) / [DoclingVllmVlmEngineOptions](#model-doclingvllmvlmengineoptions) |  | Runtime configuration (transformers, mlx, api, etc.) |
| `extract_code` | não | boolean | default=true | Extract code blocks |
| `extract_formulas` | não | boolean | default=true | Extract mathematical formulas |
| `max_size` | não | integer / null | default=null | Maximum image dimension (width or height) |
| `model_spec` | sim | [DoclingVlmModelSpec](#model-doclingvlmmodelspec) |  | Model specification with runtime-specific overrides |
| `scale` | não | number | default=2.0 | Image scaling factor for preprocessing |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration for VLM-based code and formula extraction.\n\nThis stage uses vision-language models to extract code blocks and\nmathematical formulas from document images. Supports preset-based\nconfiguration via StagePresetMixin.\n\nExamples:\n    # Use CodeFormulaV2 preset\n    options = CodeFormulaVlmOptions.from_preset(\"codeformulav2\")\n\n    # Use Granite Docling preset\n    options = CodeFormulaVlmOptions.from_preset(\"granite_docling\")",
  "properties": {
    "engine_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingApiVlmEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingAutoInlineVlmEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingMlxVlmEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingTransformersVlmEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingVllmVlmEngineOptions"
        }
      ],
      "description": "Runtime configuration (transformers, mlx, api, etc.)"
    },
    "extract_code": {
      "default": true,
      "description": "Extract code blocks",
      "title": "Extract Code",
      "type": "boolean"
    },
    "extract_formulas": {
      "default": true,
      "description": "Extract mathematical formulas",
      "title": "Extract Formulas",
      "type": "boolean"
    },
    "max_size": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Maximum image dimension (width or height)",
      "title": "Max Size"
    },
    "model_spec": {
      "$ref": "#/components/schemas/DoclingVlmModelSpec",
      "description": "Model specification with runtime-specific overrides"
    },
    "scale": {
      "default": 2.0,
      "description": "Image scaling factor for preprocessing",
      "title": "Scale",
      "type": "number"
    }
  },
  "required": [
    "engine_options",
    "model_spec"
  ],
  "title": "CodeFormulaVlmOptions",
  "type": "object"
}
```

<a id="model-doclingcontentlayer"></a>

### DoclingContentLayer

ContentLayer.

Esquema JSON completo:

```json
{
  "description": "ContentLayer.",
  "enum": [
    "body",
    "furniture",
    "background",
    "invisible",
    "notes"
  ],
  "title": "ContentLayer",
  "type": "string"
}
```

<a id="model-doclingdocitemlabel"></a>

### DoclingDocItemLabel

DocItemLabel.

Esquema JSON completo:

```json
{
  "description": "DocItemLabel.",
  "enum": [
    "caption",
    "chart",
    "footnote",
    "formula",
    "list_item",
    "page_footer",
    "page_header",
    "picture",
    "section_header",
    "table",
    "text",
    "title",
    "document_index",
    "code",
    "checkbox_selected",
    "checkbox_unselected",
    "form",
    "key_value_region",
    "grading_scale",
    "handwritten_text",
    "empty_value",
    "paragraph",
    "reference",
    "field_region",
    "field_heading",
    "field_item",
    "field_key",
    "field_value",
    "field_hint",
    "marker"
  ],
  "title": "DocItemLabel",
  "type": "string"
}
```

<a id="model-doclingdocumentpictureclassifieroptions"></a>

### DoclingDocumentPictureClassifierOptions

Options for configuring the DocumentPictureClassifier stage.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_options` | sim | [DoclingApiKserveV2ImageClassificationEngineOptions](#model-doclingapikservev2imageclassificationengineoptions) / [DoclingOnnxRuntimeImageClassificationEngineOptions](#model-doclingonnxruntimeimageclassificationengineoptions) / [DoclingTransformersImageClassificationEngineOptions](#model-doclingtransformersimageclassificationengineoptions) |  | Runtime configuration for the image-classification engine. |
| `kind` | não | string | default="document_picture_classifier"; const="document_picture_classifier" |  |
| `model_spec` | não | [DoclingImageClassificationModelSpec](#model-doclingimageclassificationmodelspec) |  | Image-classification model specification for picture classification. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Options for configuring the DocumentPictureClassifier stage.",
  "properties": {
    "engine_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingApiKserveV2ImageClassificationEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingOnnxRuntimeImageClassificationEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingTransformersImageClassificationEngineOptions"
        }
      ],
      "description": "Runtime configuration for the image-classification engine."
    },
    "kind": {
      "const": "document_picture_classifier",
      "default": "document_picture_classifier",
      "title": "Engine",
      "type": "string"
    },
    "model_spec": {
      "$ref": "#/components/schemas/DoclingImageClassificationModelSpec",
      "description": "Image-classification model specification for picture classification."
    }
  },
  "required": [
    "engine_options"
  ],
  "title": "DocumentPictureClassifierOptions",
  "type": "object"
}
```

<a id="model-doclingeasyocroptions"></a>

### DoclingEasyOcrOptions

Configuration for EasyOCR engine.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `bitmap_area_threshold` | não | number | default=0.05 | Percentage of the page area for a bitmap to be processed with OCR. |
| `confidence_threshold` | não | number | default=0.5 | Minimum confidence score for text recognition. Text with confidence below this threshold is filtered out. Range: 0.0-1.0. Lower values include more text but may reduce accuracy. |
| `download_enabled` | não | boolean | default=true | Allow automatic download of EasyOCR models on first use. Disable for offline environments where models must be pre-installed. |
| `force_full_page_ocr` | não | boolean | default=false | If enabled, a full-page OCR is always applied. |
| `kind` | não | string | default="easyocr"; const="easyocr" |  |
| `lang` | não | array de string | default=["fr", "de", "es", "en"] | List of language codes for OCR. EasyOCR supports 80+ languages. Use ISO 639-1 codes (e.g., `en`, `fr`, `de`). Multiple languages can be specified for multilingual documents. |
| `model_storage_directory` | não | string / null | default=null | Directory path for storing downloaded EasyOCR models. If None, uses default EasyOCR cache location. Useful for offline environments or custom model management. |
| `recog_network` | não | string / null | default="standard" | Recognition network architecture to use. Options: `standard` (default, balanced), `craft` (higher accuracy). Different networks may perform better on specific document types. |
| `suppress_mps_warnings` | não | boolean | default=true | Suppress Metal Performance Shaders (MPS) warnings on macOS. Reduces console noise when using Apple Silicon GPUs with EasyOCR. |
| `use_gpu` | não | boolean / null | default=null | Enable GPU acceleration for EasyOCR. If None, automatically detects and uses GPU if available. Set to False to force CPU-only processing. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration for EasyOCR engine.",
  "properties": {
    "bitmap_area_threshold": {
      "default": 0.05,
      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
      "examples": [
        0.05,
        0.1
      ],
      "title": "Bitmap Area Threshold",
      "type": "number"
    },
    "confidence_threshold": {
      "default": 0.5,
      "description": "Minimum confidence score for text recognition. Text with confidence below this threshold is filtered out. Range: 0.0-1.0. Lower values include more text but may reduce accuracy.",
      "title": "Confidence Threshold",
      "type": "number"
    },
    "download_enabled": {
      "default": true,
      "description": "Allow automatic download of EasyOCR models on first use. Disable for offline environments where models must be pre-installed.",
      "title": "Download Enabled",
      "type": "boolean"
    },
    "force_full_page_ocr": {
      "default": false,
      "description": "If enabled, a full-page OCR is always applied.",
      "examples": [
        false
      ],
      "title": "Force Full Page Ocr",
      "type": "boolean"
    },
    "kind": {
      "const": "easyocr",
      "default": "easyocr",
      "title": "Engine",
      "type": "string"
    },
    "lang": {
      "default": [
        "fr",
        "de",
        "es",
        "en"
      ],
      "description": "List of language codes for OCR. EasyOCR supports 80+ languages. Use ISO 639-1 codes (e.g., `en`, `fr`, `de`). Multiple languages can be specified for multilingual documents.",
      "items": {
        "type": "string"
      },
      "title": "Lang",
      "type": "array"
    },
    "model_storage_directory": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Directory path for storing downloaded EasyOCR models. If None, uses default EasyOCR cache location. Useful for offline environments or custom model management.",
      "title": "Model Storage Directory",
      "readOnly": true
    },
    "recog_network": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": "standard",
      "description": "Recognition network architecture to use. Options: `standard` (default, balanced), `craft` (higher accuracy). Different networks may perform better on specific document types.",
      "title": "Recog Network"
    },
    "suppress_mps_warnings": {
      "default": true,
      "description": "Suppress Metal Performance Shaders (MPS) warnings on macOS. Reduces console noise when using Apple Silicon GPUs with EasyOCR.",
      "title": "Suppress Mps Warnings",
      "type": "boolean"
    },
    "use_gpu": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Enable GPU acceleration for EasyOCR. If None, automatically detects and uses GPU if available. Set to False to force CPU-only processing.",
      "title": "Use Gpu"
    }
  },
  "title": "EasyOcrOptions",
  "type": "object"
}
```

<a id="model-doclingenginemodelconfig"></a>

### DoclingEngineModelConfig

Engine-specific model configuration.

Allows overriding model settings for specific engines.
For example, MLX might use a different repo_id than Transformers.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `extra_config` | não | object | additionalProperties=true | Additional engine-specific configuration |
| `repo_id` | não | string / null | default=null | Override model repository ID for this engine |
| `revision` | não | string / null | default=null | Override model revision for this engine |
| `torch_dtype` | não | string / null | default=null | Override torch dtype for this engine (e.g., 'bfloat16') |

Esquema JSON completo:

```json
{
  "description": "Engine-specific model configuration.\n\nAllows overriding model settings for specific engines.\nFor example, MLX might use a different repo_id than Transformers.",
  "properties": {
    "extra_config": {
      "additionalProperties": true,
      "description": "Additional engine-specific configuration",
      "title": "Extra Config",
      "type": "object"
    },
    "repo_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Override model repository ID for this engine",
      "title": "Repo Id"
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
      "default": null,
      "description": "Override model revision for this engine",
      "title": "Revision"
    },
    "torch_dtype": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Override torch dtype for this engine (e.g., 'bfloat16')",
      "title": "Torch Dtype"
    }
  },
  "title": "EngineModelConfig",
  "type": "object"
}
```

<a id="model-doclingexportdoclang"></a>

### DoclingExportDoclang

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `add_named_groups` | não | boolean | default=false |  |
| `image_mode` | não | [DoclingImageRefMode](#model-doclingimagerefmode) | default="placeholder" |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "add_named_groups": {
      "default": false,
      "title": "Add Named Groups",
      "type": "boolean"
    },
    "image_mode": {
      "$ref": "#/components/schemas/DoclingImageRefMode",
      "default": "placeholder"
    }
  },
  "title": "ExportDoclang",
  "type": "object"
}
```

<a id="model-doclingexportdoctags"></a>

### DoclingExportDoctags

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `add_content` | não | boolean | default=true |  |
| `add_location` | não | boolean | default=true |  |
| `add_page_index` | não | boolean | default=true |  |
| `add_table_cell_location` | não | boolean | default=false |  |
| `add_table_cell_text` | não | boolean | default=true |  |
| `delim` | não | string | default="" |  |
| `from_element` | não | integer | default=0 |  |
| `labels` | não | array de [DoclingDocItemLabel](#model-doclingdocitemlabel) / null | default=null |  |
| `minified` | não | boolean | default=false |  |
| `pages` | não | array de integer / null | default=null |  |
| `to_element` | não | integer | default=9223372036854775807 |  |
| `xsize` | não | integer | default=500 |  |
| `ysize` | não | integer | default=500 |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "add_content": {
      "default": true,
      "title": "Add Content",
      "type": "boolean"
    },
    "add_location": {
      "default": true,
      "title": "Add Location",
      "type": "boolean"
    },
    "add_page_index": {
      "default": true,
      "title": "Add Page Index",
      "type": "boolean"
    },
    "add_table_cell_location": {
      "default": false,
      "title": "Add Table Cell Location",
      "type": "boolean"
    },
    "add_table_cell_text": {
      "default": true,
      "title": "Add Table Cell Text",
      "type": "boolean"
    },
    "delim": {
      "default": "",
      "title": "Delim",
      "type": "string"
    },
    "from_element": {
      "default": 0,
      "title": "From Element",
      "type": "integer"
    },
    "labels": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingDocItemLabel"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Labels"
    },
    "minified": {
      "default": false,
      "title": "Minified",
      "type": "boolean"
    },
    "pages": {
      "anyOf": [
        {
          "items": {
            "type": "integer"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Pages"
    },
    "to_element": {
      "default": 9223372036854775807,
      "title": "To Element",
      "type": "integer"
    },
    "xsize": {
      "default": 500,
      "title": "Xsize",
      "type": "integer"
    },
    "ysize": {
      "default": 500,
      "title": "Ysize",
      "type": "integer"
    }
  },
  "title": "ExportDoctags",
  "type": "object"
}
```

<a id="model-doclingexportdocumenttokens"></a>

### DoclingExportDocumentTokens

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `add_content` | não | boolean | default=true |  |
| `add_location` | não | boolean | default=true |  |
| `add_page_index` | não | boolean | default=true |  |
| `add_table_cell_location` | não | boolean | default=false |  |
| `add_table_cell_text` | não | boolean | default=true |  |
| `delim` | não | string | default="" |  |
| `from_element` | não | integer | default=0 |  |
| `labels` | não | array de [DoclingDocItemLabel](#model-doclingdocitemlabel) / null | default=null |  |
| `minified` | não | boolean | default=false |  |
| `pages` | não | array de integer / null | default=null |  |
| `to_element` | não | integer | default=9223372036854775807 |  |
| `xsize` | não | integer | default=500 |  |
| `ysize` | não | integer | default=500 |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "add_content": {
      "default": true,
      "title": "Add Content",
      "type": "boolean"
    },
    "add_location": {
      "default": true,
      "title": "Add Location",
      "type": "boolean"
    },
    "add_page_index": {
      "default": true,
      "title": "Add Page Index",
      "type": "boolean"
    },
    "add_table_cell_location": {
      "default": false,
      "title": "Add Table Cell Location",
      "type": "boolean"
    },
    "add_table_cell_text": {
      "default": true,
      "title": "Add Table Cell Text",
      "type": "boolean"
    },
    "delim": {
      "default": "",
      "title": "Delim",
      "type": "string"
    },
    "from_element": {
      "default": 0,
      "title": "From Element",
      "type": "integer"
    },
    "labels": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingDocItemLabel"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Labels"
    },
    "minified": {
      "default": false,
      "title": "Minified",
      "type": "boolean"
    },
    "pages": {
      "anyOf": [
        {
          "items": {
            "type": "integer"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Pages"
    },
    "to_element": {
      "default": 9223372036854775807,
      "title": "To Element",
      "type": "integer"
    },
    "xsize": {
      "default": 500,
      "title": "Xsize",
      "type": "integer"
    },
    "ysize": {
      "default": 500,
      "title": "Ysize",
      "type": "integer"
    }
  },
  "title": "ExportDoctags",
  "type": "object"
}
```

<a id="model-doclingexportelementtree"></a>

### DoclingExportElementTree

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {},
  "title": "ExportElementTree",
  "type": "object"
}
```

<a id="model-doclingexporthtml"></a>

### DoclingExportHtml

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `enable_chart_tables` | não | boolean | default=true |  |
| `formula_to_mathml` | não | boolean | default=true |  |
| `from_element` | não | integer | default=0 |  |
| `html_head` | não | string | default="null" |  |
| `html_lang` | não | string | default="en" |  |
| `image_mode` | não | [DoclingImageRefMode](#model-doclingimagerefmode) | default="placeholder" |  |
| `include_annotations` | não | boolean | default=true |  |
| `included_content_layers` | não | array de [DoclingContentLayer](#model-doclingcontentlayer) / null | default=null |  |
| `labels` | não | array de [DoclingDocItemLabel](#model-doclingdocitemlabel) / null | default=null |  |
| `page_no` | não | integer / null | default=null |  |
| `split_page_view` | não | boolean | default=false |  |
| `to_element` | não | integer | default=9223372036854775807 |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "enable_chart_tables": {
      "default": true,
      "title": "Enable Chart Tables",
      "type": "boolean"
    },
    "formula_to_mathml": {
      "default": true,
      "title": "Formula To Mathml",
      "type": "boolean"
    },
    "from_element": {
      "default": 0,
      "title": "From Element",
      "type": "integer"
    },
    "html_head": {
      "default": "null",
      "title": "Html Head",
      "type": "string"
    },
    "html_lang": {
      "default": "en",
      "title": "Html Lang",
      "type": "string"
    },
    "image_mode": {
      "$ref": "#/components/schemas/DoclingImageRefMode",
      "default": "placeholder"
    },
    "include_annotations": {
      "default": true,
      "title": "Include Annotations",
      "type": "boolean"
    },
    "included_content_layers": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingContentLayer"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Included Content Layers"
    },
    "labels": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingDocItemLabel"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Labels"
    },
    "page_no": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Page No"
    },
    "split_page_view": {
      "default": false,
      "title": "Split Page View",
      "type": "boolean"
    },
    "to_element": {
      "default": 9223372036854775807,
      "title": "To Element",
      "type": "integer"
    }
  },
  "title": "ExportHtml",
  "type": "object"
}
```

<a id="model-doclingexportjson"></a>

### DoclingExportJson

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `by_alias` | não | boolean | default=true |  |
| `confid_precision` | não | integer / null | default=null |  |
| `coord_precision` | não | integer / null | default=null |  |
| `exclude_none` | não | boolean | default=true |  |
| `mode` | não | string | default="json" |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "by_alias": {
      "default": true,
      "title": "By Alias",
      "type": "boolean"
    },
    "confid_precision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Confid Precision"
    },
    "coord_precision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Coord Precision"
    },
    "exclude_none": {
      "default": true,
      "title": "Exclude None",
      "type": "boolean"
    },
    "mode": {
      "default": "json",
      "title": "Mode",
      "type": "string"
    }
  },
  "title": "ExportDict",
  "type": "object"
}
```

<a id="model-doclingexportmarkdown"></a>

### DoclingExportMarkdown

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `allowed_meta_names` | não | array de string / null | default=null |  |
| `blocked_meta_names` | não | array de string / null | default=null |  |
| `caption_placement` | não | [DoclingCaptionPlacement](#model-doclingcaptionplacement) | default="standard" |  |
| `compact_tables` | não | boolean | default=false |  |
| `delim` | não | string | default="\n\n" |  |
| `enable_chart_tables` | não | boolean | default=true |  |
| `escape_html` | não | boolean | default=true |  |
| `escape_underscores` | não | boolean | default=true |  |
| `from_element` | não | integer | default=0 |  |
| `image_mode` | não | [DoclingImageRefMode](#model-doclingimagerefmode) | default="placeholder" |  |
| `image_placeholder` | não | string | default="<!-- image -->" |  |
| `include_annotations` | não | boolean | default=true |  |
| `include_picture_classification` | não | boolean | default=true |  |
| `included_content_layers` | não | array de [DoclingContentLayer](#model-doclingcontentlayer) / null | default=null |  |
| `indent` | não | integer | default=4 |  |
| `labels` | não | array de [DoclingDocItemLabel](#model-doclingdocitemlabel) / null | default=null |  |
| `mark_annotations` | não | boolean | default=false |  |
| `mark_meta` | não | boolean | default=false |  |
| `page_break_placeholder` | não | string / null | default=null |  |
| `page_no` | não | integer / null | default=null |  |
| `strict_text` | não | boolean | default=false |  |
| `text_width` | não | integer | default=-1 |  |
| `to_element` | não | integer | default=9223372036854775807 |  |
| `traverse_pictures` | não | boolean | default=false |  |
| `use_legacy_annotations` | não | boolean / null | default=null |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "allowed_meta_names": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Allowed Meta Names"
    },
    "blocked_meta_names": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Blocked Meta Names"
    },
    "caption_placement": {
      "$ref": "#/components/schemas/DoclingCaptionPlacement",
      "default": "standard"
    },
    "compact_tables": {
      "default": false,
      "title": "Compact Tables",
      "type": "boolean"
    },
    "delim": {
      "default": "\n\n",
      "title": "Delim",
      "type": "string"
    },
    "enable_chart_tables": {
      "default": true,
      "title": "Enable Chart Tables",
      "type": "boolean"
    },
    "escape_html": {
      "default": true,
      "title": "Escape Html",
      "type": "boolean"
    },
    "escape_underscores": {
      "default": true,
      "title": "Escape Underscores",
      "type": "boolean"
    },
    "from_element": {
      "default": 0,
      "title": "From Element",
      "type": "integer"
    },
    "image_mode": {
      "$ref": "#/components/schemas/DoclingImageRefMode",
      "default": "placeholder"
    },
    "image_placeholder": {
      "default": "<!-- image -->",
      "title": "Image Placeholder",
      "type": "string"
    },
    "include_annotations": {
      "default": true,
      "title": "Include Annotations",
      "type": "boolean"
    },
    "include_picture_classification": {
      "default": true,
      "title": "Include Picture Classification",
      "type": "boolean"
    },
    "included_content_layers": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingContentLayer"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Included Content Layers"
    },
    "indent": {
      "default": 4,
      "title": "Indent",
      "type": "integer"
    },
    "labels": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingDocItemLabel"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Labels"
    },
    "mark_annotations": {
      "default": false,
      "title": "Mark Annotations",
      "type": "boolean"
    },
    "mark_meta": {
      "default": false,
      "title": "Mark Meta",
      "type": "boolean"
    },
    "page_break_placeholder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Page Break Placeholder"
    },
    "page_no": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Page No"
    },
    "strict_text": {
      "default": false,
      "title": "Strict Text",
      "type": "boolean"
    },
    "text_width": {
      "default": -1,
      "title": "Text Width",
      "type": "integer"
    },
    "to_element": {
      "default": 9223372036854775807,
      "title": "To Element",
      "type": "integer"
    },
    "traverse_pictures": {
      "default": false,
      "title": "Traverse Pictures",
      "type": "boolean"
    },
    "use_legacy_annotations": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Use Legacy Annotations"
    }
  },
  "title": "ExportMarkdown",
  "type": "object"
}
```

<a id="model-doclingexporttxt"></a>

### DoclingExportTxt

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `delim` | não | string | default="\n\n" |  |
| `from_element` | não | integer | default=0 |  |
| `included_content_layers` | não | array de [DoclingContentLayer](#model-doclingcontentlayer) / null | default=null |  |
| `labels` | não | array de [DoclingDocItemLabel](#model-doclingdocitemlabel) / null | default=null |  |
| `page_break_placeholder` | não | string / null | default=null |  |
| `page_no` | não | integer / null | default=null |  |
| `to_element` | não | integer | default=9223372036854775807 |  |
| `traverse_pictures` | não | boolean | default=false |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "delim": {
      "default": "\n\n",
      "title": "Delim",
      "type": "string"
    },
    "from_element": {
      "default": 0,
      "title": "From Element",
      "type": "integer"
    },
    "included_content_layers": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingContentLayer"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Included Content Layers"
    },
    "labels": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingDocItemLabel"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Labels"
    },
    "page_break_placeholder": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Page Break Placeholder"
    },
    "page_no": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Page No"
    },
    "to_element": {
      "default": 9223372036854775807,
      "title": "To Element",
      "type": "integer"
    },
    "traverse_pictures": {
      "default": false,
      "title": "Traverse Pictures",
      "type": "boolean"
    }
  },
  "title": "ExportText",
  "type": "object"
}
```

<a id="model-doclingexportvtt"></a>

### DoclingExportVtt

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `included_content_layers` | não | array de [DoclingContentLayer](#model-doclingcontentlayer) / null | default=null |  |
| `omit_hours_if_zero` | não | boolean | default=false |  |
| `omit_voice_end` | não | boolean | default=false |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "included_content_layers": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingContentLayer"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Included Content Layers"
    },
    "omit_hours_if_zero": {
      "default": false,
      "title": "Omit Hours If Zero",
      "type": "boolean"
    },
    "omit_voice_end": {
      "default": false,
      "title": "Omit Voice End",
      "type": "boolean"
    }
  },
  "title": "ExportVtt",
  "type": "object"
}
```

<a id="model-doclingimageclassificationenginetype"></a>

### DoclingImageClassificationEngineType

Supported inference engine types for image-classification models.

Esquema JSON completo:

```json
{
  "description": "Supported inference engine types for image-classification models.",
  "enum": [
    "onnxruntime",
    "transformers",
    "api_kserve_v2"
  ],
  "title": "ImageClassificationEngineType",
  "type": "string"
}
```

<a id="model-doclingimageclassificationmodelspec"></a>

### DoclingImageClassificationModelSpec

Specification for an image-classification model.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_overrides` | não | object | additionalProperties={"$ref": "#/components/schemas/DoclingEngineModelConfig"} | Engine-specific configuration overrides |
| `name` | sim | string |  | Human-readable model name |
| `repo_id` | sim | string |  | Default HuggingFace repository ID |
| `revision` | não | string | default="main" | Default model revision |

Esquema JSON completo:

```json
{
  "description": "Specification for an image-classification model.",
  "properties": {
    "engine_overrides": {
      "additionalProperties": {
        "$ref": "#/components/schemas/DoclingEngineModelConfig"
      },
      "description": "Engine-specific configuration overrides",
      "propertyNames": {
        "$ref": "#/components/schemas/DoclingImageClassificationEngineType"
      },
      "title": "Engine Overrides",
      "type": "object"
    },
    "name": {
      "description": "Human-readable model name",
      "title": "Name",
      "type": "string"
    },
    "repo_id": {
      "description": "Default HuggingFace repository ID",
      "title": "Repo Id",
      "type": "string"
    },
    "revision": {
      "default": "main",
      "description": "Default model revision",
      "title": "Revision",
      "type": "string"
    }
  },
  "required": [
    "name",
    "repo_id"
  ],
  "title": "ImageClassificationModelSpec",
  "type": "object"
}
```

<a id="model-doclingimagerefmode"></a>

### DoclingImageRefMode

ImageRefMode.

Esquema JSON completo:

```json
{
  "description": "ImageRefMode.",
  "enum": [
    "placeholder",
    "embedded",
    "referenced"
  ],
  "title": "ImageRefMode",
  "type": "string"
}
```

<a id="model-doclingkservev2ocroptions"></a>

### DoclingKserveV2OcrOptions

Configuration for KServe v2-based OCR (e.g., Triton Inference Server).

This OCR engine connects to a remote KServe v2-compatible inference server
(such as Triton) to perform OCR via gRPC or HTTP. It combines standard OCR
options with KServe v2 connection settings inherited from KserveV2OptionsMixin.

The engine handles custom preprocessing (RGB conversion, transpose, batching)
to match the expected input format of typical OCR models deployed on KServe v2
endpoints.

See Also:
    `KserveV2OptionsMixin`: Provides all KServe v2 connection configuration.
    `RapidOcrOptions`: Local OCR engine for comparison.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `bitmap_area_threshold` | não | number | default=0.05 | Percentage of the page area for a bitmap to be processed with OCR. |
| `force_full_page_ocr` | não | boolean | default=false | If enabled, a full-page OCR is always applied. |
| `grpc_max_message_bytes` | não | integer | default=67108864; minimum=1 | Max send/receive gRPC message size in bytes. |
| `grpc_metadata` | não | object | additionalProperties={"type": "string"} | Optional gRPC metadata for authentication/routing when transport='grpc'. No HTTP headers are reused in gRPC mode. |
| `grpc_use_binary_data` | não | boolean | default=true | Whether to request/expect binary tensor payloads on gRPC output tensors. Set to False for servers that do not support binary_data output parameters. |
| `grpc_use_tls` | não | boolean | default=false | Whether to use TLS for the gRPC channel. When omitted, plain-text h2c is used. |
| `headers` | não | object | additionalProperties={"type": "string"} | Optional HTTP headers for authentication/routing when transport='http'. |
| `kind` | não | string | default="kserve_v2_ocr"; const="kserve_v2_ocr" |  |
| `lang` | não | array de string | default=["english", "chinese"] | List of OCR languages. Note: Language selection depends on the deployed model. This parameter is passed to the server but may not be used by all models. |
| `model_name` | não | string | default="ocr" | Remote model name registered in the KServe v2 endpoint. |
| `model_version` | não | string / null | default=null | Optional model version. If omitted, the server default is used. |
| `request_parameters` | não | object | additionalProperties=true | Optional top-level KServe v2 infer request parameters. |
| `scale` | não | number | default=2.0; exclusiveMinimum=0.0 | Image scale multiplier for OCR processing. Higher values increase resolution for better text recognition. Default 2.0 converts 72 DPI to 144 DPI. |
| `timeout` | não | number | default=60.0 | Per-request timeout in seconds for both HTTP and gRPC calls. |
| `transport` | não | string | default="grpc"; enum=["grpc", "http"] | Transport protocol for KServe v2 calls. Use 'grpc' for binary tensor payloads (default), or 'http' for JSON REST. |
| `url` | sim | string |  | Endpoint URL for KServe v2 transport. For transport='http', use http(s)://host[:port] or plain host:port. For transport='grpc', use plain host:port. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration for KServe v2-based OCR (e.g., Triton Inference Server).\n\nThis OCR engine connects to a remote KServe v2-compatible inference server\n(such as Triton) to perform OCR via gRPC or HTTP. It combines standard OCR\noptions with KServe v2 connection settings inherited from KserveV2OptionsMixin.\n\nThe engine handles custom preprocessing (RGB conversion, transpose, batching)\nto match the expected input format of typical OCR models deployed on KServe v2\nendpoints.\n\nSee Also:\n    `KserveV2OptionsMixin`: Provides all KServe v2 connection configuration.\n    `RapidOcrOptions`: Local OCR engine for comparison.",
  "properties": {
    "bitmap_area_threshold": {
      "default": 0.05,
      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
      "examples": [
        0.05,
        0.1
      ],
      "title": "Bitmap Area Threshold",
      "type": "number"
    },
    "force_full_page_ocr": {
      "default": false,
      "description": "If enabled, a full-page OCR is always applied.",
      "examples": [
        false
      ],
      "title": "Force Full Page Ocr",
      "type": "boolean"
    },
    "grpc_max_message_bytes": {
      "default": 67108864,
      "description": "Max send/receive gRPC message size in bytes.",
      "minimum": 1,
      "title": "Grpc Max Message Bytes",
      "type": "integer"
    },
    "grpc_metadata": {
      "additionalProperties": {
        "type": "string"
      },
      "description": "Optional gRPC metadata for authentication/routing when transport='grpc'. No HTTP headers are reused in gRPC mode.",
      "title": "Grpc Metadata",
      "type": "object"
    },
    "grpc_use_binary_data": {
      "default": true,
      "description": "Whether to request/expect binary tensor payloads on gRPC output tensors. Set to False for servers that do not support binary_data output parameters.",
      "title": "Grpc Use Binary Data",
      "type": "boolean"
    },
    "grpc_use_tls": {
      "default": false,
      "description": "Whether to use TLS for the gRPC channel. When omitted, plain-text h2c is used.",
      "title": "Grpc Use Tls",
      "type": "boolean"
    },
    "headers": {
      "additionalProperties": {
        "type": "string"
      },
      "description": "Optional HTTP headers for authentication/routing when transport='http'.",
      "title": "Headers",
      "type": "object"
    },
    "kind": {
      "const": "kserve_v2_ocr",
      "default": "kserve_v2_ocr",
      "title": "Engine",
      "type": "string"
    },
    "lang": {
      "default": [
        "english",
        "chinese"
      ],
      "description": "List of OCR languages. Note: Language selection depends on the deployed model. This parameter is passed to the server but may not be used by all models.",
      "items": {
        "type": "string"
      },
      "title": "Lang",
      "type": "array"
    },
    "model_name": {
      "default": "ocr",
      "description": "Remote model name registered in the KServe v2 endpoint.",
      "title": "Model Name",
      "type": "string"
    },
    "model_version": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional model version. If omitted, the server default is used.",
      "title": "Model Version"
    },
    "request_parameters": {
      "additionalProperties": true,
      "description": "Optional top-level KServe v2 infer request parameters.",
      "title": "Request Parameters",
      "type": "object"
    },
    "scale": {
      "default": 2.0,
      "description": "Image scale multiplier for OCR processing. Higher values increase resolution for better text recognition. Default 2.0 converts 72 DPI to 144 DPI.",
      "exclusiveMinimum": 0.0,
      "title": "Scale",
      "type": "number"
    },
    "timeout": {
      "default": 60.0,
      "description": "Per-request timeout in seconds for both HTTP and gRPC calls.",
      "title": "Timeout",
      "type": "number"
    },
    "transport": {
      "default": "grpc",
      "description": "Transport protocol for KServe v2 calls. Use 'grpc' for binary tensor payloads (default), or 'http' for JSON REST.",
      "enum": [
        "grpc",
        "http"
      ],
      "title": "Transport",
      "type": "string"
    },
    "url": {
      "description": "Endpoint URL for KServe v2 transport. For transport='http', use http(s)://host[:port] or plain host:port. For transport='grpc', use plain host:port.",
      "title": "Url",
      "type": "string"
    }
  },
  "required": [
    "url"
  ],
  "title": "KserveV2OcrOptions",
  "type": "object",
  "x-unavailable-reason": "Serviços remotos desabilitados no servidor"
}
```

<a id="model-doclinglayoutmodelconfig"></a>

### DoclingLayoutModelConfig

Configuration for document layout analysis models from HuggingFace.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `model_path` | sim | string |  | Relative path within the repository to model artifacts. Empty string indicates artifacts are in the repository root. Used for repositories with multiple models or nested structures. |
| `name` | sim | string |  | Human-readable name identifier for the layout model. Used for logging, debugging, and model selection. |
| `repo_id` | sim | string |  | HuggingFace repository ID where the model is hosted. Used to download model weights and configuration files from HuggingFace Hub. |
| `revision` | sim | string |  | Git revision (branch, tag, or commit hash) of the model repository to use. Allows pinning to specific model versions for reproducibility. |
| `supported_devices` | não | array de [DoclingAcceleratorDevice](#model-doclingacceleratordevice) | default=["cpu", "cuda", "mps", "xpu"] | List of hardware accelerators supported by this model. The model can only run on devices in this list. |

Esquema JSON completo:

```json
{
  "description": "Configuration for document layout analysis models from HuggingFace.",
  "properties": {
    "model_path": {
      "description": "Relative path within the repository to model artifacts. Empty string indicates artifacts are in the repository root. Used for repositories with multiple models or nested structures.",
      "title": "Model Path",
      "type": "string",
      "readOnly": true
    },
    "name": {
      "description": "Human-readable name identifier for the layout model. Used for logging, debugging, and model selection.",
      "examples": [
        "docling_layout_heron",
        "docling_layout_egret_large"
      ],
      "title": "Name",
      "type": "string"
    },
    "repo_id": {
      "description": "HuggingFace repository ID where the model is hosted. Used to download model weights and configuration files from HuggingFace Hub.",
      "examples": [
        "docling-project/docling-layout-heron",
        "docling-project/docling-layout-egret-large"
      ],
      "title": "Repo Id",
      "type": "string"
    },
    "revision": {
      "description": "Git revision (branch, tag, or commit hash) of the model repository to use. Allows pinning to specific model versions for reproducibility.",
      "examples": [
        "main",
        "v1.0.0"
      ],
      "title": "Revision",
      "type": "string"
    },
    "supported_devices": {
      "default": [
        "cpu",
        "cuda",
        "mps",
        "xpu"
      ],
      "description": "List of hardware accelerators supported by this model. The model can only run on devices in this list.",
      "items": {
        "$ref": "#/components/schemas/DoclingAcceleratorDevice"
      },
      "title": "Supported Devices",
      "type": "array"
    }
  },
  "required": [
    "name",
    "repo_id",
    "revision",
    "model_path"
  ],
  "title": "LayoutModelConfig",
  "type": "object"
}
```

<a id="model-doclinglayoutoptions"></a>

### DoclingLayoutOptions

Options for layout processing using Docling's built-in layout model.

Provides configuration for the default layout analysis path, including
model selection (e.g., Heron, Egret variants) and orphan cluster
creation for elements not assigned to any detected structure.

Notes:
    The default model is ``DOCLING_LAYOUT_HERON``. For higher accuracy
    on complex documents, consider ``DOCLING_LAYOUT_EGRET_LARGE`` or
    ``DOCLING_LAYOUT_EGRET_XLARGE``.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `create_orphan_clusters` | não | boolean | default=true | Create clusters for orphaned elements not assigned to any structure. When True, isolated text or elements are grouped into their own clusters. Recommended for complete document coverage. |
| `keep_empty_clusters` | não | boolean | default=false | Retain empty clusters in layout analysis results. When False, clusters without content are removed. Enable for debugging or when empty regions are semantically important. |
| `kind` | não | string | default="docling_layout_default"; const="docling_layout_default" |  |
| `model_spec` | não | [DoclingLayoutModelConfig](#model-doclinglayoutmodelconfig) | default={"model_path": "", "name": "docling_layout_heron", "repo_id": "docling-project/docling-layout-heron", "revision": "main", "supported_devices": ["cpu", "cuda", "mps", "xpu"]} | Layout model configuration specifying which model to use for document layout analysis. Options include DOCLING_LAYOUT_HERON (default, balanced), DOCLING_LAYOUT_EGRET_* (higher accuracy), etc. |
| `skip_cell_assignment` | não | boolean | default=false | Skip assignment of cells to table structures during layout analysis. When True, cells are detected but not associated with tables. Use for performance optimization when table structure is not needed. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Options for layout processing using Docling's built-in layout model.\n\nProvides configuration for the default layout analysis path, including\nmodel selection (e.g., Heron, Egret variants) and orphan cluster\ncreation for elements not assigned to any detected structure.\n\nNotes:\n    The default model is ``DOCLING_LAYOUT_HERON``. For higher accuracy\n    on complex documents, consider ``DOCLING_LAYOUT_EGRET_LARGE`` or\n    ``DOCLING_LAYOUT_EGRET_XLARGE``.",
  "properties": {
    "create_orphan_clusters": {
      "default": true,
      "description": "Create clusters for orphaned elements not assigned to any structure. When True, isolated text or elements are grouped into their own clusters. Recommended for complete document coverage.",
      "title": "Create Orphan Clusters",
      "type": "boolean"
    },
    "keep_empty_clusters": {
      "default": false,
      "description": "Retain empty clusters in layout analysis results. When False, clusters without content are removed. Enable for debugging or when empty regions are semantically important.",
      "title": "Keep Empty Clusters",
      "type": "boolean"
    },
    "kind": {
      "const": "docling_layout_default",
      "default": "docling_layout_default",
      "title": "Engine",
      "type": "string"
    },
    "model_spec": {
      "$ref": "#/components/schemas/DoclingLayoutModelConfig",
      "default": {
        "model_path": "",
        "name": "docling_layout_heron",
        "repo_id": "docling-project/docling-layout-heron",
        "revision": "main",
        "supported_devices": [
          "cpu",
          "cuda",
          "mps",
          "xpu"
        ]
      },
      "description": "Layout model configuration specifying which model to use for document layout analysis. Options include DOCLING_LAYOUT_HERON (default, balanced), DOCLING_LAYOUT_EGRET_* (higher accuracy), etc."
    },
    "skip_cell_assignment": {
      "default": false,
      "description": "Skip assignment of cells to table structures during layout analysis. When True, cells are detected but not associated with tables. Use for performance optimization when table structure is not needed.",
      "title": "Skip Cell Assignment",
      "type": "boolean"
    }
  },
  "title": "LayoutOptions",
  "type": "object"
}
```

<a id="model-doclingmlxvlmengineoptions"></a>

### DoclingMlxVlmEngineOptions

Options for Apple MLX inference engine (Apple Silicon only).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_type` | não | string | default="mlx"; const="mlx" |  |
| `trust_remote_code` | não | boolean | default=false | Allow execution of custom code from model repo |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Options for Apple MLX inference engine (Apple Silicon only).",
  "properties": {
    "engine_type": {
      "const": "mlx",
      "default": "mlx",
      "title": "Engine Type",
      "type": "string"
    },
    "trust_remote_code": {
      "default": false,
      "description": "Allow execution of custom code from model repo",
      "title": "Trust Remote Code",
      "type": "boolean"
    }
  },
  "title": "MlxVlmEngineOptions",
  "type": "object"
}
```

<a id="model-doclingocrautooptions"></a>

### DoclingOcrAutoOptions

Automatic OCR engine selection based on system availability.

When this option is used, Docling probes the runtime environment at
pipeline initialization and selects the best available OCR engine
(e.g., EasyOCR if GPU is present, Tesseract otherwise). Language
settings are deferred to the chosen engine's defaults.

Notes:
    The `lang` field is intentionally defaulted to an empty list.
    To control language selection, specify an explicit OCR engine
    option class instead.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `bitmap_area_threshold` | não | number | default=0.05 | Percentage of the page area for a bitmap to be processed with OCR. |
| `force_full_page_ocr` | não | boolean | default=false | If enabled, a full-page OCR is always applied. |
| `kind` | não | string | default="auto"; const="auto" |  |
| `lang` | não | array de string | default=[] | The automatic OCR engine will use the default values of the engine. Please specify the engine explicitly to change the language selection. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Automatic OCR engine selection based on system availability.\n\nWhen this option is used, Docling probes the runtime environment at\npipeline initialization and selects the best available OCR engine\n(e.g., EasyOCR if GPU is present, Tesseract otherwise). Language\nsettings are deferred to the chosen engine's defaults.\n\nNotes:\n    The `lang` field is intentionally defaulted to an empty list.\n    To control language selection, specify an explicit OCR engine\n    option class instead.",
  "properties": {
    "bitmap_area_threshold": {
      "default": 0.05,
      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
      "examples": [
        0.05,
        0.1
      ],
      "title": "Bitmap Area Threshold",
      "type": "number"
    },
    "force_full_page_ocr": {
      "default": false,
      "description": "If enabled, a full-page OCR is always applied.",
      "examples": [
        false
      ],
      "title": "Force Full Page Ocr",
      "type": "boolean"
    },
    "kind": {
      "const": "auto",
      "default": "auto",
      "title": "Engine",
      "type": "string"
    },
    "lang": {
      "default": [],
      "description": "The automatic OCR engine will use the default values of the engine. Please specify the engine explicitly to change the language selection.",
      "items": {
        "type": "string"
      },
      "title": "Lang",
      "type": "array"
    }
  },
  "title": "OcrAutoOptions",
  "type": "object"
}
```

<a id="model-doclingocrmacoptions"></a>

### DoclingOcrMacOptions

Configuration for native macOS OCR using Vision framework.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `bitmap_area_threshold` | não | number | default=0.05 | Percentage of the page area for a bitmap to be processed with OCR. |
| `force_full_page_ocr` | não | boolean | default=false | If enabled, a full-page OCR is always applied. |
| `framework` | não | string | default="vision" | macOS framework to use for OCR. Currently supports `vision` (Apple Vision framework). Future versions may support additional frameworks. |
| `kind` | não | string | default="ocrmac"; const="ocrmac" |  |
| `lang` | não | array de string | default=["fr-FR", "de-DE", "es-ES", "en-US"] | List of language locale codes for macOS OCR. Use format `language-REGION` (e.g., `en-US`, `fr-FR`). Leverages native macOS Vision framework for OCR on Apple platforms. |
| `recognition` | não | string | default="accurate" | Recognition accuracy level. Options: `accurate` (higher quality, slower) or `fast` (lower quality, faster). Choose based on speed vs. accuracy requirements. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration for native macOS OCR using Vision framework.",
  "properties": {
    "bitmap_area_threshold": {
      "default": 0.05,
      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
      "examples": [
        0.05,
        0.1
      ],
      "title": "Bitmap Area Threshold",
      "type": "number"
    },
    "force_full_page_ocr": {
      "default": false,
      "description": "If enabled, a full-page OCR is always applied.",
      "examples": [
        false
      ],
      "title": "Force Full Page Ocr",
      "type": "boolean"
    },
    "framework": {
      "default": "vision",
      "description": "macOS framework to use for OCR. Currently supports `vision` (Apple Vision framework). Future versions may support additional frameworks.",
      "title": "Framework",
      "type": "string"
    },
    "kind": {
      "const": "ocrmac",
      "default": "ocrmac",
      "title": "Engine",
      "type": "string"
    },
    "lang": {
      "default": [
        "fr-FR",
        "de-DE",
        "es-ES",
        "en-US"
      ],
      "description": "List of language locale codes for macOS OCR. Use format `language-REGION` (e.g., `en-US`, `fr-FR`). Leverages native macOS Vision framework for OCR on Apple platforms.",
      "items": {
        "type": "string"
      },
      "title": "Lang",
      "type": "array"
    },
    "recognition": {
      "default": "accurate",
      "description": "Recognition accuracy level. Options: `accurate` (higher quality, slower) or `fast` (lower quality, faster). Choose based on speed vs. accuracy requirements.",
      "title": "Recognition",
      "type": "string"
    }
  },
  "title": "OcrMacOptions",
  "type": "object"
}
```

<a id="model-doclingocroptions"></a>

### DoclingOcrOptions

Base configuration for Optical Character Recognition engines.

Defines the common interface shared by all OCR engine implementations.
Subclasses provide engine-specific parameters while inheriting the shared
language selection, full-page OCR toggle, and bitmap area threshold.

See Also:
    `OcrAutoOptions`: Automatic engine selection based on availability.
    `EasyOcrOptions`, `TesseractCliOcrOptions`, `TesseractOcrOptions`,
    `RapidOcrOptions`, `OcrMacOptions`: Engine-specific configurations.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `bitmap_area_threshold` | não | number | default=0.05 | Percentage of the page area for a bitmap to be processed with OCR. |
| `force_full_page_ocr` | não | boolean | default=false | If enabled, a full-page OCR is always applied. |
| `lang` | sim | array de string |  | List of OCR languages to use. The format must match the values of the OCR engine of choice. |

Esquema JSON completo:

```json
{
  "description": "Base configuration for Optical Character Recognition engines.\n\nDefines the common interface shared by all OCR engine implementations.\nSubclasses provide engine-specific parameters while inheriting the shared\nlanguage selection, full-page OCR toggle, and bitmap area threshold.\n\nSee Also:\n    `OcrAutoOptions`: Automatic engine selection based on availability.\n    `EasyOcrOptions`, `TesseractCliOcrOptions`, `TesseractOcrOptions`,\n    `RapidOcrOptions`, `OcrMacOptions`: Engine-specific configurations.",
  "properties": {
    "bitmap_area_threshold": {
      "default": 0.05,
      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
      "examples": [
        0.05,
        0.1
      ],
      "title": "Bitmap Area Threshold",
      "type": "number"
    },
    "force_full_page_ocr": {
      "default": false,
      "description": "If enabled, a full-page OCR is always applied.",
      "examples": [
        false
      ],
      "title": "Force Full Page Ocr",
      "type": "boolean"
    },
    "lang": {
      "description": "List of OCR languages to use. The format must match the values of the OCR engine of choice.",
      "examples": [
        [
          "deu",
          "eng"
        ]
      ],
      "items": {
        "type": "string"
      },
      "title": "Lang",
      "type": "array"
    }
  },
  "required": [
    "lang"
  ],
  "title": "OcrOptions",
  "type": "object"
}
```

<a id="model-doclingonnxruntimeimageclassificationengineoptions"></a>

### DoclingOnnxRuntimeImageClassificationEngineOptions

Runtime configuration for ONNX Runtime based image-classification models.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `engine_type` | não | string | default="onnxruntime"; const="onnxruntime" |  |
| `graph_optimization_level` | não | integer | default=99 | ONNX Runtime graph optimization level. Accepts onnxruntime.GraphOptimizationLevel int values: 0 (ORT_DISABLE_ALL), 1 (ORT_ENABLE_BASIC), 2 (ORT_ENABLE_EXTENDED), 99 (ORT_ENABLE_ALL). Default enables all optimizations including layout optimizations. |
| `model_filename` | não | string | default="model.onnx" | Filename of the ONNX export inside the model repository |
| `providers` | não | array de string |  | Ordered list of ONNX Runtime execution providers to try |
| `top_k` | não | integer / null | default=null | Maximum number of classes to return. If None, all classes are returned. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Runtime configuration for ONNX Runtime based image-classification models.",
  "properties": {
    "engine_type": {
      "const": "onnxruntime",
      "default": "onnxruntime",
      "title": "Engine Type",
      "type": "string"
    },
    "graph_optimization_level": {
      "default": 99,
      "description": "ONNX Runtime graph optimization level. Accepts onnxruntime.GraphOptimizationLevel int values: 0 (ORT_DISABLE_ALL), 1 (ORT_ENABLE_BASIC), 2 (ORT_ENABLE_EXTENDED), 99 (ORT_ENABLE_ALL). Default enables all optimizations including layout optimizations.",
      "title": "Graph Optimization Level",
      "type": "integer"
    },
    "model_filename": {
      "default": "model.onnx",
      "description": "Filename of the ONNX export inside the model repository",
      "title": "Model Filename",
      "type": "string"
    },
    "providers": {
      "description": "Ordered list of ONNX Runtime execution providers to try",
      "items": {
        "type": "string"
      },
      "title": "Providers",
      "type": "array"
    },
    "top_k": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Maximum number of classes to return. If None, all classes are returned.",
      "title": "Top K"
    }
  },
  "title": "OnnxRuntimeImageClassificationEngineOptions",
  "type": "object"
}
```

<a id="model-doclingpictureclassificationlabel"></a>

### DoclingPictureClassificationLabel

PictureClassificationLabel.

Esquema JSON completo:

```json
{
  "description": "PictureClassificationLabel.",
  "enum": [
    "bar_chart",
    "box_plot",
    "flow_chart",
    "line_chart",
    "pie_chart",
    "scatter_plot",
    "table",
    "other_chart",
    "full_page_image",
    "page_thumbnail",
    "photograph",
    "chemistry_structure",
    "bar_code",
    "icon",
    "logo",
    "qr_code",
    "signature",
    "stamp",
    "engineering_drawing",
    "screenshot_from_computer",
    "screenshot_from_manual",
    "geographical_map",
    "topographical_map",
    "calendar",
    "crossword_puzzle",
    "music",
    "other",
    "cad_drawing",
    "electrical_diagram",
    "map",
    "heatmap",
    "chemistry_markush_structure",
    "chemistry_molecular_structure",
    "natural_image",
    "picture_group",
    "remote_sensing",
    "scatter_chart",
    "screenshot",
    "stacked_bar_chart",
    "stratigraphic_chart"
  ],
  "title": "PictureClassificationLabel",
  "type": "string"
}
```

<a id="model-doclingpicturedescriptionapioptions"></a>

### DoclingPictureDescriptionApiOptions

Configuration for API-based picture description services.

Sends images to an OpenAI-compatible chat completions endpoint for
description generation. Supports custom headers for authentication,
configurable timeouts, and concurrent request control.

Notes:
    Requires ``enable_remote_services=True`` on the parent pipeline
    options to permit external API calls.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `batch_size` | não | integer | default=8; minimum=1 | Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory. |
| `classification_allow` | não | array de [DoclingPictureClassificationLabel](#model-doclingpictureclassificationlabel) / null | default=null | List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts). |
| `classification_deny` | não | array de [DoclingPictureClassificationLabel](#model-doclingpictureclassificationlabel) / null | default=null | List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos). |
| `classification_min_confidence` | não | number | default=0.0 | Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence). |
| `concurrency` | não | integer | default=1 | Number of concurrent API requests allowed. Higher values improve throughput but may hit API rate limits. Adjust based on API service quotas and network capacity. |
| `headers` | não | object | default={}; additionalProperties={"type": "string"} | HTTP headers to include in API requests. Use for authentication or custom headers required by your API service. |
| `kind` | não | string | default="api"; const="api" |  |
| `params` | não | object | default={}; additionalProperties=true | Additional query parameters to include in API requests. Service-specific parameters for customizing API behavior beyond standard options. |
| `picture_area_threshold` | não | number | default=0.05 | Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images. |
| `prompt` | não | string | default="Describe this image in a few sentences." | Prompt template sent to the vision model for image description. Customize to guide the model's output style, detail level, or focus. |
| `provenance` | não | string | default="" | Provenance information to track the source or method of picture descriptions. Used for metadata and auditing purposes in the output document. |
| `scale` | não | number | default=2.0; exclusiveMinimum=0 | Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical. |
| `timeout` | não | number | default=20.0 | Maximum time in seconds to wait for API response before timing out. Increase for slow networks or complex image descriptions. Recommended: 10-60 seconds. |
| `url` | não | string (uri) | default="http://localhost:8000/v1/chat/completions"; minLength=1 | API endpoint URL for picture description service. Must be OpenAI-compatible chat completions endpoint. Default points to local server; update for cloud services or custom deployments. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration for API-based picture description services.\n\nSends images to an OpenAI-compatible chat completions endpoint for\ndescription generation. Supports custom headers for authentication,\nconfigurable timeouts, and concurrent request control.\n\nNotes:\n    Requires ``enable_remote_services=True`` on the parent pipeline\n    options to permit external API calls.",
  "properties": {
    "batch_size": {
      "default": 8,
      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
      "minimum": 1,
      "title": "Batch Size",
      "type": "integer"
    },
    "classification_allow": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingPictureClassificationLabel"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
      "title": "Classification Allow"
    },
    "classification_deny": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingPictureClassificationLabel"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
      "title": "Classification Deny"
    },
    "classification_min_confidence": {
      "default": 0.0,
      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
      "title": "Classification Min Confidence",
      "type": "number"
    },
    "concurrency": {
      "default": 1,
      "description": "Number of concurrent API requests allowed. Higher values improve throughput but may hit API rate limits. Adjust based on API service quotas and network capacity.",
      "title": "Concurrency",
      "type": "integer"
    },
    "headers": {
      "additionalProperties": {
        "type": "string"
      },
      "default": {},
      "description": "HTTP headers to include in API requests. Use for authentication or custom headers required by your API service.",
      "examples": [
        {
          "Authorization": "Bearer TOKEN"
        }
      ],
      "title": "Headers",
      "type": "object"
    },
    "kind": {
      "const": "api",
      "default": "api",
      "title": "Engine",
      "type": "string"
    },
    "params": {
      "additionalProperties": true,
      "default": {},
      "description": "Additional query parameters to include in API requests. Service-specific parameters for customizing API behavior beyond standard options.",
      "title": "Params",
      "type": "object"
    },
    "picture_area_threshold": {
      "default": 0.05,
      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
      "title": "Picture Area Threshold",
      "type": "number"
    },
    "prompt": {
      "default": "Describe this image in a few sentences.",
      "description": "Prompt template sent to the vision model for image description. Customize to guide the model's output style, detail level, or focus.",
      "examples": [
        "Provide a technical description of this diagram"
      ],
      "title": "Prompt",
      "type": "string"
    },
    "provenance": {
      "default": "",
      "description": "Provenance information to track the source or method of picture descriptions. Used for metadata and auditing purposes in the output document.",
      "title": "Provenance",
      "type": "string"
    },
    "scale": {
      "default": 2.0,
      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
      "exclusiveMinimum": 0,
      "title": "Scale",
      "type": "number"
    },
    "timeout": {
      "default": 20.0,
      "description": "Maximum time in seconds to wait for API response before timing out. Increase for slow networks or complex image descriptions. Recommended: 10-60 seconds.",
      "title": "Timeout",
      "type": "number"
    },
    "url": {
      "default": "http://localhost:8000/v1/chat/completions",
      "description": "API endpoint URL for picture description service. Must be OpenAI-compatible chat completions endpoint. Default points to local server; update for cloud services or custom deployments.",
      "format": "uri",
      "minLength": 1,
      "title": "Url",
      "type": "string"
    }
  },
  "title": "PictureDescriptionApiOptions",
  "type": "object",
  "x-unavailable-reason": "Serviços remotos desabilitados no servidor"
}
```

<a id="model-doclingpicturedescriptionbaseoptions"></a>

### DoclingPictureDescriptionBaseOptions

Base configuration for picture description models.

Provides shared parameters for all picture description backends,
including batch processing, image scaling, area thresholds, and
classification-based filtering (allow/deny lists). Concrete
implementations supply the actual model integration.

See Also:
    `PictureDescriptionApiOptions`: OpenAI-compatible API backend.
    `PictureDescriptionVlmOptions`: Legacy HuggingFace Transformers
        backend.
    `PictureDescriptionVlmEngineOptions`: New runtime-based backend
        with preset support (recommended).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `batch_size` | não | integer | default=8; minimum=1 | Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory. |
| `classification_allow` | não | array de [DoclingPictureClassificationLabel](#model-doclingpictureclassificationlabel) / null | default=null | List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts). |
| `classification_deny` | não | array de [DoclingPictureClassificationLabel](#model-doclingpictureclassificationlabel) / null | default=null | List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos). |
| `classification_min_confidence` | não | number | default=0.0 | Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence). |
| `picture_area_threshold` | não | number | default=0.05 | Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images. |
| `scale` | não | number | default=2.0; exclusiveMinimum=0 | Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical. |

Esquema JSON completo:

```json
{
  "description": "Base configuration for picture description models.\n\nProvides shared parameters for all picture description backends,\nincluding batch processing, image scaling, area thresholds, and\nclassification-based filtering (allow/deny lists). Concrete\nimplementations supply the actual model integration.\n\nSee Also:\n    `PictureDescriptionApiOptions`: OpenAI-compatible API backend.\n    `PictureDescriptionVlmOptions`: Legacy HuggingFace Transformers\n        backend.\n    `PictureDescriptionVlmEngineOptions`: New runtime-based backend\n        with preset support (recommended).",
  "properties": {
    "batch_size": {
      "default": 8,
      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
      "minimum": 1,
      "title": "Batch Size",
      "type": "integer"
    },
    "classification_allow": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingPictureClassificationLabel"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
      "title": "Classification Allow"
    },
    "classification_deny": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingPictureClassificationLabel"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
      "title": "Classification Deny"
    },
    "classification_min_confidence": {
      "default": 0.0,
      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
      "title": "Classification Min Confidence",
      "type": "number"
    },
    "picture_area_threshold": {
      "default": 0.05,
      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
      "title": "Picture Area Threshold",
      "type": "number"
    },
    "scale": {
      "default": 2.0,
      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
      "exclusiveMinimum": 0,
      "title": "Scale",
      "type": "number"
    }
  },
  "title": "PictureDescriptionBaseOptions",
  "type": "object"
}
```

<a id="model-doclingpicturedescriptionvlmengineoptions"></a>

### DoclingPictureDescriptionVlmEngineOptions

Configuration for VLM runtime-based picture description.

This is the new implementation that uses the pluggable runtime system with preset support.
Supports all runtime types (Transformers, MLX, API, etc.) through the unified runtime interface.

Use `from_preset()` to create instances from registered presets.

Examples:
    # Use preset with default runtime
    options = PictureDescriptionVlmEngineOptions.from_preset("smolvlm")

    # Use preset with runtime override
    from docling.datamodel.vlm_engine_options import MlxVlmEngineOptions, VlmEngineType
    options = PictureDescriptionVlmEngineOptions.from_preset(
        "smolvlm",
        engine_options=MlxVlmEngineOptions(engine_type=VlmEngineType.MLX)
    )

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `batch_size` | não | integer | default=8; minimum=1 | Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory. |
| `classification_allow` | não | array de [DoclingPictureClassificationLabel](#model-doclingpictureclassificationlabel) / null | default=null | List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts). |
| `classification_deny` | não | array de [DoclingPictureClassificationLabel](#model-doclingpictureclassificationlabel) / null | default=null | List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos). |
| `classification_min_confidence` | não | number | default=0.0 | Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence). |
| `engine_options` | sim | [DoclingApiVlmEngineOptions](#model-doclingapivlmengineoptions) / [DoclingAutoInlineVlmEngineOptions](#model-doclingautoinlinevlmengineoptions) / [DoclingMlxVlmEngineOptions](#model-doclingmlxvlmengineoptions) / [DoclingTransformersVlmEngineOptions](#model-doclingtransformersvlmengineoptions) / [DoclingVllmVlmEngineOptions](#model-doclingvllmvlmengineoptions) |  | Runtime configuration (transformers, mlx, api, etc.) |
| `generation_config` | não | object | default={"do_sample": false, "max_new_tokens": 200}; additionalProperties=true | Generation configuration for text generation. Controls output length, sampling strategy, temperature, etc. |
| `kind` | não | string | default="picture_description_vlm_engine"; const="picture_description_vlm_engine" |  |
| `model_spec` | sim | [DoclingVlmModelSpec](#model-doclingvlmmodelspec) |  | Model specification with runtime-specific overrides |
| `picture_area_threshold` | não | number | default=0.05 | Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images. |
| `prompt` | não | string | default="Describe this image in a few sentences." | Prompt template for the vision model. Customize to control description style, detail level, or focus. |
| `scale` | não | number | default=2.0; exclusiveMinimum=0 | Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration for VLM runtime-based picture description.\n\nThis is the new implementation that uses the pluggable runtime system with preset support.\nSupports all runtime types (Transformers, MLX, API, etc.) through the unified runtime interface.\n\nUse `from_preset()` to create instances from registered presets.\n\nExamples:\n    # Use preset with default runtime\n    options = PictureDescriptionVlmEngineOptions.from_preset(\"smolvlm\")\n\n    # Use preset with runtime override\n    from docling.datamodel.vlm_engine_options import MlxVlmEngineOptions, VlmEngineType\n    options = PictureDescriptionVlmEngineOptions.from_preset(\n        \"smolvlm\",\n        engine_options=MlxVlmEngineOptions(engine_type=VlmEngineType.MLX)\n    )",
  "properties": {
    "batch_size": {
      "default": 8,
      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
      "minimum": 1,
      "title": "Batch Size",
      "type": "integer"
    },
    "classification_allow": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingPictureClassificationLabel"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
      "title": "Classification Allow"
    },
    "classification_deny": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingPictureClassificationLabel"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
      "title": "Classification Deny"
    },
    "classification_min_confidence": {
      "default": 0.0,
      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
      "title": "Classification Min Confidence",
      "type": "number"
    },
    "engine_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingApiVlmEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingAutoInlineVlmEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingMlxVlmEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingTransformersVlmEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingVllmVlmEngineOptions"
        }
      ],
      "description": "Runtime configuration (transformers, mlx, api, etc.)"
    },
    "generation_config": {
      "additionalProperties": true,
      "default": {
        "do_sample": false,
        "max_new_tokens": 200
      },
      "description": "Generation configuration for text generation. Controls output length, sampling strategy, temperature, etc.",
      "title": "Generation Config",
      "type": "object"
    },
    "kind": {
      "const": "picture_description_vlm_engine",
      "default": "picture_description_vlm_engine",
      "title": "Engine",
      "type": "string"
    },
    "model_spec": {
      "$ref": "#/components/schemas/DoclingVlmModelSpec",
      "description": "Model specification with runtime-specific overrides"
    },
    "picture_area_threshold": {
      "default": 0.05,
      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
      "title": "Picture Area Threshold",
      "type": "number"
    },
    "prompt": {
      "default": "Describe this image in a few sentences.",
      "description": "Prompt template for the vision model. Customize to control description style, detail level, or focus.",
      "examples": [
        "What is shown in this image?",
        "Provide a detailed technical description"
      ],
      "title": "Prompt",
      "type": "string"
    },
    "scale": {
      "default": 2.0,
      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
      "exclusiveMinimum": 0,
      "title": "Scale",
      "type": "number"
    }
  },
  "required": [
    "engine_options",
    "model_spec"
  ],
  "title": "PictureDescriptionVlmEngineOptions",
  "type": "object"
}
```

<a id="model-doclingpicturedescriptionvlmoptions"></a>

### DoclingPictureDescriptionVlmOptions

Configuration for inline vision-language models for picture description.

This is the legacy implementation that uses direct HuggingFace Transformers integration.
For the new runtime-based system with preset support, use PictureDescriptionVlmEngineOptions.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `batch_size` | não | integer | default=8; minimum=1 | Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory. |
| `classification_allow` | não | array de [DoclingPictureClassificationLabel](#model-doclingpictureclassificationlabel) / null | default=null | List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts). |
| `classification_deny` | não | array de [DoclingPictureClassificationLabel](#model-doclingpictureclassificationlabel) / null | default=null | List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos). |
| `classification_min_confidence` | não | number | default=0.0 | Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence). |
| `generation_config` | não | object | default={"do_sample": false, "max_new_tokens": 200}; additionalProperties=true | HuggingFace generation configuration for text generation. Controls output length, sampling strategy, temperature, etc. See: https://huggingface.co/docs/transformers/en/main_classes/text_generation#transformers.GenerationConfig |
| `kind` | não | string | default="vlm"; const="vlm" |  |
| `padding_side` | não | string | default="left"; enum=["left", "right"] | Tokenizer padding side used for batched generation. Defaults to left to preserve the legacy behavior, but can be overridden for models that require right padding. |
| `picture_area_threshold` | não | number | default=0.05 | Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images. |
| `prompt` | não | string | default="Describe this image in a few sentences." | Prompt template for the vision model. Customize to control description style, detail level, or focus. |
| `repo_id` | sim | string |  | HuggingFace model repository ID for the vision-language model. Must be a model capable of image-to-text generation for picture descriptions. |
| `scale` | não | number | default=2.0; exclusiveMinimum=0 | Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration for inline vision-language models for picture description.\n\nThis is the legacy implementation that uses direct HuggingFace Transformers integration.\nFor the new runtime-based system with preset support, use PictureDescriptionVlmEngineOptions.",
  "properties": {
    "batch_size": {
      "default": 8,
      "description": "Number of images to process in a single batch during picture description. Higher values improve throughput but increase memory usage. Adjust based on available GPU/CPU memory.",
      "minimum": 1,
      "title": "Batch Size",
      "type": "integer"
    },
    "classification_allow": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingPictureClassificationLabel"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "List of picture classification labels to allow for description. Only pictures classified with these labels will be processed. If None, all picture types are allowed unless explicitly denied. Use to focus description on specific image types (e.g., diagrams, charts).",
      "title": "Classification Allow"
    },
    "classification_deny": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingPictureClassificationLabel"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "List of picture classification labels to exclude from description. Pictures classified with these labels will be skipped. If None, no picture types are denied unless not in allow list. Use to exclude unwanted image types (e.g., decorative images, logos).",
      "title": "Classification Deny"
    },
    "classification_min_confidence": {
      "default": 0.0,
      "description": "Minimum classification confidence score (0.0-1.0) required for a picture to be processed. Pictures with classification confidence below this threshold are skipped. Higher values ensure only confidently classified images are described. Range: 0.0 (no filtering) to 1.0 (maximum confidence).",
      "title": "Classification Min Confidence",
      "type": "number"
    },
    "generation_config": {
      "additionalProperties": true,
      "default": {
        "do_sample": false,
        "max_new_tokens": 200
      },
      "description": "HuggingFace generation configuration for text generation. Controls output length, sampling strategy, temperature, etc. See: https://huggingface.co/docs/transformers/en/main_classes/text_generation#transformers.GenerationConfig",
      "title": "Generation Config",
      "type": "object"
    },
    "kind": {
      "const": "vlm",
      "default": "vlm",
      "title": "Engine",
      "type": "string"
    },
    "padding_side": {
      "default": "left",
      "description": "Tokenizer padding side used for batched generation. Defaults to left to preserve the legacy behavior, but can be overridden for models that require right padding.",
      "enum": [
        "left",
        "right"
      ],
      "title": "Padding Side",
      "type": "string"
    },
    "picture_area_threshold": {
      "default": 0.05,
      "description": "Minimum picture area as fraction of page area (0.0-1.0) to trigger description. Pictures smaller than this threshold are skipped. Use lower values (e.g., 0.01) to describe small images.",
      "title": "Picture Area Threshold",
      "type": "number"
    },
    "prompt": {
      "default": "Describe this image in a few sentences.",
      "description": "Prompt template for the vision model. Customize to control description style, detail level, or focus.",
      "examples": [
        "What is shown in this image?",
        "Provide a detailed technical description"
      ],
      "title": "Prompt",
      "type": "string"
    },
    "repo_id": {
      "description": "HuggingFace model repository ID for the vision-language model. Must be a model capable of image-to-text generation for picture descriptions.",
      "examples": [
        "HuggingFaceTB/SmolVLM-256M-Instruct",
        "ibm-granite/granite-vision-3.3-2b"
      ],
      "title": "Repo Id",
      "type": "string"
    },
    "scale": {
      "default": 2.0,
      "description": "Scaling factor for image resolution before processing. Higher values (e.g., 2.0) provide more detail for the vision model but increase processing time and memory. Range: 0.5-4.0 typical.",
      "exclusiveMinimum": 0,
      "title": "Scale",
      "type": "number"
    }
  },
  "required": [
    "repo_id"
  ],
  "title": "PictureDescriptionVlmOptions",
  "type": "object"
}
```

<a id="model-doclingpipelineoptions"></a>

### DoclingPipelineOptions

Configuration options for the PDF document processing pipeline.

Notes:
    - Enabling multiple features (OCR, table structure, formulas) increases the processing time significantly.
        Enable only necessary features for your use case.
    - For production systems processing large document volumes, implement a timeout protection (for instance, 90-120
        seconds via `document_timeout` parameter).
    - OCR requires a system installation of engines (Tesseract, EasyOCR). Verify the installation before enabling
        OCR via `do_ocr=True`.
    - RapidOCR has known issues with read-only filesystems (e.g., Databricks). Consider Tesseract or alternative
        backends for distributed systems.

See Also:
    - `examples/pipeline_options_advanced.py`: Comprehensive configuration examples.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `accelerator_options` | não | [DoclingAcceleratorOptions](#model-doclingacceleratoroptions) | default={"cuda_use_flash_attention2": false, "device": "auto", "num_threads": 4} | Hardware acceleration configuration for model inference. Controls GPU device selection, memory management, and execution optimization settings for layout, OCR, and table structure models. |
| `allow_external_plugins` | não | boolean | default=false | Allow loading external third-party plugins for OCR, layout, table structure, or picture description models. Enables custom model implementations via plugin system. Disabled by default for security. |
| `artifacts_path` | não | string (path) / string / null | default=null | Local directory containing pre-downloaded model artifacts (weights, configs). If None, models are fetched from remote sources on first use. Use `docling-tools models download` to pre-fetch artifacts for offline operation or faster initialization. |
| `batch_polling_interval_seconds` | não | number | default=0.5 | Polling interval in seconds for batch collection in threaded pipeline stages. Each stage waits up to this duration to accumulate items before processing. Lower values reduce latency but may decrease batching efficiency. Only used by `StandardPdfPipeline` (threaded mode). |
| `chart_extraction_options` | não | [DoclingChartExtractionModelOptions](#model-doclingchartextractionmodeloptions) | default={"chart2code": false, "chart2csv": true, "chart2summary": false, "kind": "chart_extraction", "model": "granite-vision-v4"} | Configuration for the chart extraction model, including which model variant to use and which output formats to generate (CSV, code, summary). |
| `code_formula_options` | não | [DoclingCodeFormulaVlmOptions](#model-doclingcodeformulavlmoptions) | default={"engine_options": {"engine_type": "auto_inline"}, "extract_code": true, "extract_formulas": true, "max_size": null, "model_spec": {"api_overrides": {}, "default_repo_id": "docling-project/CodeFormulaV2", "engine_overrides": {"transformers": {"extra_config": {"extra_generation_config": {"skip_special_tokens": false}, "torch_dtype": "bfloat16", "transformers_model_type": "automodel-imagetexttotext"}, "repo_id": null, "revision": null, "torch_dtype": null}}, "max_new_tokens": 4096, "name": "CodeFormulaV2", "prompt": "", "response_format": "plaintext", "revision": "main", "stop_strings": ["</doctag>", "<end_of_utterance>"], "supported_engines": null, "trust_remote_code": false}, "scale": 2.0} | Configuration for code and formula extraction using VLM. Uses new preset system (recommended). Default: 'default' preset. Only applicable when `do_code_enrichment=True` or `do_formula_enrichment=True`. Example: CodeFormulaVlmOptions.from_preset('granite_vision') |
| `do_chart_extraction` | não | boolean | default=false | Enable chart data extraction to convert bar, pie, and line charts into structured tabular data. Automatically enables picture classification. Only applicable when `do_chart_extraction=True`. |
| `do_code_enrichment` | não | boolean | default=false | Enable specialized processing for code blocks. Applies code-aware OCR and formatting to improve accuracy of programming language snippets, terminal output, and structured code content. |
| `do_formula_enrichment` | não | boolean | default=false | Enable mathematical formula recognition and LaTeX conversion. Uses specialized models to detect and extract mathematical expressions, converting them to LaTeX format for accurate representation. |
| `do_ocr` | não | boolean | default=true | Enable Optical Character Recognition for scanned or image-based PDFs. Replaces or supplements programmatic text extraction with OCR-detected text. Required for scanned documents with no embedded text layer. Note: OCR significantly increases processing time. |
| `do_picture_classification` | não | boolean | default=false | Enable picture classification to categorize images by type (photo, diagram, chart, etc.). Useful for downstream processing that requires image type awareness. |
| `do_picture_description` | não | boolean | default=false | Enable automatic generation of textual descriptions for pictures using vision-language models. Descriptions are added to the document for accessibility and searchability. |
| `do_table_structure` | não | boolean | default=true | Enable table structure extraction and reconstruction. Detects table regions, extracts cell content with row/column relationships, and reconstructs the logical table structure for downstream processing. |
| `document_timeout` | não | number / null | default=null | Maximum processing time in seconds before aborting document conversion. When exceeded, the pipeline stops processing and returns partial results with PARTIAL_SUCCESS status. If None, no timeout is enforced. Recommended: 90-120 seconds for production systems. |
| `enable_remote_services` | não | boolean | default=false | Allow pipeline to call external APIs or cloud services during processing. Required for API-based picture description models. Disabled by default for security and offline operation. |
| `force_backend_text` | não | boolean | default=false | Force use of PDF backend's native text extraction instead of layout model predictions. When enabled, bypasses the layout model's text detection and uses the embedded text from the PDF file directly. Useful for PDFs with reliable programmatic text layers. |
| `generate_page_images` | não | boolean | default=false | Generate rendered page images during extraction. Creates PNG representations of each page for visual preview, validation, or downstream image-based machine learning tasks. |
| `generate_parsed_pages` | não | boolean | default=false | Retain intermediate parsed page representations after processing. When enabled, keeps detailed page-level parsing data structures for debugging or advanced post-processing. Increases memory usage. Automatically disabled after document assembly unless explicitly enabled. |
| `generate_picture_images` | não | boolean | default=false | Extract and save embedded images from the PDF. Exports individual images (figures, photos, diagrams, charts) found in the document as separate image files for downstream use. |
| `generate_table_images` | não | boolean | default=false |  |
| `images_scale` | não | number | default=1.0 | Scaling factor for generated images. Higher values produce higher resolution but increase processing time and storage requirements. Recommended values: 1.0 (standard quality), 2.0 (high resolution), 0.5 (lower resolution for previews). |
| `layout_batch_size` | não | integer | default=4 | Batch size for layout analysis stage in threaded pipeline. Pages are grouped and processed together by the layout model. Higher values improve throughput but increase memory usage. Only used by `StandardPdfPipeline` (threaded mode). |
| `layout_options` | não | [DoclingLayoutOptions](#model-doclinglayoutoptions) | default={"create_orphan_clusters": true, "keep_empty_clusters": false, "kind": "docling_layout_default", "model_spec": {"model_path": "", "name": "docling_layout_heron", "repo_id": "docling-project/docling-layout-heron", "revision": "main", "supported_devices": ["cpu", "cuda", "mps", "xpu"]}, "skip_cell_assignment": false} | Configuration for document layout analysis model. Controls layout detection behavior including cluster creation for orphaned elements, cell assignment to table structures, and handling of empty regions. Specifies which layout model to use (default: Heron). |
| `ocr_batch_size` | não | integer | default=4 | Batch size for OCR processing stage in threaded pipeline. Pages are grouped and processed together to improve throughput. Higher values increase GPU/CPU utilization but require more memory. Only used by `StandardPdfPipeline` (threaded mode). |
| `ocr_options` | não | [DoclingEasyOcrOptions](#model-doclingeasyocroptions) / [DoclingKserveV2OcrOptions](#model-doclingkservev2ocroptions) / [DoclingOcrAutoOptions](#model-doclingocrautooptions) / [DoclingOcrMacOptions](#model-doclingocrmacoptions) / [DoclingRapidOcrOptions](#model-doclingrapidocroptions) / [DoclingTesseractCliOcrOptions](#model-doclingtesseractcliocroptions) / [DoclingTesseractOcrOptions](#model-doclingtesseractocroptions) | default={"bitmap_area_threshold": 0.05, "force_full_page_ocr": false, "kind": "auto", "lang": []} | Configuration for OCR engine. Specifies which OCR engine to use (Tesseract, EasyOCR, RapidOCR, etc.) and engine-specific settings. Only applicable when `do_ocr=True`. |
| `picture_classification_options` | não | [DoclingDocumentPictureClassifierOptions](#model-doclingdocumentpictureclassifieroptions) | default={"engine_options": {"engine_type": "transformers", "top_k": null}, "kind": "document_picture_classifier", "model_spec": {"engine_overrides": {}, "name": "document_figure_classifier_v2", "repo_id": "docling-project/DocumentFigureClassifier-v2.5", "revision": "main"}} | Configuration for picture classification model/runtime. Supports selecting transformers, onnxruntime, or remote api_kserve_v2 inference engines. |
| `picture_description_options` | não | [DoclingPictureDescriptionApiOptions](#model-doclingpicturedescriptionapioptions) / [DoclingPictureDescriptionVlmEngineOptions](#model-doclingpicturedescriptionvlmengineoptions) / [DoclingPictureDescriptionVlmOptions](#model-doclingpicturedescriptionvlmoptions) | default={"batch_size": 8, "classification_allow": null, "classification_deny": null, "classification_min_confidence": 0.0, "engine_options": {"engine_type": "auto_inline"}, "generation_config": {"do_sample": false, "max_new_tokens": 200}, "kind": "picture_description_vlm_engine", "model_spec": {"api_overrides": {"api_lmstudio": {"params": {"model": "smolvlm-256m-instruct"}}}, "default_repo_id": "HuggingFaceTB/SmolVLM-256M-Instruct", "engine_overrides": {"mlx": {"extra_config": {}, "repo_id": "moot20/SmolVLM-256M-Instruct-MLX", "revision": null, "torch_dtype": null}, "transformers": {"extra_config": {"transformers_model_type": "automodel-imagetexttotext"}, "repo_id": null, "revision": null, "torch_dtype": "bfloat16"}}, "max_new_tokens": 4096, "name": "SmolVLM-256M-Instruct", "prompt": "Describe this image in a few sentences.", "response_format": "plaintext", "revision": "main", "stop_strings": [], "supported_engines": null, "trust_remote_code": false}, "picture_area_threshold": 0.05, "prompt": "Describe this image in a few sentences.", "scale": 2.0} | Configuration for picture description model. Uses new preset system (recommended). Default: 'smolvlm' preset. Only applicable when `do_picture_description=True`. Example: PictureDescriptionVlmOptions.from_preset('granite_vision') |
| `queue_max_size` | não | integer | default=100 | Maximum queue size for inter-stage communication in threaded pipeline. Limits the number of items buffered between processing stages to prevent memory overflow. When full, upstream stages block until space is available. Only used by `StandardPdfPipeline` (threaded mode). |
| `table_batch_size` | não | integer | default=4 | Batch size for table structure extraction stage in threaded pipeline. Tables from multiple pages are processed together. Higher values improve throughput but increase memory usage. Only used by `StandardPdfPipeline` (threaded mode). |
| `table_structure_options` | não | [DoclingTableStructureOptions](#model-doclingtablestructureoptions) | default={"do_cell_matching": true, "kind": "docling_tableformer", "mode": "accurate"} | Configuration for table structure extraction. Controls table detection accuracy, cell matching behavior, and table formatting. Only applicable when `do_table_structure=True`. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration options for the PDF document processing pipeline.\n\nNotes:\n    - Enabling multiple features (OCR, table structure, formulas) increases the processing time significantly.\n        Enable only necessary features for your use case.\n    - For production systems processing large document volumes, implement a timeout protection (for instance, 90-120\n        seconds via `document_timeout` parameter).\n    - OCR requires a system installation of engines (Tesseract, EasyOCR). Verify the installation before enabling\n        OCR via `do_ocr=True`.\n    - RapidOCR has known issues with read-only filesystems (e.g., Databricks). Consider Tesseract or alternative\n        backends for distributed systems.\n\nSee Also:\n    - `examples/pipeline_options_advanced.py`: Comprehensive configuration examples.",
  "properties": {
    "accelerator_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingAcceleratorOptions"
        }
      ],
      "default": {
        "cuda_use_flash_attention2": false,
        "device": "auto",
        "num_threads": 4
      },
      "description": "Hardware acceleration configuration for model inference. Controls GPU device selection, memory management, and execution optimization settings for layout, OCR, and table structure models.",
      "readOnly": true
    },
    "allow_external_plugins": {
      "default": false,
      "description": "Allow loading external third-party plugins for OCR, layout, table structure, or picture description models. Enables custom model implementations via plugin system. Disabled by default for security.",
      "examples": [
        false
      ],
      "title": "Allow External Plugins",
      "type": "boolean",
      "readOnly": true
    },
    "artifacts_path": {
      "anyOf": [
        {
          "format": "path",
          "type": "string"
        },
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Local directory containing pre-downloaded model artifacts (weights, configs). If None, models are fetched from remote sources on first use. Use `docling-tools models download` to pre-fetch artifacts for offline operation or faster initialization.",
      "examples": [
        "./artifacts",
        "/tmp/docling_outputs"
      ],
      "title": "Artifacts Path",
      "readOnly": true
    },
    "batch_polling_interval_seconds": {
      "default": 0.5,
      "description": "Polling interval in seconds for batch collection in threaded pipeline stages. Each stage waits up to this duration to accumulate items before processing. Lower values reduce latency but may decrease batching efficiency. Only used by `StandardPdfPipeline` (threaded mode).",
      "title": "Batch Polling Interval Seconds",
      "type": "number"
    },
    "chart_extraction_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingChartExtractionModelOptions"
        }
      ],
      "default": {
        "chart2code": false,
        "chart2csv": true,
        "chart2summary": false,
        "kind": "chart_extraction",
        "model": "granite-vision-v4"
      },
      "description": "Configuration for the chart extraction model, including which model variant to use and which output formats to generate (CSV, code, summary)."
    },
    "code_formula_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingCodeFormulaVlmOptions"
        }
      ],
      "default": {
        "engine_options": {
          "engine_type": "auto_inline"
        },
        "extract_code": true,
        "extract_formulas": true,
        "max_size": null,
        "model_spec": {
          "api_overrides": {},
          "default_repo_id": "docling-project/CodeFormulaV2",
          "engine_overrides": {
            "transformers": {
              "extra_config": {
                "extra_generation_config": {
                  "skip_special_tokens": false
                },
                "torch_dtype": "bfloat16",
                "transformers_model_type": "automodel-imagetexttotext"
              },
              "repo_id": null,
              "revision": null,
              "torch_dtype": null
            }
          },
          "max_new_tokens": 4096,
          "name": "CodeFormulaV2",
          "prompt": "",
          "response_format": "plaintext",
          "revision": "main",
          "stop_strings": [
            "</doctag>",
            "<end_of_utterance>"
          ],
          "supported_engines": null,
          "trust_remote_code": false
        },
        "scale": 2.0
      },
      "description": "Configuration for code and formula extraction using VLM. Uses new preset system (recommended). Default: 'default' preset. Only applicable when `do_code_enrichment=True` or `do_formula_enrichment=True`. Example: CodeFormulaVlmOptions.from_preset('granite_vision')"
    },
    "do_chart_extraction": {
      "default": false,
      "description": "Enable chart data extraction to convert bar, pie, and line charts into structured tabular data. Automatically enables picture classification. Only applicable when `do_chart_extraction=True`.",
      "title": "Do Chart Extraction",
      "type": "boolean"
    },
    "do_code_enrichment": {
      "default": false,
      "description": "Enable specialized processing for code blocks. Applies code-aware OCR and formatting to improve accuracy of programming language snippets, terminal output, and structured code content.",
      "title": "Do Code Enrichment",
      "type": "boolean"
    },
    "do_formula_enrichment": {
      "default": false,
      "description": "Enable mathematical formula recognition and LaTeX conversion. Uses specialized models to detect and extract mathematical expressions, converting them to LaTeX format for accurate representation.",
      "title": "Do Formula Enrichment",
      "type": "boolean"
    },
    "do_ocr": {
      "default": true,
      "description": "Enable Optical Character Recognition for scanned or image-based PDFs. Replaces or supplements programmatic text extraction with OCR-detected text. Required for scanned documents with no embedded text layer. Note: OCR significantly increases processing time.",
      "title": "Do Ocr",
      "type": "boolean"
    },
    "do_picture_classification": {
      "default": false,
      "description": "Enable picture classification to categorize images by type (photo, diagram, chart, etc.). Useful for downstream processing that requires image type awareness.",
      "title": "Do Picture Classification",
      "type": "boolean"
    },
    "do_picture_description": {
      "default": false,
      "description": "Enable automatic generation of textual descriptions for pictures using vision-language models. Descriptions are added to the document for accessibility and searchability.",
      "title": "Do Picture Description",
      "type": "boolean"
    },
    "do_table_structure": {
      "default": true,
      "description": "Enable table structure extraction and reconstruction. Detects table regions, extracts cell content with row/column relationships, and reconstructs the logical table structure for downstream processing.",
      "title": "Do Table Structure",
      "type": "boolean"
    },
    "document_timeout": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Maximum processing time in seconds before aborting document conversion. When exceeded, the pipeline stops processing and returns partial results with PARTIAL_SUCCESS status. If None, no timeout is enforced. Recommended: 90-120 seconds for production systems.",
      "examples": [
        10.0,
        20.0
      ],
      "title": "Document Timeout"
    },
    "enable_remote_services": {
      "default": false,
      "description": "Allow pipeline to call external APIs or cloud services during processing. Required for API-based picture description models. Disabled by default for security and offline operation.",
      "examples": [
        false
      ],
      "title": "Enable Remote Services",
      "type": "boolean",
      "readOnly": true
    },
    "force_backend_text": {
      "default": false,
      "description": "Force use of PDF backend's native text extraction instead of layout model predictions. When enabled, bypasses the layout model's text detection and uses the embedded text from the PDF file directly. Useful for PDFs with reliable programmatic text layers.",
      "title": "Force Backend Text",
      "type": "boolean"
    },
    "generate_page_images": {
      "default": false,
      "description": "Generate rendered page images during extraction. Creates PNG representations of each page for visual preview, validation, or downstream image-based machine learning tasks.",
      "title": "Generate Page Images",
      "type": "boolean"
    },
    "generate_parsed_pages": {
      "default": false,
      "description": "Retain intermediate parsed page representations after processing. When enabled, keeps detailed page-level parsing data structures for debugging or advanced post-processing. Increases memory usage. Automatically disabled after document assembly unless explicitly enabled.",
      "title": "Generate Parsed Pages",
      "type": "boolean"
    },
    "generate_picture_images": {
      "default": false,
      "description": "Extract and save embedded images from the PDF. Exports individual images (figures, photos, diagrams, charts) found in the document as separate image files for downstream use.",
      "title": "Generate Picture Images",
      "type": "boolean"
    },
    "generate_table_images": {
      "default": false,
      "deprecated": true,
      "title": "Generate Table Images",
      "type": "boolean"
    },
    "images_scale": {
      "default": 1.0,
      "description": "Scaling factor for generated images. Higher values produce higher resolution but increase processing time and storage requirements. Recommended values: 1.0 (standard quality), 2.0 (high resolution), 0.5 (lower resolution for previews).",
      "title": "Images Scale",
      "type": "number"
    },
    "layout_batch_size": {
      "default": 4,
      "description": "Batch size for layout analysis stage in threaded pipeline. Pages are grouped and processed together by the layout model. Higher values improve throughput but increase memory usage. Only used by `StandardPdfPipeline` (threaded mode).",
      "title": "Layout Batch Size",
      "type": "integer"
    },
    "layout_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingLayoutOptions"
        }
      ],
      "default": {
        "create_orphan_clusters": true,
        "keep_empty_clusters": false,
        "kind": "docling_layout_default",
        "model_spec": {
          "model_path": "",
          "name": "docling_layout_heron",
          "repo_id": "docling-project/docling-layout-heron",
          "revision": "main",
          "supported_devices": [
            "cpu",
            "cuda",
            "mps",
            "xpu"
          ]
        },
        "skip_cell_assignment": false
      },
      "description": "Configuration for document layout analysis model. Controls layout detection behavior including cluster creation for orphaned elements, cell assignment to table structures, and handling of empty regions. Specifies which layout model to use (default: Heron)."
    },
    "ocr_batch_size": {
      "default": 4,
      "description": "Batch size for OCR processing stage in threaded pipeline. Pages are grouped and processed together to improve throughput. Higher values increase GPU/CPU utilization but require more memory. Only used by `StandardPdfPipeline` (threaded mode).",
      "title": "Ocr Batch Size",
      "type": "integer"
    },
    "ocr_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingEasyOcrOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingKserveV2OcrOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingOcrAutoOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingOcrMacOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingRapidOcrOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingTesseractCliOcrOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingTesseractOcrOptions"
        }
      ],
      "default": {
        "bitmap_area_threshold": 0.05,
        "force_full_page_ocr": false,
        "kind": "auto",
        "lang": []
      },
      "description": "Configuration for OCR engine. Specifies which OCR engine to use (Tesseract, EasyOCR, RapidOCR, etc.) and engine-specific settings. Only applicable when `do_ocr=True`."
    },
    "picture_classification_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingDocumentPictureClassifierOptions"
        }
      ],
      "default": {
        "engine_options": {
          "engine_type": "transformers",
          "top_k": null
        },
        "kind": "document_picture_classifier",
        "model_spec": {
          "engine_overrides": {},
          "name": "document_figure_classifier_v2",
          "repo_id": "docling-project/DocumentFigureClassifier-v2.5",
          "revision": "main"
        }
      },
      "description": "Configuration for picture classification model/runtime. Supports selecting transformers, onnxruntime, or remote api_kserve_v2 inference engines."
    },
    "picture_description_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingPictureDescriptionApiOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingPictureDescriptionVlmEngineOptions"
        },
        {
          "$ref": "#/components/schemas/DoclingPictureDescriptionVlmOptions"
        }
      ],
      "default": {
        "batch_size": 8,
        "classification_allow": null,
        "classification_deny": null,
        "classification_min_confidence": 0.0,
        "engine_options": {
          "engine_type": "auto_inline"
        },
        "generation_config": {
          "do_sample": false,
          "max_new_tokens": 200
        },
        "kind": "picture_description_vlm_engine",
        "model_spec": {
          "api_overrides": {
            "api_lmstudio": {
              "params": {
                "model": "smolvlm-256m-instruct"
              }
            }
          },
          "default_repo_id": "HuggingFaceTB/SmolVLM-256M-Instruct",
          "engine_overrides": {
            "mlx": {
              "extra_config": {},
              "repo_id": "moot20/SmolVLM-256M-Instruct-MLX",
              "revision": null,
              "torch_dtype": null
            },
            "transformers": {
              "extra_config": {
                "transformers_model_type": "automodel-imagetexttotext"
              },
              "repo_id": null,
              "revision": null,
              "torch_dtype": "bfloat16"
            }
          },
          "max_new_tokens": 4096,
          "name": "SmolVLM-256M-Instruct",
          "prompt": "Describe this image in a few sentences.",
          "response_format": "plaintext",
          "revision": "main",
          "stop_strings": [],
          "supported_engines": null,
          "trust_remote_code": false
        },
        "picture_area_threshold": 0.05,
        "prompt": "Describe this image in a few sentences.",
        "scale": 2.0
      },
      "description": "Configuration for picture description model. Uses new preset system (recommended). Default: 'smolvlm' preset. Only applicable when `do_picture_description=True`. Example: PictureDescriptionVlmOptions.from_preset('granite_vision')"
    },
    "queue_max_size": {
      "default": 100,
      "description": "Maximum queue size for inter-stage communication in threaded pipeline. Limits the number of items buffered between processing stages to prevent memory overflow. When full, upstream stages block until space is available. Only used by `StandardPdfPipeline` (threaded mode).",
      "title": "Queue Max Size",
      "type": "integer"
    },
    "table_batch_size": {
      "default": 4,
      "description": "Batch size for table structure extraction stage in threaded pipeline. Tables from multiple pages are processed together. Higher values improve throughput but increase memory usage. Only used by `StandardPdfPipeline` (threaded mode).",
      "title": "Table Batch Size",
      "type": "integer"
    },
    "table_structure_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingTableStructureOptions"
        }
      ],
      "default": {
        "do_cell_matching": true,
        "kind": "docling_tableformer",
        "mode": "accurate"
      },
      "description": "Configuration for table structure extraction. Controls table detection accuracy, cell matching behavior, and table formatting. Only applicable when `do_table_structure=True`."
    }
  },
  "title": "PdfPipelineOptions",
  "type": "object"
}
```

<a id="model-doclingrapidocroptions"></a>

### DoclingRapidOcrOptions

Configuration for RapidOCR engine with multiple backend support.

See Also:
    - https://rapidai.github.io/RapidOCRDocs/install_usage/api/RapidOCR/
    - https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/#__tabbed_3_4

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `backend` | não | string | default="onnxruntime"; enum=["onnxruntime", "openvino", "paddle", "torch"] | Inference backend for RapidOCR. Options: `onnxruntime` (default, cross-platform), `openvino` (Intel), `paddle` (PaddlePaddle), `torch` (PyTorch). Choose based on your hardware and available libraries. |
| `bitmap_area_threshold` | não | number | default=0.05 | Percentage of the page area for a bitmap to be processed with OCR. |
| `cls_model_path` | não | string / null | default=null | Custom path to text classification model. If None, uses default RapidOCR model. |
| `det_model_path` | não | string / null | default=null | Custom path to text detection model. If None, uses default RapidOCR model. |
| `font_path` | não | string / null | default=null | Custom path to font file for text rendering in visualization. |
| `force_full_page_ocr` | não | boolean | default=false | If enabled, a full-page OCR is always applied. |
| `kind` | não | string | default="rapidocr"; const="rapidocr" |  |
| `lang` | não | array de string | default=["english", "chinese"] | List of OCR languages. Note: RapidOCR does not currently support language selection; this parameter is reserved for future compatibility. See RapidOCR documentation for supported languages. |
| `print_verbose` | não | boolean | default=false | Enable verbose logging output from RapidOCR for debugging purposes. |
| `rapidocr_params` | não | object | default={}; additionalProperties=true | Additional parameters to pass through to RapidOCR engine. Use this to override or extend default RapidOCR configuration with engine-specific options. |
| `rec_font_path` | não | string / null | default=null | Deprecated. Use font_path instead. |
| `rec_keys_path` | não | string / null | default=null | Custom path to recognition keys file. If None, uses default RapidOCR keys. |
| `rec_model_path` | não | string / null | default=null | Custom path to text recognition model. If None, uses default RapidOCR model. |
| `text_score` | não | number | default=0.5 | Minimum confidence score for text detection. Text regions with scores below this threshold are filtered out. Range: 0.0-1.0. Lower values detect more text but may include false positives. |
| `use_cls` | não | boolean / null | default=null | Enable text direction classification stage. If None, uses RapidOCR default behavior. |
| `use_det` | não | boolean / null | default=null | Enable text detection stage. If None, uses RapidOCR default behavior. |
| `use_rec` | não | boolean / null | default=null | Enable text recognition stage. If None, uses RapidOCR default behavior. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration for RapidOCR engine with multiple backend support.\n\nSee Also:\n    - https://rapidai.github.io/RapidOCRDocs/install_usage/api/RapidOCR/\n    - https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/#__tabbed_3_4",
  "properties": {
    "backend": {
      "default": "onnxruntime",
      "description": "Inference backend for RapidOCR. Options: `onnxruntime` (default, cross-platform), `openvino` (Intel), `paddle` (PaddlePaddle), `torch` (PyTorch). Choose based on your hardware and available libraries.",
      "enum": [
        "onnxruntime",
        "openvino",
        "paddle",
        "torch"
      ],
      "title": "Backend",
      "type": "string"
    },
    "bitmap_area_threshold": {
      "default": 0.05,
      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
      "examples": [
        0.05,
        0.1
      ],
      "title": "Bitmap Area Threshold",
      "type": "number"
    },
    "cls_model_path": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Custom path to text classification model. If None, uses default RapidOCR model.",
      "title": "Cls Model Path",
      "readOnly": true
    },
    "det_model_path": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Custom path to text detection model. If None, uses default RapidOCR model.",
      "title": "Det Model Path",
      "readOnly": true
    },
    "font_path": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Custom path to font file for text rendering in visualization.",
      "title": "Font Path",
      "readOnly": true
    },
    "force_full_page_ocr": {
      "default": false,
      "description": "If enabled, a full-page OCR is always applied.",
      "examples": [
        false
      ],
      "title": "Force Full Page Ocr",
      "type": "boolean"
    },
    "kind": {
      "const": "rapidocr",
      "default": "rapidocr",
      "title": "Engine",
      "type": "string"
    },
    "lang": {
      "default": [
        "english",
        "chinese"
      ],
      "description": "List of OCR languages. Note: RapidOCR does not currently support language selection; this parameter is reserved for future compatibility. See RapidOCR documentation for supported languages.",
      "items": {
        "type": "string"
      },
      "title": "Lang",
      "type": "array"
    },
    "print_verbose": {
      "default": false,
      "description": "Enable verbose logging output from RapidOCR for debugging purposes.",
      "title": "Print Verbose",
      "type": "boolean"
    },
    "rapidocr_params": {
      "additionalProperties": true,
      "default": {},
      "description": "Additional parameters to pass through to RapidOCR engine. Use this to override or extend default RapidOCR configuration with engine-specific options.",
      "title": "Rapidocr Params",
      "type": "object"
    },
    "rec_font_path": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "deprecated": true,
      "description": "Deprecated. Use font_path instead.",
      "title": "Rec Font Path",
      "readOnly": true
    },
    "rec_keys_path": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Custom path to recognition keys file. If None, uses default RapidOCR keys.",
      "title": "Rec Keys Path",
      "readOnly": true
    },
    "rec_model_path": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Custom path to text recognition model. If None, uses default RapidOCR model.",
      "title": "Rec Model Path",
      "readOnly": true
    },
    "text_score": {
      "default": 0.5,
      "description": "Minimum confidence score for text detection. Text regions with scores below this threshold are filtered out. Range: 0.0-1.0. Lower values detect more text but may include false positives.",
      "title": "Text Score",
      "type": "number"
    },
    "use_cls": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Enable text direction classification stage. If None, uses RapidOCR default behavior.",
      "title": "Use Cls"
    },
    "use_det": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Enable text detection stage. If None, uses RapidOCR default behavior.",
      "title": "Use Det"
    },
    "use_rec": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Enable text recognition stage. If None, uses RapidOCR default behavior.",
      "title": "Use Rec"
    }
  },
  "title": "RapidOcrOptions",
  "type": "object"
}
```

<a id="model-doclingresponseformat"></a>

### DoclingResponseFormat

Esquema JSON completo:

```json
{
  "enum": [
    "doctags",
    "markdown",
    "deepseekocr_markdown",
    "html",
    "otsl",
    "plaintext"
  ],
  "title": "ResponseFormat",
  "type": "string"
}
```

<a id="model-doclingtableformermode"></a>

### DoclingTableFormerMode

Operating modes for TableFormer table structure extraction model.

Controls the trade-off between processing speed and extraction accuracy.
Choose based on your performance requirements and document complexity.

Attributes:
    FAST: Fast mode prioritizes speed over precision. Suitable for simple tables or high-volume
        processing.
    ACCURATE: Accurate mode provides higher quality results with slower processing. Recommended for complex
        tables and production use.

Esquema JSON completo:

```json
{
  "description": "Operating modes for TableFormer table structure extraction model.\n\nControls the trade-off between processing speed and extraction accuracy.\nChoose based on your performance requirements and document complexity.\n\nAttributes:\n    FAST: Fast mode prioritizes speed over precision. Suitable for simple tables or high-volume\n        processing.\n    ACCURATE: Accurate mode provides higher quality results with slower processing. Recommended for complex\n        tables and production use.",
  "enum": [
    "fast",
    "accurate"
  ],
  "title": "TableFormerMode",
  "type": "string"
}
```

<a id="model-doclingtablestructureoptions"></a>

### DoclingTableStructureOptions

Options for the table structure (TableFormer V1).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `do_cell_matching` | não | boolean | default=true | Enable cell matching to align detected table cells with their content. When enabled, the model attempts to match table structure predictions with actual cell content for improved accuracy. |
| `kind` | não | string | default="docling_tableformer"; const="docling_tableformer" |  |
| `mode` | não | [DoclingTableFormerMode](#model-doclingtableformermode) | default="accurate" | Table structure extraction mode. `accurate` provides higher quality results with slower processing, while `fast` prioritizes speed over precision. Recommended: `accurate` for production use. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Options for the table structure (TableFormer V1).",
  "properties": {
    "do_cell_matching": {
      "default": true,
      "description": "Enable cell matching to align detected table cells with their content. When enabled, the model attempts to match table structure predictions with actual cell content for improved accuracy.",
      "title": "Do Cell Matching",
      "type": "boolean"
    },
    "kind": {
      "const": "docling_tableformer",
      "default": "docling_tableformer",
      "title": "Engine",
      "type": "string"
    },
    "mode": {
      "$ref": "#/components/schemas/DoclingTableFormerMode",
      "default": "accurate",
      "description": "Table structure extraction mode. `accurate` provides higher quality results with slower processing, while `fast` prioritizes speed over precision. Recommended: `accurate` for production use."
    }
  },
  "title": "TableStructureOptions",
  "type": "object"
}
```

<a id="model-doclingtesseractcliocroptions"></a>

### DoclingTesseractCliOcrOptions

Configuration for Tesseract OCR via command-line interface.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `bitmap_area_threshold` | não | number | default=0.05 | Percentage of the page area for a bitmap to be processed with OCR. |
| `force_full_page_ocr` | não | boolean | default=false | If enabled, a full-page OCR is always applied. |
| `kind` | não | string | default="tesseract"; const="tesseract" |  |
| `lang` | não | array de string | default=["fra", "deu", "spa", "eng"] | List of Tesseract language codes. Use 3-letter ISO 639-2 codes (e.g., `eng`, `fra`, `deu`). Multiple languages enable multilingual OCR. Requires corresponding Tesseract language data files. |
| `path` | não | string / null | default=null | Path to Tesseract data directory containing language files. If None, uses Tesseract's default TESSDATA_PREFIX location. |
| `psm` | não | integer / null | default=null | Page Segmentation Mode for Tesseract. Values 0-13 control how Tesseract segments the page. Common values: 3 (auto), 6 (uniform block), 11 (sparse text). If None, uses Tesseract default. |
| `tesseract_cmd` | não | string | default="tesseract" | Command or path to Tesseract executable. Use `tesseract` if in system PATH, or provide full path for custom installations (e.g., `/usr/local/bin/tesseract`). |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration for Tesseract OCR via command-line interface.",
  "properties": {
    "bitmap_area_threshold": {
      "default": 0.05,
      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
      "examples": [
        0.05,
        0.1
      ],
      "title": "Bitmap Area Threshold",
      "type": "number"
    },
    "force_full_page_ocr": {
      "default": false,
      "description": "If enabled, a full-page OCR is always applied.",
      "examples": [
        false
      ],
      "title": "Force Full Page Ocr",
      "type": "boolean"
    },
    "kind": {
      "const": "tesseract",
      "default": "tesseract",
      "title": "Engine",
      "type": "string"
    },
    "lang": {
      "default": [
        "fra",
        "deu",
        "spa",
        "eng"
      ],
      "description": "List of Tesseract language codes. Use 3-letter ISO 639-2 codes (e.g., `eng`, `fra`, `deu`). Multiple languages enable multilingual OCR. Requires corresponding Tesseract language data files.",
      "items": {
        "type": "string"
      },
      "title": "Lang",
      "type": "array"
    },
    "path": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Path to Tesseract data directory containing language files. If None, uses Tesseract's default TESSDATA_PREFIX location.",
      "title": "Path",
      "readOnly": true
    },
    "psm": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Page Segmentation Mode for Tesseract. Values 0-13 control how Tesseract segments the page. Common values: 3 (auto), 6 (uniform block), 11 (sparse text). If None, uses Tesseract default.",
      "title": "Psm"
    },
    "tesseract_cmd": {
      "default": "tesseract",
      "description": "Command or path to Tesseract executable. Use `tesseract` if in system PATH, or provide full path for custom installations (e.g., `/usr/local/bin/tesseract`).",
      "title": "Tesseract Cmd",
      "type": "string",
      "readOnly": true
    }
  },
  "title": "TesseractCliOcrOptions",
  "type": "object"
}
```

<a id="model-doclingtesseractocroptions"></a>

### DoclingTesseractOcrOptions

Configuration for Tesseract OCR via Python bindings (tesserocr).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `bitmap_area_threshold` | não | number | default=0.05 | Percentage of the page area for a bitmap to be processed with OCR. |
| `force_full_page_ocr` | não | boolean | default=false | If enabled, a full-page OCR is always applied. |
| `kind` | não | string | default="tesserocr"; const="tesserocr" |  |
| `lang` | não | array de string | default=["fra", "deu", "spa", "eng"] | List of Tesseract language codes. Use 3-letter ISO 639-2 codes (e.g., `eng`, `fra`, `deu`). Multiple languages enable multilingual OCR. Requires corresponding Tesseract language data files. |
| `path` | não | string / null | default=null | Path to Tesseract data directory containing language files. If None, uses Tesseract's default TESSDATA_PREFIX location. |
| `psm` | não | integer / null | default=null | Page Segmentation Mode for Tesseract. Values 0-13 control how Tesseract segments the page. Common values: 3 (auto), 6 (uniform block), 11 (sparse text). If None, uses Tesseract default. |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Configuration for Tesseract OCR via Python bindings (tesserocr).",
  "properties": {
    "bitmap_area_threshold": {
      "default": 0.05,
      "description": "Percentage of the page area for a bitmap to be processed with OCR.",
      "examples": [
        0.05,
        0.1
      ],
      "title": "Bitmap Area Threshold",
      "type": "number"
    },
    "force_full_page_ocr": {
      "default": false,
      "description": "If enabled, a full-page OCR is always applied.",
      "examples": [
        false
      ],
      "title": "Force Full Page Ocr",
      "type": "boolean"
    },
    "kind": {
      "const": "tesserocr",
      "default": "tesserocr",
      "title": "Engine",
      "type": "string"
    },
    "lang": {
      "default": [
        "fra",
        "deu",
        "spa",
        "eng"
      ],
      "description": "List of Tesseract language codes. Use 3-letter ISO 639-2 codes (e.g., `eng`, `fra`, `deu`). Multiple languages enable multilingual OCR. Requires corresponding Tesseract language data files.",
      "items": {
        "type": "string"
      },
      "title": "Lang",
      "type": "array"
    },
    "path": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Path to Tesseract data directory containing language files. If None, uses Tesseract's default TESSDATA_PREFIX location.",
      "title": "Path",
      "readOnly": true
    },
    "psm": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Page Segmentation Mode for Tesseract. Values 0-13 control how Tesseract segments the page. Common values: 3 (auto), 6 (uniform block), 11 (sparse text). If None, uses Tesseract default.",
      "title": "Psm"
    }
  },
  "title": "TesseractOcrOptions",
  "type": "object"
}
```

<a id="model-doclingtransformersimageclassificationengineoptions"></a>

### DoclingTransformersImageClassificationEngineOptions

Runtime configuration for Transformers-based image-classification models.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `compile_model` | não | boolean |  | Whether to compile the model with torch.compile() for better performance. |
| `engine_type` | não | string | default="transformers"; const="transformers" |  |
| `top_k` | não | integer / null | default=null | Maximum number of classes to return. If None, all classes are returned. |
| `torch_dtype` | não | string / null | default=null | PyTorch dtype for model inference (e.g., 'float32', 'float16', 'bfloat16') |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Runtime configuration for Transformers-based image-classification models.",
  "properties": {
    "compile_model": {
      "description": "Whether to compile the model with torch.compile() for better performance.",
      "title": "Compile Model",
      "type": "boolean"
    },
    "engine_type": {
      "const": "transformers",
      "default": "transformers",
      "title": "Engine Type",
      "type": "string"
    },
    "top_k": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Maximum number of classes to return. If None, all classes are returned.",
      "title": "Top K"
    },
    "torch_dtype": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "PyTorch dtype for model inference (e.g., 'float32', 'float16', 'bfloat16')",
      "title": "Torch Dtype"
    }
  },
  "title": "TransformersImageClassificationEngineOptions",
  "type": "object"
}
```

<a id="model-doclingtransformersvlmengineoptions"></a>

### DoclingTransformersVlmEngineOptions

Options for HuggingFace Transformers inference engine.

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `compile_model` | não | boolean |  | Whether to compile the model with torch.compile() for better performance. |
| `device` | não | [DoclingAcceleratorDevice](#model-doclingacceleratordevice) / null | default=null | Device to use (auto-detected if None) |
| `engine_type` | não | string | default="transformers"; const="transformers" |  |
| `llm_int8_threshold` | não | number | default=6.0 | Threshold for LLM.int8() quantization |
| `load_in_8bit` | não | boolean | default=true | Load model in 8-bit precision using bitsandbytes |
| `quantized` | não | boolean | default=false | Whether the model is pre-quantized |
| `torch_dtype` | não | string / null | default=null | PyTorch dtype (e.g., 'float16', 'bfloat16') |
| `trust_remote_code` | não | boolean | default=false | Allow execution of custom code from model repo |
| `use_kv_cache` | não | boolean | default=true | Enable key-value caching for attention |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Options for HuggingFace Transformers inference engine.",
  "properties": {
    "compile_model": {
      "description": "Whether to compile the model with torch.compile() for better performance.",
      "title": "Compile Model",
      "type": "boolean"
    },
    "device": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingAcceleratorDevice"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Device to use (auto-detected if None)"
    },
    "engine_type": {
      "const": "transformers",
      "default": "transformers",
      "title": "Engine Type",
      "type": "string"
    },
    "llm_int8_threshold": {
      "default": 6.0,
      "description": "Threshold for LLM.int8() quantization",
      "title": "Llm Int8 Threshold",
      "type": "number"
    },
    "load_in_8bit": {
      "default": true,
      "description": "Load model in 8-bit precision using bitsandbytes",
      "title": "Load In 8Bit",
      "type": "boolean"
    },
    "quantized": {
      "default": false,
      "description": "Whether the model is pre-quantized",
      "title": "Quantized",
      "type": "boolean"
    },
    "torch_dtype": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "PyTorch dtype (e.g., 'float16', 'bfloat16')",
      "title": "Torch Dtype"
    },
    "trust_remote_code": {
      "default": false,
      "description": "Allow execution of custom code from model repo",
      "title": "Trust Remote Code",
      "type": "boolean"
    },
    "use_kv_cache": {
      "default": true,
      "description": "Enable key-value caching for attention",
      "title": "Use Kv Cache",
      "type": "boolean"
    }
  },
  "title": "TransformersVlmEngineOptions",
  "type": "object"
}
```

<a id="model-doclingvllmcudagraphmode"></a>

### DoclingVllmCudaGraphMode

CUDA graph capture mode for the vLLM v1 engine.

Controls whether and how vLLM captures CUDA graphs to speed up inference.
CUDA graphs reduce kernel-launch overhead by replaying a recorded sequence
of CUDA operations instead of launching each kernel individually.

NONE:
    Disable CUDA graphs entirely; everything runs in eager mode.
    Fastest startup, lowest steady-state throughput.
    Best for short-lived processes, notebooks, and debugging.

FULL:
    Capture the entire forward pass as one monolithic CUDA graph.
    Maximum graph coverage but requires very static execution shapes;
    may fail with some models or dynamic workloads.

PIECEWISE:
    Capture segments of the model (e.g. transformer blocks) as multiple
    smaller graphs between selected ops.  Handles dynamic shapes better
    than FULL while still accelerating most of the forward pass.

FULL_AND_PIECEWISE:
    Hybrid mode (default in many vLLM versions): FULL graphs for
    decode-only batches; PIECEWISE graphs for prefill and mixed
    prefill+decode batches.  Usually the best throughput option for
    typical LLM serving workloads.

FULL_DECODE_ONLY:
    FULL CUDA graphs only for decode batches; prefill and mixed batches
    run in eager mode.  Dramatically reduces graph-capture time and
    memory footprint compared to FULL_AND_PIECEWISE while still
    accelerating token generation.

Esquema JSON completo:

```json
{
  "description": "CUDA graph capture mode for the vLLM v1 engine.\n\nControls whether and how vLLM captures CUDA graphs to speed up inference.\nCUDA graphs reduce kernel-launch overhead by replaying a recorded sequence\nof CUDA operations instead of launching each kernel individually.\n\nNONE:\n    Disable CUDA graphs entirely; everything runs in eager mode.\n    Fastest startup, lowest steady-state throughput.\n    Best for short-lived processes, notebooks, and debugging.\n\nFULL:\n    Capture the entire forward pass as one monolithic CUDA graph.\n    Maximum graph coverage but requires very static execution shapes;\n    may fail with some models or dynamic workloads.\n\nPIECEWISE:\n    Capture segments of the model (e.g. transformer blocks) as multiple\n    smaller graphs between selected ops.  Handles dynamic shapes better\n    than FULL while still accelerating most of the forward pass.\n\nFULL_AND_PIECEWISE:\n    Hybrid mode (default in many vLLM versions): FULL graphs for\n    decode-only batches; PIECEWISE graphs for prefill and mixed\n    prefill+decode batches.  Usually the best throughput option for\n    typical LLM serving workloads.\n\nFULL_DECODE_ONLY:\n    FULL CUDA graphs only for decode batches; prefill and mixed batches\n    run in eager mode.  Dramatically reduces graph-capture time and\n    memory footprint compared to FULL_AND_PIECEWISE while still\n    accelerating token generation.",
  "enum": [
    "NONE",
    "FULL",
    "PIECEWISE",
    "FULL_AND_PIECEWISE",
    "FULL_DECODE_ONLY"
  ],
  "title": "VllmCudaGraphMode",
  "type": "string"
}
```

<a id="model-doclingvllmvlmengineoptions"></a>

### DoclingVllmVlmEngineOptions

Options for vLLM inference engine (high-throughput serving).

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `cudagraph_mode` | não | [DoclingVllmCudaGraphMode](#model-doclingvllmcudagraphmode) | default="PIECEWISE" | CUDA graph capture mode (vLLM v1 engine only). See VllmCudaGraphMode for the available options and their trade-offs. |
| `device` | não | [DoclingAcceleratorDevice](#model-doclingacceleratordevice) / null | default=null | Device to use (auto-detected if None) |
| `engine_type` | não | string | default="vllm"; const="vllm" |  |
| `gpu_memory_utilization` | não | number | default=0.9 | Fraction of GPU memory to use |
| `tensor_parallel_size` | não | integer | default=1 | Number of GPUs for tensor parallelism |
| `trust_remote_code` | não | boolean | default=false | Allow execution of custom code from model repo |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "description": "Options for vLLM inference engine (high-throughput serving).",
  "properties": {
    "cudagraph_mode": {
      "$ref": "#/components/schemas/DoclingVllmCudaGraphMode",
      "default": "PIECEWISE",
      "description": "CUDA graph capture mode (vLLM v1 engine only). See VllmCudaGraphMode for the available options and their trade-offs."
    },
    "device": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DoclingAcceleratorDevice"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Device to use (auto-detected if None)"
    },
    "engine_type": {
      "const": "vllm",
      "default": "vllm",
      "title": "Engine Type",
      "type": "string"
    },
    "gpu_memory_utilization": {
      "default": 0.9,
      "description": "Fraction of GPU memory to use",
      "title": "Gpu Memory Utilization",
      "type": "number"
    },
    "tensor_parallel_size": {
      "default": 1,
      "description": "Number of GPUs for tensor parallelism",
      "title": "Tensor Parallel Size",
      "type": "integer"
    },
    "trust_remote_code": {
      "default": false,
      "description": "Allow execution of custom code from model repo",
      "title": "Trust Remote Code",
      "type": "boolean"
    }
  },
  "title": "VllmVlmEngineOptions",
  "type": "object"
}
```

<a id="model-doclingvlmenginetype"></a>

### DoclingVlmEngineType

Types of VLM inference engines available.

Esquema JSON completo:

```json
{
  "description": "Types of VLM inference engines available.",
  "enum": [
    "transformers",
    "mlx",
    "vllm",
    "api",
    "api_ollama",
    "api_lmstudio",
    "api_openai",
    "auto_inline"
  ],
  "title": "VlmEngineType",
  "type": "string"
}
```

<a id="model-doclingvlmmodelspec"></a>

### DoclingVlmModelSpec

Specification for a VLM model.

This defines the model configuration that is independent of the engine.
It includes:
- Default model repository ID
- Prompt template
- Response format
- Engine-specific overrides

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `api_overrides` | não | object | additionalProperties={"$ref": "#/components/schemas/DoclingApiModelConfig"} | API-specific configuration overrides |
| `default_repo_id` | sim | string |  | Default HuggingFace repository ID |
| `engine_overrides` | não | object | additionalProperties={"$ref": "#/components/schemas/DoclingEngineModelConfig"} | Engine-specific configuration overrides |
| `max_new_tokens` | não | integer | default=4096 | Maximum number of new tokens to generate |
| `name` | sim | string |  | Human-readable model name |
| `prompt` | sim | string |  | Prompt template for this model |
| `response_format` | sim | [DoclingResponseFormat](#model-doclingresponseformat) |  | Expected response format from the model |
| `revision` | não | string | default="main" | Default model revision |
| `stop_strings` | não | array de string |  | Stop strings for generation |
| `supported_engines` | não | array de [DoclingVlmEngineType](#model-doclingvlmenginetype) / null | default=null | Set of supported engines (None = all supported) |
| `trust_remote_code` | não | boolean | default=false | Whether to trust remote code for this model |

Esquema JSON completo:

```json
{
  "description": "Specification for a VLM model.\n\nThis defines the model configuration that is independent of the engine.\nIt includes:\n- Default model repository ID\n- Prompt template\n- Response format\n- Engine-specific overrides",
  "properties": {
    "api_overrides": {
      "additionalProperties": {
        "$ref": "#/components/schemas/DoclingApiModelConfig"
      },
      "description": "API-specific configuration overrides",
      "propertyNames": {
        "$ref": "#/components/schemas/DoclingVlmEngineType"
      },
      "title": "Api Overrides",
      "type": "object"
    },
    "default_repo_id": {
      "description": "Default HuggingFace repository ID",
      "title": "Default Repo Id",
      "type": "string"
    },
    "engine_overrides": {
      "additionalProperties": {
        "$ref": "#/components/schemas/DoclingEngineModelConfig"
      },
      "description": "Engine-specific configuration overrides",
      "propertyNames": {
        "$ref": "#/components/schemas/DoclingVlmEngineType"
      },
      "title": "Engine Overrides",
      "type": "object"
    },
    "max_new_tokens": {
      "default": 4096,
      "description": "Maximum number of new tokens to generate",
      "title": "Max New Tokens",
      "type": "integer"
    },
    "name": {
      "description": "Human-readable model name",
      "title": "Name",
      "type": "string"
    },
    "prompt": {
      "description": "Prompt template for this model",
      "title": "Prompt",
      "type": "string"
    },
    "response_format": {
      "$ref": "#/components/schemas/DoclingResponseFormat",
      "description": "Expected response format from the model"
    },
    "revision": {
      "default": "main",
      "description": "Default model revision",
      "title": "Revision",
      "type": "string"
    },
    "stop_strings": {
      "description": "Stop strings for generation",
      "items": {
        "type": "string"
      },
      "title": "Stop Strings",
      "type": "array"
    },
    "supported_engines": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/DoclingVlmEngineType"
          },
          "type": "array",
          "uniqueItems": true
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Set of supported engines (None = all supported)",
      "title": "Supported Engines"
    },
    "trust_remote_code": {
      "default": false,
      "description": "Whether to trust remote code for this model",
      "title": "Trust Remote Code",
      "type": "boolean"
    }
  },
  "required": [
    "name",
    "default_repo_id",
    "prompt",
    "response_format"
  ],
  "title": "VlmModelSpec",
  "type": "object"
}
```

<a id="model-documentcapabilities"></a>

### DocumentCapabilities

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `provider` | não | string | default="docling" |  |
| `version` | sim | string |  |  |
| `core_version` | sim | string |  |  |
| `image_extensions` | sim | array de string |  |  |
| `pipeline_schema` | sim | object | additionalProperties=true |  |
| `exports` | sim | object | additionalProperties=true |  |
| `presets` | sim | object | additionalProperties=true |  |
| `server_managed` | sim | array de string |  |  |
| `restrictions` | sim | array de string |  |  |
| `workers_running` | não | boolean | default=false |  |
| `worker_prerequisites` | não | array de object |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "provider": {
      "type": "string",
      "title": "Provider",
      "default": "docling"
    },
    "version": {
      "type": "string",
      "title": "Version"
    },
    "core_version": {
      "type": "string",
      "title": "Core Version"
    },
    "image_extensions": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Image Extensions"
    },
    "pipeline_schema": {
      "additionalProperties": true,
      "type": "object",
      "title": "Pipeline Schema"
    },
    "exports": {
      "additionalProperties": true,
      "type": "object",
      "title": "Exports"
    },
    "presets": {
      "additionalProperties": true,
      "type": "object",
      "title": "Presets"
    },
    "server_managed": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Server Managed"
    },
    "restrictions": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Restrictions"
    },
    "workers_running": {
      "type": "boolean",
      "title": "Workers Running",
      "default": false
    },
    "worker_prerequisites": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "type": "array",
      "title": "Worker Prerequisites"
    }
  },
  "type": "object",
  "required": [
    "version",
    "core_version",
    "image_extensions",
    "pipeline_schema",
    "exports",
    "presets",
    "server_managed",
    "restrictions"
  ],
  "title": "DocumentCapabilities"
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
| `provider` | não | string / null |  |  |
| `model` | não | string / null |  |  |
| `language_probability` | não | number / null |  |  |
| `processing_seconds` | não | number / null |  |  |
| `configuration` | não | object / null |  |  |
| `output_format` | não | string / null |  |  |
| `analysis_status` | não | string / null |  |  |
| `reason_code` | não | string / null |  |  |
| `source_page_number` | não | integer / null |  |  |
| `source_page_numbers` | não | array de integer / null |  |  |

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
    "provider": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Provider"
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
    "language_probability": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "title": "Language Probability"
    },
    "processing_seconds": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "title": "Processing Seconds"
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
    "output_format": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Output Format"
    },
    "analysis_status": {
      "anyOf": [
        {
          "type": "string",
          "enum": [
            "completed",
            "partial",
            "failed",
            "cancelled"
          ]
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
    },
    "source_page_number": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Page Number"
    },
    "source_page_numbers": {
      "anyOf": [
        {
          "items": {
            "type": "integer"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Source Page Numbers"
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

<a id="model-documentoptions"></a>

### DocumentOptions

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `pipeline` | não | [DoclingPipelineOptions](#model-doclingpipelineoptions) |  |  |
| `formats` | não | array de string | minItems=1; maxItems=9 |  |
| `output_format` | não | string | default="markdown"; enum=["markdown", "json", "html", "txt", "doclang", "doctags", "document_tokens", "element_tree", "vtt"] |  |
| `export_options` | não | object | additionalProperties=false | Parâmetros nativos por formato; caminhos de imagens são geridos pelo servidor. |
| `page_range` | não | array de objeto livre / null | default=null | Primeira/última página inclusivas, numeradas a partir de 1. |
| `max_num_pages` | não | integer / null | default=null |  |
| `max_file_size` | não | integer / null | default=null | Limite da conversão em bytes, adicional ao limite de upload do serviço. |
| `raises_on_error` | não | boolean | default=true |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "pipeline": {
      "$ref": "#/components/schemas/DoclingPipelineOptions"
    },
    "formats": {
      "items": {
        "enum": [
          "markdown",
          "json",
          "html",
          "txt",
          "doclang",
          "doctags",
          "document_tokens",
          "element_tree",
          "vtt"
        ],
        "type": "string"
      },
      "maxItems": 9,
      "minItems": 1,
      "title": "Formats",
      "type": "array"
    },
    "output_format": {
      "default": "markdown",
      "enum": [
        "markdown",
        "json",
        "html",
        "txt",
        "doclang",
        "doctags",
        "document_tokens",
        "element_tree",
        "vtt"
      ],
      "title": "Output Format",
      "type": "string"
    },
    "export_options": {
      "additionalProperties": false,
      "description": "Parâmetros nativos por formato; caminhos de imagens são geridos pelo servidor.",
      "title": "Export Options",
      "type": "object",
      "properties": {
        "doclang": {
          "$ref": "#/components/schemas/DoclingExportDoclang"
        },
        "doctags": {
          "$ref": "#/components/schemas/DoclingExportDoctags"
        },
        "document_tokens": {
          "$ref": "#/components/schemas/DoclingExportDocumentTokens"
        },
        "element_tree": {
          "$ref": "#/components/schemas/DoclingExportElementTree"
        },
        "html": {
          "$ref": "#/components/schemas/DoclingExportHtml"
        },
        "json": {
          "$ref": "#/components/schemas/DoclingExportJson"
        },
        "markdown": {
          "$ref": "#/components/schemas/DoclingExportMarkdown"
        },
        "txt": {
          "$ref": "#/components/schemas/DoclingExportTxt"
        },
        "vtt": {
          "$ref": "#/components/schemas/DoclingExportVtt"
        }
      }
    },
    "page_range": {
      "anyOf": [
        {
          "maxItems": 2,
          "minItems": 2,
          "prefixItems": [
            {
              "type": "integer"
            },
            {
              "type": "integer"
            }
          ],
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Primeira/última página inclusivas, numeradas a partir de 1.",
      "title": "Page Range"
    },
    "max_num_pages": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Max Num Pages"
    },
    "max_file_size": {
      "anyOf": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Limite da conversão em bytes, adicional ao limite de upload do serviço.",
      "title": "Max File Size"
    },
    "raises_on_error": {
      "default": true,
      "title": "Raises On Error",
      "type": "boolean"
    }
  },
  "title": "DocumentOptions",
  "type": "object"
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
| `text_input` | não | string / null |  | Frase/descrição/objetos nas tarefas que recebem texto. |
| `region` | não | array de number / null |  | Região normalizada [x_min,y_min,x_max,y_max], valores entre 0 e 1. |
| `generation` | não | [VisionGenerationOptions](#model-visiongenerationoptions) |  |  |

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
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "ImageAnalyzeOptions"
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
| `poll_url` | sim | string |  |  |
| `result_url` | sim | string |  |  |

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
    "poll_url": {
      "type": "string",
      "title": "Poll Url"
    },
    "result_url": {
      "type": "string",
      "title": "Result Url"
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

<a id="model-importobject"></a>

### ImportObject

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `connection_id` | sim | string | minLength=1; maxLength=36 |  |
| `bucket` | sim | string | minLength=1; maxLength=255 |  |
| `key` | sim | string | minLength=1; maxLength=1024 |  |
| `project` | não | string / null |  |  |
| `project_id` | não | string / null |  |  |
| `folder` | não | string / null |  |  |
| `folder_id` | não | string / null |  |  |
| `name` | não | string / null |  |  |
| `tags` | não | array de string |  |  |
| `docling_preset` | não | string | default="fast" |  |
| `conversion_options` | não | [DocumentOptions](#model-documentoptions) / null |  |  |
| `audio_options` | não | [AudioConversionOptions](#model-audioconversionoptions) / null |  |  |
| `datalake` | não | [Destination](#model-destination) / null |  |  |

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
    "key": {
      "type": "string",
      "maxLength": 1024,
      "minLength": 1,
      "title": "Key"
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
      "title": "Tags"
    },
    "docling_preset": {
      "type": "string",
      "title": "Docling Preset",
      "default": "fast"
    },
    "conversion_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/DocumentOptions"
        },
        {
          "type": "null"
        }
      ]
    },
    "audio_options": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/AudioConversionOptions"
        },
        {
          "type": "null"
        }
      ]
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
  "type": "object",
  "required": [
    "connection_id",
    "bucket",
    "key"
  ],
  "title": "ImportObject"
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
| `kind` | não | string / null |  |  |
| `image_analysis` | não | object / null |  |  |
| `configuration` | não | object / null |  | Solicitação persistida: operation, provider, model e options. |
| `status` | sim | [JobStatus](#model-jobstatus) |  |  |
| `progress` | sim | integer | minimum=0.0; maximum=100.0 |  |
| `created_at` | sim | string (date-time) |  |  |
| `started_at` | não | string (date-time) / null |  |  |
| `completed_at` | não | string (date-time) / null |  |  |
| `error` | não | string / null |  |  |
| `name` | não | string / null |  |  |
| `tags` | não | array de string | default=[] |  |
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
    "kind": {
      "anyOf": [
        {
          "type": "string",
          "enum": [
            "document",
            "transcription",
            "image"
          ]
        },
        {
          "type": "null"
        }
      ],
      "title": "Kind"
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
      "title": "Configuration",
      "description": "Solicitação persistida: operation, provider, model e options."
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

<a id="model-livecapabilities"></a>

### LiveCapabilities

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `enabled` | sim | boolean |  |  |
| `ready` | sim | boolean |  |  |
| `options_supported` | não | boolean | default=false |  |
| `provider` | não | string | default="faster-whisper"; const="faster-whisper" |  |
| `model` | sim | string |  |  |
| `languages` | sim | array de string |  |  |
| `protocol` | não | integer | default=1; const=1 |  |
| `max_duration_seconds` | sim | integer |  |  |
| `options_schema` | não | object | additionalProperties=true |  |
| `managed_parameters` | não | object | additionalProperties=true |  |
| `restrictions` | não | array de string |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "enabled": {
      "type": "boolean",
      "title": "Enabled"
    },
    "ready": {
      "type": "boolean",
      "title": "Ready"
    },
    "options_supported": {
      "type": "boolean",
      "title": "Options Supported",
      "default": false
    },
    "provider": {
      "type": "string",
      "const": "faster-whisper",
      "title": "Provider",
      "default": "faster-whisper"
    },
    "model": {
      "type": "string",
      "title": "Model"
    },
    "languages": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Languages"
    },
    "protocol": {
      "type": "integer",
      "const": 1,
      "title": "Protocol",
      "default": 1
    },
    "max_duration_seconds": {
      "type": "integer",
      "title": "Max Duration Seconds"
    },
    "options_schema": {
      "additionalProperties": true,
      "type": "object",
      "title": "Options Schema"
    },
    "managed_parameters": {
      "additionalProperties": true,
      "type": "object",
      "title": "Managed Parameters"
    },
    "restrictions": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "title": "Restrictions"
    }
  },
  "type": "object",
  "required": [
    "enabled",
    "ready",
    "model",
    "languages",
    "max_duration_seconds"
  ],
  "title": "LiveCapabilities"
}
```

<a id="model-livedecodingoptions"></a>

### LiveDecodingOptions

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `append_punctuations` | não | string | default="\"'.。,，!！?？:：”)]}、"; maxLength=128 |  |
| `beam_size` | não | integer | default=1; minimum=1.0; maximum=20.0 |  |
| `best_of` | não | integer | default=5; minimum=1.0; maximum=20.0 |  |
| `compression_ratio_threshold` | não | number / null | default=2.4 |  |
| `hallucination_silence_threshold` | não | number / null |  |  |
| `hotwords` | não | string / null |  |  |
| `initial_prompt` | não | string / null |  |  |
| `length_penalty` | não | number | default=1; minimum=0.0; maximum=2.0 |  |
| `log_prob_threshold` | não | number / null | default=-1.0 |  |
| `max_initial_timestamp` | não | number | default=1; minimum=0.0; maximum=30.0 |  |
| `max_new_tokens` | não | integer | default=128; minimum=1.0; maximum=448.0 |  |
| `no_repeat_ngram_size` | não | integer | default=0; minimum=0.0; maximum=100.0 |  |
| `no_speech_threshold` | não | number / null | default=0.6 |  |
| `patience` | não | number | default=1; maximum=10.0; exclusiveMinimum=0.0 |  |
| `prefix` | não | string / null |  |  |
| `prepend_punctuations` | não | string | default="\"'“¿([{-"; maxLength=128 |  |
| `prompt_reset_on_temperature` | não | number | default=0.5; minimum=0.0; maximum=1.0 |  |
| `repetition_penalty` | não | number | default=1; maximum=5.0; exclusiveMinimum=0.0 |  |
| `suppress_blank` | não | boolean | default=true |  |
| `suppress_tokens` | não | array de integer | maxItems=256 |  |
| `temperature` | não | number / array de number | default=0.0 |  |
| `vad_filter` | não | boolean | default=true |  |
| `vad_parameters` | não | [VadParameters](#model-vadparameters) / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "append_punctuations": {
      "type": "string",
      "maxLength": 128,
      "title": "Append Punctuations",
      "default": "\"'.。,，!！?？:：”)]}、"
    },
    "beam_size": {
      "type": "integer",
      "maximum": 20.0,
      "minimum": 1.0,
      "title": "Beam Size",
      "default": 1
    },
    "best_of": {
      "type": "integer",
      "maximum": 20.0,
      "minimum": 1.0,
      "title": "Best Of",
      "default": 5
    },
    "compression_ratio_threshold": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 1000000000.0,
          "exclusiveMinimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Compression Ratio Threshold",
      "default": 2.4
    },
    "hallucination_silence_threshold": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 1000000000.0,
          "exclusiveMinimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Hallucination Silence Threshold"
    },
    "hotwords": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 1024
        },
        {
          "type": "null"
        }
      ],
      "title": "Hotwords"
    },
    "initial_prompt": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 1024
        },
        {
          "type": "null"
        }
      ],
      "title": "Initial Prompt"
    },
    "length_penalty": {
      "type": "number",
      "maximum": 2.0,
      "minimum": 0.0,
      "title": "Length Penalty",
      "default": 1
    },
    "log_prob_threshold": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 1000000000.0,
          "minimum": -1000000000.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Log Prob Threshold",
      "default": -1.0
    },
    "max_initial_timestamp": {
      "type": "number",
      "maximum": 30.0,
      "minimum": 0.0,
      "title": "Max Initial Timestamp",
      "default": 1
    },
    "max_new_tokens": {
      "type": "integer",
      "maximum": 448.0,
      "minimum": 1.0,
      "title": "Max New Tokens",
      "default": 128
    },
    "no_repeat_ngram_size": {
      "type": "integer",
      "maximum": 100.0,
      "minimum": 0.0,
      "title": "No Repeat Ngram Size",
      "default": 0
    },
    "no_speech_threshold": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 1.0,
          "minimum": 0.0
        },
        {
          "type": "null"
        }
      ],
      "title": "No Speech Threshold",
      "default": 0.6
    },
    "patience": {
      "type": "number",
      "maximum": 10.0,
      "exclusiveMinimum": 0.0,
      "title": "Patience",
      "default": 1
    },
    "prefix": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 1024
        },
        {
          "type": "null"
        }
      ],
      "title": "Prefix"
    },
    "prepend_punctuations": {
      "type": "string",
      "maxLength": 128,
      "title": "Prepend Punctuations",
      "default": "\"'“¿([{-"
    },
    "prompt_reset_on_temperature": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Prompt Reset On Temperature",
      "default": 0.5
    },
    "repetition_penalty": {
      "type": "number",
      "maximum": 5.0,
      "exclusiveMinimum": 0.0,
      "title": "Repetition Penalty",
      "default": 1
    },
    "suppress_blank": {
      "type": "boolean",
      "title": "Suppress Blank",
      "default": true
    },
    "suppress_tokens": {
      "items": {
        "type": "integer"
      },
      "type": "array",
      "maxItems": 256,
      "title": "Suppress Tokens"
    },
    "temperature": {
      "anyOf": [
        {
          "type": "number",
          "maximum": 1.0,
          "minimum": 0.0
        },
        {
          "items": {
            "type": "number",
            "maximum": 1.0,
            "minimum": 0.0
          },
          "type": "array",
          "maxItems": 100,
          "minItems": 1
        }
      ],
      "title": "Temperature",
      "default": 0.0
    },
    "vad_filter": {
      "type": "boolean",
      "title": "Vad Filter",
      "default": true
    },
    "vad_parameters": {
      "anyOf": [
        {
          "$ref": "#/components/schemas/VadParameters"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "LiveDecodingOptions"
}
```

<a id="model-liveoptions"></a>

### LiveOptions

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `decoding` | não | [LiveDecodingOptions](#model-livedecodingoptions) |  |  |
| `interval_seconds` | não | number | default=0.6; minimum=0.2; maximum=5.0 | Minimum received audio between decoding passes. |
| `max_context_seconds` | não | number | default=8; minimum=4.0; maximum=30.0 | Context before trimming confirmed audio; unconfirmed audio is never discarded. |
| `segment_no_speech_threshold` | não | number | default=0.9; minimum=0.0; maximum=1.0 | Discard a decoded segment above this no-speech probability. |

Esquema JSON completo:

```json
{
  "properties": {
    "decoding": {
      "$ref": "#/components/schemas/LiveDecodingOptions"
    },
    "interval_seconds": {
      "type": "number",
      "maximum": 5.0,
      "minimum": 0.2,
      "title": "Interval Seconds",
      "description": "Minimum received audio between decoding passes.",
      "default": 0.6
    },
    "max_context_seconds": {
      "type": "number",
      "maximum": 30.0,
      "minimum": 4.0,
      "title": "Max Context Seconds",
      "description": "Context before trimming confirmed audio; unconfirmed audio is never discarded.",
      "default": 8
    },
    "segment_no_speech_threshold": {
      "type": "number",
      "maximum": 1.0,
      "minimum": 0.0,
      "title": "Segment No Speech Threshold",
      "description": "Discard a decoded segment above this no-speech probability.",
      "default": 0.9
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "LiveOptions"
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

<a id="model-locationbody"></a>

### LocationBody

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `project_id` | sim | string | minLength=1; maxLength=36 |  |
| `folder_id` | não | string / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "project_id": {
      "type": "string",
      "maxLength": 36,
      "minLength": 1,
      "title": "Project Id"
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 36,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "project_id"
  ],
  "title": "LocationBody"
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

<a id="model-movebody"></a>

### MoveBody

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `project_id` | sim | string | minLength=1; maxLength=36 |  |
| `folder_id` | não | string / null |  |  |
| `job_ids` | sim | array de string | minItems=1; maxItems=100 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "project_id": {
      "type": "string",
      "maxLength": 36,
      "minLength": 1,
      "title": "Project Id"
    },
    "folder_id": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 36,
          "minLength": 1
        },
        {
          "type": "null"
        }
      ],
      "title": "Folder Id"
    },
    "job_ids": {
      "items": {
        "type": "string"
      },
      "type": "array",
      "maxItems": 100,
      "minItems": 1,
      "title": "Job Ids"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "project_id",
    "job_ids"
  ],
  "title": "MoveBody"
}
```

<a id="model-namebody"></a>

### NameBody

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | sim | string | minLength=1; maxLength=100 |  |

Esquema JSON completo:

```json
{
  "properties": {
    "name": {
      "type": "string",
      "maxLength": 100,
      "minLength": 1,
      "title": "Name"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "name"
  ],
  "title": "NameBody"
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

<a id="model-projectpatch"></a>

### ProjectPatch

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `name` | não | string / null |  |  |
| `description` | não | string / null |  |  |
| `archived` | não | boolean / null |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "name": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 100
        },
        {
          "type": "null"
        }
      ],
      "title": "Name"
    },
    "description": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 4000
        },
        {
          "type": "null"
        }
      ],
      "title": "Description"
    },
    "archived": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ],
      "title": "Archived"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "ProjectPatch"
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
| `partial_count` | não | integer | default=0 |  |
| `completed_count` | não | integer | default=0 |  |
| `cancelled_count` | não | integer | default=0 |  |
| `total_bytes` | não | integer | default=0 | Sum of source file sizes, not current disk usage |
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
    "partial_count": {
      "type": "integer",
      "title": "Partial Count",
      "default": 0
    },
    "completed_count": {
      "type": "integer",
      "title": "Completed Count",
      "default": 0
    },
    "cancelled_count": {
      "type": "integer",
      "title": "Cancelled Count",
      "default": 0
    },
    "total_bytes": {
      "type": "integer",
      "title": "Total Bytes",
      "description": "Sum of source file sizes, not current disk usage",
      "default": 0
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

<a id="model-registrationsettings"></a>

### RegistrationSettings

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `signup_enabled` | sim | boolean |  |  |

Esquema JSON completo:

```json
{
  "properties": {
    "signup_enabled": {
      "type": "boolean",
      "title": "Signup Enabled"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "signup_enabled"
  ],
  "title": "RegistrationSettings"
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
| `permissions` | não | array de string | default=[] |  |
| `engine_access_enabled` | não | boolean | default=false |  |

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

<a id="model-vadparameters"></a>

### VadParameters

| Campo | Obrigatório | Tipo | Padrões/limites | Descrição |
| --- | --- | --- | --- | --- |
| `threshold` | não | number | default=0.5; minimum=0; maximum=1 |  |
| `neg_threshold` | não | number / null | default=null |  |
| `min_speech_duration_ms` | não | integer | default=0; minimum=0; maximum=1000000000 |  |
| `max_speech_duration_s` | não | number / null | default=null | Omitir para duração ilimitada. |
| `min_silence_duration_ms` | não | integer | default=500; minimum=0; maximum=1000000000 |  |
| `speech_pad_ms` | não | integer | default=400; minimum=0; maximum=1000000000 |  |

Esquema JSON completo:

```json
{
  "additionalProperties": false,
  "properties": {
    "threshold": {
      "default": 0.5,
      "maximum": 1,
      "minimum": 0,
      "title": "Threshold",
      "type": "number"
    },
    "neg_threshold": {
      "anyOf": [
        {
          "maximum": 1,
          "minimum": 0,
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Neg Threshold"
    },
    "min_speech_duration_ms": {
      "default": 0,
      "maximum": 1000000000,
      "minimum": 0,
      "title": "Min Speech Duration Ms",
      "type": "integer"
    },
    "max_speech_duration_s": {
      "anyOf": [
        {
          "exclusiveMinimum": 0,
          "maximum": 1000000000.0,
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Omitir para duração ilimitada.",
      "title": "Max Speech Duration S"
    },
    "min_silence_duration_ms": {
      "default": 500,
      "maximum": 1000000000,
      "minimum": 0,
      "title": "Min Silence Duration Ms",
      "type": "integer"
    },
    "speech_pad_ms": {
      "default": 400,
      "maximum": 1000000000,
      "minimum": 0,
      "title": "Speech Pad Ms",
      "type": "integer"
    }
  },
  "title": "VadParameters",
  "type": "object"
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
| `max_new_tokens` | não | integer / null |  | Limite de tokens gerados (contexto do checkpoint integrado: 1024); omitido usa a configuração do worker. |
| `num_beams` | não | integer / null |  | Número de candidatos na busca; omitido usa a configuração do worker. |
| `do_sample` | não | boolean | default=false | Amostrar o próximo token em vez de usar busca determinística. |
| `temperature` | não | number | default=1.0; maximum=2.0; exclusiveMinimum=0.0 | Variação da amostragem; utilizada quando do_sample=true. |
| `top_p` | não | number | default=1.0; maximum=1.0; exclusiveMinimum=0.0 | Fração acumulada de probabilidade na amostragem. |
| `top_k` | não | integer | default=50; minimum=0.0; maximum=100.0 | Quantidade de candidatos na amostragem; zero não limita. |
| `repetition_penalty` | não | number | default=1.0; minimum=0.5; maximum=3.0 | Penalidade de tokens repetidos. |
| `length_penalty` | não | number | default=1.0; minimum=-2.0; maximum=2.0 | Preferência por sequências longas na busca por beams. |
| `no_repeat_ngram_size` | não | integer | default=0; minimum=0.0; maximum=20.0 | Impedir repetição de sequências deste tamanho; zero desativa. |
| `early_stopping` | não | boolean / string | default=false | Critério de parada da busca por beams. |

Esquema JSON completo:

```json
{
  "properties": {
    "max_new_tokens": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 1024.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Max New Tokens",
      "description": "Limite de tokens gerados (contexto do checkpoint integrado: 1024); omitido usa a configuração do worker."
    },
    "num_beams": {
      "anyOf": [
        {
          "type": "integer",
          "maximum": 8.0,
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Num Beams",
      "description": "Número de candidatos na busca; omitido usa a configuração do worker."
    },
    "do_sample": {
      "type": "boolean",
      "title": "Do Sample",
      "description": "Amostrar o próximo token em vez de usar busca determinística.",
      "default": false
    },
    "temperature": {
      "type": "number",
      "maximum": 2.0,
      "exclusiveMinimum": 0.0,
      "title": "Temperature",
      "description": "Variação da amostragem; utilizada quando do_sample=true.",
      "default": 1.0
    },
    "top_p": {
      "type": "number",
      "maximum": 1.0,
      "exclusiveMinimum": 0.0,
      "title": "Top P",
      "description": "Fração acumulada de probabilidade na amostragem.",
      "default": 1.0
    },
    "top_k": {
      "type": "integer",
      "maximum": 100.0,
      "minimum": 0.0,
      "title": "Top K",
      "description": "Quantidade de candidatos na amostragem; zero não limita.",
      "default": 50
    },
    "repetition_penalty": {
      "type": "number",
      "maximum": 3.0,
      "minimum": 0.5,
      "title": "Repetition Penalty",
      "description": "Penalidade de tokens repetidos.",
      "default": 1.0
    },
    "length_penalty": {
      "type": "number",
      "maximum": 2.0,
      "minimum": -2.0,
      "title": "Length Penalty",
      "description": "Preferência por sequências longas na busca por beams.",
      "default": 1.0
    },
    "no_repeat_ngram_size": {
      "type": "integer",
      "maximum": 20.0,
      "minimum": 0.0,
      "title": "No Repeat Ngram Size",
      "description": "Impedir repetição de sequências deste tamanho; zero desativa.",
      "default": 0
    },
    "early_stopping": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "string",
          "const": "never"
        }
      ],
      "title": "Early Stopping",
      "description": "Critério de parada da busca por beams.",
      "default": false
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "VisionGenerationOptions"
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
