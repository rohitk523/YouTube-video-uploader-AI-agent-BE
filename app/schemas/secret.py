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


class SecretUploadRequest(BaseModel):
    """Schema for secret upload request."""
    
    filename: str = Field(..., description="Original filename")
    file_content: str = Field(..., description="Base64 encoded file content")
    
    @validator('filename')
    def validate_filename(cls, v):
        """Validate filename format."""
        if not v.endswith('.json'):
            raise ValueError("File must be a JSON file")
        return v


class SecretResponse(BaseModel):
    """Schema for secret response."""
    
    id: UUID
    user_id: UUID
    project_id: str
    is_active: bool
    is_verified: bool
    original_filename: str
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None
    
    # Non-sensitive configuration
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    redirect_uris: Optional[List[str]] = None
    
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


class SecretValidationResponse(BaseModel):
    """Schema for secret validation response."""
    
    valid: bool
    project_id: Optional[str] = None
    client_id_preview: Optional[str] = None  # First 10 chars for preview
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class SecretUploadResponse(BaseModel):
    """Schema for successful secret upload response."""
    
    id: UUID
    message: str
    secret: SecretResponse


class SecretStatusResponse(BaseModel):
    """Schema for checking if user has uploaded secrets."""
    
    has_secrets: bool
    secret_count: int
    active_secrets: int
    latest_upload: Optional[datetime] = None 