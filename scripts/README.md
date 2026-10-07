# Scripts - Doc2MD

This directory contains utility scripts for testing, development, and Docker management.

## 📁 Structure

```
scripts/
├── README.md                         # This file
├── tests/                            # Test scripts
│   ├── test_pages.sh                # Test page-related endpoints
│   └── test_page_endpoints.sh       # Test page number endpoints
├── docker-build.sh                  # Build Docker images
├── docker-clean.sh                  # Clean Docker resources
├── test_cli.py                      # Interactive CLI client for API testing
├── test_docling_conversion.py       # Test Docling conversion with optimization
├── test_docling_auto.py             # Automated Docling tests
├── test_celery_standalone.py        # Test Celery workers standalone
├── test_page_jobs.py                # Simulate hierarchical job workflow
├── test_pdf_split.py                # Test PDF splitting functionality
├── test_page_conversion_mock.py     # Mock page conversion tests
└── test_upload_endpoint.py          # Test file upload endpoint
```

## 🐳 Docker Scripts

### docker-build.sh
Builds Docker images for API and worker services.

```bash
./scripts/docker-build.sh
```

### docker-clean.sh
Cleans Docker containers, images, and volumes.

```bash
./scripts/docker-clean.sh
```

## 🧪 Test Scripts

### test_cli.py - Interactive CLI Client
**Status:** ✅ WORKING

Interactive Python script to test all API functionalities.

```bash
python scripts/test_cli.py
```

**Features:**
1. Health Check - Verify API status
2. Upload PDF - Upload and convert documents
3. Job Status - Check any job status
4. List Pages - View all page jobs
5. Job Result - Get converted markdown
6. Monitor Job - Real-time progress tracking
7. Full Flow - Automated end-to-end test

**Colored terminal output:**
- 🟢 Green: Success
- 🔵 Blue: Information
- 🟡 Yellow: Warnings
- 🔴 Red: Errors
- 🟣 Purple: Headers

---

### test_docling_conversion.py - Docling Conversion Test
**Status:** ✅ OPTIMIZED

Optimized script to test PDF to Markdown conversion with Docling.

```bash
python3 scripts/test_docling_conversion.py
```

**Features:**
- ✅ Performance optimizations (OCR, Tables, Backend V2)
- ✅ Page-by-page conversion with statistics
- ✅ Markdown output with metadata
- ✅ Complete merged document
- ✅ Performance benchmarks and estimates

**Configuration options:**
- **Maximum Speed (digital PDFs):** OCR=N, Tables=N (~10x faster)
- **Balanced (default):** OCR=N, Tables=Y (~10x faster, preserves tables)
- **Maximum Quality (scanned PDFs):** OCR=Y, Tables=Y (best quality, slower)

**Output:**
```
tmp/test_docling_output/
├── page_0001.md          # Page 1 with metadata
├── page_0002.md          # Page 2 with metadata
├── page_0003.md          # Page 3 with metadata
└── complete_document.md  # Complete merged document
```

---

### test_pdf_split.py - PDF Splitting Test
**Status:** ✅ TESTED AND WORKING

Tests PDF splitting into individual pages without Docker or API.

```bash
python scripts/test_pdf_split.py
```

**What it tests:**
- ✅ Split 50-page PDF
- ✅ Create individual files (page_0001.pdf to page_0050.pdf)
- ✅ Verify file existence
- ✅ Calculate sizes and overhead
- ✅ Cleanup temporary files

**Result:**
```
✓ 50 pages created
✓ Average size: ~51 KB per page
✓ Overhead: 167.9% (normal for PDFs)
```

---

### test_page_jobs.py - Hierarchical Job Simulation
**Status:** ✅ TESTED AND WORKING

Simulates complete conversion workflow with job hierarchy: MAIN → SPLIT → PAGES → MERGE.

```bash
python scripts/test_page_jobs.py
```

**What it does:**
- ✅ Create MAIN JOB (upload)
- ✅ Create SPLIT JOB (actual PDF splitting)
- ✅ Create 50 PAGE JOBS (simulated conversion)
- ✅ Create MERGE JOB (result combination)
- ✅ Real-time progress display
- ✅ Final hierarchy visualization

**Workflow demonstrated:**
```
MAIN JOB (b71344da)
 │
 ├─ SPLIT JOB (cfe3ee0f)
 │   └─ Splits PDF into 50 pages
 │
 ├─ PAGE JOBS (50 parallel jobs)
 │   ├─ Page 1  (199937e5)
 │   ├─ Page 2  (f6768d47)
 │   ├─ ...
 │   └─ Page 50 (2fe3de98)
 │
 └─ MERGE JOB (48607c47)
     └─ Combines 50 results
```

**Statistics:**
```
Total jobs created: 53
• 1 MAIN job
• 1 SPLIT job
• 50 PAGE jobs
• 1 MERGE job

Completed: 53/53
Simulated time: ~5 seconds
```

---

### test_celery_standalone.py - Celery Standalone Test
Tests Celery workers without Docker.

```bash
python scripts/test_celery_standalone.py
```

---

### test_upload_endpoint.py - Upload Endpoint Test
Tests file upload endpoint functionality.

```bash
python scripts/test_upload_endpoint.py
```

---

### test_page_conversion_mock.py - Page Conversion Mock
Mock tests for page conversion logic.

```bash
python scripts/test_page_conversion_mock.py
```

---

### test_docling_auto.py - Automated Docling Tests
Automated tests for Docling integration.

```bash
python scripts/test_docling_auto.py
```

---

## 🧪 Test Scripts (Shell)

Located in `tests/` subdirectory:

### test_pages.sh
Comprehensive tests for page-related endpoints.

```bash
./scripts/tests/test_pages.sh
```

### test_page_endpoints.sh
Tests page number-based endpoints.

```bash
./scripts/tests/test_page_endpoints.sh
```

---

## 📚 Common Workflows

### Quick API Test
```bash
# 1. Start services
docker compose up -d

# 2. Run interactive CLI
python scripts/test_cli.py

# 3. Choose option 7 (Full Flow Test)
```

### Test PDF Splitting (No Docker)
```bash
# Standalone test without services
python scripts/test_pdf_split.py
```

### Test Docling Conversion (No Docker)
```bash
# Interactive conversion test
python3 scripts/test_docling_conversion.py
```

### Simulate Job Hierarchy (No Docker)
```bash
# Simulate full job workflow
python scripts/test_page_jobs.py
```

### Clean Everything
```bash
# Clean Docker and temporary files
./scripts/docker-clean.sh
rm -rf tmp/*
```

---

## 🔧 Troubleshooting

**Error: "Could not connect to API"**
```bash
# Start Docker containers
docker compose up -d

# Check logs
docker compose logs -f
```

**Error: "PDF not found"**
```bash
# Verify PDF exists in root
ls -la /var/www/doc2md/AI-50p.pdf
```

**Job stuck in "processing"**
```bash
# Check worker logs
docker compose logs worker -f
```

**Slow Docling performance?**
- Disable OCR for digital PDFs
- Disable tables if not needed
- Backend V2 is already enabled

---

## 📖 Related Documentation

- **[../docs/ARCHITECTURE_JOBS.md](../docs/ARCHITECTURE_JOBS.md)** - Job hierarchy architecture
- **[../docs/DOCKER_OPTIMIZATION.md](../docs/DOCKER_OPTIMIZATION.md)** - Docker optimization guide
- **[../CLAUDE.md](../CLAUDE.md)** - Claude Code development guide
