import type { ChatMessage } from "./conversation.ts";

export const OPENAI_ORIGIN = "https://api.openai.com";

export const FALLBACK_MODELS = [
  "gpt-4o-mini",
  "gpt-4o",
  "gpt-4.1-mini",
  "gpt-4.1",
  "o4-mini",
];

const SKIP_TOKENS = [
  "embedding",
  "tts",
  "whisper",
  "audio",
  "image",
  "moderation",
  "realtime",
  "transcribe",
  "search",
];

export class OpenAIRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "OpenAIRequestError";
    this.status = status;
  }
}

export function filterChatModels(ids: string[]): string[] {
  const chat = ids.filter((id) => {
    const chatLike =
      id.startsWith("gpt-") ||
      id.startsWith("o1") ||
      id.startsWith("o3") ||
      id.startsWith("o4") ||
      id.startsWith("o5");
    return chatLike && !SKIP_TOKENS.some((token) => id.includes(token));
  });
  const unique = [...new Set(chat)].sort();
  return unique.length > 0 ? unique : [...FALLBACK_MODELS];
}

export function audioFilename(mime: string): string {
  if (mime.includes("mp4") || mime.includes("m4a")) return "speech.m4a";
  if (mime.includes("mpeg") || mime.includes("mp3")) return "speech.mp3";
  if (mime.includes("wav")) return "speech.wav";
  return "speech.webm";
}

async function openaiFetch(apiKey: string, path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${apiKey}`);
  try {
    return await fetch(`${OPENAI_ORIGIN}/v1${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new OpenAIRequestError(
      "Couldn't reach OpenAI. Check your connection and try again.",
      0,
    );
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { error?: { message?: string } };
    if (data.error?.message) return data.error.message;
  } catch {
    /* The body was not JSON. */
  }
  return `OpenAI request failed (HTTP ${res.status}).`;
}

/** Reject keys OpenAI will not accept. A network failure does not store the key. */
export async function verifyApiKey(apiKey: string): Promise<void> {
  const res = await openaiFetch(apiKey, "/models/gpt-4o-mini", { method: "GET" });
  if (res.status === 401 || res.status === 403) {
    throw new OpenAIRequestError(
      "OpenAI rejected that key. Check it and try again.",
      res.status,
    );
  }
  if (res.ok || res.status === 404 || res.status === 429) return;
  throw new OpenAIRequestError(await errorMessage(res), res.status);
}

export async function listModels(apiKey: string): Promise<string[]> {
  try {
    const res = await openaiFetch(apiKey, "/models", { method: "GET" });
    if (!res.ok) return [...FALLBACK_MODELS];
    const data = (await res.json()) as { data?: { id?: string }[] };
    const ids = (data.data ?? [])
      .map((item) => item.id)
      .filter((id): id is string => typeof id === "string");
    return filterChatModels(ids);
  } catch {
    return [...FALLBACK_MODELS];
  }
}

export async function createChatCompletion(
  apiKey: string,
  model: string,
  messages: ChatMessage[],
): Promise<string> {
  const res = await openaiFetch(apiKey, "/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, messages }),
  });
  if (!res.ok) throw new OpenAIRequestError(await errorMessage(res), res.status);
  const data = (await res.json()) as {
    choices?: { message?: { content?: string | null } }[];
  };
  return (data.choices?.[0]?.message?.content ?? "").trim();
}

export async function transcribeAudio(apiKey: string, audio: Blob): Promise<string> {
  const form = new FormData();
  form.append("file", audio, audioFilename(audio.type));
  form.append("model", "whisper-1");
  const res = await openaiFetch(apiKey, "/audio/transcriptions", {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new OpenAIRequestError(await errorMessage(res), res.status);
  const data = (await res.json()) as { text?: string };
  return (data.text ?? "").trim();
}
