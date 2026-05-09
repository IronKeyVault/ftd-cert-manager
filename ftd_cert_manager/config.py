#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Secure credential and configuration management.

Storage strategy:
1. Try OS keyring (SecretService / GNOME Keyring) - works on desktop Linux
2. If keyring is unavailable (headless), fall back to a local credentials
   file at ~/ftd-cert-manager/credentials.json with chmod 600 (owner-only).
   Credentials are encrypted at rest using Fernet with a machine-derived key
   (from /etc/machine-id + username).
"""
import json, os, logging, base64, hashlib, getpass
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("ftd-cert-manager")
SERVICE_NAME = "ftd-cert-manager"
CONFIG_DIR = Path.home() / "ftd-cert-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
LOG_DIR = CONFIG_DIR / "logs"

CREDENTIAL_KEYS = ("fmc_username", "fmc_password", "pkcs12_password")
CLOUDFLARE_KEY = "cloudflare_api_token"


def _derive_key() -> bytes:
    """Derive a Fernet encryption key from machine identity (no key file needed).

    Uses /etc/machine-id + username as input to scrypt. The result is
    deterministic on the same machine for the same user, but cannot be
    reproduced on another machine or by another user.
    """
    try:
        machine_id = Path("/etc/machine-id").read_text().strip()
    except FileNotFoundError:
        machine_id = "ftd-cert-manager-fallback-id"
    username = getpass.getuser()
    salt = f"ftd-cert-manager-{username}-{machine_id}".encode()
    key = hashlib.scrypt(salt, salt=salt, n=16384, r=8, p=1, dklen=32)
    return base64.urlsafe_b64encode(key)


def _encrypt(data: dict) -> bytes:
    return Fernet(_derive_key()).encrypt(json.dumps(data).encode())


def _decrypt(token: bytes) -> dict:
    return json.loads(Fernet(_derive_key()).decrypt(token))


def _keyring_available() -> bool:
    """Check if OS keyring is usable (desktop session with unlocked keyring)."""
    try:
        from keyring.backends.SecretService import Keyring as SS
        ss = SS()
        ss.get_password("ftd_cert_manager_probe", "probe")
        return True
    except Exception:
        return False


def _ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _read_credentials_file() -> dict:
    if not CREDENTIALS_FILE.exists():
        return {}
    raw = CREDENTIALS_FILE.read_bytes()
    try:
        return _decrypt(raw)
    except InvalidToken:
        log.error("Failed to decrypt credentials file (machine-id changed?)")
        return {}


def _write_credentials_file(data: dict):
    """Write encrypted credentials to local file with chmod 600 from creation."""
    _ensure_config_dir()
    encrypted = _encrypt(data)
    fd = os.open(CREDENTIALS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(encrypted)


class CredentialManager:
    """Manage FMC credentials and PKCS12 password.

    Stores: fmc_username, fmc_password, pkcs12_password
    """

    @staticmethod
    def set_credentials(fmc_username: str, fmc_password: str, pkcs12_password: str):
        if _keyring_available():
            import keyring
            keyring.set_password(SERVICE_NAME, "fmc_username", fmc_username)
            keyring.set_password(SERVICE_NAME, "fmc_password", fmc_password)
            keyring.set_password(SERVICE_NAME, "pkcs12_password", pkcs12_password)
            log.info("Credentials stored in OS keyring")
        else:
            _write_credentials_file({
                "fmc_username": fmc_username,
                "fmc_password": fmc_password,
                "pkcs12_password": pkcs12_password,
            })
            log.info("Credentials encrypted and stored in %s (chmod 600)", CREDENTIALS_FILE)
        return True

    @staticmethod
    def get_credentials() -> dict:
        if _keyring_available():
            import keyring
            data = {k: keyring.get_password(SERVICE_NAME, k) for k in CREDENTIAL_KEYS}
            if all(data.values()):
                return data

        try:
            data = _read_credentials_file()
            if all(k in data for k in CREDENTIAL_KEYS):
                return data
        except Exception as e:
            log.error("Failed to read credentials file: %s", e)

        return None

    @staticmethod
    def clear_credentials():
        if _keyring_available():
            import keyring
            for key in CREDENTIAL_KEYS:
                try:
                    keyring.delete_password(SERVICE_NAME, key)
                except Exception:
                    pass

        if CREDENTIALS_FILE.exists():
            CREDENTIALS_FILE.unlink()

        log.info("Credentials cleared")
        return True

    @staticmethod
    def get_storage_backend() -> str:
        if _keyring_available():
            return "OS keyring (SecretService)"
        return f"Local file ({CREDENTIALS_FILE}, encrypted, chmod 600)"

    @staticmethod
    def set_cloudflare_token(token: str):
        if _keyring_available():
            import keyring
            keyring.set_password(SERVICE_NAME, CLOUDFLARE_KEY, token)
        else:
            data = _read_credentials_file()
            data[CLOUDFLARE_KEY] = token
            _write_credentials_file(data)
        log.info("Cloudflare API token stored")

    @staticmethod
    def get_cloudflare_token():
        if _keyring_available():
            import keyring
            return keyring.get_password(SERVICE_NAME, CLOUDFLARE_KEY)
        return _read_credentials_file().get(CLOUDFLARE_KEY)

    @staticmethod
    def write_cloudflare_creds_file(path: str) -> bool:
        """Materialize the Cloudflare token to a chmod 600 file at `path`.

        Returns True on success. certbot's --dns-cloudflare-credentials needs
        a real file with restrictive permissions.
        """
        token = CredentialManager.get_cloudflare_token()
        if not token:
            return False
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"dns_cloudflare_api_token = {token}\n")
        return True


class ConfigManager:
    """Non-secret configuration stored in ~/ftd-cert-manager/config.json."""

    @staticmethod
    def ensure_directories():
        _ensure_config_dir()

    @staticmethod
    def get_config_dir() -> Path:
        ConfigManager.ensure_directories()
        return CONFIG_DIR

    @staticmethod
    def get_log_dir() -> Path:
        ConfigManager.ensure_directories()
        return LOG_DIR

    @staticmethod
    def get_log_file() -> Path:
        return ConfigManager.get_log_dir() / "ftd-cert-manager.log"

    @staticmethod
    def _load() -> dict:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        return {}

    @staticmethod
    def _save(data: dict):
        ConfigManager.ensure_directories()
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def get(key: str, default=None):
        return ConfigManager._load().get(key, default)

    @staticmethod
    def set(key: str, value):
        data = ConfigManager._load()
        data[key] = value
        ConfigManager._save(data)
        log.info("Config saved: %s", key)

    @staticmethod
    def update(values: dict):
        """Set multiple keys atomically."""
        data = ConfigManager._load()
        data.update(values)
        ConfigManager._save(data)
        log.info("Config updated: %s", list(values.keys()))

    @staticmethod
    def all() -> dict:
        return ConfigManager._load()

    @staticmethod
    def clear():
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
        log.info("Config cleared")
