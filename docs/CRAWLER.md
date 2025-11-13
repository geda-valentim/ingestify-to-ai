# Product Requirements Document (PRD)
# Website Scraper Application

**Version:** 2.0
**Date:** October 2025
**Status:** Draft

---

## 1. Executive Summary

A professional Python-based web scraping application that enables users to download entire websites or specific pages through an interactive CLI interface. The application features browser simulation, task scheduling, Elasticsearch-powered data persistence with advanced search capabilities, and follows clean architecture principles for maintainability and scalability.

---

## 2. Product Vision

Build a robust, user-friendly web scraping tool that empowers developers and data analysts to efficiently extract web content with support for complex scenarios including JavaScript-heavy sites, rate limiting, and scheduled operations.

---

## 3. Target Users

- **Data Analysts**: Collecting data for research and analysis
- **Developers**: Building automated content aggregation systems
- **QA Engineers**: Testing and monitoring web applications
- **Content Managers**: Archiving websites and documentation

---

## 4. Core Features

### 4.1 Interactive CLI Interface

**Requirements:**
- Beautiful, intuitive terminal UI with colors and formatting
- Friendly option selection menus
- Progress bars and real-time status updates
- Input validation and helpful error messages
- Support for both interactive and command-line argument modes

**User Experience:**
```
┌─────────────────────────────────────────────┐
│     Website Scraper v1.0                    │
│     Professional Web Content Downloader     │
└─────────────────────────────────────────────┘

Select Operation:
  ❯ 1. Download Single Page
    2. Download Full Website
    3. Schedule Scraping Job
    4. View Job Status
    5. Settings
    6. Exit
```

### 4.2 Download Capabilities

#### 4.2.1 Page Download Options

Users can select from three download modes:

**Option 1: Page Only**
- Download only the HTML page content
- No linked resources or assets
- Fastest download option
- Ideal for text content extraction

**Option 2: Page + All Linked Files**
- Download the page and ALL linked resources
- Includes: HTML, CSS, JS, images, documents, media
- Complete offline browsing capability
- All file types preserved

**Option 3: Page + Filtered Links (Extension-Based)**
- Download page + specific file types only
- Flexible selection modes:

**Selection Mode 1: Quick Select from Categories**
- User selects from predefined categories:
  - Documents: `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`, `.txt`, `.csv`
  - Images: `.jpg`, `.jpeg`, `.png`, `.gif`, `.svg`, `.webp`, `.bmp`
  - Media: `.mp4`, `.mp3`, `.avi`, `.mov`, `.wav`
  - Archives: `.zip`, `.rar`, `.tar`, `.gz`
  - Code: `.js`, `.css`, `.json`, `.xml`, `.html`
- Can select one, many, or all categories
- Multi-select with space bar

**Selection Mode 2: Choose Individual Extensions**
- User can drill down into categories
- Select specific extensions only
- Example: Only `.pdf` and `.xlsx` (not all documents)
- Mix and match across categories

**Selection Mode 3: Custom Extension Input**
- User manually types extensions
- Comma-separated list
- Examples:
  - Single: `pdf`
  - Multiple: `pdf, xlsx, csv`
  - Uncommon: `dwg, psd, ai`
- System validates and normalizes (adds dots, lowercase)

**Workflow:**
```
? How do you want to specify file types?
  ❯ Quick Select (predefined categories)
    Choose Individual Extensions
    Type Custom Extensions

[If Quick Select chosen:]
? Select categories: (space to select)
  [✓] Documents (pdf, doc, docx, xls, xlsx, ppt, pptx, txt, csv)
  [ ] Images (jpg, png, gif, svg, webp, bmp)
  [ ] Media (mp4, mp3, avi, mov, wav)
  [ ] Archives (zip, rar, tar, gz)
  [ ] Code (js, css, json, xml, html)

[If Choose Individual Extensions:]
? Select extensions: (space to select, enter to finish)
  Documents:
    [✓] pdf
    [✓] xlsx
    [ ] doc
    [ ] docx
    [ ] csv
  Images:
    [ ] jpg
    [ ] png
  ...

[If Type Custom Extensions:]
? Enter file extensions (comma-separated): pdf, xlsx, dwg
✓ Validated: .pdf, .xlsx, .dwg
```

**Common Use Cases:**
- Research papers: Page + `.pdf` files only
- Data analysis: Page + `.csv`, `.xlsx`, `.json` files
- Media archival: Page + `.mp4`, `.mp3` files
- Documentation: Page + `.pdf`, `.docx` files
- CAD files: Page + custom `.dwg`, `.dxf` extensions

#### 4.2.2 PDF-Specific Handling

When PDF files are included in the download, users can specify:

**Save Mode Options:**

1. **Individual Files (Default)**
   - Each PDF saved separately
   - Original filenames preserved
   - Organized in subdirectories by source page
   - Example structure:
     ```
     downloads/example.com_20251019/
     ├── page.html
     └── pdfs/
         ├── document1.pdf
         ├── report2024.pdf
         └── whitepaper.pdf
     ```

2. **Combined/Merged PDFs**
   - All PDFs merged into single file
   - Automatically named: `{domain}_merged_{timestamp}.pdf`
   - Preserves original order from page
   - Table of contents with source URLs
   - Requires: PyPDF2 or pypdf library
   - Example: `example.com_merged_20251019.pdf`

3. **Both Individual + Combined**
   - Saves individual files AND creates merged version
   - Best for archival purposes
   - Allows both granular and consolidated access
   - Slightly more storage space required

**PDF Merge Features:**
- Bookmark generation for each source PDF
- Metadata preservation (title, author, date)
- Compression options to reduce file size
- Progress indication during merge operation
- Error handling for corrupted PDFs

#### 4.2.3 Full Website Download
- Recursive crawling with configurable depth limits
- Respect robots.txt (with override option)
- Domain boundary controls
- Duplicate detection and prevention
- Resume capability for interrupted downloads
- Support for all download modes (page only, all files, filtered)

### 4.3 Browser Simulation

**Requirements:**
- Multiple browser user-agent support (Chrome, Firefox, Safari, Edge)
- Random user-agent rotation
- Cookie and session management
- JavaScript rendering support
- Custom header injection

**Implementation Options:**
1. **Direct BeautifulSoup**: Fast, lightweight for static content
2. **Web Proxy Mode**: Use external proxy services for complex scenarios
3. **Hybrid Approach**: Automatic fallback between methods

### 4.4 Duplicate Detection & URL Pattern Matching

**Pre-Download Validation:**

Before executing any download, the system performs intelligent duplicate detection:

1. **URL Pattern Analysis**
   - Normalizes URLs (removes trailing slashes, sorts query parameters)
   - Generates URL pattern fingerprint
   - Checks against existing scheduled jobs in MongoDB
   - Example patterns:
     ```
     https://example.com/page          → Pattern: example.com/page
     https://example.com/page?id=123   → Pattern: example.com/page?id=*
     https://example.com/blog/2024/01  → Pattern: example.com/blog/*/*
     ```

2. **Duplicate Detection Scenarios**

   **Exact Match:**
   ```
   Existing: https://example.com/docs
   New:      https://example.com/docs
   → Result: DUPLICATE DETECTED
   ```

   **Pattern Match with Parameters:**
   ```
   Existing: https://example.com/article?id=100
   New:      https://example.com/article?id=200
   → Pattern: example.com/article?id=*
   → Result: SIMILAR URL PATTERN (user can override)
   ```

   **Scheduled Job Check:**
   ```
   Existing Job: https://example.com/news (scheduled: daily)
   New Request:  https://example.com/news
   → Result: ALREADY SCHEDULED (shows next run time)
   ```

3. **User Notification Flow**
   ```
   ⚠️  Duplicate Detected

   URL: https://example.com/docs

   Existing Job:
     - Job ID: abc123
     - Status: Scheduled (runs daily at 09:00 UTC)
     - Last Run: 2025-10-18 09:00:00
     - Next Run: 2025-10-19 09:00:00

   What would you like to do?
     1. Cancel and view existing job
     2. Continue anyway (create new job)
     3. Update existing job schedule
     4. Run now (one-time execution)
   ```

4. **Pattern Matching Rules**
   - Domain matching (exact)
   - Path matching (exact or wildcard)
   - Query parameter matching (optional)
   - Fragment identifier matching (optional)
   - Case-insensitive matching option
   - User-defined pattern rules

5. **Override Options**
   - Force download (ignore duplicates)
   - Different download mode (e.g., existing: page only, new: page + PDFs)
   - Different file filters
   - Different schedule pattern

### 4.5 Task Scheduling & Frequency Configuration

**Powered by Celery:**

When creating a download job, users first choose between one-time or recurring execution, then configure details:

**Duplicate Detection Implementation:**
- URL normalization and pattern generation
- Elasticsearch query with fuzzy matching
- Real-time conflict detection
- User decision workflow

**Primary Schedule Choice:**

```
? When do you want to run this job?
  ❯ Run Once (single execution)
    Run on Schedule (recurring)
```

---

**Option A: Run Once (One-Time Execution)**

Two sub-options:

1. **Run Immediately**
   - Executes right away
   - No scheduling delay
   - Default for one-time downloads

2. **Run at Specific Time**
   - Schedule for future date/time
   - Example: "Run on 2025-10-25 at 14:30 UTC"
   - Useful for planned downloads

