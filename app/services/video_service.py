"""
Video processing service for YouTube Shorts creation
"""

import asyncio
import tempfile
import os
import subprocess
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import shutil

import aiofiles
import httpx

from app.config import get_settings

settings = get_settings()


class VideoService:
    """Service for video processing and manipulation."""
    
    def __init__(self):
        """Initialize video service."""
        self.temp_dir = Path(tempfile.gettempdir())
        self.supported_formats = ["mp4", "mov", "avi", "mkv", "webm"]
        self.target_resolution = (1080, 1920)  # YouTube Shorts format
        self.max_duration = 60  # seconds
    
    async def download_video_from_s3(self, s3_url: str) -> Dict[str, Any]:
        """
        Download video from S3 URL to local temporary file.
        
        Args:
            s3_url: S3 URL or HTTPS URL to video file
            
        Returns:
            Dict with download information
        """
        try:
            if not s3_url:
                raise ValueError("S3 URL is required")
            
            # Generate temporary file path
            file_extension = self._extract_file_extension(s3_url)
            temp_file = self.temp_dir / f"download_{hash(s3_url) & 0x7FFFFFFF}.{file_extension}"
            
            # Handle different URL types
            if s3_url.startswith("s3://"):
                # Handle s3:// URLs using boto3
                await self._download_from_s3_boto3(s3_url, temp_file)
            elif s3_url.startswith(("http://", "https://")):
                # Handle HTTPS URLs directly
                await self._download_from_https(s3_url, temp_file)
            else:
                raise ValueError(f"Unsupported URL protocol: {s3_url}")
            
            # Verify file was downloaded
            if not temp_file.exists():
                raise Exception("File was not downloaded successfully")
            
            file_size = temp_file.stat().st_size
            
            return {
                "status": "success",
                "local_path": str(temp_file),
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "original_url": s3_url
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Video download failed: {str(e)}"
            }
    
    async def _download_from_s3_boto3(self, s3_url: str, local_path: Path):
        """
        Download file from S3 using boto3.
        
        Args:
            s3_url: S3 URL in format s3://bucket/key
            local_path: Local file path to save to
        """
        try:
            # Parse S3 URL
            s3_parts = s3_url.replace("s3://", "").split("/", 1)
            if len(s3_parts) != 2:
                raise ValueError(f"Invalid S3 URL format: {s3_url}")
            
            bucket_name, key = s3_parts
            
            # Initialize S3 client
            import boto3
            from app.config import get_settings
            
            settings = get_settings()
            
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region
            )
            
            # Download file
            await asyncio.to_thread(
                s3_client.download_file,
                bucket_name,
                key,
                str(local_path)
            )
            
        except Exception as e:
            # If boto3 fails, try converting to presigned URL
            try:
                presigned_url = await self._get_presigned_url(s3_url)
                await self._download_from_https(presigned_url, local_path)
            except Exception as fallback_error:
                raise Exception(f"S3 download failed: {str(e)}. Fallback also failed: {str(fallback_error)}")
    
    async def _download_from_https(self, url: str, local_path: Path):
        """
        Download file from HTTPS URL.
        
        Args:
            url: HTTPS URL
            local_path: Local file path to save to
        """
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                
                async with aiofiles.open(local_path, 'wb') as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        await f.write(chunk)
    
    async def _get_presigned_url(self, s3_url: str, expiry: int = 3600) -> str:
        """
        Convert S3 URL to presigned HTTPS URL.
        
        Args:
            s3_url: S3 URL in format s3://bucket/key
            expiry: URL expiry time in seconds
            
        Returns:
            Presigned HTTPS URL
        """
        try:
            # Parse S3 URL
            s3_parts = s3_url.replace("s3://", "").split("/", 1)
            if len(s3_parts) != 2:
                raise ValueError(f"Invalid S3 URL format: {s3_url}")
            
            bucket_name, key = s3_parts
            
            # Initialize S3 client
            import boto3
            from app.config import get_settings
            
            settings = get_settings()
            
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region
            )
            
            # Generate presigned URL
            presigned_url = await asyncio.to_thread(
                s3_client.generate_presigned_url,
                'get_object',
                Params={'Bucket': bucket_name, 'Key': key},
                ExpiresIn=expiry
            )
            
            return presigned_url
            
        except Exception as e:
            raise Exception(f"Failed to generate presigned URL: {str(e)}")
    
    async def process_video_for_shorts(
        self, 
        input_path: str, 
        target_duration: int = 60
    ) -> Dict[str, Any]:
        """
        Process video for YouTube Shorts format.
        
        Args:
            input_path: Path to input video file
            target_duration: Target duration in seconds
            
        Returns:
            Dict with processing results
        """
        try:
            if not os.path.exists(input_path):
                raise FileNotFoundError(f"Input video not found: {input_path}")
            
            # Get video info first
            video_info = await self.get_video_info(input_path)
            if video_info["status"] == "error":
                return video_info
            
            # Generate output path
            output_file = self.temp_dir / f"processed_{hash(input_path) & 0x7FFFFFFF}.mp4"
            
            # Build FFmpeg command for YouTube Shorts format
            ffmpeg_cmd = [
                "ffmpeg", "-y",  # Overwrite output file
                "-i", input_path,
                "-vf", f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-ar", "44100",
                "-t", str(target_duration),  # Limit duration
                "-movflags", "+faststart",  # Optimize for web
                str(output_file)
            ]
            
            # Run FFmpeg
            result = await asyncio.to_thread(
                subprocess.run,
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg failed: {result.stderr}")
            
            # Verify output file
            if not output_file.exists():
                raise Exception("Processed video file was not created")
            
            # Get output file info
            output_size = output_file.stat().st_size
            output_info = await self.get_video_info(str(output_file))
            
            return {
                "status": "success",
                "output_path": str(output_file),
                "file_size_bytes": output_size,
                "file_size_mb": round(output_size / (1024 * 1024), 2),
                "duration": output_info.get("duration", target_duration),
                "resolution": "1080x1920",
                "format": "mp4",
                "original_info": video_info
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Video processing failed: {str(e)}"
            }
    
    async def combine_video_with_audio(
        self,
        video_path: str,
        audio_path: str,
        output_title: str = "combined_video"
    ) -> Dict[str, Any]:
        """
        Combine video with audio track.
        
        Args:
            video_path: Path to video file
            audio_path: Path to audio file
            output_title: Title for output file
            
        Returns:
            Dict with combination results
        """
        try:
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            # Generate output path
            safe_title = "".join(c for c in output_title if c.isalnum() or c in " -_").strip()
            output_file = self.temp_dir / f"{safe_title}_final.mp4"
            
            # Get video and audio durations
            video_info = await self.get_video_info(video_path)
            audio_info = await self.get_audio_info(audio_path)
            
            # Build FFmpeg command to combine video and audio
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",  # Copy video stream as-is
                "-c:a", "aac",   # Re-encode audio as AAC
                "-b:a", "128k",
                "-ar", "44100",
                "-shortest",  # Use shortest duration
                "-movflags", "+faststart",
                str(output_file)
            ]
            
            # Run FFmpeg
            result = await asyncio.to_thread(
                subprocess.run,
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg combination failed: {result.stderr}")
            
            # Verify output
            if not output_file.exists():
                raise Exception("Combined video file was not created")
            
            output_size = output_file.stat().st_size
            final_info = await self.get_video_info(str(output_file))
            
            return {
                "status": "success",
                "output_path": str(output_file),
                "file_size_bytes": output_size,
                "file_size_mb": round(output_size / (1024 * 1024), 2),
                "duration": final_info.get("duration", 0),
                "title": output_title,
                "video_info": video_info,
                "audio_info": audio_info
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Video-audio combination failed: {str(e)}"
            }
    
    async def get_video_info(self, video_path: str) -> Dict[str, Any]:
        """
        Get video file information using ffprobe.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dict with video information
        """
        try:
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            # Use ffprobe to get video info
            ffprobe_cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path
            ]
            
            result = await asyncio.to_thread(
                subprocess.run,
                ffprobe_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise Exception(f"ffprobe failed: {result.stderr}")
            
            import json
            probe_data = json.loads(result.stdout)
            
            # Extract relevant information
            format_info = probe_data.get("format", {})
            streams = probe_data.get("streams", [])
            
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
            
            duration = float(format_info.get("duration", 0))
            width = video_stream.get("width", 0)
            height = video_stream.get("height", 0)
            
            return {
                "status": "success",
                "duration": duration,
                "width": width,
                "height": height,
                "resolution": f"{width}x{height}",
                "video_codec": video_stream.get("codec_name"),
                "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
                "bitrate": int(format_info.get("bit_rate", 0)),
                "file_size": int(format_info.get("size", 0)),
                "format_name": format_info.get("format_name")
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Failed to get video info: {str(e)}"
            }
    
    async def get_audio_info(self, audio_path: str) -> Dict[str, Any]:
        """
        Get audio file information.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Dict with audio information
        """
        try:
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            ffprobe_cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                audio_path
            ]
            
            result = await asyncio.to_thread(
                subprocess.run,
                ffprobe_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise Exception(f"ffprobe failed: {result.stderr}")
            
            import json
            probe_data = json.loads(result.stdout)
            
            format_info = probe_data.get("format", {})
            streams = probe_data.get("streams", [])
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
            
            return {
                "status": "success",
                "duration": float(format_info.get("duration", 0)),
                "codec": audio_stream.get("codec_name"),
                "sample_rate": int(audio_stream.get("sample_rate", 0)),
                "channels": int(audio_stream.get("channels", 0)),
                "bitrate": int(format_info.get("bit_rate", 0)),
                "file_size": int(format_info.get("size", 0))
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Failed to get audio info: {str(e)}"
            }
    
    def _extract_file_extension(self, url: str) -> str:
        """Extract file extension from URL."""
        path = url.split('?')[0]  # Remove query parameters
        extension = Path(path).suffix.lstrip('.')
        return extension if extension in self.supported_formats else "mp4"
    
    def _check_ffmpeg_available(self) -> bool:
        """Check if FFmpeg is available."""
        try:
            subprocess.run(["ffmpeg", "-version"], 
                         capture_output=True, timeout=10)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def _check_ffprobe_available(self) -> bool:
        """Check if ffprobe is available."""
        try:
            subprocess.run(["ffprobe", "-version"], 
                         capture_output=True, timeout=10)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    async def validate_video_file(self, video_path: str) -> Dict[str, Any]:
        """
        Validate video file for processing.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dict with validation results
        """
        try:
            if not os.path.exists(video_path):
                return {
                    "valid": False,
                    "error": "Video file not found"
                }
            
            # Check file size
            file_size = os.path.getsize(video_path)
            max_size = settings.max_file_size_mb * 1024 * 1024
            
            if file_size > max_size:
                return {
                    "valid": False,
                    "error": f"File too large. Maximum size: {settings.max_file_size_mb}MB"
                }
            
            # Check if FFmpeg tools are available
            if not self._check_ffmpeg_available():
                return {
                    "valid": False,
                    "error": "FFmpeg not available for video processing"
                }
            
            # Get video info to validate format
            video_info = await self.get_video_info(video_path)
            if video_info["status"] == "error":
                return {
                    "valid": False,
                    "error": video_info["error_message"]
                }
            
            # Check duration
            duration = video_info.get("duration", 0)
            if duration > 600:  # 10 minutes max
                return {
                    "valid": False,
                    "error": "Video too long. Maximum duration: 10 minutes"
                }
            
            return {
                "valid": True,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "duration": duration,
                "resolution": video_info.get("resolution"),
                "format": video_info.get("format_name")
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"Validation failed: {str(e)}"
            }
    
    async def cleanup_temp_files(self, file_paths: list) -> Dict[str, Any]:
        """
        Clean up temporary video files.
        
        Args:
            file_paths: List of file paths to clean up
            
        Returns:
            Dict with cleanup results
        """
        cleaned_files = []
        failed_files = []
        
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    cleaned_files.append(file_path)
            except Exception as e:
                failed_files.append({"file": file_path, "error": str(e)})
        
        return {
            "cleaned_files": len(cleaned_files),
            "failed_files": len(failed_files),
            "details": {
                "cleaned": cleaned_files,
                "failed": failed_files
            }
        } 