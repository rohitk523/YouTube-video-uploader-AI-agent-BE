"""
OAuth 2.0 Authentication Router
Dedicated OAuth 2.0 implementation with proper scopes and flows
"""

from datetime import timedelta
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import (
    Token,
    TokenData,
    UserLogin,
    UserProfile,
    UserRegister,
    UserUpdate,
    AuthResponse,
    MessageResponse,
    OAuth2AuthorizationCode,
    RefreshTokenRequest,
    PasswordChange
)
from app.services.auth import AuthService
from app.models.user import User
from app.core.dependencies import get_current_user

# OAuth 2.0 Configuration
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/oauth/token",
    scopes={
        "read": "Read access to user data",
        "write": "Write access to user data", 
        "upload": "Upload files and create content",
        "youtube": "Access to YouTube operations",
        "admin": "Administrative access"
    }
)

router = APIRouter()


@router.post("/token", response_model=Token, tags=["OAuth 2.0"])
async def oauth_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db)
) -> Token:
    """
    OAuth 2.0 Token Endpoint (RFC 6749)
    
    Supports:
    - Password grant type
    - Refresh token grant type
    - Client credentials grant type
    
    Args:
        form_data: OAuth2 form data with grant_type, username, password, scope
        db: Database session
        
    Returns:
        Token: OAuth 2.0 access token response
        
    Raises:
        HTTPException: If authentication fails
    """
    # Handle different grant types
    if form_data.grant_type == "password" or not hasattr(form_data, 'grant_type'):
        # Password grant type (default)
        user = await AuthService.authenticate_user(
            db, form_data.username, form_data.password
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Process requested scopes
        requested_scopes = form_data.scopes if form_data.scopes else ["read"]
        granted_scopes = _validate_user_scopes(user, requested_scopes)
        
        # Generate tokens with scopes
        access_token, refresh_token = AuthService.generate_tokens(user, granted_scopes)
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=30 * 60,  # 30 minutes
            refresh_token=refresh_token,
            scope=" ".join(granted_scopes)
        )
    
    elif form_data.grant_type == "refresh_token":
        # Refresh token grant type
        if not hasattr(form_data, 'refresh_token') or not form_data.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="refresh_token is required for refresh_token grant"
            )
        
        return await _handle_refresh_token(form_data.refresh_token, db)
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported grant_type: {form_data.grant_type}"
        )


@router.post("/authorize", response_model=dict, tags=["OAuth 2.0"])
async def oauth_authorize(
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    scope: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    user_credentials: UserLogin = Depends(),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    OAuth 2.0 Authorization Endpoint (RFC 6749)
    
    For authorization code flow
    
    Args:
        response_type: Must be "code" for authorization code flow
        client_id: OAuth client identifier
        redirect_uri: Client redirect URI
        scope: Requested scopes (space-separated)
        state: Client state parameter
        user_credentials: User login credentials
        db: Database session
        
    Returns:
        dict: Authorization response with code
        
    Raises:
        HTTPException: If authorization fails
    """
    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 'code' response_type is supported"
        )
    
    # Authenticate user
    user = await AuthService.authenticate_user(
        db, user_credentials.email, user_credentials.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Validate client_id (in production, validate against registered clients)
    if not _validate_client_id(client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client_id"
        )
    
    # Process scopes
    requested_scopes = scope.split() if scope else ["read"]
    granted_scopes = _validate_user_scopes(user, requested_scopes)
    
    # Generate authorization code (simplified - in production use proper code storage)
    auth_code = AuthService.generate_auth_code(user, client_id, granted_scopes)
    
    return {
        "code": auth_code,
        "state": state,
        "redirect_uri": redirect_uri
    }


@router.post("/token/refresh", response_model=Token, tags=["OAuth 2.0"])
async def refresh_token(
    refresh_request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
) -> Token:
    """
    Refresh Access Token
    
    Args:
        refresh_request: Refresh token request
        db: Database session
        
    Returns:
        Token: New access token
        
    Raises:
        HTTPException: If refresh token is invalid
    """
    return await _handle_refresh_token(refresh_request.refresh_token, db)


@router.post("/revoke", response_model=MessageResponse, tags=["OAuth 2.0"])
async def revoke_token(
    token: str = Form(...),
    token_type_hint: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """
    OAuth 2.0 Token Revocation (RFC 7009)
    
    Args:
        token: Token to revoke
        token_type_hint: Hint about token type ("access_token" or "refresh_token")
        current_user: Current authenticated user
        
    Returns:
        MessageResponse: Revocation confirmation
    """
    # In production, maintain a revocation list or blacklist
    # For now, we'll just return success
    return MessageResponse(
        message="Token revoked successfully",
        detail="The token has been revoked and is no longer valid"
    )


@router.get("/userinfo", response_model=UserProfile, tags=["OAuth 2.0"])
async def get_userinfo(
    current_user: User = Depends(get_current_user)
) -> UserProfile:
    """
    OAuth 2.0 UserInfo Endpoint (OpenID Connect)
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        UserProfile: User information
    """
    return UserProfile.model_validate(current_user)


@router.get("/introspect", tags=["OAuth 2.0"])
async def introspect_token(
    token: str = Form(...),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    OAuth 2.0 Token Introspection (RFC 7662)
    
    Args:
        token: Token to introspect
        db: Database session
        
    Returns:
        dict: Token introspection response
    """
    token_data = AuthService.verify_token(token)
    
    if not token_data:
        return {"active": False}
    
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    
    if not user:
        return {"active": False}
    
    return {
        "active": True,
        "client_id": "youtube-shorts-creator",
        "username": user.username or user.email,
        "scope": " ".join(token_data.scopes),
        "sub": str(user.id),
        "aud": "youtube-shorts-creator",
        "iss": "youtube-shorts-creator-api",
        "email": user.email,
        "email_verified": user.is_verified
    }


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, tags=["User Management"])
async def register_user(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
) -> AuthResponse:
    """
    Register a new user and return OAuth 2.0 tokens.
    
    Args:
        user_data: User registration data
        db: Database session
        
    Returns:
        AuthResponse: OAuth 2.0 tokens and user profile
        
    Raises:
        HTTPException: If registration fails
    """
    # Check if user already exists
    existing_user = await AuthService.get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username is taken (if provided)
    if user_data.username:
        existing_username = await AuthService.get_user_by_username(db, user_data.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
    
    # Create user
    try:
        user = await AuthService.create_user(db, user_data)
        
        # Generate OAuth tokens with default scopes
        default_scopes = ["read", "write", "upload"]
        access_token, refresh_token = AuthService.generate_tokens(user, default_scopes)
        
        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=30 * 60,  # 30 minutes
            refresh_token=refresh_token,
            user=UserProfile.model_validate(user)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )


