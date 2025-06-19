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
            
            # Validate audio file has actual content
            if audio_info.get("status") == "error":
                raise Exception(f"Invalid audio file: {audio_info.get('error_message')}")
            
            # Check if audio has duration > 0
            audio_duration = audio_info.get("duration", 0)
            if audio_duration <= 0:
                raise Exception(f"Audio file has no duration or is invalid: {audio_duration}s")
            
            # Test audio file to ensure it's actually decodable
            audio_test = await self.test_audio_file(audio_path)
            if audio_test.get("status") == "error":
                raise Exception(f"Audio file failed validation: {audio_test.get('error_message')}")
            elif audio_test.get("status") == "warning":
                print(f"Warning about audio file: {audio_test.get('warning_message')}")
            
            # Build FFmpeg command with explicit stream mapping and better audio handling
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", video_path,      # Input 0: video
                "-i", audio_path,      # Input 1: audio
                "-map", "0:v:0",       # Map first video stream from input 0
                "-map", "1:a:0",       # Map first audio stream from input 1
                "-c:v", "copy",        # Copy video stream as-is
                "-c:a", "aac",         # Re-encode audio as AAC
                "-b:a", "128k",        # Audio bitrate
                "-ar", "44100",        # Audio sample rate
                "-ac", "2",            # Stereo audio
                "-af", "volume=1.0",   # Ensure audio volume is normalized
                "-shortest",           # Use shortest duration
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",  # Handle timestamp issues
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
                # Log the full FFmpeg error for debugging
                error_details = f"FFmpeg stderr: {result.stderr}\nFFmpeg stdout: {result.stdout}"
                raise Exception(f"FFmpeg combination failed: {error_details}")
            
            # Verify output exists and has content
            if not output_file.exists():
                raise Exception("Combined video file was not created")
            
            output_size = output_file.stat().st_size
            if output_size == 0:
                raise Exception("Combined video file is empty")
            
            final_info = await self.get_video_info(str(output_file))
            
            # Verify the final video has audio
            final_audio_info = await self.get_audio_info(str(output_file))
            if final_audio_info.get("status") == "error":
                print(f"Warning: Combined video may not have audio: {final_audio_info.get('error_message')}")
            
            # Additional verification to check if audio is actually audible
            audio_verification = await self.verify_video_has_audio(str(output_file))
            if audio_verification.get("status") == "error":
                print(f"Error: Final video audio verification failed: {audio_verification.get('error_message')}")
            elif audio_verification.get("status") == "warning":
                print(f"Warning: {audio_verification.get('warning_message')}")
            
            return {
                "status": "success",
                "output_path": str(output_file),
                "file_size_bytes": output_size,
                "file_size_mb": round(output_size / (1024 * 1024), 2),
                "duration": final_info.get("duration", 0),
                "title": output_title,
                "video_info": video_info,
                "audio_info": audio_info,
                "final_audio_check": final_audio_info,
                "audio_verification": audio_verification,
                "audio_test_result": audio_test,
                "ffmpeg_command": " ".join(ffmpeg_cmd)  # For debugging
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
    
    async def test_audio_file(self, audio_path: str) -> Dict[str, Any]:
        """
        Test if an audio file is valid and playable.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Dict with test results
        """
        try:
            if not os.path.exists(audio_path):
                return {
                    "status": "error",
                    "error_message": f"Audio file not found: {audio_path}"
                }
            
            # Get basic file info
            file_size = os.path.getsize(audio_path)
            if file_size == 0:
                return {
                    "status": "error",
                    "error_message": "Audio file is empty"
                }
            
            # Use ffprobe to analyze the audio
            ffprobe_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,sample_rate,channels,duration",
                "-show_entries", "format=duration,bit_rate",
                "-of", "csv=p=0",
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
                return {
                    "status": "error",
                    "error_message": f"Failed to analyze audio file: {result.stderr}"
                }
            
            # Test if FFmpeg can actually decode the audio
            test_cmd = [
                "ffmpeg", "-v", "error",
                "-i", audio_path,
                "-f", "null",
                "-t", "1",  # Test only first second
                "-"
            ]
            
            test_result = await asyncio.to_thread(
                subprocess.run,
                test_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if test_result.returncode != 0:
                return {
                    "status": "warning",
                    "warning_message": f"Audio file may have decoding issues: {test_result.stderr}",
                    "file_size": file_size
                }
            
            return {
                "status": "success",
                "file_size": file_size,
                "decodable": True,
                "message": "Audio file is valid and decodable"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Audio test failed: {str(e)}"
            }
    
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
    
    async def verify_video_has_audio(self, video_path: str) -> Dict[str, Any]:
        """
        Verify that a video file contains audible audio content.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dict with verification results
        """
        try:
            if not os.path.exists(video_path):
                return {
                    "status": "error",
                    "error_message": f"Video file not found: {video_path}"
                }
            
            # Check if video has audio streams
            ffprobe_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_name,sample_rate,channels,duration",
                "-of", "csv=p=0",
                video_path
            ]
            
            result = await asyncio.to_thread(
                subprocess.run,
                ffprobe_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                return {
                    "status": "error",
                    "error_message": "Video file has no audio streams"
                }
            
            # Extract a small audio sample and check if it has content
            # This creates a temporary audio file to analyze
            import tempfile
            temp_audio = tempfile.mktemp(suffix=".wav")
            
            try:
                extract_cmd = [
                    "ffmpeg", "-y", "-v", "error",
                    "-i", video_path,
                    "-vn",  # No video
                    "-acodec", "pcm_s16le",
                    "-ar", "44100",
                    "-ac", "2",
                    "-t", "5",  # Extract first 5 seconds
                    temp_audio
                ]
                
                extract_result = await asyncio.to_thread(
                    subprocess.run,
                    extract_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if extract_result.returncode != 0:
                    return {
                        "status": "warning",
                        "warning_message": f"Could not extract audio for analysis: {extract_result.stderr}"
                    }
                
                # Check if extracted audio file has content
                if os.path.exists(temp_audio):
                    audio_size = os.path.getsize(temp_audio)
                    # A 5-second stereo 44.1kHz 16-bit audio should be ~440KB
                    # If it's much smaller, it might be silent
                    expected_min_size = 5 * 44100 * 2 * 2 * 0.1  # 10% of expected size
                    
                    if audio_size < expected_min_size:
                        return {
                            "status": "warning",
                            "warning_message": f"Audio content appears to be mostly silent (size: {audio_size} bytes)"
                        }
                    
                    return {
                        "status": "success",
                        "message": "Video has audible audio content",
                        "audio_size_bytes": audio_size
                    }
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_audio):
                    try:
                        os.remove(temp_audio)
                    except:
                        pass
            
            return {
                "status": "warning",
                "warning_message": "Could not verify audio content"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Audio verification failed: {str(e)}"
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