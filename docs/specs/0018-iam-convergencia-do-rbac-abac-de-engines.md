# 0018 — IAM: convergência do RBAC/ABAC de engines (0009) no IAM

| | |
|---|---|
| **Status** | Em implementação |
| **Autor** | Geda Valentim / Claude |
| **Criada em** | 2026-10-07 |
| **Atualizada em** | 2026-10-07 |
| **Relacionadas** | [0009](0009-perfis-de-execucao-e-controle-de-acesso.md) (substituída no armazenamento e administração de grants), [0013](0013-iam-da-plataforma.md) (**emenda §4 regras 1–2**, ver §4.7), [0014](0014-iam-nucleo-de-decisao-e-papeis-de-plataforma.md) |
| **Substituída por** | — |

---

## 1. Problema

A 0014 deixou um ponto de decisão e de aplicação único, mas **dois planos de
concessão** convivem:

| Aspecto | 0009 | 0014 |
|---|---|---|
| Armazenamento | `access_role_grants` (+ `access_policies`/`access_policy_revisions`) | `iam_bindings` |
| API | `/admin/access/grants` | `/admin/iam/bindings` |
| Tela | `admin/access/` | `admin/platform-access/` |
| Flag | `ENGINE_ACCESS_ENABLED` | `IAM_MODE` |
| Ciclo de vida (expiração, revogação, versão, acima do concedente) | `shared/access/policy.py`, `service.py` | `shared/iam/bindings.py`, `decide.py` |
| Delegação (envelope + grant pai) | sim | não |
| Alvo de auditoria | `access` | `iam_binding` |

O padrão de mercado (GCP IAM Conditions, Azure ABAC "built on RBAC", chaves de condição
por serviço da AWS, Cedar, Zanzibar) é **um** modelo: binding = sujeito + papel +
escopo + condição opcional, avaliado por um ponto de decisão. Restrições de domínio —
aqui, host/GPU/modelo/ambiente/`max_usd` de engine — são **condições** desse binding,
não um segundo sistema. Manter os dois planos obriga o admin a saber em que tela
conceder o quê, duplica regras que podem divergir e faria a 0017 (grupos, papéis
customizados, delegação por organização) nascer em duplicata.

## 2. Objetivo

Toda concessão de acesso — de plataforma e de engines — é um `iam_binding`,
administrado por uma API e uma tela, governado por um flag, com a delegação da 0009
preservada para a família de engines; as políticas ABAC da 0009 passam a ser
**condições** de bindings e continuam avaliadas por `shared.access.policy.authorize`.

Unifica-se o **armazenamento e a administração**, não a regra de concessão: cada
papel pertence a uma **família** (`platform` = papéis da 0014, `engines` = papéis da
0009), e cada família mantém sua própria autoridade de concessão, suas validações e
sua semântica de decisão. As famílias nunca se enxergam (§4.3).

### Fora de escopo

- Mudar a semântica de decisão da 0009: "um grant satisfaz integralmente", vários
  grants do mesmo papel por usuário, limites, recursos canônicos, epoch, admissão de
  efeito, fencing do executor, contexto legado e principais de instalação continuam
  iguais. Única exceção deliberada: autoconcessão proibida também para papéis de
  engines (0013 §4 regra 6; §4.5).
- Apagar `access_role_grants` (fica como espelho só-escrita/histórico; remoção numa
  spec futura).
- Organizações, compartilhamento, grupos e papéis customizados (0016, 0017).
- Linguagem de condição genérica (CEL/Cedar). A única família de condição é a
  revisão de política ABAC de engines já existente.
- Papéis de engines para `service_principal` (a 0009 só decide atores `User`).

## 3. Critérios de aceitação

- [ ] CA1. Após a migração, cada linha de `access_role_grants` tem um `iam_binding`
  com o **mesmo id**, `subject_type='user'`, `subject_id=user_id`, papel, permissões
  (materializadas, nunca NULL), `condition_ref=policy_revision_id`, delegação, pai,
  validade, revogação, concedente e versão; `revoked_by` vem da auditoria (§4.2.2).
  Referências existentes por `grant_id` (decisões gravadas em planos/operações/
  admissões, auditoria) continuam válidas. Todo binding de papel `engines` tem
  `permissions` não vazia ⊆ papel e `condition_ref` resolvível; todo binding de papel
  `platform` tem `permissions`, `condition_ref`, `delegation` e `parent_id` NULL.
- [ ] CA2. `policy.authorize`, `policy.grants`, `active_grant`, `navigation`,
  `visible_catalog`, `scoped_query`, `_delegator` e `access_session` leem **somente**
  `iam_bindings`. Um teste falha se algum módulo consultar `RoleGrant`, exceto a
  migração da 0018 (`shared/iam/migration.py`), o espelho de rollback
  (`shared/iam/engine_mirror.py`, só escrita por id) e a cópia congelada de CA4
  (`shared/iam/engine_equivalence.py`).
