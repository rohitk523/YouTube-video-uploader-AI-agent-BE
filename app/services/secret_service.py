"""
Service for managing YouTube OAuth secrets
"""

import json
import base64
import logging
from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, status

from app.models.secret import Secret
from app.models.user import User
from app.schemas.secret import (
    YouTubeOAuthJSON, 
    SecretValidationResponse, 
    SecretResponse,
    SecretStatusResponse,
    YouTubeOAuthInitResponse,
    YouTubeOAuthCallbackResponse,
    YouTubeTokenRefreshResponse,
    YouTubeAuthStatusResponse
)
from app.services.encryption_service import get_encryption_service

logger = logging.getLogger(__name__)


class SecretService:
    """Service for managing YouTube OAuth secrets."""
    
    def __init__(self, db: AsyncSession):
        """
        Initialize secret service.
        
        Args:
            db: Database session
        """
        self.db = db
        self.encryption_service = get_encryption_service()
    
    async def validate_oauth_json(self, file_content: str) -> SecretValidationResponse:
        """
        Validate YouTube OAuth JSON file content.
        
        Args:
            file_content: Base64 encoded JSON file content
            
        Returns:
            SecretValidationResponse: Validation result
        """
        try:
            # Decode base64 content
            try:
                json_content = base64.b64decode(file_content).decode('utf-8')
            except Exception:
                return SecretValidationResponse(
                    valid=False,
                    errors=["Invalid base64 encoding"]
                )
            
            # Parse JSON
            try:
                data = json.loads(json_content)
            except json.JSONDecodeError as e:
                return SecretValidationResponse(
                    valid=False,
                    errors=[f"Invalid JSON format: {str(e)}"]
                )
            
            # Validate using Pydantic schema
            try:
                oauth_data = YouTubeOAuthJSON(**data)
                web_config = oauth_data.web
                
                return SecretValidationResponse(
                    valid=True,
                    project_id=web_config.get('project_id'),
                    client_id_preview=web_config.get('client_id', '')[:20] + '...',
                    warnings=[]
                )
            except ValueError as e:
                return SecretValidationResponse(
                    valid=False,
                    errors=[str(e)]
                )
        
        except Exception as e:
            return SecretValidationResponse(
                valid=False,
                errors=[f"Validation failed: {str(e)}"]
            )
    
    async def upload_secret(
        self, 
        user_id: UUID, 
        filename: str, 
        file_content: str
    ) -> SecretResponse:
        """
        Upload and store YouTube OAuth secret.
        
        Args:
            user_id: User ID
            filename: Original filename
            file_content: Base64 encoded JSON file content
            
        Returns:
            SecretResponse: Created secret information
            
        Raises:
            HTTPException: If upload fails
        """
        # First validate the file
        validation = await self.validate_oauth_json(file_content)
        if not validation.valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid OAuth JSON file: {', '.join(validation.errors)}"
            )
        
        try:
            # Decode and parse JSON
            json_content = base64.b64decode(file_content).decode('utf-8')
            data = json.loads(json_content)
            web_config = data['web']
            
            # Check if user already has secrets (deactivate old ones)
            await self._deactivate_existing_secrets(user_id)
            
            # Encrypt sensitive fields
            client_id_encrypted = self.encryption_service.encrypt(web_config['client_id'])
            client_secret_encrypted = self.encryption_service.encrypt(web_config['client_secret'])
            
            # Prepare redirect URIs
            redirect_uris_json = None
            if 'redirect_uris' in web_config:
                redirect_uris_json = json.dumps(web_config['redirect_uris'])
            
            # Create secret record
            secret = Secret(
                user_id=user_id,
                project_id=web_config['project_id'],
                client_id_encrypted=client_id_encrypted,
                client_secret_encrypted=client_secret_encrypted,
                auth_uri=web_config.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
                token_uri=web_config.get('token_uri', 'https://oauth2.googleapis.com/token'),
                auth_provider_x509_cert_url=web_config.get(
                    'auth_provider_x509_cert_url', 
                    'https://www.googleapis.com/oauth2/v1/certs'
                ),
                redirect_uris=redirect_uris_json,
                original_filename=filename,
                is_active=True,
                is_verified=True,
                youtube_authenticated=False  # User needs to complete OAuth flow
            )
            
            self.db.add(secret)
            await self.db.commit()
            await self.db.refresh(secret)
            
            return SecretResponse.model_validate(secret)
            
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to store secret: {str(e)}"
            )
    
    async def _deactivate_existing_secrets(self, user_id: UUID) -> None:
        """Deactivate existing secrets for a user."""
        stmt = select(Secret).where(
            and_(Secret.user_id == user_id, Secret.is_active == True)
        )
        result = await self.db.execute(stmt)
        existing_secrets = result.scalars().all()
        
        for secret in existing_secrets:
            secret.is_active = False
        
        await self.db.commit()
    
    async def get_active_secret(self, user_id: UUID) -> Optional[Secret]:
        """
        Get active secret for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Optional[Secret]: Active secret or None
        """
        stmt = select(Secret).where(
            and_(
                Secret.user_id == user_id,
                Secret.is_active == True,
                Secret.is_verified == True
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def check_user_secret_status(self, user_id: UUID) -> SecretStatusResponse:
        """
        Check user's secret status.
        
        Args:
            user_id: User ID
            
        Returns:
            SecretStatusResponse: Secret status information
        """
        stmt = select(Secret).where(Secret.user_id == user_id)
        result = await self.db.execute(stmt)
        secrets = result.scalars().all()
        
        active_secrets = [s for s in secrets if s.is_active and s.is_verified]
        active_secret = active_secrets[0] if active_secrets else None
        
        # Use the same logic as YouTube auth-status: just check if we have access token and youtube_authenticated flag
        has_youtube_auth = (
            active_secret and 
            active_secret.youtube_authenticated and 
            active_secret.youtube_access_token_encrypted is not None
        )
        
        return SecretStatusResponse(
            has_secrets=len(secrets) > 0,
            active_secrets=len(active_secrets),
            youtube_authenticated=has_youtube_auth,
            requires_youtube_auth=not has_youtube_auth,
            project_id=active_secret.project_id if active_secret else None,
            last_updated=active_secret.updated_at if active_secret else None,
            youtube_tokens_expires_at=active_secret.youtube_token_expires_at if active_secret else None
        )
    
    async def get_user_secrets(self, user_id: UUID) -> List[SecretResponse]:
        """
        Get list of user's secrets (non-sensitive data only).
        
        Args:
            user_id: User ID
            
        Returns:
            List[SecretResponse]: List of user's secrets
        """
        stmt = select(Secret).where(Secret.user_id == user_id).order_by(Secret.created_at.desc())
        result = await self.db.execute(stmt)
        secrets = result.scalars().all()
        
        return [SecretResponse.model_validate(secret) for secret in secrets]
    
    async def delete_secret(self, user_id: UUID, secret_id: UUID) -> bool:
        """
        Delete (deactivate) a secret.
        
        Args:
            user_id: User ID
            secret_id: Secret ID
            
        Returns:
            bool: True if successful
        """
        stmt = select(Secret).where(
            and_(Secret.id == secret_id, Secret.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        secret = result.scalar_one_or_none()
        
        if secret:
            secret.is_active = False
            secret.youtube_authenticated = False
            await self.db.commit()
            return True
        
        return False
    
    async def get_decrypted_credentials(self, user_id: UUID) -> Optional[Dict[str, str]]:
        """
        Get decrypted OAuth credentials for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Optional[Dict[str, str]]: Decrypted credentials with client_id and client_secret
        """
        secret = await self.get_active_secret(user_id)
        if not secret:
            return None
        
        try:
            client_id = self.encryption_service.decrypt(secret.client_id_encrypted)
            client_secret = self.encryption_service.decrypt(secret.client_secret_encrypted)
            
            # Update last used timestamp
            secret.last_used_at = datetime.now(timezone.utc)
            await self.db.commit()
            
            return {
                'client_id': client_id,
                'client_secret': client_secret,
                'project_id': secret.project_id,
                'auth_uri': secret.auth_uri,
                'token_uri': secret.token_uri
            }
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to decrypt credentials: {str(e)}"
            )

    # NEW METHODS FOR YOUTUBE OAUTH TOKEN MANAGEMENT

    async def initiate_youtube_oauth(self, user_id: UUID, scopes: List[str], state: Optional[str] = None) -> YouTubeOAuthInitResponse:
        """
        Initiate YouTube OAuth flow.
        
        Args:
            user_id: User ID
            scopes: OAuth scopes to request
            state: Optional state parameter for security
            
        Returns:
            YouTubeOAuthInitResponse: Authorization URL and state
        """
        secret = await self.get_active_secret(user_id)
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No OAuth credentials found. Please upload your client_secret.json first."
            )
        
        try:
            from google_auth_oauthlib.flow import Flow
            import secrets as secrets_module
            
            # Get decrypted credentials
            credentials = await self.get_decrypted_credentials(user_id)
            
            # Create OAuth flow
            client_config = {
                "web": {
                    "client_id": credentials['client_id'],
                    "client_secret": credentials['client_secret'],
                    "auth_uri": credentials['auth_uri'],
                    "token_uri": credentials['token_uri'],
                    "redirect_uris": ["http://localhost:8080", "http://localhost:3000", "http://localhost:8000/oauth/callback"]  # Common URIs
                }
            }
            
            flow = Flow.from_client_config(
                client_config=client_config,
                scopes=scopes
            )
            
            # Try common redirect URIs that are often pre-configured
            flow.redirect_uri = "http://localhost:8000/oauth/callback"  # Most common default
            
            # Generate state if not provided
            if not state:
                state = secrets_module.token_urlsafe(32)
            
            # Generate authorization URL
            authorization_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent',  # Force consent screen to get refresh token
                state=state
            )
            
            return YouTubeOAuthInitResponse(
                authorization_url=authorization_url,
                state=state
            )
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initiate OAuth flow: {str(e)}"
            )

    async def handle_youtube_oauth_callback(self, user_id: UUID, code: str, state: Optional[str] = None) -> YouTubeOAuthCallbackResponse:
        """
        Handle YouTube OAuth callback and store tokens.
        
        Args:
            user_id: User ID
            code: Authorization code from YouTube
            state: State parameter for verification
            
        Returns:
            YouTubeOAuthCallbackResponse: Callback result
        """
        secret = await self.get_active_secret(user_id)
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No OAuth credentials found."
            )
        
        try:
            from google_auth_oauthlib.flow import Flow
            from google.oauth2.credentials import Credentials
            
            # Get decrypted credentials
            credentials = await self.get_decrypted_credentials(user_id)
            
            # Create OAuth flow
            client_config = {
                "web": {
                    "client_id": credentials['client_id'],
                    "client_secret": credentials['client_secret'],
                    "auth_uri": credentials['auth_uri'],
                    "token_uri": credentials['token_uri'],
                    "redirect_uris": ["http://localhost:8080", "http://localhost:3000", "http://localhost:8000/oauth/callback"]
                }
            }
            
            flow = Flow.from_client_config(
                client_config=client_config,
                scopes=[
                    "https://www.googleapis.com/auth/youtube.upload",
                    "https://www.googleapis.com/auth/youtube"
                ]
            )
            flow.redirect_uri = "http://localhost:8000/oauth/callback"
            
            # Exchange authorization code for tokens
            flow.fetch_token(code=code)
            
            # Get credentials with tokens
            creds = flow.credentials
            
            # Store encrypted tokens
            await self._store_youtube_tokens(secret, creds)
            
            return YouTubeOAuthCallbackResponse(
                success=True,
                message="YouTube OAuth completed successfully",
                youtube_authenticated=True,
                scopes_granted=creds.scopes or [],
                expires_at=creds.expiry
            )
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"OAuth callback failed: {str(e)}"
            )

    async def _store_youtube_tokens(self, secret: Secret, credentials) -> None:
        """
        Store YouTube OAuth tokens in database.
        
        Args:
            secret: Secret record
            credentials: Google OAuth credentials object
        """
        try:
            # Encrypt and store tokens
            if credentials.token:
                secret.youtube_access_token_encrypted = self.encryption_service.encrypt(credentials.token)
            
            if credentials.refresh_token:
                secret.youtube_refresh_token_encrypted = self.encryption_service.encrypt(credentials.refresh_token)
            
            # Store expiry and metadata
            if credentials.expiry:
                # Ensure the expiry datetime is timezone-aware before storing
                expiry = credentials.expiry
                if expiry.tzinfo is None:
                    # If timezone-naive, assume UTC
                    expiry = expiry.replace(tzinfo=timezone.utc)
                secret.youtube_token_expires_at = expiry
            else:
                secret.youtube_token_expires_at = None
            secret.youtube_scopes = json.dumps(credentials.scopes or [])
            secret.youtube_authenticated = True
            secret.youtube_tokens_updated_at = datetime.now(timezone.utc)
            
            await self.db.commit()
            
        except Exception as e:
            await self.db.rollback()
            raise Exception(f"Failed to store YouTube tokens: {str(e)}")

    async def get_youtube_credentials(self, user_id: UUID, auto_refresh: bool = True):
        """
        Get YouTube credentials with automatic token refresh.
        
        Args:
            user_id: User ID
            auto_refresh: Whether to automatically refresh expired tokens
            
        Returns:
            Google OAuth credentials object
        """
        secret = await self.get_active_secret(user_id)
        if not secret or not secret.youtube_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="YouTube authentication required. Please complete OAuth flow."
            )
        
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            
            # Decrypt tokens
            access_token = None
            refresh_token = None
            
            if secret.youtube_access_token_encrypted:
                access_token = self.encryption_service.decrypt(secret.youtube_access_token_encrypted)
            
            if secret.youtube_refresh_token_encrypted:
                refresh_token = self.encryption_service.decrypt(secret.youtube_refresh_token_encrypted)
            
            if not access_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="No access token found. Please re-authenticate."
                )
            
            # Get client credentials
            client_creds = await self.get_decrypted_credentials(user_id)
            
            # Create credentials object
            creds = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri=client_creds['token_uri'],
                client_id=client_creds['client_id'],
                client_secret=client_creds['client_secret'],
                scopes=json.loads(secret.youtube_scopes or '[]')
            )
            
            # Set expiry if available
            if secret.youtube_token_expires_at:
                expiry = secret.youtube_token_expires_at
                # Convert to naive UTC datetime as expected by google-auth library
                if expiry.tzinfo is not None:
                    expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
                creds.expiry = expiry
            
            # Check if token needs refresh
            if auto_refresh and (creds.expired or self._token_expires_soon(creds)):
                if creds.refresh_token:
                    try:
                        # Update last refresh attempt
                        secret.youtube_last_refresh_attempt = datetime.now(timezone.utc)
                        await self.db.commit()
                        
                        # Refresh the token
                        creds.refresh(Request())
                        
                        # Store updated tokens
                        await self._store_youtube_tokens(secret, creds)
                        
                    except Exception as refresh_error:
                        # If refresh fails, mark as requiring re-auth
                        secret.youtube_authenticated = False
                        await self.db.commit()
                        
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Token refresh failed: {str(refresh_error)}. Please re-authenticate."
                        )
                else:
                    # No refresh token available
                    secret.youtube_authenticated = False
                    await self.db.commit()
                    
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="No refresh token available. Please re-authenticate."
                    )
            
            return creds
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get YouTube credentials: {str(e)}"
            )

    def _token_expires_soon(self, credentials, minutes_before: int = 5) -> bool:
        """
        Check if token expires within the specified minutes.
        
        Args:
            credentials: Google OAuth credentials
            minutes_before: Minutes before expiry to consider "soon"
            
        Returns:
            bool: True if token expires soon
        """
        if not credentials.expiry:
            return False
        
        now = datetime.now(timezone.utc)
        
        # Ensure credentials.expiry is timezone-aware
        expiry = credentials.expiry
        if expiry.tzinfo is None:
            # If timezone-naive, assume UTC
            expiry = expiry.replace(tzinfo=timezone.utc)
        
        expires_soon = expiry - timedelta(minutes=minutes_before)
        
        return now >= expires_soon

    async def refresh_youtube_tokens(self, user_id: UUID, force_refresh: bool = False) -> YouTubeTokenRefreshResponse:
        """
        Manually refresh YouTube tokens.
        
        Args:
            user_id: User ID
            force_refresh: Force refresh even if not expired
            
        Returns:
            YouTubeTokenRefreshResponse: Refresh result
        """
        try:
            secret = await self.get_active_secret(user_id)
            if not secret or not secret.youtube_authenticated:
                return YouTubeTokenRefreshResponse(
                    success=False,
                    message="No YouTube authentication found",
                    requires_reauth=True
                )
            
            # Get current credentials
            creds = await self.get_youtube_credentials(user_id, auto_refresh=False)
            
            # Check if refresh is needed
            if not force_refresh and not (creds.expired or self._token_expires_soon(creds)):
                return YouTubeTokenRefreshResponse(
                    success=True,
                    message="Token is still valid, no refresh needed",
                    new_expires_at=creds.expiry
                )
            
            # Perform refresh
            from google.auth.transport.requests import Request
            
            if not creds.refresh_token:
                secret.youtube_authenticated = False
                await self.db.commit()
                
                return YouTubeTokenRefreshResponse(
                    success=False,
                    message="No refresh token available",
                    requires_reauth=True
                )
            
            try:
                creds.refresh(Request())
                await self._store_youtube_tokens(secret, creds)
                
                return YouTubeTokenRefreshResponse(
                    success=True,
                    message="Token refreshed successfully",
                    new_expires_at=creds.expiry
                )
                
            except Exception as refresh_error:
                secret.youtube_authenticated = False
                await self.db.commit()
                
                return YouTubeTokenRefreshResponse(
                    success=False,
                    message=f"Token refresh failed: {str(refresh_error)}",
                    requires_reauth=True
                )
                
        except Exception as e:
            return YouTubeTokenRefreshResponse(
                success=False,
                message=f"Refresh operation failed: {str(e)}",
                requires_reauth=True
            )

    async def get_youtube_auth_status(self, user_id: UUID) -> YouTubeAuthStatusResponse:
        """
        Get YouTube authentication status.
        
        Args:
            user_id: User ID
            
        Returns:
            YouTubeAuthStatusResponse: Authentication status
        """
        try:
            secret = await self.get_active_secret(user_id)
            
            if not secret or not secret.youtube_authenticated:
                return YouTubeAuthStatusResponse(
                    authenticated=False,
                    requires_reauth=True
                )
            
            # Calculate time until expiry
            expires_in_minutes = None
            if secret.youtube_token_expires_at:
                now = datetime.now(timezone.utc)
                
                # Ensure youtube_token_expires_at is timezone-aware
                expires_at = secret.youtube_token_expires_at
                if expires_at.tzinfo is None:
                    # If timezone-naive, assume UTC
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                
                delta = expires_at - now
                expires_in_minutes = int(delta.total_seconds() / 60) if delta.total_seconds() > 0 else 0
            
            # Parse scopes
            scopes_granted = []
            if secret.youtube_scopes:
                try:
                    scopes_granted = json.loads(secret.youtube_scopes)
                except json.JSONDecodeError:
                    pass
            
            return YouTubeAuthStatusResponse(
                authenticated=True,
                scopes_granted=scopes_granted,
                token_expires_at=secret.youtube_token_expires_at,
                token_expires_in_minutes=expires_in_minutes,
                last_refresh_attempt=secret.youtube_last_refresh_attempt,
                requires_reauth=expires_in_minutes is not None and expires_in_minutes <= 0
            )
            
        except Exception as e:
            return YouTubeAuthStatusResponse(
                authenticated=False,
                requires_reauth=True
            )

    async def get_secret_status(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get secret status summary for user.
        
        Args:
            user_id: User UUID
            
        Returns:
            Dict with secret status information including YouTube auth status
        """
        try:
            # Get all user secrets
            result = await self.db.execute(
                select(Secret).where(Secret.user_id == user_id)
            )
            secrets = result.scalars().all()
            
            if not secrets:
                return {
                    "has_secrets": False,
                    "secret_count": 0,
                    "active_secrets": 0,
                    "latest_upload": None,
                    "has_youtube_auth": False
                }
            
            active_secrets = [s for s in secrets if s.is_active]
            latest_secret = max(secrets, key=lambda s: s.created_at) if secrets else None
            
            # Check if any secret has YouTube authentication
            # Use the same logic as YouTube auth-status: just check access token and youtube_authenticated flag
            has_youtube_auth = any(
                secret.youtube_authenticated and 
                secret.youtube_access_token_encrypted
                for secret in active_secrets
            )
            
            return {
                "has_secrets": len(secrets) > 0,
                "secret_count": len(secrets),
                "active_secrets": len(active_secrets),
                "latest_upload": latest_secret.created_at.isoformat() if latest_secret else None,
                "has_youtube_auth": has_youtube_auth
            }
            
        except Exception as e:
            logger.error(f"Failed to get secret status for user {user_id}: {e}")
            return {
                "has_secrets": False,
                "secret_count": 0,
                "active_secrets": 0,
                "latest_upload": None,
                "has_youtube_auth": False
            } 