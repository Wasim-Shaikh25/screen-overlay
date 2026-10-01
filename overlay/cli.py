"""Command-line interface for the AI overlay tool.

Subcommands:
    ai-overlay config   Save/view settings (API key, model, voice, etc.).
    ai-overlay run       Launch the floating overlay.
    ai-overlay info      Show config paths and current status.

The API key is saved on the first ``config`` call — to the OS keyring when a
credential store is available, otherwise to ``~/.ai-overlay/config.json`` with
owner-only permissions — so each user sets it once and ``run`` picks it up.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from . import __version__
from .settings import (
    USER_CONFIG_FILE,
    USER_DB_PATH,
    clear_api_key,
    key_storage_location,
    load_settings,
    update_values,
)

_HOTKEYS_HELP = """\
Hotkeys while the overlay is running:
  Ctrl+Space      Show / hide the overlay
  Ctrl+Shift+S    Read the screen (OCR) and summarize
  Ctrl+Shift+T    Start / stop push-to-talk voice input
  Esc             Hide the overlay

In the window: type a question and press Enter, or use the
Read Screen / Talk / Clear buttons. Drag the window to move it."""


def _mask(secret: str) -> str:
    """Mask a secret for display, keeping only a short suffix."""
    if not secret:
        return "(not set)"
    if len(secret) <= 8:
        return "****"
    return f"****{secret[-4:]}"


def _prompt_for_key(hidden: bool = False) -> str:
    """Interactively prompt for an API key.

    By default the key is shown as you type/paste it, because hidden prompts in
    some Windows terminals silently drop pasted text. Pass ``hidden=True`` to
    use a masked prompt instead. Re-prompts once if the first entry is empty.

    Returns an empty string if nothing is entered.
    """
    print("Enter your OpenAI API key (starts with 'sk-').")
    print("You can create one at https://platform.openai.com/api-keys")
    print("Tip: paste with right-click or Ctrl+V. The key is shown so you can")
    print("confirm it pasted correctly; it is then stored securely.\n")

    for attempt in range(2):
        try:
            if hidden and sys.stdin is not None and sys.stdin.isatty():
                key = getpass.getpass("OpenAI API key: ").strip()
            else:
                key = input("OpenAI API key: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return ""
        if key:
            return key
        if attempt == 0:
            print("Nothing entered - try pasting again (right-click or Ctrl+V).")
    return ""


def _cmd_setup(_args: argparse.Namespace) -> int:
    """Handle ``ai-overlay setup``: interactive first-time configuration."""
    print("=" * 60)
    print(" AI Overlay setup")
    print("=" * 60)

    settings = load_settings()
    if settings.openai_api_key:
        print(f"An API key is already configured ({_mask(settings.openai_api_key)}).")
        answer = input("Replace it? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print("Keeping the existing key.")
            _print_ready()
            return 0

    key = _prompt_for_key(hidden=getattr(_args, "hidden", False))
    if not key:
        print("\nNo key entered. You can run 'ai-overlay setup' again anytime.")
        return 1
    if not key.startswith("sk-"):
        print(
            "\nWarning: that does not look like an OpenAI key (expected 'sk-...'). "
            "Saving it anyway; re-run setup if it is wrong."
        )

    update_values(openai_api_key=key)
    print(f"\nSaved. Key stored in: {key_storage_location()}")
    _print_ready()
    return 0


def _print_ready() -> None:
    """Print the 'you're ready' instructions shown after setup."""
    print("\n" + "-" * 60)
    print("You're ready. Launch the assistant with:\n")
    print("    ai-overlay run\n")
    print("Pick a model (optional):")
    print("    ai-overlay models        (list what's available)")
    print("    ai-overlay model gpt-4o  (change it)\n")
    print(_HOTKEYS_HELP)
    print("-" * 60)


