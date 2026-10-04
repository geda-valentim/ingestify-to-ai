# Arquitetura de Jobs - Doc2MD

> **Parcialmente atualizado (2026-10-04).** A hierarquia MAIN → SPLIT → PAGE → MERGE descrita
> aqui continua correta. A fórmula de progresso, os estados e as filas foram corrigidos
> abaixo; exemplos de payload e a seção de "vantagens" são do desenho original. Para o
> comportamento atual verificado no código, veja
> [features/conversion.md](features/conversion.md) e [features/jobs-api.md](features/jobs-api.md).
> As páginas extraídas ficam no MinIO (`ingestify-pages/pages/{job_id}/page_NNNN.pdf`).

## 📊 Hierarquia de Jobs

```
MAIN JOB (user request)
  └─> SPLIT JOB (divide PDF)
       ├─> PAGE JOB 1 (converte página 1)
       ├─> PAGE JOB 2 (converte página 2)
       ├─> PAGE JOB 3 (converte página 3)
       └─> ...
       └─> MERGE JOB (combina resultados)
```

## 🗂️ Estrutura de Dados no Redis

### Main Job
```
job:{main_job_id}:status = {
  "type": "main",
  "status": "processing",
  "progress": 0,
  "created_at": "...",
  "started_at": "...",
  "completed_at": null,
  "error": null,
  "source_type": "file",
  "file_format": "pdf",
  "total_pages": 10,
  "child_jobs": {
    "split_job_id": "split-abc-123",
    "page_jobs": ["page-1-abc", "page-2-abc", ...],
    "merge_job_id": "merge-xyz-789"
  }
}
```

### Split Job
```
job:{split_job_id}:status = {
  "type": "split",
  "status": "completed",
  "parent_job_id": "main-abc-123",
  "total_pages": 10,
  "pages_created": 10,
  "created_at": "...",
  "completed_at": "..."
}
```

### Page Job (cada página)
```
job:{page_job_id}:status = {
  "type": "page",
  "status": "completed",
  "parent_job_id": "main-abc-123",
  "page_number": 1,
  "created_at": "...",
  "started_at": "...",
  "completed_at": "...",
  "error": null
}

job:{page_job_id}:result = {
  "markdown": "# Conteúdo da página 1...",
  "metadata": {
    "page_number": 1,
    "words": 250,
    "size_bytes": 50000
  }
}
```

### Merge Job
```
job:{merge_job_id}:status = {
  "type": "merge",
  "status": "processing",
  "parent_job_id": "main-abc-123",
  "total_pages": 10,
  "pages_merged": 0,
  "created_at": "...",
  "completed_at": null
}

job:{merge_job_id}:result = {
  "markdown": "# Combined from all pages...",
  "metadata": {
    "pages": 10,
    "total_words": 2500,
    "total_size_bytes": 500000
  }
}
```

## 🔄 Fluxo de Processamento

### 1. Upload (Main Job Created)
```python
POST /convert
  → main_job_id = uuid4()
  → redis.set_job_status(main_job_id, "queued")
  → celery.process_conversion.delay(main_job_id)
  → return main_job_id
```

### 2. Process Conversion Task
```python
def process_conversion(main_job_id):
    # Download file
    file_path = download_file()

    if is_pdf_multi_page(file_path):
        # Create SPLIT JOB
        split_job_id = create_split_job(main_job_id)
        celery.split_pdf.delay(split_job_id, file_path)
    else:
        # Convert directly
        result = convert_to_markdown(file_path)
        store_result(main_job_id, result)
```

### 3. Split PDF Task
```python
def split_pdf(split_job_id):
    parent_job = get_parent_job(split_job_id)

    # Split into pages
    page_files = pdf_splitter.split(file_path)

    # Create PAGE JOBS
    page_job_ids = []
    for page_num, page_file in page_files:
        page_job_id = create_page_job(parent_job.id, page_num, page_file)
        page_job_ids.append(page_job_id)

        # Launch page conversion
        celery.convert_page.delay(page_job_id)

    # Update parent job
    update_child_jobs(parent_job.id, page_jobs=page_job_ids)

    # Mark split as completed
    complete_job(split_job_id)
```

