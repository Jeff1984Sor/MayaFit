// Next 16: "proxy" (antigo middleware). Verificação OTIMISTA de sessão: sem cookie de refresh, páginas privadas nem renderizam.
// A autorização de verdade é da API (cada chamada confere token, versão do token e permissão do perfil).
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { REFRESH } from "@/lib/server/sessao";

// "assinar": páginas públicas de assinatura de contrato/termo por link (módulo contratos)
// "app": app do aluno (sessão própria, BFF em /app/api)
// "cadastro", "primeiro-acesso", "aprovar": telas públicas do Admin MayaFit (formulário do site e links de e-mail)
const PUBLICAS = /^\/(login|esqueci-senha|redefinir-senha|assinar|app|cadastro|primeiro-acesso|aprovar)(\/|$)/;

export function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  if (PUBLICAS.test(pathname) || req.cookies.has(REFRESH)) return NextResponse.next();
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = pathname === "/" ? "" : `?volta=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  // tudo, menos o BFF, arquivos internos do Next e estáticos
  matcher: ["/((?!bff|_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|webp|ico|css|js|map|txt|webmanifest)$).*)"],
};
