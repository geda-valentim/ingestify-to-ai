# Changelog - Hierarquia de Jobs Implementada

> **Registro histórico (2025-10).** Não é mantido; para mudanças posteriores use `git log`. Observação: `workers/tasks_old.py`, citado abaixo, não existe (há um `workers/tasks.py.backup`). Exceção: mudanças de comportamento intencionais que uma spec manda registrar aqui entram na seção abaixo.

## 2026-10: Raiz do repositório enxuta

- Scripts de desenvolvimento movidos para `scripts/dev/`: `start.sh`, `rebuild.sh`, `infra.sh`,
  `run_api.sh`, `run_worker.sh`, `stop_api.sh`, `validate-frontend.sh`. Os alvos do `Makefile`
  (`make start`, `make rebuild`, …) não mudam; os scripts funcionam de qualquer diretório.
- Removidos testes manuais obsoletos da raiz: `test_auth.sh`, `test_pagination.sh`,
  `test_upload_apikey.sh`, `test_conversion_flow.py` (cobertos pela suíte `pytest` e por `scripts/`).
- Os `docker-compose*.yml` ficam na raiz: o host agent fixa o caminho e o hash de cada um.

## 2026-10: Guardar ou apagar os arquivos de origem de documentos

- `POST /upload` e `POST /convert` aceitam `purge_source` (form, padrão `false`; mesmo
  nome e sentido do `/transcribe`). Com `true`, os **arquivos de origem** — o original
  (MinIO `uploads/…` e cópias locais, inclusive o download de URL no diretório de
  trabalho) e os PDFs por página de um PDF dividido (`pages/{job_id}/…`) — são apagados
  quando o job MAIN termina de vez: `completed`, ou `failed`/`partial` **depois de
  esgotadas as tentativas automáticas**; nunca com retry ou página pendente. O Markdown
  fica. A opção e a data ficam nas colunas `jobs.purge_source` e `jobs.source_deleted_at`
  (a opção pedida no próprio request também aparece na configuração solicitada). Falha ao
  apagar não muda o job.
- **Migração aditiva Alembic `b8f20022e1c4`** (head única; também no boot por
  `_add_missing_columns`): colunas `jobs.purge_source`, `jobs.source_deleted_at`,
  `jobs.operation_key` e índice único `uq_pages_job_page (job_id, page_number)`. A migração
  remove antes linhas de página duplicadas (fica a `COMPLETED`, senão a mais recente); o
  boot não apaga nada e pula o índice se houver duplicatas.
- Contabilidade de purge/dedup (`operation_key`, `source_deleted_at`, `purge_source` vindo
  de uma duplicata) **não aparece mais** em `GET /jobs/{id}.configuration` nem em
  "Configuração solicitada"; os campos `source_*` de `GET /jobs/{id}` continuam.
- Split que esgota as tentativas marca o job MAIN `failed` (mensagem `SPLIT_FAILED`) e
  aplica `purge_source` (antes: `processing` para sempre, `DELETE /source` 409 para
  sempre). Um retry do split reaproveita as linhas `pages` (e os page job ids) da
  tentativa anterior e não reenfileira página que já começou.
- Retry automático que não pôde ser publicado (broker fora) marca o job `failed` (ou a
  página `failed`) com `RETRY_NOT_QUEUED`, em vez de `pending` para sempre.
- Monitoramento: `detect_stuck_jobs` agora grava de fato no MySQL (antes alterava objetos
  de uma sessão fechada); página travada → `failed`, recontagem do pai (`partial`) e
  `purge_source`. `auto_retry_failed_pages` reenfileira de verdade pelo mesmo caminho do
  retry manual (antes deixava a página `pending` sem fila); job sem original é pulado.
- **Mudança de contrato:** `POST /admin/jobs/{job_id}/retry-all-failed` reenfileira cada
  página `failed` (mesmo caminho do retry manual, sob o lock do job) e põe o job em
  `processing`; resposta com `pages_retried` e `page_job_ids` (sai
  `pages_marked_for_retry`/`note`); `404` para job inexistente; `409 SOURCE_NOT_AVAILABLE`
  sem mudar nada se o original foi apagado.
- `recount_parent_pages` lê o pai com `SELECT … FOR UPDATE` e as páginas com leitura
  bloqueante: recontagens concorrentes não gravam contagens velhas.
- Frontend: a lista de páginas e o aviso de fila tratam `partial` como estado final (antes
  a página do job consultava para sempre).
- **Mudança de comportamento:** depois do apagamento o retry manual de página responde
  `409 SOURCE_NOT_AVAILABLE` sem mudar nada (antes: página presa em `pending` e `500`), e
  `GET /jobs/{id}/pages/{n}/pdf` responde `410 SOURCE_PURGED` com a data.
- Nova rota `DELETE /jobs/{job_id}/source` (`jobs.delete`): apaga os arquivos de origem
  de um job terminado (documento ou áudio) e responde `{job_id, source_deleted: true,
  source_deleted_at}`; `404` sem arquivos ou de outro usuário; `409 JOB_STILL_PROCESSING`
  enquanto o job, um retry automático ou uma página está pendente.
- `GET /jobs/{job_id}` ganha `source_available`, `source_deleted_at` e `source_deletable`
  (todos do MySQL).
