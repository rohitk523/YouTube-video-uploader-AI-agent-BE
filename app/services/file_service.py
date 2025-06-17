"""
File service for handling uploads and file management
"""

import os
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.upload import Upload
from app.schemas.upload import UploadResponse

settings = get_settings()


class FileService:
    """Service for file upload and management operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Ensure upload and temp directories exist."""
        Path(settings.upload_directory).mkdir(parents=True, exist_ok=True)
        Path(settings.temp_directory).mkdir(parents=True, exist_ok=True)
        Path(settings.static_directory).mkdir(parents=True, exist_ok=True)
    
    async def save_uploaded_file(
        self, 
        file: UploadFile, 
        file_type: str,
        job_id: Optional[UUID] = None
    ) -> UploadResponse:
        """
        Save uploaded file to disk and database.
        
        Args:
            file: Uploaded file
            file_type: Type of file (video/transcript)
            job_id: Optional job ID to associate with upload
            
        Returns:
            UploadResponse: Upload information
            
        Raises:
            HTTPException: If file save fails
        """
        try:
            # Generate unique filename
            file_extension = file.filename.split(".")[-1] if file.filename else ""
            unique_filename = f"{uuid4()}.{file_extension}"
            file_path = os.path.join(settings.upload_directory, unique_filename)
            
            # Save file to disk
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Create database record
            upload = Upload(
                filename=unique_filename,
                original_filename=file.filename or "",
                file_path=file_path,
                file_type=file_type,
                file_size_bytes=file_size,
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
            
        except Exception as e:
            # Clean up file if database save failed
            if os.path.exists(file_path):
                os.remove(file_path)
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {str(e)}"
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
    
    async def delete_upload(self, upload_id: UUID) -> bool:
        """
        Delete upload and associated file.
        
        Args:
            upload_id: Upload UUID
            
        Returns:
            bool: True if deleted successfully
        """
        upload = await self.get_upload_by_id(upload_id)
        if not upload:
            return False
        
        try:
            # Mark as inactive in database
            upload.is_active = False
            await self.db.commit()
            
            # Delete file from disk
            if os.path.exists(upload.file_path):
                os.remove(upload.file_path)
            
            return True
            
        except Exception:
            await self.db.rollback()
            return False
    
    async def cleanup_old_files(self, hours: int = 24) -> int:
        """
        Clean up old inactive upload files.
        
        Args:
            hours: Files older than this many hours will be deleted
            
        Returns:
            int: Number of files deleted
        """
        from datetime import datetime, timedelta, timezone
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        result = await self.db.execute(
            select(Upload).where(
                Upload.is_active == False,
                Upload.upload_time < cutoff_time
            )
        )
        old_uploads = result.scalars().all()
        
        deleted_count = 0
        for upload in old_uploads:
            try:
                if os.path.exists(upload.file_path):
                    os.remove(upload.file_path)
                
                await self.db.delete(upload)
                deleted_count += 1
                
            except Exception:
                continue
        
        await self.db.commit()
        return deleted_count
    
    def get_file_info(self, file_path: str) -> dict:
        """
        Get file information.
        
        Args:
            file_path: Path to file
            
        Returns:
            dict: File information
        """
        if not os.path.exists(file_path):
            return {"exists": False}
        
        stat = os.stat(file_path)
        return {
            "exists": True,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified_time": stat.st_mtime,
            "extension": Path(file_path).suffix.lower()
        } 