"""
File service for handling uploads and file management with S3 storage
"""

from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.upload import Upload
from app.schemas.upload import UploadResponse

settings = get_settings()


class FileService:
    """Service for file upload and management operations using S3 storage."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.s3_service = None
        self._init_s3_service()
    
    def _init_s3_service(self):
        """Initialize S3 service with proper error handling."""
        try:
            from app.services.s3_service import S3Service
            self.s3_service = S3Service()
        except ValueError as e:
            # S3 not configured - this will be handled in individual methods
            self.s3_service = None
            print(f"Warning: S3 not configured - {str(e)}")
        except Exception as e:
            # Other S3 initialization errors
            self.s3_service = None
            print(f"Error: Failed to initialize S3 service - {str(e)}")
    
    def _check_s3_available(self) -> None:
        """Check if S3 service is available and raise appropriate error if not."""
        if self.s3_service is None:
            missing_configs = []
            if not settings.aws_access_key_id:
                missing_configs.append("AWS_ACCESS_KEY_ID")
            if not settings.aws_secret_access_key:
                missing_configs.append("AWS_SECRET_ACCESS_KEY")
            if not settings.s3_bucket_name:
                missing_configs.append("S3_BUCKET_NAME")
            
            if missing_configs:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"S3 storage not configured. Missing: {', '.join(missing_configs)}. Please configure AWS credentials and S3 bucket in environment variables."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="S3 storage service unavailable. Please check AWS configuration and credentials."
                )
    
    async def save_uploaded_file(
        self, 
        file: UploadFile, 
        file_type: str,
        job_id: Optional[UUID] = None,
        is_temp: bool = True
    ) -> UploadResponse:
        """
        Save uploaded file to S3 and database.
        
        Args:
            file: Uploaded file
            file_type: Type of file (video/transcript)
            job_id: Optional job ID to associate with upload
            is_temp: Whether this is a temporary file
            
        Returns:
            UploadResponse: Upload information
            
        Raises:
            HTTPException: If file save fails
        """
        # Check S3 availability
        self._check_s3_available()
        
        try:
            # Generate unique upload ID
            upload_id = uuid4()
            
            # Upload file to S3
            s3_result = await self.s3_service.upload_file(
                file=file,
                file_type=file_type,
                upload_id=upload_id,
                is_temp=is_temp
            )
            
            # Create database record
            upload = Upload(
                id=upload_id,
                filename=s3_result['s3_key'].split('/')[-1],  # Extract filename from S3 key
                original_filename=file.filename or "",
                file_type=file_type,
                file_size_bytes=s3_result['file_size_bytes'],
                s3_bucket=s3_result['bucket_name'],
                s3_key=s3_result['s3_key'],
                s3_url=s3_result['s3_url'],
                is_temp=is_temp,
                job_id=job_id
            )
            
            self.db.add(upload)
            await self.db.commit()
            await self.db.refresh(upload)
            
            return UploadResponse(
                id=upload.id,
                filename=upload.filename,
                original_filename=upload.original_filename,
                file_type=upload.file_type,
                file_size_mb=upload.file_size_mb,
                upload_time=upload.upload_time
            )
            
        except HTTPException:
            # Re-raise HTTP exceptions (like S3 service unavailable)
            raise
        except Exception as e:
            # Clean up S3 file if database save failed
            try:
                if 's3_result' in locals() and self.s3_service:
                    await self.s3_service.delete_file(s3_result['s3_key'])
            except:
                pass
            
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {str(e)}"
            )
    
    async def save_transcript_text(
        self,
        content: str,
        upload_id: Optional[UUID] = None,
        job_id: Optional[UUID] = None,
        filename: str = "transcript.txt",
        is_temp: bool = True
    ) -> UploadResponse:
        """
        Save transcript text content to S3 and database.
        
        Args:
            content: Transcript text content
            upload_id: Optional specific upload ID to use
            job_id: Optional job ID to associate with upload
            filename: Name for the transcript file
            is_temp: Whether this is a temporary file
            
        Returns:
            UploadResponse: Upload information
        """
        # Check S3 availability
        self._check_s3_available()
        
        try:
            # Use provided upload_id or generate new one
            if not upload_id:
                upload_id = uuid4()
            
            # Upload transcript to S3
            s3_result = await self.s3_service.upload_transcript_text(
                content=content,
                upload_id=upload_id,
                filename=filename,
                is_temp=is_temp
            )
            
            # Create database record
            upload = Upload(
                id=upload_id,
                filename=s3_result['s3_key'].split('/')[-1],
                original_filename=filename,
                file_type="transcript",
                file_size_bytes=s3_result['file_size_bytes'],
                s3_bucket=s3_result['bucket_name'],
                s3_key=s3_result['s3_key'],
                s3_url=s3_result['s3_url'],
                is_temp=is_temp,
                job_id=job_id
            )
            
            self.db.add(upload)
            await self.db.commit()
            await self.db.refresh(upload)
            
            return UploadResponse(
                id=upload.id,
                filename=upload.filename,
                original_filename=upload.original_filename,
                file_type=upload.file_type,
                file_size_mb=upload.file_size_mb,
                upload_time=upload.upload_time
            )
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            # Clean up S3 file if database save failed
            try:
                if 's3_result' in locals() and self.s3_service:
                    await self.s3_service.delete_file(s3_result['s3_key'])
            except:
                pass
            
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save transcript: {str(e)}"
            )
    
    async def get_upload_by_id(self, upload_id: UUID) -> Optional[Upload]:
        """
        Get upload by ID.
        
        Args:
            upload_id: Upload UUID
            
        Returns:
            Upload or None if not found
        """
        result = await self.db.execute(
            select(Upload).where(Upload.id == upload_id, Upload.is_active == True)
        )
        return result.scalar_one_or_none()
    
    async def get_file_content(self, upload_id: UUID) -> bytes:
        """
        Get file content from S3.
        
        Args:
            upload_id: Upload UUID
            
        Returns:
            File content as bytes
            
        Raises:
            HTTPException: If file not found or download fails
        """
        # Check S3 availability
        self._check_s3_available()
        
        upload = await self.get_upload_by_id(upload_id)
        if not upload:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upload not found"
            )
        
        if not upload.is_s3_stored:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is not stored in S3"
            )
        
        return await self.s3_service.download_file(upload.s3_key)
    
    async def get_presigned_download_url(self, upload_id: UUID, expiration: int = 3600) -> str:
        """
        Generate a presigned URL for downloading a file.
        
        Args:
            upload_id: Upload UUID
            expiration: URL expiration time in seconds
            
        Returns:
            Presigned download URL
            
        Raises:
            HTTPException: If upload not found
        """
        # Check S3 availability
        self._check_s3_available()
        
        upload = await self.get_upload_by_id(upload_id)
        if not upload:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upload not found"
            )
        
        if not upload.is_s3_stored:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is not stored in S3"
            )
        
        return await self.s3_service.generate_presigned_url(
            upload.s3_key,
            expiration=expiration
        )
    
    async def delete_upload(self, upload_id: UUID) -> bool:
        """
        Delete upload and associated S3 file.
        
        Args:
            upload_id: Upload UUID
            
        Returns:
            bool: True if deleted successfully
        """
        upload = await self.get_upload_by_id(upload_id)
        if not upload:
            return False
        
        try:
            # Delete file from S3 if it exists and S3 is available
            if upload.is_s3_stored and self.s3_service:
                await self.s3_service.delete_file(upload.s3_key)
            
            # Mark as inactive in database (soft delete)
            upload.is_active = False
            await self.db.commit()
            
            return True
            
        except Exception:
            await self.db.rollback()
            return False
    
    async def move_temp_to_permanent(self, upload_id: UUID) -> bool:
        """
        Move a temporary file to permanent storage.
        
        Args:
            upload_id: Upload UUID
            
        Returns:
            bool: True if moved successfully
        """
        # Check S3 availability
        self._check_s3_available()
        
        upload = await self.get_upload_by_id(upload_id)
        if not upload or not upload.is_temp or not upload.is_s3_stored:
            return False
        
        try:
            # Generate new S3 key for permanent storage
            new_s3_key = self.s3_service._generate_s3_key(
                upload.original_filename,
                upload.file_type,
                upload.id,
                is_temp=False
            )
            
            # Move file in S3
            success = await self.s3_service.move_file(upload.s3_key, new_s3_key)
            
            if success:
                # Update database record
                upload.s3_key = new_s3_key
                upload.s3_url = f"s3://{upload.s3_bucket}/{new_s3_key}"
                upload.is_temp = False
                upload.filename = new_s3_key.split('/')[-1]
                
                await self.db.commit()
                return True
            
            return False
            
        except Exception:
            await self.db.rollback()
            return False
    
    async def cleanup_temp_files(self, hours: int = None) -> Dict[str, Any]:
        """
        Clean up old temporary files from S3 and database.
        
        Args:
            hours: Files older than this many hours will be deleted
            
        Returns:
            Dict with cleanup statistics
        """
        try:
            # Clean up S3 temp files if S3 is available
            s3_cleanup_result = {}
            if self.s3_service:
                s3_cleanup_result = await self.s3_service.cleanup_temp_files(hours)
            else:
                s3_cleanup_result = {"error": "S3 service not available"}
            
            # Also clean up database records for temp files
            from datetime import datetime, timedelta, timezone
            
            hours = hours or settings.s3_cleanup_temp_hours
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # Get old temp uploads
            result = await self.db.execute(
                select(Upload).where(
                    Upload.is_temp == True,
                    Upload.is_active == False,
                    Upload.upload_time < cutoff_time
                )
            )
            old_uploads = result.scalars().all()
            
            # Delete old upload records
            db_deleted_count = 0
            for upload in old_uploads:
                try:
                    await self.db.delete(upload)
                    db_deleted_count += 1
                except Exception:
                    continue
            
            await self.db.commit()
            
            return {
                "s3_cleanup": s3_cleanup_result,
                "database_records_deleted": db_deleted_count,
                "total_temp_files_processed": s3_cleanup_result.get("total_checked", 0)
            }
            
        except Exception as e:
            await self.db.rollback()
            return {
                "error": f"Cleanup failed: {str(e)}",
                "s3_cleanup": {},
                "database_records_deleted": 0
            }
    
    async def get_upload_stats(self) -> Dict[str, Any]:
        """
        Get upload statistics.
        
        Returns:
            Dict with upload statistics
        """
        try:
            # Count total uploads
            total_result = await self.db.execute(
                select(Upload).where(Upload.is_active == True)
            )
            total_uploads = len(total_result.scalars().all())
            
            # Count by file type
            video_result = await self.db.execute(
                select(Upload).where(
                    Upload.is_active == True,
                    Upload.file_type == "video"
                )
            )
            video_count = len(video_result.scalars().all())
            
            transcript_result = await self.db.execute(
                select(Upload).where(
                    Upload.is_active == True,
                    Upload.file_type == "transcript"
                )
            )
            transcript_count = len(transcript_result.scalars().all())
            
            # Count temporary files
            temp_result = await self.db.execute(
                select(Upload).where(
                    Upload.is_active == True,
                    Upload.is_temp == True
                )
            )
            temp_count = len(temp_result.scalars().all())
            
            return {
                "total_uploads": total_uploads,
                "video_uploads": video_count,
                "transcript_uploads": transcript_count,
                "temporary_files": temp_count,
                "permanent_files": total_uploads - temp_count,
                "s3_bucket": settings.s3_bucket_name,
                "s3_configured": self.s3_service is not None
            }
            
        except Exception as e:
            return {
                "error": f"Failed to get stats: {str(e)}",
                "total_uploads": 0,
                "video_uploads": 0,
                "transcript_uploads": 0,
                "temporary_files": 0,
                "permanent_files": 0,
                "s3_configured": self.s3_service is not None
            } 