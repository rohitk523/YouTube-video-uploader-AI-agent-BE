"""
Configuration settings for YouTube Shorts Creator API
"""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings


def get_env_file() -> str:
    """Get environment file based on ENVIRONMENT variable."""
    environment = os.getenv("ENVIRONMENT", "").lower()
    
    if environment == "development":
        return ".env.dev"
    elif environment == "production":
        return ".env.prod"
    else:
        # Default fallback order
        if os.path.exists(".env.dev"):
            return ".env.dev"
        elif os.path.exists(".env.prod"):
            return ".env.prod"
        else:
            return ".env"


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application (defaults - no env vars needed)
    app_name: str = "YouTube Shorts Creator API"
    version: str = "1.0.0"
    debug: bool = False
    
    # Database (SECRET - requires env var)
    database_url: str = "postgresql://user:password@localhost:5432/youtube_shorts"
    database_echo: bool = False
    
    # API Configuration (defaults - no env vars needed)
    api_version: str = "v1"
    api_title: str = "YouTube Shorts Creator API"
    api_description: str = "AI-powered YouTube Shorts creation and automation"
    
    # File Upload (defaults - no env vars needed)
    max_file_size_mb: int = 500
    upload_directory: str = "./uploads"
    allowed_video_types_str: str = "mp4,mov,avi,mkv"
    allowed_transcript_types_str: str = "txt,md"
    
    # AWS S3 Configuration (SECRETS - require env vars)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    s3_bucket_name: Optional[str] = None
    
    # S3 Settings (defaults - no env vars needed)
    aws_region: str = "us-east-1"
    s3_videos_prefix: str = "videos/"
    s3_transcripts_prefix: str = "transcripts/"
    s3_temp_prefix: str = "temp/"
    s3_processed_prefix: str = "processed/"
    s3_presigned_url_expiry: int = 3600  # 1 hour in seconds
    s3_multipart_threshold: int = 100 * 1024 * 1024  # 100MB
    s3_cleanup_temp_hours: int = 24  # Hours after which temp files are deleted
    
    # OpenAI (SECRET - requires env var)
    openai_api_key: Optional[str] = None
    
    # OpenAI Settings (defaults - no env vars needed)
    openai_tts_model: str = "tts-1"
    openai_default_voice: str = "alloy"
    
    # Langfuse (SECRETS - require env vars)
    langfuse_secret_key: Optional[str] = None
    langfuse_public_key: Optional[str] = None
    
    # Langfuse Settings (defaults - no env vars needed)
    langfuse_host: str = "https://cloud.langfuse.com"
    
    # Security (SECRET - requires env var)
    secret_key: str = "your-secret-key-change-this-in-production"
    
    # Security Settings (defaults - no env vars needed)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    cors_origins_str: str = "http://localhost:3000,https://yourdomain.com,https://rohitk523.github.io,http://youtube.codewithrk.in,https://youtube.codewithrk.in"
    
    # Background Jobs (SECRETS - require env vars)
    redis_url: Optional[str] = None
    redis_password: Optional[str] = None
    
    # Background Job Settings (defaults - no env vars needed)
    job_timeout_minutes: int = 30
    cleanup_interval_hours: int = 24
    
    # File paths (defaults - no env vars needed)
    static_directory: str = "./static"
    temp_directory: str = "./temp"
    
    @property
    def allowed_video_types(self) -> List[str]:
        """Get allowed video types as a list."""
        return [ext.strip() for ext in self.allowed_video_types_str.split(',') if ext.strip()]
    
    @property
    def allowed_transcript_types(self) -> List[str]:
        """Get allowed transcript types as a list."""
        return [ext.strip() for ext in self.allowed_transcript_types_str.split(',') if ext.strip()]
    
    @property 
    def cors_origins(self) -> List[str]:
        """Get CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins_str.split(',') if origin.strip()]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return not self.debug
    
    @property
    def s3_configured(self) -> bool:
        """Check if S3 is properly configured."""
        return bool(
            self.aws_access_key_id and 
            self.aws_secret_access_key and 
            self.s3_bucket_name
        )
    
    @property
    def openai_configured(self) -> bool:
        """Check if OpenAI is properly configured."""
        return bool(self.openai_api_key)
    
    @property
    def redis_configured(self) -> bool:
        """Check if Redis is properly configured."""
        return bool(self.redis_url)
    
    @property
    def langfuse_configured(self) -> bool:
        """Check if Langfuse is properly configured."""
        return bool(self.langfuse_secret_key and self.langfuse_public_key)

    class Config:
        env_file = get_env_file()
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in environment file


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get settings instance (singleton pattern).
    
    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """
    Reload settings from environment (useful for testing).
    
    Returns:
        New settings instance
    """
    global _settings
    _settings = Settings()
    return _settings


def get_settings_for_production() -> Settings:
    """Get settings instance for production environment."""
    settings = get_settings()
    if not settings.is_production:
        raise ValueError("This function should only be called in production environment")
    return settings


def get_settings_for_development() -> Settings:
    """Get settings instance for development environment."""
    settings = get_settings()
    if settings.is_production:
        raise ValueError("This function should not be called in production environment")
    return settings


def get_database_url(async_driver: bool = True) -> str:
    """
    Get database URL with appropriate driver.
    
    Args:
        async_driver: Whether to use async driver
        
    Returns:
        Database URL with correct driver
    """
    settings = get_settings()
    if async_driver and not settings.database_url.startswith("postgresql+asyncpg://"):
        return settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
    elif not async_driver and settings.database_url.startswith("postgresql+asyncpg://"):
        return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return settings.database_url


def get_cors_origins_list() -> List[str]:
    """
    Get CORS origins as a list.
    
    Returns:
        List of CORS origins
    """
    settings = get_settings()
    if isinstance(settings.cors_origins, str):
        return [origin.strip() for origin in settings.cors_origins.split(",")]
    return settings.cors_origins


def validate_required_for_production() -> List[str]:
    """
    Validate required settings for production.
    
    Returns:
        List of missing required settings
    """
    settings = get_settings()
    missing = []
    
    if settings.is_production:
        if settings.secret_key == "your-secret-key-change-this-in-production":
            missing.append("SECRET_KEY must be set in production")
        
        if not settings.s3_configured:
            missing.append("S3 configuration (AWS credentials and bucket) required in production")
        
        if not settings.openai_configured:
            missing.append("OpenAI API key required for TTS functionality")
    
    return missing


def is_production() -> bool:
    """Check if running in production environment."""
    settings = get_settings()
    return not settings.debug and not settings.testing


def s3_configured() -> bool:
    """Check if S3 is properly configured."""
    settings = get_settings()
    return bool(
        settings.aws_access_key_id and 
        settings.aws_secret_access_key and 
        settings.s3_bucket_name
    )


def openai_configured() -> bool:
    """Check if OpenAI is properly configured."""
    settings = get_settings()
    return bool(settings.openai_api_key)


def redis_configured() -> bool:
    """Check if Redis is properly configured."""
    settings = get_settings()
    return bool(settings.redis_url) 