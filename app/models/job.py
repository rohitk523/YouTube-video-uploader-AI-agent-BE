"""
Job model for tracking YouTube Short creation
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DECIMAL, Integer, String, Text, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class Job(Base):
    """Job model for tracking YouTube Short creation progress."""
    
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
    
    # Content details
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    voice: Mapped[str] = mapped_column(String(20), default="alloy")
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))
    
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
    
    # File paths
    original_video_path: Mapped[Optional[str]] = mapped_column(String(500))
    transcript_content: Mapped[Optional[str]] = mapped_column(Text)
    processed_video_path: Mapped[Optional[str]] = mapped_column(String(500))
    audio_path: Mapped[Optional[str]] = mapped_column(String(500))
    final_video_path: Mapped[Optional[str]] = mapped_column(String(500))
    
    # YouTube result
    youtube_video_id: Mapped[Optional[str]] = mapped_column(String(100))
    youtube_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Metadata
    video_duration: Mapped[Optional[int]] = mapped_column(Integer)
    file_size_mb: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 2))
    processing_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    
    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title='{self.title}', status='{self.status}')>" 