**Workflow:**
```
? Run Once - When?
  ❯ Now (immediate)
    Schedule for later

[If Schedule for later:]
? Date: [2025-10-25]
? Time: [14]:30 UTC
```

---

**Option B: Run on Schedule (Recurring)**

Multiple frequency options with flexible time configuration:

**1. Hourly**
   - Every N hours
   - Specify minute of the hour
   - Example: Every 6 hours at :00 minutes

**2. Daily**
   - Every day at specific time(s)
   - **Support multiple times per day**
   - Examples:
     - Once: Daily at 09:00
     - Multiple: Daily at 07:00, 12:00, 18:00

**3. Weekly**
   - Select specific days of week
   - **Support multiple times per day**
   - Can select one or more days
   - Examples:
     - Monday, Wednesday, Friday at 09:00
     - Monday, Wednesday, Friday at 07:00, 09:00, 12:00
     - Weekdays (Mon-Fri) at 06:00, 18:00

**4. Monthly**
   - Specific day(s) of month
   - Specific time(s)
   - Examples:
     - 1st of month at 00:00
     - 1st and 15th at 09:00, 17:00

**5. Custom (Cron Expression)**
   - Full cron syntax support
   - For advanced users
   - Examples:
     ```
     0 */4 * * *         → Every 4 hours
     0 9 * * 1-5         → Weekdays at 9 AM
     0 0 1,15 * *        → 1st and 15th of month
     0 7,9,12 * * 1,3,5  → Mon, Wed, Fri at 7 AM, 9 AM, 12 PM
     ```
   - Built-in validator with human-readable translation

---

**Detailed Scheduling Workflows:**

**Daily with Multiple Times:**
```
? Frequency: Daily

? How many times per day?
  ❯ Once
    Multiple times

[If Multiple times:]
? Select times (space to add, enter when done):
  Add time: [07]:00 UTC  [Added]
  Add time: [09]:00 UTC  [Added]
  Add time: [12]:00 UTC  [Added]
  Add time: ___:___ UTC

Times configured: 07:00, 09:00, 12:00

✓ Will run 3 times daily at: 07:00, 09:00, 12:00 UTC
```

**Weekly with Multiple Days and Times:**
```
? Frequency: Weekly

? Select days: (space to select)
  [✓] Monday
  [ ] Tuesday
  [✓] Wednesday
  [ ] Thursday
  [✓] Friday
  [ ] Saturday
  [ ] Sunday

[3 days selected: Monday, Wednesday, Friday]

? How many times per day?
  ❯ Once
    Multiple times

[If Multiple times:]
? Select times:
  Add time: [07]:00 UTC  [Added]
  Add time: [09]:00 UTC  [Added]
  Add time: [12]:00 UTC  [Added]

✓ Schedule: Monday, Wednesday, Friday at 07:00, 09:00, 12:00 UTC
✓ Total: 9 executions per week
```

**Preview Next Executions:**
```
? Preview next 10 runs:
  • Monday    2025-10-20 07:00:00 UTC
  • Monday    2025-10-20 09:00:00 UTC
  • Monday    2025-10-20 12:00:00 UTC
  • Wednesday 2025-10-22 07:00:00 UTC
  • Wednesday 2025-10-22 09:00:00 UTC
  • Wednesday 2025-10-22 12:00:00 UTC
  • Friday    2025-10-24 07:00:00 UTC
  • Friday    2025-10-24 09:00:00 UTC
  • Friday    2025-10-24 12:00:00 UTC
  • Monday    2025-10-27 07:00:00 UTC

? Confirm schedule? (Y/n)
```

---

**Advanced Features:**

**Timezone Configuration:**
- Default: UTC
- User can select from timezone list
- Examples: America/Sao_Paulo, Europe/London, Asia/Tokyo
- All times converted and stored in UTC internally

**Schedule Constraints:**
- Max executions limit (optional)
  - Example: "Run 100 times then stop"
- Expiration date for recurring jobs
  - Example: "Run until 2025-12-31"
- Blackout periods (future enhancement)
  - Example: "Skip weekends and holidays"

**Schedule Storage in Elasticsearch:**
```json
{
  "schedule": {
    "type": "recurring",
    "frequency": "weekly",
    "days_of_week": [1, 3, 5],
    "times": ["07:00", "09:00", "12:00"],
    "timezone": "America/Sao_Paulo",
    "cron_expression": "0 7,9,12 * * 1,3,5",
    "next_runs": [
      "2025-10-20T10:00:00Z",
      "2025-10-20T12:00:00Z",
      "2025-10-20T15:00:00Z"
    ],
    "max_executions": null,
    "expires_at": null
  }
}
```

---

**Scheduling Features:**
- Schedule validation before creation
- Timezone support (UTC + 400+ timezones)
- Next 5-10 execution times preview
- Schedule conflict detection
- Priority queue management
- Retry logic with exponential backoff
- Concurrent task execution with rate limiting
- Max executions limit (optional)
- Expiration date for recurring jobs
- Human-readable schedule description

**Schedule Management:**
- View scheduled tasks (grouped by frequency)
- Pause/resume tasks
- Edit schedule without recreating job
- Cancel running tasks
- Skip next execution
- Run immediately (override schedule)
- Task history and logging with timestamps
- Duplicate execution prevention

### 4.6 Data Persistence with Elasticsearch

**Why Elasticsearch:**

Elasticsearch provides superior capabilities for this application compared to traditional document databases:

1. **Advanced Search & Analytics**
   - Full-text search across job metadata
   - Complex queries with filters and aggregations
   - Fuzzy matching for URL pattern detection
   - Near real-time search capabilities

2. **Time-Series Data Optimization**
   - Perfect for metrics and execution history
   - Built-in time-based indices
   - Efficient data rollover and retention policies
   - Fast time-range queries

3. **Scalability**
   - Horizontal scaling with sharding
   - High write throughput for metrics
   - Distributed architecture
   - Automatic replication

4. **Analytics & Visualization**
   - Aggregation framework for statistics
   - Integration with Kibana for dashboards (future)
   - Real-time analytics
   - Performance metrics analysis

5. **Schema Flexibility**
   - Dynamic mapping for evolving data structures
   - Nested object support
   - Array handling
   - No need for migrations

**Elasticsearch Storage:**
- Downloaded content metadata
- Task scheduling information
- Job execution history with time-series indexing
- Configuration settings
- Error logs and analytics
- URL pattern fingerprints for duplicate detection
- Real-time metrics and performance data
- Search and filter capabilities

**Index Strategy:**
```
jobs-*                    → Job definitions and configurations
job-executions-*          → Individual execution records (time-based)
job-metrics-YYYY.MM.DD    → Time-series metrics (daily indices)
system-metrics-YYYY.MM.DD → System health metrics (daily indices)
job-files-*               → Downloaded files metadata
alerts-*                  → System alerts and notifications
```

**Document Schema Design:**
```json
{
  "jobs": {
    "job_id": "uuid",
    "url": "string",
    "url_pattern": "string",
    "type": "page_only|page_with_all|page_with_filtered|full_website",
    "status": "pending|running|completed|failed|paused",
    "schedule": {
      "type": "one_time|recurring",
      "run_immediately": "bool",
      "scheduled_datetime": "datetime",
      "frequency": "hourly|daily|weekly|monthly|custom",
      "days_of_week": [1, 3, 5],
      "days_of_month": [1, 15],
      "times": ["07:00", "09:00", "12:00"],
      "cron_expression": "string",
      "timezone": "America/Sao_Paulo",
      "next_runs": ["datetime", "datetime", "datetime"],
      "last_run": "datetime",
      "max_executions": "int",
      "execution_count": "int",
      "expires_at": "datetime"
    },
    "download_config": {
      "mode": "page_only|page_with_all|page_with_filtered",
      "extension_selection_mode": "quick_select|individual|custom",
      "file_extensions": ["pdf", "xlsx", "csv"],
      "extension_categories": ["documents", "images"],
      "pdf_handling": "individual|combined|both",
      "max_depth": "int",
      "follow_external_links": "bool"
    },
    "created_at": "datetime",
    "started_at": "datetime",
    "completed_at": "datetime",
    "config": {},
    "stats": {
      "pages_downloaded": "int",
      "files_downloaded": "int",
      "pdfs_merged": "int",
      "total_size": "int",
      "errors": "int"
    },
    "execution_history": [
      {
        "execution_id": "uuid",
        "started_at": "datetime",
        "completed_at": "datetime",
        "status": "completed|failed",
        "files_downloaded": "int",
        "errors": "int"
      }
    ]
  }
}
```

---

## 5. Technical Architecture

### 5.1 Clean Architecture Layers

```
┌──────────────────────────────────────────┐
│         Presentation Layer               │
│  (CLI Interface, Input Handlers)         │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│         Application Layer                │
│  (Use Cases, Business Logic)             │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│         Domain Layer                     │
│  (Entities, Value Objects, Interfaces)   │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│         Infrastructure Layer             │
│  (DB, HTTP Clients, File System)         │
└──────────────────────────────────────────┘
```

### 5.2 Directory Structure

