"""Persistent user settings stored in the user's home directory.

Non-secret settings (model, voice, OCR languages) are written to
``~/.ai-overlay/config.json``. The OpenAI API key is stored separately and
securely:

* Preferred: the operating system credential store, via the ``keyring``
  package (Windows Credential Manager, macOS Keychain, Secret Service on Linux).
* Fallback: if no usable keyring backend is available, the key is written to
  ``config.json`` with owner-only file permissions, and a flag records that it
  lives there.

This split means each user configures the tool once and the secret never has to
sit in plain text when a real credential store exists.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

# Base directory and config file for user-level settings.
USER_CONFIG_DIR = Path(os.path.expanduser("~")) / ".ai-overlay"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"

# Local app data (conversations, screenshots) also live under the user dir so
# the tool works identically no matter where it is installed from.
USER_DATA_DIR = USER_CONFIG_DIR / "data"
USER_SCREENSHOT_DIR = USER_DATA_DIR / "screenshots"
USER_DB_PATH = USER_DATA_DIR / "conversations.db"

# keyring service/username under which the API key is stored.
_KEYRING_SERVICE = "ai-overlay"
_KEYRING_USERNAME = "openai_api_key"

# Non-secret keys editable through the CLI "config" command.
_EDITABLE_NONSECRET_KEYS = ("openai_model", "whisper_model", "tts_voice",
                            "ocr_languages")


@dataclass
class UserSettings:
    """In-memory snapshot of user settings (secret + non-secret combined)."""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    whisper_model: str = "base"
    tts_voice: str = "en-US-AriaNeural"
    ocr_languages: list[str] = field(default_factory=lambda: ["en"])

    def nonsecret_json(self) -> dict:
        """Serialize only the non-secret settings for the JSON file."""
        return {
            "openai_model": self.openai_model,
            "whisper_model": self.whisper_model,
            "tts_voice": self.tts_voice,
            "ocr_languages": self.ocr_languages,
        }


def ensure_dirs() -> None:
    """Create the user config and data directories if missing."""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------- keyring layer

def _keyring_available() -> bool:
    """Return True if keyring is importable and has a usable backend."""
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        backend = keyring.get_keyring()
        return not isinstance(backend, FailKeyring)
    except Exception:  # noqa: BLE001 - any import/backend error means unavailable
        return False


def _keyring_get() -> str | None:
    try:
        import keyring

        return keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
    except Exception:  # noqa: BLE001
        return None


def _keyring_set(secret: str) -> bool:
    try:
        import keyring

        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, secret)
        return True
    except Exception:  # noqa: BLE001
        return False


def _keyring_delete() -> None:
    try:
        import keyring

        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
    except Exception:  # noqa: BLE001 - absent or unsupported; ignore
        pass


# ------------------------------------------------------------------- JSON layer

def _read_json() -> dict:
    if not USER_CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(USER_CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(data: dict) -> None:
    ensure_dirs()
    USER_CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        USER_CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


# -------------------------------------------------------------- public helpers

def key_storage_location() -> str:
    """Describe where the API key is (or would be) stored, for display."""
    return "OS keyring" if _keyring_available() else "config.json (fallback)"


def load_settings() -> UserSettings:
    """Load settings, resolving the API key from keyring or JSON fallback."""
    ensure_dirs()
    raw = _read_json()

    languages = raw.get("ocr_languages", ["en"])
    if isinstance(languages, str):
        languages = [c.strip() for c in languages.split(",") if c.strip()]

    # Resolve the key: prefer keyring, then any plaintext fallback in JSON.
    api_key = _keyring_get() or str(raw.get("openai_api_key", "")).strip()

    return UserSettings(
        openai_api_key=(api_key or "").strip(),
        openai_model=str(raw.get("openai_model", "gpt-4o-mini")).strip(),
        whisper_model=str(raw.get("whisper_model", "base")).strip(),
        tts_voice=str(raw.get("tts_voice", "en-US-AriaNeural")).strip(),
        ocr_languages=languages or ["en"],
    )


def save_settings(settings: UserSettings) -> Path:
    """Persist settings: non-secret to JSON, API key to keyring if possible."""
    data = settings.nonsecret_json()

    stored_in_keyring = False
    if settings.openai_api_key:
        stored_in_keyring = _keyring_set(settings.openai_api_key)

    if settings.openai_api_key and not stored_in_keyring:
        # No usable keyring: fall back to plaintext in the JSON file.
        data["openai_api_key"] = settings.openai_api_key
        data["key_in_keyring"] = False
    else:
        # Key is in the keyring (or empty); never leave a plaintext copy behind.
        data["key_in_keyring"] = bool(stored_in_keyring and settings.openai_api_key)

    _write_json(data)
    return USER_CONFIG_FILE


def update_values(**changes: object) -> UserSettings:
    """Apply ``changes`` to stored settings and persist them.

    Accepts the non-secret editable keys plus ``openai_api_key``. ``None``
    values are skipped so callers can pass optional CLI args directly.
    """
    settings = load_settings()
    for key, value in changes.items():
        if value is None:
            continue
        if key == "openai_api_key":
            settings.openai_api_key = str(value).strip()
            continue
        if key not in _EDITABLE_NONSECRET_KEYS:
            continue
        if key == "ocr_languages" and isinstance(value, str):
            value = [c.strip() for c in value.split(",") if c.strip()]
        setattr(settings, key, value)
    save_settings(settings)
    return settings


def clear_api_key() -> None:
    """Remove the stored API key from both keyring and JSON fallback."""
    _keyring_delete()
    data = _read_json()
    data.pop("openai_api_key", None)
    data["key_in_keyring"] = False
    _write_json(data)
