"""
Upload API endpoints with S3 storage support
"""

from typing import Dict, Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, verify_file_upload
from app.database import get_db
from app.schemas.upload import UploadResponse, TranscriptUpload
from app.services.file_service import FileService
from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/config/check")
async def check_s3_config(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Check S3 configuration status.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Dict with S3 configuration status
    """
    config_status = {
        "aws_access_key_id_configured": bool(settings.aws_access_key_id),
        "aws_secret_access_key_configured": bool(settings.aws_secret_access_key),
        "s3_bucket_name_configured": bool(settings.s3_bucket_name),
        "aws_region": settings.aws_region,
        "s3_bucket_name": settings.s3_bucket_name if settings.s3_bucket_name else "Not configured",
        "all_configured": bool(settings.aws_access_key_id and settings.aws_secret_access_key and settings.s3_bucket_name)
    }
    
    if config_status["all_configured"]:
        # Test S3 connection
        try:
            from app.services.s3_service import S3Service
            s3_service = S3Service()
            config_status["s3_connection_status"] = "Success"
            config_status["s3_service_available"] = True
        except Exception as e:
            config_status["s3_connection_status"] = f"Failed: {str(e)}"
            config_status["s3_service_available"] = False
    else:
        config_status["s3_connection_status"] = "Not tested - missing configuration"
        config_status["s3_service_available"] = False
    
    return {
        "status": "success",
        "s3_configuration": config_status,
        "recommendations": _get_config_recommendations(config_status)
    }


def _get_config_recommendations(config_status: Dict[str, Any]) -> List[str]:
    """Get configuration recommendations based on current status."""
    recommendations = []
    
    if not config_status["aws_access_key_id_configured"]:
        recommendations.append("Set AWS_ACCESS_KEY_ID in your environment variables")
    
    if not config_status["aws_secret_access_key_configured"]:
        recommendations.append("Set AWS_SECRET_ACCESS_KEY in your environment variables")
    
    if not config_status["s3_bucket_name_configured"]:
        recommendations.append("Set S3_BUCKET_NAME in your environment variables")
    
    if not config_status["all_configured"]:
        recommendations.append("Ensure your S3 bucket exists and you have proper permissions")
        recommendations.append("Check your AWS IAM user has s3:GetObject, s3:PutObject, s3:DeleteObject, s3:ListBucket permissions")
    
    if config_status["all_configured"] and not config_status.get("s3_service_available", False):
        recommendations.append("Check your AWS credentials are valid")
        recommendations.append("Verify the S3 bucket exists and is accessible")
        recommendations.append("Check your AWS region is correct")
    
    if not recommendations:
        recommendations.append("S3 is properly configured!")
    
    return recommendations


@router.post("/video", response_model=UploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    is_temp: bool = Query(True, description="Whether this is a temporary upload"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    """
    Upload a video file to S3 for YouTube Short creation.
    
    Args:
        file: Video file to upload
        is_temp: Whether this is a temporary file (default: True)
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        UploadResponse: Upload information including S3 details
        
    Raises:
        HTTPException: If upload fails
    """
    # Validate file
    file_info = verify_file_upload(file)
    
    if file_info.file_type != "video":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only video files are allowed for this endpoint"
        )
    
    # Save file to S3
    file_service = FileService(db)
    try:
        upload_response = await file_service.save_uploaded_file(
            file=file,
            file_type="video",
            is_temp=is_temp
        )
        return upload_response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload video to S3: {str(e)}"
        )


@router.post("/transcript-text", response_model=UploadResponse)
async def upload_transcript_text(
    transcript_data: TranscriptUpload,
    is_temp: bool = Query(True, description="Whether this is a temporary upload"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    """
    Upload transcript as text content to S3.
    
    Args:
        transcript_data: Transcript content
        is_temp: Whether this is a temporary file (default: True)
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        UploadResponse: Upload information including S3 details
    """
    if not transcript_data.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript content cannot be empty"
        )
    
    # Save transcript to S3
    file_service = FileService(db)
    try:
        upload_response = await file_service.save_transcript_text(
            content=transcript_data.content,
            filename="transcript.txt",
            is_temp=is_temp
        )
        return upload_response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload transcript to S3: {str(e)}"
        )


@router.post("/transcript-file", response_model=UploadResponse)
async def upload_transcript_file(
    file: UploadFile = File(...),
    is_temp: bool = Query(True, description="Whether this is a temporary upload"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    """
    Upload a transcript file to S3.
    
    Args:
        file: Transcript file (txt, md)
        is_temp: Whether this is a temporary file (default: True)
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        UploadResponse: Upload information including S3 details
        
    Raises:
        HTTPException: If upload fails
    """
    # Validate file
    file_info = verify_file_upload(file)
    
    if file_info.file_type != "transcript":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only transcript files (.txt, .md) are allowed for this endpoint"
        )
    
    # Save file to S3
    file_service = FileService(db)
    try:
        upload_response = await file_service.save_uploaded_file(
            file=file,
            file_type="transcript",
            is_temp=is_temp
        )
        return upload_response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload transcript file to S3: {str(e)}"
        )


@router.get("/{upload_id}", response_model=UploadResponse)
async def get_upload(
    upload_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    """
    Get upload information by ID.
    
    Args:
        upload_id: Upload UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        UploadResponse: Upload information
        
    Raises:
        HTTPException: If upload not found
    """
    file_service = FileService(db)
    upload = await file_service.get_upload_by_id(upload_id)
    
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found"
        )
    
    return UploadResponse(
        id=upload.id,
        filename=upload.filename,
        original_filename=upload.original_filename,
        file_type=upload.file_type,
        file_size_mb=upload.file_size_mb,
        upload_time=upload.upload_time
    )


@router.get("/{upload_id}/download")
async def download_upload(
    upload_id: UUID,
    use_presigned: bool = Query(True, description="Use presigned URL for download"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Download an uploaded file from S3.
    
    Args:
        upload_id: Upload UUID
        use_presigned: Whether to use presigned URL (default: True)
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Redirect to presigned URL or file content
        
    Raises:
        HTTPException: If upload not found
    """
    file_service = FileService(db)
    upload = await file_service.get_upload_by_id(upload_id)
    
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found"
        )
    
    if use_presigned:
        # Generate presigned URL and redirect
        try:
            presigned_url = await file_service.get_presigned_download_url(upload_id)
            return RedirectResponse(url=presigned_url, status_code=302)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate download URL: {str(e)}"
            )
    else:
        # Direct download (not recommended for large files)
        try:
            from fastapi.responses import Response
            
            file_content = await file_service.get_file_content(upload_id)
            
            # Determine content type
            content_type = "application/octet-stream"
            if upload.file_type == "video":
                content_type = "video/mp4"
            elif upload.file_type == "transcript":
                content_type = "text/plain"
            
            return Response(
                content=file_content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f"attachment; filename={upload.original_filename}"
                }
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to download file: {str(e)}"
            )


