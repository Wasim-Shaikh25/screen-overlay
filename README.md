# AI Overlay

A floating, always-on-top desktop AI assistant. It helps you summarize and
reason about things you explicitly share with it: on-screen text, screenshots,
your own voice, code, emails, and documents. It is packaged as a command-line
tool (`ai-overlay`) and a small floating window that stays on top of your other
apps (Chrome, VS Code, Teams, and so on).

You set your OpenAI API key once; it is stored securely in your operating
system's credential store and reused on every run.

The same assistant is also available as a self-hosted web page in `web/`.
That version keeps the API key in the browser for 7 days and is deployed with
the root `Dockerfile`. The command-line tool below is unchanged.

---

## Table of contents

- [Consent and responsible use](#consent-and-responsible-use)
- [Features](#features)
- [Requirements](#requirements)
- [Install](#install)
- [Quick start](#quick-start)
- [CLI reference](#cli-reference)
- [The floating window](#the-floating-window)
- [Hotkeys](#hotkeys)
- [How it works](#how-it-works)
- [Where your data lives](#where-your-data-lives)
- [Build from source](#build-from-source)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Web app](#web-app)
- [License](#license)

---

## Consent and responsible use

This tool is built for **personal productivity** and is intentionally
**push-to-trigger**:

- Screen capture (OCR or screenshot) runs only when you press a hotkey or click
  a button.
- Microphone recording runs only while you have explicitly started it.

If you use the voice features during a call or meeting, you must inform the
other participants, comply with your local laws, and respect your
organisation's policies and the meeting platform's terms of service. This
project does not provide covert monitoring or always-on recording of other
people. Your conversations are stored only on your own machine.

---

## Features

- Always-on-top floating window that works over other applications.
- Two on-demand screen modes:
  - **OCR** – extract on-screen *text* and summarize it ("Read Screen").
  - **Vision** – send the actual *screenshot image* plus your prompt to the
    model ("Screenshot + Ask", or `ai-overlay ask "..." --screenshot`).
- Push-to-talk microphone input with local Whisper transcription.
- OpenAI integration for reasoning and summaries, with model selection.
- Optional voice replies (Edge TTS), **off by default**, toggled in the window.
- Each run starts fresh; full conversation context is kept during a session.
- Secure API key storage in the OS credential store (keyring).
- One-time interactive setup and simple CLI.

---

## Requirements

- **Python 3.11+** (tested on 3.12). On Windows, tick "Add Python to PATH"
  during installation.
- An **OpenAI API key** (starts with `sk-`). Create one at
  <https://platform.openai.com/api-keys>.

The optional `[full]` extra adds screen OCR and local voice transcription and
pulls in PyTorch, which is a large one-time download.

---

## Install

### Option A — one-click (Windows, for non-technical users)

The `dist-bundle/` folder is a self-contained hand-off package. Download or copy
it, then double-click **`install.bat`**. It installs the tool, asks you to paste
your API key, and shows you how to start it. Afterwards, double-click
**`AI-Overlay.bat`** to launch. See `dist-bundle/READ-ME-FIRST.txt` for a
plain-language guide.

### Option B — pipx (isolated global command)

[pipx](https://pipx.pypa.io) keeps the tool in its own environment and puts the
`ai-overlay` command on your PATH.

```bash
python -m pip install --user pipx
python -m pipx ensurepath     # then restart your terminal

# Core only (window + typed chat + voice output):
pipx install "dist-bundle/ai_overlay-1.0.2-py3-none-any.whl"

# Everything (adds OCR + local Whisper, pulls PyTorch):
pipx install "dist-bundle/ai_overlay-1.0.2-py3-none-any.whl[full]"
```

### Option C — pip into a virtual environment

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install "dist-bundle/ai_overlay-1.0.2-py3-none-any.whl[full]"
```

### Option D — editable (for development)

Fastest for iterating on the code: your edits apply live, no reinstall.

```bash
pip install -e ".[full]"
```

---

## Quick start

```bash
ai-overlay setup     # paste your API key (stored securely)
ai-overlay models    # see available models
ai-overlay model gpt-4o     # optional: pick a model
ai-overlay run       # open the floating window
```

Ask a one-shot question straight from the terminal:

```bash
ai-overlay ask "explain what a closure is in Python"
ai-overlay ask "what's wrong on my screen?" --screenshot
```

---

## CLI reference

| Command | What it does |
| --- | --- |
| `ai-overlay setup` | Interactive first-time setup (prompts for your API key). |
| `ai-overlay config` | Show current settings (API key masked). |
| `ai-overlay config --api-key <key>` | Save your OpenAI API key. |
| `ai-overlay config --model <name>` | Set the OpenAI model. |
| `ai-overlay config --voice <voice>` | Set the Edge TTS voice. |
| `ai-overlay config --whisper-model <size>` | Set the local Whisper size. |
| `ai-overlay config --ocr-languages <a,b>` | Set OCR languages. |
| `ai-overlay config --clear-key` | Remove the stored API key. |
| `ai-overlay models` | List selectable models (marks the current one). |
| `ai-overlay model <name\|number>` | Select the model by name or list number. |
| `ai-overlay ask "<prompt>"` | One-shot text question, prints the answer. |
| `ai-overlay ask "<prompt>" --screenshot` | Capture the screen now and send image + prompt (vision). |
| `ai-overlay run` | Launch the floating overlay. |
| `ai-overlay info` | Show version, paths, and key status. |
| `ai-overlay --version` | Print the version. |

Environment variables override saved settings for a single run:
`OPENAI_API_KEY`, `OPENAI_MODEL`, `WHISPER_MODEL`, `TTS_VOICE`, `OCR_LANGUAGES`.

---

## The floating window

- Type a question and press Enter, or use the buttons.
- **Read Screen** – OCRs the screen to text and summarizes it.
- **Screenshot + Ask** – type a prompt first, then click; sends the screenshot
  image together with your prompt to the vision model.
- **Talk** – click to start recording, click again to stop and transcribe.
- **Clear** – erases the current conversation.
- **Voice: Off/On** – opt-in spoken replies; off by default.
- While a request runs, the controls disable and the status shows "Processing..."
  so a request cannot be fired twice.
- Drag the window by its body to reposition it.

---

## Hotkeys

| Shortcut | Action |
| --- | --- |
| `Ctrl+Space` | Show / hide the overlay |
| `Ctrl+Shift+S` | Read the screen (OCR) and summarize |
| `Ctrl+Shift+T` | Start / stop push-to-talk |
| `Esc` | Hide the overlay |

---

## How it works

- **OCR path:** `mss` captures the screen; `easyocr` extracts text; the text is
  sent to the chat model.
- **Vision path:** `mss` captures a PNG; the image is sent inline (base64) with
  your prompt to a vision-capable model.
- **Voice in:** `sounddevice` records the mic; local `openai-whisper`
  transcribes it.
- **Voice out:** `edge-tts` synthesizes speech; it plays in-process (Windows MCI)
  so no external media app opens.
- **Sessions:** each run starts with a clean history; within a run the full
  conversation is kept for context.

---

## Where your data lives

Everything stays on the local machine.

| Location | Contents |
| --- | --- |
| OS credential store (keyring) | OpenAI API key (secure) |
| `~/.ai-overlay/config.json` | Non-secret settings (model, voice, OCR langs) |
| `~/.ai-overlay/data/conversations.db` | Current-session conversation (wiped on each new run) |

The only network calls are the OpenAI requests you trigger and the Edge TTS
voice synthesis.

---

## Build from source

```bash
pip install build
python -m build
```

This produces `dist/ai_overlay-<version>-py3-none-any.whl` and a `.tar.gz`
source archive. Copy the wheel into `dist-bundle/` to refresh the hand-off
package.

---

## Project layout

```text
screen-overlay/
├── main.py                 # Dev entry point (python main.py <command>)
├── pyproject.toml          # Packaging + console_scripts (ai-overlay)
├── requirements.txt        # Dev dependency list
├── LICENSE
├── README.md
├── .env.example
├── dist-bundle/            # Hand-off package (installer, launcher, wheel, guide)
│   ├── install.bat
│   ├── AI-Overlay.bat
│   ├── READ-ME-FIRST.txt
│   └── ai_overlay-*.whl
├── Dockerfile              # Production image: build the web app, serve it with nginx
├── docker-compose.yml      # Optional: docker compose up --build
├── web/                    # Self-hosted browser version (see Web app below)
└── overlay/
    ├── cli.py              # CLI: setup / config / models / model / ask / run / info
    ├── settings.py         # Persistent settings + keyring secure storage
    ├── config.py           # Runtime config (settings + env overrides)
    ├── ai_client.py        # OpenAI chat + vision wrapper, model listing
    ├── screen_ocr.py       # mss capture + easyocr OCR, PNG capture
    ├── audio_stt.py        # sounddevice capture + Whisper STT
    ├── tts.py              # edge-tts synthesis + in-process playback
    ├── storage.py          # SQLite conversation store
    ├── hotkeys.py          # pynput global hotkeys
    ├── workers.py          # QThread workers for blocking tasks
    └── app.py              # Floating overlay UI + wiring
```

---

## Troubleshooting

- **`'ai-overlay' is not recognized`** – open a new terminal (PATH updates only
  in new windows), or use the full path to the installed executable.
- **No AI replies** – run `ai-overlay info` and confirm the key is configured;
  re-run `ai-overlay setup` if needed.
- **Read Screen / Talk disabled or erroring** – install the full extra:
  `pipx install "ai_overlay-<version>-py3-none-any.whl[full]"`.
- **Pasting the key into the hidden prompt does nothing** – use
  `ai-overlay config --api-key sk-...` (visible), the setup prompt now shows
  the key as you paste it.
- **First screen read or transcription is slow** – EasyOCR and Whisper download
  their models on first use only.
- **Microphone error** – check OS microphone permissions and that an input
  device is available.

---

## Web app

A browser version of the floating assistant, for hosting on your own server.
The Python CLI stays available and is not required to run the site.

The page is static. Nginx only serves files. The OpenAI API key is written to
`localStorage` in the visitor's browser, with the time it was saved, and is
removed after 7 days. Chat, vision, and transcription requests are made by the
browser directly to `https://api.openai.com`. The key is not sent to, logged
by, or stored on your server.

### What it does

- First screen asks for an OpenAI API key until a valid, unexpired key is
  already in this browser. Saving a key checks it with OpenAI before storing
  it. **Change key** removes it immediately.
- Chat keeps the full conversation for the current page load. Refresh or
  **Clear** starts over.
- **Read screen** uses the browser screen picker, takes one frame, then stops
  the share. Text is read in the browser with Tesseract.js (English) and sent
  to the model to summarize.
- **Screenshot** sends that frame, with the prompt you typed, to the vision
  model.
- **Talk** records the microphone until you stop, sends that clip to OpenAI
  transcription (`whisper-1`), then asks the model.
- **Voice** speaks replies with the browser's speech synthesis. It starts off
  on every visit.
- **Detach** moves the page into a small always-on-top window with the
  Document Picture-in-Picture API (Chrome and Edge 116+). **Re-attach** puts
  it back. Other browsers get a small popup and a note that always-on-top is
  not supported.

While the page or the detached window is focused, `Ctrl+Shift+S` reads the
screen and `Ctrl+Shift+T` starts or stops the mic.

### Differences from the CLI

| Desktop CLI | Web app |
| --- | --- |
| Always-on-top Qt window | Document Picture-in-Picture in Chrome/Edge. Elsewhere, a normal popup. |
| `mss` captures a monitor with no extra prompt | `getDisplayMedia` asks you to pick a screen or window, captures one frame, then stops. |
| EasyOCR, languages you configure | Tesseract.js in the browser, English language data served by this site. |
| Global hotkeys (`Ctrl+Space`, `Esc`, and the others) | Shortcuts work only while the overlay window is focused. |
| Local Whisper, audio stays on the machine | Audio is sent to OpenAI transcription when you stop recording. |
| Edge TTS voices | The browser's own voices. Still off until you enable Voice. |
| API key in the OS credential store | API key in `localStorage` for 7 days, then the add-key screen returns. |
| `ai-overlay ask` from the terminal | Use the page. The CLI command still works for the desktop install. |

### Run it on your server

From the repository root. The container listens on **port 8080**.

```bash
docker build -t ai-overlay .
docker run --rm -p 8080:8080 ai-overlay
```

Open `http://<your-server>:8080`. A check is available at
`http://<your-server>:8080/healthz`.

Or use Compose, which publishes the same port:

```bash
docker compose up --build -d
```

The image is a multi-stage build: Node builds the static files, then nginx
serves `web/dist`. It does not contain an API key and it does not proxy
OpenAI.

### Local development

```bash
cd web
npm install
npm test
npm run dev
```

The dev server listens on port 5173. `npm run build` writes `web/dist/`.
Production hosting should use the Docker image above so the Tesseract files
are included the same way.

## License

MIT. See [LICENSE](LICENSE).
