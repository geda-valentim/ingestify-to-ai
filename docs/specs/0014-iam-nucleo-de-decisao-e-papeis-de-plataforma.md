# 0014 — IAM: núcleo de decisão, cobertura de rotas e papéis de plataforma

| | |
|---|---|
| **Status** | Em implementação |
| **Autor** | Geda Valentim / Claude |
| **Criada em** | 2026-10-06 |
| **Atualizada em** | 2026-10-07 |
| **Relacionadas** | [0013](0013-iam-da-plataforma.md) (guarda-chuva), [0009](0009-perfis-de-execucao-e-controle-de-acesso.md), [0003](0003-motores-de-execucao-roteamento-e-orcamento.md) |
| **Substituída por** | — |

---

Primeira fatia do IAM (0013 §3). Não introduz tenancy, compartilhamento nem mudança em
API keys: a decisão sobre **dados** continua equivalente a "só o dono". O que muda é que
toda rota passa por um ponto de decisão único, e o poder administrativo deixa de ser
tudo-ou-nada.

## 1. Problema

- **Admin é tudo-ou-nada.** `require_admin` (`api/admin_routes.py:39-50`) protege de
  `/admin/stats` (leitura) a `PATCH /admin/settings` (fecha o cadastro) e
  `POST /admin/jobs/{id}/retry-all-failed` (age em job de qualquer usuário). Não dá para
  ter um operador que só recupera jobs travados nem um auditor só-leitura.
- **Gasto remoto decidido por booleano.** `is_effective_admin` é chamado em 9 pontos de
  API e worker (`routes.py:423,513,870,2881`, `image_routes.py:277`,
  `workers/tasks.py:261,889`, `image_full_tasks.py:229`) e o resultado é congelado em
  `JobDispatch.remote_allowed` no `submit()` (`shared/engines/dispatch.py:177`). O
  dispatcher lê esse flag (`workers/engines/dispatcher.py:264,272,494`); rebaixar um admin
  não afeta um PDF de 300 páginas já enfileirado. E o teto `user_period_limit_usd` só se
  aplica quando `remote_allowed_for = 'all'` (`dispatcher.py:378`): admins gastam sem teto.
- **Autorização sem inventário.** Ownership vive em dependências (`api/deps.py`) e em ~84
  filtros inline. Uma rota nova sem `Depends` adequado fica aberta a qualquer usuário
  autenticado, e nenhum teste falha.

## 2. Objetivo

Toda rota HTTP/WS declara uma permissão de um catálogo fechado e é decidida por
`shared/iam/decide.py`; administração de plataforma é concedida por papéis
(`platform_admin`, `platform_operator`, `platform_auditor`); o uso de engine remota é a
permissão `engines.remote.use`, verificada no momento do dispatch.

### Fora de escopo

- Organizações, `org_id`, compartilhamento, grupos, papéis customizados (0016, 0017).
- Mudança de comportamento de API keys (0015). Nesta fatia uma key continua agindo como o
  dono, **inclusive com papéis de plataforma** — mesmo risco que existe hoje com admin;
  fechado pela 0015, que deve ser a próxima a entrar.
- Remapear as rotas de engine da 0009 (`engine_admin_routes.py`, `engine_control_routes.py`,
  `access_routes.py`). Continuam sob `access_session`/`require_admin_session` e
  `policy.authorize`; esta fatia só as **declara** no inventário.
- Remover o fallback de vínculo pai/filho via Redis em `api/deps.py:129-137` (0016).

## 3. Critérios de aceitação

**Cobertura**
- [ ] CA1. `tests/test_iam_route_coverage.py` enumera `app.routes` e falha se alguma rota
  não tiver exatamente uma declaração de autorização: `require(perm)`,
  `authorized(Model, perm)`, `visible(Model, perm)`, `engine_access(...)` (rotas 0009,
  apenas marcador) ou entrada na allowlist pública (`/`, `/health`, `/auth/login`,
  `/auth/register`, `/auth/refresh`, `/auth/registration-settings`, `/internal/*` com
  identidade de máquina, WS `/live/{id}/stream` com ticket).
