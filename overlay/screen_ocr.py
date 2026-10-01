"""Screen capture and OCR.

Grabs the current screen with ``mss`` on demand and extracts visible text with
``easyocr``. Capture only runs when the user explicitly triggers it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mss
import mss.tools
import numpy as np


@dataclass
class OCRResult:
    """Outcome of a screen OCR request."""

    ok: bool
    text: str


def capture_png(monitor_index: int = 1) -> bytes:
    """Capture a monitor and return the screenshot as PNG bytes.

    This performs no OCR; it is used for the vision path where the raw image
    is sent to the model. ``monitor_index`` 1 is the primary monitor; index 0
    is the virtual "all monitors" bounding box.
    """
    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_index >= len(monitors):
            monitor_index = 1 if len(monitors) > 1 else 0
        raw = sct.grab(monitors[monitor_index])

    # mss.tools.to_png encodes the raw BGRA pixels to a PNG byte string.
    return mss.tools.to_png(raw.rgb, raw.size)


class ScreenOCR:
    """Captures a monitor and runs OCR over the pixels.

    The easyocr reader is created lazily on first use because loading its
    models is slow and should not block application startup.
    """

    def __init__(
        self, languages: list[str], screenshot_dir: Path | None = None
    ) -> None:
        self._languages = languages or ["en"]
        self._screenshot_dir = screenshot_dir
        self._reader = None  # Lazily initialised easyocr.Reader

    def _ensure_reader(self) -> None:
        if self._reader is None:
            # Imported lazily so startup does not pay the model-load cost.
            import easyocr

            self._reader = easyocr.Reader(self._languages, gpu=False)

    def capture_monitor(self, monitor_index: int = 1) -> np.ndarray:
        """Capture a monitor and return an RGB numpy array.

        ``monitor_index`` 1 is the primary monitor in mss; index 0 is the
        virtual "all monitors" bounding box.
        """
        with mss.mss() as sct:
            monitors = sct.monitors
            if monitor_index >= len(monitors):
                monitor_index = 1 if len(monitors) > 1 else 0
            raw = sct.grab(monitors[monitor_index])

        # mss returns BGRA; drop alpha and reverse to RGB for easyocr.
        frame = np.array(raw)[:, :, :3][:, :, ::-1]
        return np.ascontiguousarray(frame)

    def read_screen(self, monitor_index: int = 1) -> OCRResult:
        """Capture the screen and return extracted text joined by newlines."""
        try:
            self._ensure_reader()
            frame = self.capture_monitor(monitor_index)
        except Exception as exc:  # noqa: BLE001 - surface any capture/model error
            return OCRResult(ok=False, text=f"Screen capture failed: {exc}")

        try:
            lines = self._reader.readtext(frame, detail=0, paragraph=True)
        except Exception as exc:  # noqa: BLE001 - surface OCR errors
            return OCRResult(ok=False, text=f"OCR failed: {exc}")

        text = "\n".join(line.strip() for line in lines if line.strip())
        if not text:
            return OCRResult(ok=False, text="No readable text found on screen.")
        return OCRResult(ok=True, text=text)
