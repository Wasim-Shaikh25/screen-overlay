import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ApiKeyStore,
  KEY_STORAGE_ID,
  KEY_TTL_MS,
  formatExpiry,
  loadPrefs,
  maskKey,
  parseStoredKey,
  savePrefs,
  type KeyStorage,
} from "./key-store.ts";

function memoryStorage(): KeyStorage & { dump(): Map<string, string> } {
  const values = new Map<string, string>();
  return {
    dump: () => values,
    getItem: (id) => values.get(id) ?? null,
    setItem: (id, value) => values.set(id, value),
    removeItem: (id) => values.delete(id),
  };
}

test("a key is valid until the 7 day mark and gone at the mark", () => {
  const savedAt = 1_700_000_000_000;
  const raw = JSON.stringify({ key: " sk-test-key ", savedAt });
  const justBefore = parseStoredKey(raw, savedAt + KEY_TTL_MS - 1);
  assert.equal(justBefore?.key, "sk-test-key");
  assert.equal(justBefore?.expiresAt, savedAt + KEY_TTL_MS);
  assert.equal(parseStoredKey(raw, savedAt + KEY_TTL_MS), null);
});

test("corrupt, empty, and future records are ignored", () => {
  const now = 1_700_000_000_000;
  assert.equal(parseStoredKey(null, now), null);
  assert.equal(parseStoredKey("not-json", now), null);
  assert.equal(parseStoredKey(JSON.stringify({ key: "sk-abc" }), now), null);
  assert.equal(parseStoredKey(JSON.stringify({ key: "  ", savedAt: now }), now), null);
  assert.equal(
    parseStoredKey(JSON.stringify({ key: "sk-abc", savedAt: now + 120_000 }), now),
    null,
  );
});

test("the store deletes an expired key the next time it is read", () => {
  const storage = memoryStorage();
  let now = 1_000;
  const store = new ApiKeyStore(storage, () => now);
  const saved = store.save("sk-live-key");
  assert.equal(storage.dump().has(KEY_STORAGE_ID), true);
  now = saved.expiresAt;
  assert.equal(store.load(), null);
  assert.equal(storage.dump().has(KEY_STORAGE_ID), false);
});

test("clear removes the key and leaves other preferences alone", () => {
  const storage = memoryStorage();
  const store = new ApiKeyStore(storage, () => 50);
  store.save("sk-live-key");
  savePrefs(storage, { model: "gpt-4o", voiceName: "Aria" });
  store.clear();
  assert.equal(store.load(), null);
  assert.deepEqual(loadPrefs(storage), { model: "gpt-4o", voiceName: "Aria" });
});

test("expiry text counts down in days, hours, and minutes", () => {
  const expiresAt = 10_000_000;
  assert.equal(formatExpiry(expiresAt, expiresAt), "expired");
  assert.equal(formatExpiry(expiresAt, expiresAt - 30_000), "expires in 1 min");
  assert.equal(formatExpiry(expiresAt, expiresAt - 2 * 3_600_000), "expires in 2 hours");
  assert.equal(formatExpiry(expiresAt, expiresAt - 3 * 86_400_000), "expires in 3 days");
});

test("keys are masked before they are shown", () => {
  assert.equal(maskKey(""), "(not set)");
  assert.equal(maskKey("short"), "••••");
  assert.equal(maskKey("sk-proj-abcdef"), "••••cdef");
});
