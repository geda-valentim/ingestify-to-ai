# 0013 — IAM da plataforma (guarda-chuva)

| | |
|---|---|
| **Status** | Rascunho |
| **Autor** | Geda Valentim / Claude |
| **Criada em** | 2026-10-06 |
| **Atualizada em** | 2026-10-06 |
| **Relacionadas** | [0004](0004-projects-and-folders.md), [0009](0009-perfis-de-execucao-e-controle-de-acesso.md), [0014](0014-iam-nucleo-de-decisao-e-papeis-de-plataforma.md), 0015, 0016, 0017 |
| **Substituída por** | — |

---

Esta spec registra **a direção e as regras transversais** do IAM. Ela não é implementada
sozinha: cada fatia tem sua própria spec, entregável e reversível isoladamente. Uma
primeira versão monolítica foi revisada por dois agentes (arquitetura e segurança) em
2026-10-06; os achados que valem para todas as fatias estão em §4, os específicos foram
para a spec da fatia correspondente.

## 1. Problema

A 0009 entregou um núcleo de autorização (papéis, políticas imutáveis, grants com
validade/revogação/delegação, principais de serviço, epoch, auditoria, nega por padrão),
mas só para **engines e perfis de execução**. O resto da plataforma usa:

| Mecanismo | Onde | Limitação |
|---|---|---|
| Dono único (`user_id`) | `api/deps.py` (`get_owned_job`, `owned_*_or_404`) e ~84 filtros inline em `routes.py`, `projects_api.py`, `project_management.py`, `image_routes.py`, `datalake_routes.py`, `apikey_routes.py`, `tag_routes.py` | Não há compartilhamento |
| `is_effective_admin` | `require_admin` (`admin_routes.py:50`, `platform_settings_routes.py`, `routing_admin_routes.py`), `require_admin_session` (`engine_admin_routes.py:56`) | Tudo-ou-nada; sem operador ou auditor |
| `is_effective_admin` para engine remota | API (`routes.py:423,513,870,2881`, `image_routes.py:277`) e workers (`workers/tasks.py:261,889`, `image_full_tasks.py:229`) → `shared/engines/dispatch.py:177` | Gasto pago decidido por um booleano; teto por usuário só vale com `remote_allowed_for='all'` (`dispatcher.py:378`) |
| API key = dono | `shared/auth.py:293-302` | Key de admin passa por `require_admin`; qualquer key gere outras keys |

Não há tenant, e não há inventário verificável de qual rota exige o quê.

## 2. Objetivo

Toda decisão de acesso — rota HTTP, WebSocket, task e API key — passa por um único ponto
de decisão `decide(principal, permissão, recurso)` sobre bindings em SQL, com
**organizações** como raiz de tenancy, **compartilhamento por recurso** e **API keys
escopadas**, preservando o ABAC de engines da 0009.

### Fora de escopo (de todas as fatias)

- SSO/SAML/OIDC, SCIM, MFA, convites por e-mail.
- Compartilhamento entre organizações; engines/GPUs/perfis pertencentes a organizações;
  billing por organização.
- Política em linguagem (DSL, Rego, Cedar), `deny` escrito por usuários, condições JSON
  arbitrárias vindas do browser; serviço IAM externo; permissão por campo.

## 3. Fatias

| Spec | Entrega | Depende de | Valor isolado |
|---|---|---|---|
| [0014](0014-iam-nucleo-de-decisao-e-papeis-de-plataforma.md) | Catálogo de permissões, `decide()`, `require()`/`authorized()` em **todas** as rotas, teste de cobertura, papéis `platform_admin/operator/auditor`, `engines.remote.use` | — | Acaba com o admin tudo-ou-nada; toda rota passa a declarar permissão |
| 0015 — API keys escopadas | Key = dono ∩ escopo; keys perdem `/admin/*` e gestão de keys | 0014 | Fecha o risco atual de key de admin vazada |
| 0016 — Organizações pessoais | `organizations`, membros, `org_id` nas tabelas, `X-Org-Id`, índices, `org_id` no ES, link SQL de jobs filhos | 0014 | Raiz de tenant; equivalência com o modelo atual verificável exaustivamente |
| 0017 — Compartilhamento e times | Orgs `team`, grupos, papéis customizados, bindings em projeto/pasta/job/datalake, "Compartilhados comigo" | 0014, 0016 | Colaboração |

