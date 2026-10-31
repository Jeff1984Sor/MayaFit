"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  CircleDashed,
  Copy,
  ExternalLink,
  Globe,
  Inbox,
  Loader2,
  MoreHorizontal,
  Palette,
  PanelsTopLeft,
  PowerOff,
  RotateCcw,
  Rocket,
  Save,
  Search,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/mayacorp/confirm-dialog";
import { PageHeader } from "@/components/mayacorp/page-header";
import { StatusBadge } from "@/components/mayacorp/status-badge";
import { ContatosSite } from "@/components/site/editor/contatos-site";
import { FORMULARIOS, Privacidade, Seo, type Atualizar } from "@/components/site/editor/formularios";
import { Previa } from "@/components/site/editor/previa";
import { FONTES_SITE } from "@/components/site/fontes";
import { temConteudo } from "@/components/site/pagina-site";
import { NOMES_SECAO, paginaDaPrevia } from "@/components/site/util";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { relativo } from "@/lib/format";
import type { ConteudoSite, EditorSite as EditorDados, Tema } from "@/lib/tipos-site";
import { cn } from "@/lib/utils";

const CHAVE = ["site", "editor"];

const TEMAS: { id: Tema; nome: string; desc: string; fundo: string; texto: string; fonte: string; caixa?: boolean }[] = [
  { id: "aurora", nome: "Aurora", desc: "Luminoso, serifa elegante e luzes na cor do estúdio.", fundo: "#fbfaff", texto: "#141827", fonte: "var(--font-fraunces)" },
  { id: "zen", nome: "Zen", desc: "Tons de areia, arcos e respiro. Pilates boutique.", fundo: "#f6f1ea", texto: "#2b2620", fonte: "var(--font-cormorant)" },
  { id: "energia", nome: "Energia", desc: "Escuro e forte, caixa alta. Funcional e academia.", fundo: "#0b0d14", texto: "#f4f5f8", fonte: "var(--font-archivo)", caixa: true },
];

function Painel({
  id,
  titulo,
  icone: I,
  aberto,
  onToggle,
  extra,
  children,
}: {
  id: string;
  titulo: string;
  icone?: React.ComponentType<{ className?: string }>;
  aberto: boolean;
  onToggle: () => void;
  extra?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div id={`painel-${id}`} className={cn("card-surface scroll-mt-24 overflow-hidden transition", aberto && "ring-1 ring-brand/30")}>
      <button type="button" onClick={onToggle} aria-expanded={aberto} className="flex w-full items-center gap-2 px-4 py-3 text-left">
        {I && <I className="size-4 text-muted-foreground" />}
        <span className="flex-1 text-sm font-semibold">{titulo}</span>
        {extra}
        <ChevronDown className={cn("size-4 text-muted-foreground transition", aberto && "rotate-180")} />
      </button>
      {aberto && <div className="grid gap-4 border-t px-4 py-4">{children}</div>}
    </div>
  );
}

/** Itens do "pronto para publicar" (o que mais faz diferença para converter visitantes). */
function checklist(c: ConteudoSite, d: EditorDados) {
  return [
    { ok: !!c.hero.foto, txt: "Foto de capa" },
    { ok: c.sobre.texto.trim().length > 40, txt: "Texto do “Sobre”" },
    { ok: !!c.contato.whatsapp, txt: "WhatsApp de contato" },
    { ok: !!c.localizacao.endereco, txt: "Endereço" },
    { ok: c.equipe.itens.some((i) => i.mostrar), txt: "Equipe no site" },
    { ok: d.dados.planos.length > 0 && c.secoes.some((s) => s.tipo === "planos" && s.ativa), txt: "Planos visíveis" },
    { ok: !!c.seo.descricao, txt: "Descrição para o Google" },
  ];
}

