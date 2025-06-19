"""
Jobs API endpoints
"""

from typing import Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.schemas.job import JobCreate, JobResponse, JobStatus, JobList
from app.services.job_service import JobService
from app.services.youtube_service import YouTubeService

router = APIRouter()


@router.post("/create", response_model=JobResponse)
async def create_job(
    job_data: JobCreate,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> JobResponse:
    """
    Create a new YouTube short creation job.
    
    Args:
        job_data: Job creation data
        background_tasks: FastAPI background tasks
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        JobResponse: Created job information
        
    Raises:
        HTTPException: If job creation fails
    """
    job_service = JobService(db)
    
    try:
        # Create job in database
        job_response = await job_service.create_job(job_data)
        
        # Start background processing
        background_tasks.add_task(
            process_youtube_short_background,
            job_response.id,
            job_data
        )
        
        return job_response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create job: {str(e)}"
        )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> JobResponse:
    """
    Get job by ID.
    
    Args:
        job_id: Job UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        JobResponse: Job information
        
    Raises:
        HTTPException: If job not found
    """
    job_service = JobService(db)
    job = await job_service.get_job_by_id(job_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    return job


@router.get("/{job_id}/status", response_model=JobStatus)
async def get_job_status(
    job_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> JobStatus:
    """
    Get job status and progress.
    
    Args:
        job_id: Job UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        JobStatus: Job status information
        
    Raises:
        HTTPException: If job not found
    """
    job_service = JobService(db)
    job_status = await job_service.get_job_status(job_id)
    
    if not job_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    return job_status


@router.get("", response_model=JobList)
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> JobList:
    """
    List jobs with pagination and filtering.
    
    Args:
        page: Page number (1-based)
        per_page: Items per page
        status_filter: Optional status filter
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        JobList: Paginated job list
    """
    job_service = JobService(db)
    return await job_service.list_jobs(
        page=page,
        page_size=per_page,
        status_filter=status_filter
    )


@router.delete("/{job_id}")
async def delete_job(
    job_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Delete a job and its associated files.
    
    Args:
        job_id: Job UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Dict with success message
        
    Raises:
        HTTPException: If job not found or deletion fails
    """
    job_service = JobService(db)
    success = await job_service.delete_job(job_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or already deleted"
        )
    
    return {"status": "success", "message": "Job deleted successfully"}


@router.get("/{job_id}/download")
async def download_processed_video(
    job_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Download the processed video from a completed mock mode job.
    
    Args:
        job_id: Job UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Redirect to presigned URL for downloading the processed video
        
    Raises:
        HTTPException: If job not found, not completed, or not in mock mode
    """
    job_service = JobService(db)
    job = await job_service.get_job_by_id(job_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    if not job.mock_mode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Download is only available for mock mode jobs. This job was configured to upload to YouTube."
        )
    
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job must be completed to download video. Current status: {job.status}"
        )
    
    if not job.final_video_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processed video file not found. The file may have been cleaned up or processing failed."
        )
    
    # Check if file exists
    import os
    if not os.path.exists(job.final_video_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processed video file no longer exists on server. The file may have been cleaned up."
        )
    
    try:
        # Generate filename for download
        safe_title = "".join(c for c in job.title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{safe_title}_processed.mp4" if safe_title else f"video_{job_id}_processed.mp4"
        
        return FileResponse(
            path=job.final_video_path,
            media_type="video/mp4",
            filename=filename,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-cache"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download video: {str(e)}"
        )


async def process_youtube_short_background(job_id: UUID, job_data: JobCreate):
    """
    Background task to process YouTube short creation.
    
    Args:
        job_id: Job UUID
        job_data: Job creation data
    """
    from app.database import AsyncSessionLocal
    
    async with AsyncSessionLocal() as db:
        job_service = JobService(db)
        
        try:
            # Update job status to processing
            await job_service.update_job_progress(
                job_id, 0, "Starting processing...", "processing"
            )
            
            # Create progress callback
            async def progress_callback(jid: UUID, progress: int, message: str):
                await job_service.update_job_progress(jid, progress, message)
            
            # Initialize YouTube service with progress callback
            youtube_service = YouTubeService(progress_callback=progress_callback)
            
            # Get job details for processing
            job = await job_service.get_job_by_id(job_id)
            if not job:
                raise Exception("Job not found")
            
            # Get video S3 URL for processing
            video_s3_url = await job_service.get_video_s3_url(job_id)
            if not video_s3_url:
                raise Exception("Video file not found or not accessible")
            
            # Get transcript content
            transcript_content = job_data.transcript_content
            if not transcript_content and job.transcript_upload_id:
                # TODO: Download transcript from S3 if needed
                # For now, use the provided transcript content
                transcript_content = job.transcript_content or "Sample transcript"
            
            # Process the YouTube short
            result = await youtube_service.create_youtube_short_async(
                job_id=job_id,
                video_path=video_s3_url,  # Use S3 URL instead of local path
                transcript=transcript_content,
                title=job_data.title,
                description=job_data.description,
                voice=job_data.voice,
                tags=job_data.tags,
                mock_mode=job_data.mock_mode
            )
            
            # Update job with completion results
            await job_service.update_job_completion(job_id, result)
            
        except Exception as e:
            # Update job with error
            await job_service.update_job_progress(
                job_id, -1, f"Processing failed: {str(e)}", "failed"
            ) 