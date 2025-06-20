"""
Video API endpoints for S3 video management
"""

import math
from typing import Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.repositories.video_repository import VideoRepository
from app.schemas.video import (
    VideoListResponse, 
    VideoResponse, 
    RecentVideosResponse,
    VideoStats,
    VideoUpdate,
    VideoCreate
)

router = APIRouter()


@router.get("/s3-videos", response_model=VideoListResponse)
async def get_s3_videos(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page"),
    search: str = Query(None, description="Search in filename"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> VideoListResponse:
    """
    Get paginated list of user's S3 videos.
    
    Args:
        page: Page number (1-based)
        page_size: Number of items per page (max 50)
        search: Optional search term for filename
        sort_by: Field to sort by (default: created_at)
        sort_order: Sort order (asc/desc, default: desc)
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Paginated list of videos with metadata
        
    Raises:
        HTTPException: If error occurs during retrieval
    """
    try:
        video_repo = VideoRepository(db)
        
        # Validate sort_by field
        valid_sort_fields = ["created_at", "filename", "file_size", "duration"]
        if sort_by not in valid_sort_fields:
            sort_by = "created_at"
        
        videos, total_count = await video_repo.get_user_videos_paginated(
            user_id=current_user.id,
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
        has_more = page < total_pages
        
        return VideoListResponse(
            videos=[VideoResponse.model_validate(video) for video in videos],
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_more=has_more
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching videos: {str(e)}"
        )


@router.get("/s3-videos/recent", response_model=RecentVideosResponse)
async def get_recent_videos(
    limit: int = Query(5, ge=1, le=20, description="Number of recent videos"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> RecentVideosResponse:
    """
    Get recent videos for quick selection.
    
    Args:
        limit: Number of recent videos to return (max 20)
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        List of recent videos
        
    Raises:
        HTTPException: If error occurs during retrieval
    """
    try:
        video_repo = VideoRepository(db)
        
        videos = await video_repo.get_recent_videos(
            user_id=current_user.id,
            limit=limit
        )
        
        return RecentVideosResponse(
            videos=[VideoResponse.model_validate(video) for video in videos]
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching recent videos: {str(e)}"
        )


@router.get("/s3-videos/by-key/{s3_key:path}", response_model=VideoResponse)
async def get_video_by_s3_key(
    s3_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> VideoResponse:
    """
    Get video by S3 key.
    
    Args:
        s3_key: S3 object key (path parameter)
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Video details
        
    Raises:
        HTTPException: If video not found or access denied
    """
    try:
        video_repo = VideoRepository(db)
        
        video = await video_repo.get_by_s3_key(
            s3_key=s3_key,
            user_id=current_user.id
        )
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        return VideoResponse.model_validate(video)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching video: {str(e)}"
        )


@router.get("/s3-videos/{video_id}", response_model=VideoResponse)
async def get_video_by_id(
    video_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> VideoResponse:
    """
    Get video by ID.
    
    Args:
        video_id: Video UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Video details
        
    Raises:
        HTTPException: If video not found or access denied
    """
    try:
        video_repo = VideoRepository(db)
        
        video = await video_repo.get_by_id(
            video_id=video_id,
            user_id=current_user.id
        )
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        return VideoResponse.model_validate(video)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching video: {str(e)}"
        )


@router.patch("/s3-videos/{video_id}", response_model=VideoResponse)
async def update_video_metadata(
    video_id: UUID,
    update_data: VideoUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> VideoResponse:
    """
    Update video metadata.
    
    Args:
        video_id: Video UUID
        update_data: Update data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Updated video details
        
    Raises:
        HTTPException: If video not found or update fails
    """
    try:
        video_repo = VideoRepository(db)
        
        # Check if video exists and belongs to user
        existing_video = await video_repo.get_by_id(
            video_id=video_id,
            user_id=current_user.id
        )
        
        if not existing_video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        # Update video
        updated_video = await video_repo.update_video(
            video_id=video_id,
            user_id=current_user.id,
            update_data=update_data
        )
        
        if not updated_video:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update video"
            )
        
        return VideoResponse.model_validate(updated_video)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating video: {str(e)}"
        )


@router.delete("/s3-videos/{video_id}")
async def delete_video(
    video_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Soft delete video (mark as deleted).
    
    Args:
        video_id: Video UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If video not found or deletion fails
    """
    try:
        video_repo = VideoRepository(db)
        
        # Check if video exists and belongs to user
        existing_video = await video_repo.get_by_id(
            video_id=video_id,
            user_id=current_user.id
        )
        
        if not existing_video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        # Soft delete video
        success = await video_repo.soft_delete_video(
            video_id=video_id,
            user_id=current_user.id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete video"
            )
        
        return {"message": "Video deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting video: {str(e)}"
        )


@router.get("/s3-videos/stats/overview", response_model=VideoStats)
async def get_video_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> VideoStats:
    """
    Get video statistics overview for current user.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Video statistics
        
    Raises:
        HTTPException: If error occurs during retrieval
    """
    try:
        video_repo = VideoRepository(db)
        
        stats = await video_repo.get_video_stats(current_user.id)
        
        return VideoStats(**stats)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching video stats: {str(e)}"
        )


@router.post("/s3-videos/sync")
async def sync_s3_videos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Sync S3 video files with the database.
    
    This endpoint scans the S3 bucket for video files and creates
    database records for any videos that exist in S3 but aren't
    tracked in the videos table.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Sync results with counts of processed files
        
    Raises:
        HTTPException: If sync fails
    """
    try:
        from app.services.s3_service import S3Service
        
        s3_service = S3Service()
        video_repo = VideoRepository(db)
        
        sync_results = {
            "total_s3_files": 0,
            "video_files_found": 0,
            "already_tracked": 0,
            "newly_created": 0,
            "errors": 0,
            "created_videos": []
        }
        
        # List all objects in S3 bucket
        try:
            s3_objects = await s3_service.list_objects()
            sync_results["total_s3_files"] = len(s3_objects)
            
            for s3_object in s3_objects:
                s3_key = s3_object.get("Key", "")
                
                # Check if it's a video file (by extension)
                video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
                if not any(s3_key.lower().endswith(ext) for ext in video_extensions):
                    continue
                
                sync_results["video_files_found"] += 1
                
                # Check if this video is already tracked in the database
                existing_video = await video_repo.check_s3_key_exists(s3_key, current_user.id)
                if existing_video:
                    sync_results["already_tracked"] += 1
                    continue
                
                try:
                    # Get additional metadata from S3
                    file_metadata = s3_service.get_object_metadata(s3_key)
                    
                    # Extract filename from S3 key
                    filename = s3_key.split('/')[-1] if '/' in s3_key else s3_key
                    
                    # Generate S3 URL
                    s3_url = s3_service.generate_presigned_url_sync(s3_key, expiration=3600)
                    
                    # Create video record
                    video_data = VideoCreate(
                        filename=filename,
                        original_filename=filename,
                        s3_key=s3_key,
                        s3_url=s3_url,
                        s3_bucket=s3_service.bucket_name,
                        content_type=file_metadata.get("ContentType", "video/mp4"),
                        file_size=file_metadata.get("ContentLength", 0),
                        user_id=current_user.id
                    )
                    
                    created_video = await video_repo.create_video(video_data)
                    sync_results["newly_created"] += 1
                    sync_results["created_videos"].append({
                        "id": str(created_video.id),
                        "filename": created_video.filename,
                        "s3_key": created_video.s3_key
                    })
                    
                except Exception as video_error:
                    sync_results["errors"] += 1
                    print(f"Error creating video record for {s3_key}: {str(video_error)}")
                    
        except Exception as s3_error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error accessing S3: {str(s3_error)}"
            )
        
        return {
            "message": "S3 sync completed",
            "results": sync_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during S3 sync: {str(e)}"
        )


@router.post("/s3-videos/{video_id}/create-upload-record")
async def create_upload_record_for_video(
    video_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create an upload record for an existing video to make it compatible with job system.
    
    This is a workaround for videos that were synced from S3 but don't have
    corresponding upload records.
    
    Args:
        video_id: Video UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Upload record information
        
    Raises:
        HTTPException: If video not found or upload record creation fails
    """
    try:
        from app.models.upload import Upload
        from app.schemas.upload import UploadResponse
        from uuid import uuid4
        
        video_repo = VideoRepository(db)
        
        # Get the video
        video = await video_repo.get_by_id(video_id, current_user.id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        # Check if upload record already exists for this video
        from sqlalchemy import select
        existing_upload_result = await db.execute(
            select(Upload).where(Upload.s3_key == video.s3_key)
        )
        existing_upload = existing_upload_result.scalar_one_or_none()
        
        if existing_upload:
            return {
                "message": "Upload record already exists",
                "upload_id": str(existing_upload.id),
                "video_id": str(video_id)
            }
        
        # Create upload record for the video
        upload = Upload(
            id=uuid4(),
            filename=video.filename,
            original_filename=video.original_filename,
            file_type="video",
            file_size_bytes=video.file_size,
            s3_key=video.s3_key,
            s3_url=video.s3_url,
            s3_bucket=video.s3_bucket,
            is_temp=False,
            is_active=True
        )
        
        db.add(upload)
        await db.commit()
        await db.refresh(upload)
        
        return {
            "message": "Upload record created successfully",
            "upload_id": str(upload.id),
            "video_id": str(video_id),
            "s3_key": video.s3_key
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating upload record: {str(e)}"
        )


@router.get("/youtube-videos", response_model=Dict[str, Any])
async def get_youtube_videos(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=50, description="Items per page"),
    next_page_token: str = Query(None, description="YouTube API next page token"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get paginated list of user's YouTube videos with S3 sync status.
    
    Args:
        page: Page number (1-based)
        page_size: Number of items per page (max 50)
        next_page_token: YouTube API pagination token
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Paginated list of YouTube videos with S3 status
        
    Raises:
        HTTPException: If error occurs during retrieval
    """
    try:
        from app.services.youtube_video_service import YouTubeVideoService
        
        youtube_service = YouTubeVideoService(db)
        
        # Get YouTube videos from user's channel
        videos_response = await youtube_service.get_user_youtube_videos(
            user_id=current_user.id,
            page_size=page_size,
            page_token=next_page_token
        )
        
        return {
            "videos": videos_response["videos"],
            "total_count": videos_response.get("total_count", len(videos_response["videos"])),
            "page": page,
            "page_size": page_size,
            "has_more": videos_response.get("has_more", False),
            "next_page_token": videos_response.get("next_page_token"),
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching YouTube videos: {str(e)}"
        )


@router.post("/youtube-videos/{video_id}/add-to-s3")
async def add_youtube_video_to_s3(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Download a YouTube video and add it to S3 storage.
    
    Args:
        video_id: YouTube video ID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Information about the S3 upload
        
    Raises:
        HTTPException: If download or upload fails
    """
    try:
        from app.services.youtube_video_service import YouTubeVideoService
        
        youtube_service = YouTubeVideoService(db)
        
        # Download video from YouTube and upload to S3
        result = await youtube_service.download_and_upload_to_s3(
            youtube_video_id=video_id,
            user_id=current_user.id
        )
        
        return {
            "success": True,
            "message": f"Video '{result['title']}' successfully added to S3",
            "s3_video_id": result["s3_video_id"],
            "s3_key": result["s3_key"],
            "download_url": result.get("download_url"),
            "processing_info": {
                "file_size_mb": result.get("file_size_mb"),
                "duration": result.get("duration"),
                "resolution": result.get("resolution"),
                "format": result.get("format")
            }
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding YouTube video to S3: {str(e)}"
        )


@router.post("/youtube-videos/sync-all-to-s3")
async def sync_all_youtube_videos_to_s3(
    max_videos: int = Query(50, ge=1, le=100, description="Maximum number of videos to sync"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Sync all YouTube videos to S3 storage (batch operation).
    
    Args:
        max_videos: Maximum number of videos to sync in this batch
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Summary of sync operation
        
    Raises:
        HTTPException: If sync operation fails
    """
    try:
        from app.services.youtube_video_service import YouTubeVideoService
        
        youtube_service = YouTubeVideoService(db)
        
        # Start background sync operation
        result = await youtube_service.sync_all_videos_to_s3(
            user_id=current_user.id,
            max_videos=max_videos
        )
        
        return {
            "success": True,
            "message": "Sync operation completed",
            "sync_id": result["sync_id"],
            "summary": {
                "total_videos_found": result["total_videos_found"],
                "videos_already_in_s3": result["videos_already_in_s3"],
                "videos_synced": result["videos_synced"],
                "errors": result["errors"],
                "processing_time_seconds": result["processing_time_seconds"]
            },
            "synced_videos": result["synced_videos"]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error syncing YouTube videos: {str(e)}"
        )


@router.get("/sync-status/{sync_id}")
async def get_sync_status(
    sync_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get the status of a sync operation.
    
    Args:
        sync_id: Sync operation ID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Sync operation status and progress
        
    Raises:
        HTTPException: If sync ID not found
    """
    try:
        from app.services.youtube_video_service import YouTubeVideoService
        
        youtube_service = YouTubeVideoService(db)
        
        status = await youtube_service.get_sync_status(sync_id)
        
        if not status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sync operation not found"
            )
            
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting sync status: {str(e)}"
        ) 