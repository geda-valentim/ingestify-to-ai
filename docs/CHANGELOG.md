# Changelog - Hierarquia de Jobs Implementada

> **Registro histórico (2025-10).** Não é mantido; para mudanças posteriores use `git log`. Observação: `workers/tasks_old.py`, citado abaixo, não existe (há um `workers/tasks.py.backup`). Exceção: mudanças de comportamento intencionais que uma spec manda registrar aqui entram na seção abaixo.

## 2026-10: Spec 0020 — perfis de execução padrão na instalação

- O root cria e publica um perfil `Padrão — <modelo>` por modelo aprovado do catálogo e
  um perfil `<engine> — <feature>` por binding configurado, e vincula este último quando a
  engine/feature ainda não tem perfil desejado. Roda na criação do root, em todo boot da
  API com root, quando um host agent se registra ou volta, e por
  `scripts/seed_execution_profiles.py` / `python -m shared.access.seed` (`--dry-run`).
- **Mudança de comportamento:** engines vinculadas pela semeadura passam a "gerenciadas"
  (escritores legados de capacidade exigem operação), e engines sem atributos recebem o
  ambiente da instalação. Nada é aplicado, implantado ou reservado.
- Sem `IAM_MODE=enforce` a semeadura não faz nada (`ACCESS_NOT_ENABLED`). Ver
  [execution-profiles](features/execution-profiles.md#perfis-padrão-da-instalação-spec-0020).

## 2026-10: Spec 0019 — usuário root na primeira inicialização

Ver [specs/0019](specs/0019-usuario-root-na-primeira-inicializacao.md).

- **A primeira conta cadastrada numa instalação sem nenhum usuário vira root** (`users.root_slot = 1`,
  `is_admin = true`), único por índice único e irrevogável pela aplicação. Migration
  `f1c90019d3e4` (depois de `d4e80018a2b6`); a coluna também é criada no boot.
- **Mudança de comportamento:** numa instalação **nova** (sem usuários) com
  `ENVIRONMENT=production` e sem `ROOT_SETUP_TOKEN`, o cadastro fica fechado
  (`403 ROOT_SETUP_TOKEN_REQUIRED`) até o token ser configurado. Instalações com usuários não
  mudam; designe o root com `make_admin.py --root`. O compose repassa `ROOT_SETUP_TOKEN` à API.
- `GET /auth/setup` (público, com `root_pending`), `is_root` em `/auth/me`, `make_admin.py --root`.
- `PUT /admin/access/subjects/{id}/state` recusa desativar ou rebaixar o root (`409 ROOT_IMMUTABLE`).

## 2026-10: Spec 0018 — IAM: convergência do RBAC/ABAC de engines (0009)

Ver [specs/0018](specs/0018-iam-convergencia-do-rbac-abac-de-engines.md) e a
[seção 6 do runbook](runbooks/execution-profiles-access.md#6-convergência-no-iam-spec-0018).

- **Grants de engines viram `iam_bindings`** da família `engines`, com o **mesmo id** do grant
  (decisões e auditoria que citam `grant_id` continuam válidas). A decisão da 0009 não muda:
  `policy.authorize`, "um grant satisfaz integralmente", vários grants do mesmo papel,
  delegação por envelope, epoch e admissão de efeito. Papéis de plataforma e de engines nunca
  se enxergam (`/iam/check`, `platform_roles` e `ROLE_ABOVE_GRANTOR` ignoram engines).
- **Migration `d4e80018a2b6`** (depois de `03e70014b8c5`): colunas `permissions`,
  `condition_ref`, `delegation`, `parent_id`, FKs e índice `ix_iam_bindings_subject_role` em
  `iam_bindings`; cópia + reconciliação + validação sob o lock do epoch; marcador
  `0018_engine_bindings`. A reconciliação roda também a cada boot da API e dos workers e só
  restringe. Gate antes do deploy: `python -m shared.iam.engine_equivalence` (ou
  `scripts/iam_engine_equivalence.py`) com 0 divergências.
- **`access_role_grants` vira espelho só-escrita** para rollback: toda concessão/revogação de
  engines grava a linha de mesmo id na mesma transação. O downgrade aplica nela o mais
  restritivo antes de apagar os bindings `engines`.
- **Flag:** `IAM_MODE=enforce` liga o acesso de engines; `ENGINE_ACCESS_ENABLED` vira alias
  depreciado que, quando definido (`true`/`false`), vence com aviso no boot; vazio = não
  definido. `ENGINE_ACCESS_ENABLED=false` continua sendo a alavanca de emergência. Os compose
  files passam `IAM_MODE` e `ENGINE_ACCESS_ENABLED` (default vazio) a todos os processos que
  decidem engines, e cada um registra `engine_access_enabled=` no boot. **Atenção:** antes
  desta release `ENGINE_ACCESS_ENABLED` ausente valia `false`; agora segue `IAM_MODE`. Uma
  instalação com `IAM_MODE=enforce` e a variável ausente (nunca ligou engines, ou desligou
  apagando a linha) passa a ligar o enforcement de engines e a exigir o esquema da 0009, e
  os grants ativos de `access_role_grants` voltam a valer: fixe `ENGINE_ACCESS_ENABLED=false`
  ou revise/revogue esses grants antes do deploy (runbook §6.1).
- **InnoDB:** as leituras com lock da família `engines` travam bindings só pela chave
  primária (sem gap): uma admissão de efeito de um filho delegado não entra mais em deadlock
  com uma concessão de plataforma ao dono do pai. Conceder e revogar papéis `engines` leem
  autoridade e delegação com lock, vendo uma revogação do pai mesmo com snapshot antigo.
  Testes opt-in em MySQL (`ENGINE_CONTROL_TEST_DATABASE_URL`) para concorrência e para o
  round trip da migração.
- **Boot:** com `IAM_MODE` diferente de `off` (inclusive `shadow` com engines desligado) ou
  engines ligado, a API não sobe sem a migração da 0018 (colunas, FKs, índice), e esta exige a
  migração da 0009 mesmo em instalações só com IAM de plataforma.
- **API:** `/admin/iam/bindings*` administra as duas famílias, com regras por família
  (corpo ganha `permissions`, `condition_ref`, `delegation`; resposta ganha `family` e
  `parent_id`). `/admin/access/grants*` ficam como aliases **depreciados** com o contrato da
  0009, só para papéis de engines.
- **Mudança intencional:** autoconcessão de papel de engines passa a ser recusada
  (`422 SELF_GRANT`) nas duas rotas.
- **Auditoria:** concessões e revogações das duas famílias gravam `iam.binding.grant` /
  `iam.binding.revoke` em `target_type="iam_binding"`; linhas antigas (`access`) intactas.
- **Frontend:** uma tela **Admin → Acesso** (`/admin/access`) com abas Concessões, Políticas,
  Atributos de engine, Recursos e Principais de instalação; `/admin/platform-access` redireciona
  para ela e o menu tem um item "Acesso".

## 2026-10: Spec 0014 — IAM: núcleo de decisão e papéis de plataforma

Ver [specs/0014](specs/0014-iam-nucleo-de-decisao-e-papeis-de-plataforma.md).

- **`IAM_MODE`** (`off` | `shadow` | `enforce`, padrão `off`). Em `off` as rotas da API decidem
  pela regra legada (`is_effective_admin`, dono do recurso) e os bindings ficam inertes; `shadow`
  decide pelo legado e registra `iam_shadow_divergence` no log; `enforce` decide por
  `shared/iam/decide.py`. Antes de `enforce`, rodar `scripts/iam_equivalence.py` contra o
  snapshot (CA3): precisa sair com 0 divergências.
- **Migration `a1c40014e7b2` (`iam_bindings`)**: aditiva, só `CREATE TABLE iam_bindings`
  (marcador `0014_iam_bindings` em `app_migrations`). Nenhuma tabela da 0009 muda.
- **Mudança intencional (CA10):** `user_period_limit_usd` vale também em rotas com
  `remote_allowed_for=admins`, **bootstrap incluído**. Jobs de admins em rotas restritas passam a
  receber recusa `user_cap` quando o teto da rota é atingido; antes gastavam sem teto.
- **Mudança intencional (CA9):** o dispatcher decide `engines.remote.use` do dono a cada placement
  remoto em rota `admins`, em vez de confiar só no `remote_allowed` gravado no submit. Rebaixar um
  admin (ou revogar o binding) alcança páginas já enfileiradas: vão para o caminho local ou seguem
  `on_no_engine`. Isso e o CA10 **não dependem de `IAM_MODE`**: em `off` o dispatcher usa a regra
  legada, mas a cada placement.
- `/auth/me` ganha `bootstrap` e `platform_roles`; `permissions` passa a incluir as permissões de
  plataforma. Novas rotas `/iam/permissions`, `/iam/check` e `/admin/iam/bindings*`.
- Na UI de roteamento, `remote_allowed_for=admins` aparece como "restricted (needs the remote engine
  permission)".

## 2025-10-01: Job Hierarchy Architecture + CLI Tests

### ✅ Endpoint de Upload Ajustado (Adicionado)

#### Melhorias no POST /convert:

1. **Otimizações de Performance:**
   - Arquivo lido apenas 1 vez (antes: 2 vezes)
   - Uso de Path para manipulação de caminhos
   - Validação de tamanho antes de salvar

2. **Tratamento de Erros:**
   - ImportError: HTTP 503 se Celery indisponível
   - Exception: HTTP 500 com mensagem específica
   - Job marcado como "failed" no Redis em caso de erro

3. **Logging Melhorado:**
   - Log de upload (filename, size)
   - Log de MAIN JOB criado
   - Log de arquivo salvo (path)
   - Log de job enfileirado
   - Log de erros com traceback

4. **Teste Criado:**
   - scripts/test_upload_endpoint.py
   - Simula fluxo completo: MAIN → SPLIT → PAGES → MERGE
   - Resultado: ✅ PASSOU (8 jobs criados, progresso 0% → 100%)

### ✅ Testes CLI Realizados (Adicionado)

#### Scripts de Teste Criados:

1. **scripts/test_pdf_split.py** - Teste de divisão de PDF
   - Testa PDFSplitter sem Docker
   - Divide AI-50p.pdf em 50 páginas
   - Resultado: ✅ PASSOU
   - 50 arquivos criados (page_0001.pdf a page_0050.pdf)
   - Tamanho médio: 51 KB por página

2. **scripts/test_page_jobs.py** - Simulação de hierarquia de jobs
   - Simula fluxo completo MAIN → SPLIT → PAGES → MERGE
   - Cria 53 jobs (1+1+50+1)
   - Mostra progresso 0% → 100%
   - Resultado: ✅ PASSOU
   - Hierarquia demonstrada com sucesso

3. **scripts/test_cli.py** - Cliente CLI interativo
   - 7 funcionalidades testáveis
   - Menu interativo com cores
   - Requer API rodando
   - Status: ⏳ Aguardando Docker build

4. **Documentação criada:**
   - scripts/README.md - Guia do cliente CLI
   - scripts/README_TESTS.md - Resultados completos dos testes
   - TEST_RESULTS.md - Documento de validação
   - QUICK_START.md - Guia rápido

#### Resultados dos Testes:

```
TESTE 1: PDFSplitter
✓ PDF dividido: 50 páginas
✓ Arquivos criados: 2.6 MB total
✓ Overhead: 167.9% (esperado)

TESTE 2: Job Hierarchy Simulation
✓ 53 jobs criados corretamente
✓ Progresso: 0% → 10% → 20% → ... → 90% → 100%
✓ Hierarquia parent-child validada
✓ Processamento paralelo simulado (5 workers, 10 batches)
```

### ✅ Completed Implementation

#### 1. **workers/tasks.py** (anteriormente tasks_new.py)
Implementação completa da arquitetura hierárquica de jobs:

- **process_conversion** (MAIN JOB)
  - Ponto de entrada para conversões
  - Faz download do documento
  - Cria split_job se PDF multi-página
  - Converte diretamente se documento único

- **split_pdf_task** (SPLIT JOB)
  - Divide PDF em páginas individuais
  - Cria page_job para cada página
  - Lança convert_page_task em paralelo

- **convert_page_task** (PAGE JOB)
  - Converte página individual com Docling
  - Atualiza progresso do main job
  - Triggers merge_job quando todas páginas completam

- **merge_pages_task** (MERGE JOB)
  - Combina resultados de todas as páginas
  - Armazena resultado final no main job
  - Marca main job como completed
  - Limpa arquivos temporários

#### 2. **shared/redis_client.py**
Métodos de hierarquia adicionados:

- `add_child_job()` - Liga child ao parent
- `get_child_jobs()` - Retorna children do parent
- `get_page_jobs()` - Lista page job IDs
- `count_completed_page_jobs()` - Conta páginas completas
- `count_failed_page_jobs()` - Conta páginas falhas
- `all_page_jobs_completed()` - Verifica se pode fazer merge

Atualizado `set_job_status()` para incluir:
- `job_type` (main/split/page/merge)
- `parent_job_id` (para child jobs)
- `page_number` (para page jobs)
- `child_job_ids` (dict com split_job_id, page_job_ids, merge_job_id)

#### 3. **api/routes.py**
Endpoints atualizados para suportar hierarquia:

**GET /jobs/{job_id}** - Retorna status de qualquer tipo de job
- Detecta job_type automaticamente
- Para MAIN: retorna child_jobs, total_pages, pages_completed
- Para PAGE: retorna page_number, parent_job_id
- Para SPLIT/MERGE: retorna parent_job_id

**GET /jobs/{job_id}/result** - Resultado de main ou page individual
- MAIN jobs: retorna resultado merged (armazenado pelo merge job)
- PAGE jobs: retorna resultado individual da página
- Inclui page_number e parent_job_id para page jobs

**GET /jobs/{job_id}/pages** - Lista page jobs com IDs individuais
- Retorna `PageJobInfo` com:
  - `page_number`: número da página
  - `job_id`: UUID do page job
  - `status`: status do page job
  - `url`: endpoint para consultar resultado (`/jobs/{page_job_id}/result`)

#### 4. **shared/schemas.py**
Schemas atualizados:

- `JobType` enum: MAIN, SPLIT, PAGE, MERGE, DOWNLOAD
- `JobStatus` enum: QUEUED, PROCESSING, COMPLETED, FAILED, CANCELLED
- `ChildJobs`: model para child job relationships
- `PageJobInfo`: informação de page job individual com URL
- `JobStatusResponse`: updated com type, parent_job_id, child_jobs
- `JobResultResponse`: updated com type, page_number, parent_job_id

### Fluxo Completo

```
1. POST /convert
   └─> Cria MAIN JOB
       └─> Lança process_conversion task
           ├─> Download (10-20%)
           └─> Se PDF multi-página:
               └─> Cria SPLIT JOB
                   └─> split_pdf_task
                       ├─> Divide PDF
                       └─> Cria PAGE JOBS
                           ├─> page_job_1 (convert_page_task)
                           ├─> page_job_2 (convert_page_task)
                           └─> page_job_N (convert_page_task)
                               └─> Última página triggers:
                                   └─> Cria MERGE JOB
                                       └─> merge_pages_task
                                           ├─> Combina resultados
                                           ├─> Armazena em MAIN
                                           └─> Marca MAIN como completed

2. GET /jobs/{main_job_id}
   └─> Retorna status com:
       - type: "main"
       - child_jobs: {split_job_id, page_job_ids[], merge_job_id}
       - total_pages, pages_completed, pages_failed
       - progress: calculado baseado em páginas

3. GET /jobs/{main_job_id}/pages
   └─> Retorna lista de PageJobInfo:
       [{page_number: 1, job_id: "page_job_uuid_1", url: "/jobs/page_job_uuid_1/result"}, ...]

4. GET /jobs/{page_job_id}/result
   └─> Retorna resultado individual da página com page_number

5. GET /jobs/{main_job_id}/result
   └─> Retorna resultado merged (armazenado pelo merge job)
```

### Cálculo de Progresso

- **Download**: 10-20%
- **Pages**: 20-90% (70% dividido pelo número de páginas)
- **Merge**: 90-100%

Fórmula em `convert_page_task`:
```python
pages_progress = int((completed_pages / total_pages) * 70)
main_progress = 20 + pages_progress
```

### Rastreabilidade Completa

Agora é possível:
1. ✅ Consultar status de qualquer job (main, split, page, merge)
2. ✅ Obter resultado de qualquer page individualmente
3. ✅ Ver hierarquia completa de jobs (parent/child relationships)
4. ✅ Rastrear progresso granular por página
5. ✅ Retry individual de qualquer operação

### Arquivos Modificados

- `workers/tasks.py` (renomeado de tasks_new.py)
- `workers/tasks_old.py` (backup do arquivo antigo)
- `shared/redis_client.py` (métodos de hierarquia)
- `api/routes.py` (endpoints atualizados)
- `shared/schemas.py` (já estava atualizado)

### Próximos Passos para Testes

1. Rebuild Docker containers (demora devido ao PyTorch no Docling)
2. Testar fluxo completo:
   - Upload de PDF multi-página
   - Verificar split job criado
   - Verificar page jobs executando em paralelo
   - Consultar resultados individuais de páginas
   - Verificar merge job ao final
   - Consultar resultado final merged

### Como Testar

```bash
# 1. Upload PDF multi-página
curl -X POST http://localhost:8080/convert \
  -F "source_type=file" \
  -F "file=@sample.pdf"

# Response: {"job_id": "main-job-uuid", ...}

# 2. Consultar status do main job (ver child jobs)
curl http://localhost:8080/jobs/{main-job-uuid}

# 3. Listar page jobs
curl http://localhost:8080/jobs/{main-job-uuid}/pages

# 4. Consultar resultado de página individual
curl http://localhost:8080/jobs/{page-job-uuid}/result

# 5. Consultar resultado final merged
curl http://localhost:8080/jobs/{main-job-uuid}/result
```
