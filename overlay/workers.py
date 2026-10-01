"""Qt worker threads for blocking operations.

OCR, transcription, AI requests, and TTS are all slow and/or blocking. Running
them on ``QThread`` workers keeps the overlay UI responsive. Each worker emits a
``finished`` signal with an ``ok`` flag and a text payload.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QThread, pyqtSignal


class _ResultWorker(QThread):
    """Runs a callable returning an object with ``ok`` and ``text`` fields."""

    finished = pyqtSignal(bool, str)

    def __init__(self, task: Callable[[], object]) -> None:
        super().__init__()
        self._task = task

    def run(self) -> None:
        try:
            result = self._task()
            ok = bool(getattr(result, "ok", False))
            text = str(getattr(result, "text", ""))
        except Exception as exc:  # noqa: BLE001 - report failures to the UI
            ok, text = False, f"Unexpected error: {exc}"
        self.finished.emit(ok, text)


class OCRWorker(_ResultWorker):
    """Runs screen OCR off the UI thread."""


class STTWorker(_ResultWorker):
    """Runs speech transcription off the UI thread."""


class AIWorker(_ResultWorker):
    """Runs an OpenAI request off the UI thread."""


class TTSWorker(QThread):
    """Speaks text off the UI thread (fire-and-forget)."""

    finished = pyqtSignal()

    def __init__(self, speak: Callable[[], None]) -> None:
        super().__init__()
        self._speak = speak

    def run(self) -> None:
        try:
            self._speak()
        except Exception:  # noqa: BLE001 - playback is best-effort
            pass
        self.finished.emit()
