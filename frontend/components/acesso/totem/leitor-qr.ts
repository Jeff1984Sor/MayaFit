"use client";

import jsQR from "jsqr";

// Leitura de QR pela câmera: BarcodeDetector nativo quando existe (Chrome Android), senão jsQR num canvas.

interface DetectorNativo {
  detect(fonte: CanvasImageSource): Promise<{ rawValue: string }[]>;
}

let nativo: DetectorNativo | null | undefined;

function detectorNativo(): DetectorNativo | null {
  if (nativo !== undefined) return nativo;
  const C = (globalThis as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => DetectorNativo }).BarcodeDetector;
  try {
    nativo = C ? new C({ formats: ["qr_code"] }) : null;
  } catch {
    nativo = null;
  }
  return nativo;
}

let canvas: HTMLCanvasElement | null = null;

export async function lerQr(video: HTMLVideoElement): Promise<string | null> {
  if (!video.videoWidth) return null;
  const d = detectorNativo();
  if (d) {
    try {
      const r = await d.detect(video);
      if (r[0]?.rawValue) return r[0].rawValue;
      return null;
    } catch {
      nativo = null;
    }
  }
  canvas ??= document.createElement("canvas");
  const escala = Math.min(1, 640 / video.videoWidth);
  canvas.width = Math.round(video.videoWidth * escala);
  canvas.height = Math.round(video.videoHeight * escala);
  const c = canvas.getContext("2d", { willReadFrequently: true });
  if (!c) return null;
  c.drawImage(video, 0, 0, canvas.width, canvas.height);
  const img = c.getImageData(0, 0, canvas.width, canvas.height);
  return jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" })?.data ?? null;
}
