"""Regras PURAS da integração Wellhub (sem banco, sem rede): assinatura, leitura do payload, idempotência,
comparação de vagas, repasse, passos do assistente e alertas. Testadas em `tests/wellhub/test_regras.py`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# Tipos de evento documentados (Booking API e Access Control API). Variações de grafia aceitas de propósito.
RESERVA_PEDIDA = "booking-requested"
RESERVA_CANCELADA = "booking-canceled"
RESERVA_CANCELADA_TARDE = "booking-late-canceled"
CHECKIN = "checkin"
CHECKIN_RESERVA = "checkin-booking-occurred"

_SINONIMOS = {
    "booking-requested": RESERVA_PEDIDA, "booking_requested": RESERVA_PEDIDA,
    "booking-canceled": RESERVA_CANCELADA, "booking-cancelled": RESERVA_CANCELADA, "booking_canceled": RESERVA_CANCELADA,
    "booking-late-canceled": RESERVA_CANCELADA_TARDE, "booking-late-cancelled": RESERVA_CANCELADA_TARDE,
    "booking_late_canceled": RESERVA_CANCELADA_TARDE,
    "checkin": CHECKIN, "check-in": CHECKIN, "check_in": CHECKIN, "gympass-checkin": CHECKIN,
    "checkin-booking-occurred": CHECKIN_RESERVA, "checkin_booking_occurred": CHECKIN_RESERVA,
}
TIPOS_CONHECIDOS = frozenset(_SINONIMOS.values())

ROTULO_TIPO = {
    RESERVA_PEDIDA: "Reserva pedida",
    RESERVA_CANCELADA: "Reserva cancelada",
    RESERVA_CANCELADA_TARDE: "Cancelamento tardio",
    CHECKIN: "Check-in",
    CHECKIN_RESERVA: "Check-in em aula reservada",
}

# Resultados de um evento. Os "finais" não são processados de novo (reenvio = duplicado).
RESULTADOS = ("processado", "cancelado", "rejeitado", "descartado", "erro", "pendente")
RESULTADOS_FINAIS = frozenset({"processado", "cancelado", "rejeitado", "descartado"})


# ------------------------------------------------------------------------------------------------ assinatura
def assinar(segredo: str, corpo: bytes) -> str:
    """X-Gympass-Signature: HMAC-SHA1 do corpo CRU com o segredo, em hexadecimal MAIÚSCULO (documentação pública)."""
    return hmac.new(segredo.encode(), corpo, hashlib.sha1).hexdigest().upper()


def assinatura_confere(segredo: str, corpo: bytes, recebida: str | None) -> bool:
    """Compara em tempo constante. Aceita o hex em maiúsculas ou minúsculas e um eventual prefixo `sha1=`."""
    if not segredo or not recebida:
        return False
    valor = recebida.strip()
    if valor.lower().startswith("sha1="):
        valor = valor[5:]
    try:
        recebido = valor.upper().encode("ascii")
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(assinar(segredo, corpo).encode("ascii"), recebido)


# ------------------------------------------------------------------------------------------------ payload
def _d(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _txt(v: Any, limite: int = 200) -> str:
    return str(v if v is not None else "").strip()[:limite]


def tipo_do_evento(payload: dict) -> str:
    bruto = _txt(payload.get("event_type") or payload.get("type") or payload.get("event"), 60).lower()
    return _SINONIMOS.get(bruto, bruto)


def dados_do_evento(payload: dict) -> dict:
    return _d(payload.get("event_data")) or _d(payload.get("data"))


def usuario_do_evento(payload: dict) -> dict:
    return _d(dados_do_evento(payload).get("user"))


def gympass_id(payload: dict) -> str:
    u = usuario_do_evento(payload)
    valor = u.get("unique_token") or u.get("gympass_id") or u.get("gpw_id") or u.get("id")
    return re.sub(r"\s", "", _txt(valor, 20))


def slot_do_evento(payload: dict) -> dict:
    return _d(dados_do_evento(payload).get("slot"))


def booking_number(payload: dict) -> str:
    d = dados_do_evento(payload)
    return _txt(slot_do_evento(payload).get("booking_number") or d.get("booking_number")
                or _d(d.get("booking")).get("booking_number") or _d(d.get("booking")).get("number"), 60)


def slot_id(payload: dict) -> str:
    return _txt(slot_do_evento(payload).get("id") or dados_do_evento(payload).get("slot_id"), 40)


def gym_id(payload: dict) -> str:
    d = dados_do_evento(payload)
    return _txt(slot_do_evento(payload).get("gym_id") or _d(d.get("gym")).get("id") or d.get("gym_id")
                or payload.get("gym_id"), 40)


def nome_do_usuario(payload: dict) -> str:
    u = usuario_do_evento(payload)
    nome = _txt(u.get("name") or u.get("full_name"), 150)
    if not nome:
        nome = " ".join(p for p in (_txt(u.get("first_name"), 80), _txt(u.get("last_name"), 80)) if p)
    return nome[:150]


def documento_do_usuario(payload: dict) -> str:
    u = usuario_do_evento(payload)
    return re.sub(r"\D", "", _txt(u.get("document") or u.get("cpf") or u.get("document_number"), 30))


def instante_do_evento(payload: dict, padrao: datetime) -> datetime:
    """`timestamp` (segundos ou milissegundos desde 1970) ou ISO 8601. Sem ou inválido: `padrao`."""
    d = dados_do_evento(payload)
    v = d.get("timestamp", payload.get("timestamp"))
    if isinstance(v, int | float) and v > 0:
        return datetime.fromtimestamp(v / 1000 if v > 10**11 else v, UTC)
    if isinstance(v, str) and v.strip():
        s = v.strip()
        if s.isdigit():
            n = int(s)
            return datetime.fromtimestamp(n / 1000 if n > 10**11 else n, UTC)
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return padrao
    return padrao


def chave_do_evento(payload: dict) -> str:
    """Idempotência: o id do evento quando vier; senão o hash do conteúdo canônico (o reenvio idêntico casa)."""
    d = dados_do_evento(payload)
    explicito = _txt(payload.get("event_id") or payload.get("id") or d.get("event_id"), 60)
    if explicito:
        return f"id:{explicito}"
    canonico = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(canonico.encode()).hexdigest()[:64]


def mascarar_gympass(g: str | None) -> str | None:
    if not g:
        return None
    return "•" * max(len(g) - 4, 0) + g[-4:]


# ------------------------------------------------------------------------------------------------ grade
@dataclass(frozen=True)
class Vagas:
    capacidade: int
    reservadas: int


def acao_do_slot(publicado: Vagas | None, atual: Vagas | None) -> str:
    """O que fazer com o horário no Wellhub: criar | atualizar | remover | manter."""
    if atual is None:
        return "remover" if publicado is not None else "manter"
    if publicado is None:
        return "criar"
    return "manter" if publicado == atual else "atualizar"


def vagas_para_publicar(capacidade: int, reservadas: int) -> Vagas:
    """Nunca publica mais reservas que a capacidade nem números negativos."""
    cap = max(int(capacidade or 0), 0)
    return Vagas(cap, min(max(int(reservadas or 0), 0), cap))


# ------------------------------------------------------------------------------------------------ repasse
def valor_estimado(checkins_validados: int, valor_unitario: Decimal | None) -> Decimal:
    if not valor_unitario or checkins_validados <= 0:
        return Decimal("0.00")
    return (Decimal(checkins_validados) * Decimal(valor_unitario)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def variacao(atual: float, anterior: float) -> float | None:
    if not anterior:
        return None
    return round((atual - anterior) / anterior, 4)


# ------------------------------------------------------------------------------------------------ assistente
@dataclass
class EstadoConfig:
    existe: bool = False
    ativo: bool = False
    gym_id: bool = False
    api_key: bool = False
    webhook_secret: bool = False
    teste_ok: bool | None = None
    mapeamentos_com_produto: int = 0
    mapeamentos_publicados: int = 0
    sync_ok: bool | None = None
    slots_publicados: int = 0
    valor_repasse: bool = False


@dataclass
class Passo:
    id: str
    titulo: str
    concluido: bool
    pendencia: str | None = None


def passos_do_assistente(e: EstadoConfig) -> list[Passo]:
    credenciais = e.gym_id and e.api_key
    return [
        Passo("credenciais", "Credenciais e conexão", credenciais and e.teste_ok is True,
              None if credenciais and e.teste_ok else ("Cadastre o gym id e a chave de API." if not credenciais
                                                       else "Teste a conexão com o Wellhub.")),
        Passo("webhook", "Webhook (segredo da assinatura)", e.webhook_secret,
              None if e.webhook_secret else "Cadastre o segredo do webhook (o mesmo informado ao Wellhub)."),
        Passo("mapeamento", "Serviços ↔ produtos Wellhub", e.mapeamentos_com_produto > 0,
              None if e.mapeamentos_com_produto else "Ligue ao menos um serviço do estúdio a um produto do Wellhub."),
        Passo("grade", "Publicar a grade", e.mapeamentos_publicados > 0 and e.sync_ok is not False,
              None if e.mapeamentos_publicados and e.sync_ok is not False else "Publique as aulas no Wellhub."),
        Passo("repasse", "Repasse e ativação", e.valor_repasse and e.ativo,
              None if e.valor_repasse and e.ativo else ("Informe o valor de repasse por check-in." if not e.valor_repasse
                                                        else "Ative a integração.")),
    ]


# ------------------------------------------------------------------------------------------------ alertas
@dataclass
class Alerta:
    nivel: str  # danger | warning | info
    titulo: str
    descricao: str
    acao: str | None = None  # eventos | assistente | relatorio
    extra: dict = field(default_factory=dict)


def montar_alertas(*, ativo: bool, configurada: bool, eventos_com_erro: int, falhas_assinatura_24h: int,
                   sync_ok: bool | None, sync_resumo: str | None, teste_ok: bool | None,
                   checkins_sem_validacao: int, reservas_sem_resposta: int) -> list[Alerta]:
    a: list[Alerta] = []
    if reservas_sem_resposta:
        a.append(Alerta("danger", f"{reservas_sem_resposta} reserva(s) sem resposta ao Wellhub",
                        "O Wellhub rejeita sozinho a reserva que não for respondida em 15 minutos. Reprocesse o evento.",
                        "eventos"))
    if eventos_com_erro:
        a.append(Alerta("danger", f"{eventos_com_erro} evento(s) do Wellhub com erro",
                        "Confira o motivo de cada um, corrija (serviço, capacidade, aluno) e reprocesse.", "eventos"))
    if falhas_assinatura_24h:
        a.append(Alerta("warning", "Chamadas com assinatura inválida",
                        f"{falhas_assinatura_24h} chamada(s) recusada(s) nas últimas 24 h. Confira se o segredo do webhook é o "
                        "mesmo cadastrado no Wellhub.", "assistente"))
    if sync_ok is False:
        a.append(Alerta("danger", "A última publicação da grade falhou", sync_resumo or "Tente publicar de novo.", "assistente"))
    if teste_ok is False:
        a.append(Alerta("warning", "O último teste de conexão falhou",
                        "Confira a chave de API, o gym id e o ambiente (sandbox ou produção).", "assistente"))
    if checkins_sem_validacao:
        a.append(Alerta("warning", f"{checkins_sem_validacao} check-in(s) de dias anteriores sem validação",
                        "Check-in não validado no Wellhub não entra no repasse.", "relatorio"))
    if configurada and not ativo:
        a.append(Alerta("info", "Integração desligada", "O webhook responde que está desativado e nada é gravado.",
                        "assistente"))
    return a
