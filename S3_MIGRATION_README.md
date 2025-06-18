# S3 Storage Migration Guide

This document outlines the migration from local file storage to AWS S3 bucket storage for the YouTube Shorts Creator API.

## Overview

The system has been migrated from local file storage to AWS S3 bucket storage to provide:
- Scalable cloud storage
- Better file management for temporary and permanent files
- Improved performance and reliability
- Cost-effective storage with automatic cleanup

## Key Changes

### 1. Storage Architecture
- **Before**: Files stored locally on server filesystem
- **After**: Files stored in AWS S3 bucket with organized prefixes:
  - `videos/` - Permanent video files
  - `transcripts/` - Permanent transcript files
  - `temp/` - Temporary files (auto-cleaned after 24 hours)
  - `processed/` - Processed video/audio files

### 2. Upload Workflow
1. **Video Upload**: Upload video to S3 with temporary flag
2. **Transcript Upload**: Upload transcript file or text to S3 with temporary flag
3. **Job Creation**: Reference upload IDs instead of file paths
4. **Processing**: Download from S3, process, upload results back to S3
5. **Cleanup**: Automatically delete temporary files after YouTube upload

### 3. New API Endpoints

#### Upload Endpoints
- `POST /api/upload/video?is_temp=true` - Upload video to S3
- `POST /api/upload/transcript-text?is_temp=true` - Upload transcript text to S3
- `POST /api/upload/transcript-file?is_temp=true` - Upload transcript file to S3
- `GET /api/upload/{upload_id}/download` - Download file via presigned URL
- `POST /api/upload/{upload_id}/move-to-permanent` - Move temp file to permanent storage
- `POST /api/upload/cleanup-temp?hours=24` - Cleanup temporary files
- `GET /api/upload/stats/overview` - Get upload statistics

#### Job Creation
```json
{
  "title": "My YouTube Short",
  "description": "Description here",
  "voice": "alloy",
  "tags": ["shorts", "ai"],
  "video_upload_id": "uuid-of-video-upload",
  "transcript_upload_id": "uuid-of-transcript-upload"
}
```

## Configuration

### Required Environment Variables

```bash
# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name

# S3 Storage Prefixes
S3_VIDEOS_PREFIX=videos/
S3_TRANSCRIPTS_PREFIX=transcripts/
S3_TEMP_PREFIX=temp/
S3_PROCESSED_PREFIX=processed/

# S3 Settings
S3_PRESIGNED_URL_EXPIRY=3600
S3_MULTIPART_THRESHOLD=104857600
S3_CLEANUP_TEMP_HOURS=24
```

### AWS S3 Bucket Setup

1. **Create S3 Bucket**:
   ```bash
   aws s3 mb s3://your-bucket-name
   ```

2. **Set Bucket Policy** (example):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {"AWS": "arn:aws:iam::ACCOUNT:user/youtube-shorts-user"},
         "Action": [
           "s3:GetObject",
           "s3:PutObject",
           "s3:DeleteObject",
           "s3:ListBucket"
         ],
         "Resource": [
           "arn:aws:s3:::your-bucket-name",
           "arn:aws:s3:::your-bucket-name/*"
         ]
       }
     ]
   }
   ```

3. **Configure Lifecycle Rules** (optional):
   - Automatically delete files in `temp/` prefix after 1 day
   - Move files to cheaper storage classes after 30 days

## Migration Steps

### 1. Install Dependencies
```bash
pip install boto3==1.34.0 botocore==1.34.0
```

### 2. Run Database Migration
```bash
python migration_add_s3_support.py migrate
```

### 3. Update Environment Variables
Add S3 configuration to your `.env` file.

### 4. Test S3 Connection
```python
from app.services.s3_service import S3Service

s3_service = S3Service()
# This will validate credentials and bucket access
```

## Usage Examples

### 1. Upload Video and Create Job
```python
# 1. Upload video
video_response = await upload_video(video_file, is_temp=True)
video_upload_id = video_response.id

# 2. Upload transcript
transcript_response = await upload_transcript_text({
    "content": "Your transcript content here"
}, is_temp=True)
transcript_upload_id = transcript_response.id

# 3. Create job
job_response = await create_job({
    "title": "My Video",
    "description": "Video description",
    "voice": "alloy",
    "tags": ["ai", "shorts"],
    "video_upload_id": video_upload_id,
    "transcript_upload_id": transcript_upload_id
})
```

### 2. Download Files
```python
# Get presigned URL (recommended)
download_url = await get_presigned_download_url(upload_id)

# Or direct download (for small files)
file_content = await get_file_content(upload_id)
```

### 3. Cleanup Temporary Files
```python
# Manual cleanup
cleanup_result = await cleanup_temp_files(hours=24)

# Automatic cleanup (runs in background)
# Files older than S3_CLEANUP_TEMP_HOURS are automatically deleted
```

## File Lifecycle

1. **Upload**: Files uploaded with `is_temp=true` flag
2. **Processing**: Jobs reference upload IDs, system downloads files for processing
3. **Results**: Processed files uploaded to S3 with permanent storage
4. **Cleanup**: After successful YouTube upload:
   - Temporary input files are deleted
   - Processed files can be kept or deleted based on configuration
   - Original files moved to permanent storage if needed

## Monitoring and Maintenance

### 1. Storage Statistics
```bash
curl -X GET "/api/upload/stats/overview" \
  -H "Authorization: Bearer $TOKEN"
```

### 2. Manual Cleanup
```bash
curl -X POST "/api/upload/cleanup-temp?hours=24" \
  -H "Authorization: Bearer $TOKEN"
```

### 3. S3 Monitoring
Monitor your S3 bucket for:
- Storage usage
- Request costs
- Failed uploads
- Lifecycle rule effectiveness

## Troubleshooting

### Common Issues

1. **AWS Credentials Error**:
   - Check `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
   - Verify IAM permissions

2. **Bucket Access Denied**:
   - Check bucket policy
   - Verify bucket exists in correct region

3. **Upload Failures**:
   - Check file size limits
   - Verify network connectivity
   - Check S3 bucket permissions

### Error Handling

The system includes comprehensive error handling:
- Failed uploads are automatically cleaned up
- Database rollback on S3 upload failures
- Graceful fallback for missing files
- Detailed error logging

## Backward Compatibility

The migration maintains backward compatibility:
- Legacy `file_path` field is preserved
- Old endpoints continue to work
- Gradual migration of existing data possible

## Performance Optimizations

- **Presigned URLs**: Reduce server load for file downloads
- **Multipart Uploads**: Handle large files efficiently
- **Connection Pooling**: Optimize S3 client performance
- **Async Operations**: Non-blocking file operations

## Security Considerations

- **IAM Roles**: Use least-privilege access
- **Presigned URL Expiry**: Short-lived download URLs
- **Encryption**: Enable S3 encryption at rest
- **Access Logging**: Monitor bucket access

## Cost Optimization

- **Lifecycle Rules**: Automatically transition to cheaper storage
- **Intelligent Tiering**: Automatic cost optimization
- **Regular Cleanup**: Remove temporary files promptly
- **Monitoring**: Track storage costs and usage patterns

## Next Steps

1. Monitor S3 usage and costs
2. Implement additional lifecycle rules
3. Consider CDN for frequently accessed files
4. Optimize upload/download performance
5. Add more comprehensive monitoring and alerting 