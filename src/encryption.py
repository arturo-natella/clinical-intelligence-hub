"""
Clinical Intelligence Hub — AES-256-GCM Encryption + Argon2id Key Derivation

Responsibilities:
  - Derive encryption key from user passphrase (Argon2id)
  - Encrypt/decrypt patient profile data (AES-256-GCM)
  - Multi-profile management (create, load, save, switch, delete)
  - Encrypted vault for API keys (Gemini, OpenFDA, etc.)

Security model:
  - Passphrase entered at startup via start.command
  - Key derived using Argon2id (memory-hard, GPU-resistant)
  - All patient data encrypted at rest with AES-256-GCM
  - Salt stored alongside ciphertext (unique per encryption)
  - API keys stored in an encrypted vault file (shared across profiles)
  - Profile index is unencrypted (contains only names + IDs, no PII)
"""

import json
import logging
import os
import secrets
import uuid
from datetime import datetime
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

    Supports multiple named profiles, each stored as a separate
    encrypted file. The profile index (names + IDs) is unencrypted
    and contains no patient data.

    The vault uses a passphrase (entered at startup) to derive
    encryption keys via Argon2id. All data is encrypted at rest
    using AES-256-GCM.
    """

    def __init__(self, data_dir: Path, passphrase: str):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._passphrase = passphrase
        self._profiles_dir = self.data_dir / "profiles"
        self._index_path = self._profiles_dir / "index.json"
        self._vault_path = self.data_dir / "api_vault.enc"
        # Legacy path (single-profile era)
        self._legacy_profile_path = self.data_dir / "patient_profile.enc"
        # Active profile for convenience methods
        self.active_profile_id: Optional[str] = None

    # ── Profile Management ────────────────────────────────

    def list_profiles(self) -> list[dict]:
        """List all profiles. Returns unencrypted metadata only (no PII)."""
        if not self._index_path.exists():
            return []
        try:
            with open(self._index_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning("Profile index corrupted — returning empty list")
            return []

    def create_profile(self, name: str) -> str:
        """Create a new empty profile. Returns the profile_id."""
        profile_id = uuid.uuid4().hex[:8]
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

        index = self.list_profiles()
        today = datetime.now().strftime("%Y-%m-%d")
        index.append({
            "id": profile_id,
            "name": name,
            "created": today,
            "last_accessed": today,
        })
        self._save_index(index)

        logger.info(f"Created profile '{name}' (id={profile_id})")
        return profile_id

    def save_profile(self, profile_data: dict, profile_id: str = None):
        """Encrypt and save a patient profile.

        Uses active_profile_id if profile_id not specified.
        Falls back to legacy single-file format if no profile system is active.
        """
        pid = profile_id or self.active_profile_id

        if not pid:
            # Legacy fallback for code that hasn't been updated
            self._legacy_save(profile_data)
            return

        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        path = self._profiles_dir / f"{pid}.enc"

        json_bytes = json.dumps(profile_data, indent=2, default=str).encode('utf-8')
        encrypted = encrypt_data(json_bytes, self._passphrase)

        with open(path, 'wb') as f:
            f.write(encrypted)

        self._update_access_time(pid)
        logger.debug(
            f"Profile {pid} saved ({len(json_bytes):,} bytes → "
            f"{len(encrypted):,} bytes)"
        )

    def load_profile(self, profile_id: str = None) -> Optional[dict]:
        """Decrypt and load a patient profile.

        Uses active_profile_id if profile_id not specified.
        Falls back to legacy single-file format if no profile system is active.
        """
        pid = profile_id or self.active_profile_id

        if not pid:
            return self._legacy_load()

        path = self._profiles_dir / f"{pid}.enc"
        if not path.exists():
            return None

        try:
            with open(path, 'rb') as f:
                encrypted = f.read()
            decrypted = decrypt_data(encrypted, self._passphrase)
            self._update_access_time(pid)
            return json.loads(decrypted.decode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to decrypt profile {pid}: {e}")
            raise

    def delete_profile(self, profile_id: str):
        """Delete a profile and its encrypted data."""
        path = self._profiles_dir / f"{profile_id}.enc"
        if path.exists():
            path.unlink()

        index = [p for p in self.list_profiles() if p["id"] != profile_id]
        self._save_index(index)

        if self.active_profile_id == profile_id:
            self.active_profile_id = None

        logger.info(f"Deleted profile {profile_id}")

    def rename_profile(self, profile_id: str, new_name: str):
        """Rename a profile."""
        index = self.list_profiles()
        for entry in index:
            if entry["id"] == profile_id:
                entry["name"] = new_name
                break
        self._save_index(index)
        logger.info(f"Renamed profile {profile_id} → '{new_name}'")

    def profile_exists(self, profile_id: str = None) -> bool:
        """Check if an encrypted profile exists."""
        pid = profile_id or self.active_profile_id
        if pid:
            return (self._profiles_dir / f"{pid}.enc").exists()
        return self._legacy_profile_path.exists()

    # ── Legacy Migration ──────────────────────────────────

    def migrate_legacy_profile(self) -> Optional[str]:
        """
        Migrate old single-file patient_profile.enc to the new
        multi-profile system. Returns the new profile_id, or None
        if there was nothing to migrate.
        """
        if not self._legacy_profile_path.exists():
            return None

        try:
            profile = self._legacy_load()
            if not profile:
                return None

            profile_id = self.create_profile("My Records")
            self.save_profile(profile, profile_id)

            # Rename legacy file so we don't migrate again
            backup = self._legacy_profile_path.with_suffix(".enc.migrated")
            self._legacy_profile_path.rename(backup)

            logger.info(
                f"Migrated legacy profile → '{profile_id}' "
                f"(backup at {backup.name})"
            )
            return profile_id

        except Exception as e:
            logger.error(f"Legacy profile migration failed: {e}")
            return None

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
        """
        # Check API vault
        if self._vault_path.exists():
            try:
                with open(self._vault_path, 'rb') as f:
                    encrypted = f.read()
                decrypt_data(encrypted, self._passphrase)
                return True
            except Exception:
                return False

        # Check legacy profile
        if self._legacy_profile_path.exists():
            try:
                with open(self._legacy_profile_path, 'rb') as f:
                    encrypted = f.read()
                decrypt_data(encrypted, self._passphrase)
                return True
            except Exception:
                return False

        # Check any profile in profiles dir
        if self._profiles_dir.exists():
            for enc_file in self._profiles_dir.glob("*.enc"):
                try:
                    with open(enc_file, 'rb') as f:
                        encrypted = f.read()
                    decrypt_data(encrypted, self._passphrase)
                    return True
                except Exception:
                    return False

        # No existing data — any passphrase is fine for first run
        return True

    # ── Session Reset ─────────────────────────────────────

    def clear_patient_profile(self, profile_id: str = None):
        """Delete a patient profile. Keeps API keys intact."""
        pid = profile_id or self.active_profile_id
        if pid:
            self.delete_profile(pid)
        elif self._legacy_profile_path.exists():
            self._legacy_profile_path.unlink()
            logger.info("Legacy profile deleted")

    # ── Private Helpers ────────────────────────────────────

    def _save_index(self, index: list[dict]):
        """Write the profile index to disk."""
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        with open(self._index_path, 'w') as f:
            json.dump(index, f, indent=2)

    def _update_access_time(self, profile_id: str):
        """Update last_accessed timestamp in the profile index."""
        index = self.list_profiles()
        today = datetime.now().strftime("%Y-%m-%d")
        for entry in index:
            if entry["id"] == profile_id:
                entry["last_accessed"] = today
                break
        self._save_index(index)

    def _legacy_save(self, profile_data: dict):
        """Save to the old single-file format (backward compat)."""
        json_bytes = json.dumps(profile_data, indent=2, default=str).encode('utf-8')
        encrypted = encrypt_data(json_bytes, self._passphrase)
        with open(self._legacy_profile_path, 'wb') as f:
            f.write(encrypted)
        logger.debug("Profile saved (legacy format)")

    def _legacy_load(self) -> Optional[dict]:
        """Load from the old single-file format."""
        if not self._legacy_profile_path.exists():
            return None
        try:
            with open(self._legacy_profile_path, 'rb') as f:
                encrypted = f.read()
            decrypted = decrypt_data(encrypted, self._passphrase)
            return json.loads(decrypted.decode('utf-8'))
        except Exception as e:
            # Check for unencrypted legacy profile
            try:
                with open(self._legacy_profile_path, 'r') as f:
                    profile = json.load(f)
                logger.warning("Found unencrypted profile — re-encrypting...")
                self._legacy_save(profile)
                return profile
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.error(f"Failed to decrypt legacy profile: {e}")
                raise
