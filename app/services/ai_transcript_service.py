"""
AI Transcript Generation service for creating YouTube Shorts scripts
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional
from pathlib import Path

import aiofiles
from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()

# Set up logging
logger = logging.getLogger(__name__)

# Initialize Langfuse with environment variables
langfuse = None
if settings.langfuse_configured:
    try:
        from langfuse import Langfuse
        langfuse = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_host
        )
    except ImportError:
        logger.warning("Langfuse not installed but configured. Install with: pip install langfuse")
    except Exception as e:
        logger.warning(f"Failed to initialize Langfuse: {e}")


class AITranscriptService:
    """Service for generating AI-powered YouTube Shorts transcripts."""
    
    def __init__(self):
        """Initialize AI transcript service with OpenAI client."""
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key is required for AI transcript generation")
        
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.langfuse = langfuse
        
        # Set up prompt file path
        self.prompt_file_path = Path(__file__).parent.parent.parent / "prompts" / "transcript_generation.txt"
        
        # Default model settings
        self.default_model = "gpt-4"
        self.fallback_model = "gpt-3.5-turbo"
        self.max_tokens = 500
        self.temperature = 0.7
        
    async def _load_prompt_from_langfuse(self) -> str:
        """
        Load the prompt template from Langfuse prompt management.
        Falls back to file-based prompt, then hardcoded prompt if needed.
        
        Returns:
            Prompt template string
        """
        try:
            if self.langfuse:
                # Fetch the prompt from Langfuse
                prompt_response = self.langfuse.get_prompt("transcript_generation")
                if prompt_response and hasattr(prompt_response, 'prompt'):
                    logger.info("Successfully loaded prompt from Langfuse")
                    return prompt_response.prompt
                else:
                    logger.warning("Prompt 'transcript_generation' not found in Langfuse, falling back to file/hardcoded prompt")
                    return self._get_fallback_prompt()
            else:
                logger.info("Langfuse not configured, using file/hardcoded prompt fallback")
                return self._get_fallback_prompt()
        except Exception as e:
            logger.warning(f"Failed to load prompt from Langfuse: {e}, falling back to file/hardcoded prompt")
            return self._get_fallback_prompt()
    
    def _get_fallback_prompt(self) -> str:
        """
        Get fallback prompt if Langfuse prompt loading fails.
        Tries to read from transcript_generation.txt file first, then uses basic hardcoded prompt.
        
        Returns:
            Fallback prompt string
        """
        try:
            # Try to read from the prompt file
            if self.prompt_file_path.exists():
                with open(self.prompt_file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read().strip()
                    if file_content:
                        logger.info(f"Using prompt from file: {self.prompt_file_path}")
                        return file_content
                    else:
                        logger.warning(f"Prompt file is empty: {self.prompt_file_path}")
            else:
                logger.warning(f"Prompt file not found: {self.prompt_file_path}")
        except Exception as e:
            logger.warning(f"Failed to read prompt file {self.prompt_file_path}: {e}")
        
        # Last resort: basic hardcoded prompt
        logger.info("Using basic hardcoded fallback prompt")
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
        
        # Initialize tracing variables
        trace_id = None
        
        if self.langfuse:
            try:
                # Create a unique trace ID
                trace_id = self.langfuse.create_trace_id()
            except Exception as e:
                logger.warning(f"Failed to create Langfuse trace ID: {e}")
        
        try:
            # Load prompt template from Langfuse
            prompt_template = await self._load_prompt_from_langfuse()
            
            # Format prompt with context
            formatted_prompt = prompt_template.format(context=context.strip())
            
            # Add custom instructions if provided
            if custom_instructions:
                formatted_prompt += f"\n\nAdditional Instructions: {custom_instructions}"
            
            # Use Langfuse context manager for proper tracing
            if self.langfuse:
                try:
                    with self.langfuse.start_as_current_generation(
                        name="ai_transcript_generation",
                        model=self.default_model,
                        input=formatted_prompt,
                        metadata={
                            "user_id": user_id,
                            "context_length": len(context),
                            "has_custom_instructions": bool(custom_instructions),
                            "temperature": self.temperature,
                            "max_tokens": self.max_tokens
                        }
                    ) as generation:
                        # Try with primary model first
                        try:
                            response = await self._generate_with_model(
                                prompt=formatted_prompt,
                                model=self.default_model
                            )
                        except Exception as e:
                            logger.warning(f"Primary model failed, trying fallback: {e}")
                            # Update metadata with fallback info
                            generation.update(metadata={"fallback_used": True, "primary_error": str(e)})
                            
                            # Fallback to secondary model
                            response = await self._generate_with_model(
                                prompt=formatted_prompt,
                                model=self.fallback_model
                            )
                        
                        transcript = response.choices[0].message.content.strip()
                        
                        # Calculate metrics
                        word_count = len(transcript.split())
                        estimated_duration = self._estimate_speaking_duration(transcript)
                        
                        # End generation with output and usage
                        generation.end(
                            output=transcript,
                            usage_details={
                                "input": response.usage.prompt_tokens,
                                "output": response.usage.completion_tokens,
                                "total": response.usage.total_tokens
                            },
                            metadata={
                                "word_count": word_count,
                                "estimated_duration_seconds": estimated_duration,
                                "model_used": response.model,
                                "success": True
                            }
                        )
                        
                except Exception as langfuse_error:
                    logger.warning(f"Langfuse tracing failed, continuing without tracing: {langfuse_error}")
                    # Fall back to generation without tracing
                    response = await self._generate_without_tracing(formatted_prompt)
                    transcript = response.choices[0].message.content.strip()
                    word_count = len(transcript.split())
                    estimated_duration = self._estimate_speaking_duration(transcript)
            else:
                # Generate without tracing if Langfuse not available
                response = await self._generate_without_tracing(formatted_prompt)
                transcript = response.choices[0].message.content.strip()
                word_count = len(transcript.split())
                estimated_duration = self._estimate_speaking_duration(transcript)
            
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
                "context_provided": context[:100] + "..." if len(context) > 100 else context,
                "trace_id": trace_id  # Include trace ID for debugging
            }
            
            # Flush Langfuse to ensure data is sent
            if self.langfuse:
                try:
                    self.langfuse.flush()
                except Exception as e:
                    logger.warning(f"Failed to flush Langfuse: {e}")
            
            return result
            
        except Exception as e:
            error_message = f"Failed to generate transcript: {str(e)}"
            
            return {
                "status": "error",
                "error_message": error_message,
                "error_type": "generation_error",
                "trace_id": trace_id
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
    
    async def _generate_without_tracing(self, prompt: str):
        """
        Generate transcript without Langfuse tracing.
        
        Args:
            prompt: Formatted prompt
            
        Returns:
            OpenAI response
        """
        try:
            return await self._generate_with_model(prompt=prompt, model=self.default_model)
        except Exception as e:
            logger.warning(f"Primary model failed, trying fallback: {e}")
            return await self._generate_with_model(prompt=prompt, model=self.fallback_model) 