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
            "mock_mode": True,
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
            "YouTube upload and publishing (or mock mode for download only)"
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


@router.post("/voices/preview")
async def generate_voice_preview(
    voice: str,
    text: str = "Hello! This is how I sound. Perfect for your YouTube Shorts.",
    current_user = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Generate a voice preview for the specified voice.
    
    Args:
        voice: Voice name to preview (alloy, echo, fable, onyx, nova, shimmer)
        text: Optional custom text to preview (default: standard preview text)
        
    Returns:
        Dict with preview audio information and download URL
    """
    try:
        youtube_service = YouTubeService()
        
        # Validate voice
        supported_voices = youtube_service.get_supported_voices()
        if voice not in supported_voices:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported voice: {voice}. Supported voices: {supported_voices}"
            )
        
        # Limit preview text length
        if len(text) > 200:
            text = text[:200] + "..."
        
        # Generate preview audio with caching
        audio_result = await youtube_service.tts_service.generate_voice_preview(
            voice=voice,
            custom_text=text if text != "Hello! This is how I sound. Perfect for your YouTube Shorts." else None,
            use_cache=True
        )
        
        if audio_result["status"] == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate voice preview: {audio_result['error_message']}"
            )
        
        # Get voice information
        voice_info = youtube_service.get_voice_info()
        voice_details = voice_info["voices"].get(voice, {})
        
        return {
            "status": "success",
            "voice": voice,
            "audio_path": audio_result["audio_path"],
            "duration": audio_result["duration"],
            "file_size_bytes": audio_result["file_size_bytes"],
            "voice_info": {
                "name": voice_details.get("name", voice.title()),
                "description": voice_details.get("description", ""),
                "style": voice_details.get("style", ""),
                "recommended_for": voice_details.get("recommended_for", [])
            },
            "preview_text": text,
            "download_url": f"/api/v1/youtube/voices/preview/{voice}/download",
            "expires_in_minutes": 15  # Audio files expire in 15 minutes
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/voices/preview/{voice}/download")
async def download_voice_preview(
    voice: str,
    text: str = "Hello! This is how I sound. Perfect for your YouTube Shorts.",
    current_user = Depends(get_current_user)
) -> FileResponse:
    """
    Download voice preview audio file.
    
    Args:
        voice: Voice name
        text: Preview text (must match the generated preview)
        
    Returns:
        FileResponse with the audio file
    """
    try:
        youtube_service = YouTubeService()
        
        # Generate the same preview audio with caching
        audio_result = await youtube_service.tts_service.generate_voice_preview(
            voice=voice,
            custom_text=text if text != "Hello! This is how I sound. Perfect for your YouTube Shorts." else None,
            use_cache=True
        )
        
        if audio_result["status"] == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate preview audio"
            )
        
        audio_path = audio_result["audio_path"]
        
        # Return file with proper headers for audio playback
        return FileResponse(
            path=audio_path,
            media_type="audio/mpeg",
            filename=f"voice_preview_{voice}.mp3",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download preview: {str(e)}"
        )


@router.post("/voices/preview/custom")
async def generate_custom_voice_preview(
    voice: str,
    custom_text: str,
    current_user = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Generate voice preview with custom text from user's transcript.
    
    Args:
        voice: Voice name to preview
        custom_text: User's actual transcript text (first 100 characters)
        
    Returns:
        Dict with preview information
    """
    try:
        # Limit and clean the custom text
        preview_text = custom_text.strip()[:100]
        if len(preview_text) < 10:
            preview_text = "Hello! This is how I sound with your content."
        
        # Add ellipsis if truncated
        if len(custom_text) > 100:
            preview_text += "..."
        
        # Generate preview
        return await generate_voice_preview(voice, preview_text, current_user)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate custom preview: {str(e)}"
        )


@router.delete("/voices/preview/cache")
async def cleanup_voice_preview_cache(
    max_age_hours: int = 48,
    current_user = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Clean up old voice preview cache files.
    
    Args:
        max_age_hours: Maximum age for cache files in hours (default: 48)
        
    Returns:
        Dict with cleanup results
    """
    try:
        youtube_service = YouTubeService()
        
        # Cleanup cache
        cleanup_result = await youtube_service.tts_service.cleanup_cache(max_age_hours)
        
        return {
            "status": "success",
            "message": f"Cache cleanup completed",
            "cleanup_result": cleanup_result
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup cache: {str(e)}"
        )


@router.get("/voices/preview/cache/info")
async def get_voice_preview_cache_info(
    current_user = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get information about voice preview cache.
    
    Returns:
        Dict with cache information
    """
    try:
        youtube_service = YouTubeService()
        cache_dir = youtube_service.tts_service.cache_dir
        
        if not cache_dir.exists():
            return {
                "status": "success",
                "cache_exists": False,
                "message": "No cache directory found"
            }
        
        # Calculate cache statistics
        cache_files = list(cache_dir.glob("*.mp3"))
        total_files = len(cache_files)
        total_size = sum(f.stat().st_size for f in cache_files if f.exists())
        
        # Get oldest and newest files
        if cache_files:
            file_ages = [(f, f.stat().st_mtime) for f in cache_files if f.exists()]
            file_ages.sort(key=lambda x: x[1])
            
            import time
            current_time = time.time()
            oldest_age_hours = (current_time - file_ages[0][1]) / 3600 if file_ages else 0
            newest_age_hours = (current_time - file_ages[-1][1]) / 3600 if file_ages else 0
        else:
            oldest_age_hours = 0
            newest_age_hours = 0
        
        return {
            "status": "success",
            "cache_exists": True,
            "cache_directory": str(cache_dir),
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "oldest_file_age_hours": round(oldest_age_hours, 2),
            "newest_file_age_hours": round(newest_age_hours, 2),
            "recommended_cleanup": oldest_age_hours > 24
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cache info: {str(e)}"
        ) 