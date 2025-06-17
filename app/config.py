"""
Configuration settings for YouTube Shorts Creator API
"""

import os
from typing import List
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
    
    # Application
    app_name: str = "YouTube Shorts Creator API"
    version: str = "1.0.0"
    debug: bool = False
    
    # Database
    database_url: str = "postgresql://user:password@localhost:5432/youtube_shorts"
    
    # File Upload
    max_file_size_mb: int = 100
    upload_directory: str = "./uploads"
    allowed_video_types: List[str] = ["mp4", "mov", "avi", "mkv"]
    allowed_transcript_types: List[str] = ["txt", "md"]
    
    # YouTube API
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""
    
    # OpenAI
    openai_api_key: str = ""
    
    # Security
    secret_key: str = "your-secret-key-change-in-production"
    cors_origins: List[str] = ["http://localhost:3000", "https://yourdomain.com"]
    
    # Background Jobs
    redis_url: str = "redis://localhost:6379"
    job_timeout_minutes: int = 30
    cleanup_interval_hours: int = 24
    
    # File paths
    static_directory: str = "./static"
    temp_directory: str = "./temp"
    
    class Config:
        env_file = get_env_file()
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance."""
    return settings 