```
website-scraper/
├── src/
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── job.py
│   │   │   ├── page.py
│   │   │   └── website.py
│   │   ├── value_objects/
│   │   │   ├── url.py
│   │   │   └── scraping_config.py
│   │   └── interfaces/
│   │       ├── repository.py
│   │       └── scraper.py
│   ├── application/
│   │   ├── use_cases/
│   │   │   ├── download_page.py
│   │   │   ├── download_website.py
│   │   │   └── schedule_job.py
│   │   └── services/
│   │       ├── scraper_service.py
│   │       └── scheduler_service.py
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── mongodb_repository.py
│   │   │   └── models.py
│   │   ├── http/
│   │   │   ├── beautifulsoup_client.py
│   │   │   └── proxy_client.py
│   │   ├── tasks/
│   │   │   └── celery_tasks.py
│   │   └── storage/
│   │       └── file_storage.py
│   └── presentation/
│       ├── cli/
│       │   ├── main.py
│       │   ├── menus.py
│       │   └── formatters.py
│       └── validators/
│           └── input_validator.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   └── API.md
├── requirements.txt
├── pyproject.toml
└── README.md
```

### 5.3 Data Access Layer - Elasticsearch DSL

**Elasticsearch-DSL (Selected):**

High-level Python library for Elasticsearch built on top of the official elasticsearch-py client.

**Why Elasticsearch-DSL:**
- Clean, Pythonic API wrapping Elasticsearch queries
- Document class for data modeling with validation
- Type hints and IDE autocomplete support
- Query builder with chainable methods
- Automatic mapping generation
- Async/await support via AsyncElasticsearch
- Pydantic integration for validation
- Perfect for time-series data

**Example Models:**

```python
from elasticsearch_dsl import Document, Date, Keyword, Text, Integer, Float, Nested, Boolean
from elasticsearch_dsl.connections import connections
from datetime import datetime
from typing import Optional, List
from enum import Enum

# Establish connection
connections.create_connection(hosts=['localhost:9200'])

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

class DownloadMode(str, Enum):
    PAGE_ONLY = "page_only"
    PAGE_WITH_ALL = "page_with_all"
    PAGE_WITH_FILTERED = "page_with_filtered"
    FULL_WEBSITE = "full_website"

class PDFHandling(str, Enum):
    INDIVIDUAL = "individual"
    COMBINED = "combined"
    BOTH = "both"

class ScheduleConfig(Document):
    type = Keyword()
    run_immediately = Boolean()
    scheduled_datetime = Date()
    frequency = Keyword()
    days_of_week = Integer(multi=True)
    days_of_month = Integer(multi=True)
    times = Keyword(multi=True)
    cron_expression = Text()
    timezone = Keyword()
    next_runs = Date(multi=True)
    last_run = Date()
    max_executions = Integer()
    execution_count = Integer()
    expires_at = Date()

class DownloadConfig(Document):
    mode = Keyword()
    extension_selection_mode = Keyword()
    file_extensions = Keyword(multi=True)
    extension_categories = Keyword(multi=True)
    pdf_handling = Keyword()
    max_depth = Integer()
    follow_external_links = Boolean()

class ExecutionRecord(Document):
    execution_id = Keyword()
    started_at = Date()
    completed_at = Date()
    status = Keyword()
    files_downloaded = Integer()
    errors = Integer()
    error_details = Text()

    class Index:
        name = 'job-executions-*'

class JobStats(Document):
    pages_downloaded = Integer()
    files_downloaded = Integer()
    pdfs_merged = Integer()
    total_size = Integer()
    errors = Integer()

class Job(Document):
    job_id = Keyword()
    url = Keyword()  # For exact matching
    url_pattern = Text(analyzer='standard')  # For fuzzy/full-text search
    job_type = Keyword()
    status = Keyword()

    # Nested objects
    schedule = Nested(ScheduleConfig)
    download_config = Nested(DownloadConfig)
    stats = Nested(JobStats)

    # Timestamps
    created_at = Date()
    started_at = Date()
    completed_at = Date()

    # Additional fields
    execution_history = Nested(ExecutionRecord)
    error_message = Text()

    # Tags for filtering
    tags = Keyword(multi=True)

    class Index:
        name = 'jobs-*'
        settings = {
            'number_of_shards': 2,
            'number_of_replicas': 1
        }

    def save(self, **kwargs):
        if not self.created_at:
            self.created_at = datetime.utcnow()
        return super().save(**kwargs)

    def mark_running(self):
        self.status = JobStatus.RUNNING.value
        self.started_at = datetime.utcnow()
        self.save()

    def mark_completed(self):
        self.status = JobStatus.COMPLETED.value
        self.completed_at = datetime.utcnow()
        self.save()

    def mark_failed(self, error: str):
        self.status = JobStatus.FAILED.value
        self.error_message = error
        self.completed_at = datetime.utcnow()
        self.save()

    @classmethod
    def search_by_url_pattern(cls, pattern: str):
        """Find jobs with similar URL patterns using fuzzy matching"""
        s = cls.search()
        s = s.query('match', url_pattern={'query': pattern, 'fuzziness': 'AUTO'})
        return s.execute()

    @classmethod
    def get_active_jobs(cls):
        """Get all active jobs"""
        s = cls.search()
        s = s.filter('terms', status=[JobStatus.RUNNING.value, JobStatus.PENDING.value])
        return s.execute()

# Example: Time-series metrics document
class JobMetric(Document):
    job_id = Keyword()
    execution_id = Keyword()
    timestamp = Date()

    # Progress metrics
    progress_percentage = Float()
    urls_downloaded = Integer()
    files_downloaded = Integer()
    bytes_downloaded = Integer()

    # Performance metrics
    download_speed_bps = Integer()
    response_time_ms = Float()

    # Resource metrics
    memory_mb = Float()
    cpu_percent = Float()

    # Error tracking
    error_count = Integer()
    errors = Text(multi=True)

    class Index:
        name = 'job-metrics-*'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 0,
            'refresh_interval': '5s'  # Near real-time
        }

# Initialize indices
def init_indices():
    """Initialize all Elasticsearch indices"""
    Job.init()
    JobMetric.init()
    ExecutionRecord.init()
```

**Query Examples:**

```python
# Find duplicate URLs with fuzzy matching
def check_duplicate(url_pattern: str):
    s = Job.search()
    s = s.query('match', url_pattern={'query': url_pattern, 'fuzziness': 'AUTO'})
    s = s.filter('term', status=JobStatus.PENDING.value)
    return s[:10].execute()

# Get jobs scheduled in next hour
def get_upcoming_jobs():
    s = Job.search()
    s = s.filter('range', schedule__next_runs={'gte': 'now', 'lte': 'now+1h'})
    return s[:100].execute()

# Aggregate metrics by domain
def get_stats_by_domain():
    s = Job.search()
    s.aggs.bucket('by_domain', 'terms', field='url', size=10)
    return s.execute()

# Time-series query for job metrics
def get_job_metrics(job_id: str, last_minutes: int = 10):
    s = JobMetric.search()
    s = s.filter('term', job_id=job_id)
    s = s.filter('range', timestamp={'gte': f'now-{last_minutes}m'})
    s = s.sort('-timestamp')
    return s[:1000].execute()
```

**Benefits for This Project:**
- Native Elasticsearch query capabilities
- Full-text search for URL pattern matching
- Time-series optimization for metrics
- Aggregations for analytics and reporting
- Type safety with field definitions
- Easy integration with Celery tasks
- Scalable for high-volume metrics
- Fast near real-time search
- Flexible schema evolution
- Built-in index lifecycle management

---

## 6. Technology Stack

### 6.1 Core Technologies

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Runtime | Python | 3.14 | Application runtime |
| Web Scraping | BeautifulSoup4 | Latest | HTML parsing |
| HTTP Client | httpx | Latest | Async HTTP requests |
| Browser Automation | Playwright (optional) | Latest | JS rendering |
| Task Queue | Celery | 5.x | Job scheduling |
| Message Broker | Redis | 7.x | Celery backend |
| **Search & Storage** | **Elasticsearch** | **8.x** | **Primary data store, search, and analytics** |
| **ES Client** | **elasticsearch** | **8.x** | **Official Python Elasticsearch client** |
| **ES DSL** | **elasticsearch-dsl** | **Latest** | **High-level Elasticsearch ORM/query builder** |
| PDF Processing | pypdf | Latest | PDF merging and manipulation |
| CLI Framework | Rich | Latest | Beautiful terminal UI |
| CLI Interaction | questionary | Latest | Interactive prompts |
| Validation | Pydantic | 2.x | Data validation |
| Cron Parser | croniter | Latest | Cron expression validation and parsing |
| URL Parsing | urllib3 | Latest | URL normalization and pattern matching |
| File Type Detection | python-magic | Latest | Automatic file type detection |
| Timezone Handling | pytz | Latest | Timezone conversion and management |
| System Monitoring | psutil | Latest | CPU, memory, disk, network metrics |
| Testing | pytest | Latest | Testing framework |
| Async Testing | pytest-asyncio | Latest | Async test support |

### 6.2 Docker Configuration

**Python 3.14 Base Image:**
```dockerfile
FROM python:3.14-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Application setup
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "-m", "src.presentation.cli.main"]
```

**Docker Compose Services:**
- `app`: Main Python application
- `celery-worker`: Celery task workers (scalable)
- `celery-beat`: Celery scheduler
- `elasticsearch`: Search engine and primary data store
- `redis`: Message broker for Celery
- `kibana`: Elasticsearch UI and analytics (optional, dev/monitoring)

