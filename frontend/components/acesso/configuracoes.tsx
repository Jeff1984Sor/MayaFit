"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Field, FormSection, SwitchRow } from "@/components/mayacorp/form";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ConfigAcesso, OpcoesAcesso } from "@/lib/tipos-acesso";

function hhmm(min: number) {
  const m = ((min % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

/** Linha do tempo ao vivo: mostra, para uma aula das 09:00, de quando até quando a entrada libera. */
function JanelaVisual({ antes, depois }: { antes: number; depois: number }) {
  const AULA = 9 * 60;
  const DURACAO = 50;
  const ini = AULA - 120;
  const fim = AULA + 120;
  const pct = (m: number) => `${(100 * (Math.min(fim, Math.max(ini, m)) - ini)) / (fim - ini)}%`;
  return (
    <div className="sm:col-span-2 rounded-xl border bg-background/60 p-4">
      <p className="mb-6 text-xs text-muted-foreground">Exemplo: aula das 09:00 (50 min). A faixa verde é quando o totem libera a entrada.</p>
      <div className="relative h-10">
        <div className="absolute inset-x-0 top-4 h-2 rounded-full bg-muted" />
        <div className="absolute top-4 h-2 rounded-full bg-brand/30" style={{ left: pct(AULA), width: `calc(${pct(AULA + DURACAO)} - ${pct(AULA)})` }} />
        <div className="absolute top-2.5 h-5 rounded-full bg-success/80 shadow-[0_0_12px] shadow-success/40 transition-all duration-500" style={{ left: pct(AULA - antes), width: `calc(${pct(AULA + depois)} - ${pct(AULA - antes)})` }} />
        <div className="absolute -top-4 -translate-x-1/2 text-[11px] font-medium" style={{ left: pct(AULA) }}>
          aula 09:00
        </div>
        <div className="absolute top-8 -translate-x-1/2 text-[11px] text-success-ink num" style={{ left: pct(AULA - antes) }}>
          {hhmm(AULA - antes)}
        </div>
        <div className="absolute top-8 -translate-x-1/2 text-[11px] text-success-ink num" style={{ left: pct(AULA + depois) }}>
          {hhmm(AULA + depois)}
        </div>
      </div>
    </div>
  );
}

export function ConfiguracoesAcesso() {
  const { pode } = useAuth();
  const qc = useQueryClient();
  const editar = pode("acesso.configurar");
  const cfg = useQuery({ queryKey: ["acesso", "config"], queryFn: () => api.get<ConfigAcesso>("/acesso/config") });
  const opcoes = useQuery({ queryKey: ["acesso", "opcoes"], queryFn: () => api.get<OpcoesAcesso>("/acesso/opcoes") });
  const [edicao, setF] = useState<ConfigAcesso | null>(null);
  const f = edicao ?? cfg.data ?? null;
  const salvar = useMutation({
    mutationFn: (c: ConfigAcesso) => api.put<ConfigAcesso>("/acesso/config", c),
    onSuccess: (c) => {
      setF(c);
      qc.invalidateQueries({ queryKey: ["acesso"] });
      toast.success("Regras de acesso salvas.");
    },
  });
  if (!f) return <Skeleton className="h-96 rounded-2xl" />;
  const set = (p: Partial<ConfigAcesso>) => setF({ ...f, ...p });
  const num = (v: string, min: number, max: number) => Math.min(max, Math.max(min, Number(v) || 0));

  return (
    <form
      className="card-surface divide-y p-5"
      onSubmit={(e) => {
        e.preventDefault();
        salvar.mutate(f);
      }}
    >
      <fieldset disabled={!editar} className="contents">
        <FormSection titulo="Janela da aula" descricao="Quanto antes e depois do início da aula o aluno consegue entrar.">
          <Field label="Minutos antes do início">
            <Input type="number" min={0} max={240} value={f.janela_antes_min} onChange={(e) => set({ janela_antes_min: num(e.target.value, 0, 240) })} />
          </Field>
          <Field label="Minutos depois do início">
            <Input type="number" min={0} max={240} value={f.janela_depois_min} onChange={(e) => set({ janela_depois_min: num(e.target.value, 0, 240) })} />
          </Field>
          <JanelaVisual antes={f.janela_antes_min} depois={f.janela_depois_min} />
        </FormSection>

        <FormSection titulo="Mensalidade" descricao="Parcela vencida e não paga bloqueia a entrada depois da tolerância. Dentro dela, o totem só dá um aviso gentil.">
          <Field label="Tolerância de atraso (dias)" dica={f.tolerancia_atraso_dias === 0 ? "Sem tolerância: bloqueia no dia seguinte ao vencimento." : `Bloqueia a partir do ${f.tolerancia_atraso_dias + 1}º dia de atraso.`}>
            <Input type="number" min={0} max={90} value={f.tolerancia_atraso_dias} onChange={(e) => set({ tolerancia_atraso_dias: num(e.target.value, 0, 90) })} />
          </Field>
        </FormSection>

        <FormSection titulo="Planos de acesso livre" descricao="Academia/musculação: quem tem contrato vigente nestes planos entra a qualquer hora do horário de funcionamento, sem aula marcada.">
          <div className="sm:col-span-2 grid gap-2 sm:grid-cols-2">
            {opcoes.data?.planos.length ? (
              opcoes.data.planos.map((p) => (
                <label key={p.id} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                  <Checkbox
                    checked={f.planos_livres.includes(p.id)}
                    onCheckedChange={(v) => set({ planos_livres: v ? [...f.planos_livres, p.id] : f.planos_livres.filter((x) => x !== p.id) })}
                  />
                  {p.nome}
                </label>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Nenhum plano ativo cadastrado.</p>
            )}
          </div>
          <Field label="Permanência estimada (min)" dica="Por quanto tempo quem entra sem aula aparece em “Quem está no estúdio”.">
            <Input type="number" min={15} max={600} value={f.permanencia_livre_min} onChange={(e) => set({ permanencia_livre_min: num(e.target.value, 15, 600) })} />
          </Field>
        </FormSection>

        <FormSection titulo="Reconhecimento facial" descricao="Quanto mais alto o limiar, mais rigoroso (menos chance de liberar a pessoa errada, mais chance de pedir para tentar de novo).">
          <Field label={`Semelhança mínima: ${Math.round(f.limiar_similaridade * 100)}%`} dica="Recomendado entre 55% e 70%. Calibre com o equipamento real.">
            <input type="range" min={40} max={95} step={1} value={Math.round(f.limiar_similaridade * 100)} onChange={(e) => set({ limiar_similaridade: Number(e.target.value) / 100 })} className="w-full accent-[var(--brand)]" />
          </Field>
          <Field label={`Margem para gêmeos/parecidos: ${Math.round(f.margem_ambiguidade * 100)} pontos`} dica="Se dois alunos ficarem perto demais, o totem pede CPF ou QR.">
            <input type="range" min={0} max={20} step={1} value={Math.round(f.margem_ambiguidade * 100)} onChange={(e) => set({ margem_ambiguidade: Number(e.target.value) / 100 })} className="w-full accent-[var(--brand)]" />
          </Field>
          <div className="sm:col-span-2 grid gap-2">
            <SwitchRow titulo="Exigir prova de vida" descricao="Pede para piscar (ou usa os modelos antifraude). Evita liberar com foto ou tela na frente da câmera.">
              <Switch checked={f.exigir_prova_vida} onCheckedChange={(v) => set({ exigir_prova_vida: v })} />
            </SwitchRow>
            <SwitchRow titulo="Exigir PIN na entrada por CPF/código" descricao="Recomendado: sem PIN, qualquer um que saiba o CPF entraria.">
              <Switch checked={f.exigir_pin} onCheckedChange={(v) => set({ exigir_pin: v })} />
            </SwitchRow>
            <SwitchRow titulo="Marcar presença na aula" descricao="O check-in marca “chegou” na reserva da aula (mesma regra da agenda).">
              <Switch checked={f.registrar_presenca} onCheckedChange={(v) => set({ registrar_presenca: v })} />
            </SwitchRow>
          </div>
        </FormSection>

        <FormSection titulo="Mensagens e termo" descricao="O termo de consentimento é mostrado ao aluno antes do cadastro do rosto (LGPD). Alterar o termo vale para os próximos aceites.">
          <Field label="Boas-vindas no totem" dica="Use {nome} para o primeiro nome. Em branco: “Olá, Ana! Boa aula.”" className="sm:col-span-2">
            <Input value={f.mensagem_boas_vindas ?? ""} onChange={(e) => set({ mensagem_boas_vindas: e.target.value || null })} maxLength={200} placeholder="Que bom te ver, {nome}!" />
          </Field>
          <Field label="Termo de consentimento da biometria" className="sm:col-span-2">
            <Textarea value={f.termo_biometria} onChange={(e) => set({ termo_biometria: e.target.value })} rows={10} minLength={40} maxLength={8000} />
          </Field>
        </FormSection>
      </fieldset>
      {editar && (
        <div className="flex justify-end pt-4">
          <Button type="submit" disabled={salvar.isPending}>
            {salvar.isPending ? <Loader2 className="animate-spin" /> : <Save />} Salvar regras
          </Button>
        </div>
      )}
    </form>
  );
}