- [ ] CA2. Um teste falha se `is_effective_admin` ou `.is_admin` aparecer em `api/` ou
  `workers/` fora de `shared/iam/`, `shared/access/` (0009) e `shared/schemas.py:317`
  (serialização de `/auth/me`). Comparações `user_id ==` para autorizar são rastreadas por
  allowlist explícita de usos não-autorizativos (budget por usuário, idempotência de
  `ImageAnalysisSubmission`), e a allowlist só pode diminuir.
  *Nota de implementação (2026-10-07):* `api/admin_routes.py` não lê mais o flag de admin; a
  regra de bootstrap vem de `shared.iam.decide.is_bootstrap_admin`. `require_admin` e
  `require_admin_session` continuam existindo como guardas das rotas de engine da 0009 (fora de
  escopo, §2) e só deixam de ser dependências próprias no §8 item 7, depois de `enforce`; as
  entradas restantes da allowlist de admin são código da 0009 (CA13). As duas comparações
  `user_id !=` do vínculo key→projeto (`apikey_routes.py`, `projects_api.py`) ficam na allowlist
  como trabalho da **0015**, que muda o que uma key pode fazer.

**Equivalência**
- [ ] CA3. `scripts/iam_equivalence.py`, rodado sobre um dump do MySQL, compara para cada
  par (usuário, job MAIN/projeto/pasta/datalake/key) a decisão legada e a nova para
  `read/update/delete`; qualquer divergência falha. Executado no CI contra a fixture de
  integração e uma vez contra snapshot do dev antes de `enforce`.
  *Implementação:* a lógica (com cópia congelada da regra legada do merge-base) está em
  `backend/shared/iam/equivalence.py`; o CI a roda em `tests/test_iam_equivalence.py`. Não há
  tabela de datalakes neste código ainda, então datalakes não são percorridos. Offline não há
  Redis: os dois lados recebem o mesmo "desconhecido" para o vínculo pai/filho e o dono em cache.
- [ ] CA4. Para cada listagem convertida (`GET /jobs`, `/search`, `/projects`, `/tags`,
  `/datalakes`, `/api-keys`, contagens de `projects_api`), um teste compara o conjunto de
  IDs retornado antes e depois da conversão para usuários com e sem dados.

**Papéis de plataforma**
- [ ] CA5. `platform_operator` recebe `200` em `/admin/stats`, `/admin/jobs/stuck`,
  `/admin/jobs/recover-stuck`, `/admin/jobs/{id}/retry-all-failed`,
  `/admin/broker/unacked*`, `/admin/health/monitoring`, `GET /admin/routing`,
  `/admin/engines/status`; e `403` em `PATCH /admin/settings`, `PUT|DELETE /admin/routing/*`
  `POST /admin/cleanup` e `/admin/iam/*`.
- [ ] CA6. `platform_auditor` recebe `200` em todas as leituras acima e em
  `GET /admin/iam/bindings`, e `403` em toda mutação.
  *Dependência:* `GET`/`PATCH /admin/settings` (e `/auth/registration-settings`) chegam com
  `feat/face-analysis` (`api/platform_settings_routes.py`) e não existem neste branch. Estão
  fixados em `tests/test_iam_route_coverage.py` (`RESERVED_PLATFORM_ROUTES`:
  `platform.settings.read` e `platform.settings.update` + sessão) e são verificados assim que
  existirem; o caso `PATCH /admin/settings → 403` do CA5 é fechado no merge daquele branch.
- [ ] CA7. Ninguém concede a si próprio; ninguém concede papel cujas permissões não possui;
  binding de plataforma exige `expires_at` ≤ 365 dias; revogar tem efeito na próxima
  requisição (sem cache entre requisições).
- [ ] CA8. Bootstrap (`is_admin`/`ADMIN_USER_IDS`) continua passando em toda permissão de
  plataforma, aparece como `bootstrap: true` em `/auth/me`, e cada uso de permissão de
  mutação por bootstrap gera `AdminAudit` com `auth_method` e a permissão exercida.

**Engine remota**
- [ ] CA9. Com rota `remote_allowed_for='admins'`, usuário sem `engines.remote.use` não
  recebe placement remoto; com a permissão, recebe; revogar a permissão no meio de um PDF
  impede placements remotos das páginas ainda não colocadas (vão para o caminho local ou
  ficam em `hold`/`fail` conforme `on_no_engine` da rota).
- [ ] CA10. `user_period_limit_usd` passa a valer também para rotas `admins` (hoje só
  `all`); bootstrap não está isento.
