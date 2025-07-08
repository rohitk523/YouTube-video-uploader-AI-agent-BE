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
    
    # Video source - either from upload or existing S3 video
    video_upload_id: Optional[UUID] = Field(None, description="ID of uploaded video file in S3")
    s3_video_id: Optional[UUID] = Field(None, description="ID of existing S3 video for reuse")
    
    # Transcript source
    transcript_upload_id: Optional[UUID] = Field(None, description="ID of uploaded transcript file in S3")
    
    # Direct transcript content (alternative to transcript_upload_id)
    transcript_content: Optional[str] = Field(
        None, 
        min_length=1, 
        max_length=10000, 
        description="Direct transcript content (alternative to transcript_upload_id)"
    )
    
    # Backward compatibility field - will be mapped to transcript_content
    transcript_text: Optional[str] = Field(
        None, 
        min_length=1, 
        max_length=10000, 
        description="Legacy field name for transcript content (mapped to transcript_content)"
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
    def validate_sources(self) -> "JobCreate":
        """Validate video and transcript sources."""
        # Validate video source
        if not self.video_upload_id and not self.s3_video_id:
            raise ValueError("Either video_upload_id or s3_video_id must be provided")
        
        if self.video_upload_id and self.s3_video_id:
            raise ValueError("Provide either video_upload_id or s3_video_id, not both")
        
        # Handle backward compatibility: map transcript_text to transcript_content
        if self.transcript_text and not self.transcript_content:
            self.transcript_content = self.transcript_text
        
        # Validate transcript source
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
    
    # Video and transcript source references
    video_upload_id: Optional[UUID] = None
    s3_video_id: Optional[UUID] = None
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