- [ ] CA3. Toda a suíte da 0009 passa com **asserções inalteradas**. Podem mudar
  apenas: o helper de criação de grants dos fixtures e os acessos diretos a linhas de
  grant (`db.get(RoleGrant, id)`, `query(RoleGrant).filter_by(user_id=...)`, hoje em
  `tests/test_execution_profiles.py` e `tests/test_execution_profiles_migration.py`),
  que passam a usar `IamBinding` por um helper único (`grant_row(db, id)` /
  `grant_rows(db, user_id)`). O diff dos testes contém só essas trocas.
- [ ] CA4. Equivalência: para um conjunto de grants legados — ativos, revogados,
  expirados, delegados, pai revogado, pai expirado, dono do grant inativo, dono do pai
  inativo, ciclo de `parent_id`, vários grants do mesmo papel com subconjuntos de
  permissões distintos — e uma matriz de pedidos
  (ator × permissão × engine/perfil/feature/runtime/recursos, mais `navigation`,
  `visible_catalog`, `scoped_query` e `_delegator`), a decisão nova é idêntica à de uma
  **cópia congelada** de `policy.grants`/`active_grant` anterior à 0018 lendo
  `RoleGrant`, mantida em `shared/iam/engine_equivalence.py` (não importa o código
  novo). A mesma comparação é exposta como script contra o snapshot de dev e é gate
  antes do deploy. `condition_ref` ausente, pendente, `permissions` vazias ou sujeito
  não-usuário ficam **fora** da equivalência: a migração recusa esses grants (CA1) e,
  no lado legado, `authorize` lança `AttributeError` enquanto `navigation` ainda conta
  o grant, de modo que não há decisão legada a igualar. Só o lado novo é testado, como
  defesa em profundidade: o binding malformado não contribui nada (→ nega).
- [ ] CA5. Escrever binding de papel `engines` trava o epoch da 0009 (`FOR UPDATE`)
  antes de ler ou alterar qualquer binding ou usuário e o incrementa na mesma
  transação; bindings de papel `platform` não tocam o epoch (0013 §4 regra 2).
  Ordem global de locks (§4.3) respeitada; teste de concorrência em MySQL: admissão de
  efeito de um filho × concessão 0014 ao dono do pai, sem deadlock.
- [ ] CA6. `POST /admin/iam/bindings` concede papéis das duas famílias, com regras
  **por família** que nunca se cruzam:
  - `platform`: as da 0014, inalteradas — `iam.bindings.manage`, autoconcessão
    proibida (`SELF_GRANT`), papel acima do concedente calculado só sobre bindings
    `platform` (`ROLE_ABOVE_GRANTOR`), um binding ativo por (sujeito, papel)
    (`BINDING_EXISTS`). Enviar `permissions`, `condition_ref`, `delegation` ou
    `parent_id` → 422 `FIELD_NOT_ALLOWED_FOR_ROLE`.
  - `engines`: as de `create_grant` — bootstrap (`is_effective_admin`) ou
    `access.grants.manage` + `_delegator` (envelope cobre permissões, condição ⊆ e
    prazo); `condition_ref` obrigatório; `permissions` opcional no corpo, sempre
    materializada (`sorted(policy.ROLES[role])` quando omitida), não vazia e ⊆ papel;
    `delegation` só para `access_admin` e ⊆ `policy.PERMISSIONS`; `subject_type` só
    `user` (422 `INVALID_SUBJECT`); `parent_id` é definido pelo serviço e sempre aponta
    para um binding `engines` (`access_admin`); códigos `ROLE_UNKNOWN`,
    `PERMISSIONS_OUTSIDE_ROLE`, `GRANT_TARGET_NOT_FOUND`, `GRANT_EXPIRY_INVALID`,
    `DELEGATION_INVALID`, `DELEGATION_EXCEEDED`. **Não** se aplicam
    `BINDING_EXISTS` (vários bindings ativos do mesmo papel para o mesmo usuário são
    válidos, cada um com sua condição) nem `ROLE_ABOVE_GRANTOR` (o limite é o
    envelope). Autoconcessão proibida (`SELF_GRANT`, desvio intencional da 0009).
    Com `engine_access_enabled` falso → 503 `ACCESS_NOT_ENABLED`, como os aliases.
  - As duas famílias exigem sessão JWT nas escritas (API key → 403).

  Testes: quem tem só binding `platform_admin` (sem bootstrap) recebe 403
  `ACCESS_DENIED` ao conceder ou revogar papel `engines`; um `access_admin` delegado
  recebe 403 `ACCESS_DENIED` ao conceder ou revogar papel `platform`; dois
  `engine_operator` com subconjuntos distintos para o mesmo usuário → 201 e 201.
