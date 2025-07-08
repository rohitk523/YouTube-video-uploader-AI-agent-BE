"""
Main FastAPI application for YouTube Shorts Creator
"""

import logging
import warnings
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_database, close_database
from app.core.middleware import (
    add_cors_middleware,
    add_security_middleware,
    add_request_logging_middleware,
    add_file_size_middleware
)
from app.core.dependencies import verify_upload_directory
from app.schemas.upload import HealthCheck, ApiInfo

# Import API routers
from app.api import upload, jobs, youtube, oauth, videos, secrets

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress bcrypt warnings
warnings.filterwarnings("ignore", message=".*bcrypt version.*", category=UserWarning)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan management.
    
    Args:
        app: FastAPI application instance
    """
    # Startup
    logger.info("Starting YouTube Shorts Creator API...")
    
    # Initialize database
    try:
        await init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # Verify upload directory
    if not verify_upload_directory():
        logger.error("Upload directory is not accessible")
        raise RuntimeError("Upload directory setup failed")
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down YouTube Shorts Creator API...")
    
    try:
        await close_database()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during database shutdown: {e}")
    
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Create YouTube Shorts with AI voiceover using Google ADK",
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Add custom exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Custom handler for request validation errors (422).
    Logs the validation errors for debugging.
    """
    logger.warning(f"Request validation failed for {request.method} {request.url}")
    logger.warning(f"Validation errors: {exc.errors()}")
    
    # Don't try to read request body as it may have been consumed
    # The validation errors already contain the problematic input data
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Request validation failed",
            "errors": exc.errors()
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Custom handler for HTTP exceptions.
    Logs authentication and other HTTP errors.
    """
    if exc.status_code == 401:
        logger.warning(f"Authentication failed for {request.method} {request.url}: {exc.detail}")
    elif exc.status_code >= 400:
        logger.warning(f"HTTP {exc.status_code} error for {request.method} {request.url}: {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# Add middleware
add_cors_middleware(app)
add_security_middleware(app)
add_request_logging_middleware(app)
add_file_size_middleware(app)

# Mount static files
try:
    app.mount("/static", StaticFiles(directory=settings.static_directory), name="static")
except Exception as e:
    logger.warning(f"Could not mount static files: {e}")

# Include API routes
app.include_router(
    oauth.router,
    prefix="/api/v1/oauth",
    tags=["OAuth 2.0"]
)
app.include_router(
    upload.router, 
    prefix="/api/v1/upload", 
    tags=["upload"]
)
app.include_router(
    jobs.router, 
    prefix="/api/v1/jobs", 
    tags=["jobs"]
)
app.include_router(
    youtube.router, 
    prefix="/api/v1/youtube", 
    tags=["youtube"]
)
app.include_router(
    videos.router,
    prefix="/api/v1/videos",
    tags=["videos"]
)
app.include_router(
    secrets.router,
    prefix="/api/v1/secrets",
    tags=["secrets"]
)


@app.get("/")
async def root() -> dict:
    """
    Root endpoint with API information.
    
    Returns:
        dict: Basic API information
    """
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.version,
        "docs": "/docs",
        "status": "operational"
    }


@app.get("/api/v1/health", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """
    Health check endpoint.
    
    Returns:
        HealthCheck: Application health status
    """
    # Check database connection
    database_connected = True
    try:
        from app.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        database_connected = False
    
    # Check upload directory
    upload_directory_accessible = verify_upload_directory()
    
    return HealthCheck(
        status="healthy" if database_connected and upload_directory_accessible else "unhealthy",
        timestamp=datetime.now(),
        version=settings.version,
        database_connected=database_connected,
        upload_directory_accessible=upload_directory_accessible
    )


@app.get("/api/v1/info", response_model=ApiInfo)
async def api_info() -> ApiInfo:
    """
    API information endpoint.
    
    Returns:
        ApiInfo: Detailed API information
    """
    return ApiInfo(
        name=settings.app_name,
        version=settings.version,
        description="Create YouTube Shorts with AI voiceover using Google ADK"
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info"
    ) 