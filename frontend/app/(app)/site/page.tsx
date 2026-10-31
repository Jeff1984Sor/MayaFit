"use client";

import { SemAcesso } from "@/components/mayacorp/sem-acesso";
import { EditorSite } from "@/components/site/editor/editor-site";
import { useAuth } from "@/lib/auth";

export default function SitePage() {
  const { pode } = useAuth();
  if (!pode("site.ver")) return <SemAcesso titulo="Site do estúdio" />;
  return <EditorSite podeEditar={pode("site.editar")} />;
}
