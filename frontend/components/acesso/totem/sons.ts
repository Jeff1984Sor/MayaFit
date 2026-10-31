"use client";

// Sons do totem gerados na hora (WebAudio): nada de arquivo de áudio.
let ctx: AudioContext | null = null;

function audio(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const C = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!C) return null;
  ctx ??= new C();
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

/** Destrava o áudio no primeiro toque (navegadores exigem gesto do usuário). */
export function destravarAudio() {
  audio();
}

function nota(freq: number, inicio: number, dur: number, tipo: OscillatorType = "sine", volume = 0.18) {
  const a = audio();
  if (!a) return;
  const t = a.currentTime + inicio;
  const o = a.createOscillator();
  const g = a.createGain();
  o.type = tipo;
  o.frequency.setValueAtTime(freq, t);
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(volume, t + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(a.destination);
  o.start(t);
  o.stop(t + dur + 0.05);
}

/** Dois toques agradáveis (sol-dó). */
export function somSucesso() {
  nota(784, 0, 0.35);
  nota(1047, 0.13, 0.55);
}

/** Tom grave e suave, sem susto. */
export function somNegado() {
  nota(330, 0, 0.3, "triangle", 0.14);
  nota(262, 0.18, 0.45, "triangle", 0.12);
}

/** Melodia curtinha de parabéns. */
export function somAniversario() {
  [523, 523, 587, 523, 698, 659].forEach((f, i) => nota(f, i * 0.16, 0.3, "sine", 0.14));
}

export function somToque() {
  nota(1200, 0, 0.06, "sine", 0.06);
}