export function EditorSite({ podeEditar }: { podeEditar: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: CHAVE, queryFn: () => api.get<EditorDados>("/site") });
  // rascunho local: null = igual ao salvo no servidor
  const [rascunho, setRascunho] = useState<{ tema: Tema; conteudo: ConteudoSite } | null>(null);
  const [aberto, setAberto] = useState<string | null>("tema");
  const [aba, setAba] = useState("editar");
  const [confirmarDespublicar, setConfirmarDespublicar] = useState(false);

  const dados = q.data;
  const atual = useMemo(() => rascunho ?? (dados ? { tema: dados.tema, conteudo: dados.conteudo } : null), [rascunho, dados]);
  const sujo = rascunho !== null;
  const ro = !podeEditar;

  const set: Atualizar = useCallback(
    (fn) => {
      if (!atual || ro) return;
      const novo = structuredClone(atual.conteudo);
      fn(novo);
      setRascunho({ tema: atual.tema, conteudo: novo });
    },
    [atual, ro],
  );

  const aplicar = (d: EditorDados) => {
    qc.setQueryData(CHAVE, d);
    setRascunho(null);
  };

  const salvar = useMutation({
    mutationFn: () => api.put<EditorDados>("/site", atual),
    onSuccess: (d) => {
      aplicar(d);
      toast.success(d.publicado ? "Rascunho salvo — publique para o site mudar" : "Rascunho salvo");
    },
  });
  const publicar = useMutation({
    mutationFn: async () => {
      if (sujo) await api.put<EditorDados>("/site", atual);
      return api.post<EditorDados>("/site/publicar");
    },
    onSuccess: async (d) => {
      const primeira = !dados?.publicado;
      aplicar(d);
      toast.success(primeira ? "Seu site está no ar! 🎉" : "Alterações publicadas");
      if (primeira) {
        const confetti = (await import("canvas-confetti")).default;
        confetti({ particleCount: 140, spread: 80, origin: { y: 0.3 } });
      }
    },
  });
  const despublicar = useMutation({
    mutationFn: () => api.post<EditorDados>("/site/despublicar"),
    onSuccess: (d) => {
      aplicar(d);
      setConfirmarDespublicar(false);
      toast.success("Site fora do ar. O endereço volta a abrir o login.");
    },
  });
  const descartar = useMutation({
    mutationFn: () => api.post<EditorDados>("/site/descartar"),
    onSuccess: (d) => {
      aplicar(d);
      toast.success("Alterações descartadas: o editor voltou à versão publicada");
    },
  });

  // Ctrl+S salva; sair com alteração não salva pede confirmação
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (sujo && !salvar.isPending) salvar.mutate();
      }
    };
    const sair = (e: BeforeUnloadEvent) => {
      if (sujo) e.preventDefault();
    };
    window.addEventListener("keydown", tecla);
    window.addEventListener("beforeunload", sair);
    return () => {
      window.removeEventListener("keydown", tecla);
      window.removeEventListener("beforeunload", sair);
    };
  }, [sujo, salvar]);

  const previa = useMemo(
    () => (atual && dados ? paginaDaPrevia({ tema: atual.tema, conteudo: atual.conteudo, dados: dados.dados, identidade: dados.identidade }) : null),
    [atual, dados],
  );

  if (q.isPending)
    return (
      <div className="grid gap-4 xl:grid-cols-[420px_1fr]">
        <Skeleton className="h-[70vh] rounded-2xl" />
        <Skeleton className="h-[70vh] rounded-2xl" />
      </div>
    );
  if (!dados || !atual || !previa) return <p className="text-sm text-danger">Não foi possível carregar o site. Recarregue a página.</p>;

  const c = atual.conteudo;
  const host = dados.endereco.principal ?? (typeof window !== "undefined" ? window.location.host : "");
  const urlSite = host ? `${typeof window !== "undefined" ? window.location.protocol : "https:"}//${host}/` : "/s";
  const itens = checklist(c, dados);
  const feitos = itens.filter((i) => i.ok).length;
  const toggle = (id: string) => setAberto((a) => (a === id ? null : id));
  const abrir = (id: string) => {
    setAberto(id);
    requestAnimationFrame(() => document.getElementById(`painel-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };
  const copiar = () => navigator.clipboard.writeText(urlSite).then(() => toast.success("Endereço copiado"));
  const F = { c, set, dados: dados.dados, ro };

  return (
    <div>
      <PageHeader
        titulo="Site do estúdio"
        descricao="Seu site grátis: modalidades, planos, horários e equipe vêm do sistema e ficam sempre atualizados."
        icone={Globe}
        migalhas={[{ label: "Início", href: "/" }, { label: "Site" }]}
        acoes={
          <>
            {dados.publicado ? <StatusBadge label="No ar" tom="success" pulse /> : <StatusBadge label="Fora do ar" tom="neutral" />}
            {(sujo || dados.alteracoes_pendentes) && <StatusBadge label={sujo ? "Não salvo" : "Alterações não publicadas"} tom="warning" />}
            <Button variant="outline" render={<a href={dados.publicado ? urlSite : "/s"} target="_blank" rel="noopener noreferrer" />} disabled={!dados.publicado}>
              <ExternalLink /> Ver site
            </Button>
            {podeEditar && (
              <>
                <Button variant="outline" onClick={() => salvar.mutate()} disabled={!sujo || salvar.isPending}>
                  {salvar.isPending ? <Loader2 className="animate-spin" /> : <Save />} Salvar
                </Button>
                <Button
                  onClick={() => publicar.mutate()}
                  disabled={publicar.isPending || (dados.publicado && !sujo && !dados.alteracoes_pendentes)}
                >
                  {publicar.isPending ? <Loader2 className="animate-spin" /> : <Rocket />}
                  {dados.publicado ? "Publicar alterações" : "Publicar site"}
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label="Mais ações do site" />}>
                    <MoreHorizontal />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-60">
                    <DropdownMenuItem onClick={copiar}>
                      <Copy /> Copiar endereço do site
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => descartar.mutate()} disabled={!dados.publicado || (!dados.alteracoes_pendentes && !sujo)}>
                      <RotateCcw /> Descartar alterações
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => setConfirmarDespublicar(true)} disabled={!dados.publicado} className="text-danger">
                      <PowerOff /> Tirar o site do ar
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </>
            )}
          </>
        }
      />

      <div className="card-surface mb-4 flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand/12 text-info-ink">
          <Globe className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">Endereço do seu site{dados.publicado && dados.publicado_em ? ` · publicado ${relativo(dados.publicado_em)}` : ""}</p>
          <p className="truncate font-mono text-sm font-medium">{urlSite.replace(/\/$/, "")}</p>
          {dados.endereco.dominios.length > 0 && <p className="truncate text-xs text-muted-foreground">Também em: {dados.endereco.dominios.join(", ")}</p>}
        </div>
        <p className="text-xs text-muted-foreground sm:max-w-64">
          Quer um domínio próprio (www.seuestudio.com.br)? A MayaCorp configura para você — fale com o suporte.
        </p>
        <Button variant="outline" size="sm" onClick={copiar}>
          <Copy /> Copiar
        </Button>
      </div>

      <Tabs value={aba} onValueChange={(v) => setAba(String(v))}>
        <TabsList>
          <TabsTrigger value="editar">
            <PanelsTopLeft /> Editar e pré-visualizar
          </TabsTrigger>
          <TabsTrigger value="contatos">
            <Inbox /> Contatos recebidos
            {dados.contatos_nao_lidos > 0 && (
              <span className="ml-1 rounded-full bg-brand px-1.5 text-[10px] font-semibold text-brand-foreground tabular-nums">{dados.contatos_nao_lidos}</span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="editar" className="mt-3">
          <div className="grid gap-4 xl:grid-cols-[420px_1fr]">
            <div className="grid content-start gap-3">
              {/* pronto para publicar */}
              <div className="card-surface p-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-semibold">Pronto para publicar</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {feitos}/{itens.length}
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full brand-gradient transition-all duration-500" style={{ width: `${(feitos / itens.length) * 100}%` }} />
                </div>
                <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                  {itens.map((i) => (
                    <li key={i.txt} className={cn("flex items-center gap-1.5", i.ok ? "text-foreground" : "text-muted-foreground")}>
                      {i.ok ? <Check className="size-3.5 text-success" /> : <CircleDashed className="size-3.5" />}
                      {i.txt}
                    </li>
                  ))}
                </ul>
              </div>

              <Painel id="tema" titulo="Modelo visual" icone={Palette} aberto={aberto === "tema"} onToggle={() => toggle("tema")}>
                <div className={cn("grid gap-2", FONTES_SITE)}>
                  {TEMAS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      disabled={ro}
                      onClick={() => setRascunho({ tema: t.id, conteudo: c })}
                      className={cn(
                        "flex items-center gap-3 rounded-xl border p-2 text-left transition hover:border-brand/50",
                        atual.tema === t.id && "border-brand ring-2 ring-brand/30",
                      )}
                    >
                      <span className="relative grid h-14 w-20 shrink-0 place-items-center overflow-hidden rounded-lg border" style={{ background: t.fundo, color: t.texto }}>
                        <span className="text-xl font-semibold" style={{ fontFamily: t.fonte, textTransform: t.caixa ? "uppercase" : undefined }}>
                          Aa
                        </span>
                        <span className="absolute right-1.5 bottom-1.5 h-1.5 w-6 rounded-full" style={{ background: dados.identidade.cor }} />
                      </span>
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5 text-sm font-semibold">
                          {t.nome} {atual.tema === t.id && <Check className="size-3.5 text-brand" />}
                        </span>
                        <span className="block text-xs text-muted-foreground">{t.desc}</span>
                      </span>
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  Cor e logo vêm de Configurações › Identidade (<span className="font-mono">{dados.identidade.cor}</span>).
                </p>
              </Painel>

              <Painel id="secoes" titulo="Seções e ordem" icone={PanelsTopLeft} aberto={aberto === "secoes"} onToggle={() => toggle("secoes")}>
                <ul className="grid gap-1.5">
                  {c.secoes.map((s, i) => {
                    const vazia = s.ativa && s.tipo !== "hero" && !temConteudo(s.tipo, previa);
                    return (
                      <li key={s.tipo} className={cn("flex items-center gap-2 rounded-lg border px-2 py-1.5", !s.ativa && "opacity-60")}>
                        <span className="w-4 text-center font-mono text-[11px] text-muted-foreground">{i + 1}</span>
                        <button type="button" className="min-w-0 flex-1 truncate text-left text-sm hover:underline" onClick={() => abrir(s.tipo)}>
                          {NOMES_SECAO[s.tipo]}
                        </button>
                        {vazia && <span className="rounded bg-warning/15 px-1.5 text-[10px] font-medium text-warning-ink">vazia</span>}
                        <Button variant="ghost" size="icon-xs" disabled={ro || i === 0} aria-label="Subir" onClick={() => set((x) => void x.secoes.splice(i - 1, 0, ...x.secoes.splice(i, 1)))}>
                          <ArrowUp />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          disabled={ro || i === c.secoes.length - 1}
                          aria-label="Descer"
                          onClick={() => set((x) => void x.secoes.splice(i + 1, 0, ...x.secoes.splice(i, 1)))}
                        >
                          <ArrowDown />
                        </Button>
                        <Switch size="sm" checked={s.ativa} disabled={ro} aria-label={`Mostrar ${NOMES_SECAO[s.tipo]}`} onCheckedChange={(v) => set((x) => void (x.secoes[i].ativa = v))} />
                      </li>
                    );
                  })}
                </ul>
              </Painel>

              <fieldset disabled={ro} className="grid gap-3">
                {c.secoes.map((s) => {
                  const Form = FORMULARIOS[s.tipo];
                  return (
                    <Painel
                      key={s.tipo}
                      id={s.tipo}
                      titulo={NOMES_SECAO[s.tipo]}
                      aberto={aberto === s.tipo}
                      onToggle={() => toggle(s.tipo)}
                      extra={!s.ativa && <span className="text-[11px] text-muted-foreground">desligada</span>}
                    >
                      <Form {...F} />
                    </Painel>
                  );
                })}
                <Painel id="seo" titulo="Google e redes sociais (SEO)" icone={Search} aberto={aberto === "seo"} onToggle={() => toggle("seo")}>
                  <Seo {...F} host={host} />
                </Painel>
                <Painel id="privacidade" titulo="Privacidade (LGPD)" icone={ShieldCheck} aberto={aberto === "privacidade"} onToggle={() => toggle("privacidade")}>
                  <Privacidade {...F} />
                </Painel>
              </fieldset>
            </div>

            <div className="xl:sticky xl:top-[calc(var(--tb,64px)+var(--faixa,0px)+16px)] xl:h-[calc(100dvh-var(--tb,64px)-var(--faixa,0px)-32px)] h-[75vh]">
              <Previa pagina={previa} endereco={urlSite} />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="contatos" className="mt-3">
          <ContatosSite publicado={dados.publicado} podeEditar={podeEditar} onPublicar={() => publicar.mutate()} />
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={confirmarDespublicar}
        onOpenChange={setConfirmarDespublicar}
        titulo="Tirar o site do ar?"
        descricao="Quem abrir o endereço do estúdio verá a tela de login. O conteúdo fica guardado e você pode publicar de novo quando quiser."
        confirmar="Tirar do ar"
        destrutivo
        carregando={despublicar.isPending}
        onConfirm={() => despublicar.mutate()}
      />
    </div>
  );
}