0015 e 0016 podem andar em paralelo após a 0014.

## 4. Regras transversais

Valem para todas as fatias; uma spec de fatia pode detalhar, nunca contrariar.

1. **Um ponto de decisão.** `shared/iam/decide.py`. Permissões de engine delegam a
   `shared/access/policy.authorize` da 0009 sem alterá-la.
2. **Tabelas da 0009 intactas.** Bindings do IAM vivem em `iam_bindings`, nunca em
   `access_role_grants`. O epoch da 0009 (`access_authorization_epoch`, linha única com
   `FOR UPDATE`) continua exclusivo de admissões de efeito em engines. *(Revisão: gravar
   bindings de dados nos grants da 0009 quebrava `active_grant`, `list_grants` e
   `navigation`, e serializava compartilhamentos contra operações de engine.)*
3. **Autoridade só do SQL.** Nada de claims do JWT, Redis ou parâmetros do request. O
   vínculo pai/filho de jobs SPLIT/MERGE hoje vem do Redis (`api/deps.py:129-132`); a 0016
   o leva para SQL antes de qualquer compartilhamento existir.
4. **Nega por padrão; NULL nega.** Recurso sem `org_id` (após a 0016), principal ausente
   ou binding expirado nunca autoriza.
5. **404 vs 403.** `403` só quando o principal **efetivo** (key ∩ dono, quando houver key)
   pode ler o recurso; em qualquer outro caso `404`, idêntico a inexistente. `/iam/check`
   responde igual para inexistente e fora de alcance.
6. **Concessão nunca acima do concedente**, inclusive por via indireta: adicionar a
   grupo, editar papel já vinculado, mover recurso para container próprio. Autoconcessão
   proibida.
7. **Bootstrap (`is_admin`/`ADMIN_USER_IDS`)** é acesso de emergência: libera permissões
   de plataforma, engines e IAM, auditado; nunca dados de organização. Principais de
   plataforma não se adicionam a organizações nem se dão bindings de dados; leitura de
   suporte só por break-glass explícito, com prazo, auditoria e aviso à organização (0017).
8. **Sem cache positivo entre requisições.** Bindings carregados uma vez por requisição.
9. **Efeitos pagos decididos onde acontecem.** Uso de engine remota é verificado no
   dispatcher, contra a engine concreta, com autoridade de quem iniciou ∩ dono (0014).
10. **Rollout por evidência, não por tempo.** Antes de `enforce`, comparar offline a
    decisão legada × nova para todo par (usuário, recurso) de um snapshot; shadow em
    runtime só nas checagens por ID. Rollback nunca amplia acesso (keys escopadas não
    voltam a ser keys plenas).

## 5. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Uma spec monolítica | Revisão de 2026-10-06: nada chegava ao usuário antes da última fatia, shadow não provava semântica e rollback ficava acoplado |
| Serviço externo (OpenFGA, SpiceDB, Keycloak) | Infra nova e segunda fonte de verdade sincronizada com o MySQL; o grafo tem 4 níveis |
| OPA/Cedar com políticas em linguagem | Linguagem antes de domínio estável; políticas de usuário viram superfície de ataque |
| Casbin | Não resolve listagem filtrada nem herança por FK; duplicaria a 0009 |
| Estender `access_role_grants` | Quebra invariantes da 0009 (ver §4.2) |
| Materializar binding `owner` por recurso | Milhões de linhas para o que `user_id` já expressa |
| Workspaces = projetos, sem org | Descartado pelo autor: sem raiz de tenant |
| Compartilhar só por projeto | Descartado pelo autor: precisa compartilhar job, pasta e datalake |

## 6. Questões transversais

- [x] Tenancy? → **Decisão (2026-10-06):** organizações; cada usuário ganha uma pessoal.
- [x] Granularidade do compartilhamento? → **Decisão (2026-10-06):** qualquer recurso
  (projeto, pasta, job, datalake), herança só descendente.
- [x] API keys? → **Decisão (2026-10-06):** escopadas, interseção com o dono.
- [x] Uma spec ou várias? → **Decisão (2026-10-06):** guarda-chuva + 0014–0017.
- [ ] `org_admin`/`org_owner` leem todos os dados da org? Proposta: não; papel
  `org_data_reader` explícito e auditado (decidir na 0017).
- [ ] Destino dos recursos de membro removido? Proposta: transferir ao `org_owner` em
  orgs `team` (decidir na 0017).
