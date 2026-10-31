"""Serviço do app do aluno (PWA, R15).

Segurança (o app antigo não tinha nada disto):
- código de 6 dígitos (``secrets``), validade de 10 min, UM por vez (pedir outro invalida o anterior), uso único (marcado
  por UPDATE condicional, então duas verificações simultâneas não passam as duas), no máximo ``MAX_TENTATIVAS`` erros por
  código, só o hash vai ao banco e a comparação é em tempo constante;
- a resposta ao pedido de código é SEMPRE a mesma (CPF inexistente, aluno inativo, sem telefone, telefone inválido ou envio
  que falhou): ninguém descobre quem é aluno;
- JWT próprio do aluno: ``typ`` e ``aud`` distintos dos da equipe (um não serve no outro), access de 12 h, refresh de 7 dias.

A agenda continua sendo a dona das regras (``agenda.servico``): aqui só se confere que a reserva é do aluno e se traduz o erro.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import tenancy
from app.core.config import settings
from app.core.db import agora as agora_utc
from app.core.estudio_http import definir_pelo_token
from app.core.security import hash_token
from app.domain import documentos, status_aula
from app.domain.financeiro import hoje_de_negocio
from app.domain.telefone import normalizar_telefone_br
from app.modules.agenda import servico as agenda
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.alunos.models import Aluno, AlunoTelefone, AppCodigo, StatusAluno
from app.modules.cadastros.models import Profissional, TipoServico, Unidade

# --- parâmetros (constantes do módulo; testes podem sobrescrever) ---
CODIGO_MINUTOS = 10
MAX_TENTATIVAS = 5  # erros por código; ao chegar, o código morre e é preciso pedir outro
ACCESS_HORAS = 12
REFRESH_DIAS = 7
AUDIENCIA = "mayafit-aluno"
TIPO_ACCESS = "aluno_access"
TIPO_REFRESH = "aluno_refresh"

MENSAGEM_PEDIDO = "Se o CPF estiver cadastrado, enviaremos um código por WhatsApp para o telefone do cadastro."
ERRO_CODIGO = "Código inválido ou expirado. Peça um novo código."


class ErroAluno(Exception):
    """Erro de regra com mensagem pronta; ``status`` é o HTTP sugerido."""

    status = 400

    def __init__(self, mensagem: str, *, dados: dict | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.dados = dados or {}


class NaoAutenticado(ErroAluno):
    status = 401


class NaoEncontrado(ErroAluno):
    status = 404


class Conflito(ErroAluno):
    status = 409


class Invalido(ErroAluno):
    status = 422


# ------------------------------------------------------------------------------------------------------------ login
def _hash_codigo(aluno_id: int, codigo: str) -> str:
    return hash_token(f"app-aluno:{aluno_id}:{codigo}")


def achar_aluno_por_cpf(db: Session, cpf_bruto: str) -> Aluno | None:
    """Aluno ATIVO com esse CPF (com ou sem máscara). Marcador ``SEM_CPF`` nunca casa (R16)."""
    digitos = documentos.so_digitos(cpf_bruto)
    if len(digitos) != 11:
        return None
    return db.scalar(select(Aluno).where(Aluno.cpf == digitos, Aluno.sem_cpf.is_(False), Aluno.status == StatusAluno.ATIVO))


def telefone_do_aluno(db: Session, aluno_id: int) -> str | None:
    """Primeiro telefone (por ordem) que dá para enviar WhatsApp (normalizado, 55+DDD+número)."""
    numeros = db.scalars(
        select(AlunoTelefone.numero).where(AlunoTelefone.aluno_id == aluno_id).order_by(AlunoTelefone.ordem, AlunoTelefone.id)
    )
    for n in numeros:
        norm = normalizar_telefone_br(n)
        if norm:
            return norm
    return None


@dataclass
class Envio:
    telefone: str
    texto: str


def pedir_codigo(db: Session, cpf_bruto: str, *, agora: datetime | None = None) -> Envio | None:
    """Gera o código e devolve o ``Envio`` a fazer (quem chama manda DEPOIS de responder, para o tempo de resposta
    não revelar nada). Devolve ``None`` quando não há o que enviar; a resposta HTTP é a mesma nos dois casos.
    Faz ``commit``."""
    momento = agora or agora_utc()
    aluno = achar_aluno_por_cpf(db, cpf_bruto)
    telefone = telefone_do_aluno(db, aluno.id) if aluno else None
    if aluno is None or telefone is None:
        _hash_codigo(0, "000000")  # custo parecido com o caminho feliz
        return None
    # invalida os códigos anteriores ainda abertos
    db.execute(update(AppCodigo).where(AppCodigo.aluno_id == aluno.id, AppCodigo.usado.is_(False)).values(usado=True))
    codigo = f"{secrets.randbelow(10**6):06d}"
    db.add(
        AppCodigo(
            aluno_id=aluno.id,
            codigo_hash=_hash_codigo(aluno.id, codigo),
            expira_em=momento + timedelta(minutes=CODIGO_MINUTOS),
            usado=False,
            tentativas=0,
            criado_em=momento,
        )
    )
    db.commit()
    primeiro = aluno.nome.split()[0] if aluno.nome else ""
    texto = (
        f"Olá, {primeiro}! Seu código de acesso ao app é {codigo}. Vale por {CODIGO_MINUTOS} minutos. "
        "Não compartilhe com ninguém."
    )
    return Envio(telefone, texto)


def _emitir(aluno_id: int, tipo: str, validade: timedelta, agora: datetime) -> str:
    payload = {
        "sub": str(aluno_id),
        "typ": tipo,
        "aud": AUDIENCIA,
        "iat": agora,
        "exp": agora + validade,
        "jti": secrets.token_hex(16),
        **tenancy.claims(),  # um banco por estúdio: o token do aluno só vale no estúdio dele (claim `est`)
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def emitir_tokens(aluno_id: int, *, agora: datetime | None = None) -> dict[str, Any]:
    t = agora or datetime.now(UTC)
    return {
        "access_token": _emitir(aluno_id, TIPO_ACCESS, timedelta(hours=ACCESS_HORAS), t),
        "refresh_token": _emitir(aluno_id, TIPO_REFRESH, timedelta(days=REFRESH_DIAS), t),
        "expira_em_segundos": ACCESS_HORAS * 3600,
    }


def decodificar(token: str, tipo: str) -> int:
    """Valida assinatura, expiração, audiência e tipo; devolve o id do aluno. Levanta ``NaoAutenticado``."""
    try:
        p = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=AUDIENCIA,
            options={"require": ["exp", "sub", "typ", "aud", "jti"]},
        )
        if p.get("typ") != tipo:
            raise jwt.InvalidTokenError("tipo")
        if not tenancy.token_do_estudio_atual(p):
            raise jwt.InvalidTokenError("estúdio")
        return int(p["sub"])
    except (jwt.PyJWTError, ValueError):
        raise NaoAutenticado("Sessão expirada. Entre novamente.") from None


def verificar_codigo(db: Session, cpf_bruto: str, codigo_bruto: str, *, agora: datetime | None = None) -> Aluno:
    """Confere o código. Todo erro tem a mesma mensagem. Faz ``commit`` (tentativas e uso precisam persistir)."""
    momento = agora or agora_utc()
    codigo = documentos.so_digitos(codigo_bruto)
    aluno = achar_aluno_por_cpf(db, cpf_bruto)
    linha = None
    if aluno is not None:
        linha = db.scalar(
            select(AppCodigo)
            .where(AppCodigo.aluno_id == aluno.id, AppCodigo.usado.is_(False))
            .order_by(AppCodigo.id.desc())
            .limit(1)
        )
    if aluno is None or linha is None:
        _hash_codigo(0, codigo)
        raise NaoAutenticado(ERRO_CODIGO)
    if linha.expira_em <= momento or linha.tentativas >= MAX_TENTATIVAS:
        db.execute(update(AppCodigo).where(AppCodigo.id == linha.id).values(usado=True))
        db.commit()
        raise NaoAutenticado(ERRO_CODIGO)
    certo = hmac.compare_digest(linha.codigo_hash, _hash_codigo(aluno.id, codigo))
    if not certo:
        tentativas = linha.tentativas + 1
        db.execute(
            update(AppCodigo).where(AppCodigo.id == linha.id).values(tentativas=tentativas, usado=tentativas >= MAX_TENTATIVAS)
        )
        db.commit()
        raise NaoAutenticado(ERRO_CODIGO)
    # uso único: só uma verificação consegue virar o `usado`
    r = db.execute(update(AppCodigo).where(AppCodigo.id == linha.id, AppCodigo.usado.is_(False)).values(usado=True))
    db.commit()
    if r.rowcount != 1:
        raise NaoAutenticado(ERRO_CODIGO)
    return aluno


def aluno_do_token(db: Session, token: str, tipo: str = TIPO_ACCESS) -> Aluno:
    definir_pelo_token(token)  # refresh chega no corpo: o estúdio vem do próprio token (um banco por estúdio)
    aluno = db.get(Aluno, decodificar(token, tipo))
    if aluno is None or StatusAluno(aluno.status) != StatusAluno.ATIVO:
        raise NaoAutenticado("Sessão expirada. Entre novamente.")
    return aluno


# ---------------------------------------------------------------------------------------------------------- consulta
def _agora(agora: datetime | None) -> datetime:
    return agora or agora_utc()


def _nome_prof(db: Session, profissional_id: int | None) -> str | None:
    p = db.get(Profissional, profissional_id) if profissional_id else None
    return p.nome if p else None


def _nome_servico(db: Session, tipo_id: int) -> str | None:
    t = db.get(TipoServico, tipo_id)
    return t.nome if t else None


def me(db: Session, aluno: Aluno) -> dict:
    un = db.get(Unidade, aluno.unidade_id)
    return {"nome": aluno.nome, "primeiro_nome": aluno.nome.split()[0] if aluno.nome else "", "unidade": un.nome if un else None}


_ABERTAS = (StatusReserva.RESERVADA, StatusReserva.PENDENTE)


def _aula_dict(db: Session, r: Reserva, s: AulaSessao, momento: datetime) -> dict:
    status = StatusReserva(r.status)
    hoje = hoje_de_negocio(momento)
    aberta = status in _ABERTAS and s.data >= hoje
    fim = status_aula.momento_da_sessao(s.data, s.hora_fim)
    inicio = status_aula.momento_da_sessao(s.data, s.hora_inicio)
    un = db.get(Unidade, s.unidade_id)
    no_prazo = agenda.prazo_de_desmarcar_cumprido(s, momento)
    limite = agenda.limite_para_desmarcar(s)
    return {
        "id": r.id,
        "data": s.data,
        "hora_inicio": s.hora_inicio,
        "hora_fim": s.hora_fim,
        "servico": _nome_servico(db, s.tipo_servico_id),
        "profissional": _nome_prof(db, s.profissional_id),
        "unidade": un.nome if un else None,
        "status": status_aula.status_exibido(status.value, inicio, fim, momento),
        "confirmada": r.confirmada_em is not None,
        "confirmada_em": r.confirmada_em,
        "pode_confirmar": aberta and r.confirmada_em is None,
        "pode_desmarcar": aberta and no_prazo,
        # regra das 6 horas: até quando o aluno pode desmarcar (None se a aula não é desmarcável)
        "desmarcar_ate": f"{limite:%d/%m} às {limite:%H:%M}" if aberta else None,
    }


def listar_aulas(db: Session, aluno: Aluno, *, agora: datetime | None = None, limite: int = 60) -> list[dict]:
    """Aulas futuras do PRÓPRIO aluno, exceto CANCELADA (essas aparecem em Reposições)."""
    momento = _agora(agora)
    hoje = hoje_de_negocio(momento)
    linhas = db.execute(
        select(Reserva, AulaSessao)
        .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
        .where(Reserva.aluno_id == aluno.id, AulaSessao.data >= hoje, Reserva.status != StatusReserva.CANCELADA)
        .order_by(AulaSessao.data, AulaSessao.hora_inicio, Reserva.id)
        .limit(limite)
    ).all()
    return [_aula_dict(db, r, s, momento) for r, s in linhas]


def _reserva_do_aluno(db: Session, aluno: Aluno, reserva_id: int) -> tuple[Reserva, AulaSessao]:
    """Id alheio ou inexistente: 404 igual (não revela que existe)."""
    r = db.get(Reserva, reserva_id)
    if r is None or r.aluno_id != aluno.id:
        raise NaoEncontrado("Aula não encontrada.")
    return r, db.get(AulaSessao, r.aula_sessao_id)


def _exigir_aberta(r: Reserva, acao: str) -> None:
    """Aluno só mexe em aula ainda por acontecer. (CANCELADA segue para o domínio, que responde "já desmarcada".)"""
    st = StatusReserva(r.status)
    if st not in _ABERTAS and st != StatusReserva.CANCELADA:
        raise Conflito(f"Esta aula não pode ser {acao}.")


def confirmar(db: Session, aluno: Aluno, reserva_id: int, *, agora: datetime | None = None) -> dict:
    r, _ = _reserva_do_aluno(db, aluno, reserva_id)
    _exigir_aberta(r, "confirmada")
    try:
        r = agenda.confirmar_reserva(db, reserva_id, aluno_id=aluno.id, agora=agora)
    except agenda.ErroAgenda as e:
        raise _traduzir(e) from e
    s = db.get(AulaSessao, r.aula_sessao_id)
    return _aula_dict(db, r, s, _agora(agora))


def desmarcar(db: Session, aluno: Aluno, reserva_id: int, *, agora: datetime | None = None) -> dict:
    r, _ = _reserva_do_aluno(db, aluno, reserva_id)
    _exigir_aberta(r, "desmarcada")
    try:
        r = agenda.desmarcar_reserva_do_aluno(db, aluno.id, reserva_id, agora=agora)
    except agenda.ErroAgenda as e:
        raise _traduzir(e) from e
    return {
        "mensagem": f"Aula desmarcada. Você pode repor até {r.reposicao_ate:%d/%m/%Y} (30 dias).",
        "reposicao_ate": r.reposicao_ate,
    }


def _traduzir(e: agenda.ErroAgenda) -> ErroAluno:
    if isinstance(e, agenda.NaoEncontrado):
        return NaoEncontrado("Aula não encontrada.")
    if isinstance(e, agenda.Conflito):
        return Conflito(e.mensagem, dados=e.dados)
    return ErroAluno(e.mensagem)


