"""
YouTube upload service for publishing videos to YouTube using YouTube Data API v3
"""

import asyncio
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
import tempfile
import logging

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class YouTubeUploadService:
    """Service for uploading videos to YouTube using YouTube Data API v3."""
    
    def __init__(self, user_id: Optional[str] = None, secret_service=None):
        """
        Initialize YouTube upload service with user-specific authentication.
        
        Args:
            user_id: User ID for credential lookup
            secret_service: SecretService instance for token management
        """
        self.user_id = user_id
        self.secret_service = secret_service
        self.api_key = None
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
    
    async def get_oauth_authorization_url(self, user_id: str) -> Dict[str, Any]:
        """
        Get YouTube OAuth authorization URL for user authentication.
        
        Args:
            user_id: User ID for credential lookup
            
        Returns:
            Dict containing authorization_url and state
        """
        if not self.secret_service:
            raise Exception("SecretService not initialized")
        
        try:
            from uuid import UUID
            
            # Convert string user_id to UUID if needed
            if isinstance(user_id, str):
                user_uuid = UUID(user_id)
            else:
                user_uuid = user_id
            
            # Use the secret service OAuth initialization
            oauth_response = await self.secret_service.initiate_youtube_oauth(
                user_id=user_uuid,
                scopes=[
                    "https://www.googleapis.com/auth/youtube.upload",
                    "https://www.googleapis.com/auth/youtube"
                ]
            )
            
            return {
                "authorization_url": oauth_response.authorization_url,
                "state": oauth_response.state
            }
            
        except Exception as e:
            raise Exception(f"Failed to get OAuth authorization URL: {str(e)}")

    async def handle_oauth_callback(self, user_id: str, authorization_code: str, state: str) -> Dict[str, Any]:
        """
        Handle OAuth callback and store tokens.
        
        Args:
            user_id: User ID
            authorization_code: Authorization code from OAuth callback
            state: State parameter from OAuth callback
            
        Returns:
            Dict with callback result
        """
        if not self.secret_service:
            raise Exception("SecretService not initialized")
        
        try:
            from uuid import UUID
            
            # Convert string user_id to UUID if needed
            if isinstance(user_id, str):
                user_uuid = UUID(user_id)
            else:
                user_uuid = user_id
            
            # Use the secret service OAuth callback handling
            callback_response = await self.secret_service.handle_youtube_oauth_callback(
                user_id=user_uuid,
                code=authorization_code,
                state=state
            )
            
            return {
                "authenticated": callback_response.success,
                "message": callback_response.message,
                "channel_info": {
                    "authenticated": callback_response.youtube_authenticated,
                    "scopes": callback_response.scopes_granted
                }
            }
            
        except Exception as e:
            return {
                "authenticated": False,
                "message": f"OAuth callback failed: {str(e)}"
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
            
            # Check if user authentication is available
            if not self.user_id or not self.secret_service:
                raise Exception("User authentication not configured. YouTube upload requires authenticated user.")
            
            # Perform real YouTube upload
            return await self._perform_youtube_upload(
                video_path, title, description, tags, category, privacy, made_for_kids
            )
            
        except Exception as e:
            # Improve error logging and avoid nested error messages
            error_msg = str(e)
            
            # Don't wrap already detailed error messages
            if "YouTube API" in error_msg or "authentication failed" in error_msg.lower():
                return {
                    "status": "error",
                    "error_message": error_msg
                }
            else:
                return {
                    "status": "error",
                    "error_message": f"YouTube upload failed: {error_msg}"
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
            from googleapiclient.errors import HttpError
            
            logger.info(f"Starting YouTube upload for user {self.user_id}")
            
            # Get authenticated YouTube credentials with automatic refresh
            logger.info("Retrieving YouTube credentials...")
            credentials = await self.secret_service.get_youtube_credentials(
                user_id=self.user_id,
                auto_refresh=True
            )
            logger.info("YouTube credentials retrieved successfully")
            
            # Build YouTube service
            logger.info("Building YouTube service...")
            youtube = build('youtube', 'v3', credentials=credentials)
            logger.info("YouTube service built successfully")
            
            # Prepare video metadata
            logger.info(f"Preparing video metadata - Title: {title}, Category: {category}, Privacy: {privacy}")
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
            logger.info(f"Creating media upload object for file: {video_path}")
            media = MediaFileUpload(
                video_path, 
                chunksize=-1, 
                resumable=True,
                mimetype='video/mp4'
            )
            logger.info("Media upload object created successfully")
            
            # Execute upload
            logger.info("Starting YouTube API upload request...")
            insert_request = youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            logger.info("Upload request created, starting upload process...")
            
            # Handle resumable upload with proper error handling
            response = None
            error = None
            retry = 0
            
            while response is None:
                try:
                    status, response = insert_request.next_chunk()
                    if status:
                        logger.info(f"Upload progress: {int(status.progress() * 100)}%")
                except HttpError as e:
                    # Extract detailed error information from Google API
                    error_details = []
                    
                    # Add status code and reason
                    error_details.append(f"HTTP {e.resp.status}: {e.reason if hasattr(e, 'reason') else 'Unknown'}")
                    
                    # Try to extract more specific error from the response content
                    try:
                        import json
                        if hasattr(e, 'content') and e.content:
                            content = json.loads(e.content.decode('utf-8'))
                            if 'error' in content:
                                if 'message' in content['error']:
                                    error_details.append(f"Message: {content['error']['message']}")
                                if 'errors' in content['error']:
                                    for err in content['error']['errors']:
                                        if 'reason' in err:
                                            error_details.append(f"Reason: {err['reason']}")
                                        if 'message' in err:
                                            error_details.append(f"Detail: {err['message']}")
                    except:
                        # If we can't parse the error content, continue with basic error
                        pass
                    
                    detailed_error = " | ".join(error_details) if error_details else str(e)
                    
                    if e.resp.status in [401, 403]:
                        # Authentication/authorization error - likely token issue
                        raise Exception(f"YouTube API authentication failed: {detailed_error}. Please re-authenticate with YouTube.")
                    elif e.resp.status in [500, 502, 503, 504] and retry < self.max_retries:
                        # Recoverable server errors
                        retry += 1
                        logger.warning(f"Server error {e.resp.status}, retrying ({retry}/{self.max_retries}): {detailed_error}")
                        await asyncio.sleep(2 ** retry)  # Exponential backoff
                        continue
                    else:
                        raise Exception(f"YouTube API error: {detailed_error}")
                except Exception as e:
                    if retry < self.max_retries:
                        retry += 1
                        logger.warning(f"Upload error, retrying ({retry}/{self.max_retries}): {str(e)}")
                        await asyncio.sleep(2 ** retry)  # Exponential backoff
                        continue
                    else:
                        raise Exception(f"Upload failed after {self.max_retries} retries: {str(e)}")
            
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
            # Log the full error details for debugging
            logger.error(f"YouTube upload failed for user {self.user_id}: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {repr(e)}")
            
            # Handle token refresh failures
            if "invalid_grant" in str(e).lower() or "unauthorized" in str(e).lower():
                raise Exception(f"YouTube authentication expired or invalid: {str(e)}. Please re-authenticate with YouTube.")
            
            # Don't wrap already detailed error messages
            error_msg = str(e)
            if "YouTube API" in error_msg or "authentication failed" in error_msg.lower():
                raise Exception(error_msg)
            else:
                raise Exception(f"YouTube API upload failed: {error_msg}")
    
    async def _authenticate_youtube(self, scopes: List[str]):
        """
        DEPRECATED: Use SecretService.get_youtube_credentials() instead.
        
        This method is kept for backward compatibility but should not be used
        in new code. The new authentication flow uses database-stored tokens
        with automatic refresh.
        """
        raise Exception(
            "File-based authentication is deprecated. "
            "Use SecretService.get_youtube_credentials() for database-based token management."
        )
    
    async def _validate_upload_params(
        self, 
        title: str, 
        description: str, 
        tags: Optional[List[str]], 
        category: str, 
        privacy: str
    ) -> Dict[str, Any]:
        """
        Validate upload parameters.
        
        Args:
            title: Video title
            description: Video description  
            tags: Video tags
            category: Video category
            privacy: Privacy setting
            
        Returns:
            Dict with validation result
        """
        errors = []
        
        # Validate title
        if not title or not title.strip():
            errors.append("Title is required")
        elif len(title) > 100:
            errors.append("Title must be 100 characters or less")
        
        # Validate description
        if description and len(description) > 5000:
            errors.append("Description must be 5000 characters or less")
        
        # Validate tags
        if tags:
            if len(tags) > 500:
                errors.append("Maximum 500 tags allowed")
            for tag in tags:
                if len(tag) > 500:
                    errors.append("Each tag must be 500 characters or less")
        
        # Validate category
        if category not in self.supported_categories:
            errors.append(f"Invalid category. Supported: {list(self.supported_categories.keys())}")
        
        # Validate privacy
        valid_privacy = ["public", "unlisted", "private"]
        if privacy not in valid_privacy:
            errors.append(f"Invalid privacy setting. Must be one of: {valid_privacy}")
        
        return {
            "valid": len(errors) == 0,
            "error": "; ".join(errors) if errors else None
        }
    
    def get_upload_guidelines(self) -> Dict[str, Any]:
        """
        Get YouTube upload guidelines and requirements.
        
        Returns:
            Dict with upload guidelines
        """
        return {
            "file_requirements": {
                "max_file_size_gb": 256,
                "supported_formats": [
                    ".mov", ".mpeg4", ".mp4", ".avi", ".wmv", ".mpegps", ".flv", ".3gpp", ".webm"
                ],
                "recommended_format": ".mp4",
                "max_duration_hours": 12,
                "min_resolution": "426x240",
                "max_resolution": "3840x2160",
                "recommended_resolution": "1920x1080"
            },
            "content_guidelines": {
                "title_max_length": 100,
                "description_max_length": 5000,
                "tags_max_count": 500,
                "tag_max_length": 500,
                "thumbnail_formats": [".jpg", ".gif", ".png"],
                "thumbnail_max_size_mb": 2,
                "thumbnail_resolution": "1280x720"
            },
            "privacy_options": [
                {"value": "public", "label": "Public", "description": "Anyone can search for and view"},
                {"value": "unlisted", "label": "Unlisted", "description": "Anyone with the link can view"},
                {"value": "private", "label": "Private", "description": "Only you can view"}
            ],
            "categories": [
                {"value": key, "label": key.title(), "id": value}
                for key, value in self.supported_categories.items()
            ],
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
            
            if not self.user_id or not self.secret_service:
                raise Exception("User authentication not configured")
            
            # Get authenticated credentials
            credentials = await self.secret_service.get_youtube_credentials(
                user_id=self.user_id,
                auto_refresh=True
            )
            
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
                "processing_failure_reason": processing.get('processingFailureReason'),
                "processing_issues_availability": processing.get('processingIssuesAvailability'),
                "tag_suggestions_availability": processing.get('tagSuggestionsAvailability'),
                "editor_suggestions_availability": processing.get('editorSuggestionsAvailability'),
                "thumbnail_availability": processing.get('thumbnailsAvailability')
            }
            
        except Exception as e:
            return {
                "error": f"Failed to check processing status: {str(e)}",
                "video_id": video_id
            }
    
    async def get_channel_info(self, user_id: str) -> Dict[str, Any]:
        """
        Get YouTube channel information for authenticated user.
        
        Args:
            user_id: User ID for credential lookup
            
        Returns:
            Dict with channel information
        """
        try:
            from googleapiclient.discovery import build
            
            if not self.secret_service:
                raise Exception("SecretService not initialized")
            
            # Get authenticated credentials
            credentials = await self.secret_service.get_youtube_credentials(
                user_id=user_id,
                auto_refresh=True
            )
            
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # Get channel information
            request = youtube.channels().list(
                part="snippet,statistics",
                mine=True
            )
            response = request.execute()
            
            if not response['items']:
                return {
                    "error": "No channel found for authenticated user"
                }
            
            channel = response['items'][0]
            snippet = channel.get('snippet', {})
            stats = channel.get('statistics', {})
            
            return {
                "id": channel.get('id'),
                "title": snippet.get('title'),
                "description": snippet.get('description'),
                "custom_url": snippet.get('customUrl'),
                "published_at": snippet.get('publishedAt'),
                "thumbnail_url": snippet.get('thumbnails', {}).get('default', {}).get('url'),
                "subscriber_count": int(stats.get('subscriberCount', 0)),
                "video_count": int(stats.get('videoCount', 0)),
                "view_count": int(stats.get('viewCount', 0))
            }
            
        except Exception as e:
            return {
                "error": f"Failed to get channel info: {str(e)}"
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
            
            if not self.user_id or not self.secret_service:
                raise Exception("User authentication not configured")
            
            # Get authenticated credentials
            credentials = await self.secret_service.get_youtube_credentials(
                user_id=self.user_id,
                auto_refresh=True
            )
            
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
                "title": snippet.get('title'),
                "published_at": snippet.get('publishedAt'),
                "view_count": int(stats.get('viewCount', 0)),
                "like_count": int(stats.get('likeCount', 0)),
                "dislike_count": int(stats.get('dislikeCount', 0)),
                "comment_count": int(stats.get('commentCount', 0)),
                "favorite_count": int(stats.get('favoriteCount', 0)),
                "duration": snippet.get('duration'),
                "tags": snippet.get('tags', []),
                "category_id": snippet.get('categoryId'),
                "default_language": snippet.get('defaultLanguage')
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
                    "title": "Upload Credentials",
                    "description": "Upload the client_secrets.json file via the API",
                    "endpoint": "/api/v1/secrets/upload"
                },
                {
                    "step": 6,
                    "title": "Complete OAuth Flow",
                    "description": "Complete YouTube OAuth authentication",
                    "endpoints": [
                        "/api/v1/secrets/youtube/oauth/init",
                        "/api/v1/secrets/youtube/oauth/callback"
                    ]
                }
            ],
            "authentication_flow": {
                "description": "Database-based OAuth token management with automatic refresh",
                "features": [
                    "Encrypted token storage",
                    "Automatic token refresh",
                    "Per-user authentication",
                    "Secure credential management"
                ]
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