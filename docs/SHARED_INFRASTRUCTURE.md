# Shared Infrastructure Guide

This guide explains how to use Ingestify's smart infrastructure detection to share Redis, MinIO, and Elasticsearch across multiple projects or machines.

## Overview

Ingestify supports **two modes** of operation:

1. **Standalone Mode** - Each project runs its own infrastructure (Redis, MinIO, Elasticsearch)
2. **Shared Mode** - Multiple projects share a single infrastructure instance

The `start.sh` script automatically detects which mode to use, making the project fully portable between machines without manual configuration.

## Why Shared Infrastructure?

### Benefits

- **Resource Efficiency**: One Redis/MinIO/Elasticsearch instance instead of multiple copies
- **Faster Startup**: Skip infrastructure startup if already running
- **Development Workflow**: Switch between projects instantly without restarting infrastructure
- **Multi-Machine Support**: Works seamlessly on desktop, laptop, or any machine
- **Zero Configuration**: Automatic detection, no environment variables needed

### Use Cases

- Working on multiple projects simultaneously
- Moving project between different development machines
- CI/CD environments with pre-provisioned infrastructure
- Resource-constrained environments (limited RAM/CPU)

## Quick Start

### Option 1: Auto-Detection (Recommended)

```bash
# Just run start.sh - it figures out everything automatically
./start.sh

# Or use make
make start
```

The script will:
1. Check if shared infrastructure is running
2. Use it if available, otherwise start local infrastructure
3. Configure services automatically
4. Create MinIO buckets
5. Display access URLs

### Option 2: Explicit Shared Infrastructure

```bash
# Terminal 1: Start shared infrastructure once
make infra-start
# Or: docker compose -f docker-compose.infra.yml up -d

# Terminal 2: Start ingestify (will detect and use shared infra)
./start.sh

# Terminal 3: Start another project (also uses shared infra)
cd /path/to/other-project
./start.sh
```

### Option 3: Standalone Mode

```bash
# Force standalone mode (ignore shared infrastructure)
docker compose --profile infra up -d --build
```

## How It Works

### Detection Logic

The `start.sh` script checks for these containers:

- `shared-redis`
- `shared-minio`
- `shared-elasticsearch`

If **all three** are running → Use shared infrastructure

If **any are missing** → Start local infrastructure

### Network Configuration

**Shared Mode:**
- Services connect via `shared-dev-network`
- Uses container names: `shared-redis`, `shared-minio`, `shared-elasticsearch`

**Standalone Mode:**
- Services connect via `ingestify-network`
- Uses local container names: `ingestify-redis`, `ingestify-minio`, `ingestify-elasticsearch`

### Environment Variables

The script creates `.env` file automatically:

**Shared Mode (`.env`):**
```env
REDIS_HOST=shared-redis
MINIO_HOST=shared-minio
ELASTICSEARCH_HOST=shared-elasticsearch
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
```

**Standalone Mode:**
- No `.env` file needed
- Uses defaults from `docker-compose.yml`

## Infrastructure Management

### Start Shared Infrastructure

```bash
# Start infrastructure
make infra-start

# Check status
make infra-status

# View logs
make infra-logs

# Stop infrastructure
make infra-stop
```

### Shared Infrastructure Services

After starting, access:

- **Redis**: `localhost:6379`
- **MinIO API**: `http://localhost:9000`
- **MinIO UI**: `http://localhost:9001` (minioadmin / minioadmin)
- **Elasticsearch**: `http://localhost:9200`

### MinIO Buckets

Each project creates its own buckets automatically:

- `ingestify-uploads` - Uploaded files
- `ingestify-pages` - Extracted pages
- `ingestify-audio` - Audio files
- `ingestify-results` - Conversion results

To create buckets for another project, the start script will detect and create them automatically.

## Multi-Project Workflow

### Scenario: Working on 3 Projects

```bash
# Step 1: Start shared infrastructure once
make infra-start

# Step 2: Start project A
cd ~/projects/ingestify-to-ai
./start.sh  # ✅ Uses shared infrastructure

# Step 3: Start project B (different terminal)
cd ~/projects/ingestify-v2
./start.sh  # ✅ Uses same shared infrastructure

# Step 4: Start project C
cd ~/projects/ingestify-enterprise
./start.sh  # ✅ All three share Redis/MinIO/Elasticsearch
```

### Switching Machines

**On Desktop:**
```bash
cd ~/ingestify-to-ai
./start.sh  # Detects no shared infra → starts local
```

**On Laptop:**
```bash
cd ~/ingestify-to-ai
./start.sh  # Also detects nothing → starts local
```

**Zero configuration needed!** The script adapts automatically.

## Docker Compose Files

### Main Configuration (`docker-compose.yml`)

- Infrastructure services have `profiles: [infra]`
- Only started with `--profile infra` flag
- Application services (api, worker, beat, frontend) always start

### Shared Infrastructure (`docker-compose.infra.yml`)

- Dedicated file for shared infrastructure
- Container names: `shared-redis`, `shared-minio`, `shared-elasticsearch`
- Network: `shared-dev-network`
- Volumes: `shared-redis-data`, `shared-minio-data`, `shared-elasticsearch-data`

## Makefile Commands

### Application

```bash
make start          # Smart start (auto-detect)
make stop           # Stop services
make restart        # Restart all
make logs           # View logs
make ps             # Show status
```