- [ ] CA11. A decisão remota no dispatcher é por placement, não por chunk; o p95 do ciclo
  do dispatcher não piora mais que 5 ms com 1 000 itens em backlog.
  *Como é medido:* a única diferença de trabalho entre um tick em rota `admins` e em rota `all` é
  `_may_use_remote`; o teste mede o tempo gasto nele por tick (50 ticks, 1 000 itens) e exige p95
  ≤ 5 ms (medido ~1 ms em SQLite), além de contar statements SQL (até 2 por usuário por tick).
  Comparar p95 de ticks inteiros (~50 ms cada) mede ruído da máquina da mesma ordem do orçamento.

**Compatibilidade**
- [ ] CA12. Nenhum contrato de rota muda. `/auth/me` só ganha campos; `permissions`
  continua lista plana e passa a incluir as permissões de plataforma.
- [ ] CA13. Toda a suíte da 0009 passa sem alteração.

## 4. Solução proposta

### 4.1 Fluxo

```
request → get_current_active_user (inalterado: JWT ou X-API-Key)
        → dependência declarada na rota
            require("platform.settings.update")        → decide(principal, perm, PLATFORM)
            authorized(Job, "jobs.read")                → carrega o recurso pelo path,
                                                          decide(principal, perm, recurso)
            visible(Job, "jobs.read")                   → devolve um predicado SQLAlchemy
                                                          para a listagem aplicar
        → handler (inalterado)

worker dispatcher, ao escolher executor remoto:
        decide(dispatch.user_id, "engines.remote.use", PLATFORM)
        → negado: trata como "sem engine remota" para aquele item
```

### 4.2 Catálogo de permissões (`shared/iam/catalog.py`)

Fechado, em código, exposto em `GET /iam/permissions`. Nesta fatia só existem os níveis
`platform` e `owner` (dados do próprio usuário). As famílias de dados já usam os nomes
definitivos para que 0016/0017 só ampliem quem as recebe.

| Família | Permissões | Quem tem nesta fatia |
|---|---|---|
| Dados | `jobs.read`, `jobs.create`, `jobs.update`, `jobs.retry`, `jobs.cancel`, `jobs.delete`, `projects.read/create/update/delete`, `folders.read/create/update/delete`, `datalakes.read/create/update/delete/use`, `datalake_exports.retry`, `api_keys.read/manage`, `search.query`, `documents.convert`, `audio.transcribe`, `images.analyze`, `live.sessions.create` | O dono do recurso (criação: todo usuário ativo) |
| Plataforma | `platform.stats.read`, `platform.jobs.read` (metadados de jobs de todos: id, status, filename, user_id), `platform.jobs.recover`, `platform.jobs.cleanup`, `platform.monitoring.read`, `platform.broker.requeue`, `platform.settings.read`, `platform.settings.update`, `platform.routing.read`, `platform.routing.update`, `platform.audit.read`, `engines.remote.use` | Papéis de plataforma (§4.3) |
| IAM | `iam.bindings.read`, `iam.bindings.manage` | `platform_admin`, auditor (só `read`) |
| Engines (0009) | inalterado; só referenciado | grants da 0009 |

`platform.jobs.read` é explícito porque `/admin/jobs/stuck` expõe nomes de arquivos de
qualquer usuário (`admin_routes.py:99-130`); quem a recebe vê metadados entre usuários.

### 4.3 Papéis gerenciados

Definidos em código (`catalog.py`), não em tabela: mudar um papel é um deploy revisado,
e não existe segunda fonte de verdade. Papéis customizados ficam para a 0017.

| Papel | Permissões |
|---|---|
| `platform_admin` | Todas as `platform.*`, `iam.*`, `engines.remote.use` |
| `platform_operator` | `platform.stats.read`, `platform.jobs.read`, `platform.jobs.recover`, `platform.monitoring.read`, `platform.broker.requeue`, `platform.routing.read` |
| `platform_auditor` | Todas as `platform.*.read`, `platform.audit.read`, `iam.bindings.read` |
| `remote_engine_user` | `engines.remote.use` |

Bootstrap equivale a `platform_admin` e não é representado por binding.

### 4.4 Algoritmo

