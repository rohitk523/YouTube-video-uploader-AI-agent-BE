"""
Secrets API endpoints for YouTube OAuth credentials management
"""

import base64
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db, restart_database_connection
from app.models.user import User
from app.schemas.secret import (
    SecretUploadRequest,
    SecretValidationResponse,
    SecretUploadResponse,
    SecretResponse,
    SecretStatusResponse,
    YouTubeOAuthInitRequest,
    YouTubeOAuthInitResponse,
    YouTubeOAuthCallbackRequest,
    YouTubeOAuthCallbackResponse,
    YouTubeTokenRefreshRequest,
    YouTubeTokenRefreshResponse,
    YouTubeAuthStatusResponse
)
from app.services.secret_service import SecretService

router = APIRouter()


@router.post("/restart-db-connection", tags=["Admin"])
async def restart_db_connection(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Admin endpoint to restart database connection pool.
    This clears all cached prepared statements.
    """
    try:
        await restart_database_connection()
        return {"message": "Database connection pool restarted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restart database connection: {str(e)}"
        )


@router.post("/validate", response_model=SecretValidationResponse, tags=["Secrets"])
async def validate_oauth_json(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> SecretValidationResponse:
    """
    Validate YouTube OAuth JSON file without storing it.
    
    Args:
        file: JSON file to validate
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        SecretValidationResponse: Validation result
        
    Raises:
        HTTPException: If validation fails
    """
    # Validate file type
    if not file.filename.endswith('.json'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a JSON file"
        )
    
    # Read and encode file content
    try:
        content = await file.read()
        file_content_base64 = base64.b64encode(content).decode('utf-8')
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}"
        )
    
    # Validate using service
    secret_service = SecretService(db)
    return await secret_service.validate_oauth_json(file_content_base64)


@router.post("/upload", response_model=SecretUploadResponse, tags=["Secrets"])
async def upload_oauth_secret(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> SecretUploadResponse:
    """
    Upload and store YouTube OAuth JSON file.
    
    This endpoint stores the OAuth credentials securely with encryption.
    Only one active secret per user is allowed.
    
    Args:
        file: JSON file containing OAuth credentials
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        SecretUploadResponse: Upload result with secret information
        
    Raises:
        HTTPException: If upload fails
    """
    # Validate file type
    if not file.filename.endswith('.json'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a JSON file"
        )
    
    # Check file size (limit to 1MB)
    max_size = 1024 * 1024  # 1MB
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 1MB"
        )
    
    # Encode file content
    try:
        file_content_base64 = base64.b64encode(content).decode('utf-8')
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process file: {str(e)}"
        )
    
    # Upload using service
    secret_service = SecretService(db)
    secret_response = await secret_service.upload_secret(
        user_id=current_user.id,
        filename=file.filename,
        file_content=file_content_base64
    )
    
    return SecretUploadResponse(
        id=secret_response.id,
        message="OAuth credentials uploaded and encrypted successfully",
        secret=secret_response
    )


@router.get("/status", response_model=SecretStatusResponse, tags=["Secrets"])
async def get_secret_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> SecretStatusResponse:
    """
    Check if user has uploaded OAuth credentials.
    
    This endpoint is used to determine if the user can proceed to the main application
    or needs to complete the OAuth setup step.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        SecretStatusResponse: Secret status information
    """
    secret_service = SecretService(db)
    return await secret_service.check_user_secret_status(current_user.id)


@router.get("/list", response_model=List[SecretResponse], tags=["Secrets"])
async def get_user_secrets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[SecretResponse]:
    """
    Get list of user's OAuth credentials (non-sensitive data only).
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        List[SecretResponse]: List of user's secrets
    """
    secret_service = SecretService(db)
    return await secret_service.get_user_secrets(current_user.id)


@router.delete("/{secret_id}", tags=["Secrets"])
async def delete_secret(
    secret_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Delete (deactivate) an OAuth credential.
    
    Args:
        secret_id: Secret ID to delete
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        dict: Deletion confirmation
        
    Raises:
        HTTPException: If secret not found or deletion fails
    """
    secret_service = SecretService(db)
    success = await secret_service.delete_secret(current_user.id, secret_id)
    
    if success:
        return {"message": "OAuth credential deleted successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete OAuth credential"
        )


@router.post("/reupload", response_model=SecretUploadResponse, tags=["Secrets"])
async def reupload_oauth_secret(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> SecretUploadResponse:
    """
    Re-upload OAuth credentials (replaces existing active credentials).
    
    This is an alias for the upload endpoint but makes the intent clearer
    when users want to replace their existing credentials.
    
    Args:
        file: New JSON file containing OAuth credentials
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        SecretUploadResponse: Upload result
    """
    # This is the same as upload - it automatically deactivates existing secrets
    return await upload_oauth_secret(file, current_user, db)


# NEW YOUTUBE OAUTH ENDPOINTS

@router.post("/youtube/oauth/init", response_model=YouTubeOAuthInitResponse, tags=["YouTube OAuth"])
async def initiate_youtube_oauth(
    request: YouTubeOAuthInitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> YouTubeOAuthInitResponse:
    """
    Initiate YouTube OAuth 2.0 authorization flow.
    
    This endpoint generates an authorization URL that the user should visit
    to grant YouTube access permissions. After user consent, they will be
    redirected back to your callback URL with an authorization code.
    
    Args:
        request: OAuth initialization request with scopes
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        YouTubeOAuthInitResponse: Authorization URL and state parameter
        
    Raises:
        HTTPException: If OAuth flow initialization fails
    """
    secret_service = SecretService(db)
    return await secret_service.initiate_youtube_oauth(
        user_id=current_user.id,
        scopes=request.scopes,
        state=request.state
    )


@router.post("/youtube/oauth/callback", response_model=YouTubeOAuthCallbackResponse, tags=["YouTube OAuth"])
async def handle_youtube_oauth_callback(
    request: YouTubeOAuthCallbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> YouTubeOAuthCallbackResponse:
    """
    Handle YouTube OAuth 2.0 authorization callback.
    
    This endpoint processes the authorization code received from YouTube
    after user consent and exchanges it for access and refresh tokens.
    The tokens are then encrypted and stored in the database.
    
    Args:
        request: OAuth callback request with authorization code
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        YouTubeOAuthCallbackResponse: Callback processing result
        
    Raises:
        HTTPException: If callback processing fails
    """
    secret_service = SecretService(db)
    return await secret_service.handle_youtube_oauth_callback(
        user_id=current_user.id,
        code=request.code,
        state=request.state
    )


@router.get("/youtube/auth/status", response_model=YouTubeAuthStatusResponse, tags=["YouTube OAuth"])
async def get_youtube_auth_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> YouTubeAuthStatusResponse:
    """
    Get YouTube authentication status for the current user.
    
    This endpoint provides information about the user's YouTube OAuth
    authentication state, including token expiry and granted scopes.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        YouTubeAuthStatusResponse: YouTube authentication status
    """
    secret_service = SecretService(db)
    return await secret_service.get_youtube_auth_status(current_user.id)


@router.post("/youtube/tokens/refresh", response_model=YouTubeTokenRefreshResponse, tags=["YouTube OAuth"])
async def refresh_youtube_tokens(
    request: YouTubeTokenRefreshRequest = YouTubeTokenRefreshRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> YouTubeTokenRefreshResponse:
    """
    Manually refresh YouTube OAuth tokens.
    
    This endpoint allows manual refresh of YouTube access tokens using
    the stored refresh token. Normally, tokens are refreshed automatically
    when needed, but this endpoint can be used for manual refresh or testing.
    
    Args:
        request: Token refresh request
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        YouTubeTokenRefreshResponse: Token refresh result
    """
    secret_service = SecretService(db)
    return await secret_service.refresh_youtube_tokens(
        user_id=current_user.id,
        force_refresh=request.force_refresh
    )


@router.delete("/youtube/auth", tags=["YouTube OAuth"])
async def revoke_youtube_auth(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Revoke YouTube authentication and clear stored tokens.
    
    This endpoint clears all stored YouTube OAuth tokens for the user,
    requiring them to re-authenticate for future YouTube operations.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        dict: Revocation confirmation
        
    Raises:
        HTTPException: If revocation fails
    """
    secret_service = SecretService(db)
    secret = await secret_service.get_active_secret(current_user.id)
    
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No OAuth credentials found"
        )
    
    try:
        # Clear YouTube tokens and authentication status
        secret.youtube_access_token_encrypted = None
        secret.youtube_refresh_token_encrypted = None
        secret.youtube_token_expires_at = None
        secret.youtube_scopes = None
        secret.youtube_authenticated = False
        secret.youtube_tokens_updated_at = None
        secret.youtube_last_refresh_attempt = None
        
        await db.commit()
        
        return {
            "message": "YouTube authentication revoked successfully",
            "requires_reauth": True
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke YouTube authentication: {str(e)}"
        ) 