"""
Job model for tracking YouTube Short creation with S3 support
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DECIMAL, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class Job(Base):
    """Job model for tracking YouTube Short creation progress with S3 storage."""
    
    __tablename__ = "jobs"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4
    )
    
    # Job status and progress
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="pending"
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Content details
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    voice: Mapped[str] = mapped_column(String(20), default="alloy")
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))
    
    # Mock mode flag
    mock_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Video source references
    video_upload_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("uploads.id")
    )
    s3_video_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("videos.id")
    )
    
    # Transcript source reference
    transcript_upload_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("uploads.id")
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # S3 Storage paths (for processed files)
    processed_video_s3_key: Mapped[Optional[str]] = mapped_column(String(500))
    audio_s3_key: Mapped[Optional[str]] = mapped_column(String(500))
    final_video_s3_key: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Legacy file paths (kept for backward compatibility)
    original_video_path: Mapped[Optional[str]] = mapped_column(String(500))
    transcript_content: Mapped[Optional[str]] = mapped_column(Text)
    processed_video_path: Mapped[Optional[str]] = mapped_column(String(500))
    audio_path: Mapped[Optional[str]] = mapped_column(String(500))
    final_video_path: Mapped[Optional[str]] = mapped_column(String(500))
    
    # YouTube result
    youtube_video_id: Mapped[Optional[str]] = mapped_column(String(100))
    youtube_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Processing flags
    temp_files_cleaned: Mapped[bool] = mapped_column(Boolean, default=False)
    permanent_storage: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Metadata
    video_duration: Mapped[Optional[int]] = mapped_column(Integer)
    file_size_mb: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 2))
    processing_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    
    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title='{self.title}', status='{self.status}', video_upload_id='{self.video_upload_id}')>"
    
    @property
    def has_s3_storage(self) -> bool:
        """Check if job uses S3 storage."""
        return bool(self.video_upload_id or self.transcript_upload_id)
    
    @property
    def is_processing_complete(self) -> bool:
        """Check if processing is complete."""
        return self.status in ["completed", "failed"]
    
    @property
    def can_cleanup_temp_files(self) -> bool:
        """Check if temp files can be cleaned up."""
        return self.is_processing_complete and not self.temp_files_cleaned 