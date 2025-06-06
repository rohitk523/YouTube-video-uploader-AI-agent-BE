"""
YouTube API endpoints
"""

from typing import Dict, Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.schemas.upload import SupportedVoices
from app.schemas.job import JobCreate, JobResponse
from app.services.job_service import JobService
from app.services.youtube_service import YouTubeService

router = APIRouter()


@router.get("/voices", response_model=SupportedVoices)
async def get_supported_voices() -> SupportedVoices:
    """
    Get list of supported TTS voices.
    
    Returns:
        SupportedVoices: List of supported voice names
    """
    youtube_service = YouTubeService()
    voices = youtube_service.get_supported_voices()
    
    return SupportedVoices(
        voices=voices,
        default_voice="alloy"
    )


@router.get("/download/{job_id}")
async def download_video(
    job_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> FileResponse:
    """
    Download the final processed video file.
    
    Args:
        job_id: Job UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        FileResponse: Video file download
        
    Raises:
        HTTPException: If job not found or video not ready
    """
    job_service = JobService(db)
    job = await job_service.get_job_by_id(job_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job not completed. Current status: {job.status}"
        )
    
    if not job.final_video_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Final video file not found"
        )
    
    import os
    if not os.path.exists(job.final_video_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file no longer exists on server"
        )
    
    # Generate download filename
    safe_title = "".join(c for c in job.title if c.isalnum() or c in " -_").strip()
    download_filename = f"{safe_title}_youtube_short.mp4"
    
    return FileResponse(
        path=job.final_video_path,
        filename=download_filename,
        media_type="video/mp4"
    )


@router.get("/info")
async def get_youtube_info() -> Dict[str, Any]:
    """
    Get YouTube processing information and capabilities.
    
    Returns:
        Dict with YouTube service information
    """
    youtube_service = YouTubeService()
    
    return {
        "service": "YouTube Shorts Creator",
        "capabilities": {
            "video_processing": True,
            "tts_generation": True,
            "youtube_upload": True,
            "supported_formats": ["mp4", "mov", "avi", "mkv"],
            "max_duration": 60,  # seconds
            "output_format": "mp4",
            "output_resolution": "1080x1920"
        },
        "supported_voices": youtube_service.get_supported_voices(),
        "processing_steps": [
            "Video processing and formatting",
            "Text-to-speech audio generation", 
            "Audio and video combination",
            "YouTube upload and publishing"
        ],
        "estimated_processing_time": "2-5 minutes per video"
    } 