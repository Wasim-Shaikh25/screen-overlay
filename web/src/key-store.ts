/** Browser-only API key storage. Nothing here is sent to the self-hosted server. */

export const KEY_STORAGE_ID = "ai-overlay.openai-key.v1";
export const PREFS_STORAGE_ID = "ai-overlay.prefs.v1";
export const KEY_TTL_MS = 7 * 24 * 60 * 60 * 1000;

const FUTURE_SKEW_MS = 60_000;

export interface KeyStatus {
  key: string;
  savedAt: number;
  expiresAt: number;
}

export interface KeyStorage {
  getItem(id: string): string | null;
  setItem(id: string, value: string): void;
  removeItem(id: string): void;
}

export interface Prefs {
  model: string;
  voiceName: string;
}

export const DEFAULT_PREFS: Prefs = {
  model: "gpt-4o-mini",
  voiceName: "",
};

export function parseStoredKey(raw: string | null, now = Date.now()): KeyStatus | null {
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const record = parsed as { key?: unknown; savedAt?: unknown };
  if (typeof record.key !== "string") return null;
  const key = record.key.trim();
  if (!key) return null;
  if (typeof record.savedAt !== "number" || !Number.isFinite(record.savedAt)) return null;
  if (record.savedAt > now + FUTURE_SKEW_MS) return null;
  const expiresAt = record.savedAt + KEY_TTL_MS;
  if (now >= expiresAt) return null;
  return { key, savedAt: record.savedAt, expiresAt };
}

export function maskKey(secret: string): string {
  if (!secret) return "(not set)";
  if (secret.length <= 8) return "••••";
  return `••••${secret.slice(-4)}`;
}

export function formatExpiry(expiresAt: number, now = Date.now()): string {
  const ms = expiresAt - now;
  if (ms <= 0) return "expired";
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (ms < hour) {
    const minutes = Math.max(1, Math.ceil(ms / minute));
    return `expires in ${minutes} min`;
  }
  if (ms < day) {
    const hours = Math.ceil(ms / hour);
    return `expires in ${hours} ${hours === 1 ? "hour" : "hours"}`;
  }
  const days = Math.ceil(ms / day);
  return `expires in ${days} ${days === 1 ? "day" : "days"}`;
}

export class ApiKeyStore {
  private readonly storage: KeyStorage;
  private readonly now: () => number;

  constructor(storage: KeyStorage, now: () => number = () => Date.now()) {
    this.storage = storage;
    this.now = now;
  }

  load(): KeyStatus | null {
    const raw = this.storage.getItem(KEY_STORAGE_ID);
    const status = parseStoredKey(raw, this.now());
    if (raw && !status) this.storage.removeItem(KEY_STORAGE_ID);
    return status;
  }

  save(key: string): KeyStatus {
    const savedAt = this.now();
    const trimmed = key.trim();
    const status: KeyStatus = {
      key: trimmed,
      savedAt,
      expiresAt: savedAt + KEY_TTL_MS,
    };
    this.storage.setItem(
      KEY_STORAGE_ID,
      JSON.stringify({ key: status.key, savedAt: status.savedAt }),
    );
    return status;
  }

  clear(): void {
    this.storage.removeItem(KEY_STORAGE_ID);
  }
}

export function loadPrefs(storage: KeyStorage): Prefs {
  const raw = storage.getItem(PREFS_STORAGE_ID);
  if (!raw) return { ...DEFAULT_PREFS };
  try {
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    const model =
      typeof parsed.model === "string" && parsed.model.trim()
        ? parsed.model.trim()
        : DEFAULT_PREFS.model;
    const voiceName = typeof parsed.voiceName === "string" ? parsed.voiceName : "";
    return { model, voiceName };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export function savePrefs(storage: KeyStorage, prefs: Prefs): void {
  storage.setItem(PREFS_STORAGE_ID, JSON.stringify(prefs));
}
