"""Text-to-speech via edge-tts.

Synthesizes an MP3 from text using Microsoft Edge's online TTS voices, then
plays it back locally and quietly. Playback must never open an external media
application or steal window focus, so on Windows it uses the in-process MCI API
rather than ``os.startfile``.

Synthesis is async under the hood; a synchronous ``speak`` helper is provided
for easy use from worker threads.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import uuid
from pathlib import Path

import edge_tts


class TextToSpeech:
    """Synthesizes speech to an MP3 file and plays it back in-process."""

    def __init__(self, voice: str) -> None:
        self._voice = voice

    async def synthesize(self, text: str, out_path: Path) -> None:
        """Render ``text`` to an MP3 at ``out_path``."""
        communicator = edge_tts.Communicate(text, self._voice)
        await communicator.save(str(out_path))

    def speak(self, text: str) -> None:
        """Synthesize ``text`` and play it. Blocks until playback finishes.

        Intended to be called from a background worker thread so the UI stays
        responsive. Playback is quiet: it does not open any external app or
        change which window is focused.
        """
        text = (text or "").strip()
        if not text:
            return

        # Unique temp file per call so overlapping calls don't clash.
        tmp = Path(tempfile.gettempdir()) / f"overlay_tts_{uuid.uuid4().hex}.mp3"
        try:
            asyncio.run(self.synthesize(text, tmp))
            self._play(tmp)
        finally:
            # Best-effort cleanup.
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _play(self, path: Path) -> None:
        """Play an audio file in-process without opening an external app."""
        if sys.platform.startswith("win"):
            self._play_windows_mci(path)
        elif sys.platform == "darwin":
            import subprocess

            subprocess.run(["afplay", str(path)], check=False)
        else:
            # Linux: prefer a non-GUI player if present; silent if none.
            import shutil
            import subprocess

            for player in ("ffplay", "aplay", "mpg123", "paplay"):
                if shutil.which(player):
                    args = [player, str(path)]
                    if player == "ffplay":
                        args = ["ffplay", "-nodisp", "-autoexit", str(path)]
                    subprocess.run(args, check=False)
                    return

    @staticmethod
    def _play_windows_mci(path: Path) -> None:
        """Play audio via the Windows MCI API (ctypes).

        MCI decodes and plays MP3 within this process. It never opens a visible
        media application and never changes window focus, which avoids the
        overlay losing focus or appearing to close.
        """
        try:
            import ctypes

            winmm = ctypes.windll.winmm  # type: ignore[attr-defined]
            alias = f"ttsclip_{uuid.uuid4().hex}"

            def _mci(command: str) -> int:
                return winmm.mciSendStringW(command, None, 0, None)

            # Quote the path so spaces are handled.
            _mci(f'open "{path}" type mpegvideo alias {alias}')
            try:
                _mci(f"play {alias} wait")
            finally:
                _mci(f"close {alias}")
        except Exception:  # noqa: BLE001 - playback is best-effort, never fatal
            pass
