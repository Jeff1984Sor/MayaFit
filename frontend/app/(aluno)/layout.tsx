import type { Metadata, Viewport } from "next";

import { RegistrarSW } from "@/components/app-aluno/registrar-sw";

// App do aluno (PWA em /app): fora do shell da equipe. O manifest e os ícones levam a marca do estúdio (vem do banco).
export const metadata: Metadata = {
  title: "Minhas aulas",
  description: "Confirme presença, desmarque e agende reposições.",
  manifest: "/app/manifest.json",
  applicationName: "Minhas aulas",
  appleWebApp: { capable: true, title: "Minhas aulas", statusBarStyle: "default" },
  icons: { icon: "/app/icon.svg", apple: "/app/icone/192" },
  robots: { index: false, follow: false },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#7c8fff",
};

export default function AlunoLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <RegistrarSW />
      {children}
    </>
  );
}