def _cmd_config(args: argparse.Namespace) -> int:
    """Handle ``ai-overlay config``: show, update, or clear settings."""
    if args.clear_key:
        clear_api_key()
        print("Removed the stored OpenAI API key.")
        return 0

    mutating = any(
        value is not None
        for value in (
            args.api_key,
            args.model,
            args.whisper_model,
            args.voice,
            args.ocr_languages,
        )
    )

    if not mutating:
        settings = load_settings()
        print("Current settings:")
        print(f"  openai_api_key : {_mask(settings.openai_api_key)}")
        print(f"  openai_model   : {settings.openai_model}")
        print(f"  whisper_model  : {settings.whisper_model}")
        print(f"  tts_voice      : {settings.tts_voice}")
        print(f"  ocr_languages  : {','.join(settings.ocr_languages)}")
        print(f"\n  key storage    : {key_storage_location()}")
        print(f"  config file    : {USER_CONFIG_FILE}")
        return 0

    settings = update_values(
        openai_api_key=args.api_key,
        openai_model=args.model,
        whisper_model=args.whisper_model,
        tts_voice=args.voice,
        ocr_languages=args.ocr_languages,
    )
    print("Saved settings.")
    if args.api_key is not None:
        print(f"  openai_api_key : {_mask(settings.openai_api_key)}")
        print(f"  key storage    : {key_storage_location()}")
    return 0


def _cmd_models(_args: argparse.Namespace) -> int:
    """Handle ``ai-overlay models``: list selectable models."""
    from .ai_client import AIClient
    from .config import load_config

    config = load_config()
    client = AIClient(config.openai_api_key, config.openai_model)
    if not client.is_ready:
        print("No API key configured; showing common models.\n")

    models = client.list_models()
    current = config.openai_model
    print("Available models:")
    for i, name in enumerate(models, start=1):
        marker = "  <- current" if name == current else ""
        print(f"  {i:>2}. {name}{marker}")
    print("\nChange it with:")
    print("  ai-overlay model <name>        (e.g. ai-overlay model gpt-4o)")
    print("  ai-overlay model <number>      (the number from this list)")
    return 0


def _cmd_model(args: argparse.Namespace) -> int:
    """Handle ``ai-overlay model <name|number>``: select the model."""
    from .ai_client import AIClient
    from .config import load_config

    choice = (args.name or "").strip()
    if not choice:
        # No argument: behave like `models` (show the list).
        return _cmd_models(args)

    config = load_config()
    client = AIClient(config.openai_api_key, config.openai_model)
    models = client.list_models()

    # Allow selecting by list number.
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(models):
            choice = models[index]
        else:
            print(f"Number out of range. Run 'ai-overlay models' to see options.",
                  file=sys.stderr)
            return 1

    if models and choice not in models:
        print(f"Warning: '{choice}' is not in the detected model list. "
              "Saving it anyway (it may still be valid for your account).")

    update_values(openai_model=choice)
    print(f"Model set to: {choice}")
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    """Handle ``ai-overlay ask``: one-shot question, optionally with a screenshot.

    Without ``--screenshot`` this is a plain text question. With it, a screenshot
    is captured on the spot and sent together with the prompt to the vision
    model. Capture happens only here, on this explicit command.
    """
    from .ai_client import AIClient
    from .config import load_config

    config = load_config()
    client = AIClient(config.openai_api_key, config.openai_model)
    if not client.is_ready:
        print(
            "No OpenAI API key configured. Run 'ai-overlay setup' first.",
            file=sys.stderr,
        )
        return 1

    prompt = (args.prompt or "").strip()

    if args.screenshot:
        try:
            from .screen_ocr import capture_png

            print("Capturing screenshot...", file=sys.stderr)
            png = capture_png(args.monitor)
        except Exception as exc:  # noqa: BLE001
            print(f"Screenshot capture failed: {exc}", file=sys.stderr)
            return 1
        result = client.ask_with_image(prompt, png)
    else:
        if not prompt:
            print("Please provide a prompt, e.g. ai-overlay ask \"...\".",
                  file=sys.stderr)
            return 1
        result = client.ask(prompt)

    print(result.text)
    return 0 if result.ok else 1


