"""
Service for managing YouTube OAuth secrets
"""

import json
import base64
from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException, status

from app.models.secret import Secret
from app.models.user import User
from app.schemas.secret import (
    YouTubeOAuthJSON, 
    SecretValidationResponse, 
    SecretResponse,
    SecretStatusResponse
)
from app.services.encryption_service import get_encryption_service


class SecretService:
    """Service for managing YouTube OAuth secrets."""
    
    def __init__(self, db: AsyncSession):
        """
        Initialize secret service.
        
        Args:
            db: Database session
        """
        self.db = db
        self.encryption_service = get_encryption_service()
    
    async def validate_oauth_json(self, file_content: str) -> SecretValidationResponse:
        """
        Validate YouTube OAuth JSON file content.
        
        Args:
            file_content: Base64 encoded JSON file content
            
        Returns:
            SecretValidationResponse: Validation result
        """
        try:
            # Decode base64 content
            try:
                json_content = base64.b64decode(file_content).decode('utf-8')
            except Exception:
                return SecretValidationResponse(
                    valid=False,
                    errors=["Invalid base64 encoding"]
                )
            
            # Parse JSON
            try:
                data = json.loads(json_content)
            except json.JSONDecodeError as e:
                return SecretValidationResponse(
                    valid=False,
                    errors=[f"Invalid JSON format: {str(e)}"]
                )
            
            # Validate using Pydantic schema
            try:
                oauth_data = YouTubeOAuthJSON(**data)
                web_config = oauth_data.web
                
                return SecretValidationResponse(
                    valid=True,
                    project_id=web_config.get('project_id'),
                    client_id_preview=web_config.get('client_id', '')[:20] + '...',
                    warnings=[]
                )
            except ValueError as e:
                return SecretValidationResponse(
                    valid=False,
                    errors=[str(e)]
                )
        
        except Exception as e:
            return SecretValidationResponse(
                valid=False,
                errors=[f"Validation failed: {str(e)}"]
            )
    
    async def upload_secret(
        self, 
        user_id: UUID, 
        filename: str, 
        file_content: str
    ) -> SecretResponse:
        """
        Upload and store YouTube OAuth secret.
        
        Args:
            user_id: User ID
            filename: Original filename
            file_content: Base64 encoded JSON file content
            
        Returns:
            SecretResponse: Created secret information
            
        Raises:
            HTTPException: If upload fails
        """
        # First validate the file
        validation = await self.validate_oauth_json(file_content)
        if not validation.valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid OAuth JSON file: {', '.join(validation.errors)}"
            )
        
        try:
            # Decode and parse JSON
            json_content = base64.b64decode(file_content).decode('utf-8')
            data = json.loads(json_content)
            web_config = data['web']
            
            # Check if user already has secrets (deactivate old ones)
            await self._deactivate_existing_secrets(user_id)
            
            # Encrypt sensitive fields
            client_id_encrypted = self.encryption_service.encrypt(web_config['client_id'])
            client_secret_encrypted = self.encryption_service.encrypt(web_config['client_secret'])
            
            # Prepare redirect URIs
            redirect_uris_json = None
            if 'redirect_uris' in web_config:
                redirect_uris_json = json.dumps(web_config['redirect_uris'])
            
            # Create secret record
            secret = Secret(
                user_id=user_id,
                project_id=web_config['project_id'],
                client_id_encrypted=client_id_encrypted,
                client_secret_encrypted=client_secret_encrypted,
                auth_uri=web_config.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
                token_uri=web_config.get('token_uri', 'https://oauth2.googleapis.com/token'),
                auth_provider_x509_cert_url=web_config.get(
                    'auth_provider_x509_cert_url', 
                    'https://www.googleapis.com/oauth2/v1/certs'
                ),
                redirect_uris=redirect_uris_json,
                original_filename=filename,
                is_active=True,
                is_verified=True
            )
            
            self.db.add(secret)
            await self.db.commit()
            await self.db.refresh(secret)
            
            return SecretResponse.model_validate(secret)
        
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to store secret: {str(e)}"
            )
    
    async def get_user_secrets(self, user_id: UUID) -> List[SecretResponse]:
        """
        Get all secrets for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List[SecretResponse]: List of user secrets
        """
        try:
            result = await self.db.execute(
                select(Secret)
                .where(and_(Secret.user_id == user_id, Secret.is_active == True))
                .order_by(Secret.created_at.desc())
            )
            secrets = result.scalars().all()
            
            return [SecretResponse.model_validate(secret) for secret in secrets]
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve secrets: {str(e)}"
            )
    
    async def get_active_secret(self, user_id: UUID) -> Optional[Secret]:
        """
        Get the active secret for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Optional[Secret]: Active secret if exists
        """
        try:
            result = await self.db.execute(
                select(Secret)
                .where(and_(
                    Secret.user_id == user_id, 
                    Secret.is_active == True,
                    Secret.is_verified == True
                ))
                .order_by(Secret.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve active secret: {str(e)}"
            )
    
    async def get_decrypted_credentials(self, user_id: UUID) -> Optional[Dict[str, str]]:
        """
        Get decrypted OAuth credentials for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Optional[Dict[str, str]]: Decrypted credentials with client_id and client_secret
        """
        secret = await self.get_active_secret(user_id)
        if not secret:
            return None
        
        try:
            client_id = self.encryption_service.decrypt(secret.client_id_encrypted)
            client_secret = self.encryption_service.decrypt(secret.client_secret_encrypted)
            
            # Update last used timestamp
            secret.last_used_at = datetime.utcnow()
            await self.db.commit()
            
            return {
                'client_id': client_id,
                'client_secret': client_secret,
                'project_id': secret.project_id,
                'auth_uri': secret.auth_uri,
                'token_uri': secret.token_uri
            }
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to decrypt credentials: {str(e)}"
            )
    
    async def check_user_secret_status(self, user_id: UUID) -> SecretStatusResponse:
        """
        Check if user has uploaded secrets.
        
        Args:
            user_id: User ID
            
        Returns:
            SecretStatusResponse: Secret status information
        """
        try:
            result = await self.db.execute(
                select(Secret)
                .where(Secret.user_id == user_id)
            )
            all_secrets = result.scalars().all()
            
            active_secrets = [s for s in all_secrets if s.is_active]
            latest_secret = max(all_secrets, key=lambda s: s.created_at) if all_secrets else None
            
            return SecretStatusResponse(
                has_secrets=len(all_secrets) > 0,
                secret_count=len(all_secrets),
                active_secrets=len(active_secrets),
                latest_upload=latest_secret.created_at if latest_secret else None
            )
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to check secret status: {str(e)}"
            )
    
    async def delete_secret(self, user_id: UUID, secret_id: UUID) -> bool:
        """
        Delete a secret (soft delete by setting is_active=False).
        
        Args:
            user_id: User ID
            secret_id: Secret ID
            
        Returns:
            bool: True if deleted successfully
            
        Raises:
            HTTPException: If secret not found or deletion fails
        """
        try:
            result = await self.db.execute(
                select(Secret)
                .where(and_(Secret.id == secret_id, Secret.user_id == user_id))
            )
            secret = result.scalar_one_or_none()
            
            if not secret:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Secret not found"
                )
            
            secret.is_active = False
            await self.db.commit()
            
            return True
        
        except HTTPException:
            raise
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete secret: {str(e)}"
            )
    
    async def _deactivate_existing_secrets(self, user_id: UUID) -> None:
        """
        Deactivate all existing secrets for a user.
        
        Args:
            user_id: User ID
        """
        result = await self.db.execute(
            select(Secret)
            .where(and_(Secret.user_id == user_id, Secret.is_active == True))
        )
        existing_secrets = result.scalars().all()
        
        for secret in existing_secrets:
            secret.is_active = False
        
        await self.db.commit() 