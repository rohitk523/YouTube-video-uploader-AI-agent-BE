"""
Job service for managing YouTube Short creation jobs
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.exc import IntegrityError

from app.models.job import Job
from app.models.upload import Upload
from app.schemas.job import JobCreate, JobResponse, JobStatus, JobList


class JobService:
    """Service for managing jobs."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_job(self, job_data: JobCreate) -> JobResponse:
        """
        Create a new job.
        
        Args:
            job_data: Job creation data
            
        Returns:
            JobResponse: Created job information
        """
        # Validate upload if provided
        if job_data.upload_id:
            upload = await self._get_upload_by_id(job_data.upload_id)
            if not upload:
                raise ValueError("Upload not found")
        
        # Create job
        job = Job(
            title=job_data.title,
            description=job_data.description,
            voice=job_data.voice,
            tags=job_data.tags,
            original_video_path=upload.file_path if job_data.upload_id and upload else None,
            transcript_content=job_data.transcript_content
        )
        
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        
        # Update upload with job_id if provided
        if job_data.upload_id and upload:
            upload.job_id = job.id
            await self.db.commit()
        
        return JobResponse.model_validate(job)
    
    async def get_job_by_id(self, job_id: UUID) -> Optional[JobResponse]:
        """
        Get job by ID.
        
        Args:
            job_id: Job UUID
            
        Returns:
            Optional[JobResponse]: Job information if found
        """
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return None
        
        return JobResponse.model_validate(job)
    
    async def get_job_status(self, job_id: UUID) -> Optional[JobStatus]:
        """
        Get job status and progress.
        
        Args:
            job_id: Job UUID
            
        Returns:
            Optional[JobStatus]: Job status if found
        """
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return None
        
        return JobStatus(
            id=job.id,
            status=job.status,
            progress=job.progress,
            current_step=self._get_current_step(job.progress, job.status),
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at
        )
    
    async def list_jobs(
        self, 
        page: int = 1, 
        per_page: int = 20,
        status_filter: Optional[str] = None
    ) -> JobList:
        """
        List jobs with pagination and filtering.
        
        Args:
            page: Page number (1-based)
            per_page: Items per page
            status_filter: Optional status filter
            
        Returns:
            JobList: Paginated job list
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
        
        # Apply pagination
        offset = (page - 1) * per_page
        query = query.limit(per_page).offset(offset)
        
        result = await self.db.execute(query)
        jobs = result.scalars().all()
        
        # Calculate pagination info
        total_pages = (total + per_page - 1) // per_page
        
        return JobList(
            jobs=[JobResponse.model_validate(job) for job in jobs],
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )
    
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
    
    async def delete_job(self, job_id: UUID) -> bool:
        """
        Delete job and associated files.
        
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
            
            # Delete associated uploads by setting job_id to NULL first
            uploads_result = await self.db.execute(
                select(Upload).where(Upload.job_id == job_id)
            )
            uploads = uploads_result.scalars().all()
            
            for upload in uploads:
                upload.job_id = None  # Remove foreign key reference
                upload.is_active = False  # Mark as inactive
            
            # Now delete the job
            await self.db.delete(job)
            await self.db.commit()
            
            return True
            
        except IntegrityError:
            await self.db.rollback()
            return False
        except Exception:
            await self.db.rollback()
            return False
    
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
            select(Upload).where(Upload.id == upload_id, Upload.is_active == True)
        )
        return result.scalar_one_or_none() 