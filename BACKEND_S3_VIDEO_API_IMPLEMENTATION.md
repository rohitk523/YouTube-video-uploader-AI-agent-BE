# Backend S3 Video Management API Implementation

## Overview

This document provides the complete backend implementation for S3 video management features to support the Flutter frontend's video selection functionality.

## Database Schema

### Add Videos Table

```sql
-- Add to your database migration
CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    s3_key VARCHAR(500) NOT NULL UNIQUE,
    s3_url VARCHAR(1000) NOT NULL,
    s3_bucket VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL,
    duration DECIMAL(10, 2) NULL,
    thumbnail_s3_key VARCHAR(500) NULL,
    thumbnail_url VARCHAR(1000) NULL,
    metadata JSONB NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE NULL
);

-- Add indexes for performance
CREATE INDEX idx_videos_user_id ON videos(user_id);
CREATE INDEX idx_videos_created_at ON videos(created_at DESC);
CREATE INDEX idx_videos_filename ON videos(filename);
CREATE INDEX idx_videos_s3_key ON videos(s3_key);
```

## API Endpoints

### 1. Get S3 Videos (Paginated)

**GET** `/api/v1/videos/s3-videos`

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
```
page: int = 1               # Page number
page_size: int = 10         # Items per page (max 50)
search: str = None          # Search in filename
sort_by: str = "created_at" # Sort field
sort_order: str = "desc"    # asc or desc
```

**Response (200 OK):**
```json
{
  "videos": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "my_video.mp4",
      "original_filename": "My Video.mp4",
      "s3_key": "uploads/users/550e8400-e29b-41d4-a716-446655440001/videos/1704123456_my_video.mp4",
      "s3_url": "https://your-bucket.s3.amazonaws.com/uploads/users/550e8400-e29b-41d4-a716-446655440001/videos/1704123456_my_video.mp4",
      "content_type": "video/mp4",
      "file_size": 15728640,
      "duration": 45.5,
      "thumbnail_url": "https://your-bucket.s3.amazonaws.com/uploads/users/550e8400-e29b-41d4-a716-446655440001/thumbnails/1704123456_my_video_thumb.jpg",
      "uploaded_at": "2024-01-15T10:30:00Z",
      "metadata": {
        "resolution": "1920x1080",
        "fps": 30,
        "codec": "h264"
      }
    }
  ],
  "total_count": 25,
  "page": 1,
  "page_size": 10,
  "total_pages": 3,
  "has_more": true
}
```

### 2. Get Recent Videos

**GET** `/api/v1/videos/s3-videos/recent`

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
```
limit: int = 5  # Number of recent videos (max 20)
```

**Response (200 OK):**
```json
{
  "videos": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "recent_video.mp4",
      "s3_key": "uploads/users/.../recent_video.mp4",
      "s3_url": "https://bucket.s3.amazonaws.com/.../recent_video.mp4",
      "content_type": "video/mp4",
      "file_size": 12345678,
      "duration": 30.0,
      "thumbnail_url": "https://bucket.s3.amazonaws.com/.../thumb.jpg",
      "uploaded_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### 3. Get Video by S3 Key

**GET** `/api/v1/videos/s3-videos/by-key/{s3_key}`

**Headers:** `Authorization: Bearer <access_token>`

**Response (200 OK):** Single video object (same structure as above)

### 4. Update Video Upload Endpoint

Modify your existing video upload endpoint to also store metadata in the videos table:

**POST** `/api/v1/upload/video`

**After successful S3 upload, also save to database:**

```python
# In your upload endpoint
async def save_video_metadata(
    user_id: str,
    filename: str,
    original_filename: str,
    s3_key: str,
    s3_url: str,
    content_type: str,
    file_size: int,
    duration: float = None
) -> VideoModel:
    """Save video metadata to database after S3 upload"""
    video = VideoModel(
        filename=filename,
        original_filename=original_filename,
        s3_key=s3_key,
        s3_url=s3_url,
        s3_bucket=settings.S3_BUCKET_NAME,
        content_type=content_type,
        file_size=file_size,
        duration=duration,
        user_id=user_id
    )
    
    # Save to database
    db.add(video)
    await db.commit()
    return video