### Infrastructure

```bash
make infra-start    # Start shared infrastructure
make infra-stop     # Stop shared infrastructure
make infra-status   # Check infrastructure status
make infra-logs     # View infrastructure logs
```

### Development

```bash
make dev            # Development mode
make prod           # Production mode
make scale n=10     # Scale workers to 10 replicas
make test           # Run tests
```

### Cleanup

```bash
make clean          # Remove project data
make clean-infra    # Remove shared infrastructure data
make prune          # Clean all Docker resources
```

## Troubleshooting

### Issue: Services can't connect to infrastructure

**Symptom**: API fails with "Connection refused" to Redis/MinIO

**Solution**:
```bash
# Check if infrastructure is running
make infra-status

# Check network connectivity
make network-inspect

# View logs
make logs-api
```

### Issue: Multiple infrastructure instances running

**Symptom**: Both local and shared infrastructure running

**Solution**:
```bash
# Stop local infrastructure
docker compose down

# Keep only shared infrastructure
make infra-status
```

### Issue: Shared infrastructure stopped unexpectedly

**Symptom**: Services fail after shared infrastructure restart

**Solution**:
```bash
# Restart shared infrastructure
make infra-start

# Restart application
make restart
```

### Issue: Port conflicts (9000, 9001, 6379, 9200)

**Symptom**: "Port already in use" error

**Solution**:
```bash
# Check what's using the ports
sudo lsof -i :9000
sudo lsof -i :6379

# Option 1: Stop conflicting service
# Option 2: Change ports in docker-compose.infra.yml
```

## Advanced Usage

### Custom Infrastructure Configuration

Edit `docker-compose.infra.yml` to customize:

```yaml
services:
  redis:
    environment:
      - REDIS_PASSWORD=your-password  # Add password
    ports:
      - "6380:6379"  # Change port
```

### Environment Variable Override

Create `.env` file manually to override detection:

```env
REDIS_HOST=custom-redis-host
MINIO_HOST=custom-minio-host
ELASTICSEARCH_HOST=custom-es-host
```

### Production Setup

For production, use dedicated infrastructure:

```bash
# Don't use shared infrastructure in production
# Instead, use managed services:
#   - AWS ElastiCache (Redis)
#   - AWS S3 (MinIO replacement)
#   - AWS Elasticsearch/OpenSearch

# Configure via environment variables
export REDIS_HOST=production-redis.amazonaws.com
export MINIO_HOST=s3.amazonaws.com
export ELASTICSEARCH_HOST=es.amazonaws.com

# Deploy
make prod
```

### CI/CD Integration

```yaml
# .github/workflows/deploy.yml
steps:
  - name: Start Shared Infrastructure
    run: make infra-start

  - name: Run Tests
    run: |
      ./start.sh
      make test

  - name: Cleanup
    run: |
      docker compose down
      make infra-stop
```

## Performance Considerations

### Resource Usage

**Standalone Mode** (per project):
- Redis: ~50MB RAM
- MinIO: ~100MB RAM
- Elasticsearch: ~1GB RAM
- **Total: ~1.2GB per project**

**Shared Mode** (all projects):
- **Total: ~1.2GB for ALL projects**

### When to Use Which Mode

**Use Shared Mode:**
- Local development with multiple projects
- Limited RAM (< 8GB)
- Frequently switching between projects
- Testing inter-service communication

**Use Standalone Mode:**
- Production environments
- Single-project development
- Need isolation between projects
- Testing infrastructure changes

## Best Practices

1. **Start shared infrastructure first** on dev machines
   ```bash
   # Add to ~/.bashrc or ~/.zshrc
   alias dev-infra="cd ~/infrastructure && docker compose -f docker-compose.infra.yml up -d"
   ```

2. **Monitor shared infrastructure**
   ```bash
   # Create a monitoring alias
   alias infra-health="docker ps | grep 'shared-'"
   ```

3. **Regular cleanup**
   ```bash
   # Weekly cleanup
   make prune
   ```

4. **Use make commands** for consistency
   - `make start` instead of `./start.sh`
   - `make logs` instead of `docker compose logs -f`

5. **Backup shared data** before cleanup
   ```bash
   # Backup MinIO data
   docker exec shared-minio mc mirror local/ingestify-uploads ./backups/
   ```

## Migration Guide

### From Standalone to Shared

```bash
# 1. Stop current project
docker compose down

# 2. Start shared infrastructure
make infra-start

# 3. Restart project (will detect shared infra)
make start
```

### From Shared to Standalone

```bash
# 1. Stop project
docker compose down

# 2. Stop shared infrastructure
make infra-stop

# 3. Restart in standalone mode
docker compose --profile infra up -d --build
```

## References

- [Docker Compose Profiles](https://docs.docker.com/compose/profiles/)
- [Docker Networks](https://docs.docker.com/network/)
- [MinIO Client (mc)](https://min.io/docs/minio/linux/reference/minio-mc.html)
- [Redis Docker](https://hub.docker.com/_/redis)
- [Elasticsearch Docker](https://www.elastic.co/guide/en/elasticsearch/reference/current/docker.html)

## Support

For issues or questions:

1. Check logs: `make logs`
2. View status: `make ps`
3. Test connectivity: `make test-api`
4. Review this guide
5. Check main [README.md](../README.md)

---

**Last Updated**: 2025-11-06
**Version**: 1.0.0
