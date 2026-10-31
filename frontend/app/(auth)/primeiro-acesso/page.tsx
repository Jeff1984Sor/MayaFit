"use client";

import { AlertTriangle, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Field } from "@/components/mayacorp/form";
import { SenhaInput } from "@/components/mayacorp/senha-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { PrimeiroAcessoInfo } from "@/lib/tipos-admin";

const LOGIN_OK = /^[a-z0-9._-]{3,60}$/;

/** Sugestão de login curto a partir do nome: "Ana Paula Souza" → "ana.souza". */
function sugerirLogin(nome: string) {
  const partes = nome
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z\s]/g, "")
    .split(/\s+/)
    .filter(Boolean);
  if (!partes.length) return "";
  return partes.length > 1 ? `${partes[0]}.${partes[partes.length - 1]}` : partes[0];
}

/** Boas-vindas de um estúdio novo: o dono cria o usuário master (login e senha) pelo link e já entra. */
export default function PrimeiroAcessoPage() {
  const [token, setToken] = useState<string | null>(null);
  const [info, setInfo] = useState<PrimeiroAcessoInfo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [f, setF] = useState({ nome: "", email: "", login: "", senha: "", confirma: "" });
  const [loginTocado, setLoginTocado] = useState(false);
  const [salvando, setSalvando] = useState(false);

  /* eslint-disable react-hooks/set-state-in-effect -- lê o link uma vez */
  useEffect(() => {
    const tk = new URLSearchParams(window.location.search).get("token");
    setToken(tk);
    if (!tk) {
      setErro("Link incompleto. Abra o link do e-mail de boas-vindas ou peça um novo à equipe MayaFit.");
      return;
    }
    api
      .get<PrimeiroAcessoInfo>("/auth/primeiro-acesso", { token: tk })
      .then((r) => {
        setInfo(r);
        setF((o) => ({ ...o, email: r.email ?? "" }));
      })
      .catch((e: Error) => setErro(e.message));
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  const login = loginTocado ? f.login : sugerirLogin(f.nome);
  const loginInvalido = login.length > 0 && !LOGIN_OK.test(login);
  const diferente = f.confirma.length > 0 && f.confirma !== f.senha;

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!LOGIN_OK.test(login)) return toast.error("Login: de 3 a 60 letras minúsculas, números, ponto, hífen ou sublinhado.");
    if (f.senha !== f.confirma) return toast.error("As senhas não conferem.");
    setSalvando(true);
    try {
      // o BFF transforma os tokens da resposta em cookies de sessão
      await api.post("/auth/primeiro-acesso", { token, nome: f.nome.trim(), email: f.email.trim(), login, senha: f.senha }, { auth: false });
      window.location.replace("/"); // recarrega inteiro: entra já no estúdio certo
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Não foi possível criar o acesso.");
      setSalvando(false);
    }
  };

  if (erro)
    return (
      <div className="space-y-5 text-center">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-warning/10">
          <AlertTriangle className="size-7 text-warning-ink" />
        </div>
        <h1 className="text-xl font-semibold">Não foi possível abrir o primeiro acesso</h1>
        <p className="text-sm text-muted-foreground">{erro}</p>
        <Button className="h-11 w-full" render={<Link href="/login" />}>
          Ir para o login
        </Button>
      </div>
    );

  if (!info)
    return (
      <div className="grid place-items-center py-10" aria-busy>
        <Loader2 className="animate-spin text-muted-foreground" />
      </div>
    );

  const estudio = info.estudio ?? info.escritorio ?? "seu estúdio";

  return (
    <form onSubmit={enviar} className="space-y-4">
      <div>
        <div className="mb-4 grid size-12 place-items-center rounded-xl bg-brand/12 text-navy dark:text-brand">
          <Sparkles className="size-6" />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">Bem-vindo ao MayaFit</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Crie o usuário master do <b>{estudio}</b>. Com ele você cadastra a equipe, as aulas e os alunos.
        </p>
      </div>
      <Field label="Seu nome" obrigatorio htmlFor="pa-nome">
        <Input id="pa-nome" value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} className="h-11" required minLength={3} autoFocus autoComplete="name" />
      </Field>
      <Field label="E-mail" obrigatorio htmlFor="pa-email" dica="Para recuperar a senha e receber avisos. Não é usado para entrar.">
        <Input id="pa-email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} className="h-11" required autoComplete="email" />
      </Field>
      <Field
        label="Login"
        obrigatorio
        htmlFor="pa-login"
        erro={loginInvalido ? "Use de 3 a 60 letras minúsculas, números, ponto, hífen ou sublinhado." : undefined}
        dica="É com ele que você entra. Curto e fácil, ex.: ana"
      >
        <Input
          id="pa-login"
          value={login}
          onChange={(e) => {
            setLoginTocado(true);
            setF({ ...f, login: e.target.value.toLowerCase().trim() });
          }}
          className="h-11 font-mono"
          required
          autoComplete="username"
        />
      </Field>
      <Field label="Senha" obrigatorio htmlFor="pa-senha" dica="8 ou mais caracteres, com letras e números.">
        <SenhaInput id="pa-senha" value={f.senha} onChange={(v) => setF({ ...f, senha: v })} className="h-11" required minLength={8} autoComplete="new-password" forca />
      </Field>
      <Field label="Confirme a senha" obrigatorio htmlFor="pa-conf" erro={diferente ? "As senhas não conferem" : undefined}>
        <SenhaInput id="pa-conf" value={f.confirma} onChange={(v) => setF({ ...f, confirma: v })} className="h-11" required autoComplete="new-password" />
      </Field>
      <Button type="submit" disabled={salvando || loginInvalido || diferente} className="h-11 w-full">
        {salvando && <Loader2 className="animate-spin" />}
        Criar meu acesso e entrar
      </Button>
    </form>
  );
}
