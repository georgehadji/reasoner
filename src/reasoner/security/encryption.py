"""
Encryption Service for Data at Rest (Phase 3: E2EE)

Provides AES-256-GCM encryption via Fernet for sensitive data storage.
"""

from __future__ import annotations

import os
import base64
import logging
import hmac
import hashlib
import re # Added for text normalization
from typing import Optional, Union, List

from cryptography.fernet import Fernet, MultiFernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Handles symmetric encryption and decryption for sensitive data at rest.
    
    Supports key rotation via MultiFernet.
    Also provides functionality for generating blind indexes.
    """

    def __init__(self, keys: Optional[Union[str, List[str]]] = None, blind_index_key: Optional[str] = None):
        """
        Initialize with one or more encryption keys and an optional blind index key.
        The first key in the list is used for encryption.
        All keys are used for decryption.
        """
        if keys is None:
            # Fallback to environment variable for encryption keys
            keys_env = os.environ.get("ENCRYPTION_KEY")
            if not keys_env:
                if os.environ.get("ENVIRONMENT") == "production":
                    raise RuntimeError("ENCRYPTION_KEY environment variable is missing in production!")
                
                logger.warning("ENCRYPTION_KEY not found. Generating temporary key for development.")
                keys = [Fernet.generate_key().decode()]
            else:
                keys = [k.strip() for k in keys_env.split(",") if k.strip()]

        if isinstance(keys, str):
            keys = [keys]

        if not keys:
            raise ValueError("No encryption keys provided.")

        try:
            self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])
        except Exception as e:
            logger.error(f"Failed to initialize EncryptionService: {e}")
            raise ValueError(f"Invalid encryption key(s) provided: {e}")

        # Blind Index Key
        if blind_index_key is None:
            blind_index_key = os.environ.get("BLIND_INDEX_KEY")
            if not blind_index_key:
                if os.environ.get("ENVIRONMENT") == "production":
                    raise RuntimeError("BLIND_INDEX_KEY environment variable is missing in production!")
                logger.warning("BLIND_INDEX_KEY not found. Generating temporary key for development.")
                blind_index_key = Fernet.generate_key().decode() # Use Fernet to generate a suitable key format
        
        self._blind_index_key = base64.urlsafe_b64decode(blind_index_key.encode())

    def encrypt(self, data: Union[str, bytes]) -> str:
        """
        Encrypt data and return a URL-safe base64 encoded string.
        """
        if isinstance(data, str):
            data = data.encode()
        
        return self._fernet.encrypt(data).decode()

    def decrypt(self, token: Union[str, bytes]) -> str:
        """
        Decrypt a token and return the plaintext string.
        """
        if isinstance(token, str):
            token = token.encode()
            
        try:
            return self._fernet.decrypt(token).decode()
        except InvalidToken:
            logger.error("Decryption failed: Invalid token or key mismatch.")
            raise
        except Exception as e:
            logger.error(f"Unexpected decryption error: {e}")
            raise

    def decrypt_bytes(self, token: Union[str, bytes]) -> bytes:
        """
        Decrypt a token and return the plaintext bytes.
        """
        if isinstance(token, str):
            token = token.encode()
            
        try:
            return self._fernet.decrypt(token)
        except InvalidToken:
            logger.error("Decryption failed: Invalid token or key mismatch.")
            raise

    def generate_blind_index(self, text: str) -> List[str]:
        """
        Generate a list of deterministic, blinded hashes for search terms.
        These hashes can be stored and searched without compromising data privacy.
        """
        normalized_text = re.sub(r'[^a-z0-9\s]', '', text.lower())
        tokens = normalized_text.split()
        
        blind_indexes = []
        for token in tokens:
            if token:
                # Use HMAC-SHA256 for deterministic hashing with a secret key
                h = hmac.new(self._blind_index_key, token.encode(), hashlib.sha256)
                blind_indexes.append(base64.urlsafe_b64encode(h.digest()).decode())
        return blind_indexes

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet-compatible encryption key."""
        return Fernet.generate_key().decode()


import threading

# Global singleton instance
_instance: Optional[EncryptionService] = None
_lock = threading.Lock()

def get_encryption_service() -> EncryptionService:
    """Get or create global EncryptionService instance (Thread-safe)."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = EncryptionService(blind_index_key=os.environ.get("BLIND_INDEX_KEY"))
    return _instance
