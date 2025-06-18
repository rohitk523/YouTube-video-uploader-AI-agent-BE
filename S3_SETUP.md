# S3 Storage Implementation

This document explains the S3 storage implementation for the YouTube Shorts Creator API.

## Overview

The API now uses AWS S3 for file storage instead of local storage. This provides:

- **Scalable storage**: No local disk space limitations
- **Temporary file management**: Automatic cleanup of temporary files
- **Better performance**: Presigned URLs for direct S3 downloads
- **Reliability**: AWS S3's high availability and durability

## Configuration

### Environment Variables

Add these S3 configuration variables to your environment file:

```env
# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name
S3_VIDEOS_PREFIX=videos/
S3_TRANSCRIPTS_PREFIX=transcripts/
S3_TEMP_PREFIX=temp/
S3_PROCESSED_PREFIX=processed/

# S3 Settings
S3_PRESIGNED_URL_EXPIRY=3600
S3_MULTIPART_THRESHOLD=104857600
S3_CLEANUP_TEMP_HOURS=24
```

### AWS Setup

1. Create an S3 bucket in your AWS account
2. Create an IAM user with S3 access permissions
3. Add the access keys to your environment configuration

Required S3 permissions:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
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

## API Changes

### New Upload Endpoints

1. **Upload Video**: `POST /api/upload/video?is_temp=true`
   - Uploads video to S3 temp storage by default
   - Returns upload ID for job creation

2. **Upload Transcript Text**: `POST /api/upload/transcript-text?is_temp=true`
   - Uploads transcript content to S3 as text file
   - Returns upload ID for job creation

3. **Upload Transcript File**: `POST /api/upload/transcript-file?is_temp=true`
   - Uploads transcript file to S3
   - Returns upload ID for job creation

### New File Management Endpoints

1. **Download File**: `GET /api/upload/{upload_id}/download?use_presigned=true`
   - Returns presigned URL for direct S3 download (recommended)
   - Or streams file content directly

2. **Move to Permanent**: `POST /api/upload/{upload_id}/move-to-permanent`
   - Moves file from temp to permanent storage

3. **Cleanup Temp Files**: `POST /api/upload/cleanup-temp?hours=24`
   - Removes temporary files older than specified hours

4. **Upload Statistics**: `GET /api/upload/stats/overview`
   - Returns upload statistics and S3 usage info

### Updated Job Creation

Jobs now support upload IDs instead of direct file paths:

```json
{
    "title": "My Video Title",
    "description": "Video description",
    "voice": "alloy",
    "tags": ["shorts", "ai"],
    "video_upload_id": "uuid-of-uploaded-video",
    "transcript_upload_id": "uuid-of-uploaded-transcript"
}
```

OR with direct transcript content:

```json
{
    "title": "My Video Title",
    "description": "Video description", 
    "voice": "alloy",
    "tags": ["shorts", "ai"],
    "video_upload_id": "uuid-of-uploaded-video",
    "transcript_content": "Direct transcript text..."
}
```

## Workflow

### 1. Upload Files

```bash
# Upload video file
curl -X POST "http://localhost:8000/api/upload/video?is_temp=true" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@video.mp4"

# Upload transcript
curl -X POST "http://localhost:8000/api/upload/transcript-text?is_temp=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "This is my transcript content..."}'
```

### 2. Create Job

```bash
curl -X POST "http://localhost:8000/api/jobs/create" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "My Video",
    "video_upload_id": "video-upload-uuid",
    "transcript_upload_id": "transcript-upload-uuid"
  }'
```

### 3. Process and Upload to YouTube

The job will:
1. Download files from S3 temp storage
2. Process video and generate audio
3. Upload processed files to S3 processed storage
4. Upload final video to YouTube
5. Optionally clean up temp files after successful upload

### 4. Cleanup (Optional)

```bash
# Move important files to permanent storage
curl -X POST "http://localhost:8000/api/upload/{upload_id}/move-to-permanent" \
  -H "Authorization: Bearer $TOKEN"

# Clean up old temp files
curl -X POST "http://localhost:8000/api/upload/cleanup-temp?hours=24" \
  -H "Authorization: Bearer $TOKEN"
```

## Storage Structure

S3 bucket organization:
```
your-bucket/
├── temp/           # Temporary uploads (auto-deleted)
│   ├── video-uuid.mp4
│   └── transcript-uuid.txt
├── videos/         # Permanent video storage
│   └── video-uuid.mp4
├── transcripts/    # Permanent transcript storage
│   └── transcript-uuid.txt
└── processed/      # Processed files from jobs
    ├── processed-video-uuid.mp4
    ├── audio-uuid.mp3
    └── final-video-uuid.mp4
```

## Benefits

1. **No Local Storage**: Files are stored in S3, not on the server
2. **Automatic Cleanup**: Temporary files are automatically removed
3. **Scalability**: S3 handles large files and high throughput
4. **Presigned URLs**: Direct download links without server load
5. **Job Tracking**: Upload IDs link files to processing jobs
6. **Flexibility**: Option to keep files in S3 permanently or delete after YouTube upload

## Dependencies

The implementation uses:
- `boto3`: AWS SDK for Python
- `botocore`: Low-level AWS SDK
- `FastAPI`: For async file handling
- `SQLAlchemy`: For tracking upload metadata 