```
decide(principal, permission, resource) -> Decision{allow, status, via, binding_id}

1. Principal: usuário ativo (key → seu dono; comportamento de key inalterado nesta
   fatia). Ausente/inativo → 401/403. Ator nulo nunca é admin.
2. Permissão de engines 0009 → fora deste serviço (rota continua em policy.authorize).
3. Permissão de plataforma/IAM:
     bootstrap                                   → ALLOW (via=bootstrap, auditado se mutação)
     binding ativo cujo papel contém permission → ALLOW (via=binding)
     senão                                       → 403 (a rota não é segredo)
4. Permissão de dados:
     resolver o dono do recurso exatamente como hoje (resolve_owned_job, owned_*_or_404,
     incluindo o vínculo pai/filho via Redis já existente)
     dono == principal                           → ALLOW
     senão                                       → 404
```

O passo 4 reproduz o legado de propósito: não há novo caminho de leitura de dados nesta
fatia. Bootstrap não lê dados alheios — igual a hoje, em que `get_owned_job` não tem
exceção para admin.

### 4.5 Listagens: o predicado como ponto de extensão

`visible(Model, perm)` devolve o predicado que a listagem aplica no lugar do filtro inline:

```python
# antes (routes.py:2547)
q = db.query(Job).filter(Job.user_id == current_user.id, ...)
# depois
q = db.query(Job).filter(scope.predicate, ...)    # scope = Depends(visible(Job, "jobs.read"))
```

Nesta fatia `scope.predicate` é literalmente `Model.user_id == me`, então SQL, índices e
planos de execução não mudam (CA4). É o ponto onde 0016 acrescenta `org_id` e 0017 os
ramos de compartilhamento, sem reabrir as ~84 consultas.

### 4.6 Engine remota no dispatcher

- `remote_allowed_for` mantém o ENUM `('admins','all')` (`models.py:439`), sem ALTER.
  `admins` passa a significar "exige `engines.remote.use`". UI e docs renomeiam o rótulo
  para "Restrito".
- No `submit()`, `remote_allowed` continua sendo gravado (otimização: evita considerar
  executores remotos para quem nunca teve a permissão), agora calculado por
  `decide(..., "engines.remote.use")` em vez de `is_effective_admin`.
- No dispatcher, ao escolher um executor `remote`, para rotas `admins`, revalidar com
  `decide(dispatch.user_id, "engines.remote.use")`. Negado → o item é tratado como se não
  houvesse executor remoto, e o fluxo existente de `on_no_engine`/fallback local decide.
  Uma consulta indexada por placement remoto; nenhuma por chunk.
- `user_period_limit_usd` passa a valer para qualquer rota com executor remoto
  (`dispatcher.py:378` perde o `route.remote_allowed_for == "all"`).
- Os 9 pontos que chamam `is_effective_admin` passam a chamar
  `iam.can(user, "engines.remote.use")`. `routes.py:513` (capabilities de áudio) usa o
  mesmo, para a UI não oferecer remoto a quem não pode.
- Quem é o "iniciador": `JobDispatch.user_id`, que hoje é o dono do job (retry em
  `routes.py:2881` usa `current_user`, que nesta fatia só pode ser o dono). A 0017 precisa
  separar iniciador e dono quando houver retry por terceiros.
- Admissão de efeito e epoch da 0009 não são tocados: `engines.remote.use` decide se o
  item **pode** ir para remoto; operar a engine continua sob a 0009.

### 4.7 Mapeamento das rotas administrativas

| Rota | Hoje | Depois |
|---|---|---|
| `GET /admin/stats` | `require_admin` | `platform.stats.read` |
| `GET /admin/jobs/stuck` | `require_admin` | `platform.jobs.read` |
| `POST /admin/jobs/recover-stuck`, `POST /admin/jobs/{id}/retry-all-failed` | `require_admin` | `platform.jobs.recover` |
| `POST /admin/cleanup` | `require_admin` | `platform.jobs.cleanup` (apaga jobs antigos de todos) |
| `GET /admin/health/monitoring`, `GET /admin/broker/unacked` | `require_admin` | `platform.monitoring.read` |
| `POST /admin/broker/unacked/{tag}/requeue` | `require_admin` | `platform.broker.requeue` |
| `GET /admin/settings` | `require_admin` | `platform.settings.read` |
| `PATCH /admin/settings` | `require_admin` | `platform.settings.update` + sessão JWT |
| `GET /admin/routing`, `GET /admin/engines/status` | `require_admin` | `platform.routing.read` |
| `PUT|DELETE /admin/routing/{feature}` | `require_admin_session` | `platform.routing.update` + sessão JWT |
| Rotas de engine (`/admin/gpus`, `/engines/*`, `/execution-profiles/*`, `/access/*`) | 0009 | inalterado; marcador `engine_access` no inventário |

