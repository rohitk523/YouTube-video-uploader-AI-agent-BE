"""
Encryption service for sensitive data
"""

import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import get_settings


class EncryptionService:
    """Service for encrypting and decrypting sensitive data."""
    
    def __init__(self):
        """Initialize encryption service with application secret key."""
        self.settings = get_settings()
        self._cipher_suite = self._create_cipher_suite()
    
    def _create_cipher_suite(self) -> Fernet:
        """
        Create Fernet cipher suite from application secret key.
        
        Returns:
            Fernet: Cipher suite for encryption/decryption
        """
        # Use the application's secret key as password
        password = self.settings.secret_key.encode()
        
        # Create a salt (in production, this should be stored securely)
        # For now, we'll use a derived salt from the secret key
        salt = hashes.Hash(hashes.SHA256())
        salt.update(password)
        salt_bytes = salt.finalize()[:16]  # Use first 16 bytes as salt
        
        # Derive key from password and salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_bytes,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        
        return Fernet(key)
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext string.
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            str: Base64 encoded encrypted string
            
        Raises:
            Exception: If encryption fails
        """
        try:
            if not plaintext:
                raise ValueError("Cannot encrypt empty string")
            
            encrypted_bytes = self._cipher_suite.encrypt(plaintext.encode('utf-8'))
            return base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')
        except Exception as e:
            raise Exception(f"Encryption failed: {str(e)}")
    
    def decrypt(self, encrypted_text: str) -> str:
        """
        Decrypt encrypted string.
        
        Args:
            encrypted_text: Base64 encoded encrypted string
            
        Returns:
            str: Decrypted plaintext string
            
        Raises:
            Exception: If decryption fails
        """
        try:
            if not encrypted_text:
                raise ValueError("Cannot decrypt empty string")
            
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_text.encode('utf-8'))
            decrypted_bytes = self._cipher_suite.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            raise Exception(f"Decryption failed: {str(e)}")
    
    def is_encrypted(self, text: str) -> bool:
        """
        Check if a string appears to be encrypted.
        
        Args:
            text: String to check
            
        Returns:
            bool: True if string appears to be encrypted
        """
        try:
            # Try to decode as base64
            base64.urlsafe_b64decode(text.encode('utf-8'))
            # If successful and contains Fernet token pattern, likely encrypted
            return len(text) > 50 and '=' in text
        except Exception:
            return False


# Global encryption service instance
_encryption_service: EncryptionService = None


def get_encryption_service() -> EncryptionService:
    """
    Get encryption service instance (singleton pattern).
    
    Returns:
        EncryptionService: Encryption service instance
    """
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service 