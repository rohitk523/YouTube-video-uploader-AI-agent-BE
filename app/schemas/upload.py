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


class AITranscriptRequest(BaseModel):
    """Schema for AI transcript generation request."""
    
    context: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Context or topic for transcript generation"
    )
    custom_instructions: str = Field(
        "",
        max_length=500,
        description="Additional instructions for the AI (optional)"
    )


class AITranscriptResponse(BaseModel):
    """Schema for AI transcript generation response."""
    
    status: str
    transcript: str = ""
    word_count: int = 0
    estimated_duration_seconds: float = 0.0
    model_used: str = ""
    tokens_used: dict = {}
    context_provided: str = ""
    error_message: str = ""
    error_type: str = ""


class AITranscriptValidation(BaseModel):
    """Schema for AI transcript context validation."""
    
    valid: bool
    character_count: int = 0
    word_count: int = 0
    estimated_tokens: int = 0
    error: str = ""


class AITranscriptServiceInfo(BaseModel):
    """Schema for AI transcript service information."""
    
    service_name: str
    openai_configured: bool
    langfuse_configured: bool
    langfuse_available: bool
    prompt_file_exists: bool
    default_model: str
    fallback_model: str
    max_tokens: int
    temperature: float 