- [ ] CA7. Delegação: um binding `access_admin` com envelope permite conceder dentro do
  envelope (permissões, condições ⊆, prazo máximo); revogar ou expirar o pai, ou
  desativar o dono do pai, invalida os derivados na próxima decisão; sem envelope não
  concede nada; bootstrap não precisa de envelope. Só para a família `engines`; a
  família `platform` não tem delegação nesta spec.
- [ ] CA8. `GET|POST /admin/access/grants` e `POST /admin/access/grants/{id}/revoke`
  continuam respondendo com o mesmo contrato da 0009 (status, corpo `{code}`, erros,
  re-revogação aceita, listagem incluindo revogados/expirados filtrada por
  `_delegator`), implementados sobre `iam_bindings`, só para papéis `engines` (papel
  `platform` → 422 `ROLE_UNKNOWN`; a listagem não mostra bindings `platform`), e
  marcados `deprecated` no OpenAPI. Única exceção, listada no teste: autoconcessão →
  422 `SELF_GRANT`.
- [ ] CA9. Rollback não amplia acesso:
  - o espelho grava em `access_role_grants`, na mesma transação, toda concessão e
    revogação de papel `engines`, copiando id, user_id, role, permissions
    materializadas, policy_revision_id, delegation, parent_id, granted_by,
    expires_at, revoked_at, version e created_at; falha do espelho aborta a transação;
  - a reconciliação (§4.2.3) roda a cada `alembic upgrade` e a cada boot da API,
    independentemente do marcador, e só restringe;
  - testes: (a) revogar pela API unificada → a cópia congelada de CA4 lendo
    `access_role_grants` nega; (b) migrar → revogar só em `access_role_grants`
    (código antigo) → reconciliar de novo → a decisão nega; (c) o downgrade da 0018
    aplica o mais restritivo em `access_role_grants` antes de apagar os bindings
    `engines`.
- [ ] CA10. `IAM_MODE` é o flag; `engine_access_enabled` é derivado (§4.4). Teste
  parametrizado cobre `IAM_MODE ∈ {off, shadow, enforce}` × `ENGINE_ACCESS_ENABLED ∈
  {não definido, true, false}`: explícito vence (com aviso de depreciação no boot);
  não definido → `IAM_MODE == "enforce"`; `shadow` não liga engines; valor vazio conta
  como não definido. Ambientes que usam `ENGINE_ACCESS_ENABLED=true` hoje (dev) não
  perdem o enforcement de engines; `ENGINE_ACCESS_ENABLED=false` explícito continua
  sendo a alavanca de emergência (só bootstrap em engines).
- [ ] CA11. Uma tela **Admin → Acesso** lista e administra todos os bindings
  (plataforma e engines), políticas/condições, atributos de engine, recursos canônicos
  e principais de instalação; `admin/platform-access/` redireciona para ela. O menu tem
  um único item "Acesso", visível por `iam.bindings.read` ou `access.grants.manage`;
  cada aba e cada ação aparecem só para quem tem a autoridade da família.
- [ ] CA12. Auditoria nova usa `target_type="iam_binding"` para toda concessão e
  revogação, com a mesma informação que a 0009 registrava (sujeito, papel, revisão de
  política, pai); linhas antigas intactas.
- [ ] CA13. Permissões de engine em `/auth/me.permissions` e `/admin/access/me` vêm
  exclusivamente de `policy.navigation` (cadeia de pais, dono ativo, condição
  resolvível, flag); `platform_roles`, `/iam/check` e `ROLE_ABOVE_GRANTOR` nunca
  enxergam bindings `engines`. `access_session` continua abrindo **apenas** para quem
  tem permissão da família de engines (um binding só `platform_operator` não abre —
  teste da 0014 mantido). Teste: binding filho com pai revogado não contribui nada para
  `/auth/me.permissions` nem para `platform_roles`.
- [ ] CA14. Suítes 0014 e completa verdes (exceto as falhas de ambiente conhecidas);
  `tsc` verde; documentação de API regenerada.
- [ ] CA15. Todo processo que importa `shared.access.policy` (api, worker,
  worker-audio, worker-vision, worker-remote, worker-dispatch, worker-control,
  worker-control-watchdog, beat) recebe `IAM_MODE` e `ENGINE_ACCESS_ENABLED` com o
  mesmo valor em todos os compose files; o boot de cada um registra o valor efetivo de
  `engine_access_enabled`. Um teste de compose verifica que todo serviço com
  `ENGINE_ACCESS_ENABLED` também tem `IAM_MODE`, e que nenhum compose fixa
  `ENGINE_ACCESS_ENABLED` com default `false` (o default é vazio = não definido).
