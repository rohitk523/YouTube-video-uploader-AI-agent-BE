"""
Middleware for CORS and security
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings

settings = get_settings()


def add_cors_middleware(app: FastAPI) -> None:
    """
    Add CORS middleware to FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Requested-With",
            "Accept",
            "Origin",
            "User-Agent",
            "X-CSRF-Token"
        ],
        expose_headers=["X-Total-Count", "X-Page-Count"],
        max_age=600,  # 10 minutes
    )


def add_security_middleware(app: FastAPI) -> None:
    """
    Add security middleware to FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    # Add trusted host middleware
    if settings.debug:
        # In debug mode, allow all hosts
        allowed_hosts = ["*"]
    else:
        # In production, allow specific hosts
        allowed_hosts = [
            "yourdomain.com", 
            "localhost", 
            "127.0.0.1", 
            "127.0.0.1:8000",
            "localhost:8000",
            "0.0.0.0",
            "0.0.0.0:8000"
        ]
    
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts
    )


def add_request_logging_middleware(app: FastAPI) -> None:
    """
    Add request logging middleware.
    
    Args:
        app: FastAPI application instance
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    import time
    import logging
    
    # Use a custom logger name instead of "uvicorn.access" to avoid conflicts
    logger = logging.getLogger("app.middleware")
    
    class RequestLoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            start_time = time.time()
            
            # Log request
            logger.info(f"Request: {request.method} {request.url}")
            
            response: Response = await call_next(request)
            
            # Log response
            process_time = time.time() - start_time
            logger.info(
                f"Response: {response.status_code} | "
                f"Time: {process_time:.4f}s | "
                f"Size: {response.headers.get('content-length', 'unknown')} bytes"
            )
            
            # Add performance headers
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
    
    app.add_middleware(RequestLoggingMiddleware)


def add_file_size_middleware(app: FastAPI) -> None:
    """
    Add middleware to handle large file uploads.
    
    Args:
        app: FastAPI application instance
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    
    class FileSizeMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Check content length for file uploads
            if request.method == "POST" and "/upload" in str(request.url):
                content_length = request.headers.get("content-length")
                if content_length:
                    content_length = int(content_length)
                    max_size = settings.max_file_size_mb * 1024 * 1024
                    
                    if content_length > max_size:
                        return JSONResponse(
                            status_code=413,
                            content={
                                "detail": f"File too large. Maximum size: {settings.max_file_size_mb}MB"
                            }
                        )
            
            return await call_next(request)
    
    app.add_middleware(FileSizeMiddleware) 