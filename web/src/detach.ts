export type DetachMode = "pip" | "popup";

export function preferredDetachMode(hasDocumentPictureInPicture: boolean): DetachMode {
  return hasDocumentPictureInPicture ? "pip" : "popup";
}

/**
 * A real Picture-in-Picture window is compact. Some desktops report success
 * but hand back a window the same size as the browser tab, which is not floating.
 */
export function pipWindowIsFloating(
  pipWidth: number,
  pipHeight: number,
  openerWidth: number,
  openerHeight: number,
): boolean {
  if (pipWidth < 240 || pipHeight < 280) return false;
  const widthLikeOpener = Math.abs(pipWidth - openerWidth) < Math.max(80, openerWidth * 0.08);
  const heightLikeOpener = Math.abs(pipHeight - openerHeight) < Math.max(80, openerHeight * 0.12);
  const muchWiderThanRequested = pipWidth > DETACH_WIDTH + 120;
  return !(widthLikeOpener && heightLikeOpener && muchWiderThanRequested);
}

export const DETACH_WIDTH = 420;
export const DETACH_HEIGHT = 680;

export interface DetachedSession {
  mode: DetachMode;
  alwaysOnTop: boolean;
  external: Window;
  close: () => void;
}

interface PictureInPicture {
  requestWindow(options?: { width?: number; height?: number }): Promise<Window>;
}

function pipApi(host: Window): PictureInPicture | null {
  const candidate = (host as Window & { documentPictureInPicture?: PictureInPicture })
    .documentPictureInPicture;
  if (!candidate || typeof candidate.requestWindow !== "function") return null;
  return candidate;
}

function copyStyles(from: Document, to: Document): void {
  const chunks: string[] = [];
  for (const sheet of from.styleSheets) {
    try {
      chunks.push([...sheet.cssRules].map((rule) => rule.cssText).join("\n"));
    } catch {
      if (sheet.href) {
        const link = to.createElement("link");
        link.rel = "stylesheet";
        link.href = sheet.href;
        to.head.appendChild(link);
      }
    }
  }
  const style = to.createElement("style");
  style.textContent = chunks.join("\n");
  to.head.appendChild(style);
}

function prepareDocument(doc: Document): void {
  doc.documentElement.lang = "en";
  doc.documentElement.classList.add("detached");
  doc.title = "AI Overlay";
  if (!doc.querySelector("meta[name=viewport]")) {
    const meta = doc.createElement("meta");
    meta.name = "viewport";
    meta.content = "width=device-width, initial-scale=1";
    doc.head.appendChild(meta);
  }
}

function mountInto(from: Document, target: Document, app: HTMLElement): void {
  prepareDocument(target);
  copyStyles(from, target);
  target.body.appendChild(app);
}

/**
 * Move `app` into an always-on-top Document Picture-in-Picture window when the
 * browser supports it, otherwise into a small popup. `onReturned` runs after
 * the element is back in `home`.
 */
let pictureInPictureUnusable = false;

function openPopup(opener: Window): Window {
  const popup = opener.open(
    "",
    "ai-overlay-detached",
    `popup=yes,width=${DETACH_WIDTH},height=${DETACH_HEIGHT},left=80,top=80,resizable=yes`,
  );
  if (!popup) {
    throw new Error(
      "The browser blocked the popup. Allow popups for this site, then try Detach again.",
    );
  }
  popup.document.open();
  popup.document.write(
    "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>AI Overlay</title></head><body></body></html>",
  );
  popup.document.close();
  try {
    popup.resizeTo(DETACH_WIDTH, DETACH_HEIGHT);
    popup.moveTo(80, 80);
  } catch {
    /* Some browsers ignore scripted resize. The requested size is still a hint. */
  }
  return popup;
}

export async function detachElement(
  app: HTMLElement,
  home: HTMLElement,
  onReturned: (session: DetachedSession) => void,
): Promise<DetachedSession> {
  const opener = window;
  const pip = pictureInPictureUnusable ? null : pipApi(opener);
  let external: Window;
  let mode: DetachMode;
  let alwaysOnTop: boolean;

  if (pip) {
    let candidate: Window;
    try {
      candidate = await pip.requestWindow({ width: DETACH_WIDTH, height: DETACH_HEIGHT });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not open the floating window.";
      throw new Error(message);
    }
    mountInto(opener.document, candidate.document, app);
    await new Promise((resolve) => opener.setTimeout(resolve, 60));
    if (
      pipWindowIsFloating(
        candidate.innerWidth,
        candidate.innerHeight,
        opener.innerWidth,
        opener.innerHeight,
      )
    ) {
      external = candidate;
      mode = "pip";
      alwaysOnTop = true;
    } else {
      if (!home.contains(app)) home.appendChild(app);
      candidate.close();
      pictureInPictureUnusable = true;
      throw new Error(
        "This browser didn't open an always-on-top window. Click Detach again to open a popup.",
      );
    }
  } else {
    external = openPopup(opener);
    mode = "popup";
    alwaysOnTop = false;
    mountInto(opener.document, external.document, app);
  }

  let settled = false;
  const session: DetachedSession = {
    mode,
    alwaysOnTop,
    external,
    close() {
      takeBack();
      if (!external.closed) external.close();
    },
  };

  const timer = opener.setInterval(() => {
    if (external.closed) takeBack();
  }, 400);

  function takeBack(): void {
    if (settled) return;
    settled = true;
    opener.clearInterval(timer);
    try {
      if (!home.contains(app)) home.appendChild(app);
    } catch {
      /* The floating document has already been discarded. */
    }
    onReturned(session);
  }

  external.addEventListener("pagehide", () => {
    takeBack();
  });

  return session;
}