- [ ] CA16. Com `IAM_MODE=off` e `ENGINE_ACCESS_ENABLED=true`, um delegado
  `access_admin` lista, concede e revoga papéis `engines` por `/admin/iam/bindings` e
  não vê bindings `platform`; com `IAM_MODE=enforce`, um titular só de bindings
  `platform` (sem bootstrap) não vê bindings `engines`.
- [ ] CA17. Revogar binding `engines` por `/admin/iam/bindings/{id}/revoke` trava o
  epoch antes de ler o binding, exige bootstrap ou `access.grants.manage` (403
  `ACCESS_DENIED`) + `_delegator` cobrindo o binding (403 `DELEGATION_EXCEEDED`), e
  incrementa `version` e o epoch; já revogado → 409 `ALREADY_REVOKED`; versão
  divergente → 409 `VERSION_CONFLICT`. Revogar binding `platform` mantém a regra da
  0014.
- [ ] CA18. `alembic heads` retorna um único head; `upgrade → downgrade → upgrade` é
  idempotente em MySQL e SQLite, partindo tanto de um banco novo (onde a revisão da
  0014 já cria as colunas novas) quanto de um banco existente na 0014.

## 4. Solução proposta

### 4.1 Modelo

`iam_bindings` ganha colunas (§4.2.1):

| Coluna | Uso |
|---|---|
| `permissions` JSON NULL | Papéis `engines`: **sempre materializada** na escrita (corpo ou `sorted(policy.ROLES[role])`), snapshot como na 0009 — adicionar ação a `engine_control.contracts.ACTIONS` não amplia bindings existentes; não vazia e ⊆ papel. Papéis `platform`: sempre NULL. |
| `condition_ref` String(36) NULL, FK `fk_iam_bindings_condition_ref` → `access_policy_revisions.id` | Condição ABAC de engines; obrigatória para papéis `engines`, NULL para `platform`. |
| `delegation` JSON NULL | Envelope da 0009 (`permissions` ⊆ `policy.PERMISSIONS`, `constraints`, `max_grant_seconds`); só `access_admin`. |
| `parent_id` String(36) NULL, FK `fk_iam_bindings_parent` → `iam_bindings.id` | Binding `engines` (`access_admin`) que autorizou esta concessão por delegação; NULL para `platform`. |

Índice novo `ix_iam_bindings_subject_role (subject_type, subject_id, role)` (ordem de
locks, §4.3).

**Catálogo.** Os seis papéis da 0009 (`observer`, `profile_editor`,
`runtime_configurator`, `engine_operator`, `access_admin`, `connection_manager`)
entram no catálogo num mapa **separado** `catalog.ENGINE_ROLES` (família `engines`,
permissões lidas de `policy.ROLES`, uma fonte só), **nunca** em `catalog.ROLES`. As
asserções atuais (`ROLES ⊆ PLATFORM_PERMISSIONS`, nomes sem sobreposição) ficam como
estão. `catalog.family(role)` devolve `platform`, `engines` ou `None` (papel
desconhecido). `describe()` expõe as duas famílias com o campo `family`.
`scope_type` continua `platform`: o escopo de engine é expresso pela condição, como no
GCP (binding no projeto + condição sobre o recurso).

**Defesa em profundidade.** `Decider.bindings`, `platform_permissions` e
`platform_roles` continuam filtrando `role in catalog.ROLES` e passam a ignorar (não
conceder) binding `platform` com `permissions`, `condition_ref`, `delegation` ou
`parent_id` não-NULL. O adaptador da 0009 (§4.3) descarta, inclusive em `navigation`,
binding `engines` com `permissions` NULL/vazia, `condition_ref` NULL ou revisão
inexistente, ou `subject_type != 'user'`, registrando aviso; condição ausente
**nunca** é tratada como irrestrita.

### 4.2 Esquema e migração

#### 4.2.1 Revisão Alembic e DDL

- Nova revisão com `down_revision = "03e70014b8c5"` (head único), chamando
  `shared.iam.migration.upgrade_0018` / `downgrade_0018`, no padrão das revisões
  0009/0014.
- DDL em `shared/iam/migration.py` (`COLUMNS_0018`), no padrão `COLUMNS` da 0009:
  cada coluna é adicionada **só se ausente** (num banco novo, o `create_all` da revisão
  `a1c40014e7b2` já cria a tabela com as colunas atuais do modelo); FKs com os nomes
  acima, criadas só se ausentes; índice com `checkfirst`.
- DDL e dados em passos separados (no MySQL DDL comita implicitamente): DDL primeiro,
  depois cópia + reconciliação + validação numa transação, e o marcador
  `0018_engine_bindings` em `app_migrations` gravado por último.