### 4. Convert Page Task
```python
def convert_page(page_job_id):
    page_job = get_job(page_job_id)

    # Convert page
    result = docling.convert(page_job.page_file_path)

    # Store page result
    store_result(page_job_id, result)

    # Mark page as completed
    complete_job(page_job_id)

    # Check if all pages completed
    parent_job = get_parent_job(page_job_id)
    if all_pages_completed(parent_job.id):
        # Create MERGE JOB
        merge_job_id = create_merge_job(parent_job.id)
        celery.merge_pages.delay(merge_job_id)
```

### 5. Merge Pages Task
```python
def merge_pages(merge_job_id):
    parent_job = get_parent_job(merge_job_id)
    page_jobs = get_all_page_jobs(parent_job.id)

    # Combine all pages in order
    combined_markdown = ""
    for page_job in sorted(page_jobs, key=lambda x: x.page_number):
        page_result = get_result(page_job.id)
        combined_markdown += page_result.markdown + "\n\n---\n\n"

    # Store merged result
    store_result(merge_job_id, combined_markdown)

    # Mark merge as completed
    complete_job(merge_job_id)

    # Mark parent as completed
    complete_job(parent_job.id)
```

## 📡 Endpoints Atualizados

### GET /jobs/{job_id}
Retorna status do job (qualquer tipo)

```json
// Main Job
{
  "job_id": "main-abc-123",
  "type": "main",
  "status": "processing",
  "progress": 40,
  "total_pages": 10,
  "pages_completed": 4,
  "child_jobs": {
    "split_job_id": "split-abc-123",
    "page_jobs": ["page-1-abc", "page-2-abc", ...],
    "merge_job_id": null
  },
  "created_at": "...",
  "started_at": "...",
  "completed_at": null
}

// Page Job
{
  "job_id": "page-1-abc",
  "type": "page",
  "status": "completed",
  "parent_job_id": "main-abc-123",
  "page_number": 1,
  "created_at": "...",
  "completed_at": "..."
}
```

### GET /jobs/{job_id}/result
Retorna resultado do job

```json
// Main Job Result (após merge)
{
  "job_id": "main-abc-123",
  "type": "main",
  "result": {
    "markdown": "# Combined...",
    "metadata": {
      "pages": 10,
      "total_words": 2500
    }
  }
}

// Page Job Result (página individual) ⭐ NOVO
{
  "job_id": "page-1-abc",
  "type": "page",
  "page_number": 1,
  "result": {
    "markdown": "# Página 1...",
    "metadata": {
      "page_number": 1,
      "words": 250
    }
  }
}
```

### GET /jobs/{main_job_id}/pages
Lista todas as páginas do job principal

```json
{
  "job_id": "main-abc-123",
  "total_pages": 10,
  "pages": [
    {
      "page_number": 1,
      "job_id": "page-1-abc",
      "status": "completed",
      "url": "/jobs/page-1-abc/result"
    },
    {
      "page_number": 2,
      "job_id": "page-2-abc",
      "status": "processing",
      "url": "/jobs/page-2-abc/result"
    }
  ]
}
```

### GET /jobs/{page_job_id}/result ⭐ NOVO
Consulta resultado de UMA página específica

```bash
# Exemplo
curl http://localhost:8080/jobs/page-1-abc/result

# Response
{
  "job_id": "page-1-abc",
  "type": "page",
  "page_number": 1,
  "parent_job_id": "main-abc-123",
  "status": "completed",
  "result": {
    "markdown": "# Conteúdo da página 1...",
    "metadata": {
      "page_number": 1,
      "words": 250,
      "size_bytes": 50000
    }
  },
  "completed_at": "2025-10-01T18:30:00Z"
}
```

## 🎯 Casos de Uso

### Caso 1: Consultar Progresso Geral
```bash
GET /jobs/main-abc-123
→ "progress": 40, "pages_completed": 4/10
```