**Docker Compose Example:**

```yaml
version: '3.8'

services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    container_name: scraper-elasticsearch
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    ports:
      - "9200:9200"
      - "9300:9300"
    volumes:
      - elasticsearch-data:/usr/share/elasticsearch/data
    networks:
      - scraper-network
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:9200/_cluster/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: scraper-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    networks:
      - scraper-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  app:
    build: .
    container_name: scraper-app
    depends_on:
      elasticsearch:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      - ELASTICSEARCH_URL=http://elasticsearch:9200
      - REDIS_URL=redis://redis:6379
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    volumes:
      - ./downloads:/app/downloads
      - ./logs:/app/logs
    networks:
      - scraper-network
    stdin_open: true
    tty: true

  celery-worker:
    build: .
    container_name: scraper-celery-worker
    command: celery -A src.infrastructure.tasks.celery_app worker --loglevel=info
    depends_on:
      - redis
      - elasticsearch
    environment:
      - ELASTICSEARCH_URL=http://elasticsearch:9200
      - REDIS_URL=redis://redis:6379
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    volumes:
      - ./downloads:/app/downloads
      - ./logs:/app/logs
    networks:
      - scraper-network
    deploy:
      replicas: 2  # Scale as needed

  celery-beat:
    build: .
    container_name: scraper-celery-beat
    command: celery -A src.infrastructure.tasks.celery_app beat --loglevel=info
    depends_on:
      - redis
      - elasticsearch
    environment:
      - ELASTICSEARCH_URL=http://elasticsearch:9200
      - REDIS_URL=redis://redis:6379
      - CELERY_BROKER_URL=redis://redis:6379/0
    networks:
      - scraper-network

  kibana:
    image: docker.elastic.co/kibana/kibana:8.11.0
    container_name: scraper-kibana
    depends_on:
      - elasticsearch
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    ports:
      - "5601:5601"
    networks:
      - scraper-network
    profiles:
      - monitoring  # Optional: only start with --profile monitoring

volumes:
  elasticsearch-data:
  redis-data:

networks:
  scraper-network:
    driver: bridge
```

**Scaling Workers:**
```bash
# Scale to 4 workers
docker-compose up -d --scale celery-worker=4

# View all containers
docker-compose ps

# View logs
docker-compose logs -f celery-worker
```

---

## 7. Key Use Cases

### 7.1 Download Page with Filtered File Types and PDF Merge

**Actor:** User
**Precondition:** Valid URL provided
**Flow:**
1. User selects "Download Single Page"
2. System prompts for URL
3. User enters URL: `https://research.example.com/papers`
4. System validates URL
5. **Duplicate Check:** System checks for existing jobs with same URL pattern
   - Queries Elasticsearch with fuzzy matching: `Job.search_by_url_pattern("research.example.com/papers")`
   - No duplicates found, continues
6. System presents download mode options
7. User selects "Page + Specific File Types"
8. System displays file extension checklist
9. User selects: PDF, XLSX, CSV
10. **PDF Handling:** System detects PDF selection
11. System prompts for PDF save mode
12. User selects "Both (individual + merged)"
13. **Schedule Configuration:** System asks about update frequency
14. User selects "Daily at 09:00 UTC"
15. System shows next 5 execution times preview
16. User confirms configuration
17. **Final Duplicate Check:** System performs final check with schedule pattern
18. No conflicts found
19. System creates Job document in Elasticsearch with:
    - `url_pattern`: normalized URL with text analyzer for fuzzy matching
    - `download_config`: file_extensions, pdf_handling
    - `schedule`: frequency, cron_expression, next_runs (array)
    - Indexed in `jobs-*` index
20. System creates Celery periodic task
21. Celery worker executes job at scheduled time:
    - Downloads HTML page
    - Extracts links matching file extensions
    - Downloads each file with progress updates
    - Streams metrics to Elasticsearch (`job-metrics-YYYY.MM.DD` index)
    - For PDFs:
      - Saves individual files to `/pdfs/` subdirectory
      - Merges all PDFs into single file with bookmarks
      - Applies compression
    - Updates job stats in Elasticsearch
    - Creates execution record in `job-executions-*` index
22. System displays completion summary with file counts and locations

**Postcondition:**
- Page and filtered files downloaded
- PDFs saved individually and merged
- Job scheduled for recurring execution
- All metadata stored in Elasticsearch with time-series indexing
- Metrics available for real-time querying and aggregations

**Alternative Flow - Duplicate Detected:**
5a. System finds existing job with same URL pattern
5b. System displays duplicate warning with existing job details
5c. User presented with options:
    - Cancel and view existing job
    - Update existing job configuration
    - Create new job anyway
    - Run existing job now
5d. User selects desired action
5e. System proceeds accordingly

### 7.2 Schedule Full Website Download with Custom Cron

**Actor:** User
**Precondition:** Valid URL and schedule provided
**Flow:**
1. User selects "Schedule Scraping Job"
2. User selects "Full Website"
3. User enters URL: `https://docs.example.com`
4. System performs URL pattern check
5. User configures download mode: "Page + All Linked Files"
6. User sets max depth: 3 levels
7. User selects schedule: "Custom (Cron Expression)"
8. User enters: `0 */6 * * *` (every 6 hours)
9. System validates cron expression with croniter
10. System translates to human-readable: "Every 6 hours"
11. System shows next 5 execution times
12. User confirms
13. System creates job and Celery Beat schedule
14. Celery executes recursive crawling at scheduled times
15. System respects robots.txt and rate limits
16. System stores each page and linked resources
17. System tracks progress and updates MongoDB

**Postcondition:**
- Recurring full website crawl scheduled
- Celery Beat managing execution
- Job history tracked in MongoDB

### 7.3 View Job Status and Manage Schedules

**Actor:** User
**Flow:**
1. User selects "View Job Status"
2. System queries MongoDB: `Job.find_all().sort("-created_at")`
3. System displays paginated job list with:
   - Job ID, URL, Mode, Schedule, Status
4. User can filter by:
   - Status (pending, running, completed, failed)
   - Schedule type (one-time, recurring)
   - Date range
5. User selects job "abc123" for details
6. System fetches job document from MongoDB
7. System displays:
   - Full configuration
   - Execution history
   - Downloaded files list
   - Error logs (if any)
   - Next scheduled run
8. User options:
   - Pause schedule
   - Edit schedule
   - Run now
   - Delete job
   - View downloaded files
9. User selects "Edit schedule"
10. System loads current schedule configuration
11. User changes frequency from "Daily" to "Weekly"
12. System updates MongoDB document and Celery Beat schedule
13. System confirms update with new next run time

**Postcondition:**
- User has complete visibility into job status
- Schedule updated without recreating job
- Changes reflected in both MongoDB and Celery

### 7.4 Handle URL Pattern Conflicts

**Actor:** User
**Precondition:** Similar URL already scheduled
**Flow:**
1. User attempts to schedule `https://api.example.com/data?version=2`
2. System normalizes URL pattern: `api.example.com/data?version=*`
3. System queries: `Job.find(url_pattern="api.example.com/data?version=*")`
4. Finds existing job: `https://api.example.com/data?version=1`
5. System displays warning:
   ```
   ⚠️ Similar URL Pattern Detected

   Your URL: api.example.com/data?version=2
   Existing:  api.example.com/data?version=1
   Pattern:   api.example.com/data?version=*

   These URLs differ only in query parameters.
   ```
6. User presented with options
7. User selects "Create new job anyway (different data)"
8. System proceeds with job creation
9. Both jobs now tracked separately in MongoDB

**Postcondition:**
- User aware of similar URLs
- Informed decision made
- Both jobs can coexist if needed

---

## 8. Non-Functional Requirements

### 8.1 Performance

- Handle 1000+ concurrent pages download
- Maximum 2 second response time for CLI interactions
- Support websites with 10,000+ pages
- Download speed limited only by network and target server

### 8.2 Reliability

- 99.9% uptime for scheduled tasks
- Automatic retry on transient failures (3 attempts)
- Graceful degradation on service failures
- Data integrity guarantees

### 8.3 Scalability

- Horizontal scaling of Celery workers
- MongoDB sharding support
- Rate limiting per domain
- Queue prioritization

### 8.4 Security

- Respect robots.txt by default
- Rate limiting to prevent DoS
- Secure credential storage
- Audit logging
- No credential harvesting features

### 8.5 Maintainability

- Clean architecture principles
- Comprehensive test coverage (>80%)
- Type hints throughout
- Documentation for all public APIs
- Code style: Black + Ruff

### 8.6 Usability

- Intuitive CLI interface
- Clear error messages
- Helpful defaults
- Comprehensive help system
- Examples and templates

---

## 9. Configuration Management

### 9.1 Configuration File (config.yaml)

```yaml
app:
  name: "Website Scraper"
  version: "1.0.0"
  log_level: "INFO"

scraping:
  default_timeout: 30
  max_retries: 3
  retry_delay: 5
  max_depth: 3
  respect_robots: true
  rate_limit:
    requests_per_second: 2
    concurrent_requests: 5

browser:
  user_agents:
    - "Mozilla/5.0 (Windows NT 10.0; Win64; x64)..."
    - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
  rotate_user_agents: true
  enable_javascript: false

storage:
  output_directory: "./downloads"
  save_metadata: true
  compress: true

database:
  mongodb:
    uri: "mongodb://localhost:27017"
    database: "website_scraper"

celery:
  broker_url: "redis://localhost:6379/0"
  result_backend: "redis://localhost:6379/1"
  task_serializer: "json"
  result_serializer: "json"
  timezone: "UTC"

proxy:
  enabled: false
  proxy_url: ""
  proxy_type: "http"
```