- `validate_schema` da IAM passa a checar também as colunas, as FKs e a ausência de
  grants sem binding de mesmo id; `init_db` a chama quando `iam_mode != "off"`
  **ou** `engine_access_enabled`.
- `downgrade_0018`: (1) sob o lock do epoch, aplica em `access_role_grants` o mais
  restritivo entre espelho e binding para todo id `engines` (`revoked_at`,
  `expires_at`, `version`) e insere no espelho os bindings `engines` ausentes; recusa
  se alguma linha não puder ser espelhada; (2) apaga os bindings `engines` e o
  marcador; (3) remove as FKs pelo nome, depois o índice e as colunas. O `_downgrade`
  da 0014 passa a recusar enquanto existir binding com papel fora de `catalog.ROLES`.

#### 4.2.2 Cópia

Para cada `access_role_grants` sem `iam_binding` de mesmo id, em ordem topológica por
`parent_id` (pais antes de filhos): inserir binding com `id` igual,
`subject_type='user'`, `subject_id=user_id`, `role`, `permissions`,
`condition_ref=policy_revision_id`, `delegation`, `parent_id`, `granted_by`,
`expires_at`, `revoked_at`, `version`, `created_at`, `scope_type='platform'`.
`revoked_by` = `actor_user_id` da última linha `AdminAudit(action='access.revoked',
target_type='access', target_id=id)`, senão NULL.

#### 4.2.3 Reconciliação

Função idempotente `reconcile_engine_grants(conn)` em `shared/iam/migration.py`, sob
o lock do epoch:

1. insere os ausentes como em §4.2.2 (grants criados pelo código anterior durante um
   rollback);
2. para cada id presente nas duas tabelas: `revoked_at := COALESCE(b.revoked_at,
   g.revoked_at)`, `expires_at := LEAST(b.expires_at, g.expires_at)`, `version :=
   GREATEST(b.version, g.version)`. Só restringe, nunca amplia;
3. valida: contagem igual e campos de CA1 iguais para todo id; falha aborta;
4. se alterou alguma linha, incrementa o epoch da 0009 na mesma transação.

Roda **sempre**, independentemente do marcador: em todo `upgrade_0018` e em todo boot
da API (`init_db`, único chamador hoje) enquanto `access_role_grants` existir.

### 4.3 Decisão e escrita

- `policy.grants(db, actor, lock)` passa a selecionar bindings ativos com
  `subject_type='user'`, `subject_id=actor` e papel em `catalog.ENGINE_ROLES`, com o
  mesmo `with_for_update` quando `lock=True`; `active_grant` percorre `parent_id` em
  `iam_bindings` (só bindings `engines`) e mantém a checagem de dono ativo e o guarda
  de ciclo. A interface que o resto da 0009 consome (objeto com `.permissions`,
  `.policy_revision_id`, `.delegation`, `.id`, `.expires_at`, `.parent_id`,
  `.user_id`) é preservada por um adaptador fino, sem duplicar regra. `navigation`,
  `list_grants`, `visible_catalog` e `scoped_query` nunca enxergam bindings
  `platform`.
- `decide()` da 0014 continua delegando permissões de engines a `policy.authorize`.
- Um único serviço de escrita (`shared/iam/bindings.py`) concede e revoga qualquer
  binding e **ramifica pela família do papel antes de qualquer checagem**: `platform`
  segue o caminho atual da 0014 sem mudança; `engines` segue as regras de CA6, CA7 e
  CA17, reutilizando `policy.subset` e `_delegator` (que passa a ler `iam_bindings`).
  Papel desconhecido nas duas famílias → `UNKNOWN_ROLE` (rota unificada) /
  `ROLE_UNKNOWN` (alias). Na revogação a família vem do binding alvo.
- Família `engines`: `policy.epoch(db, lock=True)` antes de tudo e `authority.version
  += 1` no commit (CA5); espelho em `access_role_grants` na mesma transação
  (`shared/iam/engine_mirror.py`, só escrita por id; CA9).
- **Ordem global de locks:** epoch (só família `engines`) → linhas `users` → linhas
  `iam_bindings`/`access_role_grants`. A checagem `BINDING_EXISTS` da família
  `platform` (`role` já validado como papel `platform`) força no MySQL o índice
  `ix_iam_bindings_subject_role` (`FORCE INDEX`), para a leitura com lock não varrer
  `ix_iam_bindings_subject` e travar bindings `engines` do mesmo sujeito; o boot
  exige o índice. Ordem não verificada em InnoDB até existir o teste de concorrência
  de CA5.
- O `_delegator` mantém o envelope restrito a `policy.PERMISSIONS`
  (`DELEGATION_INVALID`) e considera só bindings `engines`.

### 4.4 Flag

