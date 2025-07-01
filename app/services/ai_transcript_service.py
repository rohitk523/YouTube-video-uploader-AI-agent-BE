"""
AI Transcript Generation service for creating YouTube Shorts scripts
"""

import asyncio
import os
from typing import Dict, Any, Optional
from pathlib import Path

import aiofiles
from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()

# Import Langfuse if configured
_langfuse_client = None
if settings.langfuse_configured:
    try:
        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_host
        )
    except ImportError:
        print("Warning: Langfuse not installed but configured. Install with: pip install langfuse")
    except Exception as e:
        print(f"Warning: Failed to initialize Langfuse: {e}")


class AITranscriptService:
    """Service for generating AI-powered YouTube Shorts transcripts."""
    
    def __init__(self):
        """Initialize AI transcript service with OpenAI client."""
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key is required for AI transcript generation")
        
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.langfuse = _langfuse_client
        self.prompt_file_path = Path(__file__).parent.parent.parent / "prompts" / "transcript_generation.txt"
        
        # Default model settings
        self.default_model = "gpt-4"
        self.fallback_model = "gpt-3.5-turbo"
        self.max_tokens = 500
        self.temperature = 0.7
        
    async def _load_prompt_template(self) -> str:
        """
        Load the prompt template from file.
        
        Returns:
            Prompt template string
        """
        try:
            if self.prompt_file_path.exists():
                async with aiofiles.open(self.prompt_file_path, 'r', encoding='utf-8') as f:
                    return await f.read()
            else:
                # Fallback prompt if file doesn't exist
                return self._get_fallback_prompt()
        except Exception as e:
            print(f"Warning: Failed to load prompt template: {e}")
            return self._get_fallback_prompt()
    
    def _get_fallback_prompt(self) -> str:
        """
        Get fallback prompt if file loading fails.
        
        Returns:
            Fallback prompt string
        """
        return """You are an expert YouTube Shorts script writer who creates engaging, viral content. 
        Create a compelling transcript for a YouTube Short based on the user's context.
        
        Guidelines:
        - Keep it 30-60 seconds when spoken (150-300 words)
        - Start with a strong hook
        - Use simple, conversational language
        - End with a call-to-action
        - Make it engaging and appropriate for all audiences
        
        Context: {context}
        
        Create an engaging YouTube Shorts transcript based on this context."""
    
    async def generate_transcript(
        self,
        context: str,
        user_id: Optional[str] = None,
        custom_instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate AI transcript based on user context.
        
        Args:
            context: User-provided context or topic
            user_id: Optional user ID for tracking
            custom_instructions: Additional instructions for the AI
            
        Returns:
            Dict with generated transcript and metadata
        """
        if not context or not context.strip():
            return {
                "status": "error",
                "error_message": "Context cannot be empty",
                "error_type": "validation_error"
            }
        
        # Start Langfuse trace if available
        trace = None
        if self.langfuse:
            try:
                trace = self.langfuse.trace(
                    name="ai_transcript_generation",
                    user_id=user_id,
                    metadata={
                        "context_length": len(context),
                        "has_custom_instructions": bool(custom_instructions)
                    }
                )
            except Exception as e:
                print(f"Warning: Failed to create Langfuse trace: {e}")
        
        try:
            # Load prompt template
            prompt_template = await self._load_prompt_template()
            
            # Format prompt with context
            formatted_prompt = prompt_template.format(context=context.strip())
            
            # Add custom instructions if provided
            if custom_instructions:
                formatted_prompt += f"\n\nAdditional Instructions: {custom_instructions}"
            
            # Log the generation attempt
            generation = None
            if trace:
                try:
                    generation = trace.generation(
                        name="openai_transcript_generation",
                        model=self.default_model,
                        input=formatted_prompt,
                        metadata={
                            "temperature": self.temperature,
                            "max_tokens": self.max_tokens
                        }
                    )
                except Exception as e:
                    print(f"Warning: Failed to create Langfuse generation: {e}")
            
            # Try with primary model first
            try:
                response = await self._generate_with_model(
                    prompt=formatted_prompt,
                    model=self.default_model
                )
            except Exception as e:
                print(f"Primary model failed, trying fallback: {e}")
                # Fallback to secondary model
                response = await self._generate_with_model(
                    prompt=formatted_prompt,
                    model=self.fallback_model
                )
            
            transcript = response.choices[0].message.content.strip()
            
            # Calculate metrics
            word_count = len(transcript.split())
            estimated_duration = self._estimate_speaking_duration(transcript)
            
            # Log successful generation
            if generation:
                try:
                    generation.end(
                        output=transcript,
                        usage={
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens
                        }
                    )
                except Exception as e:
                    print(f"Warning: Failed to end Langfuse generation: {e}")
            
            result = {
                "status": "success",
                "transcript": transcript,
                "word_count": word_count,
                "estimated_duration_seconds": estimated_duration,
                "model_used": response.model,
                "tokens_used": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                "context_provided": context[:100] + "..." if len(context) > 100 else context
            }
            
            # End trace successfully
            if trace:
                try:
                    trace.update(
                        output=result,
                        metadata={
                            **result,
                            "success": True
                        }
                    )
                except Exception as e:
                    print(f"Warning: Failed to update Langfuse trace: {e}")
            
            return result
            
        except Exception as e:
            error_message = f"Failed to generate transcript: {str(e)}"
            
            # Log error to Langfuse
            if trace:
                try:
                    trace.update(
                        metadata={
                            "error": error_message,
                            "success": False
                        }
                    )
                except Exception as langfuse_error:
                    print(f"Warning: Failed to log error to Langfuse: {langfuse_error}")
            
            return {
                "status": "error",
                "error_message": error_message,
                "error_type": "generation_error"
            }
    
    async def _generate_with_model(self, prompt: str, model: str):
        """
        Generate transcript using specified model.
        
        Args:
            prompt: Formatted prompt
            model: Model to use
            
        Returns:
            OpenAI response
        """
        return await self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert YouTube Shorts script writer. Create engaging, viral content that captures attention and drives engagement."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=0.9,
            frequency_penalty=0.1,
            presence_penalty=0.1
        )
    
    def _estimate_speaking_duration(self, text: str) -> float:
        """
        Estimate speaking duration in seconds.
        
        Args:
            text: Text to estimate duration for
            
        Returns:
            Estimated duration in seconds
        """
        # Average speaking rate is about 150-160 words per minute for engaging content
        words_per_minute = 155
        word_count = len(text.split())
        duration_minutes = word_count / words_per_minute
        duration_seconds = duration_minutes * 60
        
        # Add buffer for pauses and emphasis (10-15%)
        duration_with_buffer = duration_seconds * 1.12
        
        return round(duration_with_buffer, 1)
    
    async def validate_context(self, context: str) -> Dict[str, Any]:
        """
        Validate the provided context.
        
        Args:
            context: Context to validate
            
        Returns:
            Validation result
        """
        if not context or not context.strip():
            return {
                "valid": False,
                "error": "Context cannot be empty"
            }
        
        context = context.strip()
        
        # Check length constraints
        if len(context) < 10:
            return {
                "valid": False,
                "error": "Context too short. Please provide at least 10 characters."
            }
        
        if len(context) > 2000:
            return {
                "valid": False,
                "error": "Context too long. Please keep it under 2000 characters."
            }
        
        # Check for inappropriate content (basic check)
        inappropriate_terms = ['explicit', 'violence', 'hate', 'spam']
        context_lower = context.lower()
        for term in inappropriate_terms:
            if term in context_lower:
                return {
                    "valid": False,
                    "error": f"Context may contain inappropriate content. Please revise."
                }
        
        return {
            "valid": True,
            "character_count": len(context),
            "word_count": len(context.split()),
            "estimated_tokens": len(context) // 4  # Rough estimate
        }
    
    def get_service_info(self) -> Dict[str, Any]:
        """
        Get service information and status.
        
        Returns:
            Service information
        """
        return {
            "service_name": "AI Transcript Service",
            "openai_configured": bool(settings.openai_api_key),
            "langfuse_configured": settings.langfuse_configured,
            "langfuse_available": self.langfuse is not None,
            "prompt_file_exists": self.prompt_file_path.exists(),
            "default_model": self.default_model,
            "fallback_model": self.fallback_model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        } 