"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleUserRound, Compass, Gem, Moon, Sun, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { Command } from "@/components/ui/command";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

import { navPara } from "./nav";
import { iniciarTour } from "./tour";

const EVENTO = "maya:paleta";
export const abrirPaleta = () => window.dispatchEvent(new Event(EVENTO));

interface AlunoBusca {
  id: number;
  nome: string;
  cpf_mascarado: string | null;
  telefone: string | null;
  status: string;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const router = useRouter();
  const { usuario, pode } = useAuth();
  const { setTheme, resolvedTheme } = useTheme();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "/" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        const campo = document.querySelector<HTMLInputElement>("input[data-busca]");
        if (campo) {
          e.preventDefault();
          campo.focus();
        }
      }
    };
    const onAbrir = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(EVENTO, onAbrir);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(EVENTO, onAbrir);
    };
  }, []);

  // Busca de alunos (nome, CPF ou telefone) a partir de 2 letras; outros registros entram com cada módulo.
  const termo = useDebounce(q.trim(), 250);
  const podeBuscarAluno = pode("alunos.ver") && !usuario?.estudio?.mayacorp;
  const { data: alunos = [] } = useQuery({
    queryKey: ["paleta-alunos", termo],
    queryFn: () => api.get<AlunoBusca[]>("/alunos/busca", { q: termo }),
    enabled: open && podeBuscarAluno && termo.length >= 2,
    staleTime: 15_000,
  });
  const ativo = false;

  const ir = (href: string) => {
    setOpen(false);
    setQ("");
    router.push(href);
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title="Busca rápida" description="Busque alunos ou vá para qualquer tela do sistema">
      <Command shouldFilter={!ativo}>
        <CommandInput placeholder={podeBuscarAluno ? "Busque um aluno ou digite o nome de uma tela…" : "Digite o nome de uma tela…"} value={q} onValueChange={setQ} />
        <CommandList className="max-h-[420px]">
          <CommandEmpty>Nada encontrado.</CommandEmpty>
          {alunos.length > 0 && (
            <CommandGroup heading="Alunos">
              {alunos.map((a) => (
                <CommandItem key={`aluno-${a.id}`} forceMount value={`aluno ${a.id} ${a.nome}`} onSelect={() => ir(`/alunos/${a.id}`)}>
                  <UserRound />
                  <span className="truncate">{a.nome}</span>
                  <CommandShortcut>{[a.cpf_mascarado, a.telefone].filter(Boolean).join(" · ")}</CommandShortcut>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {!ativo &&
            navPara(usuario && pode, { mayacorp: !!usuario?.estudio?.mayacorp, recursos: usuario?.estudio?.recursos }).map((g) => (
              <CommandGroup key={g.titulo} heading={g.titulo}>
                {g.itens
                  .filter((i) => !i.planejado)
                  .map((i) => (
                    <CommandItem key={i.href} value={`${g.titulo} ${i.label}`} onSelect={() => ir(i.href)}>
                      <i.icone />
                      {i.label}
                      {i.atalho && <CommandShortcut>{i.atalho}</CommandShortcut>}
                    </CommandItem>
                  ))}
              </CommandGroup>
            ))}
          {!ativo && (
            <>
              <CommandSeparator />
              <CommandGroup heading="Atalhos">
                <CommandItem value="minha conta perfil foto senha" onSelect={() => ir("/minha-conta")}>
                  <CircleUserRound />
                  Minha conta
                </CommandItem>
                {usuario?.administrador && usuario.estudio && !usuario.estudio.mayacorp && (
                  <CommandItem value="meu plano assinatura mensalidade" onSelect={() => ir("/minha-conta/plano")}>
                    <Gem />
                    Meu plano
                  </CommandItem>
                )}
                <CommandItem
                  value="tour guiado ajuda conhecer o sistema"
                  onSelect={() => {
                    setOpen(false);
                    iniciarTour();
                  }}
                >
                  <Compass />
                  Tour guiado
                </CommandItem>
              </CommandGroup>
              <CommandGroup heading="Preferências">
                <CommandItem
                  value="alternar tema escuro claro"
                  onSelect={() => {
                    setTheme(resolvedTheme === "dark" ? "light" : "dark");
                    setOpen(false);
                  }}
                >
                  {resolvedTheme === "dark" ? <Sun /> : <Moon />}
                  Alternar tema claro/escuro
                </CommandItem>
              </CommandGroup>
            </>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