`engine_access_enabled` vira propriedade derivada:

- `ENGINE_ACCESS_ENABLED` definido (true ou false) → esse valor (depreciado, aviso no
  boot); string vazia conta como não definido;
- não definido → `IAM_MODE == "enforce"` (`shadow` não liga engines).

`ENGINE_ACCESS_ENABLED=false` explícito continua sendo a alavanca de emergência que só
reduz acesso (engines voltam a só bootstrap), independente de `IAM_MODE`. Ligar
`IAM_MODE=enforce` numa instalação que nunca ligou engines passa a exigir o esquema da
0009 no boot e liga o enforcement de engines; o runbook manda conceder papéis
`engines` antes, ou fixar `ENGINE_ACCESS_ENABLED=false`.

Propagação (CA15): `docker-compose.yml` passa `IAM_MODE` também a worker-remote,
worker-vision e beat; `docker-compose.engine-control.yml` passa `IAM_MODE` a todos os
serviços que já recebem `ENGINE_ACCESS_ENABLED` e troca o default
`${ENGINE_ACCESS_ENABLED:-false}` por `${ENGINE_ACCESS_ENABLED:-}`.

### 4.5 API

- `/admin/iam/bindings*`: as três rotas deixam de declarar `require("iam.bindings.*")`
  fixo e declaram uma dependência única `binding_admin(write=...)` (novo kind
  `iam_or_engine_access` em `test_iam_route_coverage`): usuário ativo, sessão JWT nas
  escritas, e admite quem tem a autoridade de **alguma** família — `platform` por
  `decide.can(..., "iam.bindings.read|manage")` (honra `IAM_MODE`), `engines` por
  `policy.allowed(..., "access.grants.manage")` com `engine_access_enabled` — ou
  bootstrap. O handler decide por família (corpo na concessão, binding alvo na
  revogação). O `GET` filtra por linha: `platform` por `iam.bindings.read`; `engines`
  pelo mesmo filtro `_delegator` de `list_grants`; `include_inactive` vale para as duas.
- Corpo de concessão ganha `permissions`, `condition_ref` e `delegation`; a resposta
  ganha `family`, `permissions`, `condition_ref`, `delegation` e `parent_id`.
- `/admin/access/grants*`: aliases depreciados com contrato idêntico (CA8), sobre o
  mesmo serviço.
- Políticas (`/admin/access/policies*`), atributos, recursos e principais: inalterados.

Códigos e corpos de erro por família:

| Situação | Rota unificada, `platform` | Rota unificada, `engines` | Alias `/admin/access/grants*` |
|---|---|---|---|
| Corpo de erro | `{code, message}` | `{code, message}` | `{code}` (0009) |
| Papel desconhecido | 422 `UNKNOWN_ROLE` | 422 `UNKNOWN_ROLE` | 422 `ROLE_UNKNOWN` |
| Sujeito/condição inexistente | 422 `SUBJECT_NOT_FOUND` | 404 `GRANT_TARGET_NOT_FOUND` | 404 `GRANT_TARGET_NOT_FOUND` |
| Prazo inválido | 422 `INVALID_EXPIRES_AT` | 422 `GRANT_EXPIRY_INVALID` | 422 `GRANT_EXPIRY_INVALID` |
| Sem a permissão de administrar | 403 `ACCESS_DENIED` | 403 `ACCESS_DENIED` | 403 `ACCESS_DENIED` |
| Acima da autoridade | 422 `ROLE_ABOVE_GRANTOR` | 403 `DELEGATION_EXCEEDED` | 403 `DELEGATION_EXCEEDED` |
| Autoconcessão | 422 `SELF_GRANT` | 422 `SELF_GRANT` | 422 `SELF_GRANT` |
| Duplicado ativo | 409 `BINDING_EXISTS` | permitido | permitido |
| Campo de outra família | 422 `FIELD_NOT_ALLOWED_FOR_ROLE` | — | — |
| Revogar já revogado | 409 `ALREADY_REVOKED` | 409 `ALREADY_REVOKED` | aceito, `version += 1` (0009) |
| Revogar inexistente | 404 `BINDING_NOT_FOUND` | 404 `BINDING_NOT_FOUND` | 404 `GRANT_NOT_FOUND` |
| Engines desligado | — | 503 `ACCESS_NOT_ENABLED` | 503 `ACCESS_NOT_ENABLED` |

### 4.6 Frontend

Uma página **Admin → Acesso** com abas: Concessões (todos os bindings visíveis, filtro
por família), Políticas, Atributos de engine, Recursos, Principais de instalação.
Reaproveita componentes de `admin/access/` e `admin/platform-access/`; esta última
passa a redirecionar. Item único no menu. O formulário de concessão mostra os campos
de `engines` (condição, permissões, delegação) só para papéis dessa família.

