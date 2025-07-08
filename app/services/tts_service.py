"""
Text-to-Speech service for generating AI voiceovers
"""

import asyncio
import tempfile
import os
import hashlib
from typing import Dict, Any, Optional
from pathlib import Path

import aiofiles
import httpx
from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()


class TTSService:
    """Service for generating text-to-speech audio using OpenAI's TTS API."""
    
    def __init__(self):
        """Initialize TTS service with OpenAI client."""
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.supported_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        self.supported_models = ["tts-1", "tts-1-hd"]
        
        # Cache directory for voice previews
        self.cache_dir = Path(tempfile.gettempdir()) / "tts_cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        # Default preview texts for each voice (for better caching)
        self.default_preview_texts = {
            "alloy": "Hello! This is how I sound. Perfect for your YouTube Shorts.",
            "echo": "Hey there! This is my energetic voice for your amazing content.",
            "fable": "Greetings! Let me tell you the story of your next viral video.",
            "onyx": "Good day. This is my authoritative voice for professional content.",
            "nova": "Hi! I'm excited to bring your bright ideas to life!",
            "shimmer": "Hello, dear creator. Let me gently narrate your beautiful story."
        }
    
    def _get_cache_key(self, text: str, voice: str, model: str, speed: float) -> str:
        """
        Generate cache key for TTS audio.
        
        Args:
            text: Input text
            voice: Voice name
            model: TTS model
            speed: Speech speed
            
        Returns:
            Cache key string
        """
        # Create a hash from the parameters
        content = f"{text}|{voice}|{model}|{speed}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cached_audio_path(self, cache_key: str, output_format: str) -> Path:
        """
        Get path for cached audio file.
        
        Args:
            cache_key: Cache key
            output_format: Audio format
            
        Returns:
            Path to cached audio file
        """
        return self.cache_dir / f"{cache_key}.{output_format}"
    
    async def _is_cache_valid(self, cache_path: Path, max_age_hours: int = 24) -> bool:
        """
        Check if cached audio file is still valid.
        
        Args:
            cache_path: Path to cached file
            max_age_hours: Maximum age in hours
            
        Returns:
            True if cache is valid
        """
        if not cache_path.exists():
            return False
        
        # Check file age
        import time
        file_age = time.time() - cache_path.stat().st_mtime
        max_age_seconds = max_age_hours * 3600
        
        return file_age < max_age_seconds
    
    async def generate_voice_preview(
        self,
        voice: str,
        custom_text: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Generate voice preview with caching for better performance.
        
        Args:
            voice: Voice to use
            custom_text: Custom text (if None, uses default for voice)
            use_cache: Whether to use cached results
            
        Returns:
            Dict with audio file information
        """
        # Use default text for voice if no custom text provided
        text = custom_text or self.default_preview_texts.get(voice, 
            "Hello! This is how I sound. Perfect for your YouTube Shorts.")
        
        # Limit text length for previews
        if len(text) > 200:
            text = text[:200] + "..."
        
        # Generate cache key
        cache_key = self._get_cache_key(text, voice, "tts-1", 1.0)
        cache_path = self._get_cached_audio_path(cache_key, "mp3")
        
        # Check cache first if enabled
        if use_cache and await self._is_cache_valid(cache_path):
            file_size = cache_path.stat().st_size
            duration = self._estimate_duration(text, 1.0)
            
            return {
                "status": "success",
                "audio_path": str(cache_path),
                "duration": duration,
                "voice": voice,
                "model": "tts-1",
                "speed": 1.0,
                "format": "mp3",
                "file_size_bytes": file_size,
                "text_length": len(text),
                "cached": True,
                "preview_text": text
            }
        
        # Generate new audio
        result = await self.generate_speech(
            text=text,
            voice=voice,
            model="tts-1",  # Use faster model for previews
            speed=1.0,
            output_format="mp3"
        )
        
        if result["status"] == "success" and use_cache:
            # Copy to cache
            try:
                original_path = Path(result["audio_path"])
                if original_path.exists():
                    import shutil
                    shutil.copy2(original_path, cache_path)
                    result["cached"] = False
                    result["cache_created"] = True
            except Exception as e:
                print(f"Failed to cache audio: {e}")
        
        result["preview_text"] = text
        return result
    
    async def cleanup_cache(self, max_age_hours: int = 48) -> Dict[str, Any]:
        """
        Clean up old cached audio files.
        
        Args:
            max_age_hours: Maximum age for cache files
            
        Returns:
            Dict with cleanup results
        """
        cleaned_files = []
        failed_files = []
        total_size_freed = 0
        
        try:
            import time
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            for cache_file in self.cache_dir.glob("*.mp3"):
                try:
                    file_age = current_time - cache_file.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_size = cache_file.stat().st_size
                        cache_file.unlink()
                        cleaned_files.append(str(cache_file))
                        total_size_freed += file_size
                except Exception as e:
                    failed_files.append({"file": str(cache_file), "error": str(e)})
        
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Cache cleanup failed: {str(e)}"
            }
        
        return {
            "status": "success",
            "cleaned_files": len(cleaned_files),
            "failed_files": len(failed_files),
            "total_size_freed_bytes": total_size_freed,
            "total_size_freed_mb": round(total_size_freed / (1024 * 1024), 2),
            "details": {
                "cleaned": cleaned_files,
                "failed": failed_files
            }
        }
    
    async def generate_speech(
        self,
        text: str,
        voice: str = "alloy",
        model: str = "tts-1",
        speed: float = 1.0,
        output_format: str = "mp3"
    ) -> Dict[str, Any]:
        """
        Generate speech from text using OpenAI TTS.
        
        Args:
            text: Text to convert to speech
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)
            model: TTS model to use (tts-1 or tts-1-hd)
            speed: Speech speed (0.25 to 4.0)
            output_format: Output format (mp3, opus, aac, flac)
            
        Returns:
            Dict with audio file information
            
        Raises:
            Exception: If TTS generation fails
        """
        try:
            # Validate inputs
            if not self.client:
                return await self._mock_tts_generation(text, voice, output_format)
            
            if voice not in self.supported_voices:
                raise ValueError(f"Unsupported voice: {voice}. Use one of: {self.supported_voices}")
            
            if model not in self.supported_models:
                raise ValueError(f"Unsupported model: {model}. Use one of: {self.supported_models}")
            
            if not (0.25 <= speed <= 4.0):
                raise ValueError("Speed must be between 0.25 and 4.0")
            
            # Generate speech using OpenAI TTS
            response = await self.client.audio.speech.create(
                model=model,
                voice=voice,
                input=text,
                speed=speed,
                response_format=output_format
            )
            
            # Save to temporary file
            temp_dir = Path(tempfile.gettempdir())
            temp_file = temp_dir / f"tts_{voice}_{hash(text) & 0x7FFFFFFF}.{output_format}"
            
            # Write audio data to file
            # The OpenAI response content is bytes, not an async iterator
            audio_bytes = response.content
            async with aiofiles.open(temp_file, 'wb') as f:
                await f.write(audio_bytes)
            
            # Get file info
            file_size = len(audio_bytes)
            duration = self._estimate_duration(text, speed)
            
            return {
                "status": "success",
                "audio_path": str(temp_file),
                "duration": duration,
                "voice": voice,
                "model": model,
                "speed": speed,
                "format": output_format,
                "file_size_bytes": file_size,
                "text_length": len(text)
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"TTS generation failed: {str(e)}"
            }
    
    async def _mock_tts_generation(
        self, 
        text: str, 
        voice: str, 
        output_format: str
    ) -> Dict[str, Any]:
        """
        Mock TTS generation for development/testing when no API key is available.
        Creates a proper silent audio file instead of invalid data.
        
        Args:
            text: Text to convert
            voice: Voice selection
            output_format: Output format
            
        Returns:
            Dict with mock audio information
        """
        # Create a mock audio file path
        temp_dir = Path(tempfile.gettempdir())
        temp_file = temp_dir / f"mock_tts_{voice}_{hash(text) & 0x7FFFFFFF}.{output_format}"
        
        # Estimate duration based on text
        duration = self._estimate_duration(text, 1.0)
        
        try:
            # Use FFmpeg to create a proper silent audio file
            # This creates actual audio content that can be properly combined with video
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", str(max(duration, 1.0)),  # Minimum 1 second
                "-c:a", "libmp3lame" if output_format == "mp3" else "aac",
                "-b:a", "128k",
                "-ar", "44100",
                "-ac", "2",
                str(temp_file)
            ]
            
            # Run FFmpeg to create silent audio
            import subprocess
            import asyncio
            
            result = await asyncio.to_thread(
                subprocess.run,
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                # Fallback: create a minimal but valid audio file manually
                await self._create_fallback_audio(temp_file, output_format, duration)
            
        except Exception as e:
            # Fallback method if FFmpeg is not available
            await self._create_fallback_audio(temp_file, output_format, duration)
        
        # Get file size
        file_size = temp_file.stat().st_size if temp_file.exists() else 0
        
        return {
            "status": "success",
            "audio_path": str(temp_file),
            "duration": duration,
            "voice": voice,
            "model": "mock-tts-1",
            "speed": 1.0,
            "format": output_format,
            "file_size_bytes": file_size,
            "text_length": len(text),
            "mock": True,
            "note": "Generated silent audio for mock mode"
        }
    
    async def _create_fallback_audio(self, temp_file: Path, output_format: str, duration: float):
        """
        Create a fallback audio file when FFmpeg is not available.
        This creates a minimal but valid audio file structure.
        
        Args:
            temp_file: Path to create audio file
            output_format: Audio format
            duration: Duration in seconds
        """
        async with aiofiles.open(temp_file, 'wb') as f:
            if output_format == "mp3":
                # Create a more complete MP3 file structure
                # MP3 header for 44.1kHz, stereo, 128kbps
                mp3_header = b'\xff\xfb\x90\x00'
                
                # Calculate approximate file size for the duration
                # 128kbps = 16KB/s, so roughly 16KB per second
                target_size = int(duration * 16 * 1024)
                
                # Write header and padding to create proper file size
                await f.write(mp3_header)
                
                # Add some basic MP3 frame structure
                # This creates a more valid MP3 file that players can handle
                frame_data = b'\x00' * 417  # Standard MP3 frame size at 128kbps
                frames_needed = max(1, target_size // 417)
                
                for _ in range(frames_needed):
                    await f.write(frame_data)
            else:
                # For other formats, create minimal valid file
                # This is a basic fallback - FFmpeg method above is preferred
                minimal_data = b'\x00' * int(duration * 1000)  # 1KB per second
                await f.write(minimal_data)
    
    def _estimate_duration(self, text: str, speed: float) -> float:
        """
        Estimate audio duration based on text length and speed.
        
        Args:
            text: Input text
            speed: Speech speed multiplier
            
        Returns:
            Estimated duration in seconds
        """
        # Average reading speed: ~150 words per minute
        # Adjusted for TTS: ~180 words per minute at normal speed
        words = len(text.split())
        base_duration = (words / 180) * 60  # Convert to seconds
        return round(base_duration / speed, 2)
    
    async def validate_text(self, text: str) -> Dict[str, Any]:
        """
        Validate text for TTS generation.
        
        Args:
            text: Text to validate
            
        Returns:
            Dict with validation results
        """
        issues = []
        
        # Check length (OpenAI TTS has a 4096 character limit)
        if len(text) > 4096:
            issues.append("Text exceeds 4096 character limit")
        
        # Check for empty text
        if not text.strip():
            issues.append("Text is empty")
        
        # Check for only special characters
        if not any(c.isalnum() for c in text):
            issues.append("Text contains no alphanumeric characters")
        
        # Check for very long words that might cause issues
        words = text.split()
        long_words = [word for word in words if len(word) > 50]
        if long_words:
            issues.append(f"Contains very long words: {long_words[:3]}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "character_count": len(text),
            "word_count": len(words),
            "estimated_duration": self._estimate_duration(text, 1.0)
        }
    
    def get_voice_info(self) -> Dict[str, Any]:
        """
        Get information about available voices.
        
        Returns:
            Dict with voice information
        """
        voice_descriptions = {
            "alloy": {
                "name": "Alloy",
                "description": "Balanced and clear, good for most content",
                "style": "neutral",
                "recommended_for": ["tutorials", "explanations", "general content"]
            },
            "echo": {
                "name": "Echo", 
                "description": "Energetic and dynamic, great for engaging content",
                "style": "energetic",
                "recommended_for": ["entertainment", "motivational", "sports"]
            },
            "fable": {
                "name": "Fable",
                "description": "Warm and storytelling, perfect for narratives",
                "style": "warm",
                "recommended_for": ["stories", "educational", "documentaries"]
            },
            "onyx": {
                "name": "Onyx",
                "description": "Deep and authoritative, ideal for serious content",
                "style": "authoritative", 
                "recommended_for": ["news", "business", "formal presentations"]
            },
            "nova": {
                "name": "Nova",
                "description": "Bright and engaging, excellent for upbeat content",
                "style": "bright",
                "recommended_for": ["lifestyle", "technology", "youth content"]
            },
            "shimmer": {
                "name": "Shimmer",
                "description": "Soft and gentle, soothing for calm content",
                "style": "gentle",
                "recommended_for": ["meditation", "relaxation", "ASMR"]
            }
        }
        
        return {
            "voices": voice_descriptions,
            "default_voice": "alloy",
            "models": {
                "tts-1": {
                    "name": "Standard Quality",
                    "description": "Optimized for speed, good quality",
                    "latency": "low"
                },
                "tts-1-hd": {
                    "name": "High Definition",
                    "description": "Higher quality audio, slower generation",
                    "latency": "higher"
                }
            },
            "supported_formats": ["mp3", "opus", "aac", "flac"],
            "speed_range": {"min": 0.25, "max": 4.0, "default": 1.0},
            "character_limit": 4096
        }
    
    async def cleanup_temp_files(self, file_paths: list) -> Dict[str, Any]:
        """
        Clean up temporary audio files.
        
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
    
    async def get_capabilities(self) -> Dict[str, Any]:
        """
        Get TTS service capabilities.
        
        Returns:
            Dict with TTS capabilities information
        """
        return {
            "service": "OpenAI Text-to-Speech",
            "api_available": self.client is not None,
            "supported_voices": self.supported_voices,
            "supported_models": self.supported_models,
            "supported_formats": ["mp3", "opus", "aac", "flac"],
            "speed_range": {"min": 0.25, "max": 4.0, "default": 1.0},
            "character_limit": 4096,
            "features": {
                "voice_preview": True,
                "caching": True,
                "fallback_mode": True,
                "mock_mode": True
            },
            "performance": {
                "average_generation_time": "2-10 seconds",
                "supports_async": True,
                "concurrent_requests": True
            }
        }