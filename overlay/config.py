"""Application configuration.

Configuration is resolved by merging two sources, in order of precedence:

1. Environment variables (and a local ``.env`` if present) — useful for
   development and one-off overrides.
2. The persisted user settings file written by the CLI
   (``~/.ai-overlay/config.json``) — the normal path for installed users.

Local app data (conversation DB, screenshots) lives under the user config
directory so the tool behaves the same regardless of where it was installed.
Nothing here reaches out to the network; it only resolves settings and paths.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from .settings import (
    USER_DATA_DIR,
    USER_DB_PATH,
    USER_SCREENSHOT_DIR,
    ensure_dirs,
    load_settings,
)

# Load a local .env if one exists (dev convenience). find_dotenv-free: dotenv
# silently does nothing when the file is absent.
load_dotenv()

# Public data paths (now rooted in the user's home directory).
DATA_DIR = USER_DATA_DIR
SCREENSHOT_DIR = USER_SCREENSHOT_DIR
DB_PATH = USER_DB_PATH


def _parse_languages(raw: str) -> list[str]:
    return [code.strip() for code in raw.split(",") if code.strip()]


def _env_override(name: str, fallback: str) -> str:
    """Return a stripped env var value, or ``fallback`` if unset/empty."""
    value = os.getenv(name, "").strip()
    return value or fallback


@dataclass(frozen=True)
class AppConfig:
    """Immutable snapshot of runtime configuration."""

    openai_api_key: str
    openai_model: str
    whisper_model: str
    tts_voice: str
    ocr_languages: list[str] = field(default_factory=lambda: ["en"])

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.startswith("sk-"))


def load_config() -> AppConfig:
    """Build an :class:`AppConfig` from user settings + env overrides."""
    ensure_dirs()
    saved = load_settings()

    env_languages = os.getenv("OCR_LANGUAGES", "").strip()
    ocr_languages = (
        _parse_languages(env_languages) if env_languages else saved.ocr_languages
    )

    return AppConfig(
        openai_api_key=_env_override("OPENAI_API_KEY", saved.openai_api_key),
        openai_model=_env_override("OPENAI_MODEL", saved.openai_model),
        whisper_model=_env_override("WHISPER_MODEL", saved.whisper_model),
        tts_voice=_env_override("TTS_VOICE", saved.tts_voice),
        ocr_languages=ocr_languages or ["en"],
    )
