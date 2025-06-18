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
    
    def __init__(self, progress_callback: Optional[Callable] = None):
        """
        Initialize YouTube service with specialized services.
        
        Args:
            progress_callback: Optional callback for progress updates
        """
        self.progress_callback = progress_callback
        self.tts_service = TTSService()
        self.video_service = VideoService()
        self.youtube_upload_service = YouTubeUploadService()
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
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create YouTube short with full processing pipeline.
        
        Args:
            job_id: Job UUID for progress tracking
            video_path: S3 URL or path to input video file
            transcript: Text for TTS generation
            title: Video title
            description: Video description
            voice: TTS voice to use
            tags: List of video tags
            
        Returns:
            Dict with processing results
            
        Raises:
            Exception: If processing fails
        """
        try:
            # Update progress: Starting
            await self._update_progress(job_id, 5, "Initializing video processing...")
            
            # Step 1: Download video from S3 if needed
            local_video_path = video_path
            if video_path.startswith(("http://", "https://", "s3://")):
                await self._update_progress(job_id, 10, "Downloading video from cloud storage...")
                download_result = await self.video_service.download_video_from_s3(video_path)
                if download_result["status"] == "error":
                    raise Exception(download_result["error_message"])
                local_video_path = download_result["local_path"]
                self.temp_files.append(local_video_path)
                await self._update_progress(job_id, 15, "Video downloaded successfully")
            
            # Step 2: Process video for YouTube Shorts format
            await self._update_progress(job_id, 20, "Processing video for YouTube Shorts format...")
            video_result = await self.video_service.process_video_for_shorts(
                local_video_path, target_duration=60
            )
            if video_result["status"] == "error":
                raise Exception(video_result["error_message"])
            
            processed_video_path = video_result["output_path"]
            self.temp_files.append(processed_video_path)
            await self._update_progress(job_id, 35, "Video processed for Shorts format")
            
            # Step 3: Generate TTS audio
            await self._update_progress(job_id, 40, "Generating AI voiceover...")
            audio_result = await self.tts_service.generate_speech(
                text=transcript,
                voice=voice,
                model="tts-1",
                speed=1.0
            )
            if audio_result["status"] == "error":
                raise Exception(audio_result["error_message"])
            
            audio_path = audio_result["audio_path"]
            self.temp_files.append(audio_path)
            await self._update_progress(job_id, 55, "AI voiceover generated successfully")
            
            # Step 4: Combine video and audio
            await self._update_progress(job_id, 60, "Combining video with AI voiceover...")
            combine_result = await self.video_service.combine_video_with_audio(
                video_path=processed_video_path,
                audio_path=audio_path,
                output_title=title
            )
            if combine_result["status"] == "error":
                raise Exception(combine_result["error_message"])
            
            final_video_path = combine_result["output_path"]
            self.temp_files.append(final_video_path)
            await self._update_progress(job_id, 75, "Video and audio combined successfully")
            
            # Step 5: Upload to YouTube
            await self._update_progress(job_id, 80, "Uploading to YouTube...")
            upload_result = await self.youtube_upload_service.upload_video_to_youtube(
                video_path=final_video_path,
                title=title,
                description=description,
                tags=tags or [],
                category="entertainment",
                privacy="public"
            )
            if upload_result["status"] == "error":
                raise Exception(upload_result["error_message"])
            
            await self._update_progress(job_id, 100, "Successfully uploaded to YouTube!")
            
            # Prepare comprehensive result
            result = {
                "status": "success",
                "youtube_url": upload_result["video_url"],
                "youtube_video_id": upload_result["video_id"],
                "shorts_url": upload_result.get("shorts_url"),
                "final_video_path": final_video_path,
                "processing_steps": {
                    "video_download": download_result if video_path != local_video_path else None,
                    "video_processing": video_result,
                    "audio_generation": audio_result,
                    "video_combination": combine_result,
                    "youtube_upload": upload_result
                },
                "metadata": {
                    "original_video_duration": video_result.get("original_info", {}).get("duration"),
                    "final_video_duration": combine_result.get("duration"),
                    "audio_duration": audio_result.get("duration"),
                    "file_size_mb": combine_result.get("file_size_mb"),
                    "voice_used": voice,
                    "video_resolution": "1080x1920",
                    "temp_files_created": len(self.temp_files)
                }
            }
            
            return result
            
        except Exception as e:
            await self._update_progress(job_id, -1, f"Error: {str(e)}")
            raise e
    
    async def validate_processing_requirements(self) -> Dict[str, Any]:
        """
        Validate that all required tools and services are available.
        
        Returns:
            Dict with validation results
        """
        requirements = {
            "ffmpeg_available": self.video_service._check_ffmpeg_available(),
            "ffprobe_available": self.video_service._check_ffprobe_available(),
            "openai_configured": bool(settings.openai_api_key),
            "youtube_configured": bool(
                getattr(settings, 'youtube_api_key', None) or 
                getattr(settings, 'youtube_client_secrets_file', None)
            )
        }
        
        missing_requirements = []
        
        if not requirements["ffmpeg_available"]:
            missing_requirements.append("FFmpeg is required for video processing")
        
        if not requirements["ffprobe_available"]:
            missing_requirements.append("FFprobe is required for video analysis")
        
        if not requirements["openai_configured"]:
            missing_requirements.append("OpenAI API key is required for TTS generation")
        
        # YouTube is optional for mock mode
        if not requirements["youtube_configured"]:
            missing_requirements.append("YouTube API credentials are recommended for real uploads")
        
        return {
            "all_requirements_met": len(missing_requirements) == 0,
            "requirements": requirements,
            "missing_requirements": missing_requirements,
            "installation_notes": {
                "ffmpeg": "Install FFmpeg: https://ffmpeg.org/download.html",
                "openai": "Set OPENAI_API_KEY environment variable",
                "youtube": "Configure YouTube API credentials (see setup instructions)"
            }
        }
    
    def get_supported_voices(self) -> List[str]:
        """
        Get list of supported TTS voices.
        
        Returns:
            List of supported voice names
        """
        return self.supported_voices.copy()
    
    def get_voice_info(self) -> Dict[str, Any]:
        """
        Get detailed voice information.
        
        Returns:
            Dict with voice information
        """
        return self.tts_service.get_voice_info()
    
    async def get_processing_capabilities(self) -> Dict[str, Any]:
        """
        Get information about processing capabilities.
        
        Returns:
            Dict with capabilities information
        """
        requirements = await self.validate_processing_requirements()
        
        return {
            "video_processing": {
                "supported_formats": self.video_service.supported_formats,
                "target_resolution": "1080x1920",
                "max_duration": 60,
                "output_format": "mp4"
            },
            "audio_generation": {
                "service": "OpenAI TTS",
                "supported_voices": self.supported_voices,
                "supported_formats": ["mp3", "opus", "aac", "flac"],
                "character_limit": 4096,
                "speed_range": {"min": 0.25, "max": 4.0}
            },
            "youtube_upload": {
                "supported_categories": list(self.youtube_upload_service.supported_categories.keys()),
                "privacy_options": ["public", "unlisted", "private"],
                "real_uploads_enabled": requirements["requirements"]["youtube_configured"]
            },
            "requirements_status": requirements,
            "estimated_processing_time": "2-5 minutes per video"
        }
    
    async def cleanup_temp_files(self) -> Dict[str, Any]:
        """
        Clean up all temporary files created during processing.
        
        Returns:
            Dict with cleanup results
        """
        if not self.temp_files:
            return {
                "cleaned_files": 0,
                "message": "No temporary files to clean up"
            }
        
        # Clean up TTS files
        tts_cleanup = await self.tts_service.cleanup_temp_files(self.temp_files)
        
        # Clean up video files 
        video_cleanup = await self.video_service.cleanup_temp_files(self.temp_files)
        
        total_cleaned = tts_cleanup["cleaned_files"] + video_cleanup["cleaned_files"]
        total_failed = tts_cleanup["failed_files"] + video_cleanup["failed_files"]
        
        # Clear the temp files list
        self.temp_files.clear()
        
        return {
            "cleaned_files": total_cleaned,
            "failed_files": total_failed,
            "tts_cleanup": tts_cleanup,
            "video_cleanup": video_cleanup
        }
    
    async def _update_progress(self, job_id: UUID, progress: int, message: str):
        """
        Update job progress.
        
        Args:
            job_id: Job UUID
            progress: Progress percentage (0-100, -1 for error)
            message: Progress message
        """
        if self.progress_callback:
            await self.progress_callback(job_id, progress, message)
    
    async def get_youtube_guidelines(self) -> Dict[str, Any]:
        """
        Get YouTube upload guidelines and optimization tips.
        
        Returns:
            Dict with guidelines
        """
        return self.youtube_upload_service.get_upload_guidelines()
    
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
                    "OPENAI_API_KEY": "OpenAI API key for TTS generation",
                    "YOUTUBE_API_KEY": "YouTube Data API key (optional)",
                    "YOUTUBE_CLIENT_SECRETS_FILE": "Path to YouTube OAuth2 credentials"
                }
            },
            "quick_start": [
                "1. Install FFmpeg on your system",
                "2. Set OPENAI_API_KEY environment variable", 
                "3. Configure YouTube API credentials (optional)",
                "4. Test with a small video file first"
            ]
        } 