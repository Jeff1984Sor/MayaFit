"""Regras puras do CRM (sem banco): origem, deduplicação, prazos de tarefa, temperatura, sugestões, mensagens prontas
de WhatsApp e cálculo do funil. Tudo testado em `tests/crm/test_regras.py`.

(Por convenção do projeto as regras puras ficam em `app/domain/`; estão aqui porque o módulo foi feito em paralelo.
O coordenador pode movê-las para `app/domain/crm.py` sem mudar nada além do import.)
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from app.domain.telefone import normalizar_telefone_br
from app.modules.crm.models import MarcoEtapa, OrigemLead, SituacaoLead, StatusAulaExperimental

FUSO = ZoneInfo("America/Sao_Paulo")

ROTULO_ORIGEM = {
    OrigemLead.SITE: "Site",
    OrigemLead.INSTAGRAM: "Instagram",
    OrigemLead.INDICACAO: "Indicação",
    OrigemLead.WELLHUB: "Wellhub",
    OrigemLead.TOTALPASS: "TotalPass",
    OrigemLead.PASSANTE: "Passante (veio ao estúdio)",
    OrigemLead.WHATSAPP: "WhatsApp",
    OrigemLead.OUTROS: "Outros",
}

_SINONIMOS_ORIGEM = {
    "site": OrigemLead.SITE, "website": OrigemLead.SITE, "formulario": OrigemLead.SITE, "google": OrigemLead.SITE,
    "instagram": OrigemLead.INSTAGRAM, "insta": OrigemLead.INSTAGRAM, "ig": OrigemLead.INSTAGRAM,
    "facebook": OrigemLead.INSTAGRAM, "meta": OrigemLead.INSTAGRAM,
    "indicacao": OrigemLead.INDICACAO, "indicado": OrigemLead.INDICACAO,
    "wellhub": OrigemLead.WELLHUB, "gympass": OrigemLead.WELLHUB,
    "totalpass": OrigemLead.TOTALPASS, "total pass": OrigemLead.TOTALPASS,
    "passante": OrigemLead.PASSANTE, "balcao": OrigemLead.PASSANTE, "visita": OrigemLead.PASSANTE,
    "whatsapp": OrigemLead.WHATSAPP, "zap": OrigemLead.WHATSAPP,
    "outros": OrigemLead.OUTROS, "outro": OrigemLead.OUTROS,
}


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar_origem(valor: str | OrigemLead | None) -> OrigemLead:
    """Texto livre ("Instagram", "Gympass", "indicação", "wellhub/totalpass") -> origem conhecida; o resto vira OUTROS."""
    if isinstance(valor, OrigemLead):
        return valor
    chave = _sem_acento((valor or "").strip().lower())
    if chave in _SINONIMOS_ORIGEM:
        return _SINONIMOS_ORIGEM[chave]
    for parte in chave.replace("|", "/").split("/"):
        if parte.strip() in _SINONIMOS_ORIGEM:
            return _SINONIMOS_ORIGEM[parte.strip()]
    return OrigemLead.OUTROS


def normalizar_email(email: str | None) -> str | None:
    e = (email or "").strip().lower()
    return e if e and "@" in e else None


def normalizar_telefone(telefone: str | None) -> str | None:
    """Canônico (55 + DDD + número). Telefone que não normaliza (ex.: sem DDD) vira só dígitos, para não se perder."""
    if not telefone or not telefone.strip():
        return None
    canonico = normalizar_telefone_br(telefone)
    if canonico:
        return canonico
    digitos = "".join(c for c in telefone if c.isdigit())
    return digitos or None


def normalizar_tags(tags: Iterable[str] | None) -> list[str]:
    """Sem repetição (ignorando maiúsculas), sem vazias, no máximo 12 tags de até 30 caracteres."""
    vistas: dict[str, str] = {}
    for t in tags or []:
        limpa = " ".join((t or "").split())[:30]
        if limpa and limpa.lower() not in vistas:
            vistas[limpa.lower()] = limpa
    return list(vistas.values())[:12]


# ------------------------------------------------------------------------------------------------ tarefas
def dia_local(instante: datetime) -> date:
    return instante.astimezone(FUSO).date()


def classificar_tarefa(vence_em: datetime, concluida: bool, agora: datetime) -> str:
    """"concluida", "atrasada" (já venceu), "hoje" (vence hoje, mais tarde) ou "futura". Dia no fuso de São Paulo."""
    if concluida:
        return "concluida"
    if vence_em < agora:
        return "atrasada"
    if dia_local(vence_em) == dia_local(agora):
        return "hoje"
    return "futura"


def horario_comercial(base: datetime, *, minutos: int = 0, hora_padrao: int = 9) -> datetime:
    """`base + minutos`, empurrado para o horário comercial (8h-20h, São Paulo). Usado nos lembretes automáticos."""
    alvo = (base + timedelta(minutes=minutos)).astimezone(FUSO)
    if alvo.hour >= 20:
        alvo = (alvo + timedelta(days=1)).replace(hour=hora_padrao, minute=0, second=0, microsecond=0)
    elif alvo.hour < 8:
        alvo = alvo.replace(hour=hora_padrao, minute=0, second=0, microsecond=0)
    return alvo.astimezone(base.tzinfo or FUSO)


# ------------------------------------------------------------------------------------------------ temperatura e sugestões
def dias_entre(inicio: datetime | None, fim: datetime) -> int | None:
    if inicio is None:
        return None
    return max(0, (fim - inicio).days)


def temperatura(
    *, situacao: SituacaoLead, dias_sem_contato: int | None, dias_na_etapa: int, aula_status: StatusAulaExperimental | None,
    aula_em: datetime | None, agora: datetime,
) -> str:
    """"quente", "morno" ou "frio" (só leads abertos; os demais devolvem "encerrado").

    Quente: aula experimental agendada no futuro, aula feita há até 3 dias ou contato há até 2 dias.
    Morno: contato há até 7 dias. Frio: sem contato há mais de 7 dias, ou nunca contatado e no funil há mais de 2 dias.
    """
    if situacao != SituacaoLead.ABERTO:
        return "encerrado"
    if aula_status == StatusAulaExperimental.AGENDADA and aula_em and aula_em >= agora:
        return "quente"
    if aula_status == StatusAulaExperimental.REALIZADA and aula_em and (agora - aula_em) <= timedelta(days=3):
        return "quente"
    if dias_sem_contato is None:
        return "morno" if dias_na_etapa <= 2 else "frio"
    if dias_sem_contato <= 2:
        return "quente"
    if dias_sem_contato <= 7:
        return "morno"
    return "frio"


def esta_parado(dias_na_etapa: int, dias_alerta: int, situacao: SituacaoLead) -> bool:
    return situacao == SituacaoLead.ABERTO and dias_alerta > 0 and dias_na_etapa >= dias_alerta


def sugestao_proxima_acao(
    *, situacao: SituacaoLead, marco: MarcoEtapa | None, primeira_etapa: bool, tem_interacao: bool,
    aula_status: StatusAulaExperimental | None, aula_em: datetime | None, dias_sem_contato: int | None,
    tem_telefone: bool, agora: datetime,
) -> str | None:
    """Uma frase com o próximo passo mais útil para o lead (aparece na ficha e no cartão)."""
    if situacao == SituacaoLead.GANHO:
        return None
    if situacao == SituacaoLead.PERDIDO:
        return "Lead perdido. Se a situação mudou, reabra e retome o contato."
    if aula_status == StatusAulaExperimental.AGENDADA and aula_em:
        if aula_em >= agora:
            if aula_em - agora <= timedelta(hours=30):
                return "A aula experimental é em breve: confirme presença pelo WhatsApp."
            return "Aula experimental agendada. Um dia antes, mande a confirmação."
        return "A aula experimental já passou: registre se a pessoa compareceu."
    if aula_status == StatusAulaExperimental.FALTOU:
        return "Faltou à aula experimental: ofereça um novo horário."
    if aula_status == StatusAulaExperimental.REALIZADA and marco != MarcoEtapa.PROPOSTA:
        return "Fez a aula experimental: envie a proposta enquanto a experiência está fresca."
    if not tem_interacao:
        return ("Faça o primeiro contato agora: quem responde em minutos converte bem mais."
                if tem_telefone else "Sem telefone: peça o WhatsApp por e-mail para agilizar o contato.")
    if marco == MarcoEtapa.PROPOSTA:
        if (dias_sem_contato or 0) >= 2:
            return "Proposta enviada há dias: faça um follow-up e tire dúvidas sobre planos."
        return "Proposta na mesa: combine o início e converta em aluno."
    if aula_status is None and (primeira_etapa or marco is None):
        return "Convide para uma aula experimental: é o passo que mais converte."
    if (dias_sem_contato or 0) >= 5:
        return "Sem contato há dias: retome a conversa antes que esfrie."
    return None


# ------------------------------------------------------------------------------------------------ WhatsApp
def primeiro_nome(nome: str) -> str:
    return (nome or "").strip().split(" ")[0].title() or "tudo bem"


def link_whatsapp(telefone: str | None, texto: str | None = None) -> str | None:
    """Link wa.me (abre o WhatsApp com a mensagem pronta). Sem telefone com DDD, não há link."""
    numero = normalizar_telefone_br(telefone)
    if not numero:
        return None
    return f"https://wa.me/{numero}" + (f"?text={quote(texto)}" if texto else "")


def _quando(instante: datetime) -> str:
    local = instante.astimezone(FUSO)
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    return f"{dias[local.weekday()]}, {local:%d/%m}, às {local:%H:%M}"


def mensagens_whatsapp(
    *, nome: str, estudio: str, interesse: str | None, marco: MarcoEtapa | None, situacao: SituacaoLead,
    aula_status: StatusAulaExperimental | None, aula_em: datetime | None,
) -> list[dict[str, str]]:
    """Mensagens prontas, da mais adequada ao momento do lead para as gerais (a primeira é a sugerida)."""
    n = primeiro_nome(nome)
    oque = interesse.strip().lower() if interesse and interesse.strip() else "as aulas"
    msgs: list[dict[str, str]] = []
    if aula_status == StatusAulaExperimental.AGENDADA and aula_em:
        msgs.append({"titulo": "Confirmar aula experimental", "texto": (
            f"Oi, {n}! Aqui é do {estudio}. Passando para confirmar sua aula experimental {_quando(aula_em)}. "
            "Venha com roupa confortável e chegue uns 10 minutinhos antes. Posso confirmar?")})
    if aula_status == StatusAulaExperimental.REALIZADA or marco == MarcoEtapa.AULA_REALIZADA:
        msgs.append({"titulo": "Pós-aula", "texto": (
            f"Oi, {n}! Que bom ter você aqui no {estudio}. O que achou da aula? "
            "Se quiser, te mando as opções de planos para começar já na próxima semana.")})
    if marco == MarcoEtapa.PROPOSTA:
        msgs.append({"titulo": "Follow-up da proposta", "texto": (
            f"Oi, {n}! Conseguiu ver a proposta do {estudio}? Fico à disposição para ajustar horários "
            "ou tirar qualquer dúvida sobre os planos.")})
    if aula_status == StatusAulaExperimental.FALTOU:
        msgs.append({"titulo": "Remarcar aula", "texto": (
            f"Oi, {n}! Sentimos sua falta na aula experimental. Imprevistos acontecem! "
            "Quer que eu reserve um novo horário para você?")})
    if situacao == SituacaoLead.PERDIDO:
        msgs.append({"titulo": "Reconquistar", "texto": (
            f"Oi, {n}! Aqui é do {estudio}. Faz um tempo que conversamos sobre {oque}. "
            "Abrimos novos horários e lembrei de você. Quer fazer uma aula experimental sem compromisso?")})
    msgs.append({"titulo": "Primeiro contato", "texto": (
        f"Oi, {n}! Aqui é do {estudio}. Vi seu interesse em {oque} e queria te convidar para uma "
        "aula experimental gratuita. Qual o melhor dia e horário para você?")})
    msgs.append({"titulo": "Retomar contato", "texto": (
        f"Oi, {n}! Tudo bem? Aqui é do {estudio}. Ainda tem interesse em {oque}? "
        "Tenho alguns horários livres esta semana.")})
    return msgs


# ------------------------------------------------------------------------------------------------ funil e relatórios
@dataclass(frozen=True)
class EtapaInfo:
    id: int
    nome: str
    ordem: int
    tipo: str  # ABERTA | GANHO | PERDIDO
    cor: str = "#7C8FFF"


def etapas_do_funil(etapas: Iterable[EtapaInfo]) -> list[EtapaInfo]:
    """Etapas que formam a "escada" do funil: as abertas em ordem e, por último, a de ganho."""
    abertas = sorted((e for e in etapas if e.tipo == "ABERTA"), key=lambda e: (e.ordem, e.id))
    ganho = [e for e in etapas if e.tipo == "GANHO"]
    return abertas + ganho[:1]


def degrau_alcancado(escada: list[EtapaInfo], etapas_visitadas: Iterable[int]) -> int:
    """Índice do degrau mais alto que o lead já visitou na escada (-1 se nenhum)."""
    posicao = {e.id: i for i, e in enumerate(escada)}
    return max((posicao[i] for i in etapas_visitadas if i in posicao), default=-1)


def conversao_por_etapa(escada: list[EtapaInfo], degraus: list[int]) -> list[dict]:
    """Quantos leads chegaram a cada etapa (ou além), % do total e % da etapa anterior."""
    total = len(degraus)
    saida: list[dict] = []
    anterior: int | None = None
    for i, e in enumerate(escada):
        chegaram = sum(1 for d in degraus if d >= i)
        saida.append({
            "etapa_id": e.id, "etapa": e.nome, "cor": e.cor, "tipo": e.tipo, "quantidade": chegaram,
            "pct_total": percentual(chegaram, total),
            "pct_anterior": percentual(chegaram, anterior) if anterior is not None else 100.0 if chegaram else 0.0,
        })
        anterior = chegaram
    return saida


def percentual(parte: int | float, total: int | float | None) -> float:
    if not total:
        return 0.0
    return round(100.0 * parte / total, 1)


def media_dias(intervalos: Iterable[timedelta]) -> float | None:
    lista = list(intervalos)
    if not lista:
        return None
    return round(sum(i.total_seconds() for i in lista) / len(lista) / 86400, 1)


def somar(valores: Iterable[Decimal | None]) -> Decimal:
    return sum((v or Decimal("0") for v in valores), Decimal("0"))
