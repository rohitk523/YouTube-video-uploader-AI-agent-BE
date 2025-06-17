"""
Authentication service for OAuth 2.0 implementation
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.schemas.auth import TokenData, UserRegister, UserProfile, UserUpdate

settings = get_settings()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


class AuthService:
    """Authentication service for user management and JWT tokens."""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a plain password against its hash.
        
        Args:
            plain_password: Plain text password
            hashed_password: Hashed password from database
            
        Returns:
            bool: True if password matches
        """
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """
        Hash a password.
        
        Args:
            password: Plain text password
            
        Returns:
            str: Hashed password
        """
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(
        data: dict, 
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create JWT access token.
        
        Args:
            data: Token payload data
            expires_delta: Token expiration time
            
        Returns:
            str: JWT access token
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "type": "access"})
        
        return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    
    @staticmethod
    def create_refresh_token(data: dict) -> str:
        """
        Create JWT refresh token.
        
        Args:
            data: Token payload data
            
        Returns:
            str: JWT refresh token
        """
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        
        return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    
    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> Optional[TokenData]:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token string
            token_type: Expected token type ("access" or "refresh")
            
        Returns:
            Optional[TokenData]: Token data if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
            
            # Check token type
            if payload.get("type") != token_type:
                return None
            
            # Extract user data
            user_id: str = payload.get("sub")
            email: str = payload.get("email")
            username: Optional[str] = payload.get("username")
            scopes: list[str] = payload.get("scopes", [])
            
            if user_id is None or email is None:
                return None
            
            return TokenData(
                user_id=UUID(user_id),
                email=email,
                username=username,
                scopes=scopes
            )
        except JWTError:
            return None
    
    @staticmethod
    async def authenticate_user(
        db: AsyncSession, 
        email: str, 
        password: str
    ) -> Optional[User]:
        """
        Authenticate user with email and password.
        
        Args:
            db: Database session
            email: User email
            password: Plain text password
            
        Returns:
            Optional[User]: User if authenticated, None otherwise
        """
        result = await db.execute(
            select(User).where(
                User.email == email,
                User.is_active == True
            )
        )
        user = result.scalar_one_or_none()
        
        if not user or not AuthService.verify_password(password, user.hashed_password):
            return None
        
        # Update last login
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(last_login_at=datetime.now(timezone.utc))
        )
        await db.commit()
        
        return user
    
    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """
        Get user by email.
        
        Args:
            db: Database session
            email: User email
            
        Returns:
            Optional[User]: User if found, None otherwise
        """
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
        """
        Get user by ID.
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            Optional[User]: User if found, None otherwise
        """
        result = await db.execute(
            select(User).where(
                User.id == user_id,
                User.is_active == True
            )
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """
        Get user by username.
        
        Args:
            db: Database session
            username: Username
            
        Returns:
            Optional[User]: User if found, None otherwise
        """
        result = await db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserRegister) -> User:
        """
        Create new user.
        
        Args:
            db: Database session
            user_data: User registration data
            
        Returns:
            User: Created user
        """
        hashed_password = AuthService.get_password_hash(user_data.password)
        
        user = User(
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            is_active=True,
            is_verified=False  # Email verification required
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        return user
    
    @staticmethod
    def generate_tokens(user: User, scopes: list[str] = None) -> tuple[str, str]:
        """
        Generate access and refresh tokens for user.
        
        Args:
            user: User object
            scopes: List of scopes to include in token
            
        Returns:
            tuple[str, str]: Access token and refresh token
        """
        if scopes is None:
            scopes = ["read", "write"] if user.is_active else ["read"]
            
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "username": user.username,
            "scopes": scopes
        }
        
        access_token = AuthService.create_access_token(token_data)
        refresh_token = AuthService.create_refresh_token(token_data)
        
        return access_token, refresh_token
    
    @staticmethod
    def generate_password_reset_token() -> str:
        """
        Generate secure password reset token.
        
        Returns:
            str: Password reset token
        """
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def generate_auth_code(user: User, client_id: str, scopes: list[str]) -> str:
        """
        Generate OAuth 2.0 authorization code.
        
        In production, this should be stored with expiration and one-time use.
        
        Args:
            user: User object
            client_id: OAuth client ID
            scopes: Granted scopes
            
        Returns:
            str: Authorization code
        """
        # Create short-lived authorization code
        code_data = {
            "sub": str(user.id),
            "client_id": client_id,
            "scopes": scopes,
            "type": "auth_code"
        }
        
        # Authorization code expires in 10 minutes
        expires_delta = timedelta(minutes=10)
        return AuthService.create_access_token(code_data, expires_delta)
    
    @staticmethod
    async def update_user_password(
        db: AsyncSession,
        user_id: UUID,
        new_password: str
    ) -> bool:
        """
        Update user password.
        
        Args:
            db: Database session
            user_id: User ID
            new_password: New plain text password
            
        Returns:
            bool: True if successful
        """
        hashed_password = AuthService.get_password_hash(new_password)
        
        result = await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(hashed_password=hashed_password, updated_at=datetime.now(timezone.utc))
        )
        
        await db.commit()
        return result.rowcount > 0
    
    @staticmethod
    async def update_user(
        db: AsyncSession,
        user_id: UUID,
        user_update: UserUpdate
    ) -> User:
        """
        Update user profile.
        
        Args:
            db: Database session
            user_id: User ID
            user_update: User update data
            
        Returns:
            User: Updated user
            
        Raises:
            Exception: If update fails
        """
        update_data = user_update.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(**update_data)
        )
        await db.commit()
        
        # Return updated user
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one()
    
    @staticmethod
    async def update_password(
        db: AsyncSession,
        user_id: UUID,
        new_password: str
    ) -> bool:
        """
        Update user password.
        
        Args:
            db: Database session
            user_id: User ID
            new_password: New plain text password
            
        Returns:
            bool: True if successful
        """
        hashed_password = AuthService.get_password_hash(new_password)
        
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                hashed_password=hashed_password,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await db.commit()
        
        return True 