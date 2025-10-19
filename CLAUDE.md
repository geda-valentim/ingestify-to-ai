# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Doc2MD is a full-stack document conversion platform with a Next.js frontend and Python backend API. The system converts documents (PDF, DOCX, HTML, etc.) to Markdown format using Docling, with a distributed architecture using FastAPI, Celery workers, and Redis for scalable document processing.

**Monorepo Structure:**
- **frontend/** - Next.js 15 + React 19 web application
- **backend/** - Python FastAPI + Celery worker backend

## Architecture

### Four-Tier System

1. **Frontend Layer** ([frontend/](frontend/)) - Next.js web application for document uploads and viewing results
2. **API Layer** ([backend/api/](backend/api/)) - FastAPI REST endpoints that receive requests and return job IDs
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

### Start Services
```bash
# Full stack with Docker Compose (recommended)
docker compose up -d --build
# Services:
# - Frontend: http://localhost:3000
# - API: http://localhost:8000
# - API Docs: http://localhost:8000/docs

# Scale workers for heavy loads
docker compose up -d --scale worker=5

# Development mode (local, requires Redis)
# Terminal 1: Redis
docker run -p 6379:6379 redis:7-alpine

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: API
./run_api.sh  # Runs on port 8080

# Terminal 4: Worker
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
# Run tests
pytest tests/ -v

# Test conversion
curl -X POST http://localhost:8000/convert \
  -F "source_type=file" \
  -F "file=@test.pdf"
```

### Rebuild
```bash
# Quick rebuild
./rebuild.sh

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
- **auth_routes.py** - User registration, login, profile
- **apikey_routes.py** - API key creation, listing, deletion

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
Progress is calculated dynamically based on completed pages:
- Split: 10%
- Pages: 80% (distributed across all pages)
- Merge: 10%

See `redis_client.calculate_job_progress()` for implementation.

### 3. Redis Key Structure
```
job:{job_id}:status          # Job metadata and status
job:{job_id}:result          # Final merged result
job:{job_id}:pages           # Total page count
job:{job_id}:page:{n}:status # Individual page status
job:{job_id}:page:{n}:result # Individual page markdown
```

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

When testing conversions:
1. Start with small documents to verify basic flow
2. Test multi-page PDFs (≥2 pages) to verify parallel processing
3. Check individual page results via `/jobs/{page_job_id}/result`
4. Monitor worker logs for parallel execution

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

Workers can be scaled independently: `docker compose up -d --scale worker=N`

**Service Ports:**
- Frontend: 3000
- API: 8000
- Redis: 6379
- Elasticsearch: 9200
