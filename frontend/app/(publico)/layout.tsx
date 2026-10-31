import type { Metadata } from "next";

// Páginas PÚBLICAS (sem login e fora do shell protegido): assinatura de contrato e de termo por link.
// O token está na URL: não indexar nem repassar o endereço como "referrer".
export const metadata: Metadata = {
  title: "Assinatura · MayaFit",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function PublicoLayout({ children }: { children: React.ReactNode }) {
  return <main className="min-h-dvh bg-background px-4 py-8 sm:py-12">{children}</main>;
}
