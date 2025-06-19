"""
Pydantic schemas for video operations
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field


class VideoBase(BaseModel):
    """Base video schema with common fields."""
    
    filename: str = Field(..., description="Sanitized filename")
    original_filename: str = Field(..., description="Original filename from upload")
    s3_key: str = Field(..., description="S3 object key")
    s3_url: str = Field(..., description="S3 object URL")
    content_type: str = Field(..., description="MIME type of the video")
    file_size: int = Field(..., ge=0, description="File size in bytes")
    duration: Optional[Decimal] = Field(None, description="Video duration in seconds")
    thumbnail_url: Optional[str] = Field(None, description="URL to video thumbnail")
    video_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional video metadata")


class VideoCreate(VideoBase):
    """Schema for creating a video record."""
    
    user_id: UUID = Field(..., description="ID of the user who owns the video")
    s3_bucket: str = Field(..., description="S3 bucket name")


class VideoUpdate(BaseModel):
    """Schema for updating video metadata."""
    
    duration: Optional[Decimal] = Field(None, description="Video duration in seconds")
    thumbnail_url: Optional[str] = Field(None, description="URL to video thumbnail")
    video_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional video metadata")


class VideoResponse(VideoBase):
    """Schema for video response with additional fields."""
    
    id: UUID = Field(..., description="Unique video ID")
    uploaded_at: datetime = Field(..., description="Upload timestamp", alias="created_at")
    file_size_mb: float = Field(..., description="File size in megabytes")
    
    class Config:
        from_attributes = True
        populate_by_name = True


class VideoListResponse(BaseModel):
    """Schema for paginated video list response."""
    
    videos: List[VideoResponse] = Field(..., description="List of videos")
    total_count: int = Field(..., ge=0, description="Total number of videos")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    has_more: bool = Field(..., description="Whether there are more pages")


class RecentVideosResponse(BaseModel):
    """Schema for recent videos response."""
    
    videos: List[VideoResponse] = Field(..., description="List of recent videos")


class VideoSearchQuery(BaseModel):
    """Schema for video search parameters."""
    
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(10, ge=1, le=50, description="Items per page")
    search: Optional[str] = Field(None, description="Search term for filename")
    sort_by: str = Field("created_at", description="Field to sort by")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="Sort order")


class VideoStats(BaseModel):
    """Schema for video statistics."""
    
    total_videos: int = Field(..., ge=0, description="Total number of videos")
    total_size_mb: float = Field(..., ge=0, description="Total size in megabytes")
    total_duration_hours: Optional[float] = Field(None, ge=0, description="Total duration in hours")
    videos_this_month: int = Field(..., ge=0, description="Videos uploaded this month")
    average_file_size_mb: Optional[float] = Field(None, ge=0, description="Average file size in MB") 