### 4.7 Emenda à 0013 §4

A 0013 diz que specs de fatia podem detalhar, nunca contrariar, suas regras; esta spec
contraria as regras 1 e 2 e por isso as emenda (na fatia 1, §8):

- Regra 1 → "Permissões de engine são decididas por `shared/access/policy.authorize`
  com a semântica da 0009 (lendo `iam_bindings` desde a 0018)."
- Regra 2 → "Desde a 0018 toda concessão vive em `iam_bindings`, em duas famílias
  (`platform`, `engines`) que nunca se enxergam: `policy.grants`, `active_grant`,
  `navigation` e `list_grants` filtram papéis `engines` e `subject_type='user'`; o
  `Decider` filtra papéis `platform`. `access_role_grants` é espelho só-escrita até
  sua remoção. O epoch da 0009 continua tocado apenas por escrita de bindings
  `engines`, políticas, atributos e principais, e por admissões de efeito."

## 5. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Manter os dois planos | Débito: duas telas, duas regras, delegação só num lado, 0017 em duplicata |
| Mover `access_role_grants` para dentro do IAM sem trocar a tabela | Mantém `user_id`/`policy_revision_id NOT NULL` e não aceita grupos (0017) |
| Reescrever o ABAC da 0009 como linguagem de condição genérica | Escopo e risco desproporcionais; a revisão de política já é a condição |
| Novo id para os bindings migrados | Quebra `grant_id` gravado em decisões de operação e auditoria |
| Apagar `access_role_grants` já | Rollback ampliaria acesso (revogações perdidas) |
| Papéis 0009 em `catalog.ROLES` | Quebra a asserção `ROLES ⊆ PLATFORM_PERMISSIONS` e vaza permissões de engine (inclusive de bindings mortos) para `platform_roles`, `/iam/check` e `ROLE_ABOVE_GRANTOR` |
| Uma regra de concessão única para as duas famílias | Contradiz a 0009 (vários grants do mesmo papel; envelope em vez de "acima do concedente") e a suíte que CA3 preserva |
| `permissions` NULL = todas as do papel, resolvido na decisão | Amplia bindings existentes quando um papel ganha ação (0013 §4 regra 6) |
| Migração só uma vez, por marcador | Revogações feitas pelo código antigo num rollback não voltariam |

## 6. Impactos

- **Compatibilidade:** contratos mantidos; aliases depreciados; flag com alias; única
  mudança de comportamento: autoconcessão de papel `engines` passa a ser recusada.
- **Segurança:** autoridade de concessão por família, sem cruzamento; revogação
  continua imediata e serializada pelo epoch para efeitos de engine; rollback não
  reabre revogações (espelho + reconciliação); todos os processos veem o mesmo flag.
- **Performance:** uma consulta de bindings por decisão, como hoje; a reconciliação
  no boot é O(grants) sob o lock do epoch.
- **Operação:** migração idempotente e verificada; deploy das fatias 1 e 2 numa etapa
  só, sem pods antigos servindo `/admin/access/grants` em paralelo; no código
  anterior (rollback), papéis de engine só se revogam por `/admin/access/grants`;
  aviso de flag depreciado.

## 7. Plano de testes

Equivalência (CA4) contra a cópia congelada, com os fixtures listados em CA4; suíte
0009 com asserções intactas (CA3); concorrência em MySQL: revogação × admissão de
efeito, revogação do pai × criação de filho via `_delegator`, revogação do pai ×
admissão de efeito do filho (ambas serializadas pelo epoch; a segunda transação vê o
pai revogado) e admissão × concessão 0014 ao dono do pai (sem deadlock, CA5); regras
por família (CA6, CA16, CA17); aliases da API (CA8); espelho, reconciliação e
downgrade (CA9); migração e head único (CA18); flag/alias (CA10) e compose (CA15);
`/auth/me` (CA13); frontend com `tsc`.

## 8. Plano de implementação

As fatias 1 e 2 são PRs separados mas **implantados juntos** (um deploy); a 1 sozinha
não vai a produção.

- [x] 1. Emenda da 0013 §4 (§4.7); colunas novas, `catalog.ENGINE_ROLES`, revisão
  Alembic, cópia + reconciliação + validação, `engine_equivalence.py` (CA1, CA4, CA18).
  Revisão `d4e80018a2b6`; leitor sobre `iam_bindings` em `shared/iam/engine_bindings.py`
  (ainda não ligado a `policy.grants`, fatia 2); script
  `scripts/iam_engine_equivalence.py`. Até a fatia 3, a rota `/admin/iam/bindings` não
  lista nem revoga bindings `engines` (404 `BINDING_NOT_FOUND`).
