"""
YouTube upload service for publishing videos to YouTube using YouTube Data API v3
"""

import asyncio
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

from app.config import get_settings

settings = get_settings()


class YouTubeUploadService:
    """Service for uploading videos to YouTube using YouTube Data API v3."""
    
    def __init__(self):
        """Initialize YouTube upload service."""
        self.api_key = getattr(settings, 'youtube_api_key', None)
        self.client_secrets_file = getattr(settings, 'youtube_client_secrets_file', None)
        self.max_retries = 3
        self.supported_categories = {
            "film": "1",
            "autos": "2", 
            "music": "10",
            "pets": "15",
            "sports": "17",
            "travel": "19",
            "gaming": "20",
            "people": "22",
            "comedy": "23",
            "entertainment": "24",
            "news": "25",
            "howto": "26",
            "education": "27",
            "science": "28",
            "nonprofits": "29"
        }
    
    async def upload_video_to_youtube(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        category: str = "entertainment",
        privacy: str = "public",
        made_for_kids: bool = False
    ) -> Dict[str, Any]:
        """
        Upload video to YouTube using YouTube Data API v3.
        
        Args:
            video_path: Path to video file
            title: Video title
            description: Video description
            tags: List of video tags
            category: Video category
            privacy: Privacy setting (public, unlisted, private)
            made_for_kids: Whether video is made for kids
            
        Returns:
            Dict with upload results
        """
        try:
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            # Validate inputs
            validation_result = await self._validate_upload_params(
                title, description, tags, category, privacy
            )
            if not validation_result["valid"]:
                return {
                    "status": "error", 
                    "error_message": validation_result["error"]
                }
            
            # Check if YouTube credentials are configured
            if not self.client_secrets_file:
                raise Exception("YouTube client secrets file not configured. Set YOUTUBE_CLIENT_SECRETS_FILE environment variable.")
            
            if not os.path.exists(self.client_secrets_file):
                raise Exception(f"YouTube client secrets file not found: {self.client_secrets_file}")
            
            # Perform real YouTube upload
            return await self._perform_youtube_upload(
                video_path, title, description, tags, category, privacy, made_for_kids
            )
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"YouTube upload failed: {str(e)}"
            }
    
    async def _perform_youtube_upload(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        category: str,
        privacy: str,
        made_for_kids: bool
    ) -> Dict[str, Any]:
        """
        Perform actual YouTube upload using YouTube Data API v3.
        """
        try:
            # Import Google API client libraries
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            import pickle
            
            # OAuth 2.0 scopes
            SCOPES = [
                'https://www.googleapis.com/auth/youtube.upload',
                'https://www.googleapis.com/auth/youtube'
            ]
            
            # Authenticate and build YouTube service
            credentials = await self._authenticate_youtube(SCOPES)
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # Prepare video metadata
            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': tags or [],
                    'categoryId': self.supported_categories.get(category, '24'),
                    'defaultLanguage': 'en',
                    'defaultAudioLanguage': 'en'
                },
                'status': {
                    'privacyStatus': privacy,
                    'selfDeclaredMadeForKids': made_for_kids,
                    'notifySubscribers': True
                }
            }
            
            # Create media upload object
            media = MediaFileUpload(
                video_path, 
                chunksize=-1, 
                resumable=True,
                mimetype='video/mp4'
            )
            
            # Execute upload
            insert_request = youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            # Handle resumable upload
            response = None
            error = None
            retry = 0
            
            while response is None:
                try:
                    status, response = insert_request.next_chunk()
                    if status:
                        print(f"Upload progress: {int(status.progress() * 100)}%")
                except Exception as e:
                    if retry < self.max_retries:
                        retry += 1
                        print(f"Upload error, retrying ({retry}/{self.max_retries}): {str(e)}")
                        await asyncio.sleep(2 ** retry)  # Exponential backoff
                        continue
                    else:
                        raise e
            
            if response is None:
                raise Exception("Upload failed - no response received")
            
            # Extract video information from response
            video_id = response['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            shorts_url = f"https://www.youtube.com/shorts/{video_id}"
            
            # Get file info
            file_size = os.path.getsize(video_path)
            
            return {
                "status": "success",
                "video_id": video_id,
                "video_url": video_url,
                "shorts_url": shorts_url,
                "title": title,
                "description": description,
                "tags": tags or [],
                "category": category,
                "privacy": privacy,
                "upload_date": response.get('snippet', {}).get('publishedAt'),
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "processing_status": "uploaded",
                "channel_id": response.get('snippet', {}).get('channelId'),
                "thumbnail_url": response.get('snippet', {}).get('thumbnails', {}).get('default', {}).get('url'),
                "duration": response.get('contentDetails', {}).get('duration'),
                "definition": response.get('contentDetails', {}).get('definition'),
                "youtube_response": response
            }
            
        except ImportError:
            raise Exception("Google API client library not installed. Run: pip install google-api-python-client google-auth google-auth-oauthlib")
        except Exception as e:
            raise Exception(f"YouTube API upload failed: {str(e)}")
    
    async def _authenticate_youtube(self, scopes: List[str]):
        """
        Authenticate with YouTube using OAuth 2.0.
        
        Args:
            scopes: List of required OAuth scopes
            
        Returns:
            Authenticated credentials object
        """
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        import pickle
        import os
        
        creds = None
        token_file = "youtube_token.pickle"
        
        # Load existing token if available
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                # Refresh expired token
                creds.refresh(Request())
            else:
                # Run OAuth flow for new token
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets_file, scopes
                )
                # Use port 8080 to match the redirect URIs in client secrets
                creds = flow.run_local_server(port=8080, open_browser=True)
            
            # Save credentials for next run
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        return creds
    
    async def _validate_upload_params(
        self,
        title: str,
        description: str,
        tags: Optional[List[str]],
        category: str,
        privacy: str
    ) -> Dict[str, Any]:
        """
        Validate YouTube upload parameters.
        
        Returns:
            Dict with validation results
        """
        issues = []
        
        # Validate title
        if not title or not title.strip():
            issues.append("Title is required")
        elif len(title) > 100:
            issues.append("Title must be 100 characters or less")
        
        # Validate description
        if len(description) > 5000:
            issues.append("Description must be 5000 characters or less")
        
        # Validate tags
        if tags:
            if len(tags) > 500:
                issues.append("Maximum 500 tags allowed")
            
            for tag in tags:
                if len(tag) > 500:
                    issues.append(f"Tag too long: '{tag[:50]}...' (max 500 characters)")
        
        # Validate category
        if category not in self.supported_categories:
            issues.append(f"Invalid category: {category}. Supported: {list(self.supported_categories.keys())}")
        
        # Validate privacy
        valid_privacy = ["public", "unlisted", "private"]
        if privacy not in valid_privacy:
            issues.append(f"Invalid privacy setting: {privacy}. Use: {valid_privacy}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "error": "; ".join(issues) if issues else None
        }
    
    def get_upload_guidelines(self) -> Dict[str, Any]:
        """
        Get YouTube upload guidelines and requirements.
        
        Returns:
            Dict with guidelines
        """
        return {
            "file_requirements": {
                "max_file_size": "256 GB",
                "max_duration": "12 hours",
                "supported_formats": [
                    "MOV", "MPEG4", "MP4", "AVI", "WMV", "MPEGPS", 
                    "FLV", "3GPP", "WebM", "DNxHR", "ProRes", "CineForm", "HEVC"
                ],
                "recommended_format": "MP4",
                "recommended_codec": "H.264"
            },
            "shorts_requirements": {
                "max_duration": "60 seconds",
                "aspect_ratio": "9:16 (vertical)",
                "resolution": "1080x1920 (recommended)",
                "title_suffix": "#Shorts (optional but recommended)"
            },
            "metadata_limits": {
                "title": "100 characters",
                "description": "5000 characters", 
                "tags": "500 total tags, 500 characters per tag",
                "custom_thumbnail": "2MB max, 1280x720 recommended"
            },
            "content_policies": {
                "community_guidelines": "https://www.youtube.com/howyoutubeworks/policies/community-guidelines/",
                "copyright": "Must own or have rights to all content",
                "monetization": "Follow monetization policies for revenue",
                "age_restriction": "Properly classify content for appropriate audiences"
            },
            "privacy_options": {
                "public": "Anyone can search for and view",
                "unlisted": "Anyone with link can view",
                "private": "Only you can view",
                "scheduled": "Public at specified time"
            },
            "categories": self.supported_categories,
            "optimization_tips": [
                "Use relevant, searchable titles",
                "Write detailed descriptions with keywords",
                "Add appropriate tags for discoverability",
                "Create eye-catching thumbnails",
                "Use end screens and cards for engagement",
                "Post consistently for better algorithm performance"
            ]
        }
    
    async def check_video_processing_status(self, video_id: str) -> Dict[str, Any]:
        """
        Check the processing status of an uploaded video.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Dict with processing status
        """
        try:
            from googleapiclient.discovery import build
            
            # Authenticate and build YouTube service
            credentials = await self._authenticate_youtube([
                'https://www.googleapis.com/auth/youtube.readonly'
            ])
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # Get video details
            request = youtube.videos().list(
                part="status,processingDetails",
                id=video_id
            )
            response = request.execute()
            
            if not response['items']:
                return {
                    "error": "Video not found",
                    "video_id": video_id
                }
            
            video = response['items'][0]
            status = video.get('status', {})
            processing = video.get('processingDetails', {})
            
            return {
                "video_id": video_id,
                "upload_status": status.get('uploadStatus'),
                "privacy_status": status.get('privacyStatus'),
                "processing_status": processing.get('processingStatus'),
                "processing_progress": processing.get('processingProgress'),
                "failure_reason": status.get('failureReason'),
                "rejection_reason": status.get('rejectionReason'),
                "embeddable": status.get('embeddable'),
                "license": status.get('license'),
                "made_for_kids": status.get('selfDeclaredMadeForKids'),
                "public_stats_viewable": status.get('publicStatsViewable')
            }
            
        except Exception as e:
            return {
                "error": f"Failed to check video status: {str(e)}",
                "video_id": video_id
            }
    
    async def get_video_analytics(self, video_id: str, days: int = 7) -> Dict[str, Any]:
        """
        Get basic analytics for an uploaded video.
        
        Args:
            video_id: YouTube video ID
            days: Number of days to look back
            
        Returns:
            Dict with analytics data
        """
        try:
            from googleapiclient.discovery import build
            from datetime import datetime, timedelta
            
            # Authenticate and build YouTube service
            credentials = await self._authenticate_youtube([
                'https://www.googleapis.com/auth/youtube.readonly',
                'https://www.googleapis.com/auth/yt-analytics.readonly'
            ])
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # Get basic video statistics
            request = youtube.videos().list(
                part="statistics,snippet",
                id=video_id
            )
            response = request.execute()
            
            if not response['items']:
                return {
                    "error": "Video not found",
                    "video_id": video_id
                }
            
            video = response['items'][0]
            stats = video.get('statistics', {})
            snippet = video.get('snippet', {})
            
            return {
                "video_id": video_id,
                "period_days": days,
                "views": int(stats.get('viewCount', 0)),
                "likes": int(stats.get('likeCount', 0)),
                "comments": int(stats.get('commentCount', 0)),
                "favorites": int(stats.get('favoriteCount', 0)),
                "title": snippet.get('title'),
                "published_at": snippet.get('publishedAt'),
                "channel_title": snippet.get('channelTitle'),
                "duration": snippet.get('duration'),
                "note": "Analytics data from YouTube Data API v3. For detailed analytics, use YouTube Analytics API."
            }
            
        except Exception as e:
            return {
                "error": f"Failed to get video analytics: {str(e)}",
                "video_id": video_id
            }
    
    def setup_instructions(self) -> Dict[str, Any]:
        """
        Get instructions for setting up YouTube API integration.
        
        Returns:
            Dict with setup instructions
        """
        return {
            "steps": [
                {
                    "step": 1,
                    "title": "Create Google Cloud Project",
                    "description": "Go to Google Cloud Console and create a new project",
                    "url": "https://console.cloud.google.com/"
                },
                {
                    "step": 2,
                    "title": "Enable YouTube Data API v3",
                    "description": "Enable the YouTube Data API v3 in your project",
                    "path": "APIs & Services > Library > YouTube Data API v3"
                },
                {
                    "step": 3,
                    "title": "Create OAuth 2.0 Credentials",
                    "description": "Create OAuth 2.0 client credentials for desktop application",
                    "path": "APIs & Services > Credentials > Create Credentials"
                },
                {
                    "step": 4,
                    "title": "Download Client Secrets",
                    "description": "Download the client_secrets.json file",
                    "note": "Keep this file secure and don't commit to version control"
                },
                {
                    "step": 5,
                    "title": "Set Environment Variables",
                    "description": "Set YOUTUBE_CLIENT_SECRETS_FILE path in your environment",
                    "example": "YOUTUBE_CLIENT_SECRETS_FILE=/path/to/client_secrets.json"
                },
                {
                    "step": 6,
                    "title": "Install Dependencies",
                    "description": "Install Google API client library",
                    "command": "pip install google-api-python-client google-auth google-auth-oauthlib"
                }
            ],
            "environment_variables": {
                "YOUTUBE_CLIENT_SECRETS_FILE": "Path to OAuth2 client secrets JSON file",
                "YOUTUBE_API_KEY": "YouTube Data API key (optional, for public data only)"
            },
            "scopes_required": [
                "https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube"
            ],
            "documentation": {
                "youtube_api": "https://developers.google.com/youtube/v3",
                "oauth2_setup": "https://developers.google.com/youtube/v3/guides/auth/installed-apps",
                "upload_guide": "https://developers.google.com/youtube/v3/guides/uploading_a_video"
            }
        } 