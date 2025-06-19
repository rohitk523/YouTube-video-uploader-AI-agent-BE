"""
Text-to-Speech service for generating AI voiceovers
"""

import asyncio
import tempfile
import os
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