"""
S3 service for handling file storage operations with AWS S3
"""

import asyncio
import io
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, BinaryIO
from uuid import UUID, uuid4

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from botocore.config import Config
from fastapi import UploadFile, HTTPException, status

from app.config import get_settings

settings = get_settings()


class S3Service:
    """Service for S3 file storage operations."""
    
    def __init__(self):
        """Initialize S3 client with configuration."""
        if not all([settings.aws_access_key_id, settings.aws_secret_access_key, settings.s3_bucket_name]):
            raise ValueError("AWS credentials and S3 bucket name must be configured")
        
        # Configure boto3 with retry and timeout settings
        config = Config(
            region_name=settings.aws_region,
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            max_pool_connections=50
        )
        
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            config=config
        )
        
        self.bucket_name = settings.s3_bucket_name
    
    async def upload_file(
        self,
        file: UploadFile,
        file_type: str,
        upload_id: UUID,
        is_temp: bool = True
    ) -> Dict[str, Any]:
        """
        Upload a file to S3.
        
        Args:
            file: FastAPI UploadFile object
            file_type: Type of file (video/transcript)
            upload_id: Unique upload identifier
            is_temp: Whether this is a temporary file
            
        Returns:
            Dict with S3 upload information
            
        Raises:
            HTTPException: If upload fails
        """
        try:
            # Generate S3 key based on file type and whether it's temporary
            s3_key = self._generate_s3_key(file.filename, file_type, upload_id, is_temp)
            
            # Prepare metadata
            metadata = {
                'upload-id': str(upload_id),
                'file-type': file_type,
                'original-filename': file.filename or "",
                'upload-timestamp': datetime.now(timezone.utc).isoformat(),
                'is-temp': str(is_temp).lower()
            }
            
            # Reset file pointer to beginning
            await file.seek(0)
            file_content = await file.read()
            await file.seek(0)  # Reset for potential future reads
            
            # Upload to S3
            await asyncio.to_thread(
                self.s3_client.put_object,
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_content,
                Metadata=metadata,
                ContentType=file.content_type or 'application/octet-stream'
            )
            
            # Get file size
            file_size = len(file_content)
            
            return {
                's3_key': s3_key,
                'bucket_name': self.bucket_name,
                's3_url': f"s3://{self.bucket_name}/{s3_key}",
                'file_size_bytes': file_size,
                'file_size_mb': round(file_size / (1024 * 1024), 2),
                'upload_timestamp': datetime.now(timezone.utc),
                'is_temp': is_temp,
                'metadata': metadata
            }
            
        except (ClientError, BotoCoreError) as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"S3 upload failed: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"File upload failed: {str(e)}"
            )
    
    async def upload_transcript_text(
        self,
        content: str,
        upload_id: UUID,
        filename: str = "transcript.txt",
        is_temp: bool = True
    ) -> Dict[str, Any]:
        """
        Upload transcript text content to S3.
        
        Args:
            content: Transcript text content
            upload_id: Unique upload identifier
            filename: Name for the transcript file
            is_temp: Whether this is a temporary file
            
        Returns:
            Dict with S3 upload information
        """
        try:
            # Generate S3 key
            s3_key = self._generate_s3_key(filename, "transcript", upload_id, is_temp)
            
            # Prepare metadata
            metadata = {
                'upload-id': str(upload_id),
                'file-type': 'transcript',
                'original-filename': filename,
                'upload-timestamp': datetime.now(timezone.utc).isoformat(),
                'is-temp': str(is_temp).lower(),
                'content-type': 'text'
            }
            
            # Convert content to bytes
            content_bytes = content.encode('utf-8')
            
            # Upload to S3
            await asyncio.to_thread(
                self.s3_client.put_object,
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=content_bytes,
                Metadata=metadata,
                ContentType='text/plain; charset=utf-8'
            )
            
            return {
                's3_key': s3_key,
                'bucket_name': self.bucket_name,
                's3_url': f"s3://{self.bucket_name}/{s3_key}",
                'file_size_bytes': len(content_bytes),
                'file_size_mb': round(len(content_bytes) / (1024 * 1024), 2),
                'upload_timestamp': datetime.now(timezone.utc),
                'is_temp': is_temp,
                'metadata': metadata
            }
            
        except (ClientError, BotoCoreError) as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"S3 transcript upload failed: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Transcript upload failed: {str(e)}"
            )
    
    async def download_file(self, s3_key: str) -> bytes:
        """
        Download a file from S3.
        
        Args:
            s3_key: S3 object key
            
        Returns:
            File content as bytes
            
        Raises:
            HTTPException: If download fails
        """
        try:
            response = await asyncio.to_thread(
                self.s3_client.get_object,
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return response['Body'].read()
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not found in S3"
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"S3 download failed: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"File download failed: {str(e)}"
            )
    
    async def delete_file(self, s3_key: str) -> bool:
        """
        Delete a file from S3.
        
        Args:
            s3_key: S3 object key
            
        Returns:
            True if deleted successfully
        """
        try:
            await asyncio.to_thread(
                self.s3_client.delete_object,
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
            
        except (ClientError, BotoCoreError):
            return False
        except Exception:
            return False
    
    async def delete_multiple_files(self, s3_keys: List[str]) -> Dict[str, int]:
        """
        Delete multiple files from S3.
        
        Args:
            s3_keys: List of S3 object keys
            
        Returns:
            Dict with success and failure counts
        """
        if not s3_keys:
            return {"success": 0, "failed": 0}
        
        try:
            # Prepare delete objects request
            delete_objects = [{'Key': key} for key in s3_keys]
            
            response = await asyncio.to_thread(
                self.s3_client.delete_objects,
                Bucket=self.bucket_name,
                Delete={'Objects': delete_objects}
            )
            
            deleted = len(response.get('Deleted', []))
            errors = len(response.get('Errors', []))
            
            return {"success": deleted, "failed": errors}
            
        except (ClientError, BotoCoreError):
            return {"success": 0, "failed": len(s3_keys)}
        except Exception:
            return {"success": 0, "failed": len(s3_keys)}
    
    async def generate_presigned_url(
        self,
        s3_key: str,
        expiration: int = None,
        method: str = 'get_object'
    ) -> str:
        """
        Generate a presigned URL for S3 object.
        
        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds
            method: HTTP method (get_object, put_object)
            
        Returns:
            Presigned URL string
            
        Raises:
            HTTPException: If URL generation fails
        """
        try:
            expiration = expiration or settings.s3_presigned_url_expiry
            
            url = await asyncio.to_thread(
                self.s3_client.generate_presigned_url,
                method,
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            
            return url
            
        except (ClientError, BotoCoreError) as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate presigned URL: {str(e)}"
            )
    
    async def move_file(self, source_key: str, destination_key: str) -> bool:
        """
        Move a file from temp to permanent location in S3.
        
        Args:
            source_key: Source S3 key
            destination_key: Destination S3 key
            
        Returns:
            True if moved successfully
        """
        try:
            # Copy object to new location
            await asyncio.to_thread(
                self.s3_client.copy_object,
                Bucket=self.bucket_name,
                CopySource={'Bucket': self.bucket_name, 'Key': source_key},
                Key=destination_key
            )
            
            # Delete original object
            await self.delete_file(source_key)
            
            return True
            
        except (ClientError, BotoCoreError):
            return False
        except Exception:
            return False
    
    async def cleanup_temp_files(self, hours: int = None) -> Dict[str, int]:
        """
        Clean up temporary files older than specified hours.
        
        Args:
            hours: Files older than this many hours will be deleted
            
        Returns:
            Dict with cleanup statistics
        """
        try:
            hours = hours or settings.s3_cleanup_temp_hours
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # List objects in temp prefix
            response = await asyncio.to_thread(
                self.s3_client.list_objects_v2,
                Bucket=self.bucket_name,
                Prefix=settings.s3_temp_prefix
            )
            
            old_objects = []
            for obj in response.get('Contents', []):
                if obj['LastModified'].replace(tzinfo=timezone.utc) < cutoff_time:
                    old_objects.append(obj['Key'])
            
            if old_objects:
                result = await self.delete_multiple_files(old_objects)
                return {
                    "total_checked": len(response.get('Contents', [])),
                    "deleted": result["success"],
                    "failed": result["failed"],
                    "cutoff_time": cutoff_time.isoformat()
                }
            
            return {
                "total_checked": len(response.get('Contents', [])),
                "deleted": 0,
                "failed": 0,
                "cutoff_time": cutoff_time.isoformat()
            }
            
        except (ClientError, BotoCoreError) as e:
            return {
                "error": f"Cleanup failed: {str(e)}",
                "deleted": 0,
                "failed": 0
            }
    
    async def get_file_metadata(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """
        Get file metadata from S3.
        
        Args:
            s3_key: S3 object key
            
        Returns:
            Dict with file metadata or None if not found
        """
        try:
            response = await asyncio.to_thread(
                self.s3_client.head_object,
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            return {
                'content_length': response.get('ContentLength', 0),
                'content_type': response.get('ContentType', ''),
                'last_modified': response.get('LastModified'),
                'metadata': response.get('Metadata', {}),
                'etag': response.get('ETag', '').strip('"')
            }
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return None
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get file metadata: {str(e)}"
            )
    
    def _generate_s3_key(
        self,
        filename: str,
        file_type: str,
        upload_id: UUID,
        is_temp: bool = True
    ) -> str:
        """
        Generate S3 key for file storage.
        
        Args:
            filename: Original filename
            file_type: Type of file (video/transcript)
            upload_id: Unique upload identifier
            is_temp: Whether this is a temporary file
            
        Returns:
            S3 key string
        """
        # Get file extension
        extension = ""
        if filename and "." in filename:
            extension = filename.split(".")[-1].lower()
        
        # Generate unique filename
        unique_filename = f"{upload_id}.{extension}" if extension else str(upload_id)
        
        # Determine prefix based on file type and temp status
        if is_temp:
            prefix = settings.s3_temp_prefix
        elif file_type == "video":
            prefix = settings.s3_videos_prefix
        elif file_type == "transcript":
            prefix = settings.s3_transcripts_prefix
        else:
            prefix = settings.s3_temp_prefix  # Default to temp for unknown types
        
        return f"{prefix}{unique_filename}"
    
    async def list_files_by_prefix(self, prefix: str) -> List[Dict[str, Any]]:
        """
        List files by prefix.
        
        Args:
            prefix: S3 prefix to search
            
        Returns:
            List of file information dictionaries
        """
        try:
            response = await asyncio.to_thread(
                self.s3_client.list_objects_v2,
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            files = []
            for obj in response.get('Contents', []):
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'etag': obj.get('ETag', '').strip('"')
                })
            
            return files
            
        except (ClientError, BotoCoreError) as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list files: {str(e)}"
            )

    async def list_objects(self) -> List[Dict[str, Any]]:
        """
        List all objects in the S3 bucket.
        
        Returns:
            List of S3 object information dictionaries
        """
        try:
            response = await asyncio.to_thread(
                self.s3_client.list_objects_v2,
                Bucket=self.bucket_name
            )
            
            objects = []
            for obj in response.get('Contents', []):
                objects.append({
                    'Key': obj['Key'],
                    'Size': obj['Size'],
                    'LastModified': obj['LastModified'],
                    'ETag': obj.get('ETag', '').strip('"')
                })
            
            return objects
            
        except (ClientError, BotoCoreError) as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list objects: {str(e)}"
            )

    def get_object_metadata(self, s3_key: str) -> Dict[str, Any]:
        """
        Get object metadata synchronously (for use in sync operations).
        
        Args:
            s3_key: S3 object key
            
        Returns:
            Dict with object metadata
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            return {
                'ContentLength': response.get('ContentLength', 0),
                'ContentType': response.get('ContentType', ''),
                'LastModified': response.get('LastModified'),
                'Metadata': response.get('Metadata', {}),
                'ETag': response.get('ETag', '').strip('"')
            }
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return {}
            raise e

    def generate_presigned_url_sync(
        self,
        s3_key: str,
        expiration: int = 3600,
        method: str = 'get_object'
    ) -> str:
        """
        Generate presigned URL synchronously (for use in sync operations).
        
        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds
            method: S3 method for the URL
            
        Returns:
            Presigned URL string
        """
        try:
            url = self.s3_client.generate_presigned_url(
                method,
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            
            return url
            
        except (ClientError, BotoCoreError) as e:
            return f"s3://{self.bucket_name}/{s3_key}"  # Fallback to S3 URI 