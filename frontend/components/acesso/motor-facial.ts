"use client";

/**
 * Motor de reconhecimento facial NO NAVEGADOR (@vladmandic/human, MIT), com modelos servidos localmente em
 * `public/totem/modelos` (nada vai para CDN de terceiros). Gera o DESCRITOR (embedding de 1024 números do modelo
 * faceres) e a prova de vida básica (piscar + modelos antispoof/liveness).
 *
 * LGPD: a imagem da câmera nunca sai do navegador; só o descritor é enviado à API para comparar.
 *
 * A biblioteca (2 MB, com TensorFlow.js) é carregada sob demanda de `/totem/human/human.esm.js`, fora do bundle.
 */
import type { Config, FaceResult, Human, Result } from "@vladmandic/human";

const URL_LIB = "/totem/human/human.esm.js";
const URL_MODELOS = "/totem/modelos/";

export interface Leitura {
  rosto: FaceResult | null;
  /** algum olho piscou neste quadro */
  piscou: boolean;
  /** rosto centralizado e grande o bastante para uma boa leitura */
  enquadrado: boolean;
  /** largura do rosto em relação ao vídeo (0..1) */
  tamanho: number;
  qualidade: number;
}

export interface Captura {
  descritores: number[][];
  prova_vida: { piscou: boolean; real: number | null; live: number | null };
  qualidade: number;
}

const CONFIG: Partial<Config> = {
  modelBasePath: URL_MODELOS,
  backend: "webgl",
  warmup: "none",
  cacheModels: true,
  cacheSensitivity: 0,
  debug: false,
  filter: { enabled: true, equalization: false, flip: false },
  face: {
    enabled: true,
    detector: { rotation: true, maxDetected: 1, minConfidence: 0.5, return: false },
    mesh: { enabled: true },
    iris: { enabled: true },
    description: { enabled: true },
    emotion: { enabled: false },
    antispoof: { enabled: true },
    liveness: { enabled: true },
    attention: { enabled: false },
    gear: { enabled: false },
  },
  body: { enabled: false },
  hand: { enabled: false },
  object: { enabled: false },
  segmentation: { enabled: false },
  gesture: { enabled: true },
} as Partial<Config>;

let promessa: Promise<MotorFacial> | null = null;

/** Carrega a biblioteca e os modelos uma única vez por página. */
export function carregarMotor(): Promise<MotorFacial> {
  if (!promessa) {
    promessa = (async () => {
      const mod = (await import(/* webpackIgnore: true */ /* turbopackIgnore: true */ URL_LIB)) as { Human: new (c: Partial<Config>) => Human };
      const human = new mod.Human(CONFIG);
      await human.load();
      return new MotorFacial(human);
    })().catch((e) => {
      promessa = null;
      throw e;
    });
  }
  return promessa;
}

export class MotorFacial {
  constructor(private human: Human) {}

  async ler(video: HTMLVideoElement): Promise<Leitura> {
    const r: Result = await this.human.detect(video);
    const rosto = r.face?.[0] ?? null;
    const largura = video.videoWidth || 1;
    const altura = video.videoHeight || 1;
    if (!rosto || !rosto.embedding?.length) return { rosto: null, piscou: false, enquadrado: false, tamanho: 0, qualidade: 0 };
    const [x, y, w, h] = rosto.box;
    const cx = (x + w / 2) / largura;
    const cy = (y + h / 2) / altura;
    const tamanho = w / largura;
    const enquadrado = tamanho >= 0.18 && Math.abs(cx - 0.5) < 0.2 && Math.abs(cy - 0.5) < 0.25;
    const piscou = (r.gesture ?? []).some((g) => "face" in g && String(g.gesture).startsWith("blink"));
    const qualidade = Math.min(1, (rosto.faceScore ?? rosto.score ?? 0) * Math.min(1, tamanho / 0.3));
    return { rosto, piscou, enquadrado, tamanho, qualidade };
  }
}

/** Câmera frontal (selfie), no tamanho certo para o tablet em pé ou deitado. */
export async function abrirCamera(video: HTMLVideoElement): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Este navegador não dá acesso à câmera. Use Chrome/Edge atualizado, em endereço https.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: "user", width: { ideal: 960 }, height: { ideal: 960 } },
  });
  video.srcObject = stream;
  video.muted = true;
  video.playsInline = true;
  await video.play();
  return stream;
}

export function fecharCamera(stream: MediaStream | null) {
  stream?.getTracks().forEach((t) => t.stop());
}

export function erroDeCamera(e: unknown): string {
  const nome = e instanceof DOMException ? e.name : "";
  if (nome === "NotAllowedError") return "A câmera foi bloqueada. Libere o acesso à câmera nas permissões do navegador.";
  if (nome === "NotFoundError") return "Nenhuma câmera encontrada neste aparelho.";
  if (nome === "NotReadableError") return "A câmera está sendo usada por outro programa.";
  return e instanceof Error ? e.message : "Não foi possível abrir a câmera.";
}

/**
 * Captura com prova de vida: lê quadros até juntar `quantidade` descritores bons e (se exigido) ver uma piscada
 * ou os modelos antispoof/liveness passarem. `aoLer` recebe cada leitura (para desenhar a moldura).
 */
export async function capturar(
  motor: MotorFacial,
  video: HTMLVideoElement,
  opcoes: { quantidade?: number; tempoMaxMs?: number; exigirProvaVida?: boolean; aoLer?: (l: Leitura) => void; cancelado?: () => boolean },
): Promise<Captura> {
  const { quantidade = 3, tempoMaxMs = 12000, exigirProvaVida = true, aoLer, cancelado } = opcoes;
  const inicio = performance.now();
  const bons: { emb: number[]; q: number; t: number }[] = [];
  let piscou = false;
  let real = 0;
  let live = 0;
  while (performance.now() - inicio < tempoMaxMs) {
    if (cancelado?.()) throw new Error("cancelado");
    const l = await motor.ler(video);
    aoLer?.(l);
    if (l.rosto && l.enquadrado) {
      piscou ||= l.piscou;
      real = Math.max(real, l.rosto.real ?? 0);
      live = Math.max(live, l.rosto.live ?? 0);
      const agora = performance.now();
      // quadros espaçados (>= 250 ms) e de boa qualidade dão descritores mais representativos
      if (l.qualidade >= 0.45 && (!bons.length || agora - bons[bons.length - 1].t > 250)) {
        bons.push({ emb: Array.from(l.rosto.embedding as number[]), q: l.qualidade, t: agora });
      }
      const vivo = !exigirProvaVida || piscou || (real >= 0.5 && live >= 0.5);
      if (bons.length >= quantidade && vivo) break;
    }
    await new Promise((r) => setTimeout(r, 60));
  }
  if (bons.length < quantidade) throw new Error("Não consegui ver o rosto direito. Olhe para a câmera, com boa luz, sem boné ou óculos escuros.");
  const vivo = !exigirProvaVida || piscou || (real >= 0.5 && live >= 0.5);
  if (!vivo) throw new Error("Não detectei a piscada. Pisque devagar olhando para a câmera.");
  const escolhidos = bons.sort((a, b) => b.q - a.q).slice(0, quantidade);
  return {
    descritores: escolhidos.map((b) => b.emb),
    prova_vida: { piscou, real: real || null, live: live || null },
    qualidade: escolhidos.reduce((s, b) => s + b.q, 0) / escolhidos.length,
  };
}