"Sessão JWT" é a regra atual de `require_admin_session` (sem `X-API-Key`), mantida como
parâmetro `require(perm, session=True)`. A 0015 a torna regra geral para `platform.*`.

### 4.8 Dados (`shared/iam/models.py`)

Uma tabela nova, separada da 0009 (0013 §4.2):

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | UUID | |
| `subject_type` | `user` \| `service_principal` | `group` entra na 0017 |
| `subject_id` | String(80) | FK lógica; validada na escrita |
| `role` | String(64) | chave de papel gerenciado em `catalog.py` |
| `scope_type`, `scope_id` | `platform`, NULL | outros escopos entram na 0016/0017 |
| `granted_by` | FK `users.id` | |
| `expires_at` | DateTime NOT NULL | ≤ 365 dias para escopo `platform` |
| `revoked_at`, `revoked_by` | | |
| `version` | Integer | optimistic locking |
| `created_at` | | |

Índices: `(subject_type, subject_id, revoked_at)`, `(scope_type, scope_id)`.
Migration aditiva (só `CREATE TABLE`), aplicada pelo mesmo mecanismo da 0009
(`shared/access/migration.py`), com marcador em `app_migrations`. Reversível:
`DROP TABLE` após `IAM_MODE=off`; nenhum dado pré-existente é alterado.

**Chaves Redis:** nenhuma nova. Nenhuma decisão desta fatia lê Redis além do vínculo
pai/filho que `resolve_owned_job` já usa hoje (removido na 0016).

### 4.9 API

| Método | Rota | Permissão |
|---|---|---|
| GET | `/auth/me` | sessão — **+** `bootstrap`, `platform_roles[]`; `permissions` inclui as de plataforma |
| GET | `/iam/permissions` | sessão — catálogo e papéis gerenciados |
| POST | `/iam/check` | sessão — `[{permission}]` → `[{allowed}]` só para permissões de plataforma nesta fatia |
| GET | `/admin/iam/bindings` | `iam.bindings.read` |
| POST | `/admin/iam/bindings` | `iam.bindings.manage` + sessão JWT; corpo `{subject_type, subject_id, role, expires_at}` |
| POST | `/admin/iam/bindings/{id}/revoke` | `iam.bindings.manage` + sessão JWT; corpo `{version}` |

Erros: `401` sessão; `403` permissão de plataforma ausente; `404` recurso de dados fora de
alcance (igual hoje); `409` versão; `422` papel desconhecido, autoconcessão, papel acima do
concedente ou `expires_at` inválido.

`access_session` (0009, `api/access_deps.py:21`) continua considerando **apenas** os grants
da 0009: um binding `platform_operator` não abre as rotas de engine/perfil. Isso é testado.

### 4.10 Frontend

- `app/admin/layout.tsx` já entra com `permissions.length > 0`; cada item de navegação
  passa a exigir sua permissão (`platform.stats.read` → Estatísticas, etc.).
- Página **Admin → Acesso à plataforma**: lista bindings, conceder (usuário, papel,
  validade), revogar. Reaproveita componentes da UI de grants da 0009.
- Rótulo de rota "Somente admins" → "Restrito (exige permissão de engine remota)".

### 4.11 Rollout

`IAM_MODE` = `off` | `shadow` | `enforce`, padrão `off`.

1. Tabela + catálogo + `decide()` + testes unitários. `off`.
2. Conversão das rotas para `require`/`authorized`/`visible` com `IAM_MODE=shadow`: nas
   dependências **por ID** e em `require`, as duas decisões rodam e o legado responde;
   divergência gera log `iam_shadow_divergence` e métrica. Listagens são convertidas já
   com o predicado equivalente (CA4) — não há shadow de listagem.
3. CA3 contra snapshot do dev sem divergências → `enforce`.
4. Só então conceder os primeiros bindings de plataforma.
5. Remover `require_admin`, `require_admin_session` (como dependências próprias) e o
   import de `is_effective_admin` fora de `shared/iam/` (CA2).

