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
from app.models.user import User
from app.schemas.upload import (
    UploadResponse, 
    TranscriptUpload, 
    AITranscriptRequest, 
    AITranscriptResponse, 
    AITranscriptValidation, 
    AITranscriptServiceInfo
)
from app.schemas.video import VideoCreate
from app.services.file_service import FileService
from app.repositories.video_repository import VideoRepository
from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/config/check")
async def check_s3_config(
    current_user: User = Depends(get_current_user)
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
    custom_name: str = Query(None, description="Custom name for the video (optional)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    """
    Upload a video file to S3 for YouTube Short creation.
    
    Args:
        file: Video file to upload
        is_temp: Whether this is a temporary file (default: True)
        custom_name: Custom name for the video (optional)
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
            user_id=current_user.id,
            is_temp=is_temp,
            custom_name=custom_name
        )
        
        # If this is a video and not temporary, also save to videos table for easy reuse
        if not is_temp and file_info.file_type == "video":
            try:
                # Get the upload record to extract S3 details
                upload_record = await file_service.get_upload_by_id(upload_response.id)
                if upload_record:
                    video_repo = VideoRepository(db)
                    
                    # Check if video already exists (prevent duplicates)
                    existing_video = await video_repo.get_by_s3_key(
                        s3_key=upload_record.s3_key,
                        user_id=current_user.id
                    )
                    
                    if not existing_video:
                        # Create video record
                        video_data = VideoCreate(
                            filename=upload_record.filename,
                            original_filename=upload_record.original_filename,
                            s3_key=upload_record.s3_key,
                            s3_url=upload_record.s3_url,
                            s3_bucket=upload_record.s3_bucket,
                            content_type=file.content_type or "video/mp4",
                            file_size=upload_record.file_size_bytes,
                            user_id=current_user.id
                        )
                        
                        await video_repo.create_video(video_data)
            except Exception as video_save_error:
                # Log the error but don't fail the upload
                print(f"Warning: Failed to save video metadata: {str(video_save_error)}")
        
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
    custom_name: str = Query(None, description="Custom name for the transcript (optional)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    """
    Upload transcript as text content to S3.
    
    Args:
        transcript_data: Transcript content
        is_temp: Whether this is a temporary file (default: True)
        custom_name: Custom name for the transcript (optional)
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        UploadResponse: Upload information including S3 details
        
    Raises:
        HTTPException: If upload fails
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
            user_id=current_user.id,
            is_temp=is_temp,
            custom_name=custom_name
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
    custom_name: str = Query(None, description="Custom name for the transcript (optional)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    """
    Upload transcript file to S3.
    
    Args:
        file: Transcript file to upload
        is_temp: Whether this is a temporary file (default: True)
        custom_name: Custom name for the transcript (optional)
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
            detail="Only transcript files are allowed for this endpoint"
        )
    
    # Save file to S3
    file_service = FileService(db)
    try:
        upload_response = await file_service.save_uploaded_file(
            file=file,
            file_type="transcript",
            user_id=current_user.id,
            is_temp=is_temp,
            custom_name=custom_name
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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


@router.get("/debug/s3-test/{s3_key:path}")
async def debug_s3_access(
    s3_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Debug endpoint to test S3 access for specific files.
    
    Args:
        s3_key: S3 object key to test
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Dict with debug information
    """
    from app.services.s3_service import S3Service
    
    try:
        s3_service = S3Service()
        
        # Test 1: Check if file exists
        try:
            metadata = await s3_service.get_file_metadata(s3_key)
            file_exists = metadata is not None
            metadata_error = None
        except Exception as e:
            file_exists = False
            metadata_error = str(e)
            metadata = None
        
        # Test 2: Try to generate presigned URL
        try:
            presigned_url = await s3_service.generate_presigned_url(s3_key, expiration=300)  # 5 minutes
            presigned_success = True
            presigned_error = None
        except Exception as e:
            presigned_success = False
            presigned_error = str(e)
            presigned_url = None
        
        # Test 3: Try to download a small chunk
        download_test = False
        download_error = None
        if presigned_url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.head(presigned_url)
                    download_test = response.status_code == 200
                    if not download_test:
                        download_error = f"HTTP {response.status_code}: {response.text}"
            except Exception as e:
                download_error = str(e)
        
        return {
            "s3_key": s3_key,
            "bucket": s3_service.bucket_name,
            "file_exists": file_exists,
            "metadata": metadata if file_exists else None,
            "metadata_error": metadata_error if not file_exists else None,
            "presigned_url_generation": {
                "success": presigned_success,
                "url": presigned_url[:100] + "..." if presigned_url and len(presigned_url) > 100 else presigned_url,
                "error": presigned_error if not presigned_success else None
            },
            "download_test": {
                "success": download_test,
                "error": download_error
            }
        }
        
    except Exception as e:
        return {
            "error": f"S3 service initialization failed: {str(e)}",
            "s3_key": s3_key
        }


@router.get("/debug/aws-permissions")
async def debug_aws_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Debug endpoint to test AWS IAM permissions.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Dict with permissions test results
    """
    from app.services.s3_service import S3Service
    import boto3
    from app.config import get_settings
    
    settings = get_settings()
    results = {
        "bucket": settings.s3_bucket_name,
        "region": settings.aws_region,
        "tests": {}
    }
    
    try:
        # Test 1: List bucket objects (s3:ListBucket)
        try:
            s3_service = S3Service()
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region
            )
            
            response = s3_client.list_objects_v2(
                Bucket=settings.s3_bucket_name,
                Prefix="temp/",
                MaxKeys=1
            )
            results["tests"]["list_bucket"] = {"success": True, "message": "Can list bucket objects"}
        except Exception as e:
            results["tests"]["list_bucket"] = {"success": False, "error": str(e)}
        
        # Test 2: Get object metadata (s3:GetObject metadata)
        test_key = "temp/49948364-58bb-4a69-8426-41895624ae3f.mp4"
        try:
            response = s3_client.head_object(
                Bucket=settings.s3_bucket_name,
                Key=test_key
            )
            results["tests"]["head_object"] = {"success": True, "message": "Can read object metadata"}
        except Exception as e:
            results["tests"]["head_object"] = {"success": False, "error": str(e)}
        
        # Test 3: Get object (s3:GetObject)
        try:
            response = s3_client.get_object(
                Bucket=settings.s3_bucket_name,
                Key=test_key,
                Range="bytes=0-1023"  # Just get first 1KB
            )
            results["tests"]["get_object"] = {"success": True, "message": "Can download object content"}
        except Exception as e:
            results["tests"]["get_object"] = {"success": False, "error": str(e)}
        
        # Test 4: Check if bucket region matches configured region
        try:
            response = s3_client.get_bucket_location(Bucket=settings.s3_bucket_name)
            bucket_region = response.get('LocationConstraint') or 'us-east-1'
            results["tests"]["region_check"] = {
                "success": bucket_region == settings.aws_region,
                "bucket_region": bucket_region,
                "configured_region": settings.aws_region,
                "message": f"Bucket is in {bucket_region}, configured for {settings.aws_region}"
            }
        except Exception as e:
            results["tests"]["region_check"] = {"success": False, "error": str(e)}
            
        # Test 5: Generate and test presigned URL
        try:
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': settings.s3_bucket_name, 'Key': test_key},
                ExpiresIn=300
            )
            
            # Test the presigned URL
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.head(presigned_url)
                if response.status_code == 200:
                    results["tests"]["presigned_url"] = {"success": True, "message": "Presigned URL works"}
                else:
                    results["tests"]["presigned_url"] = {
                        "success": False, 
                        "error": f"Presigned URL returned HTTP {response.status_code}"
                    }
        except Exception as e:
            results["tests"]["presigned_url"] = {"success": False, "error": str(e)}
            
    except Exception as e:
        results["error"] = f"Failed to initialize AWS client: {str(e)}"
    
    return results


# AI Transcript Generation Endpoints

@router.post("/ai-transcript/generate", response_model=AITranscriptResponse)
async def generate_ai_transcript(
    request: AITranscriptRequest,
    current_user: User = Depends(get_current_user)
) -> AITranscriptResponse:
    """
    Generate AI-powered transcript for YouTube Shorts.
    
    Args:
        request: AI transcript generation request
        current_user: Current authenticated user
        
    Returns:
        AITranscriptResponse: Generated transcript with metadata
    """
    from app.services.ai_transcript_service import AITranscriptService
    
    try:
        # Initialize the AI transcript service
        ai_service = AITranscriptService()
        
        # Generate transcript
        result = await ai_service.generate_transcript(
            context=request.context,
            user_id=str(current_user.id),
            custom_instructions=request.custom_instructions if request.custom_instructions else None
        )
        
        return AITranscriptResponse(**result)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate AI transcript: {str(e)}"
        )


@router.post("/ai-transcript/validate", response_model=AITranscriptValidation)
async def validate_ai_transcript_context(
    request: AITranscriptRequest,
    current_user: User = Depends(get_current_user)
) -> AITranscriptValidation:
    """
    Validate context for AI transcript generation.
    
    Args:
        request: AI transcript generation request
        current_user: Current authenticated user
        
    Returns:
        AITranscriptValidation: Validation result
    """
    from app.services.ai_transcript_service import AITranscriptService
    
    try:
        ai_service = AITranscriptService()
        validation_result = await ai_service.validate_context(request.context)
        
        return AITranscriptValidation(**validation_result)
        
    except Exception as e:
        return AITranscriptValidation(
            valid=False,
            error=f"Validation failed: {str(e)}"
        )


@router.get("/ai-transcript/service-info", response_model=AITranscriptServiceInfo)
async def get_ai_transcript_service_info(
    current_user: User = Depends(get_current_user)
) -> AITranscriptServiceInfo:
    """
    Get AI transcript service information and status.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        AITranscriptServiceInfo: Service information
    """
    from app.services.ai_transcript_service import AITranscriptService
    
    try:
        ai_service = AITranscriptService()
        service_info = ai_service.get_service_info()
        
        return AITranscriptServiceInfo(**service_info)
        
    except Exception as e:
        # Return basic info even if service fails to initialize
        return AITranscriptServiceInfo(
            service_name="AI Transcript Service",
            openai_configured=bool(settings.openai_api_key),
            langfuse_configured=settings.langfuse_configured,
            langfuse_available=False,
            prompt_file_exists=False,
            default_model="gpt-4",
            fallback_model="gpt-3.5-turbo",
            max_tokens=500,
            temperature=0.7
        ) 