"""
Pydantic schemas for job operations with S3 support
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class JobCreate(BaseModel):
    """Schema for creating a new job with S3 upload references."""
    
    title: str = Field(..., min_length=1, max_length=100, description="Video title")
    description: str = Field("", max_length=5000, description="Video description")
    voice: str = Field("alloy", description="TTS voice to use")
    tags: List[str] = Field(default_factory=list, max_length=10, description="Video tags")
    
    # S3 Upload references - both are required for job creation
    video_upload_id: UUID = Field(..., description="ID of uploaded video file in S3")
    transcript_upload_id: Optional[UUID] = Field(None, description="ID of uploaded transcript file in S3")
    
    # Direct transcript content (alternative to transcript_upload_id)
    transcript_content: Optional[str] = Field(
        None, 
        min_length=1, 
        max_length=10000, 
        description="Direct transcript content (alternative to transcript_upload_id)"
    )
    
    # Mock mode flag
    mock_mode: bool = Field(
        False, 
        description="If true, skip YouTube upload and make video available for download only"
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
    
    @model_validator(mode='after')
    def validate_transcript_source(self) -> "JobCreate":
        """Validate that either transcript_upload_id or transcript_content is provided."""
        if not self.transcript_upload_id and not self.transcript_content:
            raise ValueError("Either transcript_upload_id or transcript_content must be provided")
        return self


class JobResponse(BaseModel):
    """Schema for job response with S3 support."""
    
    id: UUID
    status: str
    progress: int
    progress_message: Optional[str] = None
    title: str
    description: str
    voice: str
    tags: List[str]
    
    # Upload references
    video_upload_id: Optional[UUID] = None
    transcript_upload_id: Optional[UUID] = None
    
    # Mock mode flag
    mock_mode: bool = False
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    # Error handling
    error_message: Optional[str] = None
    
    # S3 Storage paths (for processed files)
    processed_video_s3_key: Optional[str] = None
    audio_s3_key: Optional[str] = None
    final_video_s3_key: Optional[str] = None
    
    # Legacy fields (kept for backward compatibility)
    original_video_path: Optional[str] = None
    transcript_content: Optional[str] = None
    processed_video_path: Optional[str] = None
    audio_path: Optional[str] = None
    final_video_path: Optional[str] = None
    
    # YouTube result
    youtube_url: Optional[str] = None
    youtube_video_id: Optional[str] = None
    
    # Processing flags
    temp_files_cleaned: bool = False
    permanent_storage: bool = False
    
    # Metadata
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
    progress_message: Optional[str] = None
    current_step: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    temp_files_cleaned: bool = False
    permanent_storage: bool = False
    
    class Config:
        from_attributes = True


class JobList(BaseModel):
    """Schema for job list response."""
    
    jobs: List[JobResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    
    class Config:
        from_attributes = True


class JobProgress(BaseModel):
    """Schema for job progress updates."""
    
    job_id: UUID
    progress: int
    message: str
    status: str


class JobCleanup(BaseModel):
    """Schema for job cleanup operations."""
    
    job_id: UUID
    temp_files_deleted: bool
    s3_files_deleted: List[str]
    error_message: Optional[str] = None 