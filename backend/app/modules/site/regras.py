"""Regras puras do site (sem banco): fotos, mapa, WhatsApp, anti-spam, conteúdo inicial e grade.

Testadas em `tests/site/test_regras.py`.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import time
from urllib.parse import quote, urlparse

RX_FOTO = re.compile(r"^site/[0-9a-f]{32}\.(png|jpg|jpeg|webp)$")
RX_NOME_FOTO = re.compile(r"^[0-9a-f]{32}\.(png|jpg|jpeg|webp)$")

TEXTO_CONSENTIMENTO = (
    "Autorizo o estúdio a usar meus dados para retornar este contato e agendar a aula, conforme a política de privacidade."
)
TEMPO_MINIMO_MS = 2500  # quem preenche o formulário em menos de 2,5 s é robô
ORDEM_PADRAO = ("hero", "sobre", "modalidades", "planos", "grade", "equipe", "depoimentos", "galeria", "faq",
                "localizacao", "contato")
LIGADAS_PADRAO = {"hero", "sobre", "modalidades", "planos", "grade", "equipe", "faq", "localizacao", "contato"}


def foto_valida(caminho: str | None) -> bool:
    """Só fotos enviadas pelo editor (pasta `site/`, nome aleatório) entram no conteúdo."""
    return bool(caminho and RX_FOTO.match(caminho))


def url_foto(caminho: str | None) -> str | None:
    """Caminho público (relativo à API) da foto do site."""
    if not foto_valida(caminho):
        return None
    return f"/site-publico/imagens/{caminho.split('/', 1)[1]}"


# ------------------------------------------------------------------------------------------------------------ mapa
_HOSTS_MAPA = ("google.com", "google.com.br", "maps.app.goo.gl", "goo.gl")


def _host_google(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    if u.scheme != "https" or not u.hostname:
        return False
    h = u.hostname.lower()
    return any(h == d or h.endswith("." + d) for d in _HOSTS_MAPA)


@dataclass(frozen=True)
class Mapa:
    embed: str | None  # URL para <iframe> (só google.com/maps/embed ou ?output=embed)
    link: str | None  # URL para abrir no app do Google Maps


def extrair_mapa(valor: str) -> Mapa | None:
    """Aceita o link do Google Maps (compartilhar) ou o código `<iframe>` de "Incorporar um mapa".
    Devolve None para qualquer outra coisa (nada de iframe de domínio arbitrário)."""
    v = (valor or "").strip()
    if not v:
        return None
    m = re.search(r"""<iframe[^>]*\ssrc=["']([^"']+)["']""", v, re.I)
    url = html.unescape(m.group(1)) if m else v
    if re.search(r"\s", url) or not _host_google(url):
        return None
    u = urlparse(url)
    if u.path.startswith("/maps/embed") or "output=embed" in u.query:
        return Mapa(embed=url, link=None)
    if u.hostname in ("maps.app.goo.gl", "goo.gl") or "/maps" in u.path:
        return Mapa(embed=None, link=url)
    return None


def mapa_da_pagina(valor: str, endereco: str) -> Mapa:
    """Mapa final da página: o que o estúdio colou ou, na falta de um iframe, o mapa gerado pelo endereço."""
    m = extrair_mapa(valor) if valor else None
    pelo_endereco = f"https://www.google.com/maps?q={quote(endereco)}&output=embed" if endereco.strip() else None
    busca = f"https://www.google.com/maps/search/?api=1&query={quote(endereco)}" if endereco.strip() else None
    if m and m.embed:
        return Mapa(embed=m.embed, link=busca)
    return Mapa(embed=pelo_endereco, link=(m.link if m else None) or busca)


# ------------------------------------------------------------------------------------------------- contato / redes
def so_digitos(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def numero_whatsapp(v: str | None) -> str | None:
    """Número no formato do wa.me (com DDI 55 quando vier só DDD + número)."""
    d = so_digitos(v)
    if len(d) in (10, 11):
        d = "55" + d
    return d if 12 <= len(d) <= 13 else None


def url_rede(v: str) -> str | None:
    """@usuario, usuario ou https://... (http e outros esquemas não)."""
    v = v.strip()
    if v.startswith("https://") and " " not in v:
        return v
    if re.fullmatch(r"@?[A-Za-z0-9_.\-]{1,60}", v):
        return v
    return None


