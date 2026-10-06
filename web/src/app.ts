import { blobToDataUrl, captureFrame } from "./capture.ts";
import { Conversation } from "./conversation.ts";
import { detachElement, type DetachedSession } from "./detach.ts";
import {
  ApiKeyStore,
  formatExpiry,
  KEY_STORAGE_ID,
  loadPrefs,
  maskKey,
  savePrefs,
  type KeyStatus,
} from "./key-store.ts";
import { recognizeText } from "./ocr.ts";
import {
  createChatCompletion,
  FALLBACK_MODELS,
  listModels,
  transcribeAudio,
  verifyApiKey,
} from "./openai.ts";
import { listVoices, MicRecorder, silence, speak } from "./speech.ts";

const SHORTCUTS =
  "While this window is focused, Ctrl+Shift+S reads the screen and Ctrl+Shift+T starts or stops the mic. Browsers cannot register the desktop hotkeys used by the CLI.";

export function startApp(mount: HTMLElement, parked: HTMLElement): void {
  const storage = window.localStorage;
  const store = new ApiKeyStore(storage);
  const prefs = loadPrefs(storage);
  const conversation = new Conversation();
  const recorder = new MicRecorder();

  let key: KeyStatus | null = store.load();
  let voiceOn = false;
  let busy = false;
  let confirmRemove = false;
  let session: DetachedSession | null = null;
  let modelsLoaded = false;
  let keyDoc: Document | null = null;
  let voiceWin: Window | null = null;

  const app = el("div");
  app.id = "app";

  const header = el("header");
  const title = el("h1", "AI Overlay");
  const spacer = el("div");
  spacer.className = "spacer";
  const detachBtn = button("Detach", "ghost");
  detachBtn.id = "detach";
  header.append(title, spacer, detachBtn);

  const keyScreen = el("section");
  keyScreen.id = "key-screen";
  keyScreen.className = "screen";
  keyScreen.hidden = true;
  const keyHeading = el("h2", "Add your OpenAI API key");
  const lede = el(
    "p",
    "The key stays in this browser for 7 days. Requests go straight to OpenAI. This server never sees or stores the key.",
  );
  lede.className = "lede";
  const keyLabel = el("label");
  keyLabel.append(document.createTextNode("OpenAI API key"));
  const keyRow = el("div");
  keyRow.className = "key-row";
  const keyInput = document.createElement("input");
  keyInput.id = "api-key";
  keyInput.type = "password";
  keyInput.autocomplete = "off";
  keyInput.spellcheck = false;
  keyInput.placeholder = "sk-…";
  keyInput.setAttribute("aria-describedby", "key-error");
  const toggleKey = button("Show", "ghost");
  toggleKey.type = "button";
  keyRow.append(keyInput, toggleKey);
  keyLabel.append(keyRow);
  const keyError = el("p");
  keyError.id = "key-error";
  keyError.setAttribute("role", "alert");
  const keyForm = document.createElement("form");
  const saveBtn = button("Save and continue");
  saveBtn.type = "submit";
  keyForm.append(keyLabel, keyError, saveBtn);
  const createLink = document.createElement("a");
  createLink.href = "https://platform.openai.com/api-keys";
  createLink.target = "_blank";
  createLink.rel = "noreferrer";
  createLink.textContent = "Create a key at platform.openai.com";
  const fine = el(
    "p",
    "After 7 days the key is removed and this screen comes back. You can remove it sooner from the main view.",
  );
  fine.className = "fine";
  keyScreen.append(keyHeading, lede, keyForm, createLink, fine);

  const main = el("section");
  main.id = "main-screen";
  main.className = "screen";
  main.hidden = true;
  const consent = el(
    "p",
    "Personal productivity assistant. Screen and mic capture run only when you trigger them. If you use voice on a call, tell the other people and follow local law and company policy.",
  );
  consent.className = "consent";
  const fallbackNote = el(
    "p",
    "Always-on-top isn't supported in this browser. This is a normal popup and can sit behind other windows.",
  );
  fallbackNote.id = "fallback-note";
  fallbackNote.hidden = true;
  const log = el("div");
  log.id = "log";
  log.setAttribute("role", "log");
  log.setAttribute("aria-live", "polite");
  const status = el("p", "Ready.");
  status.id = "status";
  status.setAttribute("role", "status");

  const composer = document.createElement("form");
  composer.className = "composer";
  composer.id = "composer";
  const prompt = document.createElement("input");
  prompt.id = "prompt";
  prompt.type = "text";
  prompt.placeholder = "Ask something, or use the buttons below…";
  prompt.autocomplete = "off";
  const sendBtn = button("Send");
  sendBtn.type = "submit";
  composer.append(prompt, sendBtn);

  const actions = el("div");
  actions.className = "actions";
  const readBtn = button("Read screen");
  readBtn.title = "Capture a screen, extract the text, and summarize it.";
  const shotBtn = button("Screenshot");
  shotBtn.title = "Capture a screen and send the image with your typed prompt.";
  const talkBtn = button("Talk");
  talkBtn.title = "Record your voice, transcribe it, and send it.";
  const clearBtn = button("Clear", "ghost");
  clearBtn.title = "Erase this conversation.";
  actions.append(readBtn, shotBtn, talkBtn, clearBtn);

  const meta = el("div");
  meta.className = "meta";
  const modelLabel = el("label");
  modelLabel.append(document.createTextNode("Model"));
  const modelSelect = document.createElement("select");
  modelSelect.id = "model";
  modelLabel.append(modelSelect);
  const voiceBtn = button("Voice: Off", "ghost");
  voiceBtn.id = "voice";
  voiceBtn.type = "button";
  voiceBtn.setAttribute("aria-pressed", "false");
  voiceBtn.title = "Spoken replies are off until you turn them on.";
  meta.append(modelLabel, voiceBtn);

  const options = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Options";
  const optionsBody = el("div");
  optionsBody.className = "options";
  const keyMeta = el("p");
  keyMeta.className = "fine";
  const voiceLabel = el("label");
  voiceLabel.append(document.createTextNode("Spoken voice"));
  const voiceSelect = document.createElement("select");
  voiceSelect.id = "voice-name";
  voiceLabel.append(voiceSelect);
  const hint = el("p", SHORTCUTS);
  hint.className = "hint";
  const changeKey = button("Change key", "ghost");
  changeKey.type = "button";
  optionsBody.append(keyMeta, voiceLabel, hint, changeKey);
  options.append(summary, optionsBody);

  main.append(consent, fallbackNote, log, status, composer, actions, meta, options);
  app.append(header, keyScreen, main);
  mount.append(app);

  const parkedDetail = document.getElementById("parked-detail");
  const parkedReattach = document.getElementById("parked-reattach");

  function host(): Window {
    return app.ownerDocument.defaultView ?? window;
  }

  function setStatus(text: string): void {
    status.textContent = text;
  }

  function appendLog(kind: "user" | "assistant" | "system", text: string): void {
    const empty = log.querySelector(".hint-msg");
    empty?.remove();
    const article = el("article");
    article.className = `msg ${kind}`;
    if (kind !== "system") {
      const who = el("span", kind === "user" ? "You" : "AI");
      article.append(who);
    }
    const body = el("p", text);
    article.append(body);
    log.append(article);
    log.scrollTop = log.scrollHeight;
  }

  function showHint(): void {
    log.replaceChildren();
    const hintMsg = el(
      "p",
      "Ask a question, read the screen, or talk. Nothing is captured until you trigger it.",
    );
    hintMsg.className = "hint-msg";
    log.append(hintMsg);
  }

  function setBusy(next: boolean, message?: string): void {
    busy = next;
    prompt.disabled = next;
    sendBtn.disabled = next;
    readBtn.disabled = next;
    shotBtn.disabled = next;
    clearBtn.disabled = next;
    modelSelect.disabled = next;
    talkBtn.disabled = next && !recorder.active;
    app.setAttribute("aria-busy", next ? "true" : "false");
    if (message) setStatus(message);
    else if (!next && !recorder.active) setStatus("Ready.");
  }

  function fillModels(models: string[]): void {
    const selected = prefs.model;
    const values = models.includes(selected) ? models : [selected, ...models];
    modelSelect.replaceChildren();
    for (const name of values) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      modelSelect.append(option);
    }
    modelSelect.value = selected;
  }

  function refreshVoices(): void {
    const voices = listVoices(host());
    const current = prefs.voiceName;
    voiceSelect.replaceChildren();
    const auto = document.createElement("option");
    auto.value = "";
    auto.textContent = "Browser default";
    voiceSelect.append(auto);
    for (const voice of voices) {
      const option = document.createElement("option");
      option.value = voice.name;
      option.textContent = `${voice.name} (${voice.lang})`;
      voiceSelect.append(option);
    }
    const names = new Set(voices.map((voice) => voice.name));
    voiceSelect.value = names.has(current) ? current : "";
  }

  function updateKeyMeta(): void {
    if (!key) {
      keyMeta.textContent = "";
      return;
    }
    keyMeta.textContent = `Key ${maskKey(key.key)} · ${formatExpiry(key.expiresAt)}`;
  }

  function showKeyScreen(notice = ""): void {
    keyScreen.hidden = false;
    main.hidden = true;
    keyError.textContent = notice;
    saveBtn.disabled = false;
    saveBtn.textContent = "Save and continue";
    confirmRemove = false;
    changeKey.textContent = "Change key";
  }

  function showMain(): void {
    keyScreen.hidden = true;
    main.hidden = false;
    updateKeyMeta();
    refreshVoices();
    if (!log.childElementCount) showHint();
    if (key && !modelsLoaded) {
      modelsLoaded = true;
      const saved = key;
      void listModels(saved.key).then((models) => {
        if (key?.key === saved.key) fillModels(models);
      });
    }
    prompt.focus();
  }

  function dropKey(notice: string): void {
    key = null;
    store.clear();
    conversation.reset();
    voiceOn = false;
    voiceBtn.textContent = "Voice: Off";
    voiceBtn.setAttribute("aria-pressed", "false");
    talkBtn.textContent = "Talk";
    silence(host());
    if (recorder.active) void recorder.stop().catch(() => undefined);
    setBusy(false);
    showHint();
    showKeyScreen(notice);
  }

  function watchKey(): void {
    if (!key) return;
    const current = store.load();
    if (!current) {
      dropKey("Your saved API key expired after 7 days. Add it again to continue.");
      return;
    }
    key = current;
    updateKeyMeta();
  }

  function stillAuthorized(): boolean {
    if (key && store.load()) return true;
    conversation.rollbackUserTurn();
    if (key) dropKey("Your saved API key expired after 7 days. Add it again to continue.");
    else setBusy(false);
    return false;
  }

  async function completeText(userText: string): Promise<void> {
    if (!key) return;
    const messages = conversation.beginUserTurn(userText);
    const model = prefs.model;
    const apiKey = key.key;
    setStatus("Processing…");
    try {
      const reply = await createChatCompletion(apiKey, model, messages);
      if (!stillAuthorized()) return;
      conversation.commitAssistant(reply || "(empty reply)");
      appendLog("assistant", reply || "(empty reply)");
      if (voiceOn) speak(host(), reply, prefs.voiceName);
      setBusy(false);
    } catch (error) {
      conversation.rollbackUserTurn();
      appendLog("system", describe(error));
      setBusy(false);
    }
  }

  keyForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = keyInput.value.trim();
    if (!value.startsWith("sk-") || value.length < 20) {
      keyError.textContent = "Enter an OpenAI key that starts with sk-.";
      return;
    }
    keyError.textContent = "";
    saveBtn.disabled = true;
    saveBtn.textContent = "Checking key…";
    void verifyApiKey(value)
      .then(() => {
        key = store.save(value);
        keyInput.value = "";
        modelsLoaded = false;
        showMain();
      })
      .catch((error: unknown) => {
        keyError.textContent = describe(error);
      })
      .finally(() => {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save and continue";
      });
  });

  toggleKey.addEventListener("click", () => {
    const showing = keyInput.type === "text";
    keyInput.type = showing ? "password" : "text";
    toggleKey.textContent = showing ? "Show" : "Hide";
  });

  composer.addEventListener("submit", (event) => {
    event.preventDefault();
    if (busy) return;
    const text = prompt.value.trim();
    if (!text) {
      setStatus("Type a question first.");
      return;
    }
    prompt.value = "";
    appendLog("user", text);
    setBusy(true, "Processing…");
    void completeText(text);
  });

  readBtn.addEventListener("click", () => {
    if (busy) return;
    setBusy(true, "Choose a screen or window to share…");
    void (async () => {
      let image: Blob;
      try {
        image = await captureFrame(host());
      } catch (error) {
        appendLog("system", describe(error, "Screen capture was cancelled."));
        setBusy(false);
        return;
      }
      setStatus("Reading text on screen…");
      let text = "";
      try {
        text = await recognizeText(image);
      } catch (error) {
        appendLog("system", `OCR failed: ${describe(error)}`);
        setBusy(false);
        return;
      }
      if (!text) {
        appendLog("system", "No readable text found on screen.");
        setBusy(false);
        return;
      }
      appendLog("user", "[Read screen → summarize]");
      const summaryPrompt = `Here is text captured from my screen:\n\n${text}\n\nSummarize it.`;
      await completeText(summaryPrompt);
    })();
  });

  shotBtn.addEventListener("click", () => {
    if (busy) return;
    const question = prompt.value.trim();
    if (!question) {
      setStatus("Type what to ask about the screen first.");
      return;
    }
    if (!key) return;
    setBusy(true, "Choose a screen or window to share…");
    const apiKey = key.key;
    const model = prefs.model;
    void (async () => {
      let image: Blob;
      try {
        image = await captureFrame(host());
      } catch (error) {
        appendLog("system", describe(error, "Screen capture was cancelled."));
        setBusy(false);
        return;
      }
      prompt.value = "";
      appendLog("user", `[Screenshot] ${question}`);
      setStatus("Sending the screenshot…");
      try {
        const dataUrl = await blobToDataUrl(image);
        const messages = conversation.visionMessages(question, dataUrl);
        const reply = await createChatCompletion(apiKey, model, messages);
        if (!key || !store.load()) {
          if (key) dropKey("Your saved API key expired after 7 days. Add it again to continue.");
          else setBusy(false);
          return;
        }
        conversation.commitVision(question, reply || "(empty reply)");
        appendLog("assistant", reply || "(empty reply)");
        if (voiceOn) speak(host(), reply, prefs.voiceName);
        setBusy(false);
      } catch (error) {
        appendLog("system", describe(error));
        setBusy(false);
      }
    })();
  });

  talkBtn.addEventListener("click", () => {
    if (recorder.active) {
      talkBtn.textContent = "Talk";
      setBusy(true, "Transcribing…");
      void (async () => {
        try {
          const audio = await recorder.stop();
          if (!key) {
            setBusy(false);
            return;
          }
          const text = await transcribeAudio(key.key, audio);
          if (!text) {
            appendLog("system", "Could not understand the audio.");
            setBusy(false);
            return;
          }
          appendLog("user", text);
          await completeText(text);
        } catch (error) {
          appendLog("system", describe(error));
          setBusy(false);
        }
      })();
      return;
    }
    if (busy) return;
    void recorder.start(host()).then(
      () => {
        talkBtn.textContent = "Stop";
        setStatus("Recording… click Stop when done.");
      },
      (error: unknown) => {
        appendLog("system", describe(error, "Microphone error."));
      },
    );
  });

  clearBtn.addEventListener("click", () => {
    if (busy) {
      setStatus("Please wait for the current request to finish.");
      return;
    }
    conversation.reset();
    silence(host());
    showHint();
    setStatus("Conversation cleared.");
  });

  voiceBtn.addEventListener("click", () => {
    voiceOn = !voiceOn;
    voiceBtn.textContent = voiceOn ? "Voice: On" : "Voice: Off";
    voiceBtn.setAttribute("aria-pressed", voiceOn ? "true" : "false");
    if (!voiceOn) silence(host());
    setStatus(voiceOn ? "Voice replies on." : "Voice replies off.");
  });

  modelSelect.addEventListener("change", () => {
    prefs.model = modelSelect.value;
    savePrefs(storage, prefs);
    setStatus(`Model set to ${prefs.model}.`);
  });

  voiceSelect.addEventListener("change", () => {
    prefs.voiceName = voiceSelect.value;
    savePrefs(storage, prefs);
  });

  changeKey.addEventListener("click", () => {
    if (!confirmRemove) {
      confirmRemove = true;
      changeKey.textContent = "Confirm remove";
      return;
    }
    dropKey("Add a new OpenAI API key. The previous one was removed from this browser.");
  });

  detachBtn.addEventListener("click", () => {
    if (session) {
      session.close();
      return;
    }
    void detachElement(app, mount, () => {
      session = null;
      mount.hidden = false;
      parked.hidden = true;
      detachBtn.textContent = "Detach";
      fallbackNote.hidden = true;
      bindHost(window);
      if (!keyScreen.hidden) keyInput.focus();
      else prompt.focus();
    })
      .then((opened) => {
        if (opened.external.closed) return;
        session = opened;
        mount.hidden = true;
        parked.hidden = false;
        detachBtn.textContent = "Re-attach";
        fallbackNote.hidden = opened.alwaysOnTop;
        bindHost(opened.external);
        if (parkedDetail) {
          parkedDetail.textContent = opened.alwaysOnTop
            ? "It is floating in an always-on-top window."
            : "Always-on-top isn't supported in this browser. The popup can sit behind other windows. Chrome and Edge provide the always-on-top window.";
        }
        refreshVoices();
      })
      .catch((error: unknown) => {
        setStatus(describe(error));
      });
  });

  parkedReattach?.addEventListener("click", () => {
    session?.close();
  });

  function onKey(event: KeyboardEvent): void {
    if (event.repeat) return;
    const onKeyScreen = !keyScreen.hidden;
    const blocked = busy && !recorder.active;
    if (onKeyScreen || blocked) return;
    const combo = (event.ctrlKey || event.metaKey) && event.shiftKey;
    if (!combo) return;
    const keyName = event.key.toLowerCase();
    if (keyName === "s") {
      event.preventDefault();
      readBtn.click();
    } else if (keyName === "t") {
      event.preventDefault();
      talkBtn.click();
    }
  }

  function bindHost(win: Window): void {
    if (keyDoc !== win.document) {
      keyDoc?.removeEventListener("keydown", onKey);
      win.document.addEventListener("keydown", onKey);
      keyDoc = win.document;
    }
    if (voiceWin !== win) {
      voiceWin?.speechSynthesis?.removeEventListener("voiceschanged", refreshVoices);
      win.speechSynthesis?.addEventListener("voiceschanged", refreshVoices);
      voiceWin = win;
    }
  }

  window.setInterval(watchKey, 1000);
  document.addEventListener("visibilitychange", watchKey);
  window.addEventListener("storage", (event) => {
    if (event.key === null || event.key === KEY_STORAGE_ID) watchKey();
  });

  bindHost(window);
  fillModels([prefs.model, ...FALLBACK_MODELS.filter((name) => name !== prefs.model)]);
  if (key) showMain();
  else showKeyScreen();
}

function el(tag: string, text?: string): HTMLElement {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(text: string, kind?: "ghost"): HTMLButtonElement {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = text;
  if (kind) node.className = kind;
  return node;
}

function describe(error: unknown, fallback = "Something went wrong."): string {
  if (error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "AbortError")) {
    return "Permission was dismissed. Nothing was captured.";
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
