# 0018 — IAM: convergência do RBAC/ABAC de engines (0009) no IAM

| | |
|---|---|
| **Status** | Em implementação |
| **Autor** | Geda Valentim / Claude |
| **Criada em** | 2026-10-07 |
| **Atualizada em** | 2026-10-07 |
| **Relacionadas** | [0009](0009-perfis-de-execucao-e-controle-de-acesso.md) (substituída no armazenamento e administração de grants), [0013](0013-iam-da-plataforma.md), [0014](0014-iam-nucleo-de-decisao-e-papeis-de-plataforma.md) |
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
generalizada; as políticas ABAC da 0009 passam a ser **condições** de bindings e
continuam avaliadas por `shared.access.policy.authorize`.

### Fora de escopo

- Mudar a semântica de decisão da 0009: "um grant satisfaz integralmente", limites,
  recursos canônicos, epoch, admissão de efeito, fencing do executor, contexto legado
  e principais de instalação continuam iguais.
- Apagar `access_role_grants` (fica só leitura/histórico; remoção numa spec futura).
- Organizações, compartilhamento, grupos e papéis customizados (0016, 0017).
- Linguagem de condição genérica (CEL/Cedar). A única família de condição é a
  revisão de política ABAC de engines já existente.

## 3. Critérios de aceitação

- [ ] CA1. Após a migração, cada linha de `access_role_grants` tem um `iam_binding`
  com o **mesmo id**, sujeito, papel, permissões, revisão de política, delegação, pai,
  validade, revogação, concedente e versão. Referências existentes por `grant_id`
  (decisões gravadas em planos/operações/admissões, auditoria) continuam válidas.
- [ ] CA2. `policy.authorize`, `policy.grants`, `active_grant`, `navigation`,
  `_delegator` e `access_session` leem **somente** `iam_bindings`. Um teste falha se
  algum módulo fora da migração consultar `RoleGrant`.
- [ ] CA3. Toda a suíte da 0009 passa com **asserções inalteradas**; só a forma de
  criar grants nos fixtures pode mudar (helper único), e o diff dos testes mostra isso.
- [ ] CA4. Equivalência: para um conjunto de grants legados (inclusive revogados,
  expirados, delegados e com pai revogado) e uma matriz de pedidos
  (ator × permissão × engine/perfil/feature/runtime/recursos), a decisão lendo o
  armazenamento antigo é idêntica à decisão lendo `iam_bindings`.
- [ ] CA5. Escrever binding que contenha alguma permissão de engine (0009) incrementa
  o epoch da 0009 na mesma transação, sob o mesmo lock, antes dos locks de engine;
  bindings só com permissões de plataforma 0014 não tocam o epoch (0013 §4.2).
- [ ] CA6. `POST /admin/iam/bindings` concede tanto papéis 0014 quanto papéis 0009
  (com `policy_revision_id` obrigatório para estes, `permissions` opcional como
  subconjunto do papel, `delegation` só para `access_admin`), com as mesmas validações
  e códigos de erro hoje aplicados por `create_grant` (`ROLE_UNKNOWN`,
  `PERMISSIONS_OUTSIDE_ROLE`, `GRANT_TARGET_NOT_FOUND`, `GRANT_EXPIRY_INVALID`,
  `DELEGATION_INVALID`, `DELEGATION_EXCEEDED`) e as da 0014 (autoconcessão, acima do
  concedente, sessão JWT).
- [ ] CA7. Delegação generalizada: um binding com envelope permite conceder dentro do
  envelope (permissões, condições ⊆, prazo máximo); revogar ou expirar o pai invalida os
  derivados na próxima decisão; sem envelope não concede nada; bootstrap não precisa de
  envelope. Vale para papéis 0009; papéis 0014 continuam exigindo
  `iam.bindings.manage` + possuir todas as permissões do papel.
