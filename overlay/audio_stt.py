"""Push-to-talk microphone capture and local Whisper transcription.

Recording is explicit and user-driven: :meth:`SpeechToText.start` begins
capturing the local microphone and :meth:`SpeechToText.stop_and_transcribe`
ends it and returns the text. This is a push-to-transcribe design intended for
the user's own voice, not covert monitoring of others.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import sounddevice as sd

_SAMPLE_RATE = 16_000  # Whisper expects 16 kHz mono audio.
_CHANNELS = 1


@dataclass
class STTResult:
    """Outcome of a transcription request."""

    ok: bool
    text: str


class SpeechToText:
    """Records mic audio on demand and transcribes it with local Whisper."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None  # Lazily loaded whisper model.
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []

    def _ensure_model(self) -> None:
        if self._model is None:
            import whisper

            self._model = whisper.load_model(self._model_name)

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        """Begin capturing microphone audio into an in-memory buffer."""
        if self._stream is not None:
            return
        self._frames = []

        def _callback(indata, _frames, _time, _status) -> None:
            # Copy because sounddevice reuses the buffer across callbacks.
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="float32",
            callback=_callback,
        )
        self._stream.start()

    def stop_and_transcribe(self) -> STTResult:
        """Stop recording and return the transcribed text."""
        if self._stream is None:
            return STTResult(ok=False, text="Not currently recording.")

        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

        if not self._frames:
            return STTResult(ok=False, text="No audio captured.")

        audio = np.concatenate(self._frames, axis=0).flatten().astype(np.float32)
        self._frames = []

        try:
            self._ensure_model()
            result = self._model.transcribe(audio, fp16=False)
        except Exception as exc:  # noqa: BLE001 - surface model/transcribe errors
            return STTResult(ok=False, text=f"Transcription failed: {exc}")

        text = (result.get("text") or "").strip()
        if not text:
            return STTResult(ok=False, text="Could not understand the audio.")
        return STTResult(ok=True, text=text)
