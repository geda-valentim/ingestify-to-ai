# Ativar perfis de execução e acesso granular

Verificado contra o código em **2026-10-07**. Use junto do [bootstrap de controle](engine-control-bootstrap.md). O código é
opt-in; este runbook não inicia engines/modelos nem cria grants automaticamente.

> **Desde a [spec 0018](../specs/0018-iam-convergencia-do-rbac-abac-de-engines.md)** os grants
> de engines são `iam_bindings` da família `engines`, administrados em **Admin → Acesso**
> (`/admin/access`) e por `/admin/iam/bindings`; o flag é `IAM_MODE`. Instalações que já
> rodam a 0009 seguem a [seção 6](#6-convergência-no-iam-spec-0018) antes de atualizar.
> Uma instalação que liga engines pela primeira vez aplica, **na seção 1 e antes de ligar
> qualquer flag**, a migração da 0009 e depois a da 0014+0018; só então segue as seções 2–5.
> Com `IAM_MODE` diferente de `off` ou engines ligado, a API não sobe sem as duas.

## 1. Preparação e migração

Registre backup do SQL e as revisões atuais de runtime, operações incertas,
locks, gates e reservas. Aguarde operações ativas ou preserve explicitamente a
exposição antes da janela. Impeça novos escritores durante a troca de release.
Não faça `docker compose down` em toda a instalação para isso.

A release acrescenta origem/hash ao runtime e autores de cancelamento/recovery.
Essas colunas precisam ser migradas **mesmo com `ENGINE_ACCESS_ENABLED=false`**
quando o controle da 0007 está ativo. A API falha no startup se faltarem as colunas
necessárias; não tenta alterar automaticamente um banco existente.

Com o código desta release disponível, execute a migração explícita. Use o
conjunto real de arquivos Compose da instalação, incluindo seus overlays locais:

```bash
docker compose run --rm --no-deps api python -c \
  'from shared.database import engine; from shared.access.migration import upgrade; upgrade(engine)'
```

Se a instalação já usa Alembic com a árvore corretamente estampada, a revisão é
`f0b40009c4d3`, depois de `c7e10007a1f0`. A função direta é idempotente e evita
inferir/stampar migrações históricas da instalação.

Em seguida, ainda antes de definir `IAM_MODE`/`ENGINE_ACCESS_ENABLED` na seção 2, aplique a
migração do IAM (0014) e a convergência da 0018 (detalhes na [seção 6.2](#62-migração)).
O boot valida esse esquema sempre que `IAM_MODE` não é `off` ou engines está ligado; num
banco existente o `create_all` não cria as tabelas `iam_*`, então pular este passo deixa a
API sem subir na seção 2:

```bash
docker compose run --rm --no-deps api python -c \
  'from shared.database import engine; from shared.iam import migration; migration.upgrade(engine); migration.upgrade_0018(engine)'
```

Com Alembic estampado, a revisão é `d4e80018a2b6` (head único).

A migração cria biblioteca, revisões, políticas, grants, epoch, consumidores,
admissões e contexto legado. Preserva registros antigos e não infere consumidores,
ambiente confiável, publicação ou estado aplicado. Downgrade destrutivo é recusado
para preservar auditoria e exposição.

## 2. Rollout coordenado

Defina no `.env`:

```dotenv
ENGINE_CONTROL_ENABLED=true
IAM_MODE=enforce
# ENGINE_ACCESS_ENABLED vazio: segue IAM_MODE (só `enforce` liga engines).
ENGINE_ACCESS_ENABLED=
# Opcional; só para a CLI bootstrap registrada abaixo:
ENGINE_INSTALLATION_PRINCIPAL_ID=installation:dev
```

`IAM_MODE=enforce` também liga as decisões de plataforma da
[0014](../specs/0014-iam-nucleo-de-decisao-e-papeis-de-plataforma.md); rode antes o gate
dela, `docker compose run --rm --no-deps api python -m shared.iam.equivalence` (fora do
container, `python scripts/iam_equivalence.py`). Para ligar só engines, mantendo a plataforma no legado,
use `IAM_MODE=off` com `ENGINE_ACCESS_ENABLED=true` (alias depreciado, ver seção 6.3).

`docker-compose.engine-control.yml` repassa as opções à API e aos workers de
controle/remote e demais serviços relacionados. `.env` sozinho não injeta uma
variável num container já existente. Recrie os serviços afetados com o overlay
em uso e mantenha as escalas originais; não suba workers de áudio/live só por
ativar esta biblioteca. Confirme o environment final sem imprimir segredos.

O overlay mudou nesta release. Instalações com agente local que verifica hash
de manifests precisam registrar novamente o conjunto real de Compose antes de
operar. O `manifest_hash` anterior não deve ser reaproveitado se seus arquivos
mudaram. Siga a seção de registro no runbook de controle, mantendo identidade,
permissões de arquivos e inicialização via serviço já configuradas.

Verifique saúde da API, heartbeat do worker-control/watchdog e agente local.
O watchdog permanece necessário para exposição paga; a feature não remove
readiness, orçamento, modelo aprovado, manifest, UUID de GPU ou gates da 0007.

## 3. Configuração inicial pelo bootstrap

Tudo abaixo fica em **Admin → Acesso** (`/admin/access`): abas Concessões, Políticas,
Atributos de engine, Recursos e Principais de instalação.

1. Na aba Atributos de engine, classifique o ambiente das engines que receberão grants.
2. Crie um perfil na biblioteca, publique a revisão e faça o primeiro vínculo de
   bootstrap. Isso registra os recursos canônicos sem executar nem reservar custo.
3. Em consumidores, declare todas as engines/features afetadas por cada serviço
   e GPU, incluindo o worker genérico. Marque qualificado somente após conferir
   o inventário e os usos reais. Até isso acontecer, atuação delegada falha fechada.
4. Crie uma política pequena, começando por uma engine de desenvolvimento e os
   modelos/hosts/UUIDs necessários. Escolha valores explícitos de CPU e memória.
5. Na aba Concessões, conceda `observer` com validade curta e confira que outra engine/produção,
   detalhes, histórico e SSE não aparecem. Depois conceda configurador/operador
   apenas com ações necessárias. Um grant completo deve cobrir cada decisão.
6. Para `access_admin`, defina o envelope de delegação; não conceda execução
   implicitamente. Políticas/grants não alteram o bootstrap atual.

Não use propriedade de projeto para qualificar um worker compartilhado. Não
remova consumidores da lista apenas para permitir uma operação negada.

## 4. CLI de instalação opcional

Registre o ID pelo endpoint bootstrap `POST /admin/access/installation-principals`
com corpo `{"id":"installation:dev"}` e sessão JWT. O ID deve corresponder ao
environment da API/worker em que a CLI roda; prefixo `installation:` e tamanho
máximo de 36 caracteres. O registro não concede sessão humana nem altera usuários.

```bash
docker compose exec api python scripts/engines.py \
  --installation-principal installation:dev list --json
```

Para comandos que precisam das chaves privadas, use worker-remote conforme a
instalação, mantendo a opção antes do subcomando. Usuários delegados usam os
endpoints de planos com sua sessão; não recebem acesso de SO/CLI por um grant.

Deploy CLI de engine já gerenciada continua recusado: use a operação pela API.
Um deploy bootstrap em engine não gerenciada gera admissão durável e fence dos
recursos, sem segurar transação durante a rede. Se o processo cair, ou o principal
for revogado durante o build, conserve os locks e a admissão incerta. Observe o
estado do provedor e custos com uma autoridade administrativa vigente antes de
confirmar/liberar essa exposição. Não repita o deploy nem limpe fences por um
retry automático. O diagnóstico está no `AdminAudit` e
`access_effect_admissions`; admissão CLI tem geração zero e ID próprio.

Desative o principal com `PUT /admin/access/installation-principals/{id}` usando
`version` e `active:false`; isso incrementa o epoch. Alterações de usuário pelo
endpoint `/access/subjects/{id}/state` também comparam o estado esperado e atualizam
epoch/auditoria. `make_admin.py` continua sendo o bootstrap explícito da instalação
e registra sua promoção no epoch quando a funcionalidade está ativa.

## 5. Canário e rollback

Execute primeiro um fluxo sem custo: biblioteca → publicação → vínculo → leitura
scopada. Confira que aplicado/observado não mudaram. Em seguida, numa janela
controlada, teste a prévia e uma operação da engine selecionada, com limites e
confirmação explícitos. Verifique revogação antes de novo passo, cancelamento,
recovery por outro ator e SSE encerrado. Infraestrutura real não foi executada
pelos testes automatizados desta entrega.

Para desativar delegação, defina `ENGINE_ACCESS_ENABLED=false` (a alavanca de
emergência: vence `IAM_MODE` e volta engines a só bootstrap) e recrie API e
executores de forma coordenada. O bootstrap conserva os controles anteriores;
a biblioteca/IAM deixa de aceitar uso. Desabilitar não concede um grant pendente:
operações que já guardam autoridade delegada revalidam o ator e não ganham poderes
de bootstrap. Preserve watchdog/exposição e a migração aditiva. Voltar código
anterior exige revisão específica da compatibilidade; não apague tabelas nem
locks/reservas para fazer rollback.

## 6. Convergência no IAM (spec 0018)

A 0018 move o armazenamento e a administração dos grants da 0009 para `iam_bindings`,
sem mudar a decisão: `policy.authorize`, delegação, epoch, admissão de efeito e fencing
continuam os mesmos. `access_role_grants` vira **espelho só-escrita** para rollback.
Única mudança de comportamento: autoconcessão de papel de engines é recusada
(`422 SELF_GRANT`).

### 6.1 Deploy em uma etapa

**Pré-checagem antes do deploy.** Antes da 0018, `ENGINE_ACCESS_ENABLED` ausente valia
`false`; agora, ausente ou vazio segue `IAM_MODE` (seção 6.3). Uma instalação que já roda
`IAM_MODE=enforce` (plataforma da 0014) **sem** a variável definida passa a ter o
enforcement de engines ligado só por este deploy, e todo grant não revogado e não
expirado em `access_role_grants`, copiado para `iam_bindings`, volta a valer. Nesse caso,
antes do deploy, ou fixe `ENGINE_ACCESS_ENABLED=false` no `.env`, ou revise os grants
ativos e revogue os que devem continuar desligados:

```sql
SELECT id, user_id, role, expires_at FROM access_role_grants
WHERE revoked_at IS NULL AND expires_at > UTC_TIMESTAMP();
```

As fatias 1 e 2 da 0018 vão juntas num único deploy. Não deixe pods antigos servindo
`/admin/access/grants` em paralelo com os novos: o código antigo grava só em
`access_role_grants`, e a revogação dele só volta aos bindings na próxima reconciliação.
Impeça novos escritores (concessões, revogações, políticas) durante a troca, como na
seção 1, e recrie API, workers e beat juntos.

### 6.2 Migração

Faça backup do SQL. Com o código da release disponível, aplique a migração explícita
(ela exige as migrações 0009 e 0014 já aplicadas, **inclusive numa instalação só com IAM
de plataforma e engines desligado**: `upgrade_0018` recusa com "Apply the 0009 access
migration before 0018"; a primeira chamada abaixo é idempotente):

```bash
docker compose run --rm --no-deps api python -c \
  'from shared.database import engine; from shared.iam import migration; migration.upgrade(engine); migration.upgrade_0018(engine)'
```

Com Alembic estampado, a revisão é `d4e80018a2b6`, depois de `03e70014b8c5` (head único).

A migração, em `shared/iam/migration.py`:

1. **DDL**: adiciona a `iam_bindings` as colunas `permissions`, `condition_ref`,
   `delegation` e `parent_id` (só as ausentes), as FKs `fk_iam_bindings_condition_ref` e
   `fk_iam_bindings_parent` e o índice `ix_iam_bindings_subject_role`;
2. **dados**, numa transação própria sob o lock do epoch da 0009: copia cada linha de
   `access_role_grants` para um binding com o **mesmo id** (pais antes de filhos;
   `revoked_by` vem da última auditoria de revogação), reconcilia, valida e incrementa o
   epoch se algo mudou;
3. grava o marcador `0018_engine_bindings` em `app_migrations` por último.

A validação aborta a migração se um grant tiver pai ou revisão de política inexistente,
papel fora dos seis da 0009 ou permissões vazias; corrija o dado pelo código antigo e
repita.

A **reconciliação** roda de novo a cada `upgrade_0018`, a cada boot da API (`init_db`) e no
`worker_init` de todo worker Celery com engines ligado, independentemente do marcador, e
**só restringe**: copia grants ausentes, aplica `revoked_at` e o menor `expires_at` de
qualquer das duas tabelas e o maior `version`. Se falhar, a API e o worker não sobem.
Com `IAM_MODE` diferente de `off` (inclusive `shadow`, com engines desligado) ou com engines
ligado, a API recusa o boot enquanto as colunas, FKs e índice da 0018 não existirem.

### 6.3 Flag

`IAM_MODE` governa engines; `engine_access_enabled` é derivado:

| `ENGINE_ACCESS_ENABLED` | Engines ligado |
|---|---|
| vazio ou ausente | só com `IAM_MODE=enforce` (`shadow` não liga) |
| `true` / `false` | esse valor, com aviso de depreciação no boot |

`ENGINE_ACCESS_ENABLED=true` (como no dev) continua ligando engines com `IAM_MODE=off`.
`ENGINE_ACCESS_ENABLED=false` explícito continua sendo a alavanca de emergência.
Atenção: com `IAM_MODE=enforce`, uma instalação com engines desligado por **ausência** da
variável (inclusive uma que nunca ligou engines ou que o desligou apagando a linha do
`.env`) passa a exigir o esquema da 0009 no boot e liga o enforcement de engines, com os
grants ativos que restarem; revise-os (seção 6.1), conceda antes os papéis de engines
necessários ou fixe `ENGINE_ACCESS_ENABLED=false`.

Todo processo que importa `shared.access.policy` (api, worker, worker-audio,
worker-vision, worker-remote, worker-dispatch, worker-control, worker-control-watchdog,
beat) recebe os dois valores pelos compose files e registra no boot
`engine_access_enabled=<valor> (<origem>)`. Confira essa linha em todos depois do deploy,
passando os mesmos `-f` da instalação (o `worker-control` só existe com o overlay de
controle; sem ele, tire-o da lista):

```bash
docker compose -f docker-compose.yml -f docker-compose.engine-control.yml \
  logs api worker worker-control beat 2>&1 | grep 'engine_access_enabled='
```

### 6.4 Verificação

Depois da migração, antes de reabrir as escritas:

```sql
-- 1. marcador gravado
SELECT name, applied_at FROM app_migrations WHERE name = '0018_engine_bindings';

-- 2. todo grant tem binding de mesmo id com sujeito, papel, condição, revogação,
--    pai, validade e versão iguais ou mais restritivos (esperado: 0 linhas). Não compara
--    permissões nem delegação (JSON): essas a migração/reconciliação já confere campo a
--    campo (`verify_engine_bindings`) e o gate de equivalência abaixo prova nas decisões.
SELECT g.id
FROM access_role_grants g
LEFT JOIN iam_bindings b ON b.id = g.id
WHERE b.id IS NULL
   OR b.subject_type <> 'user' OR b.subject_id <> g.user_id OR b.role <> g.role
   OR b.condition_ref IS NULL OR b.condition_ref <> g.policy_revision_id
   OR COALESCE(b.parent_id, '') <> COALESCE(g.parent_id, '')
   OR (g.revoked_at IS NOT NULL AND b.revoked_at IS NULL)
   OR b.expires_at IS NULL OR b.expires_at > g.expires_at
   OR b.version < g.version;

-- 3. bindings de plataforma sem colunas de engines (esperado: 0 linhas)
SELECT id, role FROM iam_bindings
WHERE role IN ('platform_admin', 'platform_operator', 'platform_auditor', 'remote_engine_user')
  AND (permissions IS NOT NULL OR condition_ref IS NOT NULL
       OR delegation IS NOT NULL OR parent_id IS NOT NULL);
```

A lista de papéis de plataforma da consulta 3 é a de `shared/iam/catalog.py` (`ROLES`);
confira se mudou. Em seguida rode o gate de equivalência (spec 0018 CA4), que compara as
decisões da 0009 lendo `access_role_grants` (cópia congelada do leitor anterior) e
`iam_bindings`, para todos os usuários. Precisa sair com `0 divergences` (código 0):

```bash
docker compose run --rm --no-deps api python -m shared.iam.engine_equivalence
```

Fora do container, `python scripts/iam_engine_equivalence.py --db-url ...` faz o mesmo.
Por fim, em **Admin → Acesso → Concessões**, filtre a família Engines e confira que os
grants vigentes aparecem com a mesma condição e validade.

### 6.5 Rollback

O espelho torna o rollback seguro: toda concessão e revogação de papel de engines grava,
na mesma transação, a linha de mesmo id em `access_role_grants` (falha do espelho aborta
a escrita). Portanto:

- **Voltar o código** para antes da 0018 não reabre revogações: o código antigo lê
  `access_role_grants`, que já reflete o estado atual. Enquanto o código antigo estiver
  no ar, papéis de engines só se concedem e revogam por `/admin/access/grants`: a rota
  antiga `/admin/iam/bindings` pode listar bindings de engines, mas revogar por ela não
  alcança `access_role_grants`, que é o que o código antigo decide. Ao reimplantar a 0018, a reconciliação do boot traz
  essas mudanças para os bindings, sempre pelo lado mais restritivo.
- **Desfazer a migração** (`downgrade_0018`, ou `alembic downgrade 03e70014b8c5`): sob o
  lock do epoch aplica em `access_role_grants` o mais restritivo das duas tabelas, insere
  os bindings de engines ausentes (recusa se algum não puder virar grant), apaga os
  bindings de engines e o marcador e remove FKs, índice e colunas. O downgrade da 0014
  continua recusado enquanto houver binding fora dos papéis de plataforma.
- **Desligar engines** sem voltar código: `ENGINE_ACCESS_ENABLED=false` (seção 5).

`access_role_grants` não é apagada nesta release; a remoção fica para uma spec futura.

### 6.6 Aliases depreciados

`GET|POST /admin/access/grants` e `POST /admin/access/grants/{id}/revoke` continuam com o
contrato da 0009 (corpo `{code}`, re-revogação aceita, listagem filtrada pelo envelope),
agora sobre `iam_bindings` e só para papéis de engines, e estão marcados `deprecated` no
OpenAPI. O frontend já não os chama. Migre automações para `/admin/iam/bindings`:

| Alias | Rota unificada |
|---|---|
| `GET /admin/access/grants` | `GET /admin/iam/bindings?include_inactive=true` (campo `family`) |
| `POST /admin/access/grants` com `user_id`, `role`, `policy_revision_id`, `permissions`, `delegation`, `expires_at` | `POST /admin/iam/bindings` com `subject_type: "user"`, `subject_id`, `role`, `condition_ref`, `permissions`, `delegation`, `expires_at` |
| `POST /admin/access/grants/{id}/revoke` | `POST /admin/iam/bindings/{id}/revoke` (já revogado → `409 ALREADY_REVOKED`) |

A rota unificada responde `{code, message}` e usa os códigos da tabela da
[spec 0018 §4.5](../specs/0018-iam-convergencia-do-rbac-abac-de-engines.md#45-api). As
duas exigem sessão JWT; para engines, também na leitura.

## Registro do dev (2026-10-06)

PR #45 mergeado; migração 0009 aplicada após backup consistente do SQL. Controle
e acesso habilitados na API e executores, com frontend reconstruído/reiniciado.
Host `dev-ingestify` mantém sua identidade; manifests e imagens registrados foram
atualizados. Cinco engines foram classificadas como desenvolvimento pela API.
Áudio/live continuam com zero réplicas e o worker genérico com duas.
Biblioteca, IAM, capabilities e documentação pública foram verificados.
Não foram criados grants delegados nem executados deploys pagos nessa ativação.