**Escopo de `off`:** "`off` = legado" vale para as decisões de rota da API. No dispatcher, a
revalidação de `engines.remote.use` a cada placement (§4.6, CA9) e o teto CA10 **não dependem de
`IAM_MODE`**: em `off` a decisão é a regra legada (`is_effective_admin` do dono), porém tomada no
placement e não congelada no submit. Ambos só reduzem acesso; são o defeito que esta spec corrige.

Rollback: `IAM_MODE=off` volta a `require_admin`. Bindings ficam inertes; quem só tinha
papel de plataforma perde o acesso, o que **reduz** acesso (nunca amplia).

## 5. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Papéis em tabela desde já | Sem papéis customizados nesta fatia, tabela vira segunda fonte de verdade editável por SQL |
| Reaproveitar `access_role_grants` | Quebra `active_grant`/`navigation`/`access_session` da 0009 (0013 §4.2) |
| Decidir engine remota só no `submit()` | Revogação não alcança itens enfileirados; é o defeito atual |
| Decidir engine remota por chunk | Custo sem ganho: placement é a unidade de efeito |
| Shadow também nas listagens | Autorização está dentro das consultas; rodar duas e comparar dobra carga e não testa semântica nova (não há) |
| Já restringir keys nesta fatia | Mistura uma quebra de compatibilidade com uma refatoração; 0015 isola a quebra |

## 6. Impactos

- **Compatibilidade:** nenhum contrato muda. Admins atuais seguem como bootstrap.
  Mudança de comportamento intencional: `user_period_limit_usd` passa a valer também em
  rotas `admins` (CA10) — registrar no `CHANGELOG.md`.
- **Performance:** uma consulta de bindings por requisição em rotas `platform.*`; dados
  sem consulta extra. Dispatcher: uma consulta por placement remoto em rota `admins`.
- **Segurança:** menor privilégio para operação; autoconcessão bloqueada; revogação
  imediata. Risco residual conhecido: key de usuário com papel de plataforma age com esse
  papel até a 0015.
- **Operação:** env `IAM_MODE`; sinal de shadow = linha de log estruturada
  `iam_shadow_divergence route=… permission=… subject=… legacy=… iam=…` (o projeto não tem
  facilidade de métricas; os campos são os rótulos de um futuro
  `iam_shadow_divergence_total{route,permission}`). Em rotas de dados por ID o legado e o IAM
  resolvem o dono pelo mesmo `shared.iam.ownership`, então shadow não diverge ali por
  construção: a evidência de equivalência de dados é o CA3 (cópia congelada da regra legada).
  `AdminAudit` para bindings e mutações por bootstrap.
- **Custo:** nenhum.

## 7. Plano de testes

- **Unitários:** matriz papel × permissão; autoconcessão; papel acima do concedente;
  expiração UTC; revogação; bootstrap; ator nulo.
- **Cobertura:** CA1 e CA2.
- **Equivalência:** CA3 (script) e CA4 (listagens).
- **Contrato API:** CA5–CA8 por papel; `access_session` não abre com binding IAM.
- **Dispatcher:** CA9–CA11 com engine remota simulada, incluindo revogação entre
  placements de um PDF multipágina.
- **Regressão 0009:** CA13.

## 8. Plano de implementação

- [ ] 1. `shared/iam/catalog.py`, `models.py`, `decide.py` + unitários; migration aditiva.
- [ ] 2. Dependências `require`/`authorized`/`visible` + teste de cobertura (CA1) com
  allowlist inicial = rotas ainda não convertidas, que só pode diminuir.
- [ ] 3. Converter rotas administrativas (§4.7) e `/admin/iam/*`.
- [ ] 4. Converter rotas de dados por ID e listagens (equivalentes), por arquivo de rota.
- [ ] 5. Engine remota: `submit()`, dispatcher e teto por usuário.
- [ ] 6. Frontend: navegação por permissão e página de acesso à plataforma.
- [ ] 7. `shadow` → CA3 no snapshot → `enforce`; remoção do legado (CA2).

## 9. Questões em aberto

- [x] `platform_operator` pode `POST /admin/cleanup`? → **Decisão (2026-10-06):** não;
  `platform.jobs.cleanup` existe só em `platform_admin` (destrutivo e entre usuários).
- [x] Bootstrap continua sem teto `user_period_limit_usd`? → **Decisão (2026-10-06):** não
  (CA10); emergência é acesso, não orçamento.
- [x] Bindings de plataforma precisam de aprovação por segundo admin? → **Decisão
  (2026-10-06):** não nesta fatia; auditoria basta.
