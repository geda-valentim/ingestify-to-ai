from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, APIKeyHeader
from datetime import datetime
import logging

from shared.config import get_settings
from shared.schemas import ErrorResponse
from api.routes import router
from api.auth_routes import router as auth_router
from api.apikey_routes import router as apikey_router
from api.admin_routes import router as admin_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Security schemes for Swagger UI
security_scheme_bearer = HTTPBearer()
security_scheme_apikey = APIKeyHeader(name="X-API-Key")

# Create FastAPI app
app = FastAPI(
    title="Doc2MD API",
    description="""
API assíncrona para conversão de documentos para Markdown usando Docling

## Autenticação

Esta API suporta dois métodos de autenticação:

### 1. Bearer Token (JWT)
1. Registre um usuário em `/auth/register`
2. Faça login em `/auth/login` para obter o token
3. Clique no botão **"Authorize"** (cadeado 🔒) no topo desta página
4. Cole o token no campo "bearerAuth" (sem prefixo "Bearer")
5. Clique em "Authorize"

### 2. API Key
1. Faça login para obter um token JWT
2. Crie uma API Key em `/api-keys/`
3. Clique no botão **"Authorize"** (cadeado 🔒)
4. Cole a API Key no campo "apiKeyAuth"
5. Clique em "Authorize"

Após autorizar, todos os endpoints protegidos usarão automaticamente suas credenciais.
""",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={
        "persistAuthorization": True,  # Mantém token entre reloads
    }
)

# Add security schemes to OpenAPI
app.openapi_schema = None  # Force regeneration


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi
    import json

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Replace default security scheme names with our custom names
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token obtido via /auth/login"
        },
        "apiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API Key criada via /api-keys/"
        }
    }

    # Replace security references in all paths
    for path in openapi_schema.get("paths", {}).values():
        for operation in path.values():
            if isinstance(operation, dict) and "security" in operation:
                new_security = []
                for security_req in operation["security"]:
                    # Replace HTTPBearer with bearerAuth
                    if "HTTPBearer" in security_req:
                        new_security.append({"bearerAuth": []})
                    # Replace APIKeyHeader with apiKeyAuth
                    elif "APIKeyHeader" in security_req:
                        new_security.append({"apiKeyAuth": []})
                    else:
                        new_security.append(security_req)
                operation["security"] = new_security

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    if settings.environment == "production":
        message = "Internal server error"
    else:
        message = str(exc)

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": message,
            }
        }
    )


# Startup/Shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting Doc2MD API...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Redis host: {settings.redis_host}:{settings.redis_port}")
    logger.info(f"MySQL database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'N/A'}")
    logger.info(f"Elasticsearch: {settings.elasticsearch_url}")
    logger.info(f"MinIO endpoint: {settings.minio_endpoint}")

    # Initialize MySQL database (create tables if they don't exist)
    try:
        from shared.database import init_db
        logger.info("Initializing MySQL database...")
        init_db()
        logger.info("✓ MySQL database initialized successfully")
    except Exception as e:
        logger.error(f"✗ Failed to initialize MySQL database: {e}")
        if settings.environment == "production":
            raise  # Fail fast in production

    # Check Elasticsearch connection
    try:
        from shared.elasticsearch_client import get_es_client
        es_client = get_es_client()
        if es_client.health_check():
            logger.info("✓ Elasticsearch connection OK")
        else:
            logger.warning("✗ Elasticsearch not available (search features will be limited)")
    except Exception as e:
        logger.warning(f"✗ Elasticsearch connection failed: {e}")
        # Don't fail - ES is optional for core functionality

    # Check Redis connection
    try:
        from shared.redis_client import get_redis_client
        redis_client = get_redis_client()
        if redis_client.ping():
            logger.info("✓ Redis connection OK")
        else:
            logger.error("✗ Redis not available - API cannot function")
            if settings.environment == "production":
                raise RuntimeError("Redis connection required")
    except Exception as e:
        logger.error(f"✗ Redis connection failed: {e}")
        if settings.environment == "production":
            raise

    # Initialize MinIO and ensure buckets exist
    try:
        from shared.minio_client import get_minio_client
        logger.info("Initializing MinIO object storage...")
        minio_client = get_minio_client()

        # Test connection
        if minio_client.health_check():
            logger.info("✓ MinIO connection OK")
            logger.info(f"  - Credentials: {settings.minio_access_key} / {'*' * len(settings.minio_secret_key)}")
            logger.info(f"  - Buckets created: {settings.minio_bucket_uploads}, {settings.minio_bucket_pages}, {settings.minio_bucket_audio}, {settings.minio_bucket_results}")
        else:
            logger.warning("✗ MinIO not available (file storage will use filesystem fallback)")
    except Exception as e:
        logger.warning(f"✗ MinIO initialization failed: {e}")
        logger.warning("  Continuing with filesystem storage fallback")
        # Don't fail - MinIO is optional, we can use filesystem fallback


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Doc2MD API...")


# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(apikey_router, prefix="/api-keys", tags=["API Keys"])
app.include_router(admin_router)  # Admin routes (already has /admin prefix)
app.include_router(router)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Doc2MD API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development",
    )
