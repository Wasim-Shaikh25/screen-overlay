import { createWorker, type Worker } from "tesseract.js";

let workerPromise: Promise<Worker> | null = null;

function asset(path: string): string {
  return new URL(path, document.baseURI).href;
}

function getWorker(): Promise<Worker> {
  if (!workerPromise) {
    workerPromise = createWorker("eng", 1, {
      workerPath: asset("tesseract/worker.min.js"),
      corePath: asset("tesseract/"),
      langPath: asset("tesseract/"),
    }).catch((error: unknown) => {
      workerPromise = null;
      throw error;
    });
  }
  return workerPromise;
}

/** English OCR in the browser. Language data is served by this same site. */
export async function recognizeText(image: Blob): Promise<string> {
  const worker = await getWorker();
  const result = await worker.recognize(image);
  return (result.data.text || "").replace(/\s+\n/g, "\n").trim();
}
