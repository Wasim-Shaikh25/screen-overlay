/** In-memory chat history. Matches the desktop client's session behaviour. */

export const SYSTEM_PROMPT =
  "You are a helpful desktop assistant. You help the user summarize and reason " +
  "about content they explicitly share with you: screen text, their own voice " +
  "input, code, emails, and documents. Be concise and practical. When given " +
  "OCR'd screen text, treat it as possibly noisy and focus on the user's intent.";

export const MAX_HISTORY_MESSAGES = 200;

export type TextTurn = { role: "user" | "assistant"; content: string };

export type ChatContentPart =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string } };

export type ChatMessage =
  | { role: "system"; content: string }
  | TextTurn
  | { role: "user"; content: ChatContentPart[] };

export class Conversation {
  private history: TextTurn[] = [];

  reset(): void {
    this.history = [];
  }

  get length(): number {
    return this.history.length;
  }

  beginUserTurn(text: string): ChatMessage[] {
    this.history.push({ role: "user", content: text });
    this.trim();
    return this.withSystem();
  }

  rollbackUserTurn(): void {
    const last = this.history[this.history.length - 1];
    if (last?.role === "user") this.history.pop();
  }

  commitAssistant(text: string): void {
    this.history.push({ role: "assistant", content: text });
    this.trim();
  }

  visionMessages(prompt: string, dataUrl: string): ChatMessage[] {
    return [
      ...this.withSystem(),
      {
        role: "user",
        content: [
          { type: "text", text: prompt },
          { type: "image_url", image_url: { url: dataUrl } },
        ],
      },
    ];
  }

  commitVision(prompt: string, reply: string): void {
    this.history.push({ role: "user", content: `[screenshot] ${prompt}` });
    this.history.push({ role: "assistant", content: reply });
    this.trim();
  }

  private withSystem(): ChatMessage[] {
    return [{ role: "system", content: SYSTEM_PROMPT }, ...this.history];
  }

  private trim(): void {
    if (this.history.length > MAX_HISTORY_MESSAGES) {
      this.history = this.history.slice(-MAX_HISTORY_MESSAGES);
    }
  }
}