---

## 10. CLI Interface Examples

### 10.1 Main Menu
```
┌─────────────────────────────────────────────┐
│  🌐 Website Scraper v1.0                    │
└─────────────────────────────────────────────┘

? What would you like to do?
  ❯ Download Single Page
    Download Full Website
    Schedule Scraping Job
    View Job Status
    Manage Settings
    Exit

[↑↓] Navigate  [Enter] Select  [Ctrl+C] Cancel
```

### 10.2 Download Configuration Flow
```
┌─────────────────────────────────────────────┐
│  Download Single Page                       │
└─────────────────────────────────────────────┘

? Enter URL: https://example.com/research

? Select download mode:
  ❯ Page Only (HTML content only)
    Page + All Linked Files
    Page + Specific File Types

[User selects: Page + Specific File Types]

? How do you want to specify file types?
  ❯ Quick Select (predefined categories)
    Choose Individual Extensions
    Type Custom Extensions

[User selects: Choose Individual Extensions]

? Select extensions: (space to select, enter to finish)
  Documents:
    [✓] pdf
    [✓] xlsx
    [ ] doc
    [ ] docx
    [✓] csv
  Images:
    [ ] jpg
    [ ] png
  Media:
    [ ] mp4
  Archives:
    [ ] zip

[3 selected: pdf, xlsx, csv]

? PDF files detected. How should they be saved?
  ❯ Individual files (separate PDFs)
    Combined into one PDF
    Both (individual + merged)

[User selects: Both]

? When do you want to run this job?
    Run Once (single execution)
  ❯ Run on Schedule (recurring)

[User selects: Run on Schedule]

? Frequency:
    Hourly
    Daily
  ❯ Weekly
    Monthly
    Custom (Cron)

[User selects: Weekly]

? Select days: (space to select)
  [✓] Monday
  [ ] Tuesday
  [✓] Wednesday
  [ ] Thursday
  [✓] Friday
  [ ] Saturday
  [ ] Sunday

[3 days selected]

? How many times per day?
    Once
  ❯ Multiple times

[User selects: Multiple times]

? Add time 1: [07]:00 UTC  ✓ Added
? Add time 2: [09]:00 UTC  ✓ Added
? Add time 3: [12]:00 UTC  ✓ Added
? Add time 4 (or press Enter to finish): [Enter]

✓ Schedule: Monday, Wednesday, Friday at 07:00, 09:00, 12:00 UTC
✓ Total: 9 executions per week

? Select timezone:
  ❯ UTC
    America/Sao_Paulo (BRT/BRST)
    America/New_York (EST/EDT)
    Europe/London (GMT/BST)
    Other...

[User selects: America/Sao_Paulo]

✓ Adjusted: Monday, Wednesday, Friday at 04:00, 06:00, 09:00 BRT
  (Stored as: 07:00, 09:00, 12:00 UTC)

? Preview next 10 runs:
  • Monday    2025-10-20 04:00:00 BRT (07:00 UTC)
  • Monday    2025-10-20 06:00:00 BRT (09:00 UTC)
  • Monday    2025-10-20 09:00:00 BRT (12:00 UTC)
  • Wednesday 2025-10-22 04:00:00 BRT (07:00 UTC)
  • Wednesday 2025-10-22 06:00:00 BRT (09:00 UTC)
  • Wednesday 2025-10-22 09:00:00 BRT (12:00 UTC)
  • Friday    2025-10-24 04:00:00 BRT (07:00 UTC)
  • Friday    2025-10-24 06:00:00 BRT (09:00 UTC)
  • Friday    2025-10-24 09:00:00 BRT (12:00 UTC)
  • Monday    2025-10-27 04:00:00 BRT (07:00 UTC)

? Confirm schedule? (Y/n): Y

✓ Configuration complete!

Checking for duplicates...

⚠️  Similar job found!

Existing Job: abc123
URL: https://example.com/research
Schedule: Daily at 09:00 UTC
Last Run: 2025-10-18 09:00:00

? This URL is already scheduled. What would you like to do?
    View existing job details
    Update existing job
  ❯ Create new job anyway
    Cancel

[User selects: Create new job anyway]

✓ Job created successfully!

Job ID: def456
Status: Scheduled
Next Run: 2025-10-20 09:00:00 UTC
```

### 10.3 Download Progress
```
Downloading: https://example.com/research

Job ID: def456
Mode: Page + Filtered Files (PDF, XLSX, CSV)
PDF Handling: Individual + Merged

Progress: ████████████░░░░░░░░ 60% (18/30 files)

Files Downloaded:
  HTML Pages:  1/1   ✓
  PDFs:       10/15  ⟳
  Excel:       5/8   ⟳
  CSV:         2/6   ⟳

Current: downloading report_2024.pdf (2.3 MB)
Elapsed: 00:02:45
Speed:   6.5 files/min
Size:    45.8 MB

Status:  Running...
Errors:  1 (skipped: corrupted.pdf)

[Press Ctrl+C to cancel]
```

### 10.4 PDF Merge Progress
```
Merging PDFs...

Progress: ████████████████░░░░ 80% (8/10 PDFs)

Merged so far:
  ✓ introduction.pdf (1.2 MB)
  ✓ chapter1.pdf (3.5 MB)
  ✓ chapter2.pdf (2.8 MB)
  ✓ chapter3.pdf (4.1 MB)
  ✓ appendix.pdf (1.9 MB)
  ✓ references.pdf (0.8 MB)
  ✓ figures.pdf (5.2 MB)
  ⟳ tables.pdf (2.1 MB)
  ⟳ summary.pdf (1.5 MB)

Current size: 21.5 MB
Estimated final: 25.1 MB

[Creating bookmarks and table of contents...]
```

### 10.5 Job Completion Summary
```
✓ Download Complete!

Job ID: def456
URL: https://example.com/research
Duration: 00:04:32

Files Downloaded:
  HTML Pages:  1
  PDFs:       10 (9 valid, 1 skipped)
  Excel:       8
  CSV:         6
  Total:      25 files

PDF Processing:
  Individual PDFs: 9 files saved in ./downloads/example.com_20251019/pdfs/
  Merged PDF: example.com_research_merged_20251019.pdf (24.8 MB)
  Compression: 12% reduction

Storage:
  Total Size: 58.4 MB
  Location: ./downloads/example.com_20251019/

Next Run: 2025-10-20 09:00:00 UTC

[Press Enter to continue]
```

### 10.6 Job Status View
```
┌─────────────────────────────────────────────┐
│  Recent Jobs                                │
└─────────────────────────────────────────────┘

ID       URL                    Mode      Schedule    Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
abc123   example.com/research  Page+PDF  Daily 09:00  Completed
def456   test.org/docs         All       One-time     Running
ghi789   sample.net            Page      Weekly       Scheduled
jkl012   data.io/reports       Filtered  Hourly       Failed

Filter by: [All] Status  Schedule  Date

? Select a job for details [↑↓] or press [Q] to return
```

---

## 11. Monitoring, Metrics & Status Tracking

### 11.1 Overview

Comprehensive monitoring system tracking execution status, system health, resource utilization, and business metrics in real-time.

**Monitoring Layers:**
1. **Job-Level Metrics**: Individual download job tracking
2. **System-Level Metrics**: Platform health (Celery, MongoDB, Redis)
3. **Application Metrics**: Overall performance and usage patterns
4. **Resource Metrics**: CPU, memory, disk, network utilization

---

### 11.2 Job Execution Status & Metrics

**Real-Time Job Status:**

```python
class JobExecutionStatus:
    # Identity
    job_id: str
    execution_id: str

    # Status
    status: JobStatus  # pending, running, completed, failed, paused
    progress_percentage: float  # 0-100

    # Timing
    started_at: datetime
    elapsed_time: timedelta
    estimated_completion: Optional[datetime]

    # Download Progress
    current_url: str
    urls_discovered: int
    urls_downloaded: int
    urls_pending: int
    urls_failed: int

    # File Metrics
    files_total: int
    files_downloaded: int
    files_by_type: Dict[str, int]  # {"pdf": 10, "xlsx": 5}
    current_file: str
    current_file_size: int
    current_file_progress: float

    # Data Transfer
    bytes_downloaded: int
    download_speed_bps: int  # bytes per second
    download_speed_mbps: float
    average_speed_mbps: float

    # Resource Usage (this execution)
    memory_usage_mb: float
    cpu_percent: float
    active_connections: int

    # Errors & Warnings
    error_count: int
    warning_count: int
    retry_count: int
    last_error: Optional[str]

    # Quality Metrics
    success_rate: float  # percentage
    average_response_time_ms: float
```

**Real-Time CLI Display:**

