"""Global hotkey registration via pynput.

Listens for application-wide shortcuts and invokes plain callables. The
listener runs on its own thread; callbacks are marshalled back onto the Qt
thread by the UI layer (see :mod:`overlay.app`).

Default bindings:
    Ctrl+Space        -> toggle/show the overlay
    Ctrl+Shift+S      -> read the screen (OCR)
    Ctrl+Shift+T      -> talk (push-to-talk toggle)
"""

from __future__ import annotations

from collections.abc import Callable

from pynput import keyboard


class HotkeyManager:
    """Registers global hotkeys and dispatches to callbacks."""

    def __init__(
        self,
        on_toggle: Callable[[], None],
        on_read_screen: Callable[[], None],
        on_talk: Callable[[], None],
    ) -> None:
        self._on_toggle = on_toggle
        self._on_read_screen = on_read_screen
        self._on_talk = on_talk
        self._listener: keyboard.GlobalHotKeys | None = None

    def start(self) -> None:
        """Begin listening for global hotkeys."""
        if self._listener is not None:
            return
        self._listener = keyboard.GlobalHotKeys(
            {
                "<ctrl>+<space>": self._on_toggle,
                "<ctrl>+<shift>+s": self._on_read_screen,
                "<ctrl>+<shift>+t": self._on_talk,
            }
        )
        self._listener.start()

    def stop(self) -> None:
        """Stop listening and release the keyboard hook."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
