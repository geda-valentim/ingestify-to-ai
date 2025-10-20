# Python 3.13+ Compatibility

## Overview

This project is compatible with Python 3.13 and later versions. Previously, the project was limited to Python 3.10 due to the `distutils` module being removed in Python 3.12+.

## Changes Made

### 1. Updated Requirements

Added `setuptools>=75.0.0` to `backend/requirements.txt`:
```txt
# Python 3.13+ compatibility - setuptools provides distutils
setuptools>=75.0.0
```

**Why?** The `docling` package depends on `pylatexenc`, which still uses the deprecated `distutils` module. Modern `setuptools` (75.0.0+) provides a compatibility layer that makes `distutils` available again.

### 2. Updated Dockerfiles (Optional)

The Dockerfiles can now use Python 3.13 instead of 3.10:
- `docker/Dockerfile.api`
- `docker/Dockerfile.worker`

Change from:
```dockerfile
FROM python:3.10-slim
```

To:
```dockerfile
FROM python:3.13-slim
```

## Installation

### Local Development

```bash
# Python 3.13 or later required
cd backend

# Install dependencies
pip install -r requirements.txt
```

### Docker

```bash
# Build with Python 3.13
docker compose build api worker

# Run services
docker compose up -d
```

## Compatibility Notes

- **Minimum Python Version**: 3.13+ (recommended)
- **Also works with**: Python 3.10, 3.11, 3.12
- **Key dependency**: `setuptools>=75.0.0` must be installed first

## Troubleshooting

### Error: "ModuleNotFoundError: No module named 'distutils'"

**Solution**: Install setuptools first:
```bash
pip install 'setuptools>=75.0.0'
pip install -r requirements.txt
```

### Error: "setup.py egg_info did not run successfully"

**Cause**: Old setuptools version or setuptools not installed.

**Solution**:
```bash
pip install --upgrade setuptools
```

## Why This Matters

- **Future-proof**: Works with latest Python versions
- **Modern libraries**: Can use Python 3.13 features and performance improvements
- **Development experience**: Developers can use their system Python without downgrading
- **Security**: Latest Python versions have security fixes

## Dependencies Using distutils

The following dependencies still rely on `distutils`:
- `pylatexenc` (via `docling`)

These will work through the `setuptools` compatibility layer until they migrate to modern packaging standards.