@router.post("/{upload_id}/move-to-permanent")
async def move_to_permanent(
    upload_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Move a temporary upload to permanent storage.
    
    Args:
        upload_id: Upload UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Dict with success message
        
    Raises:
        HTTPException: If upload not found or move fails
    """
    file_service = FileService(db)
    success = await file_service.move_temp_to_permanent(upload_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to move file to permanent storage. File may not exist or may already be permanent."
        )
    
    return {"status": "success", "message": "File moved to permanent storage successfully"}


@router.delete("/{upload_id}")
async def delete_upload(
    upload_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Delete an upload and its associated S3 file.
    
    Args:
        upload_id: Upload UUID
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Dict with success message
        
    Raises:
        HTTPException: If upload not found or deletion fails
    """
    file_service = FileService(db)
    success = await file_service.delete_upload(upload_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found or already deleted"
        )
    
    return {"status": "success", "message": "Upload deleted successfully"}


@router.post("/cleanup-temp")
async def cleanup_temp_files(
    hours: int = Query(24, ge=1, le=168, description="Files older than this many hours will be deleted"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Clean up temporary files older than specified hours.
    
    Args:
        hours: Files older than this many hours will be deleted (1-168 hours)
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Dict with cleanup statistics
    """
    file_service = FileService(db)
    result = await file_service.cleanup_temp_files(hours)
    
    return {
        "status": "success",
        "message": f"Cleanup completed for files older than {hours} hours",
        "cleanup_result": result
    }


@router.get("/stats/overview")
async def get_upload_stats(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get upload statistics and overview.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Dict with upload statistics
    """
    file_service = FileService(db)
    stats = await file_service.get_upload_stats()
    
    return {
        "status": "success",
        "statistics": stats
    } 