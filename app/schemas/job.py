"""
Pydantic schemas for job operations
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class JobCreate(BaseModel):
    """Schema for creating a new job."""
    
    title: str = Field(..., min_length=1, max_length=100, description="Video title")
    description: str = Field("", max_length=5000, description="Video description")
    voice: str = Field("alloy", description="TTS voice to use")
    tags: List[str] = Field(default_factory=list, max_length=10, description="Video tags")
    upload_id: Optional[UUID] = Field(None, description="ID of uploaded video file")
    transcript_content: str = Field(
        ..., 
        min_length=1, 
        max_length=10000, 
        description="Transcript content for TTS"
    )
    
    @field_validator("voice")
    @classmethod
    def validate_voice(cls, v: str) -> str:
        """Validate TTS voice option."""
        allowed_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
        if v not in allowed_voices:
            raise ValueError(f"Voice must be one of: {', '.join(allowed_voices)}")
        return v
    
    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        """Validate tags list."""
        if len(v) > 10:
            raise ValueError("Maximum 10 tags allowed")
        return [tag.strip() for tag in v if tag.strip()]


class JobResponse(BaseModel):
    """Schema for job response."""
    
    id: UUID
    status: str
    progress: int
    title: str
    description: str
    voice: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    original_video_path: Optional[str] = None
    transcript_content: Optional[str] = None
    processed_video_path: Optional[str] = None
    audio_path: Optional[str] = None
    final_video_path: Optional[str] = None
    youtube_url: Optional[str] = None
    youtube_video_id: Optional[str] = None
    video_duration: Optional[int] = None
    processing_time_seconds: Optional[int] = None
    file_size_mb: Optional[float] = None
    
    class Config:
        from_attributes = True


class JobStatus(BaseModel):
    """Schema for job status response."""
    
    id: UUID
    status: str
    progress: int
    current_step: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class JobList(BaseModel):
    """Schema for listing jobs."""
    
    jobs: List[JobResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class JobProgress(BaseModel):
    """Schema for job progress updates."""
    
    job_id: UUID
    progress: int
    message: str
    status: str 