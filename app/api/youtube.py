"""
YouTube API endpoints
"""

from typing import Dict, Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Response, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.schemas.upload import SupportedVoices
from app.schemas.job import JobCreate, JobResponse
from app.services.job_service import JobService
from app.services.youtube_service import YouTubeService
from app.services.youtube_upload_service import YouTubeUploadService

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


@router.get("/capabilities")
async def get_processing_capabilities() -> Dict[str, Any]:
    """
    Get detailed processing capabilities and system requirements.
    
    Returns:
        Dict with detailed capabilities information
    """
    youtube_service = YouTubeService()
    capabilities = await youtube_service.get_processing_capabilities()
    
    return capabilities


@router.get("/requirements")
async def check_system_requirements() -> Dict[str, Any]:
    """
    Check system requirements and configuration status.
    
    Returns:
        Dict with system requirements status
    """
    youtube_service = YouTubeService()
    requirements = await youtube_service.validate_processing_requirements()
    
    return requirements


@router.get("/setup")
async def get_setup_instructions() -> Dict[str, Any]:
    """
    Get setup instructions for configuring the YouTube processing system.
    
    Returns:
        Dict with setup instructions
    """
    youtube_service = YouTubeService()
    instructions = await youtube_service.get_setup_instructions()
    
    return instructions


@router.get("/voices/detailed")
async def get_detailed_voice_info() -> Dict[str, Any]:
    """
    Get detailed information about available TTS voices.
    
    Returns:
        Dict with detailed voice information
    """
    youtube_service = YouTubeService()
    voice_info = youtube_service.get_voice_info()
    
    return voice_info


@router.get("/guidelines")
async def get_youtube_guidelines() -> Dict[str, Any]:
    """
    Get YouTube upload guidelines and optimization tips.
    
    Returns:
        Dict with YouTube guidelines
    """
    youtube_service = YouTubeService()
    guidelines = await youtube_service.get_youtube_guidelines()
    
    return guidelines


@router.post("/upload-direct")
async def upload_video_to_youtube_direct(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    category: str = Form("entertainment"),
    privacy: str = Form("public"),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Upload a video file directly to YouTube without processing.
    
    This endpoint allows you to upload an already-processed video
    directly to YouTube, bypassing the full processing pipeline.
    
    Args:
        file: Video file to upload
        title: YouTube video title
        description: Video description
        tags: Comma-separated list of tags
        category: Video category
        privacy: Privacy setting (public, unlisted, private)
        current_user: Current authenticated user
        
    Returns:
        Dict with YouTube upload results
        
    Raises:
        HTTPException: If upload fails
    """
    try:
        # Parse tags
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []
        
        # Save uploaded file temporarily
        import tempfile
        import aiofiles
        
        temp_file = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                temp_file_path = temp_file.name
            
            # Save uploaded content to temporary file
            async with aiofiles.open(temp_file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            # Initialize YouTube upload service
            youtube_upload_service = YouTubeUploadService()
            
            # Upload to YouTube
            upload_result = await youtube_upload_service.upload_video_to_youtube(
                video_path=temp_file_path,
                title=title,
                description=description,
                tags=tag_list,
                category=category,
                privacy=privacy
            )
            
            if upload_result["status"] == "error":
                raise Exception(upload_result["error_message"])
            
            # Clean up temporary file
            import os
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            
            return {
                "success": True,
                "message": "Video uploaded to YouTube successfully",
                "youtube_data": upload_result,
                "upload_info": {
                    "original_filename": file.filename,
                    "file_size_mb": len(content) / (1024 * 1024),
                    "title": title,
                    "tags": tag_list,
                    "category": category,
                    "privacy": privacy
                }
            }
            
        except Exception as e:
            # Clean up on error
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise e
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload video to YouTube: {str(e)}"
        )


@router.post("/upload-from-job")
async def upload_processed_video_to_youtube(
    job_id: UUID,
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    category: str = Form("entertainment"),
    privacy: str = Form("public"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Upload a processed video from an existing job to YouTube.
    
    This endpoint takes a completed job and uploads its final video to YouTube
    with custom metadata.
    
    Args:
        job_id: Job UUID with completed processing
        title: YouTube video title
        description: Video description
        tags: Comma-separated list of tags
        category: Video category
        privacy: Privacy setting
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Dict with YouTube upload results
    """
    try:
        # Get job details
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
                detail=f"Job must be completed. Current status: {job.status}"
            )
        
        if not job.final_video_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No final video file found for this job"
            )
        
        import os
        if not os.path.exists(job.final_video_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Final video file no longer exists on server"
            )
        
        # Parse tags
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []
        
        # Upload to YouTube
        youtube_upload_service = YouTubeUploadService()
        upload_result = await youtube_upload_service.upload_video_to_youtube(
            video_path=job.final_video_path,
            title=title,
            description=description,
            tags=tag_list,
            category=category,
            privacy=privacy
        )
        
        if upload_result["status"] == "error":
            raise Exception(upload_result["error_message"])
        
        # Update job with YouTube info
        await job_service.update_job_progress(
            job_id=job_id,
            progress=100,
            message="Video uploaded to YouTube via direct upload",
            status="completed"
        )
        
        # Update job with YouTube URLs
        job.youtube_url = upload_result["video_url"]
        job.youtube_video_id = upload_result["video_id"]
        await db.commit()
        
        return {
            "success": True,
            "message": "Processed video uploaded to YouTube successfully", 
            "job_id": str(job_id),
            "youtube_data": upload_result,
            "upload_info": {
                "original_job_title": job.title,
                "new_title": title,
                "tags": tag_list,
                "category": category,
                "privacy": privacy
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload video to YouTube: {str(e)}"
        ) 