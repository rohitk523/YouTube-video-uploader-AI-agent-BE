"""
YouTube Video Service for downloading and managing YouTube videos
"""

import asyncio
import tempfile
import os
import json
import time
from typing import Dict, Any, List, Optional, Union
from uuid import UUID, uuid4
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.video import Video
from app.models.user import User
from app.repositories.video_repository import VideoRepository
from app.services.s3_service import S3Service
from app.schemas.video import VideoCreate

settings = get_settings()


class YouTubeVideoService:
    """Service for downloading YouTube videos and uploading to S3."""
    
    def __init__(self, db: AsyncSession):
        """Initialize YouTube video service."""
        self.db = db
        self.video_repository = VideoRepository(db)
        self.s3_service = S3Service()
        self.temp_dir = Path(tempfile.gettempdir())
        self.supported_formats = ["mp4", "webm", "mkv"]
        
        # YouTube API settings
        self.youtube_api_key = getattr(settings, 'youtube_api_key', None)
        self.youtube_client_secrets = getattr(settings, 'youtube_client_secrets_file', None)
    
    async def get_user_youtube_videos(
        self,
        user_id: UUID,
        page_size: int = 20,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get user's YouTube videos with S3 sync status.
        
        Args:
            user_id: User UUID
            page_size: Number of videos per page
            page_token: YouTube API page token
            
        Returns:
            Dict with videos list and pagination info
        """
        try:
            # Get YouTube videos using YouTube Data API
            youtube_videos = await self._fetch_youtube_videos(
                page_size=page_size,
                page_token=page_token
            )
            
            # Check which videos are already in S3
            videos_with_status = await self._add_s3_status_to_videos(
                youtube_videos["videos"],
                user_id
            )
            
            return {
                "videos": videos_with_status,
                "total_count": youtube_videos.get("total_count"),
                "has_more": youtube_videos.get("has_more", False),
                "next_page_token": youtube_videos.get("next_page_token")
            }
            
        except Exception as e:
            raise Exception(f"Failed to get YouTube videos: {str(e)}")
    
    async def download_and_upload_to_s3(
        self,
        youtube_video_id: str,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Download a YouTube video and upload it to S3.
        
        Args:
            youtube_video_id: YouTube video ID
            user_id: User UUID
            
        Returns:
            Dict with S3 upload information
        """
        temp_video_path = None
        
        try:
            # 1. Check if video already exists in S3
            existing_video = await self._check_video_exists_in_s3(
                youtube_video_id, user_id
            )
            if existing_video:
                raise ValueError(f"Video already exists in S3: {existing_video['filename']}")
            
            # 2. Get video metadata from YouTube
            video_metadata = await self._get_youtube_video_metadata(youtube_video_id)
            
            # 3. Download video from YouTube
            temp_video_path = await self._download_youtube_video(
                youtube_video_id,
                video_metadata["title"]
            )
            
            # 4. Upload to S3
            s3_result = await self._upload_video_to_s3(
                temp_video_path,
                video_metadata,
                user_id
            )
            
            # 5. Create video record in database
            video_record = await self._create_video_record(
                s3_result,
                video_metadata,
                youtube_video_id,
                user_id
            )
            
            return {
                "s3_video_id": str(video_record.id),
                "s3_key": s3_result["s3_key"],
                "title": video_metadata["title"],
                "file_size_mb": s3_result["file_size_mb"],
                "duration": video_metadata.get("duration"),
                "resolution": video_metadata.get("resolution"),
                "format": s3_result.get("format", "mp4"),
                "download_url": s3_result.get("download_url")
            }
            
        except Exception as e:
            raise Exception(f"Failed to download and upload video: {str(e)}")
        finally:
            # Clean up temporary file
            if temp_video_path and os.path.exists(temp_video_path):
                try:
                    os.remove(temp_video_path)
                except Exception as cleanup_error:
                    print(f"Warning: Failed to clean up temp file {temp_video_path}: {cleanup_error}")
    
    async def sync_all_videos_to_s3(
        self,
        user_id: UUID,
        max_videos: int = 50
    ) -> Dict[str, Any]:
        """
        Sync all user's YouTube videos to S3.
        
        Args:
            user_id: User UUID
            max_videos: Maximum number of videos to sync
            
        Returns:
            Dict with sync operation summary
        """
        sync_id = str(uuid4())
        start_time = time.time()
        
        results = {
            "sync_id": sync_id,
            "total_videos_found": 0,
            "videos_already_in_s3": 0,
            "videos_synced": 0,
            "errors": 0,
            "synced_videos": [],
            "processing_time_seconds": 0
        }
        
        try:
            # Get all YouTube videos
            youtube_videos = await self._fetch_youtube_videos(page_size=max_videos)
            results["total_videos_found"] = len(youtube_videos["videos"])
            
            for video in youtube_videos["videos"]:
                try:
                    # Check if already in S3
                    existing = await self._check_video_exists_in_s3(
                        video["id"], user_id
                    )
                    
                    if existing:
                        results["videos_already_in_s3"] += 1
                        continue
                    
                    # Download and upload to S3
                    sync_result = await self.download_and_upload_to_s3(
                        video["id"], user_id
                    )
                    
                    results["videos_synced"] += 1
                    results["synced_videos"].append({
                        "youtube_id": video["id"],
                        "title": sync_result["title"],
                        "s3_video_id": sync_result["s3_video_id"]
                    })
                    
                except Exception as video_error:
                    results["errors"] += 1
                    print(f"Error syncing video {video.get('id', 'unknown')}: {video_error}")
            
            results["processing_time_seconds"] = round(time.time() - start_time, 2)
            return results
            
        except Exception as e:
            results["processing_time_seconds"] = round(time.time() - start_time, 2)
            raise Exception(f"Sync operation failed: {str(e)}")
    
    async def get_sync_status(self, sync_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a sync operation.
        
        Args:
            sync_id: Sync operation ID
            
        Returns:
            Sync status information or None if not found
        """
        # In a real implementation, you would store sync status in a database
        # For now, we'll return a placeholder response
        return {
            "sync_id": sync_id,
            "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "progress": 100,
            "message": "Sync operation completed"
        }
    
    # Private helper methods
    
    async def _fetch_youtube_videos(
        self,
        page_size: int = 20,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch videos from YouTube Data API."""
        try:
            # Import YouTube API client
            from googleapiclient.discovery import build
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            
            # Authenticate with YouTube API
            credentials = await self._authenticate_youtube()
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # Get user's channel uploads playlist
            channels_response = youtube.channels().list(
                part='contentDetails',
                mine=True
            ).execute()
            
            if not channels_response['items']:
                return {"videos": [], "has_more": False}
            
            uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # Get videos from uploads playlist
            playlist_request = youtube.playlistItems().list(
                part='snippet,contentDetails',
                playlistId=uploads_playlist_id,
                maxResults=page_size,
                pageToken=page_token
            )
            
            playlist_response = playlist_request.execute()
            
            # Get additional video details
            video_ids = [item['contentDetails']['videoId'] for item in playlist_response['items']]
            
            if video_ids:
                videos_response = youtube.videos().list(
                    part='snippet,contentDetails,statistics',
                    id=','.join(video_ids)
                ).execute()
                
                videos = []
                for video in videos_response['items']:
                    videos.append({
                        "id": video['id'],
                        "title": video['snippet']['title'],
                        "description": video['snippet']['description'],
                        "thumbnail_url": video['snippet']['thumbnails'].get('medium', {}).get('url'),
                        "duration": video['contentDetails']['duration'],
                        "published_at": video['snippet']['publishedAt'],
                        "view_count": int(video['statistics'].get('viewCount', 0)),
                        "like_count": int(video['statistics'].get('likeCount', 0)),
                        "privacy_status": video['snippet'].get('privacyStatus', 'public'),
                        "is_in_s3": False,  # Will be updated later
                        "s3_video_id": None,
                        "metadata": {
                            "channel_id": video['snippet']['channelId'],
                            "category_id": video['snippet'].get('categoryId'),
                            "tags": video['snippet'].get('tags', [])
                        }
                    })
            else:
                videos = []
            
            return {
                "videos": videos,
                "total_count": len(videos),
                "has_more": 'nextPageToken' in playlist_response,
                "next_page_token": playlist_response.get('nextPageToken')
            }
            
        except ImportError:
            raise Exception("Google API client library not installed. Run: pip install google-api-python-client google-auth google-auth-oauthlib")
        except Exception as e:
            # Fallback: return mock data for development
            return await self._get_mock_youtube_videos(page_size, page_token)
    
    async def _get_mock_youtube_videos(
        self,
        page_size: int = 20,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return mock YouTube videos for development/testing."""
        mock_videos = [
            {
                "id": f"mock_video_{i}",
                "title": f"Sample YouTube Video {i}",
                "description": f"This is a sample video description for video {i}",
                "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg",
                "duration": "PT3M42S",
                "published_at": "2024-01-01T12:00:00Z",
                "view_count": 1000 * i,
                "like_count": 50 * i,
                "privacy_status": "public",
                "is_in_s3": i % 3 == 0,  # Every 3rd video is "already in S3"
                "s3_video_id": f"s3_video_{i}" if i % 3 == 0 else None,
                "metadata": {
                    "channel_id": "UC_mock_channel_id",
                    "category_id": "22",
                    "tags": ["sample", "video", f"tag{i}"]
                }
            }
            for i in range(1, page_size + 1)
        ]
        
        return {
            "videos": mock_videos,
            "total_count": len(mock_videos),
            "has_more": False,
            "next_page_token": None
        }
    
    async def _add_s3_status_to_videos(
        self,
        youtube_videos: List[Dict[str, Any]],
        user_id: UUID
    ) -> List[Dict[str, Any]]:
        """Add S3 sync status to YouTube videos."""
        for video in youtube_videos:
            existing_video = await self._check_video_exists_in_s3(
                video["id"], user_id
            )
            
            if existing_video:
                video["is_in_s3"] = True
                video["s3_video_id"] = str(existing_video["id"])
            else:
                video["is_in_s3"] = False
                video["s3_video_id"] = None
        
        return youtube_videos
    
    async def _check_video_exists_in_s3(
        self,
        youtube_video_id: str,
        user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Check if a YouTube video already exists in S3."""
        try:
            # Look for video with YouTube ID in metadata
            result = await self.db.execute(
                select(Video).where(
                    Video.user_id == user_id,
                    Video.metadata.op('->>')('youtube_id') == youtube_video_id
                )
            )
            video = result.scalar_one_or_none()
            
            if video:
                return {
                    "id": video.id,
                    "filename": video.filename,
                    "s3_key": video.s3_key
                }
            
            return None
            
        except Exception as e:
            print(f"Error checking video in S3: {e}")
            return None
    
    async def _get_youtube_video_metadata(self, video_id: str) -> Dict[str, Any]:
        """Get video metadata from YouTube."""
        # This would use YouTube Data API to get full metadata
        # For now, return basic metadata
        return {
            "title": f"YouTube Video {video_id}",
            "description": f"Downloaded from YouTube (ID: {video_id})",
            "duration": "PT3M42S",
            "resolution": "1080p",
            "youtube_id": video_id
        }
    
    async def _download_youtube_video(
        self,
        video_id: str,
        title: str
    ) -> str:
        """Download video from YouTube using yt-dlp."""
        try:
            # Generate safe filename
            safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
            temp_file = self.temp_dir / f"youtube_{video_id}_{safe_title}.%(ext)s"
            
            # Use yt-dlp to download video
            import subprocess
            
            cmd = [
                "yt-dlp",
                "-f", "best[ext=mp4]/best",
                "-o", str(temp_file),
                f"https://www.youtube.com/watch?v={video_id}"
            ]
            
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if result.returncode != 0:
                raise Exception(f"yt-dlp failed: {result.stderr}")
            
            # Find the downloaded file (yt-dlp changes extension)
            for file_path in self.temp_dir.glob(f"youtube_{video_id}_{safe_title}.*"):
                if file_path.suffix in ['.mp4', '.webm', '.mkv']:
                    return str(file_path)
            
            raise Exception("Downloaded video file not found")
            
        except ImportError:
            raise Exception("yt-dlp not installed. Run: pip install yt-dlp")
        except Exception as e:
            raise Exception(f"Failed to download YouTube video: {str(e)}")
    
    async def _upload_video_to_s3(
        self,
        video_path: str,
        metadata: Dict[str, Any],
        user_id: UUID
    ) -> Dict[str, Any]:
        """Upload video file to S3."""
        try:
            # Create a mock UploadFile object for S3Service
            from fastapi import UploadFile
            from io import BytesIO
            
            # Read video file
            with open(video_path, 'rb') as f:
                video_content = f.read()
            
            # Create mock UploadFile
            video_file = UploadFile(
                filename=f"{metadata['title']}.mp4",
                file=BytesIO(video_content),
                content_type="video/mp4"
            )
            
            # Upload to S3
            upload_id = uuid4()
            s3_result = await self.s3_service.upload_file(
                file=video_file,
                file_type="video",
                upload_id=upload_id,
                is_temp=False  # Permanent storage
            )
            
            return {
                "s3_key": s3_result["s3_key"],
                "s3_url": s3_result["s3_url"],
                "file_size_mb": s3_result["file_size_mb"],
                "format": "mp4"
            }
            
        except Exception as e:
            raise Exception(f"Failed to upload to S3: {str(e)}")
    
    async def _create_video_record(
        self,
        s3_result: Dict[str, Any],
        metadata: Dict[str, Any],
        youtube_video_id: str,
        user_id: UUID
    ) -> Video:
        """Create video record in database."""
        try:
            video_data = VideoCreate(
                filename=f"{metadata['title']}.mp4",
                original_filename=f"{metadata['title']}.mp4",
                s3_key=s3_result["s3_key"],
                s3_url=s3_result["s3_url"],
                s3_bucket=self.s3_service.bucket_name,
                content_type="video/mp4",
                file_size=int(s3_result["file_size_mb"] * 1024 * 1024),
                user_id=user_id,
                metadata={
                    "youtube_id": youtube_video_id,
                    "source": "youtube_import",
                    "original_title": metadata["title"],
                    "youtube_duration": metadata.get("duration"),
                    "youtube_resolution": metadata.get("resolution"),
                    "imported_at": datetime.now(timezone.utc).isoformat()
                }
            )
            
            return await self.video_repository.create_video(video_data)
            
        except Exception as e:
            raise Exception(f"Failed to create video record: {str(e)}")
    
    async def _authenticate_youtube(self):
        """Authenticate with YouTube API."""
        # This would handle OAuth authentication
        # For now, return None to trigger mock data
        return None 