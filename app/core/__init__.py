"""
Core functionality for YouTube Shorts Creator
"""

from app.core.dependencies import get_current_user, verify_file_upload
from app.core.middleware import add_cors_middleware, add_security_middleware

__all__ = [
    "get_current_user",
    "verify_file_upload", 
    "add_cors_middleware",
    "add_security_middleware"
] 