```

## Python FastAPI Implementation

### 1. Pydantic Models

```python
# app/models/video_models.py
from pydantic import BaseModel, UUID4
from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal

class VideoBase(BaseModel):
    filename: str
    original_filename: str
    s3_key: str
    s3_url: str
    content_type: str
    file_size: int
    duration: Optional[Decimal] = None
    thumbnail_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class VideoCreate(VideoBase):
    user_id: UUID4

class VideoResponse(VideoBase):
    id: UUID4
    uploaded_at: datetime
    
    class Config:
        from_attributes = True

class VideoListResponse(BaseModel):
    videos: list[VideoResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_more: bool
```

### 2. Database Model (SQLAlchemy)

```python
# app/models/database/video.py
from sqlalchemy import Column, String, BigInteger, DECIMAL, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database.base import BaseModel
import uuid

class Video(BaseModel):
    __tablename__ = "videos"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    s3_key = Column(String(500), nullable=False, unique=True)
    s3_url = Column(String(1000), nullable=False)
    s3_bucket = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    duration = Column(DECIMAL(10, 2), nullable=True)
    thumbnail_s3_key = Column(String(500), nullable=True)
    thumbnail_url = Column(String(1000), nullable=True)
    metadata = Column(JSONB, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="videos")
```

### 3. Repository Layer

```python
# app/repositories/video_repository.py
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func, or_
from app.models.database.video import Video
from app.models.video_models import VideoCreate
from typing import List, Optional, Tuple
from uuid import UUID

class VideoRepository:
    def __init__(self, db: Session):
        self.db = db
    
    async def get_user_videos_paginated(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 10,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Tuple[List[Video], int]:
        """Get paginated videos for user with optional search"""
        
        query = self.db.query(Video).filter(
            Video.user_id == user_id,
            Video.deleted_at.is_(None)
        )
        
        # Search functionality
        if search:
            search_filter = or_(
                Video.filename.ilike(f"%{search}%"),
                Video.original_filename.ilike(f"%{search}%")
            )
            query = query.filter(search_filter)
        
        # Sorting
        sort_column = getattr(Video, sort_by, Video.created_at)
        if sort_order.lower() == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        offset = (page - 1) * page_size
        videos = query.offset(offset).limit(page_size).all()
        
        return videos, total_count
    
    async def get_recent_videos(
        self,
        user_id: UUID,
        limit: int = 5
    ) -> List[Video]:
        """Get recent videos for user"""
        return self.db.query(Video).filter(
            Video.user_id == user_id,
            Video.deleted_at.is_(None)
        ).order_by(desc(Video.created_at)).limit(limit).all()
    
    async def get_by_s3_key(
        self,
        user_id: UUID,
        s3_key: str
    ) -> Optional[Video]:
        """Get video by S3 key for specific user"""
        return self.db.query(Video).filter(
            Video.user_id == user_id,
            Video.s3_key == s3_key,
            Video.deleted_at.is_(None)
        ).first()
    
    async def create_video(self, video_data: VideoCreate) -> Video:
        """Create new video record"""
        video = Video(**video_data.dict())
        self.db.add(video)
        self.db.commit()
        self.db.refresh(video)
        return video
```

### 4. API Router

```python
# app/routers/video_router.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.auth.dependencies import get_current_user
from app.models.user_models import User
from app.models.video_models import VideoListResponse, VideoResponse
from app.repositories.video_repository import VideoRepository
from typing import Optional
import math

router = APIRouter(prefix="/videos", tags=["videos"])

@router.get("/s3-videos", response_model=VideoListResponse)
async def get_s3_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    search: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get paginated list of user's S3 videos"""
    
    video_repo = VideoRepository(db)
    
    try:
        videos, total_count = await video_repo.get_user_videos_paginated(
            user_id=current_user.id,
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        total_pages = math.ceil(total_count / page_size)
        has_more = page < total_pages
        
        return VideoListResponse(
            videos=[VideoResponse.from_orm(video) for video in videos],
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more=has_more
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching videos: {str(e)}")

@router.get("/s3-videos/recent")
async def get_recent_videos(
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recent videos for quick selection"""
    
    video_repo = VideoRepository(db)
    
    try:
        videos = await video_repo.get_recent_videos(
            user_id=current_user.id,
            limit=limit
        )
        
        return {
            "videos": [VideoResponse.from_orm(video) for video in videos]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recent videos: {str(e)}")

@router.get("/s3-videos/by-key/{s3_key:path}", response_model=VideoResponse)
async def get_video_by_s3_key(
    s3_key: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get video by S3 key"""
    
    video_repo = VideoRepository(db)
    
    try:
        video = await video_repo.get_by_s3_key(
            user_id=current_user.id,
            s3_key=s3_key
        )
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return VideoResponse.from_orm(video)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching video: {str(e)}")
```

### 5. Update Existing Upload Endpoint

```python
# Modify your existing upload/video endpoint
@router.post("/video")
async def upload_video(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload video to S3 and save metadata"""
    
    # ... existing upload logic ...
    
    # After successful S3 upload, save to database
    video_repo = VideoRepository(db)
    
    video_data = VideoCreate(
        filename=safe_filename,
        original_filename=file.filename,
        s3_key=s3_key,
        s3_url=s3_url,
        content_type=file.content_type,
        file_size=file.size,
        user_id=current_user.id,
        # Add duration if you can extract it from video
        # duration=get_video_duration(file_path) if get_video_duration else None
    )
    
    await video_repo.create_video(video_data)
    
    # ... rest of your response logic ...
```

## Usage in Job Creation

Update your job creation endpoint to accept either:
1. `video_upload_id` (existing uploaded file)
2. `s3_video_id` (existing S3 video)

```python
# In your job creation endpoint
class JobCreateRequest(BaseModel):
    # Either provide upload_id OR s3_video_id
    video_upload_id: Optional[str] = None
    s3_video_id: Optional[UUID4] = None
    
    transcript_text: Optional[str] = None
    transcript_upload_id: Optional[str] = None
    
    # ... other fields ...

@router.post("/create")
async def create_job(
    request: JobCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Validate that either video_upload_id or s3_video_id is provided
    if not request.video_upload_id and not request.s3_video_id:
        raise HTTPException(status_code=400, detail="Either video_upload_id or s3_video_id must be provided")
    
    if request.video_upload_id and request.s3_video_id:
        raise HTTPException(status_code=400, detail="Provide either video_upload_id or s3_video_id, not both")
    
    # Get video information
    if request.s3_video_id:
        video_repo = VideoRepository(db)
        video = await video_repo.get_by_id(request.s3_video_id, current_user.id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        video_s3_key = video.s3_key
        video_filename = video.filename
    else:
        # Handle existing upload_id logic
        # ... existing code ...
    
    # Continue with job creation using video_s3_key and video_filename
```

## Performance Optimizations

1. **Database Indexes**: Already included in schema
2. **Caching**: Consider caching recent videos for 5-10 minutes
3. **Thumbnail Generation**: Generate thumbnails on upload for better UX
4. **S3 Presigned URLs**: Use presigned URLs for secure access

## Testing

```python
# Test the endpoints
import pytest
from fastapi.testclient import TestClient

def test_get_recent_videos():
    response = client.get("/api/v1/videos/s3-videos/recent?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "videos" in data
    assert len(data["videos"]) <= 5

def test_get_s3_videos_paginated():
    response = client.get("/api/v1/videos/s3-videos?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert "videos" in data
    assert "total_count" in data
    assert "has_more" in data
```

This implementation provides a complete backend solution that supports:
- ✅ Top 5 recent videos for quick selection
- ✅ Full video library with pagination and search
- ✅ S3 video reuse in job creation
- ✅ No duplication in S3 bucket
- ✅ Performance optimized with proper indexing
- ✅ User-scoped video access for security 