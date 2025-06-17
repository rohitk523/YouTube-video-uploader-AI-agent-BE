"""
Authentication schemas for OAuth 2.0 implementation
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# Token schemas
class Token(BaseModel):
    """OAuth 2.0 token response schema."""
    
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    scope: Optional[str] = None


class TokenData(BaseModel):
    """Token payload data."""
    
    user_id: UUID
    email: str
    username: Optional[str] = None
    scopes: list[str] = []


# User authentication schemas
class UserRegister(BaseModel):
    """User registration schema."""
    
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)


class UserLogin(BaseModel):
    """User login schema."""
    
    email: EmailStr
    password: str


class UserProfile(BaseModel):
    """User profile schema."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    email: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    profile_picture_url: Optional[str] = None
    provider: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None


class UserUpdate(BaseModel):
    """User profile update schema."""
    
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    profile_picture_url: Optional[str] = None


class PasswordChange(BaseModel):
    """Password change schema."""
    
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)


class PasswordReset(BaseModel):
    """Password reset request schema."""
    
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation schema."""
    
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)


# OAuth 2.0 specific schemas
class OAuth2AuthorizationCode(BaseModel):
    """OAuth 2.0 authorization code flow schema."""
    
    code: str
    state: Optional[str] = None
    redirect_uri: str


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""
    
    refresh_token: str


# Response schemas
class AuthResponse(BaseModel):
    """Authentication response schema."""
    
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    user: UserProfile


class MessageResponse(BaseModel):
    """Generic message response schema."""
    
    message: str
    detail: Optional[str] = None 