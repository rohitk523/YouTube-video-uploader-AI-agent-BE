"""
Pydantic schemas for upload operations
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """Schema for upload response."""
    
    id: UUID
    filename: str
    original_filename: str
    file_type: str
    file_size_mb: float
    upload_time: datetime
    
    class Config:
        from_attributes = True


class TranscriptUpload(BaseModel):
    """Schema for transcript text upload."""
    
    content: str = Field(
        ..., 
        min_length=1, 
        max_length=10000, 
        description="Transcript content for TTS"
    )


class FileUploadInfo(BaseModel):
    """Schema for file upload information."""
    
    file_type: str
    file_size_bytes: int
    content_type: str
    is_valid: bool
    error_message: str = ""


class SupportedVoices(BaseModel):
    """Schema for supported TTS voices."""
    
    voices: list[str] = [
        "alloy", 
        "echo", 
        "fable", 
        "onyx", 
        "nova", 
        "shimmer"
    ]
    default_voice: str = "alloy"


class HealthCheck(BaseModel):
    """Schema for health check response."""
    
    status: str = "healthy"
    timestamp: datetime
    version: str = "1.0.0"
    database_connected: bool = True
    upload_directory_accessible: bool = True


class ApiInfo(BaseModel):
    """Schema for API information."""
    
    name: str = "YouTube Shorts Creator API"
    version: str = "1.0.0"
    description: str = "Create YouTube Shorts with AI voiceover"
    endpoints: dict = {
        "upload": "/api/v1/upload",
        "jobs": "/api/v1/jobs", 
        "youtube": "/api/v1/youtube",
        "health": "/api/v1/health",
        "docs": "/docs"
    } 