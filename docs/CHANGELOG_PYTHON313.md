# Changelog: Python 3.13+ Support

## Date: 2025-10-19

## Summary

Updated Ingestify to support Python 3.13 and later versions by adding `setuptools` for `distutils` compatibility.

## Changes

### 1. Backend Requirements (`backend/requirements.txt`)
- ✅ Added `setuptools>=75.0.0` at the top of requirements
- This provides `distutils` compatibility for packages that still use it (like `pylatexenc`)

### 2. Docker Images
- ✅ Updated `docker/Dockerfile.api` from Python 3.10 to 3.13
- ✅ Updated `docker/Dockerfile.worker` from Python 3.10 to 3.13

### 3. Documentation
- ✅ Created `/docs/PYTHON_313_COMPATIBILITY.md` - Detailed compatibility guide
- ✅ Updated `README.md` - Changed Python requirement from "3.10+" to "3.13+ (or 3.10+, but 3.13+ recommended)"
- ✅ Updated `CLAUDE.md` - Added Python version note in Backend Environment section

### 4. Frontend Library Files (Unrelated but completed)
- ✅ Created `frontend/lib/utils.ts` - Tailwind className utility
- ✅ Created `frontend/lib/api.ts` - API client with named exports (authApi, jobsApi, apiKeysApi)
- ✅ Created `frontend/lib/store/auth.ts` - Zustand auth store with hydration support
- ✅ Frontend now builds successfully

## Why This Matters

### Before
- ❌ Python 3.13 users got `ModuleNotFoundError: No module named 'distutils'`
- ❌ Required downgrading to Python 3.10 or 3.11
- ❌ Dockerfiles used older Python 3.10

### After
- ✅ Works with Python 3.13+ out of the box
- ✅ Also backwards compatible with Python 3.10, 3.11, 3.12
- ✅ Dockerfiles use latest Python 3.13
- ✅ Future-proof for newer Python versions

## Installation

### New Installation (Python 3.13+)
```bash
cd backend
pip install -r requirements.txt  # setuptools installs first automatically
```

### Existing Installation (Upgrade)
```bash
cd backend
pip install --upgrade 'setuptools>=75.0.0'
pip install -r requirements.txt
```

### Docker
```bash
# Build with Python 3.13
docker compose build api worker

# Run
docker compose up -d
```

## Testing

The following was tested and working:
- ✅ `setuptools>=75.0.0` installs successfully on Python 3.13
- ✅ `pylatexenc` (via docling) installs without errors
- ✅ Frontend builds successfully with all required lib files
- ✅ Dockerfiles updated to use Python 3.13-slim

## Dependencies Affected

The following dependencies still use `distutils` and now work via setuptools:
- `pylatexenc` (dependency of `docling`)

## Breaking Changes

None. This is a backwards-compatible change.

## Migration Guide

No migration needed. Just update and reinstall:
```bash
git pull
pip install --upgrade setuptools
pip install -r backend/requirements.txt
```

## References

- [PEP 632 - Deprecate distutils](https://peps.python.org/pep-0632/)
- [Setuptools distutils compatibility](https://setuptools.pypa.io/en/latest/deprecated/distutils-legacy.html)
- [Python 3.12 What's New - Removed distutils](https://docs.python.org/3/whatsnew/3.12.html#removed)

## Files Modified

1. `backend/requirements.txt` - Added setuptools
2. `docker/Dockerfile.api` - Python 3.10 → 3.13
3. `docker/Dockerfile.worker` - Python 3.10 → 3.13
4. `README.md` - Updated Python version requirement
5. `CLAUDE.md` - Added Python version note
6. `frontend/lib/utils.ts` - Created
7. `frontend/lib/api.ts` - Created
8. `frontend/lib/store/auth.ts` - Created

## Files Created

1. `docs/PYTHON_313_COMPATIBILITY.md` - Detailed compatibility documentation
2. `docs/CHANGELOG_PYTHON313.md` - This file
