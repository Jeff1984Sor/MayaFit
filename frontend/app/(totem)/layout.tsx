import type { Metadata, Viewport } from "next";

// Totem de check-in (tablet/notebook na recepção): fora do shell da equipe, tela cheia, sem menu.
export const metadata: Metadata = {
  title: "Totem de check-in",
  description: "Check-in por reconhecimento facial, CPF/código ou QR do app.",
  robots: { index: false, follow: false },
  formatDetection: { telephone: false },
  appleWebApp: { capable: true, title: "Check-in", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
  themeColor: "#0f1729",
};

export default function TotemLayout({ children }: { children: React.ReactNode }) {
  return <div className="dark min-h-dvh overflow-hidden bg-[#0b1120] text-white select-none">{children}</div>;
}
