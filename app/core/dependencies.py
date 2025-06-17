"""
FastAPI dependencies for authentication and validation
"""

import os
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, UploadFile, status
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.upload import Upload
from app.models.user import User
from app.schemas.upload import FileUploadInfo
from app.services.auth import AuthService

settings = get_settings()
security = HTTPBearer(auto_error=False)


async def get_current_user(
    token: Optional[str] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get current user from authentication token.
    
    Args:
        token: Bearer token from Authorization header
        db: Database session
        
    Returns:
        User: Current authenticated user
        
    Raises:
        HTTPException: If authentication fails
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}
    )
    
    if not token:
        raise credentials_exception
    
    # HTTPBearer automatically extracts the token from "Bearer <token>" format
    token_value = token.credentials
    
    # Verify token
    token_data = AuthService.verify_token(token_value)
    if not token_data:
        raise credentials_exception
    
    # Get user from database
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    if not user:
        raise credentials_exception
    
    return user


def verify_file_upload(file: UploadFile) -> FileUploadInfo:
    """
    Verify uploaded file meets requirements.
    
    Args:
        file: Uploaded file from FastAPI
        
    Returns:
        FileUploadInfo: Validation result
        
    Raises:
        HTTPException: If file validation fails
    """
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning
    
    max_size_bytes = settings.max_file_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {settings.max_file_size_mb}MB"
        )
    
    # Check file extension
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required"
        )
    
    file_extension = file.filename.split(".")[-1].lower()
    
    # Determine file type and validate
    is_video = file_extension in settings.allowed_video_types
    is_transcript = file_extension in settings.allowed_transcript_types
    
    if not (is_video or is_transcript):
        allowed_types = settings.allowed_video_types + settings.allowed_transcript_types
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_types)}"
        )
    
    file_type = "video" if is_video else "transcript"
    
    return FileUploadInfo(
        file_type=file_type,
        file_size_bytes=file_size,
        content_type=file.content_type or "",
        is_valid=True
    )


async def get_upload_by_id(
    upload_id: UUID,
    db: AsyncSession = Depends(get_db)
) -> Upload:
    """
    Get upload by ID.
    
    Args:
        upload_id: Upload UUID
        db: Database session
        
    Returns:
        Upload: Upload record
        
    Raises:
        HTTPException: If upload not found
    """
    from sqlalchemy import select
    
    result = await db.execute(
        select(Upload).where(Upload.id == upload_id, Upload.is_active == True)
    )
    upload = result.scalar_one_or_none()
    
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found"
        )
    
    return upload


def verify_upload_directory() -> bool:
    """
    Verify upload directory exists and is writable.
    
    Returns:
        bool: True if directory is accessible
    """
    try:
        os.makedirs(settings.upload_directory, exist_ok=True)
        test_file = os.path.join(settings.upload_directory, ".test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except Exception:
        return False 