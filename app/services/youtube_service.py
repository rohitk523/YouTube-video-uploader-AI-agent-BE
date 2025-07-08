"""
YouTube service for integrating with specialized processing services
"""

import asyncio
from typing import Callable, Dict, List, Optional, Any
from uuid import UUID

from app.config import get_settings
from app.services.tts_service import TTSService
from app.services.video_service import VideoService
from app.services.youtube_upload_service import YouTubeUploadService

settings = get_settings()


class YouTubeService:
    """Service for YouTube integration with specialized processing services."""
    
    def __init__(self, progress_callback: Optional[Callable] = None, user_id: Optional[UUID] = None, secret_service=None):
        """
        Initialize YouTube service with specialized services.
        
        Args:
            progress_callback: Optional callback for progress updates
            user_id: User ID for authentication
            secret_service: SecretService instance for token management
        """
        self.progress_callback = progress_callback
        self.user_id = user_id
        self.secret_service = secret_service
        self.tts_service = TTSService()
        self.video_service = VideoService()
        
        # Initialize YouTube upload service with user authentication
        self.youtube_upload_service = YouTubeUploadService(
            user_id=str(user_id) if user_id else None,
            secret_service=secret_service
        )
        
        self.supported_voices = self.tts_service.supported_voices
        
        # Temporary file tracking for cleanup
        self.temp_files = []
    
    async def create_youtube_short_async(
        self,
        job_id: UUID,
        video_path: str,
        transcript: str,
        title: str,
        description: str = "",
        voice: str = "alloy",
        tags: Optional[List[str]] = None,
        mock_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Create a YouTube short with narration asynchronously.
        
        Args:
            job_id: Job UUID for progress tracking
            video_path: Path to source video file or S3 URL
            transcript: Text to convert to speech
            title: Video title
            description: Video description
            voice: TTS voice to use
            tags: List of video tags
            mock_mode: If True, generate video without uploading to YouTube
            
        Returns:
            Dict with processing results
        """
        try:
            # Update progress
            if self.progress_callback:
                await self.progress_callback(job_id, 5, "Starting TTS generation...")
            
            # Generate TTS audio
            tts_result = await self.tts_service.generate_speech(
                text=transcript,
                voice=voice
            )
            
            if tts_result.get("status") != "success":
                raise Exception(f"TTS generation failed: {tts_result.get('error_message', 'Unknown error')}")
            
            audio_path = tts_result.get("audio_path")
            
            if not audio_path:
                raise Exception("Failed to generate TTS audio")
            
            self.temp_files.append(audio_path)
            
            # Update progress
            if self.progress_callback:
                await self.progress_callback(job_id, 25, "TTS audio generated, processing video...")
            
            # Process video with narration
            video_result = await self.video_service.combine_video_with_audio(
                video_path=video_path,
                audio_path=audio_path,
                output_title=title.replace(" ", "_")
            )
            
            if video_result.get("status") != "success":
                raise Exception(f"Failed to process video with narration: {video_result.get('error_message', 'Unknown error')}")
            
            final_video_path = video_result.get("output_path")
            
            self.temp_files.append(final_video_path)
            
            # Update progress
            if self.progress_callback:
                await self.progress_callback(job_id, 75, "Video processing complete...")
            
            # Mock mode: Don't upload to YouTube
            if mock_mode:
                if self.progress_callback:
                    await self.progress_callback(job_id, 100, "Video ready for download (mock mode)")
                
                return {
                    "status": "success",
                    "mode": "mock",
                    "final_video_path": final_video_path,
                    "title": title,
                    "description": description,
                    "tags": tags or [],
                    "voice_used": voice,
                    "processing_info": {
                        "audio_generated": True,
                        "video_processed": True,
                        "youtube_uploaded": False
                    },
                    "message": "Video processed successfully. Ready for download."
                }
            
            # Real mode: Upload to YouTube
            if self.progress_callback:
                await self.progress_callback(job_id, 80, "Uploading to YouTube...")
            
            # Check authentication before upload
            if not self.user_id or not self.secret_service:
                raise Exception("User authentication not configured for YouTube upload")
            
            # Upload to YouTube
            upload_result = await self.youtube_upload_service.upload_video_to_youtube(
                video_path=final_video_path,
                title=title,
                description=description,
                tags=tags or [],
                category="entertainment",
                privacy="public"
            )
            
            if upload_result.get("status") == "error":
                raise Exception(f"YouTube upload failed: {upload_result.get('error_message')}")
            
            # Update progress
            if self.progress_callback:
                await self.progress_callback(job_id, 100, "Upload completed successfully!")
            
            # Cleanup temp files
            await self._cleanup_temp_files()
            
            return {
                "status": "success",
                "mode": "production",
                "youtube_data": upload_result,
                "final_video_path": final_video_path,
                "processing_info": {
                    "audio_generated": True,
                    "video_processed": True,
                    "youtube_uploaded": True
                },
                "title": title,
                "description": description,
                "tags": tags or [],
                "voice_used": voice
            }
            
        except Exception as e:
            # Cleanup on error
            await self._cleanup_temp_files()
            
            # Handle authentication errors specifically
            if "authentication" in str(e).lower() or "invalid_grant" in str(e).lower():
                if self.progress_callback:
                    await self.progress_callback(job_id, -1, f"YouTube authentication failed: {str(e)}")
                raise Exception(f"YouTube authentication failed: {str(e)}. Please re-authenticate with YouTube.")
            
            if self.progress_callback:
                await self.progress_callback(job_id, -1, f"Processing failed: {str(e)}")
            
            raise Exception(f"YouTube short creation failed: {str(e)}")
    
    def create_youtube_short(
        self,
        video_path: str,
        transcript: str,
        title: str,
        description: str = "",
        voice: str = "alloy",
        tags: Optional[List[str]] = None,
        mock_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Synchronous wrapper for create_youtube_short_async.
        
        Args:
            video_path: Path to source video file
            transcript: Text to convert to speech
            title: Video title
            description: Video description
            voice: TTS voice to use
            tags: List of video tags
            mock_mode: If True, generate video without uploading to YouTube
            
        Returns:
            Dict with processing results
        """
        return asyncio.run(self.create_youtube_short_async(
            job_id=UUID('00000000-0000-0000-0000-000000000000'),  # Dummy UUID for sync calls
            video_path=video_path,
            transcript=transcript,
            title=title,
            description=description,
            voice=voice,
            tags=tags,
            mock_mode=mock_mode
        ))
    
    async def _cleanup_temp_files(self):
        """Clean up temporary files."""
        import os
        
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Warning: Failed to cleanup temp file {file_path}: {e}")
        
        self.temp_files.clear()
    
    def get_supported_voices(self) -> List[str]:
        """
        Get list of supported TTS voices.
        
        Returns:
            List of supported voice names
        """
        return self.supported_voices
    
    async def get_processing_capabilities(self) -> Dict[str, Any]:
        """
        Get detailed processing capabilities and system requirements.
        
        Returns:
            Dict with capabilities information
        """
        tts_capabilities = await self.tts_service.get_capabilities()
        video_capabilities = await self.video_service.get_capabilities()
        youtube_guidelines = self.youtube_upload_service.get_upload_guidelines()
        
        return {
            "tts_processing": tts_capabilities,
            "video_processing": video_capabilities,
            "youtube_upload": youtube_guidelines,
            "authentication": {
                "type": "Database-based OAuth with automatic refresh",
                "supported_flows": [
                    "OAuth 2.0 Authorization Code",
                    "Automatic token refresh",
                    "Per-user credential management"
                ],
                "security_features": [
                    "Encrypted token storage",
                    "Automatic token refresh",
                    "Secure credential management",
                    "Authentication status tracking"
                ]
            },
            "processing_modes": {
                "mock_mode": {
                    "description": "Generate video without YouTube upload",
                    "use_case": "Testing and preview",
                    "output": "Local video file for download"
                },
                "production_mode": {
                    "description": "Full processing with YouTube upload",
                    "use_case": "Publishing to YouTube",
                    "output": "YouTube video URL and metadata"
                }
            },
            "supported_operations": [
                "Text-to-speech generation",
                "Video processing with narration overlay", 
                "YouTube Shorts optimization",
                "Automated YouTube upload",
                "Video format conversion",
                "Audio synchronization"
            ],
            "performance": {
                "typical_processing_time": "2-5 minutes per video",
                "max_video_length": "60 seconds (YouTube Shorts)",
                "supported_formats": ["mp4", "mov", "avi", "webm"],
                "output_format": "MP4 (H.264)"
            }
        }
    
    async def get_setup_instructions(self) -> Dict[str, Any]:
        """
        Get setup instructions for all required services.
        
        Returns:
            Dict with setup instructions
        """
        return {
            "youtube_api": self.youtube_upload_service.setup_instructions(),
            "system_requirements": {
                "python_packages": [
                    "openai>=1.0.0",
                    "aiofiles",
                    "httpx",
                    "ffmpeg-python (optional)"
                ],
                "system_tools": [
                    "FFmpeg (required for video processing)",
                    "FFprobe (usually comes with FFmpeg)"
                ],
                "environment_variables": {
                    "OPENAI_API_KEY": "OpenAI API key for TTS generation"
                }
            },
            "authentication_setup": {
                "description": "Complete YouTube OAuth setup",
                "steps": [
                    "1. Upload OAuth credentials via /api/v1/secrets/upload",
                    "2. Initiate OAuth flow via /api/v1/secrets/youtube/oauth/init", 
                    "3. Complete authorization and callback via /api/v1/secrets/youtube/oauth/callback",
                    "4. Verify authentication via /api/v1/secrets/youtube/auth/status"
                ],
                "benefits": [
                    "Automatic token refresh",
                    "Secure encrypted storage", 
                    "Per-user authentication",
                    "No manual token management"
                ]
            },
            "quick_start": [
                "1. Install FFmpeg on your system",
                "2. Set OPENAI_API_KEY environment variable", 
                "3. Upload YouTube OAuth credentials",
                "4. Complete YouTube OAuth flow",
                "5. Test with a small video file first"
            ]
        }

    async def get_oauth_url(self, user_id: UUID) -> Dict[str, str]:
        """
        Get YouTube OAuth authorization URL for user authentication.
        
        Args:
            user_id: UUID of the user
            
        Returns:
            Dict containing auth_url and state
        """
        if not self.secret_service:
            from app.services.secret_service import SecretService
            from app.database import get_db_session
            
            async with get_db_session() as db:
                self.secret_service = SecretService(db)
        
        try:
            # Use the YouTube upload service to get OAuth URL
            oauth_data = await self.youtube_upload_service.get_oauth_authorization_url(str(user_id))
            
            return {
                "auth_url": oauth_data["authorization_url"],
                "state": oauth_data.get("state", "")
            }
        except Exception as e:
            raise Exception(f"Failed to get OAuth URL: {str(e)}")

    async def handle_oauth_callback(self, user_id: UUID, code: str, state: str) -> Dict[str, Any]:
        """
        Handle OAuth callback and store tokens.
        
        Args:
            user_id: UUID of the user
            code: Authorization code from OAuth callback
            state: State parameter from OAuth callback
            
        Returns:
            Dict with authentication result
        """
        if not self.secret_service:
            from app.services.secret_service import SecretService
            from app.database import get_db_session
            
            async with get_db_session() as db:
                self.secret_service = SecretService(db)
        
        try:
            # Use the YouTube upload service to handle callback
            result = await self.youtube_upload_service.handle_oauth_callback(
                user_id=str(user_id),
                authorization_code=code,
                state=state
            )
            
            return {
                "authenticated": True,
                "message": "YouTube authentication successful",
                "channel_info": result.get("channel_info", {})
            }
        except Exception as e:
            return {
                "authenticated": False,
                "message": f"Authentication failed: {str(e)}"
            }

    async def get_auth_status(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get YouTube authentication status for user.
        
        Args:
            user_id: UUID of the user
            
        Returns:
            Dict with authentication status
        """
        if not self.secret_service:
            from app.services.secret_service import SecretService
            from app.database import get_db_session
            
            async with get_db_session() as db:
                self.secret_service = SecretService(db)
        
        try:
            # Check if user has valid YouTube authentication
            secret = await self.secret_service.get_active_secret(user_id)
            
            # Add debug logging
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[DEBUG] get_auth_status for user {user_id}")
            logger.info(f"[DEBUG] Secret found: {secret is not None}")
            if secret:
                logger.info(f"[DEBUG] youtube_authenticated: {secret.youtube_authenticated}")
                logger.info(f"[DEBUG] has_access_token: {secret.youtube_access_token_encrypted is not None}")
                logger.info(f"[DEBUG] has_refresh_token: {secret.youtube_refresh_token_encrypted is not None}")
            
            if not secret:
                return {
                    "is_authenticated": False,
                    "channel_id": None,
                    "channel_title": None,
                    "authenticated_at": None
                }
            
            # Check if YouTube tokens exist and are valid
            # For now, just require access token (refresh token is optional but recommended)
            has_youtube_auth = (
                secret.youtube_authenticated and
                secret.youtube_access_token_encrypted
            )
            
            logger.info(f"[DEBUG] has_youtube_auth check result: {has_youtube_auth}")
            logger.info(f"[DEBUG] youtube_authenticated: {secret.youtube_authenticated}")
            logger.info(f"[DEBUG] has_access_token: {secret.youtube_access_token_encrypted is not None}")
            logger.info(f"[DEBUG] has_refresh_token: {secret.youtube_refresh_token_encrypted is not None}")
            
            if has_youtube_auth:
                logger.info(f"[DEBUG] has_youtube_auth is True, returning authenticated")
                # For now, just return authenticated if tokens exist
                # We can add channel info verification later once basic auth works
                return {
                    "is_authenticated": True,
                    "channel_id": None,  # Will add this back once we fix the basic auth
                    "channel_title": None,  # Will add this back once we fix the basic auth
                    "authenticated_at": secret.youtube_tokens_updated_at.isoformat() if secret.youtube_tokens_updated_at else None
                }
            
            return {
                "is_authenticated": False,
                "channel_id": None,
                "channel_title": None,
                "authenticated_at": None
            }
            
        except Exception as e:
            return {
                "is_authenticated": False,
                "channel_id": None,
                "channel_title": None,
                "authenticated_at": None
            } 