- [x] 2. Leitura e escrita da 0009 sobre `iam_bindings`, delegação, epoch e ordem de
  locks, espelho, reconciliação no boot, flag e compose; docstrings de
  `shared/iam/models.py`, `catalog.py`, `api/iam_routes.py` e mensagem de
  `shared/access/migration.downgrade` atualizadas (CA2, CA3, CA5, CA7, CA9, CA10,
  CA13, CA15). `policy.grants`/`active_grant` delegam a `shared/iam/engine_bindings.py`;
  `shared/iam/bindings.grant_engine`/`revoke_engine`/`list_engine_grants` servem
  `create_grant`/`revoke`/`list_grants` (códigos e auditoria da 0009 até a fatia 3);
  espelho em `shared/iam/engine_mirror.py`; `migration.reconcile_on_boot` em
  `init_db` e no `worker_init` de todo worker Celery (com engines ligado; falha
  impede o boot). Testes em `tests/test_iam_engine_bindings_writes.py`. O teste de
  concorrência em MySQL de CA5 fica para quando houver banco InnoDB descartável no CI.
- [x] 3. API unificada por família, aliases depreciados, auditoria e docs de API (CA6,
  CA8, CA12, CA16, CA17). `/admin/iam/bindings*` declaram `binding_admin(write=...)`
  (kind `iam_or_engine_access`) e chamam `shared/iam/bindings.grant_binding` /
  `revoke_binding` / `list_all`, que escolhem a família antes de qualquer checagem;
  a escrita `engines` encerra a transação de leitura das dependências antes de travar
  o epoch. `parent_id` no corpo é recusado nas duas famílias (422
  `FIELD_NOT_ALLOWED_FOR_ROLE`). As duas famílias auditam `iam.binding.grant` /
  `iam.binding.revoke` em `iam_binding`. Contrato dos aliases provado contra a captura
  do código anterior à 0018 (`tests/fixtures/pre_0018_access_grants_*.json`, commit
  `bca96be`) em `tests/test_iam_access_grant_aliases.py`; regras por família em
  `tests/test_iam_bindings_api.py`. A tela de plataforma filtra a família `platform`
  até a fatia 4.
- [ ] 4. Tela única de Acesso (CA11).
- [ ] 5. Documentação de features/runbook (deploy em uma etapa, flag, rollback),
  CHANGELOG, status das specs.

## 9. Questões em aberto

- [x] Papéis 0009 entram em `catalog.ROLES`? → **Decisão (2026-10-07):** não; mapa
  separado `catalog.ENGINE_ROLES`, e o `Decider` nunca enxerga bindings `engines`
  (§4.1, CA13).
- [x] Uma regra de concessão para as duas famílias? → **Decisão (2026-10-07):** não.
  Autoridade por família sem cruzamento; para `engines` valem envelope/`_delegator` e
  vários bindings do mesmo papel, sem `BINDING_EXISTS` nem `ROLE_ABOVE_GRANTOR`
  (CA6, CA17).
- [x] Autoconcessão de papel `engines`? → **Decisão (2026-10-07):** proibida nas duas
  rotas (0013 §4 regra 6). É um desvio intencional da 0009, nenhum teste da 0009 o
  exercita, e CA8 o lista.
- [x] `permissions` NULL? → **Decisão (2026-10-07):** `engines` sempre materializada
  (snapshot da 0009); `platform` sempre NULL (§4.1).
- [x] Migração só por marcador? → **Decisão (2026-10-07):** não; reconciliação
  restritiva a cada upgrade e boot enquanto `access_role_grants` existir (§4.2.3).
- [x] Precedência do flag? → **Decisão (2026-10-07):** `ENGINE_ACCESS_ENABLED`
  explícito vence (inclusive `false`, a alavanca de emergência); senão `IAM_MODE ==
  "enforce"`; `shadow` não liga engines (§4.4, CA10).
- [x] Contradição com a 0013 §4 regras 1–2? → **Decisão (2026-10-07):** emendar a 0013
  na fatia 1 (§4.7).
- [x] Revogar binding já revogado pela rota unificada? → **Decisão (2026-10-07):** 409
  `ALREADY_REVOKED` para as duas famílias; o alias mantém a re-revogação da 0009
  (§4.5).
- [x] `active_grant` deve travar o dono do pai antes da linha do pai (proposto na
  revisão)? → **Decisão (2026-10-07):** não. Basta restringir a consulta com lock de
  `BINDING_EXISTS` a `role IN catalog.ROLES`, por um índice que inclua `role`: a
  concessão 0014 deixa de esperar linhas `engines` e o ciclo desaparece, sem mexer na
  ordem de locks já testada da 0009.
- [x] Fatias 1 e 2 implantáveis separadamente? → **Decisão (2026-10-07):** não;
  implantadas juntas (§8).
