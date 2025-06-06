"""
Upload model for tracking file uploads
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Boolean, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Upload(Base):
    """Upload model for tracking file uploads."""
    
    __tablename__ = "uploads"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4
    )
    
    # File details
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    # Timestamps
    upload_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Relationships
    job_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("jobs.id")
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    def __repr__(self) -> str:
        return f"<Upload(id={self.id}, filename='{self.filename}', file_type='{self.file_type}')>"
    
    @property
    def file_size_mb(self) -> float:
        """Get file size in megabytes."""
        return round(self.file_size_bytes / (1024 * 1024), 2) 