def avaliar_spam(website: str | None, tempo_ms: int | None) -> str | None:
    """Motivo para descartar o envio em silêncio (o robô recebe "ok"), ou None se parece humano."""
    if website and website.strip():
        return "honeypot"
    if tempo_ms is not None and tempo_ms < TEMPO_MINIMO_MS:
        return "rapido"
    return None


# ------------------------------------------------------------------------------------------------------------ grade
def primeiro_nome(nome: str | None) -> str | None:
    if not nome or not nome.strip():
        return None
    return nome.strip().split()[0]


def chave_horario(dia: int, ini: time, fim: time, modalidade: str, professor: str | None) -> tuple:
    return (dia, ini, fim, modalidade, professor or "")


# ------------------------------------------------------------------------------------------------- conteúdo inicial
def conteudo_padrao(nome_estudio: str, modalidades: list[tuple[int, str]] | None = None,
                    profissionais: list[int] | None = None) -> dict:
    """Rascunho inicial, já com cara de site pronto: o estúdio só ajusta e publica (meta: publicar em < 5 min)."""
    nome = nome_estudio or "Nosso estúdio"
    return {
        "secoes": [{"tipo": t, "ativa": t in LIGADAS_PADRAO} for t in ORDEM_PADRAO],
        "hero": {
            "titulo": "Movimento que transforma, no seu ritmo.",
            "subtitulo": f"Aulas em turmas pequenas, com atenção de verdade. Venha conhecer o {nome}.",
            "botao_texto": "Agende sua aula experimental",
        },
        "sobre": {
            "titulo": f"Sobre o {nome}",
            "texto": (
                "Somos um espaço pensado para você se sentir bem desde a primeira aula. Professores qualificados, "
                "acompanhamento individual e um ambiente acolhedor para cuidar do corpo e da mente."
            ),
            "destaques": ["Turmas reduzidas", "Profissionais qualificados", "Aula experimental"],
        },
        "modalidades": {
            "titulo": "Modalidades",
            "subtitulo": "Escolha a aula que combina com você.",
            "itens": [{"tipo_servico_id": i, "mostrar": True, "descricao": ""} for i, _ in (modalidades or [])],
        },
        "planos": {"titulo": "Planos", "subtitulo": "Escolha a frequência ideal para a sua rotina.", "mostrar_precos": True},
        "grade": {"titulo": "Horários", "subtitulo": "Confira a grade da semana.", "mostrar_professor": True},
        "equipe": {
            "titulo": "Nossa equipe",
            "itens": [{"profissional_id": i, "mostrar": False} for i in (profissionais or [])],
        },
        "faq": {
            "titulo": "Perguntas frequentes",
            "itens": [
                {"pergunta": "Preciso ter experiência?",
                 "resposta": "Não. As aulas são adaptadas ao seu nível, do iniciante ao avançado."},
                {"pergunta": "Como funciona a aula experimental?",
                 "resposta": "Você agenda pelo formulário ou WhatsApp, conhece o espaço e faz uma aula com um dos nossos professores."},
                {"pergunta": "O que devo levar?",
                 "resposta": "Roupa confortável, uma garrafinha de água e disposição. O resto é com a gente."},
            ],
        },
        "contato": {"titulo": "Fale com a gente", "subtitulo": "Respondemos rapidinho."},
        "seo": {"titulo": f"{nome}", "descricao": f"{nome}: aulas com atenção individual. Agende sua aula experimental."},
    }