- [ ] CA8. `GET|POST /admin/access/grants` e `POST /admin/access/grants/{id}/revoke`
  continuam respondendo com o mesmo contrato (status, corpo, erros), implementados
  sobre `iam_bindings`, e marcados `deprecated` no OpenAPI.
- [ ] CA9. Rollback não amplia acesso: enquanto `access_role_grants` existir,
  revogações, expirações antecipadas e novas concessões de papéis 0009 são espelhadas
  nela na mesma transação; voltar ao código anterior enxerga as mesmas revogações.
- [ ] CA10. Um único flag: `IAM_MODE`. `ENGINE_ACCESS_ENABLED=true` continua aceito como
  alias depreciado ("engines em enforce"), com aviso no boot; ambientes que o usam
  hoje (dev) não perdem o enforcement de engines na atualização.
- [ ] CA11. Uma tela **Admin → Acesso** lista e administra todos os bindings
  (plataforma e engines), políticas/condições, atributos de engine, recursos canônicos
  e principais de instalação; `admin/platform-access/` redireciona para ela. O menu tem
  um único item "Acesso", visível por `iam.bindings.read` ou `access.grants.manage`.
- [ ] CA12. Auditoria nova usa `target_type="iam_binding"` para toda concessão e
  revogação, com a mesma informação que a 0009 registrava; linhas antigas intactas.
- [ ] CA13. `/auth/me.permissions` e `/admin/access/me` derivam do mesmo armazenamento;
  `access_session` continua abrindo **apenas** para quem tem permissão da família de
  engines (um binding só `platform_operator` não abre — teste da 0014 mantido).
- [ ] CA14. Suítes 0014 e completa verdes (exceto as falhas de ambiente conhecidas);
  `tsc` verde; documentação de API regenerada.

## 4. Solução proposta

### 4.1 Modelo

`iam_bindings` ganha colunas (migration aditiva, Alembic + caminho de migração da 0014):

| Coluna | Uso |
|---|---|
| `permissions` JSON NULL | Restrição opcional a um subconjunto do papel (a 0009 permite); NULL = todas as do papel |
| `condition_ref` String(36) NULL, FK `access_policy_revisions.id` | Condição ABAC de engines; obrigatória para papéis 0009, proibida para papéis 0014 |
| `delegation` JSON NULL | Envelope da 0009 (`permissions`, `constraints`, `max_grant_seconds`) |
| `parent_id` String(36) NULL, FK `iam_bindings.id` | Binding que autorizou esta concessão por delegação |

Os seis papéis da 0009 (`observer`, `profile_editor`, `runtime_configurator`,
`engine_operator`, `access_admin`, `connection_manager`) entram no catálogo da 0014 como
papéis gerenciados da família `engines`, com permissões **lidas de `policy.ROLES`** (uma
fonte só). `scope_type` continua `platform`: o escopo de engine é expresso pela
condição, como no GCP (binding no projeto + condição sobre o recurso).

### 4.2 Migração de dados

Idempotente, com marcador em `app_migrations`:

1. Para cada `access_role_grants` sem `iam_binding` de mesmo id: inserir binding com
   `id` igual, `subject_type='user'`, `subject_id=user_id`, `role`, `permissions`,
   `condition_ref=policy_revision_id`, `delegation`, `parent_id`, `granted_by`,
   `expires_at`, `revoked_at`, `version`, `created_at`. `revoked_by` NULL quando
   desconhecido.
2. Validar: contagem igual; para cada id, campos iguais; falha aborta sem commit.
3. Pais antes de filhos (ordem topológica por `parent_id`).

### 4.3 Decisão

- `policy.grants(db, actor, lock)` passa a selecionar bindings ativos do usuário cujo
  papel é da família `engines`, com o mesmo `with_for_update` quando `lock=True`;
  `active_grant` percorre `parent_id` em `iam_bindings` e mantém a checagem de dono
  ativo. A interface que o resto da 0009 consome (objeto com `.permissions`,
  `.policy_revision_id`, `.delegation`, `.id`, `.expires_at`) é preservada por um
  adaptador fino, sem duplicar regra.
