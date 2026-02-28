"""
Clinical Intelligence Hub — AES-256-GCM Encryption + Argon2id Key Derivation

Responsibilities:
  - Derive encryption key from user passphrase (Argon2id)
  - Encrypt/decrypt patient profile data (AES-256-GCM)
  - Encrypted vault for API keys (Gemini, OpenFDA, etc.)

Security model:
  - Passphrase entered at startup via start.command
  - Key derived using Argon2id (memory-hard, GPU-resistant)
  - All patient data encrypted at rest with AES-256-GCM
  - Salt stored alongside ciphertext (unique per encryption)
  - API keys stored in an encrypted vault file
"""

import json
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("CIH-Encryption")

# Argon2id parameters (OWASP recommended minimum)
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536  # 64 MiB
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN = 32  # 256 bits for AES-256

# Salt and nonce sizes
SALT_SIZE = 16    # 128-bit salt
NONCE_SIZE = 12   # 96-bit nonce (GCM standard)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit encryption key from a passphrase using Argon2id."""
    try:
        from argon2.low_level import hash_secret_raw, Type
        return hash_secret_raw(
            secret=passphrase.encode('utf-8'),
            salt=salt,
            time_cost=ARGON2_TIME_COST,
            memory_cost=ARGON2_MEMORY_COST,
            parallelism=ARGON2_PARALLELISM,
            hash_len=ARGON2_HASH_LEN,
            type=Type.ID
        )
    except ImportError:
        logger.error("argon2-cffi not installed. Run: pip install argon2-cffi")
        raise


def encrypt_data(data: bytes, passphrase: str) -> bytes:
    """
    Encrypt data using AES-256-GCM with Argon2id key derivation.

    Output format: salt (16 bytes) || nonce (12 bytes) || ciphertext+tag
    """
    salt = secrets.token_bytes(SALT_SIZE)
    key = _derive_key(passphrase, salt)
    nonce = secrets.token_bytes(NONCE_SIZE)

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)

    return salt + nonce + ciphertext


def decrypt_data(encrypted: bytes, passphrase: str) -> bytes:
    """
    Decrypt data encrypted with encrypt_data().

    Raises cryptography.exceptions.InvalidTag if passphrase is wrong
    or data has been tampered with.
    """
    if len(encrypted) < SALT_SIZE + NONCE_SIZE + 16:  # 16 = minimum GCM tag
        raise ValueError("Encrypted data too short to be valid")

    salt = encrypted[:SALT_SIZE]
    nonce = encrypted[SALT_SIZE:SALT_SIZE + NONCE_SIZE]
    ciphertext = encrypted[SALT_SIZE + NONCE_SIZE:]

    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)

    return aesgcm.decrypt(nonce, ciphertext, None)


class EncryptedVault:
    """
    Encrypted storage for patient profiles and API keys.

    The vault uses a passphrase (entered at startup) to derive
    encryption keys via Argon2id. All data is encrypted at rest
    using AES-256-GCM.
    """

    def __init__(self, data_dir: Path, passphrase: str):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._passphrase = passphrase
        self._profile_path = self.data_dir / "patient_profile.enc"
        self._vault_path = self.data_dir / "api_vault.enc"

    # ── Patient Profile ────────────────────────────────────

    def save_profile(self, profile_data: dict):
        """Encrypt and save the patient profile."""
        json_bytes = json.dumps(profile_data, indent=2, default=str).encode('utf-8')
        encrypted = encrypt_data(json_bytes, self._passphrase)

        with open(self._profile_path, 'wb') as f:
            f.write(encrypted)
        logger.debug(f"Profile encrypted and saved ({len(json_bytes)} bytes → {len(encrypted)} bytes)")

    def load_profile(self) -> Optional[dict]:
        """Decrypt and load the patient profile."""
        if not self._profile_path.exists():
            return None

        try:
            with open(self._profile_path, 'rb') as f:
                encrypted = f.read()

            decrypted = decrypt_data(encrypted, self._passphrase)
            return json.loads(decrypted.decode('utf-8'))

        except Exception as e:
            # Check if it's a legacy unencrypted profile
            try:
                with open(self._profile_path, 'r') as f:
                    profile = json.load(f)
                logger.warning("Found unencrypted profile — re-encrypting...")
                self.save_profile(profile)
                return profile
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.error(f"Failed to decrypt profile: {e}")
                raise

    def profile_exists(self) -> bool:
        """Check if an encrypted profile exists."""
        return self._profile_path.exists()

    # ── API Key Vault ──────────────────────────────────────

    def save_api_keys(self, keys: dict):
        """Encrypt and save API keys (Gemini, OpenFDA, etc.)."""
        json_bytes = json.dumps(keys).encode('utf-8')
        encrypted = encrypt_data(json_bytes, self._passphrase)

        with open(self._vault_path, 'wb') as f:
            f.write(encrypted)
        logger.info("API keys encrypted and saved to vault")

    def load_api_keys(self) -> dict:
        """Decrypt and load API keys."""
        if not self._vault_path.exists():
            return {}

        try:
            with open(self._vault_path, 'rb') as f:
                encrypted = f.read()
            decrypted = decrypt_data(encrypted, self._passphrase)
            return json.loads(decrypted.decode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to decrypt API vault: {e}")
            return {}

    def set_api_key(self, service: str, key: str):
        """Add or update a single API key in the vault."""
        keys = self.load_api_keys()
        keys[service] = key
        self.save_api_keys(keys)

    def get_api_key(self, service: str) -> Optional[str]:
        """Get a single API key from the vault."""
        keys = self.load_api_keys()
        return keys.get(service)

    # ── Vault Verification ─────────────────────────────────

    def verify_passphrase(self) -> bool:
        """
        Verify the passphrase is correct by attempting to decrypt existing data.
        Returns True if passphrase works or if no data exists yet.
        Uses raw decrypt_data() directly to avoid error-swallowing wrappers.
        """
        for path in [self._vault_path, self._profile_path]:
            if path.exists():
                try:
                    with open(path, 'rb') as f:
                        encrypted = f.read()
                    decrypt_data(encrypted, self._passphrase)
                    return True
                except Exception:
                    return False
        # No existing data — any passphrase is fine for first run
        return True

    # ── Session Reset ─────────────────────────────────────

    def clear_patient_profile(self):
        """
        Delete the encrypted patient profile for a new session.
        Keeps API keys intact (they're reusable across sessions).
        """
        if self._profile_path.exists():
            self._profile_path.unlink()
            logger.info("Encrypted patient profile deleted — ready for new session")
        else:
            logger.debug("No patient profile to clear")
