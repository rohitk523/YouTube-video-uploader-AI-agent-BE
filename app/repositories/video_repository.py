"""
Video repository for database operations
"""

import math
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy import desc, asc, func, or_, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.video import Video
from app.schemas.video import VideoCreate, VideoUpdate


class VideoRepository:
    """Repository for video database operations."""
    
    def __init__(self, db: AsyncSession):
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
        """
        Get paginated videos for user with optional search.
        
        Args:
            user_id: User ID to filter videos
            page: Page number (1-based)
            page_size: Number of items per page
            search: Optional search term for filename
            sort_by: Field to sort by
            sort_order: Sort order (asc/desc)
            
        Returns:
            Tuple of (videos list, total count)
        """
        # Base query
        query = select(Video).where(
            and_(
                Video.user_id == user_id,
                Video.deleted_at.is_(None)
            )
        )
        
        # Search functionality
        if search:
            search_filter = or_(
                Video.filename.ilike(f"%{search}%"),
                Video.original_filename.ilike(f"%{search}%")
            )
            query = query.where(search_filter)
        
        # Count query for total
        count_query = select(func.count(Video.id)).where(
            and_(
                Video.user_id == user_id,
                Video.deleted_at.is_(None)
            )
        )
        if search:
            count_query = count_query.where(search_filter)
        
        # Get total count
        count_result = await self.db.execute(count_query)
        total_count = count_result.scalar()
        
        # Sorting
        sort_column = getattr(Video, sort_by, Video.created_at)
        if sort_order.lower() == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))
        
        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
        # Execute query
        result = await self.db.execute(query)
        videos = result.scalars().all()
        
        return list(videos), total_count
    
    async def get_recent_videos(
        self,
        user_id: UUID,
        limit: int = 5
    ) -> List[Video]:
        """
        Get recent videos for user.
        
        Args:
            user_id: User ID to filter videos
            limit: Number of recent videos to return
            
        Returns:
            List of recent videos
        """
        query = select(Video).where(
            and_(
                Video.user_id == user_id,
                Video.deleted_at.is_(None)
            )
        ).order_by(desc(Video.created_at)).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_by_id(
        self,
        video_id: UUID,
        user_id: UUID
    ) -> Optional[Video]:
        """
        Get video by ID for specific user.
        
        Args:
            video_id: Video ID
            user_id: User ID to ensure ownership
            
        Returns:
            Video if found and owned by user, None otherwise
        """
        query = select(Video).where(
            and_(
                Video.id == video_id,
                Video.user_id == user_id,
                Video.deleted_at.is_(None)
            )
        )
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_s3_key(
        self,
        s3_key: str,
        user_id: UUID
    ) -> Optional[Video]:
        """
        Get video by S3 key for specific user.
        
        Args:
            s3_key: S3 object key
            user_id: User ID to ensure ownership
            
        Returns:
            Video if found and owned by user, None otherwise
        """
        query = select(Video).where(
            and_(
                Video.s3_key == s3_key,
                Video.user_id == user_id,
                Video.deleted_at.is_(None)
            )
        )
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def create_video(self, video_data: VideoCreate) -> Video:
        """
        Create new video record.
        
        Args:
            video_data: Video creation data
            
        Returns:
            Created video
        """
        video = Video(**video_data.model_dump())
        self.db.add(video)
        await self.db.commit()
        await self.db.refresh(video)
        return video
    
    async def update_video(
        self,
        video_id: UUID,
        user_id: UUID,
        update_data: VideoUpdate
    ) -> Optional[Video]:
        """
        Update video metadata.
        
        Args:
            video_id: Video ID
            user_id: User ID to ensure ownership
            update_data: Update data
            
        Returns:
            Updated video if found and owned by user, None otherwise
        """
        video = await self.get_by_id(video_id, user_id)
        if not video:
            return None
        
        # Update fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(video, field, value)
        
        video.updated_at = func.now()
        await self.db.commit()
        await self.db.refresh(video)
        return video
    
    async def soft_delete_video(
        self,
        video_id: UUID,
        user_id: UUID
    ) -> bool:
        """
        Soft delete video (mark as deleted).
        
        Args:
            video_id: Video ID
            user_id: User ID to ensure ownership
            
        Returns:
            True if deleted, False if not found
        """
        video = await self.get_by_id(video_id, user_id)
        if not video:
            return False
        
        video.deleted_at = func.now()
        await self.db.commit()
        return True
    
    async def get_video_stats(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get video statistics for user.
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary with video statistics
        """
        # Get current month start
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        
        # Query for total videos and size
        stats_query = select(
            func.count(Video.id).label('total_videos'),
            func.sum(Video.file_size).label('total_size'),
            func.sum(Video.duration).label('total_duration'),
            func.avg(Video.file_size).label('avg_file_size')
        ).where(
            and_(
                Video.user_id == user_id,
                Video.deleted_at.is_(None)
            )
        )
        
        # Query for videos this month
        month_query = select(func.count(Video.id)).where(
            and_(
                Video.user_id == user_id,
                Video.deleted_at.is_(None),
                Video.created_at >= month_start
            )
        )
        
        # Execute queries
        stats_result = await self.db.execute(stats_query)
        month_result = await self.db.execute(month_query)
        
        stats = stats_result.first()
        videos_this_month = month_result.scalar()
        
        return {
            "total_videos": stats.total_videos or 0,
            "total_size_mb": round((stats.total_size or 0) / (1024 * 1024), 2),
            "total_duration_hours": round(float(stats.total_duration or 0) / 3600, 2) if stats.total_duration else None,
            "videos_this_month": videos_this_month or 0,
            "average_file_size_mb": round((stats.avg_file_size or 0) / (1024 * 1024), 2) if stats.avg_file_size else None
        }
    
    async def check_s3_key_exists(self, s3_key: str, user_id: UUID) -> bool:
        """
        Check if S3 key already exists for user.
        
        Args:
            s3_key: S3 object key
            user_id: User ID
            
        Returns:
            True if exists, False otherwise
        """
        query = select(func.count(Video.id)).where(
            and_(
                Video.s3_key == s3_key,
                Video.user_id == user_id,
                Video.deleted_at.is_(None)
            )
        )
        
        result = await self.db.execute(query)
        count = result.scalar()
        return count > 0 