def _cmd_run(_args: argparse.Namespace) -> int:
    """Handle ``ai-overlay run``: launch the overlay UI.

    On first run (no API key configured yet), prompt for one interactively so
    the user never has to remember a separate setup step.
    """
    settings = load_settings()
    if not settings.openai_api_key:
        print("No OpenAI API key configured yet. Let's set one up.\n")
        key = _prompt_for_key()
        if key:
            update_values(openai_api_key=key)
            print(f"Saved. Key stored in: {key_storage_location()}\n")
        else:
            print(
                "Continuing without a key. Screen reading and transcription will "
                "work, but AI replies and voice output will be disabled.\n"
            )

    # Imported lazily so `config`/`info` work even if GUI/ML deps are missing.
    try:
        from .app import run as run_app
    except ImportError as exc:
        print(
            "Could not import the overlay UI. Make sure GUI dependencies are "
            f"installed (pip install ai-overlay).\nDetails: {exc}",
            file=sys.stderr,
        )
        return 1
    return run_app()


def _cmd_info(_args: argparse.Namespace) -> int:
    """Handle ``ai-overlay info``: print paths and status."""
    settings = load_settings()
    key_status = "configured" if settings.openai_api_key else "NOT set"
    print(f"ai-overlay {__version__}")
    print(f"  Config file    : {USER_CONFIG_FILE}")
    print(f"  Conversation DB: {USER_DB_PATH}")
    print(f"  OpenAI API key : {key_status}")
    print(f"  Key storage    : {key_storage_location()}")
    print(f"  Model          : {settings.openai_model}")
    if not settings.openai_api_key:
        print(
            "\nTip: set your key with:\n"
            "  ai-overlay config --api-key sk-your-key-here"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="ai-overlay",
        description="Floating desktop AI assistant (screen OCR, voice, OpenAI).",
    )
    parser.add_argument(
        "--version", action="version", version=f"ai-overlay {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # setup (interactive first-time configuration)
    p_setup = sub.add_parser(
        "setup", help="Interactive first-time setup (prompts for your API key)."
    )
    p_setup.add_argument(
        "--hidden", action="store_true",
        help="Mask the API key while typing (default shows it so paste works).",
    )
    p_setup.set_defaults(func=_cmd_setup)

    # models (list) and model (select)
    p_models = sub.add_parser("models", help="List selectable OpenAI models.")
    p_models.set_defaults(func=_cmd_models)

    p_model = sub.add_parser(
        "model", help="Set the model by name or by number from 'models'."
    )
    p_model.add_argument(
        "name", nargs="?", default="",
        help="Model name (e.g. gpt-4o) or the number shown by 'ai-overlay models'.",
    )
    p_model.set_defaults(func=_cmd_model)

    # config
    p_config = sub.add_parser(
        "config", help="Save or view settings (API key, model, voice, OCR langs)."
    )
    p_config.add_argument("--api-key", help="OpenAI API key to save for future use.")
    p_config.add_argument("--model", help="OpenAI model (e.g. gpt-4o-mini).")
    p_config.add_argument("--whisper-model", help="Whisper STT size (base, small...).")
    p_config.add_argument("--voice", help="Edge TTS voice (e.g. en-US-AriaNeural).")
    p_config.add_argument(
        "--ocr-languages", help="Comma-separated OCR languages, e.g. 'en' or 'en,es'."
    )
    p_config.add_argument(
        "--clear-key", action="store_true", help="Remove the stored API key."
    )
    p_config.set_defaults(func=_cmd_config)

    # ask (one-shot question, optionally with a screenshot)
    p_ask = sub.add_parser(
        "ask",
        help="Ask a one-shot question; add --screenshot to send a screen image.",
    )
    p_ask.add_argument("prompt", nargs="?", default="", help="Your question.")
    p_ask.add_argument(
        "--screenshot",
        action="store_true",
        help="Capture the screen now and send the image with your prompt (vision).",
    )
    p_ask.add_argument(
        "--monitor", type=int, default=1,
        help="Monitor index to capture (1 = primary). Default 1.",
    )
    p_ask.set_defaults(func=_cmd_ask)

    # run
    p_run = sub.add_parser("run", help="Launch the floating overlay.")
    p_run.set_defaults(func=_cmd_run)

    # info
    p_info = sub.add_parser("info", help="Show config paths and status.")
    p_info.set_defaults(func=_cmd_info)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