- `decide()` da 0014 continua delegando permissões de engines a `policy.authorize`.
- Um único serviço de escrita (`shared/iam/bindings.py`) concede e revoga qualquer
  binding; para papéis 0009 aplica as validações e a delegação (§CA6/CA7) reutilizando
  `policy.subset` e a lógica de `_delegator`, que passa a ler `iam_bindings`. Para
  bindings com permissões de engine: `policy.epoch(db, lock=True)` antes de tudo e
  `authority.version += 1` no commit (CA5).
- Espelho de rollback (CA9): na mesma transação, gravar/atualizar a linha
  correspondente em `access_role_grants` para papéis 0009. O espelho é **somente
  escrita**; nada o lê.

### 4.4 Flag

`IAM_MODE` governa tudo. `engine_access_enabled` vira propriedade derivada:
`IAM_MODE == "enforce"` **ou** `ENGINE_ACCESS_ENABLED=true` (alias depreciado, aviso
no boot). Nenhum caminho da 0009 muda de comportamento enquanto o alias estiver ativo.

### 4.5 API

- `/admin/iam/bindings`: aceita os campos novos; `GET` lista todos os bindings
  visíveis ao solicitante com o mesmo filtro de visibilidade que `list_grants` aplica
  hoje para papéis 0009 e `iam.bindings.read` para 0014.
- `/admin/access/grants*`: aliases depreciados com contrato idêntico (CA8).
- Políticas (`/admin/access/policies*`), atributos, recursos e principais: inalterados.

### 4.6 Frontend

Uma página **Admin → Acesso** com abas: Concessões (todos os bindings, filtro por
família), Políticas, Atributos de engine, Recursos, Principais de instalação.
Reaproveita componentes de `admin/access/` e `admin/platform-access/`; esta última
passa a redirecionar. Item único no menu.

## 5. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Manter os dois planos | Débito: duas telas, duas regras, delegação só num lado, 0017 em duplicata |
| Mover `access_role_grants` para dentro do IAM sem trocar a tabela | Mantém `user_id`/`policy_revision_id NOT NULL` e não aceita grupos (0017) |
| Reescrever o ABAC da 0009 como linguagem de condição genérica | Escopo e risco desproporcionais; a revisão de política já é a condição |
| Novo id para os bindings migrados | Quebra `grant_id` gravado em decisões de operação e auditoria |
| Apagar `access_role_grants` já | Rollback ampliaria acesso (revogações perdidas) |

## 6. Impactos

- **Compatibilidade:** contratos mantidos; aliases depreciados; flag com alias.
- **Segurança:** uma regra de concessão; revogação continua imediata e serializada
  pelo epoch para efeitos de engine; rollback não reabre revogações.
- **Performance:** uma consulta de bindings por decisão, como hoje.
- **Operação:** migração de dados idempotente e verificada; aviso de flag depreciado.

## 7. Plano de testes

Equivalência (CA4) com fixtures cobrindo revogados, expirados, delegados e pais
revogados; suíte 0009 com asserções intactas (CA3); concorrência revogação × admissão
de efeito (epoch); aliases da API (CA8); espelho de rollback (CA9); flag/alias (CA10);
frontend com `tsc`.

## 8. Plano de implementação

- [ ] 1. Colunas novas, papéis 0009 no catálogo, migração de dados + verificação, CA1/CA4.
- [ ] 2. Leitura e escrita da 0009 sobre `iam_bindings`, delegação, epoch, espelho, flag
  (CA2, CA3, CA5, CA7, CA9, CA10, CA13).
- [ ] 3. API unificada, aliases depreciados, auditoria (CA6, CA8, CA12) e docs de API.
- [ ] 4. Tela única de Acesso (CA11).
- [ ] 5. Documentação de features/runbook, CHANGELOG, status das specs.