- **Mudança de comportamento (status):** um PDF dividido cujas páginas terminaram todas,
  com alguma falha definitiva, passa a **`partial`** ("N de M páginas falharam…") em vez
  de ficar `processing` para sempre; o retry de página o reabre (`processing`). Entre
  tentativas automáticas, `process_conversion` deixa o job `queued` (antes `failed`), a
  página espera como `pending` (antes `failed`) e o merge mantém o job `processing`.
- **Mudança de comportamento (deduplicação):** a chave inclui a operação (preset do
  Docling numa conversão, perfil numa transcrição); jobs de imagem nunca são devolvidos;
  jobs `failed` **ou `partial`** nunca são devolvidos (reenviar é a nova tentativa). Com
  `purge_source=true` a duplicata passa a apagar a origem (na hora se já terminou); com
  `false`, uma duplicata sem origem (ou que vai apagá-la) não é reaproveitada. A resposta
  de `/upload`, `/convert` e `/transcribe` ganha `duplicate` e `source_available`.
  Consequência: `/upload` (preset padrão `fast`) e `/convert` (sem preset) **não
  deduplicam mais entre si** — o mesmo arquivo enviado aos dois cria dois jobs.
- `DELETE /jobs/{job_id}` passa a apagar o original de qualquer job no bucket certo
  (antes: só transcrições, e sempre no bucket de áudio) e os PDFs por página.
- `/transcribe` grava `purge_source` também em `job_configurations` e apaga o áudio
  também quando a transcrição falha de vez.
- **Idempotency-Key por tentativa** (`/images/analyze` `mode=full` e rostos): uma chave
  cuja última tentativa terminou `failed` cria a tentativa seguinte (job novo) em vez de
  devolver o job falho; respostas trazem `attempt`. Migração aditiva Alembic
  `a7d30021c5e9` (`image_analysis_submissions.attempt`, também em `_ADDED_COLUMNS`).
- Frontend: caixa "Don't keep the original file after converting" no formulário de
  arquivo; botão "Delete original file" habilitado por `source_deletable`; "Original files
  deleted on …"; retry de página escondido (com explicação) sem original; aviso de
  duplicata no upload. Não há a opção nas abas URL/Drive/Dropbox (não guardam original).
- `scripts/dev/start.sh` mostra o próprio caminho (`./scripts/dev/start.sh`).

## 2026-10: Spec 0020 — perfis de execução padrão na instalação

- O root cria e publica um perfil `Padrão — <modelo>` por modelo aprovado do catálogo e
  um perfil `<engine> — <feature>` por binding configurado, e vincula este último quando a
  engine/feature ainda não tem perfil desejado. Roda na criação do root, em todo boot da
  API com root, quando um host agent se registra ou volta, e por
  `scripts/seed_execution_profiles.py` / `python -m shared.access.seed` (`--dry-run`).
- **Mudança de comportamento:** engines vinculadas pela semeadura passam a "gerenciadas"
  (escritores legados de capacidade exigem operação), e engines sem atributos recebem o
  ambiente da instalação. Nada é aplicado, implantado ou reservado.
- O perfil de engine semeado antes de poder ser vinculado é conferido com a configuração
  atual da engine antes do vínculo: se só a semeadura mexeu nele, ganha revisão nova; se um
  admin mexeu, `SEEDED_PROFILE_STALE`. Perfis locais apontam para o host que serve a
  feature/GPU (`HOST_AMBIGUOUS` com mais de um); cooldown segue o `scaledown_window` da
  engine; `ENVIRONMENT` desconhecido ⇒ `ENVIRONMENT_UNKNOWN` (antes contava como
  production); a classificação da engine só é gravada junto com o vínculo.
- O cadastro do root agenda a semeadura em background (a resposta não espera o lock do
  epoch). Mudança de manifest no heartbeat re-semeia no máximo uma vez por minuto por host.
- `register_engine_host.py` valida e prepara o JSON num arquivo temporário (fsync), guarda
  `<arquivo>.bak` e reescreve o alvo no lugar (mesmo inode); arquivo novo nasce `0600`
  com `O_EXCL` (`--identities-group 10001` o deixa `0640`). A API tenta de novo uma vez
  quando lê um JSON parcial.
- **Mudança visível ao cliente (API):** `POST /admin/engines/{id}/operation-plans` com capability
  desabilitada responde `422 RUNTIME_PROFILE_REQUIRED` / `403 ACCESS_DENIED` (antes `503`);
  cooldown sem perfil desejado responde `409 NOTHING_TO_COOL_DOWN`. Nas rotas de controle,
  perfis/acesso e IAM, `detail.message` agora é sempre em português (catálogo único) e vem
  com `next_steps`; `detail.code` não mudou. Ver
  [execution-profiles](features/execution-profiles.md#corpo-de-erro).
- Sem `IAM_MODE=enforce` a semeadura não faz nada (`ACCESS_NOT_ENABLED`). Ver
  [execution-profiles](features/execution-profiles.md#perfis-padrão-da-instalação-spec-0020).

## 2026-10: Spec 0019 — usuário root na primeira inicialização

Ver specs/0019.

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

Ver specs/0018 e a
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

Ver specs/0014.

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
