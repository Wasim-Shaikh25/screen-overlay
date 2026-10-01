"""OpenAI client wrapper for chat/reasoning.

Keeps a running conversation (system + message history) and sends it to the
OpenAI Chat Completions API. Network calls only happen when the user explicitly
triggers them from the overlay.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from openai import OpenAI, OpenAIError

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful desktop assistant. You help the user summarize and reason "
    "about content they explicitly share with you: screen text, their own voice "
    "input, code, emails, and documents. Be concise and practical. When given "
    "OCR'd screen text, treat it as possibly noisy and focus on the user's intent."
)

# Maximum number of prior (user/assistant) messages to keep in context during a
# single session. Set high so the full conversation is retained within a run;
# the cap only exists as a safety limit to avoid unbounded token growth over a
# very long session.
_MAX_HISTORY_MESSAGES = 200


@dataclass
class AIResult:
    """Outcome of an AI request."""

    ok: bool
    text: str


class AIClient:
    """Thin wrapper around the OpenAI chat API with local history."""

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client: OpenAI | None = None
        if api_key:
            try:
                self._client = OpenAI(api_key=api_key)
            except OpenAIError:
                self._client = None
        self._history: list[dict[str, str]] = []

    @property
    def is_ready(self) -> bool:
        """True when an API client was constructed with a usable key."""
        return self._client is not None

    def list_models(self) -> list[str]:
        """Return available chat-capable model ids from the account.

        Falls back to a small curated list if the API cannot be reached or no
        key is configured. The result is filtered to GPT chat/vision models and
        sorted for stable display.
        """
        fallback = [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1-mini",
            "gpt-4.1",
            "o4-mini",
        ]
        if self._client is None:
            return fallback

        try:
            models = self._client.models.list()
        except OpenAIError:
            return fallback

        ids = [m.id for m in models.data]
        # Keep GPT/o-series chat models; drop embeddings, tts, whisper, image,
        # moderation, realtime, and dated snapshots noise where obvious.
        chat_like = [
            mid
            for mid in ids
            if (mid.startswith("gpt-") or mid.startswith("o1") or mid.startswith("o3")
                or mid.startswith("o4"))
            and not any(
                token in mid
                for token in ("embedding", "tts", "whisper", "audio", "image",
                              "moderation", "realtime", "transcribe", "search")
            )
        ]
        chat_like = sorted(set(chat_like))
        return chat_like or fallback

    def reset(self) -> None:
        """Clear in-memory conversation history."""
        self._history.clear()

    def ask(self, user_message: str) -> AIResult:
        """Send ``user_message`` plus history to the model and return the reply."""
        if self._client is None:
            return AIResult(
                ok=False,
                text=(
                    "OpenAI is not configured. Add OPENAI_API_KEY to your .env "
                    "file to enable cloud reasoning."
                ),
            )

        self._history.append({"role": "user", "content": user_message})
        self._trim_history()

        messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
        messages.extend(self._history)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
            )
        except OpenAIError as exc:
            # Roll back the user turn so a retry does not duplicate it.
            self._history.pop()
            return AIResult(ok=False, text=f"OpenAI request failed: {exc}")

        reply = (response.choices[0].message.content or "").strip()
        self._history.append({"role": "assistant", "content": reply})
        return AIResult(ok=True, text=reply)

    def ask_with_image(self, user_message: str, png_bytes: bytes) -> AIResult:
        """Send a prompt plus a screenshot image to the vision model.

        The image is sent inline as a base64 data URI. To keep the stored
        history small, only a text placeholder for the image turn is retained
        (the raw image is not kept in history), while the assistant reply is
        stored normally so follow-up questions have context.
        """
        if self._client is None:
            return AIResult(
                ok=False,
                text=(
                    "OpenAI is not configured. Run 'ai-overlay setup' or set "
                    "OPENAI_API_KEY to enable cloud reasoning."
                ),
            )
        if not png_bytes:
            return AIResult(ok=False, text="No screenshot captured to send.")

        prompt = user_message.strip() or "Describe what is on the screen."
        b64 = base64.b64encode(png_bytes).decode("ascii")
        data_uri = f"data:image/png;base64,{b64}"

        # Build the request: prior text history for context, then this turn's
        # multimodal message (text + image).
        messages: list[dict] = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
        messages.extend(self._history)
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
            )
        except OpenAIError as exc:
            return AIResult(ok=False, text=f"OpenAI vision request failed: {exc}")

        reply = (response.choices[0].message.content or "").strip()
        # Store compact text placeholders so history stays small but coherent.
        self._history.append({"role": "user", "content": f"[screenshot] {prompt}"})
        self._history.append({"role": "assistant", "content": reply})
        self._trim_history()
        return AIResult(ok=True, text=reply)

    def _trim_history(self) -> None:
        if len(self._history) > _MAX_HISTORY_MESSAGES:
            self._history = self._history[-_MAX_HISTORY_MESSAGES:]
