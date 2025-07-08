"""
Jobs API endpoints
"""

import logging
from typing import Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.job import JobCreate, JobResponse, JobStatus, JobList
from app.services.job_service import JobService
from app.services.youtube_service import YouTubeService
from app.services.file_service import FileService
from app.services.secret_service import SecretService

# Configure logger for jobs API
logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/create", response_model=JobResponse)
async def create_job(
    job_data: JobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
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
    logger.info(f"Starting job creation for user {current_user.id}")
    logger.debug(f"Job data received: title='{job_data.title}', mock_mode={job_data.mock_mode}, "
                f"has_transcript_content={bool(job_data.transcript_content)}, "
                f"transcript_upload_id={job_data.transcript_upload_id}, "
                f"video_upload_id={job_data.video_upload_id}")
    
    job_service = JobService(db)
    
    try:
        logger.info("Initializing JobService for job creation")
        
        # Validate job data before creation
        logger.debug("Validating job creation data")
        if not job_data.title or not job_data.title.strip():
            logger.warning("Job creation failed: Missing or empty title")
            raise ValueError("Job title is required and cannot be empty")
        
        if not job_data.video_upload_id:
            logger.warning("Job creation failed: Missing video upload ID")
            raise ValueError("Video upload ID is required")
        
        if not job_data.transcript_content and not job_data.transcript_upload_id:
            logger.warning("Job creation failed: Neither transcript content nor transcript upload ID provided")
            raise ValueError("Either transcript content or transcript upload ID is required")
        
        logger.info("Job data validation passed")
        
        # Create job in database
        logger.info("Creating job record in database")
        job_response = await job_service.create_job(job_data)
        logger.info(f"Job created successfully with ID: {job_response.id}")
        
        # Start background processing
        logger.info(f"Starting background processing for job {job_response.id}")
        background_tasks.add_task(
            process_youtube_short_background,
            job_response.id,
            job_data,
            current_user.id  # Pass the user ID to the background task
        )
        logger.info(f"Background task scheduled for job {job_response.id}")
        
        logger.info(f"Job creation completed successfully for user {current_user.id}, job_id: {job_response.id}")
        return job_response
        
    except ValueError as e:
        logger.warning(f"Job creation validation error for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during job creation for user {current_user.id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create job: {str(e)}"
        )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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


async def process_youtube_short_background(job_id: UUID, job_data: JobCreate, user_id: UUID):
    """
    Background task to process YouTube short creation.
    
    Args:
        job_id: Job UUID
        job_data: Job creation data
        user_id: User UUID for credential lookup
    """
    logger.info(f"Starting background processing for job {job_id}")
    
    from app.database import AsyncSessionLocal
    
    async with AsyncSessionLocal() as db:
        job_service = JobService(db)
        
        try:
            logger.info(f"Job {job_id}: Updating status to processing")
            # Update job status to processing
            await job_service.update_job_progress(
                job_id, 0, "Starting processing...", "processing"
            )
            
            # Create progress callback
            async def progress_callback(jid: UUID, progress: int, message: str):
                logger.debug(f"Job {jid}: Progress {progress}% - {message}")
                await job_service.update_job_progress(jid, progress, message)
            
            # Get job details for processing
            logger.info(f"Job {job_id}: Fetching job details from database")
            job = await job_service.get_job_by_id(job_id)
            if not job:
                logger.error(f"Job {job_id}: Job not found in database")
                raise Exception("Job not found")
            
            logger.info(f"Job {job_id}: Job details retrieved - title: '{job.title}'")
            
            # Fetch user credentials from secrets table using the passed user_id
            logger.info(f"Job {job_id}: Fetching user credentials from secrets table for user {user_id}")
            secret_service = SecretService(db)
            credentials_dict = await secret_service.get_decrypted_credentials(user_id)
            if not credentials_dict:
                logger.error(f"Job {job_id}: No YouTube OAuth credentials found for user {user_id}")
                raise Exception("No active YouTube OAuth credentials found for user. Please upload and verify your client_secret.json.")
            
            logger.info(f"Job {job_id}: YouTube credentials retrieved successfully")
            
            # Initialize YouTube service with progress callback and credentials
            logger.info(f"Job {job_id}: Initializing YouTube service")
            youtube_service = YouTubeService(progress_callback=progress_callback, credentials_dict=credentials_dict)
            
            # Get video S3 URL for processing
            logger.info(f"Job {job_id}: Retrieving video S3 URL")
            video_s3_url = await job_service.get_video_s3_url(job_id)
            if not video_s3_url:
                logger.error(f"Job {job_id}: Video file not found or not accessible")
                raise Exception("Video file not found or not accessible")
            
            logger.info(f"Job {job_id}: Video S3 URL retrieved successfully")
            
            # Get transcript content
            logger.info(f"Job {job_id}: Processing transcript content")
            transcript_content = job_data.transcript_content
            if not transcript_content and job.transcript_upload_id:
                logger.info(f"Job {job_id}: Downloading transcript from S3 (upload_id: {job.transcript_upload_id})")
                # Download transcript from S3
                try:
                    file_service = FileService(db)
                    
                    # Get the upload record to get S3 details
                    upload = await file_service.get_upload_by_id(job.transcript_upload_id)
                    if upload and upload.s3_key:
                        logger.debug(f"Job {job_id}: Downloading transcript from S3 key: {upload.s3_key}")
                        # Download transcript content from S3
                        transcript_bytes = await file_service.s3_service.download_file(upload.s3_key)
                        transcript_content = transcript_bytes.decode('utf-8').strip()
                        
                        if not transcript_content:
                            logger.error(f"Job {job_id}: Downloaded transcript file is empty")
                            raise Exception("Downloaded transcript file is empty")
                        
                        logger.info(f"Job {job_id}: Transcript downloaded successfully from S3")
                            
                    else:
                        logger.error(f"Job {job_id}: Transcript upload record not found or invalid (upload_id: {job.transcript_upload_id})")
                        raise Exception("Transcript upload not found or invalid")
                    
                except Exception as e:
                    logger.error(f"Job {job_id}: Failed to download transcript from S3: {str(e)}", exc_info=True)
                    raise Exception(f"Failed to download transcript from S3: {str(e)}")
            
            # Ensure we have transcript content
            if not transcript_content:
                logger.error(f"Job {job_id}: No transcript content available")
                raise Exception("No transcript content available. Please provide transcript_content or upload a valid transcript file.")
            
            logger.info(f"Job {job_id}: Transcript content ready (length: {len(transcript_content)} characters)")
            
            # Process the YouTube short
            logger.info(f"Job {job_id}: Starting YouTube short creation process")
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
            
            logger.info(f"Job {job_id}: YouTube short creation completed successfully")
            
            # Update job with completion results
            logger.info(f"Job {job_id}: Updating job completion status in database")
            await job_service.update_job_completion(job_id, result)
            
            logger.info(f"Job {job_id}: Background processing completed successfully")
            
        except Exception as e:
            logger.error(f"Job {job_id}: Background processing failed with error: {str(e)}", exc_info=True)
            # Update job with error
            await job_service.update_job_progress(
                job_id, -1, f"Processing failed: {str(e)}", "failed"
            ) 