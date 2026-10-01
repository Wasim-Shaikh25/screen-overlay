"""Floating overlay UI and application wiring.

Builds a frameless, always-on-top window that floats over other applications
(Chrome, VS Code, Teams, etc.) and connects it to the AI, OCR, STT, TTS,
storage, and hotkey modules.

Consent note: this tool is designed for personal productivity. Screen capture
and microphone recording only run when the user explicitly triggers them. If you
use voice features during a call, inform the other participants and comply with
your local laws and your organisation's policies.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .ai_client import AIClient
from .audio_stt import SpeechToText
from .config import AppConfig
from .hotkeys import HotkeyManager
from .screen_ocr import ScreenOCR
from .storage import ConversationStore
from .tts import TextToSpeech
from .workers import AIWorker, OCRWorker, STTWorker, TTSWorker

_CONSENT_NOTICE = (
    "Personal productivity assistant. Screen/mic capture runs only when you "
    "trigger it. If using voice in a call, inform participants and follow local "
    "laws and company policy."
)


class OverlayWindow(QWidget):
    """Frameless always-on-top assistant window."""

    # Signals so hotkey callbacks (on a non-Qt thread) can safely reach the UI.
    _request_toggle = pyqtSignal()
    _request_read_screen = pyqtSignal()
    _request_talk = pyqtSignal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config

        # Core services.
        self._ai = AIClient(config.openai_api_key, config.openai_model)
        self._ocr = ScreenOCR(config.ocr_languages)
        self._stt = SpeechToText(config.whisper_model)
        self._tts = TextToSpeech(config.tts_voice)
        self._store = ConversationStore(_db_path())

        # Keep references so QThreads are not garbage-collected while running.
        self._threads: list[QThread] = []
        self._busy = False

        self._build_ui()
        self._wire_signals()
        # Each new run starts fresh: wipe any stored history from prior sessions.
        # The in-memory AI history (self._ai) is already empty at construction,
        # so the full conversation context is retained only within this run.
        self._reset_for_new_run()
        self._start_hotkeys()

        if not self._ai.is_ready:
            self._append_system(
                "OpenAI key not configured. Add OPENAI_API_KEY to .env to enable "
                "AI replies. Screen reading and transcription still work."
            )

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowOpacity(0.96)
        self.resize(420, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Title bar (custom, since the window is frameless).
        title_bar = QHBoxLayout()
        title = QLabel("AI Assistant")
        title.setStyleSheet("font-weight: 600; font-size: 14px; color: #e8e8e8;")
        close_btn = QPushButton("x")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.hide)
        title_bar.addWidget(title)
        title_bar.addStretch(1)
        title_bar.addWidget(close_btn)
        root.addLayout(title_bar)

        # Consent / status notice.
        notice = QLabel(_CONSENT_NOTICE)
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #9aa0a6; font-size: 10px;")
        root.addWidget(notice)

        # Conversation output.
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet(
            "background: #1e1e1e; color: #e8e8e8; border: 1px solid #333;"
            " border-radius: 6px; padding: 6px;"
        )
        root.addWidget(self._output, stretch=1)

        # Status line.
        self._status = QLabel("Ready.")
        self._status.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        root.addWidget(self._status)

        # Input row.
        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask something, or use the buttons below...")
        self._input.returnPressed.connect(self._on_send)
        self._send_btn = QPushButton("Send")
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._input, stretch=1)
        input_row.addWidget(self._send_btn)
        root.addLayout(input_row)

        # Action buttons.
        actions = QHBoxLayout()
        self._read_btn = QPushButton("Read Screen")
        self._read_btn.setToolTip("OCR the screen to text, then summarize.")
        self._read_btn.clicked.connect(self._on_read_screen)
        self._shot_btn = QPushButton("Screenshot + Ask")
        self._shot_btn.setToolTip(
            "Capture the screen as an image and send it with your typed prompt "
            "to the vision model."
        )
        self._shot_btn.clicked.connect(self._on_screenshot_ask)
        self._talk_btn = QPushButton("Talk")
        self._talk_btn.clicked.connect(self._on_talk)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._on_clear)
        actions.addWidget(self._read_btn)
        actions.addWidget(self._shot_btn)
        actions.addWidget(self._talk_btn)
        actions.addWidget(self._clear_btn)
        root.addLayout(actions)

        # Voice output toggle (opt-in; OFF by default so nothing auto-plays).
        voice_row = QHBoxLayout()
        self._voice_btn = QPushButton("Voice: Off")
        self._voice_btn.setCheckable(True)
        self._voice_btn.setChecked(False)
        self._voice_btn.setToolTip(
            "When on, spoken audio of each AI reply plays. Off by default."
        )
        self._voice_btn.toggled.connect(self._on_voice_toggled)
        voice_row.addWidget(self._voice_btn)
        voice_row.addStretch(1)
        root.addLayout(voice_row)

        self.setStyleSheet(
            "QWidget { background: #252526; }"
            "QPushButton { background: #0e639c; color: white; border: none;"
            " border-radius: 4px; padding: 6px 10px; }"
            "QPushButton:hover { background: #1177bb; }"
            "QLineEdit { background: #1e1e1e; color: #e8e8e8; border: 1px solid"
            " #333; border-radius: 4px; padding: 6px; }"
        )

        # Local shortcut to hide quickly.
        QShortcut(QKeySequence("Esc"), self, activated=self.hide)

    def _wire_signals(self) -> None:
        self._request_toggle.connect(self._toggle_visibility)
        self._request_read_screen.connect(self._on_read_screen)
        self._request_talk.connect(self._on_talk)

    # --------------------------------------------------------------- events

    def _on_send(self) -> None:
        if self._busy:
            return
        text = self._input.text().strip()
        if not text:
            self._set_status("Type a question first.")
            return
        self._input.clear()
        self._append_user(text)
        self._store.add("user", text)
        self._ask_ai(text)

    def _on_read_screen(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "Reading screen (OCR)...")
        worker = OCRWorker(self._ocr.read_screen)
        worker.finished.connect(self._on_ocr_done)
        self._run(worker)

    def _on_ocr_done(self, ok: bool, text: str) -> None:
        if not ok:
            self._set_busy(False, text)
            return
        self._set_status("Screen text captured. Summarizing...")
        prompt = f"Here is text captured from my screen:\n\n{text}\n\nSummarize it."
        self._append_user("[Read screen -> summarize]")
        self._store.add("user", prompt)
        # Keep busy; the follow-up AI call clears it when done.
        self._ask_ai(prompt, already_busy=True)

    def _on_screenshot_ask(self) -> None:
        """Capture the screen as an image and send it with the typed prompt.

        This is the vision path: unlike Read Screen (OCR to text), it sends the
        actual screenshot to the model. Capture happens here, on this click.
        A prompt is required so the model knows what you want.
        """
        if self._busy:
            return
        if not self._ai.is_ready:
            self._append_system("(OpenAI not configured - cannot use vision.)")
            return
        prompt = self._input.text().strip()
        if not prompt:
            self._set_status("Type what to ask about the screen first.")
            return
        self._input.clear()
        self._append_user(f"[Screenshot] {prompt}")
        self._set_busy(True, "Capturing screenshot and asking...")

        from .screen_ocr import capture_png

        def _capture_and_ask():
            png = capture_png(1)
            return self._ai.ask_with_image(prompt, png)

        worker = AIWorker(_capture_and_ask)
        worker.finished.connect(self._on_screenshot_done)
        self._run(worker)

    def _on_screenshot_done(self, ok: bool, text: str) -> None:
        self._set_busy(False)
        if not ok:
            self._append_system(text)
            return
        self._append_assistant(text)
        self._store.add("assistant", text)
        self._speak(text)

    def _on_talk(self) -> None:
        if self._stt.is_recording:
            self._set_busy(True, "Transcribing...")
            self._talk_btn.setText("Talk")
            worker = STTWorker(self._stt.stop_and_transcribe)
            worker.finished.connect(self._on_stt_done)
            self._run(worker)
        else:
            if self._busy:
                return
            try:
                self._stt.start()
            except Exception as exc:  # noqa: BLE001
                self._set_status(f"Microphone error: {exc}")
                return
            self._talk_btn.setText("Stop")
            self._set_status("Recording... click Stop (or Talk) when done.")

    def _on_stt_done(self, ok: bool, text: str) -> None:
        if not ok:
            self._set_busy(False, text)
            return
        self._set_status("Transcribed. Sending...")
        self._append_user(text)
        self._store.add("user", text)
        self._ask_ai(text, already_busy=True)

    def _on_clear(self) -> None:
        if self._busy:
            self._set_status("Please wait for the current request to finish.")
            return
        # Erase everything: on-screen text, in-memory AI history, and the DB.
        self._output.clear()
        self._ai.reset()
        try:
            self._store.clear()
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"History clear failed: {exc}")
            return
        self._set_status("Conversation cleared.")

    def _on_voice_toggled(self, checked: bool) -> None:
        self._voice_btn.setText("Voice: On" if checked else "Voice: Off")
        self._set_status(
            "Voice replies on." if checked else "Voice replies off."
        )

    # ------------------------------------------------------------------ AI

    def _ask_ai(self, prompt: str, already_busy: bool = False) -> None:
        if not self._ai.is_ready:
            self._append_system("(OpenAI not configured - no reply.)")
            if already_busy:
                self._set_busy(False)
            return
        self._set_busy(True, "Processing...")
        worker = AIWorker(lambda: self._ai.ask(prompt))
        worker.finished.connect(self._on_ai_done)
        self._run(worker)

    def _on_ai_done(self, ok: bool, text: str) -> None:
        self._set_busy(False)
        if not ok:
            self._append_system(text)
            return
        self._append_assistant(text)
        self._store.add("assistant", text)
        self._speak(text)

    def _speak(self, text: str) -> None:
        # Voice output is opt-in: only speak when the Voice toggle is on.
        if not self._voice_btn.isChecked():
            return
        worker = TTSWorker(lambda: self._tts.speak(text))
        self._run(worker)

    # ------------------------------------------------------------- helpers

    def _run(self, worker: QThread) -> None:
        """Track a worker, clean it up on completion, and start it."""
        self._threads.append(worker)

        def _cleanup() -> None:
            if worker in self._threads:
                self._threads.remove(worker)
            worker.deleteLater()

        worker.finished.connect(_cleanup)
        worker.start()

    def _toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self._input.setFocus()

    def _reset_for_new_run(self) -> None:
        """Start a clean session: clear stored history from previous runs.

        The on-screen output and the AI's in-memory context both begin empty,
        so nothing from a prior session carries over. Within this run, the full
        conversation is kept (see AIClient history handling).
        """
        try:
            self._store.clear()
        except Exception:  # noqa: BLE001 - a fresh start should never be fatal
            pass
        self._ai.reset()
        self._output.clear()

    def _start_hotkeys(self) -> None:
        self._hotkeys = HotkeyManager(
            on_toggle=self._request_toggle.emit,
            on_read_screen=self._request_read_screen.emit,
            on_talk=self._request_talk.emit,
        )
        self._hotkeys.start()

    def _append_user(self, text: str) -> None:
        self._output.append(f'<p style="color:#8ab4f8;"><b>You:</b> {_esc(text)}</p>')

    def _append_assistant(self, text: str) -> None:
        self._output.append(f'<p style="color:#e8e8e8;"><b>AI:</b> {_esc(text)}</p>')

    def _append_system(self, text: str) -> None:
        self._output.append(f'<p style="color:#f28b82;"><i>{_esc(text)}</i></p>')

    def _set_status(self, text: str) -> None:
        self._status.setText(text)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        """Toggle the processing state: disable inputs and show a status.

        While busy, the input box and action buttons are disabled so a request
        cannot be fired twice, and the status line shows progress. The Talk
        button is left enabled only so an in-progress recording can be stopped.
        """
        self._busy = busy
        self._input.setEnabled(not busy)
        self._send_btn.setEnabled(not busy)
        self._read_btn.setEnabled(not busy)
        self._shot_btn.setEnabled(not busy)
        self._clear_btn.setEnabled(not busy)
        # Talk stays usable to allow stopping a recording; disable only mid-AI.
        self._talk_btn.setEnabled(not busy or self._stt.is_recording)
        if message is not None:
            self._set_status(message)
        elif not busy:
            self._set_status("Ready.")

    # Allow dragging the frameless window by its body.
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(
            self, "_drag_offset"
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hotkeys.stop()
        self._store.close()
        super().closeEvent(event)


def _esc(text: str) -> str:
    """Escape HTML and preserve line breaks for the QTextEdit output."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )


def _db_path():
    from .config import DB_PATH

    return DB_PATH


def run() -> int:
    """Application entry point."""
    from .config import load_config

    config = load_config()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)  # Keep running when hidden via hotkey.
    window = OverlayWindow(config)
    window.show()
    return app.exec()