```
┌─────────────────────────────────────────────────────────────┐
│  Job Execution Monitor - def456                             │
│  https://example.com/research                               │
└─────────────────────────────────────────────────────────────┘

Status: RUNNING                    Elapsed: 00:04:32
Progress: ████████████████░░░░░░░░ 68%   ETA: 00:02:15

╔═══════════════════════════════════════════════════════════╗
║  DOWNLOAD PROGRESS                                        ║
╚═══════════════════════════════════════════════════════════╝

Current File: report_2024.pdf
File Progress: ██████████████░░░░░░ 70% (1.6 MB / 2.3 MB)

URLs: 45/68 completed (23 pending, 2 failed)
Files by Type:
  HTML:  ✓ 1/1    PDF:   ⟳ 10/15   Excel: ✓ 5/8
  CSV:   ⟳ 2/6    Images: 27/38

╔═══════════════════════════════════════════════════════════╗
║  PERFORMANCE METRICS                                      ║
╚═══════════════════════════════════════════════════════════╝

Download Speed:  8.5 MB/s  (avg: 6.2 MB/s)
Network:         ↓ 68.3 Mbps  ↑ 2.1 Mbps
Response Time:   avg 245ms, p95 580ms

Success Rate:    97.1% (66/68 successful)
Retries:         3
Errors:          2 (view details: [E])

╔═══════════════════════════════════════════════════════════╗
║  RESOURCE USAGE                                           ║
╚═══════════════════════════════════════════════════════════╝

Memory:  342 MB / 2048 MB  [████░░░░░░░░░░░░░░] 16.7%
CPU:     23.5%
Disk I/O: ↓ 15.2 MB/s  ↑ 0.8 MB/s
Connections: 5 active

╔═══════════════════════════════════════════════════════════╗
║  STORAGE                                                  ║
╚═══════════════════════════════════════════════════════════╝

Downloaded: 458.3 MB
Disk Space: 125.4 GB free / 500 GB (74.9% free)
Location:   /downloads/example.com_20251019/

[R] Refresh  [E] View Errors  [P] Pause  [C] Cancel  [Q] Quit
```

---

### 11.3 System Health Metrics

**Platform Components Monitoring:**

**1. Celery Worker Metrics**
```python
class CeleryMetrics:
    # Workers
    total_workers: int
    active_workers: int
    idle_workers: int
    offline_workers: int

    # Tasks
    tasks_active: int
    tasks_scheduled: int
    tasks_reserved: int

    # Queue
    queue_length: int
    queue_lengths_by_priority: Dict[str, int]

    # Performance
    tasks_processed_total: int
    tasks_successful: int
    tasks_failed: int
    average_task_duration_seconds: float

    # Resource Usage (all workers)
    total_memory_mb: float
    total_cpu_percent: float
```

**2. MongoDB Metrics**
```python
class MongoDBMetrics:
    # Connection
    connected: bool
    connection_pool_size: int
    active_connections: int

    # Database
    database_size_mb: float
    collection_count: int
    document_count: int
    index_count: int

    # Performance
    query_count: int
    average_query_time_ms: float
    slow_queries: int

    # Storage
    storage_size_mb: float
    index_size_mb: float
```

**3. Redis Metrics**
```python
class RedisMetrics:
    # Connection
    connected: bool
    uptime_seconds: int

    # Memory
    used_memory_mb: float
    used_memory_peak_mb: float
    memory_fragmentation_ratio: float

    # Performance
    ops_per_second: int
    hit_rate: float

    # Keys
    total_keys: int
    expired_keys: int
    evicted_keys: int
```

**System Health Dashboard:**

```
┌─────────────────────────────────────────────────────────────┐
│  System Health Dashboard                                    │
│  Last Updated: 2025-10-19 14:32:15 UTC                     │
└─────────────────────────────────────────────────────────────┘

╔═══════════════════════════════════════════════════════════╗
║  PLATFORM STATUS                                          ║
╚═══════════════════════════════════════════════════════════╝

Component       Status    Uptime       Response Time
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Application     🟢 UP     15d 4h 23m   12ms
MongoDB         🟢 UP     15d 4h 25m   3ms
Redis           🟢 UP     15d 4h 25m   <1ms
Celery Workers  🟢 UP     4/4 active   -

╔═══════════════════════════════════════════════════════════╗
║  CELERY WORKERS                                           ║
╚═══════════════════════════════════════════════════════════╝

Worker ID       Status  Tasks Active  Tasks Completed  CPU    Memory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
worker-1        🟢 UP   2/5           1,234            18%    256 MB
worker-2        🟢 UP   3/5           1,189            24%    312 MB
worker-3        🟢 UP   1/5           1,201            12%    198 MB
worker-4        🟢 UP   0/5           1,156            5%     145 MB

Total Active Tasks: 6
Queue Length: 15 (high: 5, normal: 8, low: 2)

╔═══════════════════════════════════════════════════════════╗
║  DATABASE METRICS                                         ║
╚═══════════════════════════════════════════════════════════╝

MongoDB:
  Collections:     5 (jobs, executions, metrics, logs, config)
  Documents:       12,456 total
  Database Size:   245.8 MB
  Active Queries:  3
  Avg Query Time:  4.2ms
  Slow Queries:    0 (last hour)

Redis:
  Memory Used:     82.4 MB / 512 MB (16.1%)
  Keys:           3,245
  Ops/Sec:        1,234
  Hit Rate:       94.5%

╔═══════════════════════════════════════════════════════════╗
║  RESOURCE UTILIZATION                                     ║
╚═══════════════════════════════════════════════════════════╝

CPU Usage:        [████████░░░░░░░░░░░░] 35.2%
Memory:           [███████████░░░░░░░░░] 2.8 GB / 8 GB (35%)
Disk Usage:       [████████████████░░░░] 374.6 GB / 500 GB (74.9%)
Network In:       ↓ 45.2 Mbps
Network Out:      ↑ 8.4 Mbps

╔═══════════════════════════════════════════════════════════╗
║  ALERTS & WARNINGS                                        ║
╚═══════════════════════════════════════════════════════════╝

🟡 Warning: Queue length above 10 for 5 minutes
🟢 All systems operating normally

[A] View All Alerts  [L] View Logs  [R] Refresh  [Q] Quit
```

---

### 11.4 Application-Level Metrics

**Business & Usage Metrics:**

```python
class ApplicationMetrics:
    # Jobs
    jobs_total: int
    jobs_active: int
    jobs_scheduled: int
    jobs_completed_today: int
    jobs_failed_today: int

    # Success Rates
    overall_success_rate: float
    success_rate_24h: float
    success_rate_7d: float

    # Volume Metrics
    total_downloads_lifetime: int
    total_downloads_today: int
    total_bytes_downloaded_lifetime: int
    total_bytes_downloaded_today: int

    # Performance
    average_job_duration_minutes: float
    average_download_speed_mbps: float

    # Popular Domains
    top_domains: List[Tuple[str, int]]  # (domain, count)

    # File Types
    files_by_type: Dict[str, int]  # {"pdf": 1234, "xlsx": 567}

    # Scheduling
    scheduled_jobs_next_hour: int
    scheduled_jobs_next_24h: int

    # Errors
    error_rate: float
    common_errors: List[Tuple[str, int]]  # (error_type, count)
```

**Application Metrics Dashboard:**

```
┌─────────────────────────────────────────────────────────────┐
│  Application Metrics & Analytics                           │
│  Period: Last 24 Hours                                     │
└─────────────────────────────────────────────────────────────┘

╔═══════════════════════════════════════════════════════════╗
║  OVERVIEW                                                 ║
╚═══════════════════════════════════════════════════════════╝

Jobs Today:         145 (132 completed, 8 active, 5 failed)
Success Rate:       96.5% (24h) | 97.2% (7d) | 95.8% (all time)
Files Downloaded:   3,456 files | 12.4 GB
Avg Job Duration:   4m 32s

╔═══════════════════════════════════════════════════════════╗
║  ACTIVE JOBS                                              ║
╚═══════════════════════════════════════════════════════════╝

Job ID    URL                     Progress  Speed     ETA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def456    example.com/research    68%       8.5 MB/s  2m 15s
ghi789    data.io/reports         42%       12.1 MB/s 5m 40s
jkl012    docs.site.com           89%       6.3 MB/s  45s

╔═══════════════════════════════════════════════════════════╗
║  SCHEDULED JOBS                                           ║
╚═══════════════════════════════════════════════════════════╝

Next Hour:    12 jobs
Next 24h:     87 jobs
This Week:    324 jobs

Upcoming:
  • 14:45 UTC - example.com/news (5 minutes)
  • 15:00 UTC - research.edu/papers (30 minutes)
  • 15:30 UTC - data.gov/datasets (1 hour)

╔═══════════════════════════════════════════════════════════╗
║  STATISTICS                                               ║
╚═══════════════════════════════════════════════════════════╝

Top Domains (24h):
  1. example.com        45 downloads
  2. research.edu       32 downloads
  3. data.gov          28 downloads
  4. docs.site.com     23 downloads
  5. news.org          17 downloads

File Types (24h):
  PDF:      1,234 files (8.2 GB)
  Excel:      567 files (1.8 GB)
  CSV:        423 files (0.9 GB)
  Images:     892 files (1.2 GB)
  HTML:       340 files (0.3 GB)

╔═══════════════════════════════════════════════════════════╗
║  PERFORMANCE TRENDS                                       ║
╚═══════════════════════════════════════════════════════════╝

Avg Download Speed:
  Last Hour: 9.2 MB/s  ▲ 12%
  Last 24h:  8.7 MB/s  ▲ 5%
  Last 7d:   8.3 MB/s  ▼ 2%

Success Rate Trend:
  14:00  ████████████████████░ 98%
  13:00  ███████████████████░░ 96%
  12:00  ████████████████████░ 97%
  11:00  ████████████████████░ 99%

╔═══════════════════════════════════════════════════════════╗
║  ERRORS & ISSUES                                          ║
╚═══════════════════════════════════════════════════════════╝

Total Errors (24h): 23 (1.6% error rate)

Common Errors:
  1. Timeout (10)
  2. 404 Not Found (6)
  3. Connection Refused (4)
  4. Rate Limited (3)

[V] View Details  [E] Export Report  [R] Refresh  [Q] Quit
```

