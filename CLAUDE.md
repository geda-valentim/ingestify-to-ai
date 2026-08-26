# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Ingestify** is a full-stack document conversion platform with a Next.js frontend and Python backend API. The system converts documents (PDF, DOCX, HTML, etc.) to Markdown format using Docling, with a distributed architecture using FastAPI, Celery workers, and Redis for scalable document processing.

**Monorepo Structure:**
- **frontend/** - Next.js 15 + React 19 web application
- **backend/** - Python FastAPI + Celery worker backend

## Architecture

### Backend: layered, not hexagonal

O backend é organizado em três pacotes, e a dependência flui numa direção só:

```
backend/
├── api/          # 🌐 Rotas FastAPI, autorização (deps.py), schemas de request/response
├── workers/      # ⚙️ Tasks Celery: conversão, split, merge, monitoring
└── shared/       # 🔧 Config, models SQLAlchemy, clientes (Redis, MinIO, Elasticsearch)
```

`api/` e `workers/` dependem de `shared/`; `shared/` não depende de nenhum dos dois.

> **Nota histórica:** o repositório já teve `domain/`, `application/`, `infrastructure/`
> e `presentation/` seguindo Clean Architecture. Essas camadas nunca foram ligadas —
> nenhum módulo vivo as importava, e nem eram copiadas para as imagens Docker. Foram
> removidas em 2026-08-26 após duas análises independentes; ver
> [docs/specs/0001-remover-clean-architecture-morta.md](docs/specs/0001-remover-clean-architecture-morta.md).
> Para recuperá-las: `git show 9b6b876:backend/domain/...`

### Four-Tier System (Infraestrutura)

1. **Frontend Layer** ([frontend/](frontend/)) - Next.js web application for document uploads and viewing results
2. **API Layer** ([backend/api/](backend/api/)) - FastAPI REST endpoints
3. **Message Broker** - Redis handles task queuing (Celery) and result caching
4. **Worker Layer** ([backend/workers/](backend/workers/)) - Celery workers process conversions with Docling in parallel

### Key Design: Hierarchical Job System

The system uses a sophisticated job hierarchy for processing multi-page PDFs:

```
MAIN JOB (user request)
  └─> SPLIT JOB (divides PDF)
       ├─> PAGE JOB 1 (converts page 1)
       ├─> PAGE JOB 2 (converts page 2)
       └─> MERGE JOB (combines results)
```

**Job Types** (see [shared/schemas.py](shared/schemas.py)):
- `MAIN` - User's original request
- `SPLIT` - PDF division into pages
- `PAGE` - Individual page conversion (parallel processing)
- `MERGE` - Combining page results
- `DOWNLOAD` - External source downloads

This architecture enables:
- Parallel processing of PDF pages
- Granular progress tracking per page
- Individual page result retrieval
- Intelligent retry (only failed pages, not entire document)

## Development Commands

### Environment Setup
```bash
# Frontend environment
cp frontend/.env.example frontend/.env.local
# Edit NEXT_PUBLIC_API_URL if needed (default: http://localhost:8000)

# Backend environment (optional, has sensible defaults)
# Environment variables are defined in backend/shared/config.py
# Override via docker-compose.yml or .env file
```

### Start Services
```bash
# Full stack with Docker Compose (recommended for production-like environment)
docker compose up -d --build
# Services:
# - Frontend: http://localhost:3000
# - API: http://localhost:8000
# - API Docs: http://localhost:8000/docs

# Development mode with docker-compose.dev.yml (faster iteration)
docker compose -f docker-compose.dev.yml up -d

# Scale workers for heavy loads
docker compose up -d --scale worker=5

# Local development (hybrid - services in Docker, code running locally)
# Terminal 1: Start infrastructure services only
docker compose up -d redis elasticsearch

# Terminal 2: Frontend (with hot reload)
cd frontend && npm run dev
# Access: http://localhost:3000

# Terminal 3: API (with auto-reload)
./run_api.sh  # Runs on port 8080
# Access: http://localhost:8080/docs

# Terminal 4: Worker (for background processing)
./run_worker.sh
```

### Logs & Monitoring
```bash
# View logs
docker compose logs -f api      # API logs
docker compose logs -f worker   # Worker logs
docker compose logs -f redis    # Redis logs

# Check status
docker compose ps
curl http://localhost:8000/health
```

### Testing
```bash
# Backend tests
cd backend
pytest tests/ -v

# Interactive API testing (recommended)
python scripts/test_cli.py

# Test PDF splitting (standalone, no Docker)
python scripts/test_pdf_split.py

# Test Docling conversion (standalone)
python scripts/test_docling_conversion.py

# Simulate hierarchical job workflow
python scripts/test_page_jobs.py

# Test conversion via curl
curl -X POST http://localhost:8000/convert \
  -F "source_type=file" \
  -F "file=@test.pdf"

# Shell-based endpoint tests
./scripts/tests/test_pages.sh
./scripts/tests/test_page_endpoints.sh
```

### Rebuild & Scripts
```bash
# Quick rebuild (recommended)
./rebuild.sh

# Start all services
./start.sh

# Test authentication
./test_auth.sh

# Or manually
docker compose down
docker compose up -d --build
```

## Code Structure

```
doc2md/                          # Monorepo root
├── README.md                    # Main documentation
├── CLAUDE.md                    # This file - Claude Code guide
├── docker-compose.yml           # Full stack orchestration
├── .gitignore                   # Git ignore (merged frontend + backend)
│
├── frontend/                    # 🎨 Next.js Frontend
│   ├── app/                     # Next.js App Router
│   ├── components/              # React components
│   ├── lib/                     # Utilities and API client
│   ├── hooks/                   # Custom React hooks
│   ├── types/                   # TypeScript types
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── .env.local               # Frontend environment
│
├── backend/                     # 🐍 Python Backend
│   ├── api/                     # 🌐 FastAPI layer
│   │   ├── main.py              # App initialization, CORS
│   │   ├── routes.py            # Document conversion endpoints
│   │   ├── auth_routes.py       # Authentication endpoints
│   │   └── apikey_routes.py     # API key management
│   ├── workers/                 # ⚙️ Celery workers
│   │   ├── celery_app.py        # Celery config
│   │   ├── tasks.py             # Task definitions
│   │   ├── converter.py         # Docling integration
│   │   └── sources.py           # Source handlers
│   ├── shared/                  # 🔧 Shared utilities
│   │   ├── config.py            # Environment settings
│   │   ├── schemas.py           # Pydantic models
│   │   ├── redis_client.py      # Redis operations
│   │   ├── pdf_splitter.py      # PDF splitting
│   │   ├── database.py          # SQLAlchemy setup
│   │   ├── models.py            # Database models
│   │   ├── auth.py              # Authentication utilities
│   │   └── elasticsearch_client.py  # Elasticsearch client
│   ├── tests/                   # ✅ Unit tests
│   ├── requirements.txt         # Python dependencies
│   └── pytest.ini               # Pytest configuration
│
├── docker/                      # 🐳 Docker files
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   └── Dockerfile.frontend
│
├── docs/                        # 📚 Documentation
│   ├── SPECS.md                 # API specifications
│   ├── RF.md                    # Functional requirements
│   ├── RNF.md                   # Non-functional requirements
│   ├── ARCHITECTURE_JOBS.md     # Job hierarchy deep dive
│   ├── TASKS.md                 # Implementation tasks
│   ├── STATUS.md                # Project status
│   ├── EXECUTE.md               # Execution guide
│   ├── CHANGELOG.md             # Version history
│   ├── DOCKER_OPTIMIZATION.md   # Docker tuning guide
│   └── TEST_RESULTS.md          # Test reports
│
├── scripts/                     # 🛠️ Utility scripts
│   ├── README.md                # Scripts documentation
│   ├── test_*.py                # Test scripts (Python)
│   └── tests/                   # Test scripts (shell)
│
└── tmp/                         # 📁 Temporary files (gitignored)
```

### Frontend Layer ([frontend/](frontend/))
- **app/** - Next.js App Router pages and layouts
- **components/** - Reusable React components (shadcn/ui + custom)
- **lib/** - API client, utilities, state management (Zustand)
- **hooks/** - Custom React hooks
- Built with: Next.js 15, React 19, TypeScript, Tailwind CSS, TanStack Query

### Backend Shared Layer ([backend/shared/](backend/shared/))
- **config.py** - Settings from environment variables (Pydantic Settings)
- **schemas.py** - All Pydantic models for requests/responses
- **redis_client.py** - Redis operations for job status, results, and page tracking
- **pdf_splitter.py** - PDF page splitting logic using PyPDF2
- **database.py** - SQLAlchemy database setup
- **models.py** - Database models (User, Job, Page, APIKey)
- **auth.py** - JWT authentication utilities
- **elasticsearch_client.py** - Elasticsearch client for search

### Backend API Layer ([backend/api/](backend/api/))
- **main.py** - FastAPI app initialization, CORS, exception handlers
- **routes.py** - Document conversion endpoints (convert, job status, results)
- **auth_routes.py** - User registration, login, profile (JWT-based)
- **apikey_routes.py** - API key creation, listing, deletion

**Authentication:**
The system supports two authentication methods:
1. **JWT tokens** - For user sessions (login/register via auth_routes.py)
2. **API keys** - For programmatic access (managed via apikey_routes.py)

Test authentication: `./test_auth.sh`

### Backend Worker Layer ([backend/workers/](backend/workers/))
- **celery_app.py** - Celery configuration and initialization
- **tasks.py** - Core task definitions:
  - `process_conversion` - Main conversion task, handles PDF splitting decision
  - `process_page` - Individual page processing (runs in parallel)
- **converter.py** - Docling integration for markdown conversion
- **sources.py** - Source handlers for file/url/gdrive/dropbox

## Important Patterns

### 1. PDF Processing Decision
In `process_conversion` task, the system checks if a PDF should be split:
```python
if should_split_pdf(file_path, min_pages=2):
    # Split into pages and process in parallel
else:
    # Convert entire document as single job
```

### 2. Progress Tracking
Progress is calculated dynamically based on completed page **jobs**:
- Download + split: 20%
- Pages: 70% (distributed evenly across all pages)
- Merge: the remaining 10%

The live formula is inline in [backend/workers/tasks.py](backend/workers/tasks.py)
(two occurrences), and reads:

```python
progress = 20 + int((completed_pages / total_pages) * 70)
```

where `completed_pages` comes from `redis_client.count_completed_page_jobs()` and
`total_pages` from `redis_client.get_job_pages_total()`.

Note: there is no `calculate_job_progress()` on `RedisClient` — it was removed as
dead code, and the 10/80/10 weighting this section used to document was never
implemented anywhere.

### 3. Redis Key Structure

Redis is a **TTL cache only**. Every key expires; a miss means "unknown", never
"does not exist". No authorization decision may be derived from it — ownership is
enforced by [backend/api/deps.py](backend/api/deps.py) against the database.

```
job:{job_id}:status          # Job metadata + status (24h TTL)
job:{job_id}:result          # Job result payload (RESULT_TTL_SECONDS)
job:{job_id}:pages:total     # Total page count for a split PDF (24h TTL)
job:{job_id}:owner           # Cached owner user_id; deps.py fallback only (24h TTL)
user:{user_id}:jobs          # SET of that user's job IDs (30d TTL)
```

**There is no per-page key namespace.** Each page is modelled as a *job* in its own
right: workers call `set_job_status(job_id=<page_job_id>, job_type="page",
parent_job_id=<main_job_id>, page_number=N)`, so a page's status and result live at
`job:{page_job_id}:status` / `job:{page_job_id}:result` like any other job. The
parent's `job:{job_id}:status` blob carries a `child_job_ids` field
(`split_job_id`, `page_job_ids[]`, `merge_job_id`) linking them together.

### 4. Source Handlers
Each source type (file, url, gdrive, dropbox) has a dedicated handler implementing the `SourceHandler` interface. Add new sources by creating a new handler in [workers/sources.py](workers/sources.py).

## Documentation

- **[README.md](README.md)** - Main project documentation, architecture overview
- **[docs/SPECS.md](docs/SPECS.md)** - Detailed API specifications
- **[docs/ARCHITECTURE_JOBS.md](docs/ARCHITECTURE_JOBS.md)** - Deep dive into hierarchical job system
- **[docs/RF.md](docs/RF.md)** - Functional requirements
- **[docs/RNF.md](docs/RNF.md)** - Non-functional requirements (performance, security)
- **[docs/DOCKER_OPTIMIZATION.md](docs/DOCKER_OPTIMIZATION.md)** - Docker performance tuning
- **[scripts/README.md](scripts/README.md)** - Testing and utility scripts guide

## Configuration

### Frontend Environment ([frontend/.env.local](frontend/.env.local))
- `NEXT_PUBLIC_API_URL` - Backend API URL (default: http://localhost:8000)

### Backend Environment

**Python Version**: 3.13+ (with `setuptools>=75.0.0` for `distutils` compatibility)

Environment variables are loaded via Pydantic Settings in [backend/shared/config.py](backend/shared/config.py):

**Critical settings:**
- `REDIS_HOST`, `REDIS_PORT` - Redis connection
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` - Celery queues
- `MAX_FILE_SIZE_MB` - Upload limit (default: 50)
- `CONVERSION_TIMEOUT_SECONDS` - Per-task timeout (default: 300)
- `TEMP_STORAGE_PATH` - Temporary file location (default: /tmp/doc2md)
- `RESULT_TTL_SECONDS` - How long to cache results (default: 3600)

**Performance optimization (Docling):**
- `DOCLING_ENABLE_OCR` (default: False) - Enable OCR for scanned PDFs (slower, ~10x impact)
- `DOCLING_ENABLE_TABLE_STRUCTURE` (default: True) - Enable table structure recognition
- `DOCLING_USE_V2_BACKEND` (default: True) - Use beta backend (~10x faster)

**Performance tip:** For digital PDFs, keep OCR disabled for ~10x speedup. Only enable for scanned documents.

## API Endpoints

### POST /upload (Recommended for file uploads)
Dedicated endpoint for file uploads with clear file field in Swagger UI:
- Accepts PDF, DOCX, HTML, PPTX, XLSX, RTF, ODT
- Returns `job_id` immediately
- Best for testing in Swagger (http://localhost:8080/docs)

### POST /convert
Unified endpoint accepting multiple source types:
- File upload (multipart/form-data with `file` field)
- URL conversion (JSON with `source_type: "url"`)
- Google Drive (JSON with `source_type: "gdrive"` + Bearer token)
- Dropbox (JSON with `source_type: "dropbox"` + Bearer token)

Returns immediately with `job_id`.

### GET /jobs/{job_id}
Returns job status with progress, pages completed/failed, child job IDs.

**For multi-page PDFs, returns:**
- `total_pages`: Number of pages in PDF
- `pages_completed`: Pages already converted
- `pages_failed`: Pages that failed
- `child_jobs`: Contains `split_job_id`, `page_job_ids[]`, `merge_job_id`

### GET /jobs/{job_id}/result
Returns final converted markdown.

**Behavior:**
- For MAIN jobs: Returns merged markdown from all pages
- For PAGE jobs: Returns markdown of single page only

### GET /jobs/{job_id}/pages
Lists all individual page jobs with their status (only for multi-page PDFs).

**Returns array of page info:**
```json
{
  "pages": [
    {
      "page_number": 1,
      "job_id": "page-1-abc",
      "status": "completed",
      "url": "/jobs/page-1-abc/result"
    }
  ]
}
```

**Use case:** Poll this endpoint to show per-page progress in UI, or fetch individual pages as they complete.

### GET /health
Health check showing Redis connection and worker count.

## Testing Strategy

### Interactive CLI Testing (Recommended)
The project includes `scripts/test_cli.py` - a comprehensive interactive testing tool with:
- Colored terminal output for better readability
- Full API endpoint coverage (upload, status, results, pages)
- Real-time job monitoring with progress updates
- Automated full-flow testing
- Health checks and diagnostics

```bash
python scripts/test_cli.py
# Select from 7 interactive options for testing different flows
```

### Manual Testing
When testing conversions:
1. Start with small documents to verify basic flow
2. Test multi-page PDFs (≥2 pages) to verify parallel processing
3. Check individual page results via `/jobs/{page_job_id}/result`
4. Monitor worker logs for parallel execution

### Standalone Component Testing
Test individual components without full Docker stack:
- `scripts/test_pdf_split.py` - PDF splitting logic only
- `scripts/test_docling_conversion.py` - Docling conversion with optimization benchmarks
- `scripts/test_page_jobs.py` - Job hierarchy simulation with Redis

## Common Tasks

### Adding a new document format
1. Ensure Docling supports it (check Docling documentation)
2. Update MIME type validation in source handlers
3. Add to supported formats list in README

### Adding a new source type
1. Create handler class in [workers/sources.py](workers/sources.py) implementing `SourceHandler`
2. Add to `get_source_handler()` factory
3. Update `ConvertRequest.source_type` enum in [shared/schemas.py](shared/schemas.py)
4. Update API documentation

### Debugging job failures
1. Check job status: `GET /jobs/{job_id}` for error message
2. Review worker logs: `docker compose logs -f worker`
3. For page-specific failures, check individual page status
4. Temp files are in `/tmp/doc2md/{job_id}/` (cleaned up after processing)

## Docker Structure

- **docker/Dockerfile.frontend** - Frontend container with Next.js (multi-stage build)
- **docker/Dockerfile.api** - API container with FastAPI + uvicorn
- **docker/Dockerfile.worker** - Worker container with Celery + Docling dependencies (includes libpoppler-cpp-dev, tesseract-ocr)
- **docker-compose.yml** - Orchestrates all services: elasticsearch, redis, frontend, api, and worker
- **docker-compose.dev.yml** - Development-optimized compose file

Workers can be scaled independently: `docker compose up -d --scale worker=N`

**Service Ports:**
- Frontend: 3000
- API: 8000 (Dockerized) / 8080 (local via run_api.sh)
- Redis: 6379
- Elasticsearch: 9200
- MySQL: 3306

**Database:**
- MySQL database for persistent storage (users, jobs, pages, API keys)
- See `backend/shared/models.py` for database schema
- Elasticsearch for full-text search and document indexing

## Troubleshooting

### Worker not processing jobs
```bash
# Check if workers are running
docker compose ps worker

# View worker logs for errors
docker compose logs -f worker

# Check Redis connection
docker compose exec redis redis-cli ping

# Restart workers
docker compose restart worker
```

### Jobs stuck in "processing" state
```bash
# Check worker logs for errors
docker compose logs worker --tail=100

# Check if job exists in Redis
docker compose exec redis redis-cli keys "job:*"

# Verify Celery queue
docker compose exec worker celery -A workers.celery_app inspect active
```

### Frontend can't connect to API
```bash
# Check API is running
curl http://localhost:8000/health

# Verify NEXT_PUBLIC_API_URL in frontend/.env.local
cat frontend/.env.local

# Check CORS settings in backend/api/main.py
```

### Slow PDF processing
- Disable OCR for digital PDFs (`DOCLING_ENABLE_OCR=False`)
- Disable table recognition if not needed (`DOCLING_ENABLE_TABLE_STRUCTURE=False`)
- Ensure V2 backend is enabled (`DOCLING_USE_V2_BACKEND=True`)
- Scale workers: `docker compose up -d --scale worker=5`

### Database connection errors
```bash
# Check MySQL is running
docker compose ps mysql

# Verify DATABASE_URL in config
# Check backend/shared/config.py for connection string

# View database logs
docker compose logs mysql
```

## Documentation Organization

**IMPORTANT: All documentation (.md) files MUST be created in the respective `/docs` folders:**

- **General project documentation** → `/docs/` (root level)
  - Examples: SPECS.md, RF.md, RNF.md, ARCHITECTURE_JOBS.md, TASKS.md, etc.

- **Frontend-specific documentation** → `/frontend/docs/`
  - Examples: Component guides, frontend architecture, UI patterns, etc.

- **Backend-specific documentation** → `/backend/docs/`
  - Examples: API design, job pipeline, authorization model, etc.

- **Subdirectory documentation** → `{subdirectory}/docs/`
  - Examples: `/backend/api/docs/`, `/backend/workers/docs/`, etc.
  - Each major module can have its own docs folder for detailed documentation

**Never create .md files directly in the root or in subdirectories without using the appropriate `/docs` folder.**

**Exception:** README.md and CLAUDE.md files at the root level are acceptable as they serve as entry points.

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
