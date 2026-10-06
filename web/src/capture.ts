const MAX_EDGE = 1600;

/** Capture a single frame, then stop the share so recording does not continue. */
export async function captureFrame(host: Window): Promise<Blob> {
  if (!host.navigator.mediaDevices?.getDisplayMedia) {
    throw new Error("This browser cannot capture the screen.");
  }
  const stream = await host.navigator.mediaDevices.getDisplayMedia({
    video: { frameRate: 1 },
    audio: false,
  });
  try {
    const video = host.document.createElement("video");
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    await video.play();
    if (!video.videoWidth) {
      await new Promise<void>((resolve) => {
        video.addEventListener("loadeddata", () => resolve(), { once: true });
      });
    }
    const longest = Math.max(video.videoWidth, video.videoHeight);
    const scale = longest > 0 ? Math.min(1, MAX_EDGE / longest) : 1;
    const canvas = host.document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Could not read the captured frame.");
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob((value) => resolve(value), "image/jpeg", 0.85);
    });
    if (!blob) throw new Error("Could not encode the screenshot.");
    return blob;
  } finally {
    stream.getTracks().forEach((track) => track.stop());
  }
}

export function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("Could not read the image."));
    reader.readAsDataURL(blob);
  });
}