---

### 11.5 Metrics Storage Schema

**MongoDB Collections for Metrics:**

```python
# Real-time metrics (updated during execution)
class JobExecutionMetrics(Document):
    job_id: str
    execution_id: str
    timestamp: datetime

    # Progress
    progress_percentage: float
    urls_downloaded: int
    files_downloaded: int
    bytes_downloaded: int

    # Performance
    download_speed_bps: int
    response_time_ms: float

    # Resources
    memory_mb: float
    cpu_percent: float

    # Errors
    error_count: int
    errors: List[str]

    class Settings:
        name = "job_execution_metrics"
        indexes = ["job_id", "execution_id", "timestamp"]

# System metrics (collected every minute)
class SystemMetrics(Document):
    timestamp: datetime

    # Celery
    celery_workers_active: int
    celery_tasks_active: int
    celery_queue_length: int

    # MongoDB
    mongodb_connections: int
    mongodb_query_time_avg_ms: float
    mongodb_storage_mb: float

    # Redis
    redis_memory_mb: float
    redis_ops_per_sec: int
    redis_hit_rate: float

    # Resources
    cpu_percent: float
    memory_mb: float
    disk_usage_mb: float
    network_in_mbps: float
    network_out_mbps: float

    class Settings:
        name = "system_metrics"
        indexes = ["timestamp"]
        # TTL: Keep metrics for 30 days
        indexes = [
            [("timestamp", 1)],
            [("timestamp", 1), {"expireAfterSeconds": 2592000}]
        ]

# Aggregated metrics (hourly/daily rollups)
class AggregatedMetrics(Document):
    period_start: datetime
    period_end: datetime
    granularity: str  # "hourly", "daily"

    # Job Statistics
    jobs_total: int
    jobs_completed: int
    jobs_failed: int
    success_rate: float

    # Volume
    files_downloaded: int
    bytes_downloaded: int

    # Performance
    avg_job_duration_seconds: float
    avg_download_speed_mbps: float
    avg_response_time_ms: float

    # Errors
    total_errors: int
    error_rate: float

    class Settings:
        name = "aggregated_metrics"
        indexes = ["period_start", "granularity"]
```

---

### 11.6 Metrics Collection & Reporting

**Collection Methods:**

1. **Real-Time Collection**
   - Updates every 1-5 seconds during job execution
   - Pushed to Elasticsearch asynchronously with bulk API
   - Time-series indices (`job-metrics-YYYY.MM.DD`)
   - Displayed in CLI with live updates
   - Near real-time refresh interval (5 seconds)

2. **Periodic Collection**
   - System metrics collected every 60 seconds
   - Background task (Celery Beat)
   - Indexed in `system-metrics-YYYY.MM.DD`
   - Minimal performance impact

3. **Aggregation**
   - Hourly rollups calculated at :00 minutes using Elasticsearch aggregations
   - Daily rollups calculated at 00:00 UTC
   - Stored in `aggregated-metrics-*` index
   - Index Lifecycle Management (ILM) for automatic rollover and deletion

**Metrics API:**

```python
# Service for metrics collection
class MetricsService:
    async def record_job_metric(self, job_id: str, metric: JobExecutionMetrics):
        """Record real-time job metric"""

    async def record_system_metric(self, metric: SystemMetrics):
        """Record system-level metric"""

    async def get_job_metrics(self, job_id: str, since: datetime) -> List[JobExecutionMetrics]:
        """Get job metrics for time range"""

    async def get_system_health(self) -> SystemHealthStatus:
        """Get current system health status"""

    async def get_application_metrics(self, period: str) -> ApplicationMetrics:
        """Get application metrics (24h, 7d, 30d, all)"""

    async def export_metrics(self, format: str, period: str) -> bytes:
        """Export metrics to CSV, JSON, or Excel"""
```

---

### 11.7 Alerts & Notifications

**Alert Conditions:**

```python
class AlertRule:
    # Resource Alerts
    cpu_threshold: float = 80.0  # %
    memory_threshold: float = 85.0  # %
    disk_threshold: float = 90.0  # %

    # Queue Alerts
    queue_length_threshold: int = 50
    queue_wait_time_threshold: int = 300  # seconds

    # Performance Alerts
    error_rate_threshold: float = 10.0  # %
    slow_query_threshold: int = 1000  # ms
    response_time_threshold: int = 5000  # ms

    # System Alerts
    worker_down_alert: bool = True
    mongodb_connection_alert: bool = True
    redis_connection_alert: bool = True
```

**Alert Levels:**

- 🟢 **INFO**: Informational messages
- 🟡 **WARNING**: Potential issues, action may be needed
- 🟠 **ERROR**: Issues requiring attention
- 🔴 **CRITICAL**: Severe issues requiring immediate action

**Alert Display:**

```
┌─────────────────────────────────────────────────────────────┐
│  Active Alerts (3)                                          │
└─────────────────────────────────────────────────────────────┘

🟡 WARNING - Queue Length High
   Queue has 52 pending tasks (threshold: 50)
   Duration: 8 minutes
   Action: Consider scaling workers
   [Acknowledge] [Scale Workers] [Dismiss]

🟡 WARNING - High Memory Usage
   System memory at 87.5% (threshold: 85%)
   Current: 7.0 GB / 8 GB
   Action: Monitor or increase memory
   [Acknowledge] [View Details] [Dismiss]

🟢 INFO - Scheduled Maintenance
   MongoDB backup scheduled in 2 hours
   Expected duration: 15 minutes
   [View Schedule] [Dismiss]
```

---

### 11.8 Performance Monitoring & Optimization

**Key Performance Indicators (KPIs):**

1. **Throughput**: Jobs/hour, Files/hour, GB/hour
2. **Latency**: Avg response time, p50, p95, p99
3. **Success Rate**: Overall and per-domain
4. **Resource Efficiency**: Files per CPU hour, GB per memory GB
5. **Cost Efficiency**: Cost per GB downloaded (if cloud)

**Performance Tracking:**

```
┌─────────────────────────────────────────────────────────────┐
│  Performance Analysis - Last 7 Days                         │
└─────────────────────────────────────────────────────────────┘

Throughput:
  Jobs:   234 jobs/day avg (↑ 12% vs prev week)
  Files:  4,567 files/day avg
  Data:   156 GB/day avg

Latency Percentiles:
  p50:  234ms
  p95:  1,245ms
  p99:  3,456ms
  Max:  12,345ms

Success Rate by Domain:
  example.com:     99.2% (excellent)
  research.edu:    97.8% (good)
  data.gov:        94.5% (acceptable)
  legacy.org:      78.3% (poor - investigate)

Resource Efficiency:
  CPU:     125 files per CPU-hour
  Memory:  2.3 GB downloaded per 1 GB memory used
  Network: 89% utilization efficiency

Bottlenecks Detected:
  1. MongoDB slow queries on job_history collection
     → Recommendation: Add compound index
  2. High retry rate for legacy.org domain
     → Recommendation: Increase timeout threshold
```

---

## 12. Error Handling

### 11.1 Error Categories

1. **Network Errors**
   - Timeout
   - Connection refused
   - DNS resolution failure
   - SSL certificate errors

2. **HTTP Errors**
   - 4xx Client errors
   - 5xx Server errors
   - Rate limiting (429)

3. **Content Errors**
   - Invalid HTML
   - Encoding issues
   - Resource not found

4. **System Errors**
   - Disk space full
   - Permission denied
   - Database connection failure

### 11.2 Error Handling Strategy

- Graceful degradation
- Automatic retry with exponential backoff
- Detailed error logging
- User-friendly error messages
- Recovery suggestions

---

## 12. Testing Strategy

### 12.1 Test Coverage

- **Unit Tests**: 80%+ coverage for business logic
- **Integration Tests**: Database, Celery, HTTP clients
- **E2E Tests**: Complete user workflows
- **Performance Tests**: Load testing with locust

### 12.2 Test Scenarios

1. Single page download with various content types
2. Full website crawl with depth limits
3. Failed request retry logic
4. Scheduled task execution
5. Concurrent downloads
6. Rate limiting enforcement
7. Browser user-agent rotation
8. Database operations
9. CLI interaction flows

---

## 13. Deployment

### 13.1 Docker Deployment

```bash
# Start all services
docker-compose up -d

# Scale workers
docker-compose up -d --scale celery-worker=4

# View logs
docker-compose logs -f app
```

### 13.2 Environment Variables

```bash
MONGODB_URI=mongodb://mongodb:27017
REDIS_URL=redis://redis:6379
LOG_LEVEL=INFO
WORKERS=4
MAX_CONCURRENT_DOWNLOADS=10
```

