# Changelog - Hierarquia de Jobs Implementada

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
curl -X POST http://localhost:8000/convert \
  -F "source_type=file" \
  -F "file=@sample.pdf"

# Response: {"job_id": "main-job-uuid", ...}

# 2. Consultar status do main job (ver child jobs)
curl http://localhost:8000/jobs/{main-job-uuid}

# 3. Listar page jobs
curl http://localhost:8000/jobs/{main-job-uuid}/pages

# 4. Consultar resultado de página individual
curl http://localhost:8000/jobs/{page-job-uuid}/result

# 5. Consultar resultado final merged
curl http://localhost:8000/jobs/{main-job-uuid}/result
```
