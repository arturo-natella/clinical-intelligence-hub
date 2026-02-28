import os
import json
import logging
from pathlib import Path
from cryptography.fernet import Fernet

logger = logging.getLogger("MedPrep-Encryption")

class SecurityManager:
    def __init__(self, data_dir: Path):
        self.key_path = data_dir / ".encryption_key"
        self.fernet = self._initialize_key()

    def _initialize_key(self) -> Fernet:
        """Loads the encryption key or generates a new one if it doesn't exist."""
        if self.key_path.exists():
            with open(self.key_path, 'rb') as f:
                key = f.read()
        else:
            logger.info("Generating new AES-256 key for patient data encryption at rest.")
            key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(key)
        return Fernet(key)

    def load_profile(self, profile_path: Path) -> dict:
        """Decrypts and loads the patient profile JSON."""
        if not profile_path.exists():
            return None
        
        try:
            with open(profile_path, 'rb') as f:
                encrypted_data = f.read()
            
            # Catch plain JSON if it was created before encryption was implemented
            try:
                decrypted_data = self.fernet.decrypt(encrypted_data)
                return json.loads(decrypted_data.decode('utf-8'))
            except Exception as decrypt_error:
                # Fallback to see if it's just raw JSON
                try:
                    profile = json.loads(encrypted_data.decode('utf-8'))
                    logger.warning(f"File at {profile_path.name} was NOT encrypted. Re-saving as encrypted...")
                    self.save_profile(profile, profile_path)
                    return profile
                except Exception as json_error:
                    logger.error(f"Failed to load or decrypt profile: {str(decrypt_error)}")
                    raise json_error
        except Exception as e:
            logger.error(f"Error accessing profile: {str(e)}")
            return None

    def save_profile(self, profile_data: dict, profile_path: Path):
        """Encrypts and saves the patient profile JSON to disk."""
        json_data = json.dumps(profile_data, indent=2).encode('utf-8')
        encrypted_data = self.fernet.encrypt(json_data)
        
        with open(profile_path, 'wb') as f:
            f.write(encrypted_data)
        logger.debug(f"Successfully encrypted and saved data to {profile_path.name}")
