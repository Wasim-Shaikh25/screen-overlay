import assert from "node:assert/strict";
import { test } from "node:test";

import {
  Conversation,
  MAX_HISTORY_MESSAGES,
  SYSTEM_PROMPT,
} from "./conversation.ts";
import { audioFilename, filterChatModels } from "./openai.ts";
import { preferredDetachMode } from "./detach.ts";

test("text turns keep a system prompt and roll back a failed user turn", () => {
  const conversation = new Conversation();
  const messages = conversation.beginUserTurn("hello");
  assert.equal(messages[0]?.role, "system");
  assert.equal(messages[0] && "content" in messages[0] ? messages[0].content : "", SYSTEM_PROMPT);
  assert.equal(messages.at(-1)?.role, "user");
  conversation.rollbackUserTurn();
  assert.equal(conversation.length, 0);
});

test("a screenshot is sent once and only a text placeholder stays in history", () => {
  const conversation = new Conversation();
  conversation.beginUserTurn("earlier");
  conversation.commitAssistant("noted");
  const messages = conversation.visionMessages("what is this?", "data:image/jpeg;base64,abc");
  const last = messages.at(-1);
  assert.equal(last?.role, "user");
  assert.ok(Array.isArray(last && "content" in last ? last.content : null));
  conversation.commitVision("what is this?", "a window");
  const followUp = conversation.beginUserTurn("and then?");
  const stored = followUp.filter((message) => message.role === "user").map((message) => message.content);
  assert.deepEqual(stored, ["earlier", "[screenshot] what is this?", "and then?"]);
});

test("history keeps the newest 200 messages", () => {
  const conversation = new Conversation();
  for (let i = 0; i < MAX_HISTORY_MESSAGES + 5; i += 1) {
    conversation.beginUserTurn(`m${i}`);
    conversation.commitAssistant(`a${i}`);
  }
  assert.equal(conversation.length, MAX_HISTORY_MESSAGES);
  const messages = conversation.beginUserTurn("tail");
  const firstUser = messages.find((message) => message.role === "user");
  assert.notEqual(
    firstUser && "content" in firstUser ? firstUser.content : "",
    "m0",
  );
});

test("model filtering keeps chat models and falls back when none match", () => {
  assert.deepEqual(
    filterChatModels([
      "gpt-4o-mini",
      "gpt-4o-audio-preview",
      "text-embedding-3-small",
      "whisper-1",
      "o4-mini",
      "gpt-4o-mini",
    ]),
    ["gpt-4o-mini", "o4-mini"],
  );
  const fallback = filterChatModels(["whisper-1", "tts-1"]);
  assert.ok(fallback.includes("gpt-4o-mini"));
});

test("transcription uploads use a filename OpenAI accepts", () => {
  assert.equal(audioFilename("audio/webm;codecs=opus"), "speech.webm");
  assert.equal(audioFilename("audio/mp4"), "speech.m4a");
  assert.equal(audioFilename("audio/wav"), "speech.wav");
});

test("detach prefers picture-in-picture and falls back to a popup", () => {
  assert.equal(preferredDetachMode(true), "pip");
  assert.equal(preferredDetachMode(false), "popup");
});
