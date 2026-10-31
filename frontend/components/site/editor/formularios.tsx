"use client";

import { ArrowDown, ArrowUp, ExternalLink, Info, Plus, Star, Trash2 } from "lucide-react";
import Link from "next/link";

import { Field } from "@/components/mayacorp/form";
import { CampoFoto } from "@/components/site/editor/campo-foto";
import { preco } from "@/components/site/util";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { ConteudoSite, DadosEstudio, ItemEquipe, ItemModalidade, TipoSecao } from "@/lib/tipos-site";
import { cn } from "@/lib/utils";

export type Atualizar = (fn: (c: ConteudoSite) => void) => void;
type F = { c: ConteudoSite; set: Atualizar; dados: DadosEstudio; ro: boolean };

function Contador({ v, max }: { v: string; max: number }) {
  return <span className={cn("tabular-nums", v.length > max * 0.9 && "text-warning-ink")}>{v.length}/{max}</span>;
}

function Dica({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex gap-2 rounded-lg bg-brand/8 px-3 py-2 text-xs text-foreground/80">
      <Info className="mt-0.5 size-3.5 shrink-0 text-info-ink" />
      <span>{children}</span>
    </p>
  );
}

function Vazio({ texto, href, acao }: { texto: string; href: string; acao: string }) {
  return (
    <div className="rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
      <p>{texto}</p>
      <Button variant="outline" size="sm" className="mt-3" render={<Link href={href} />}>
        <Plus /> {acao}
      </Button>
    </div>
  );
}

function Linha({ titulo, children, acoes }: { titulo: React.ReactNode; children?: React.ReactNode; acoes?: React.ReactNode }) {
  return (
    <div className="rounded-xl border bg-card p-3">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1 truncate text-sm font-medium">{titulo}</div>
        {acoes}
      </div>
      {children && <div className="mt-3 grid gap-3">{children}</div>}
    </div>
  );
}

function Mover({ i, total, mover, ro }: { i: number; total: number; mover: (de: number, para: number) => void; ro: boolean }) {
  return (
    <>
      <Button variant="ghost" size="icon-xs" disabled={ro || i === 0} onClick={() => mover(i, i - 1)} aria-label="Subir">
        <ArrowUp />
      </Button>
      <Button variant="ghost" size="icon-xs" disabled={ro || i === total - 1} onClick={() => mover(i, i + 1)} aria-label="Descer">
        <ArrowDown />
      </Button>
    </>
  );
}

function mover<T>(lista: T[], de: number, para: number) {
  const [x] = lista.splice(de, 1);
  lista.splice(para, 0, x);
}