---

## 14. Future Enhancements

### Phase 2 Features
- Web-based dashboard UI
- REST API for programmatic access
- Multiple output formats (JSON, CSV, SQLite)
- Cloud storage integration (S3, GCS)
- Screenshot capture capability
- PDF generation from scraped content
- Email notifications
- Webhook support
- Advanced analytics and reporting

### Phase 3 Features
- Machine learning for content extraction
- Distributed scraping across multiple nodes
- GraphQL API
- Plugin system for custom scrapers
- Multi-language support
- Advanced deduplication with ML
- Change detection and monitoring

---

## 15. Success Metrics

### 15.1 Key Performance Indicators

- **Reliability**: 99.5% job success rate
- **Performance**: Average 100 pages/minute download speed
- **User Satisfaction**: CLI usability rating >4.5/5
- **Code Quality**: Maintainability index >75
- **Test Coverage**: >80% across all layers

### 15.2 Monitoring

- Job completion rates
- Error frequency and types
- Average download speed
- Storage utilization
- Celery queue lengths
- MongoDB query performance

---

## 16. Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Target website blocks scraper | High | Medium | User-agent rotation, rate limiting, proxy support |
| MongoDB data corruption | High | Low | Regular backups, replication |
| Celery worker crashes | Medium | Medium | Auto-restart, health checks |
| Disk space exhaustion | Medium | Medium | Storage quotas, cleanup jobs |
| Legal compliance issues | High | Low | Respect robots.txt, ToS compliance warnings |

---

## 17. Compliance and Ethics

### 17.1 Ethical Scraping Principles

- Respect robots.txt by default
- Implement rate limiting
- Identify scraper in User-Agent
- Do not overwhelm servers
- Comply with website ToS
- Do not scrape personal data without consent
- Provide opt-out mechanisms

### 17.2 Legal Considerations

- Users responsible for compliance
- Warning messages for sensitive operations
- Audit logging for accountability
- No features for credential harvesting
- Documentation on legal usage

---

## 18. Documentation Requirements

### 18.1 User Documentation

- Installation guide
- Quick start tutorial
- CLI command reference
- Configuration guide
- Troubleshooting guide
- FAQ

### 18.2 Developer Documentation

- Architecture overview
- API documentation
- Database schema
- Contributing guidelines
- Code style guide
- Testing guide

---

## 19. Timeline and Milestones

### Sprint 1 (Weeks 1-2): Foundation & Infrastructure
- **Setup**
  - Project structure with clean architecture
  - Docker Compose configuration (Elasticsearch 8.x, Redis 7.x, Python 3.14)
  - Development environment setup
- **Elasticsearch Integration**
  - Elasticsearch-DSL models and indices
  - Index templates and mappings
  - Connection pooling and health checks
- **Celery Setup**
  - Worker and beat configuration
  - Redis broker integration
  - Basic task structure
- **CLI Framework**
  - Rich and questionary integration
  - Main menu structure
  - Basic navigation

### Sprint 2 (Weeks 3-4): Core Download Features
- **Single Page Download**
  - HTTP client with httpx
  - BeautifulSoup HTML parsing
  - File saving and organization
- **Download Modes**
  - Page only mode
  - Page + all files mode
  - Page + filtered files mode
- **File Extension Filtering**
  - Three selection modes (quick/individual/custom)
  - Extension validation and normalization
- **Basic Error Handling**
  - Network error catching
  - Retry logic
  - Error logging to Elasticsearch

### Sprint 3 (Weeks 5-6): Advanced Features & Scheduling
- **Full Website Crawling**
  - Recursive link discovery
  - Depth control
  - robots.txt respect
- **URL Pattern Matching**
  - Normalization algorithm
  - Elasticsearch fuzzy matching
  - Duplicate detection workflow
- **Task Scheduling**
  - Celery Beat periodic tasks
  - Cron expression support
  - Multiple times per day scheduling
  - Timezone handling with pytz
- **PDF Processing**
  - Individual PDF saving
  - PDF merging with pypdf
  - Bookmark generation

### Sprint 4 (Weeks 7-8): Monitoring & Metrics
- **Real-Time Metrics**
  - Job execution tracking
  - Progress percentage calculation
  - Download speed monitoring
  - Resource usage tracking (psutil)
- **Elasticsearch Time-Series Indices**
  - job-metrics-YYYY.MM.DD setup
  - system-metrics-YYYY.MM.DD setup
  - Index Lifecycle Management (ILM)
- **Dashboards**
  - Job execution monitor CLI
  - System health dashboard
  - Application metrics dashboard
- **Alerts**
  - Alert rules configuration
  - Alert display system
  - Notification triggers

### Sprint 5 (Weeks 9-10): Polish, Testing & Documentation
- **CLI Enhancements**
  - Interactive prompts polish
  - Progress bars and animations
  - Error message improvements
  - Help system
- **Testing**
  - Unit tests (pytest) - 80%+ coverage
  - Integration tests (Elasticsearch, Celery)
  - E2E workflow tests
  - Performance testing
- **Documentation**
  - User guide
  - Installation instructions
  - Configuration reference
  - API documentation
  - Troubleshooting guide
- **Performance Optimization**
  - Elasticsearch query optimization
  - Bulk indexing for metrics
  - Connection pooling tuning
  - Memory optimization

### Sprint 6 (Weeks 11-12): Release Preparation
- **Security Review**
  - Input validation audit
  - Secrets management
  - Rate limiting verification
- **Deployment**
  - Production Docker configuration
  - Elasticsearch cluster setup guide
  - Backup and recovery procedures
- **Final Testing**
  - Load testing with multiple workers
  - Long-running job testing
  - Edge case testing
- **Release**
  - Version tagging
  - Release notes
  - v1.0 production release

**Total Duration:** 12 weeks (3 months)

**Key Milestones:**
- Week 2: Infrastructure working end-to-end
- Week 4: Basic download functionality complete
- Week 6: Full scheduling and advanced features
- Week 8: Monitoring and metrics operational
- Week 10: Feature complete with testing
- Week 12: Production ready v1.0 release

---

## 20. Appendix

### 20.1 Glossary

- **Scraping**: Extracting data from websites
- **Crawling**: Systematically browsing websites
- **Elasticsearch**: Distributed search and analytics engine
- **Elasticsearch-DSL**: High-level Python library for Elasticsearch
- **Index**: Elasticsearch data structure (similar to database table)
- **Document**: Single record/entry in Elasticsearch
- **Time-Series Data**: Data indexed by timestamp
- **ILM**: Index Lifecycle Management for automatic index rotation
- **Clean Architecture**: Layered architecture pattern
- **Celery**: Distributed task queue
- **User-Agent**: Browser identification string
- **Fuzzy Matching**: Approximate string matching algorithm

### 20.2 References

- **Elasticsearch Documentation**: https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html
- **Elasticsearch-DSL Documentation**: https://elasticsearch-dsl.readthedocs.io/
- **BeautifulSoup Documentation**: https://www.crummy.com/software/BeautifulSoup/
- **Celery Documentation**: https://docs.celeryproject.org/
- **Rich Documentation**: https://rich.readthedocs.io/
- **Questionary Documentation**: https://questionary.readthedocs.io/
- **Clean Architecture**: Robert C. Martin
- **Elasticsearch Best Practices**: https://www.elastic.co/guide/en/elasticsearch/reference/current/best_practices.html

### 20.3 Contact

- Product Owner: [Name]
- Tech Lead: [Name]
- Repository: [GitHub URL]
- Documentation: [Docs URL]

---

**Document Version History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-19 | Claude | Initial PRD |
| 1.1 | 2025-10-19 | Claude | Added: Page + filtered links download modes, PDF merge options (individual/combined/both), duplicate detection with URL patterns, scheduling frequency configuration, confirmed Beanie ODM, enhanced CLI flows, updated use cases |
| 1.2 | 2025-10-19 | Claude | Enhanced: Three extension selection modes (quick select/individual/custom), one-time vs recurring schedule choice, multiple times per day scheduling, timezone support (UTC + 400+ zones), updated schema with execution history, enhanced Beanie models |
| 1.3 | 2025-10-19 | Claude | Added: Comprehensive monitoring & metrics system (Section 11) including job execution metrics, system health monitoring (Celery/MongoDB/Redis), application-level metrics, real-time dashboards, alerts & notifications, performance KPIs, metrics storage schema with TTL, psutil for system monitoring |
| **2.0** | **2025-10-19** | **Claude** | **MAJOR CHANGE: Replaced MongoDB with Elasticsearch 8.x** - Updated entire architecture to use Elasticsearch for superior search, analytics, and time-series capabilities. Changed from Beanie ODM to Elasticsearch-DSL. Added fuzzy matching for URL patterns, time-series indices (job-metrics-*, system-metrics-*), Index Lifecycle Management (ILM), Kibana integration. Updated Docker Compose with Elasticsearch cluster. Expanded timeline to 12 weeks (6 sprints). Enhanced monitoring section with Elasticsearch aggregations. Updated all schemas, queries, and examples. Added comprehensive Elasticsearch benefits rationale. |

---

**Approval Signatures**

- Product Owner: _________________  Date: _______
- Tech Lead: _________________  Date: _______
- Engineering Manager: _________________  Date: _______
