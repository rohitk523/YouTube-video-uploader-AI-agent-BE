"""
Pydantic schemas for secret management
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, validator


class YouTubeOAuthJSON(BaseModel):
    """Schema for validating YouTube OAuth JSON file structure."""
    
    web: Dict[str, Any] = Field(..., description="Web client configuration")
    
    @validator('web')
    def validate_web_config(cls, v):
        """Validate web configuration contains required fields."""
        required_fields = [
            'client_id', 'client_secret', 'project_id',
            'auth_uri', 'token_uri', 'auth_provider_x509_cert_url'
        ]
        
        for field in required_fields:
            if field not in v:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate client_id format (should be Google OAuth client ID)
        client_id = v.get('client_id', '')
        if not client_id.endswith('.apps.googleusercontent.com'):
            raise ValueError("Invalid client_id format. Must be a Google OAuth client ID")
        
        # Validate project_id
        project_id = v.get('project_id', '')
        if not project_id or len(project_id) < 5:
            raise ValueError("Invalid project_id")
        
        # Validate client_secret format
        client_secret = v.get('client_secret', '')
        if not client_secret.startswith('GOCSPX-'):
            raise ValueError("Invalid client_secret format")
        
        return v


class SecretValidationResponse(BaseModel):
    """Schema for secret validation response."""
    
    valid: bool = Field(..., description="Whether the secret is valid")
    errors: List[str] = Field(default_factory=list, description="List of validation errors")
    warnings: List[str] = Field(default_factory=list, description="List of validation warnings")
    project_id: Optional[str] = Field(None, description="Project ID from the OAuth file")
    client_id_preview: Optional[str] = Field(None, description="Preview of client ID")


class SecretResponse(BaseModel):
    """Schema for secret response."""
    
    id: UUID
    user_id: UUID
    project_id: str
    is_active: bool
    is_verified: bool
    youtube_authenticated: bool = Field(default=False, description="Whether YouTube OAuth is completed")
    original_filename: str
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None
    youtube_tokens_updated_at: Optional[datetime] = Field(None, description="When YouTube tokens were last refreshed")
    
    # Non-sensitive configuration
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    redirect_uris: Optional[List[str]] = None
    youtube_scopes: Optional[List[str]] = None
    
    class Config:
        from_attributes = True
    
    @validator('redirect_uris', pre=True)
    def parse_redirect_uris(cls, v):
        """Parse redirect URIs from JSON string."""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v
    
    @validator('youtube_scopes', pre=True)
    def parse_youtube_scopes(cls, v):
        """Parse YouTube scopes from JSON string."""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v


class SecretStatusResponse(BaseModel):
    """Schema for secret status response."""
    
    has_secrets: bool = Field(..., description="Whether user has any OAuth credentials")
    active_secrets: int = Field(..., description="Number of active OAuth credential sets")
    youtube_authenticated: bool = Field(default=False, description="Whether YouTube OAuth is completed")
    requires_youtube_auth: bool = Field(default=True, description="Whether user needs to complete YouTube OAuth")
    project_id: Optional[str] = Field(None, description="Current active project ID")
    last_updated: Optional[datetime] = Field(None, description="When credentials were last updated")
    youtube_tokens_expires_at: Optional[datetime] = Field(None, description="When YouTube tokens expire")


class SecretUploadRequest(BaseModel):
    """Schema for secret upload request."""
    
    filename: str = Field(..., description="Original filename")
    file_content: str = Field(..., description="Base64 encoded file content")


class SecretUploadResponse(BaseModel):
    """Schema for secret upload response."""
    
    id: UUID
    message: str
    secret: SecretResponse


# NEW SCHEMAS FOR YOUTUBE OAUTH FLOW

class YouTubeOAuthInitRequest(BaseModel):
    """Schema for initiating YouTube OAuth flow."""
    
    scopes: Optional[List[str]] = Field(
        default=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube"
        ],
        description="OAuth scopes to request"
    )
    state: Optional[str] = Field(None, description="State parameter for OAuth security")


class YouTubeOAuthInitResponse(BaseModel):
    """Schema for YouTube OAuth initialization response."""
    
    authorization_url: str = Field(..., description="URL to redirect user for OAuth authorization")
    state: str = Field(..., description="State parameter for verification")


class YouTubeOAuthCallbackRequest(BaseModel):
    """Schema for YouTube OAuth callback handling."""
    
    code: str = Field(..., description="Authorization code from YouTube")
    state: Optional[str] = Field(None, description="State parameter for verification")


class YouTubeOAuthCallbackResponse(BaseModel):
    """Schema for YouTube OAuth callback response."""
    
    success: bool = Field(..., description="Whether OAuth flow completed successfully")
    message: str = Field(..., description="Status message")
    youtube_authenticated: bool = Field(..., description="Whether user is now authenticated with YouTube")
    scopes_granted: List[str] = Field(default_factory=list, description="Scopes granted by user")
    expires_at: Optional[datetime] = Field(None, description="When the access token expires")


class YouTubeTokenRefreshRequest(BaseModel):
    """Schema for manual YouTube token refresh."""
    
    force_refresh: bool = Field(default=False, description="Force refresh even if token is not expired")


class YouTubeTokenRefreshResponse(BaseModel):
    """Schema for YouTube token refresh response."""
    
    success: bool = Field(..., description="Whether token refresh was successful")
    message: str = Field(..., description="Status message")
    new_expires_at: Optional[datetime] = Field(None, description="New token expiry time")
    requires_reauth: bool = Field(default=False, description="Whether user needs to re-authenticate")


class YouTubeAuthStatusResponse(BaseModel):
    """Schema for YouTube authentication status."""
    
    authenticated: bool = Field(..., description="Whether user is authenticated with YouTube")
    scopes_granted: List[str] = Field(default_factory=list, description="Currently granted scopes")
    token_expires_at: Optional[datetime] = Field(None, description="When access token expires")
    token_expires_in_minutes: Optional[int] = Field(None, description="Minutes until token expires")
    last_refresh_attempt: Optional[datetime] = Field(None, description="Last token refresh attempt")
    requires_reauth: bool = Field(default=False, description="Whether re-authentication is required") 