### Caso 2: Ver Todas as Páginas
```bash
GET /jobs/main-abc-123/pages
→ Lista de 10 páginas com seus job_ids
```

### Caso 3: Ver Página Específica (Individual)
```bash
GET /jobs/page-5-abc/result
→ Markdown da página 5 isoladamente
```

### Caso 4: Ver Resultado Completo (Merged)
```bash
GET /jobs/main-abc-123/result
→ Markdown de todas páginas combinadas
```

## 🔑 Vantagens da Nova Arquitetura

### 1. **Rastreabilidade Completa**
- Cada operação tem seu próprio job_id
- Fácil debug e monitoramento
- Histórico completo do processamento

### 2. **Consulta Granular**
- Pode consultar página individual: `/jobs/page-3-abc/result`
- Pode consultar resultado final: `/jobs/main-abc-123/result`
- Pode consultar status de split/merge

### 3. **Retry Inteligente**
- Se página 5 falhar, retry apenas dela
- Se merge falhar, retry apenas merge (páginas já processadas)
- Não precisa refazer split se já foi feito

### 4. **Flexibilidade**
- Frontend pode mostrar páginas individualmente
- Pode fazer download parcial (só página X)
- Pode refazer apenas parte do processo

### 5. **Escalabilidade**
- Split, pages e merge rodam todos na mesma fila `ingestify` (serviço `worker`).
  As filas dedicadas que existem hoje são `ingestify-audio` (transcrição) e
  `ingestify-vision` (Florence-2) — não há fila por tipo de job de documento.

## 📊 Tipos de Jobs

```python
class JobType(str, Enum):
    MAIN = "main"          # Job principal do usuário
    SPLIT = "split"        # Divisão de PDF em páginas
    PAGE = "page"          # Conversão de página individual
    MERGE = "merge"        # Combinação de páginas
    DOWNLOAD = "download"  # Download de URL/GDrive/Dropbox (opcional)
```

## 🔄 Estados dos Jobs

```python
class JobStatus(str, Enum):
    PENDING = "pending"       # Pendente (usado internamente; no MySQL é o estado inicial)
    QUEUED = "queued"         # Na fila
    PROCESSING = "processing" # Sendo processado
    COMPLETED = "completed"   # Concluído com sucesso
    FAILED = "failed"         # Falhou
    CANCELLED = "cancelled"   # Cancelado pelo usuário
```

## 📈 Cálculo de Progress

### Main Job Progress

> **Corrigido em 2026-10-04.** O cálculo 10/80/10 que constava aqui nunca foi implementado.
> A fórmula real está inline em `backend/workers/tasks.py` (`_run_page_conversion`):

```python
# 10% ao iniciar o MAIN; depois, a cada página concluída:
completed_pages = redis_client.count_completed_page_jobs(parent_job_id)
total_pages = redis_client.get_job_pages_total(parent_job_id)
progress = 20 + int((completed_pages / total_pages) * 70)
# 100% quando o merge_pages_task conclui
```

## 🗃️ Schema Unificado

```python
class Job(BaseModel):
    job_id: UUID
    type: JobType
    status: JobStatus
    parent_job_id: Optional[UUID] = None
    progress: int = 0
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    # Type-specific fields
    page_number: Optional[int] = None         # For PAGE jobs
    total_pages: Optional[int] = None          # For MAIN/SPLIT jobs
    child_job_ids: Optional[List[UUID]] = None # For MAIN jobs
```

## 🚀 Implementação

### Prioridade de Tasks

1. ✅ Atualizar schemas com JobType
2. ✅ Criar task `split_pdf_task`
3. ✅ Criar task `merge_pages_task`
4. ✅ Atualizar task `process_page` para job_id próprio
5. ✅ Atualizar Redis client para hierarquia
6. ✅ Atualizar endpoints para suportar diferentes tipos
7. ✅ Adicionar endpoint para página individual

Esta arquitetura dá **visibilidade completa** e **controle granular** de todo o processo! 🎯
