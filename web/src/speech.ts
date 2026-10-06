interface RecorderWindow extends Window {
  MediaRecorder: typeof MediaRecorder;
}

export class MicRecorder {
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];

  get active(): boolean {
    return this.recorder !== null && this.recorder.state === "recording";
  }

  async start(host: Window): Promise<void> {
    if (this.active) return;
    const media = host.navigator.mediaDevices;
    if (!media?.getUserMedia) {
      throw new Error("This browser cannot use the microphone.");
    }
    const Recorder = (host as RecorderWindow).MediaRecorder;
    if (typeof Recorder !== "function") {
      throw new Error("This browser cannot record the microphone.");
    }
    this.stream = await media.getUserMedia({ audio: true });
    const preferred = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
    const mime = preferred.find((type) => Recorder.isTypeSupported(type));
    this.chunks = [];
    this.recorder = new Recorder(this.stream, mime ? { mimeType: mime } : undefined);
    this.recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    });
    this.recorder.start();
  }

  async stop(): Promise<Blob> {
    const recorder = this.recorder;
    if (!recorder) throw new Error("Not currently recording.");
    const blob = await new Promise<Blob>((resolve) => {
      recorder.addEventListener(
        "stop",
        () => {
          resolve(new Blob(this.chunks, { type: recorder.mimeType || "audio/webm" }));
        },
        { once: true },
      );
      if (recorder.state === "inactive") {
        resolve(new Blob(this.chunks, { type: recorder.mimeType || "audio/webm" }));
      } else {
        recorder.stop();
      }
    });
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.recorder = null;
    this.chunks = [];
    return blob;
  }
}

export function listVoices(host: Window): SpeechSynthesisVoice[] {
  return host.speechSynthesis?.getVoices() ?? [];
}

export function speak(host: Window, text: string, voiceName: string): void {
  const synth = host.speechSynthesis;
  const spoken = text.trim();
  if (!synth || !spoken) return;
  synth.cancel();
  const Utterance = (host as Window & { SpeechSynthesisUtterance: typeof SpeechSynthesisUtterance })
    .SpeechSynthesisUtterance;
  const utterance = new Utterance(spoken);
  const voice = synth.getVoices().find((item) => item.name === voiceName);
  if (voice) utterance.voice = voice;
  synth.speak(utterance);
}

export function silence(host: Window): void {
  host.speechSynthesis?.cancel();
}