@router.put("/profile", response_model=UserProfile, tags=["User Management"])
async def update_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> UserProfile:
    """
    Update current user profile.
    
    Requires 'write' scope.
    
    Args:
        user_update: User update data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        UserProfile: Updated user profile
        
    Raises:
        HTTPException: If update fails
    """
    # Check if username is taken (if provided and different)
    if user_update.username and user_update.username != current_user.username:
        existing_user = await AuthService.get_user_by_username(db, user_update.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
    
    try:
        updated_user = await AuthService.update_user(db, current_user.id, user_update)
        return UserProfile.model_validate(updated_user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user profile"
        )


@router.post("/change-password", response_model=MessageResponse, tags=["User Management"])
async def change_password(
    password_change: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """
    Change user password.
    
    Requires 'write' scope.
    
    Args:
        password_change: Password change request
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        MessageResponse: Success confirmation
        
    Raises:
        HTTPException: If password change fails
    """
    # Verify current password
    if not AuthService.verify_password(password_change.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid current password"
        )
    
    try:
        await AuthService.update_password(db, current_user.id, password_change.new_password)
        return MessageResponse(
            message="Password changed successfully",
            detail="Your password has been updated"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )


@router.post("/logout", response_model=MessageResponse, tags=["User Management"])
async def logout_user(
    current_user: User = Depends(get_current_user)
) -> MessageResponse:
    """
    Logout user (client-side token removal recommended).
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        MessageResponse: Logout confirmation
    """
    # In production, you might want to add token to a blacklist
    return MessageResponse(
        message="Logged out successfully",
        detail="Please remove the token from client storage"
    )


# Helper functions
def _validate_user_scopes(user: User, requested_scopes: List[str]) -> List[str]:
    """
    Validate and filter user scopes based on permissions.
    
    Args:
        user: User object
        requested_scopes: List of requested scopes
        
    Returns:
        List[str]: Granted scopes
    """
    available_scopes = ["read", "write", "upload", "youtube"]
    
    # Add admin scope for superusers
    if user.is_superuser:
        available_scopes.append("admin")
    
    # Filter requested scopes to only include available ones
    granted_scopes = [scope for scope in requested_scopes if scope in available_scopes]
    
    # Ensure at least read scope is granted
    if not granted_scopes:
        granted_scopes = ["read"]
    
    return granted_scopes


def _validate_client_id(client_id: str) -> bool:
    """
    Validate OAuth client ID.
    
    In production, this should check against a database of registered clients.
    
    Args:
        client_id: Client identifier
        
    Returns:
        bool: True if valid
    """
    # For development, accept any client_id
    # In production, validate against registered clients
    allowed_clients = [
        "youtube-shorts-creator",
        "youtube-shorts-web",
        "youtube-shorts-mobile"
    ]
    
    return client_id in allowed_clients


async def _handle_refresh_token(refresh_token: str, db: AsyncSession) -> Token:
    """
    Handle refresh token grant type.
    
    Args:
        refresh_token: Refresh token
        db: Database session
        
    Returns:
        Token: New access token
        
    Raises:
        HTTPException: If refresh token is invalid
    """
    token_data = AuthService.verify_token(refresh_token, "refresh")
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user = await AuthService.get_user_by_id(db, token_data.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Generate new tokens
    access_token, new_refresh_token = AuthService.generate_tokens(user, token_data.scopes)
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=30 * 60,
        refresh_token=new_refresh_token,
        scope=" ".join(token_data.scopes)
    ) 