function TituloSecao({ v, onChange, max = 120 }: { v: string; onChange: (v: string) => void; max?: number }) {
  return (
    <Field label="Título da seção">
      <Input value={v} maxLength={max} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

// ------------------------------------------------------------------------------------------------------- hero
function Hero({ c, set }: F) {
  return (
    <>
      <Field label="Título principal" dica={<Contador v={c.hero.titulo} max={120} />}>
        <Input value={c.hero.titulo} maxLength={120} onChange={(e) => set((x) => void (x.hero.titulo = e.target.value))} />
      </Field>
      <Field label="Subtítulo" dica={<Contador v={c.hero.subtitulo} max={300} />}>
        <Textarea rows={3} value={c.hero.subtitulo} maxLength={300} onChange={(e) => set((x) => void (x.hero.subtitulo = e.target.value))} />
      </Field>
      <Field label="Texto do botão">
        <Input value={c.hero.botao_texto} maxLength={40} onChange={(e) => set((x) => void (x.hero.botao_texto = e.target.value))} />
      </Field>
      <Field label="Foto de capa" dica="Horizontal ou vertical, bem iluminada. Reduzimos o tamanho automaticamente.">
        <CampoFoto valor={c.hero.foto} onChange={(f) => set((x) => void (x.hero.foto = f))} proporcao="aspect-[16/10]" />
      </Field>
    </>
  );
}

function Sobre({ c, set }: F) {
  return (
    <>
      <TituloSecao v={c.sobre.titulo} onChange={(v) => set((x) => void (x.sobre.titulo = v))} />
      <Field label="Texto" dica="Deixe uma linha em branco para começar outro parágrafo.">
        <Textarea rows={7} value={c.sobre.texto} maxLength={3000} onChange={(e) => set((x) => void (x.sobre.texto = e.target.value))} />
      </Field>
      <Field label="Destaques (até 6)" dica="Aparecem com um ✓ — os 3 primeiros também na capa.">
        <div className="grid gap-2">
          {c.sobre.destaques.map((d, i) => (
            <div key={i} className="flex gap-2">
              <Input value={d} maxLength={60} onChange={(e) => set((x) => void (x.sobre.destaques[i] = e.target.value))} />
              <Button variant="ghost" size="icon" aria-label="Remover destaque" onClick={() => set((x) => void x.sobre.destaques.splice(i, 1))}>
                <Trash2 />
              </Button>
            </div>
          ))}
          {c.sobre.destaques.length < 6 && (
            <Button variant="outline" size="sm" className="justify-self-start" onClick={() => set((x) => void x.sobre.destaques.push(""))}>
              <Plus /> Destaque
            </Button>
          )}
        </div>
      </Field>
      <Field label="Foto">
        <CampoFoto valor={c.sobre.foto} onChange={(f) => set((x) => void (x.sobre.foto = f))} proporcao="aspect-[5/4]" />
      </Field>
    </>
  );
}

/** Item da modalidade no conteúdo (cria na hora se o serviço é novo no cadastro). */
function itemModalidade(x: ConteudoSite, id: number): ItemModalidade {
  let it = x.modalidades.itens.find((i) => i.tipo_servico_id === id);
  if (!it) {
    it = { tipo_servico_id: id, mostrar: true, descricao: "", foto: null };
    x.modalidades.itens.push(it);
  }
  return it;
}

function Modalidades({ c, set, dados, ro }: F) {
  return (
    <>
      <TituloSecao v={c.modalidades.titulo} onChange={(v) => set((x) => void (x.modalidades.titulo = v))} />
      <Field label="Subtítulo">
        <Input value={c.modalidades.subtitulo} maxLength={300} onChange={(e) => set((x) => void (x.modalidades.subtitulo = e.target.value))} />
      </Field>
      <Dica>As modalidades vêm dos tipos de serviço cadastrados. Serviço novo aparece sozinho no site.</Dica>
      {dados.modalidades.length === 0 && <Vazio texto="Nenhum tipo de serviço ativo." href="/cadastros/servicos" acao="Cadastrar serviços" />}
      {dados.modalidades.map((m) => {
        const it = c.modalidades.itens.find((i) => i.tipo_servico_id === m.id);
        const mostrar = it?.mostrar ?? true;
        return (
          <Linha
            key={m.id}
            titulo={m.nome}
            acoes={<Switch checked={mostrar} disabled={ro} aria-label={`Mostrar ${m.nome}`} onCheckedChange={(v) => set((x) => void (itemModalidade(x, m.id).mostrar = v))} />}
          >
            {mostrar && (
              <div className="grid grid-cols-[96px_1fr] gap-3">
                <CampoFoto valor={it?.foto ?? null} onChange={(f) => set((x) => void (itemModalidade(x, m.id).foto = f))} proporcao="aspect-square" rotulo="Foto" />
                <Textarea
                  rows={3}
                  placeholder="Descrição curta da aula"
                  value={it?.descricao ?? ""}
                  maxLength={400}
                  onChange={(e) => set((x) => void (itemModalidade(x, m.id).descricao = e.target.value))}
                />
              </div>
            )}
          </Linha>
        );
      })}
    </>
  );
}

function Planos({ c, set, dados, ro }: F) {
  const ocultos = new Set(c.planos.ocultos);
  return (
    <>
      <TituloSecao v={c.planos.titulo} onChange={(v) => set((x) => void (x.planos.titulo = v))} />
      <Field label="Subtítulo">
        <Input value={c.planos.subtitulo} maxLength={300} onChange={(e) => set((x) => void (x.planos.subtitulo = e.target.value))} />
      </Field>
      <label className="flex items-center justify-between gap-3 rounded-xl border p-3 text-sm">
        <span>
          <span className="font-medium">Mostrar preços</span>
          <span className="block text-xs text-muted-foreground">Desligado, aparece “Consulte valores”.</span>
        </span>
        <Switch checked={c.planos.mostrar_precos} disabled={ro} onCheckedChange={(v) => set((x) => void (x.planos.mostrar_precos = v))} />
      </label>
      {dados.planos.length === 0 && <Vazio texto="Nenhum plano ativo cadastrado." href="/cadastros/planos" acao="Cadastrar planos" />}
      {dados.planos.map((p) => (
        <Linha
          key={p.id}
          titulo={
            <span className="flex items-center gap-2">
              {p.nome}
              <span className="font-mono text-xs text-muted-foreground">{preco(p.valor)}</span>
            </span>
          }
          acoes={
            <>
              <Button
                variant="ghost"
                size="icon-xs"
                disabled={ro}
                aria-label="Destacar como mais escolhido"
                title="Destacar como “Mais escolhido”"
                onClick={() => set((x) => void (x.planos.destaque_id = x.planos.destaque_id === p.id ? null : p.id))}
              >
                <Star className={cn(c.planos.destaque_id === p.id && "fill-amber-maya text-amber-maya")} />
              </Button>
              <Switch
                checked={!ocultos.has(p.id)}
                disabled={ro}
                aria-label={`Mostrar ${p.nome}`}
                onCheckedChange={(v) =>
                  set((x) => {
                    x.planos.ocultos = v ? x.planos.ocultos.filter((i) => i !== p.id) : [...x.planos.ocultos, p.id];
                  })
                }
              />
            </>
          }
        />
      ))}
      <Field label="Observação abaixo dos planos">
        <Input
          value={c.planos.observacao}
          maxLength={300}
          placeholder="Ex.: matrícula isenta para quem agenda pelo site"
          onChange={(e) => set((x) => void (x.planos.observacao = e.target.value))}
        />
      </Field>
    </>
  );
}

function Grade({ c, set, dados, ro }: F) {
  return (
    <>
      <TituloSecao v={c.grade.titulo} onChange={(v) => set((x) => void (x.grade.titulo = v))} />
      <Field label="Subtítulo">
        <Input value={c.grade.subtitulo} maxLength={300} onChange={(e) => set((x) => void (x.grade.subtitulo = e.target.value))} />
      </Field>
      <label className="flex items-center justify-between gap-3 rounded-xl border p-3 text-sm">
        <span>
          <span className="font-medium">Mostrar o professor</span>
          <span className="block text-xs text-muted-foreground">Só o primeiro nome, e só de quem aparece na Equipe.</span>
        </span>
        <Switch checked={c.grade.mostrar_professor} disabled={ro} onCheckedChange={(v) => set((x) => void (x.grade.mostrar_professor = v))} />
      </label>
      <Dica>
        A grade é só leitura e vem da grade fixa de horários (ou das aulas dos próximos 14 dias). Nenhum dado de aluno aparece.
        Hoje: <strong>{dados.grade.length}</strong> horário(s).
      </Dica>
      {dados.grade.length === 0 && <Vazio texto="Nenhum horário na grade." href="/cadastros/horarios" acao="Cadastrar horários" />}
    </>
  );
}

function itemEquipe(x: ConteudoSite, id: number): ItemEquipe {
  let it = x.equipe.itens.find((i) => i.profissional_id === id);
  if (!it) {
    it = { profissional_id: id, mostrar: false, cargo: "", bio: "", foto: null };
    x.equipe.itens.push(it);
  }
  return it;
}

function Equipe({ c, set, dados, ro }: F) {
  return (
    <>
      <TituloSecao v={c.equipe.titulo} onChange={(v) => set((x) => void (x.equipe.titulo = v))} />
      <Field label="Subtítulo">
        <Input value={c.equipe.subtitulo} maxLength={300} onChange={(e) => set((x) => void (x.equipe.subtitulo = e.target.value))} />
      </Field>
      <Dica>Só aparece quem você ligar aqui. Contatos dos profissionais nunca vão para o site.</Dica>
      {dados.profissionais.length === 0 && <Vazio texto="Nenhum profissional ativo." href="/cadastros/profissionais" acao="Cadastrar profissionais" />}
      {dados.profissionais.map((p) => {
        const it = c.equipe.itens.find((i) => i.profissional_id === p.id);
        return (
          <Linha
            key={p.id}
            titulo={p.nome}
            acoes={<Switch checked={!!it?.mostrar} disabled={ro} aria-label={`Mostrar ${p.nome}`} onCheckedChange={(v) => set((x) => void (itemEquipe(x, p.id).mostrar = v))} />}
          >
            {it?.mostrar && (
              <div className="grid grid-cols-[96px_1fr] gap-3">
                <CampoFoto valor={it.foto} onChange={(f) => set((x) => void (itemEquipe(x, p.id).foto = f))} proporcao="aspect-[4/5]" rotulo="Foto" />
                <div className="grid gap-2">
                  <Input placeholder="Cargo / formação" value={it.cargo} maxLength={80} onChange={(e) => set((x) => void (itemEquipe(x, p.id).cargo = e.target.value))} />
                  <Textarea rows={3} placeholder="Mini bio" value={it.bio} maxLength={600} onChange={(e) => set((x) => void (itemEquipe(x, p.id).bio = e.target.value))} />
                </div>
              </div>
            )}
          </Linha>
        );
      })}
    </>
  );
}

function Depoimentos({ c, set, ro }: F) {
  const itens = c.depoimentos.itens;
  return (
    <>
      <TituloSecao v={c.depoimentos.titulo} onChange={(v) => set((x) => void (x.depoimentos.titulo = v))} />
      <Dica>Publique só com autorização da pessoa. Prefira o primeiro nome e a inicial (ex.: “Marina S.”).</Dica>
      {itens.map((d, i) => (
        <Linha
          key={i}
          titulo={d.nome || `Depoimento ${i + 1}`}
          acoes={
            <>
              <Mover i={i} total={itens.length} ro={ro} mover={(de, para) => set((x) => mover(x.depoimentos.itens, de, para))} />
              <Button variant="ghost" size="icon-xs" disabled={ro} aria-label="Remover" onClick={() => set((x) => void x.depoimentos.itens.splice(i, 1))}>
                <Trash2 />
              </Button>
            </>
          }
        >
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder="Nome" value={d.nome} maxLength={80} onChange={(e) => set((x) => void (x.depoimentos.itens[i].nome = e.target.value))} />
            <Input placeholder="Ex.: aluna há 2 anos" value={d.detalhe} maxLength={80} onChange={(e) => set((x) => void (x.depoimentos.itens[i].detalhe = e.target.value))} />
          </div>
          <Textarea rows={3} placeholder="Depoimento" value={d.texto} maxLength={600} onChange={(e) => set((x) => void (x.depoimentos.itens[i].texto = e.target.value))} />
        </Linha>
      ))}
      {itens.length < 12 && (
        <Button variant="outline" size="sm" className="justify-self-start" disabled={ro} onClick={() => set((x) => void x.depoimentos.itens.push({ nome: "", texto: "", detalhe: "" }))}>
          <Plus /> Depoimento
        </Button>
      )}
    </>
  );
}

function Galeria({ c, set, ro }: F) {
  const fotos = c.galeria.fotos;
  return (
    <>
      <TituloSecao v={c.galeria.titulo} onChange={(v) => set((x) => void (x.galeria.titulo = v))} />
      <div className="grid grid-cols-2 gap-3">
        {fotos.map((f, i) => (
          <div key={i} className="grid gap-1.5">
            <CampoFoto valor={f.foto} onChange={(n) => set((x) => (n ? void (x.galeria.fotos[i].foto = n) : void x.galeria.fotos.splice(i, 1)))} />
            <Input className="h-7 text-xs" placeholder="Legenda" value={f.legenda} maxLength={120} onChange={(e) => set((x) => void (x.galeria.fotos[i].legenda = e.target.value))} />
          </div>
        ))}
        {fotos.length < 24 && !ro && (
          <CampoFoto valor={null} rotulo="Adicionar foto" onChange={(n) => n && set((x) => void x.galeria.fotos.push({ foto: n, legenda: "" }))} />
        )}
      </div>
    </>
  );
}

function Faq({ c, set, ro }: F) {
  const itens = c.faq.itens;
  return (
    <>
      <TituloSecao v={c.faq.titulo} onChange={(v) => set((x) => void (x.faq.titulo = v))} />
      {itens.map((q, i) => (
        <Linha
          key={i}
          titulo={q.pergunta || `Pergunta ${i + 1}`}
          acoes={
            <>
              <Mover i={i} total={itens.length} ro={ro} mover={(de, para) => set((x) => mover(x.faq.itens, de, para))} />
              <Button variant="ghost" size="icon-xs" disabled={ro} aria-label="Remover" onClick={() => set((x) => void x.faq.itens.splice(i, 1))}>
                <Trash2 />
              </Button>
            </>
          }
        >
          <Input placeholder="Pergunta" value={q.pergunta} maxLength={200} onChange={(e) => set((x) => void (x.faq.itens[i].pergunta = e.target.value))} />
          <Textarea rows={3} placeholder="Resposta" value={q.resposta} maxLength={1200} onChange={(e) => set((x) => void (x.faq.itens[i].resposta = e.target.value))} />
        </Linha>
      ))}
      {itens.length < 20 && (
        <Button variant="outline" size="sm" className="justify-self-start" disabled={ro} onClick={() => set((x) => void x.faq.itens.push({ pergunta: "", resposta: "" }))}>
          <Plus /> Pergunta
        </Button>
      )}
    </>
  );
}

function Localizacao({ c, set }: F) {
  return (
    <>
      <TituloSecao v={c.localizacao.titulo} onChange={(v) => set((x) => void (x.localizacao.titulo = v))} />
      <Field label="Endereço">
        <Input value={c.localizacao.endereco} maxLength={300} placeholder="Rua, número - bairro, cidade - UF" onChange={(e) => set((x) => void (x.localizacao.endereco = e.target.value))} />
      </Field>
      <Field label="Horário de funcionamento">
        <Textarea rows={2} value={c.localizacao.horario_texto} maxLength={300} placeholder="Seg a sex, 6h às 21h · Sáb, 8h às 12h" onChange={(e) => set((x) => void (x.localizacao.horario_texto = e.target.value))} />
      </Field>
      <Field
        label="Mapa do Google (opcional)"
        dica="Cole o link do Google Maps ou o código de “Compartilhar › Incorporar um mapa”. Em branco, o mapa sai pelo endereço."
      >
        <Textarea rows={2} value={c.localizacao.mapa} maxLength={2000} onChange={(e) => set((x) => void (x.localizacao.mapa = e.target.value))} />
      </Field>
    </>
  );
}

function Contato({ c, set }: F) {
  const campo = (k: keyof ConteudoSite["contato"], label: string, ph?: string, dica?: string) => (
    <Field label={label} dica={dica}>
      <Input value={c.contato[k]} placeholder={ph} maxLength={k === "mensagem_whatsapp" ? 200 : 200} onChange={(e) => set((x) => void (x.contato[k] = e.target.value))} />
    </Field>
  );
  return (
    <>
      <TituloSecao v={c.contato.titulo} onChange={(v) => set((x) => void (x.contato.titulo = v))} />
      {campo("subtitulo", "Subtítulo")}
      <div className="grid grid-cols-2 gap-3">
        {campo("whatsapp", "WhatsApp", "(11) 99999-0000")}
        {campo("telefone", "Telefone", "(11) 3333-4444")}
      </div>
      {campo("mensagem_whatsapp", "Mensagem pronta do WhatsApp", undefined, "Já vem escrita quando o visitante toca no botão.")}
      {campo("email", "E-mail", "contato@seuestudio.com.br")}
      <div className="grid grid-cols-2 gap-3">
        {campo("instagram", "Instagram", "@seuestudio")}
        {campo("facebook", "Facebook", "seuestudio")}
        {campo("tiktok", "TikTok", "@seuestudio")}
        {campo("youtube", "YouTube", "@seuestudio")}
      </div>
      <Dica>O formulário “Agende sua aula experimental” vai para o CRM (funil de vendas) e fica no histórico em “Contatos recebidos”.</Dica>
    </>
  );
}

export function Seo({ c, set, host }: F & { host: string }) {
  const titulo = c.seo.titulo || "Nome do estúdio";
  const desc = c.seo.descricao || c.hero.subtitulo;
  return (
    <>
      <Field label="Título no Google" dica={<Contador v={c.seo.titulo} max={70} />}>
        <Input value={c.seo.titulo} maxLength={70} onChange={(e) => set((x) => void (x.seo.titulo = e.target.value))} />
      </Field>
      <Field label="Descrição no Google" dica={<Contador v={c.seo.descricao} max={170} />}>
        <Textarea rows={3} value={c.seo.descricao} maxLength={170} onChange={(e) => set((x) => void (x.seo.descricao = e.target.value))} />
      </Field>
      <div className="grid grid-cols-[1fr_72px] gap-3">
        <Field label="Cidade">
          <Input value={c.seo.cidade} maxLength={80} onChange={(e) => set((x) => void (x.seo.cidade = e.target.value))} />
        </Field>
        <Field label="UF">
          <Input value={c.seo.estado} maxLength={2} onChange={(e) => set((x) => void (x.seo.estado = e.target.value.toUpperCase()))} />
        </Field>
      </div>
      <Field label="Tipo de negócio">
        <select
          className="h-8 rounded-lg border bg-background px-2 text-sm"
          value={c.seo.categoria}
          onChange={(e) => set((x) => void (x.seo.categoria = e.target.value as ConteudoSite["seo"]["categoria"]))}
        >
          <option value="pilates">Estúdio de Pilates</option>
          <option value="estudio">Estúdio (outras atividades)</option>
          <option value="funcional">Funcional / cross</option>
          <option value="academia">Academia</option>
        </select>
      </Field>
      <div>
        <p className="mb-1.5 text-[13px] text-foreground/80">Como aparece no Google</p>
        <div className="rounded-xl border bg-white p-4 font-[arial,sans-serif] text-left shadow-sm">
          <p className="truncate text-xs text-[#202124]">{host}</p>
          <p className="mt-0.5 truncate text-lg leading-snug text-[#1a0dab]">{titulo}</p>
          <p className="mt-0.5 line-clamp-2 text-sm text-[#4d5156]">{desc}</p>
        </div>
      </div>
    </>
  );
}

export function Privacidade({ c, set }: F) {
  return (
    <>
      <Dica>A política de privacidade é gerada automaticamente (LGPD) e fica no rodapé e no formulário de contato.</Dica>
      <Field label="Responsável pelos dados (razão social)">
        <Input value={c.privacidade.responsavel} maxLength={150} onChange={(e) => set((x) => void (x.privacidade.responsavel = e.target.value))} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="CNPJ/CPF (opcional)">
          <Input value={c.privacidade.documento} maxLength={20} onChange={(e) => set((x) => void (x.privacidade.documento = e.target.value))} />
        </Field>
        <Field label="E-mail para privacidade">
          <Input value={c.privacidade.email} maxLength={200} onChange={(e) => set((x) => void (x.privacidade.email = e.target.value))} />
        </Field>
      </div>
      <Button variant="outline" size="sm" className="justify-self-start" render={<a href="/s/privacidade" target="_blank" rel="noopener noreferrer" />}>
        <ExternalLink /> Ver política publicada
      </Button>
    </>
  );
}

export const FORMULARIOS: Record<TipoSecao, (p: F) => React.ReactNode> = {
  hero: Hero,
  sobre: Sobre,
  modalidades: Modalidades,
  planos: Planos,
  grade: Grade,
  equipe: Equipe,
  depoimentos: Depoimentos,
  galeria: Galeria,
  faq: Faq,
  localizacao: Localizacao,
  contato: Contato,
};
