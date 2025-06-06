"""
Job service for managing YouTube short creation jobs
"""

import asyncio
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.job import Job
from app.models.upload import Upload
from app.schemas.job import JobCreate, JobResponse, JobStatus, JobList

settings = get_settings()


class JobService:
    """Service for job management operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_job(self, job_data: JobCreate) -> JobResponse:
        """
        Create a new YouTube short creation job.
        
        Args:
            job_data: Job creation data
            
        Returns:
            JobResponse: Created job information
        """
        # Verify video file exists
        video_upload = await self._get_upload_by_id(job_data.video_file_id)
        if not video_upload or video_upload.file_type != "video":
            raise ValueError("Invalid video file ID")
        
        # Create job
        job = Job(
            title=job_data.title,
            description=job_data.description,
            voice=job_data.voice,
            tags=job_data.tags,
            transcript_content=job_data.transcript_content,
            original_video_path=video_upload.file_path,
            status="pending",
            progress=0
        )
        
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        
        # Update upload with job ID
        video_upload.job_id = job.id
        await self.db.commit()
        
        return JobResponse.model_validate(job)
    
    async def get_job_by_id(self, job_id: UUID) -> Optional[JobResponse]:
        """
        Get job by ID.
        
        Args:
            job_id: Job UUID
            
        Returns:
            JobResponse or None if not found
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
        Get job status.
        
        Args:
            job_id: Job UUID
            
        Returns:
            JobStatus or None if not found
        """
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return None
        
        # Determine current step based on progress
        current_step = self._get_current_step(job.progress, job.status)
        
        return JobStatus(
            id=job.id,
            status=job.status,
            progress=job.progress,
            current_step=current_step,
            error_message=job.error_message,
            youtube_url=job.youtube_url
        )
    
    async def list_jobs(
        self, 
        page: int = 1, 
        per_page: int = 20,
        status_filter: Optional[str] = None
    ) -> JobList:
        """
        List jobs with pagination.
        
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
        job.updated_at = datetime.utcnow()
        
        # Update status if provided
        if status:
            job.status = status
            
            # Set completion time for finished jobs
            if status in ["completed", "failed"]:
                job.completed_at = datetime.utcnow()
                
                # Calculate processing time
                if job.created_at:
                    processing_time = job.completed_at - job.created_at
                    job.processing_time_seconds = int(processing_time.total_seconds())
        
        # Handle error status
        if progress == -1:
            job.status = "failed"
            job.error_message = message
            job.completed_at = datetime.utcnow()
        
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
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        
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
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return False
        
        # Delete associated uploads
        uploads_result = await self.db.execute(
            select(Upload).where(Upload.job_id == job_id)
        )
        uploads = uploads_result.scalars().all()
        
        for upload in uploads:
            upload.is_active = False
        
        # Delete job
        await self.db.delete(job)
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
            select(Upload).where(Upload.id == upload_id, Upload.is_active == True)
        )
        return result.scalar_one_or_none() 