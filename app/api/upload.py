"""
Upload API endpoints
"""

from typing import Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, verify_file_upload
from app.database import get_db
from app.schemas.upload import UploadResponse, TranscriptUpload
from app.services.file_service import FileService

router = APIRouter()


@router.post("/video", response_model=UploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    """
    Upload a video file for YouTube Short creation.
    
    Args:
        file: Video file to upload
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        UploadResponse: Upload information
        
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
    
    # Save file
    file_service = FileService(db)
    try:
        upload_response = await file_service.save_uploaded_file(
            file=file,
            file_type="video"
        )
        return upload_response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload video: {str(e)}"
        )


@router.post("/transcript-text", response_model=Dict[str, str])
async def upload_transcript_text(
    transcript_data: TranscriptUpload,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Upload transcript as text (not saved as file).
    
    Args:
        transcript_data: Transcript content
        current_user: Current authenticated user
        
    Returns:
        Dict with success message and content preview
    """
    if not transcript_data.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript content cannot be empty"
        )
    
    # Return preview of transcript
    preview = transcript_data.content[:100]
    if len(transcript_data.content) > 100:
        preview += "..."
    
    return {
        "status": "success",
        "message": "Transcript received successfully",
        "content_preview": preview,
        "character_count": len(transcript_data.content)
    }


@router.post("/transcript-file", response_model=UploadResponse)
async def upload_transcript_file(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    """
    Upload a transcript file.
    
    Args:
        file: Transcript file (txt, md)
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        UploadResponse: Upload information
        
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
    
    # Save file
    file_service = FileService(db)
    try:
        upload_response = await file_service.save_uploaded_file(
            file=file,
            file_type="transcript"
        )
        return upload_response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload transcript file: {str(e)}"
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


@router.delete("/{upload_id}")
async def delete_upload(
    upload_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Delete an upload and its associated file.
    
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