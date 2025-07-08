"""
Job service for managing YouTube Short creation jobs
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update
from sqlalchemy.exc import IntegrityError

from app.models.job import Job
from app.models.upload import Upload
from app.models.video import Video
from app.schemas.job import JobCreate, JobResponse, JobStatus, JobList


class JobService:
    """Service for managing jobs."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_job(self, job_data: JobCreate) -> JobResponse:
        """
        Create a new job with S3 upload support.
        
        Args:
            job_data: Job creation data
            
        Returns:
            JobResponse: Created job information
            
        Raises:
            ValueError: If required uploads/videos not found
        """
        # Validate video source - either video_upload_id or s3_video_id must be provided
        video_upload = None
        s3_video = None
        
        if job_data.video_upload_id:
            video_upload = await self._get_upload_by_id(job_data.video_upload_id)
            if not video_upload:
                raise ValueError("Video upload not found")
        
        if job_data.s3_video_id:
            s3_video = await self._get_video_by_id(job_data.s3_video_id)
            if not s3_video:
                raise ValueError("S3 video not found")
        
        # Validate transcript upload if provided
        transcript_upload = None
        if job_data.transcript_upload_id:
            transcript_upload = await self._get_upload_by_id(job_data.transcript_upload_id)
            if not transcript_upload:
                raise ValueError("Transcript upload not found")
        
        # Create job with S3 support
        job = Job(
            title=job_data.title,
            description=job_data.description,
            voice=job_data.voice,
            tags=job_data.tags,
            video_upload_id=job_data.video_upload_id,
            s3_video_id=job_data.s3_video_id,
            transcript_upload_id=job_data.transcript_upload_id,
            transcript_content=job_data.transcript_content,
            mock_mode=job_data.mock_mode
        )
        
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        
        # Update uploads with job_id (if applicable)
        if video_upload:
            video_upload.job_id = job.id
        if transcript_upload:
            transcript_upload.job_id = job.id
        
        if video_upload or transcript_upload:
            await self.db.commit()
        
        return JobResponse.model_validate(job)
    
    async def get_job_by_id(self, job_id: UUID) -> Optional[Job]:
        """
        Get job by ID.
        
        Args:
            job_id: Job UUID
            
        Returns:
            Job model or None if not found
        """
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()
    
    async def get_job_status(self, job_id: UUID) -> Optional[JobStatus]:
        """
        Get job status.
        
        Args:
            job_id: Job UUID
            
        Returns:
            JobStatus or None if not found
        """
        job = await self.get_job_by_id(job_id)
        if not job:
            return None
        
        return JobStatus(
            id=job.id,
            status=job.status,
            progress=job.progress,
            progress_message=job.progress_message,
            current_step=self._get_current_step(job.progress, job.status),
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
            temp_files_cleaned=job.temp_files_cleaned,
            permanent_storage=job.permanent_storage
        )
    
    async def list_jobs(
        self, 
        page: int = 1, 
        page_size: int = 20,
        status_filter: Optional[str] = None
    ) -> JobList:
        """
        List jobs with pagination.
        
        Args:
            page: Page number (1-based)
            page_size: Items per page
            status_filter: Optional status filter
            
        Returns:
            JobList with pagination info
        """
        # Build query
        query = select(Job).order_by(desc(Job.created_at))
        
        if status_filter:
            query = query.where(Job.status == status_filter)
        
        # Get total count
        count_query = select(func.count(Job.id))
        if status_filter:
            count_query = count_query.where(Job.status == status_filter)
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Get paginated results
        offset = (page - 1) * page_size
        paginated_query = query.offset(offset).limit(page_size)
        
        result = await self.db.execute(paginated_query)
        jobs = result.scalars().all()
        
        # Calculate pagination info
        total_pages = (total + page_size - 1) // page_size
        
        return JobList(
            jobs=[JobResponse.model_validate(job) for job in jobs],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    
    async def delete_job(self, job_id: UUID) -> bool:
        """
        Delete a job and handle related data properly.
        
        Args:
            job_id: Job UUID
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            # Get the job first
            result = await self.db.execute(
                select(Job).where(Job.id == job_id)
            )
            job = result.scalar_one_or_none()
            
            if not job:
                return False
            
            # Handle related uploads - set job_id to NULL instead of deleting the uploads
            # This preserves the upload records in case they're referenced elsewhere
            from app.models.upload import Upload
            await self.db.execute(
                update(Upload).where(Upload.job_id == job_id).values(job_id=None)
            )
            
            # Now delete the job
            await self.db.delete(job)
            await self.db.commit()
            return True
            
        except Exception as e:
            await self.db.rollback()
            raise e
    
    async def update_job_progress(
        self, 
        job_id: UUID, 
        progress: int, 
        message: str,
        status: Optional[str] = None
    ) -> bool:
        """
        Update job progress.
        
        Args:
            job_id: Job UUID
            progress: Progress percentage (0-100)
            message: Progress message
            status: Optional status update
            
        Returns:
            bool: True if updated successfully
        """
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return False
        
        # Update progress
        job.progress = progress
        job.updated_at = datetime.now(timezone.utc)
        
        # Update status if provided
        if status:
            job.status = status
            
            # Set completion time for finished jobs
            if status in ["completed", "failed"]:
                job.completed_at = datetime.now(timezone.utc)
                
                # Calculate processing time
                if job.created_at:
                    processing_time = job.completed_at - job.created_at
                    job.processing_time_seconds = int(processing_time.total_seconds())
        
        # Handle error status
        if progress == -1:
            job.status = "failed"
            job.error_message = message
            job.completed_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        return True
    
    async def update_job_completion(
        self, 
        job_id: UUID, 
        result_data: dict
    ) -> bool:
        """
        Update job with completion data.
        
        Args:
            job_id: Job UUID
            result_data: Processing result data
            
        Returns:
            bool: True if updated successfully
        """
        job_result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        
        if not job:
            return False
        
        # Update job with results
        job.status = "completed"
        job.progress = 100
        job.youtube_url = result_data.get("youtube_url")
        job.youtube_video_id = result_data.get("youtube_video_id")
        job.final_video_path = result_data.get("final_video_path")
        job.completed_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        
        # Calculate processing time
        if job.created_at:
            processing_time = job.completed_at - job.created_at
            job.processing_time_seconds = int(processing_time.total_seconds())
        
        await self.db.commit()
        return True
    
    async def cleanup_job_files(self, job_id: UUID) -> bool:
        """
        Clean up temporary files for a job.
        
        Args:
            job_id: Job UUID
            
        Returns:
            bool: True if cleanup successful
        """
        job_result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        
        if not job:
            return False
        
        # Mark as cleaned up
        job.temp_files_cleaned = True
        job.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        return True
    
    def _get_current_step(self, progress: int, status: str) -> str:
        """
        Get current processing step based on progress.
        
        Args:
            progress: Progress percentage
            status: Job status
            
        Returns:
            str: Current step description
        """
        if status == "failed":
            return "Failed"
        elif status == "completed":
            return "Completed"
        elif status == "pending":
            return "Waiting to start"
        elif progress < 25:
            return "Processing video"
        elif progress < 50:
            return "Generating audio"
        elif progress < 75:
            return "Combining video and audio"
        elif progress < 100:
            return "Uploading to YouTube"
        else:
            return "Finalizing"
    
    async def _get_upload_by_id(self, upload_id: UUID) -> Optional[Upload]:
        """Get upload by ID."""
        result = await self.db.execute(
            select(Upload).where(Upload.id == upload_id)
        )
        return result.scalar_one_or_none()

    async def _get_video_by_id(self, video_id: UUID) -> Optional[Video]:
        """Get video by ID."""
        result = await self.db.execute(
            select(Video).where(Video.id == video_id, Video.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_video_s3_url(self, job_id: UUID) -> Optional[str]:
        """
        Get video S3 URL for a job - returns S3 key for direct download.
        
        Args:
            job_id: Job UUID
            
        Returns:
            S3 key string (not presigned URL) for direct download, or None if not found
        """
        job = await self.get_job_by_id(job_id)
        if not job:
            return None
        
        # Return S3 key instead of presigned URL to avoid presigned URL issues
        # The video service will handle direct S3 download using boto3
        
        # Check if job uses video upload
        if job.video_upload_id:
            upload = await self._get_upload_by_id(job.video_upload_id)
            if upload and upload.s3_key:
                return f"s3://{upload.s3_bucket}/{upload.s3_key}"
        
        # Check if job uses s3 video
        if job.s3_video_id:
            video = await self._get_video_by_id(job.s3_video_id)
            if video and video.s3_key:
                return f"s3://{video.s3_bucket}/{video.s3_key}"
        
        return None

    async def create_job_with_folder_structure(
        self,
        job_data: JobCreate,
        user_id: UUID
    ) -> JobResponse:
        """
        Create a new job and set up S3 folder structure.
        
        Args:
            job_data: Job creation data
            user_id: User ID for folder organization
            
        Returns:
            JobResponse: Created job information
            
        Raises:
            ValueError: If required uploads/videos not found
        """
        # Create the job first
        job_response = await self.create_job(job_data)
        
        # Set up S3 folder structure for the new job
        try:
            from app.services.s3_service import S3Service
            s3_service = S3Service()
            
            await s3_service.create_job_folder_structure(
                user_id=user_id,
                job_id=job_response.id
            )
            
            return job_response
            
        except Exception as e:
            # If folder creation fails, we should still return the job
            # but log the error for investigation
            print(f"Warning: Failed to create S3 folder structure for job {job_response.id}: {str(e)}")
            return job_response
    
    async def move_temp_files_to_job(
        self,
        job_id: UUID,
        user_id: UUID,
        video_upload_id: Optional[UUID] = None,
        transcript_upload_id: Optional[UUID] = None,
        custom_video_name: Optional[str] = None,
        custom_transcript_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Move temporary files to the job folder structure.
        
        Args:
            job_id: Job ID
            user_id: User ID
            video_upload_id: Video upload ID to move
            transcript_upload_id: Transcript upload ID to move
            custom_video_name: Custom name for video file
            custom_transcript_name: Custom name for transcript file
            
        Returns:
            Dict with move results
        """
        try:
            from app.services.s3_service import S3Service
            s3_service = S3Service()
            
            results = {
                'job_id': str(job_id),
                'user_id': str(user_id),
                'moved_files': [],
                'errors': []
            }
            
            # Move video file if provided
            if video_upload_id:
                try:
                    video_upload = await self._get_upload_by_id(video_upload_id)
                    if video_upload and video_upload.s3_key:
                        move_result = await s3_service.move_temp_to_job_folder(
                            temp_s3_key=video_upload.s3_key,
                            user_id=user_id,
                            job_id=job_id,
                            file_type="video",
                            custom_name=custom_video_name
                        )
                        
                        # Update the upload record with new S3 location
                        video_upload.s3_key = move_result['new_s3_key']
                        video_upload.s3_url = move_result['new_s3_url']
                        video_upload.is_temp = False
                        video_upload.job_id = job_id
                        
                        results['moved_files'].append({
                            'type': 'video',
                            'upload_id': str(video_upload_id),
                            'old_key': move_result['old_s3_key'],
                            'new_key': move_result['new_s3_key']
                        })
                        
                except Exception as video_error:
                    results['errors'].append({
                        'type': 'video',
                        'upload_id': str(video_upload_id),
                        'error': str(video_error)
                    })
            
            # Move transcript file if provided
            if transcript_upload_id:
                try:
                    transcript_upload = await self._get_upload_by_id(transcript_upload_id)
                    if transcript_upload and transcript_upload.s3_key:
                        move_result = await s3_service.move_temp_to_job_folder(
                            temp_s3_key=transcript_upload.s3_key,
                            user_id=user_id,
                            job_id=job_id,
                            file_type="transcript",
                            custom_name=custom_transcript_name
                        )
                        
                        # Update the upload record with new S3 location
                        transcript_upload.s3_key = move_result['new_s3_key']
                        transcript_upload.s3_url = move_result['new_s3_url']
                        transcript_upload.is_temp = False
                        transcript_upload.job_id = job_id
                        
                        results['moved_files'].append({
                            'type': 'transcript',
                            'upload_id': str(transcript_upload_id),
                            'old_key': move_result['old_s3_key'],
                            'new_key': move_result['new_s3_key']
                        })
                        
                except Exception as transcript_error:
                    results['errors'].append({
                        'type': 'transcript',
                        'upload_id': str(transcript_upload_id),
                        'error': str(transcript_error)
                    })
            
            # Commit database changes
            await self.db.commit()
            
            return results
            
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to move temp files to job folder: {str(e)}"
            )
    
    async def get_user_jobs_with_files(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Get user's jobs with their associated files from S3.
        
        Args:
            user_id: User ID to filter jobs
            page: Page number (1-based)
            page_size: Items per page
            
        Returns:
            Dict with jobs and their files
        """
        try:
            from app.services.s3_service import S3Service
            s3_service = S3Service()
            
            # Get paginated jobs list
            jobs_result = await self.list_jobs(page=page, page_size=page_size)
            
            # For each job, get the associated files from S3
            jobs_with_files = []
            for job in jobs_result.jobs:
                try:
                    # Get videos for this job
                    videos = await s3_service.list_user_videos(
                        user_id=user_id,
                        job_id=job.id,
                        limit=10
                    )
                    
                    # Get transcripts for this job (similar pattern)
                    # This could be extended to include transcripts as well
                    
                    job_data = {
                        'job': job,
                        'videos': videos,
                        'video_count': len(videos),
                        'folder_path': f"{user_id}/{job.id}/"
                    }
                    
                    jobs_with_files.append(job_data)
                    
                except Exception as file_error:
                    # Include job even if file listing fails
                    job_data = {
                        'job': job,
                        'videos': [],
                        'video_count': 0,
                        'folder_path': f"{user_id}/{job.id}/",
                        'file_error': str(file_error)
                    }
                    jobs_with_files.append(job_data)
            
            return {
                'jobs': jobs_with_files,
                'total': jobs_result.total,
                'page': jobs_result.page,
                'page_size': jobs_result.page_size,
                'total_pages': jobs_result.total_pages
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get user jobs with files: {str(e)}"
            ) 