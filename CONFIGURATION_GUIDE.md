# Configuration Management Guide

## Overview

This project follows a **separation of concerns** approach for configuration management:

- **Configuration defaults** are defined in `app/config.py`
- **Secrets and environment-specific values** are stored in environment files (`.env.prod`, `.env.dev`)

## Why This Approach?

### Benefits:
1. **Security**: Only secrets are in environment files, reducing exposure
2. **Maintainability**: Configuration logic is centralized in code
3. **Clarity**: Easy to see what needs to be configured vs. what has sensible defaults
4. **Version Control**: Environment files can be safely committed (with placeholder values)
5. **Deployment**: Simpler deployment with fewer environment variables to manage

### Traditional Problems:
- Too many environment variables cluttering `.env` files
- Mixing secrets with configuration values
- Hard to understand what needs to be configured
- Risk of exposing non-secret configs in environment files

## Configuration Structure

### In `app/config.py` (Defaults)
```python
# Application (defaults - no env vars needed)
app_name: str = "YouTube Shorts Creator API"
version: str = "1.0.0"
debug: bool = False

# File Upload (defaults - no env vars needed)
max_file_size_mb: int = 500
allowed_video_types_str: str = "mp4,mov,avi,mkv"

# S3 Settings (defaults - no env vars needed)
aws_region: str = "us-east-1"
s3_videos_prefix: str = "videos/"
s3_presigned_url_expiry: int = 3600
```

### In `.env.prod` (Secrets Only)
```bash
# Database (SECRET)
DATABASE_URL=postgresql://username:password@host:port/database_name

# AWS S3 (SECRETS)
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
S3_BUCKET_NAME=your_s3_bucket_name

# YouTube API (SECRETS)
YOUTUBE_API_KEY=your_youtube_api_key
YOUTUBE_CLIENT_ID=your_youtube_client_id
YOUTUBE_CLIENT_SECRET=your_youtube_client_secret
```

## Environment Variables Classification

### 🔐 SECRETS (Must be in .env files)
- Database credentials
- API keys (AWS, YouTube, OpenAI, Langfuse)
- JWT secret keys
- OAuth tokens and secrets
- Redis passwords

### ⚙️ CONFIGURATION (Defaults in config.py)
- Application settings (app_name, version, debug)
- File upload limits and types
- S3 prefixes and regions
- YouTube default categories and privacy
- OpenAI model names and voices
- Security algorithms and timeouts
- Background job intervals

### 🔧 ENVIRONMENT OVERRIDES (Optional in .env files)
- Debug mode for development
- Database echo for debugging
- Custom CORS origins
- Environment-specific file paths

## Environment Files

### `.env.prod` (Production)
- Contains only secrets and production-specific values
- Should never be committed to version control
- Use `env.template.prod` as a template

### `.env.dev` (Development)
- Contains development secrets and overrides
- Can be committed with placeholder values
- Use `env.template.dev` as a template

## Migration Guide

### From Old Approach to New Approach

1. **Move configuration defaults to `config.py`**:
   ```python
   # Old: In .env file
   MAX_FILE_SIZE_MB=500
   
   # New: In config.py
   max_file_size_mb: int = 500
   ```

2. **Keep only secrets in environment files**:
   ```bash
   # Keep in .env.prod
   DATABASE_URL=postgresql://user:pass@host:port/db
   AWS_ACCESS_KEY_ID=your_key
   
   # Remove from .env.prod
   MAX_FILE_SIZE_MB=500  # Now in config.py
   ```

3. **Update deployment scripts**:
   - Remove non-secret environment variables
   - Focus on setting only the required secrets

## Best Practices

### For Development:
1. Use `env.template.dev` as starting point
2. Replace placeholder values with actual development credentials
3. Keep development secrets separate from production

### For Production:
1. Use `env.template.prod` as starting point
2. Generate strong, unique secrets for each environment
3. Never commit actual production secrets
4. Use secret management services (AWS Secrets Manager, HashiCorp Vault, etc.)

### For Configuration Changes:
1. Add new configuration options to `config.py` with sensible defaults
2. Only add environment variables for secrets or environment-specific overrides
3. Document new configuration options in this guide

## Validation

The application validates required secrets in production:

```python
def validate_required_for_production() -> List[str]:
    """Validate required settings for production."""
    settings = get_settings()
    missing = []
    
    if settings.is_production:
        if settings.secret_key == "your-secret-key-change-this-in-production":
            missing.append("SECRET_KEY must be set in production")
        
        if not settings.s3_configured:
            missing.append("S3 configuration required in production")
    
    return missing
```

## Security Considerations

1. **Never commit real secrets** to version control
2. **Use strong, unique secrets** for each environment
3. **Rotate secrets regularly** in production
4. **Use secret management services** for production deployments
5. **Validate required secrets** on application startup

## Troubleshooting

### Common Issues:

1. **Missing required secrets**: Check validation output on startup
2. **Configuration not loading**: Verify environment file path and format
3. **Default values not working**: Ensure configuration is properly defined in `config.py`

### Debug Configuration:
```python
from app.config import get_settings

settings = get_settings()
print(f"Debug mode: {settings.debug}")
print(f"S3 configured: {settings.s3_configured}")
print(f"Missing secrets: {validate_required_for_production()}")
``` 