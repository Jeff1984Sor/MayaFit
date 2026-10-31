"""Processamento dos eventos do Wellhub (webhook) e validação de check-in (Access Control API).

Fluxo de um evento: grava/acha o `WellhubEvento` pela chave (idempotente) → executa num SAVEPOINT (nada fica pela
metade) → commit → se for pedido de reserva, responde ao Wellhub (PATCH aceitar/rejeitar) → grava a resposta.
Se a resposta ao Wellhub falhar, a reserva aqui já existe e o evento fica "erro": o reprocessar só reenvia a resposta.

Regras de reserva: a vaga é pega com `agenda.criar_reserva` (mesmo bloqueio atômico da agenda). Aula lotada =
reserva REJEITADA no Wellhub com `CLASS_IS_FULL` (resultado "rejeitado", não é erro).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit, segredos
from app.core.db import agora as agora_utc
from app.domain.documentos import validar_cpf
from app.domain.financeiro import hoje_de_negocio
from app.domain.telefone import normalizar_telefone_br
from app.modules.agenda import servico as agenda
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.alunos.models import Aluno, AlunoTelefone, StatusAluno
from app.modules.cadastros.models import proximo_codigo
from app.modules.wellhub import cliente as cli
from app.modules.wellhub import regras as r
from app.modules.wellhub.cliente import ErroWellhub
from app.modules.wellhub.models import (
    WellhubAluno,
    WellhubCheckin,
    WellhubConfig,
    WellhubEvento,
    WellhubReserva,
    WellhubSlot,
)

log = logging.getLogger(__name__)


# ------------------------------------------------------------------------------------------------ segredos
def cifrar(valor: str) -> str:
    return segredos.cifrar_texto(valor.strip()).decode()


def decifrar(valor: str | None) -> str | None:
    if not valor:
        return None
    try:
        return segredos.decifrar_texto(valor.encode())
    except segredos.SegredoInvalido:
        return None


def final_do_segredo(valor_cifrado: str | None) -> str | None:
    v = decifrar(valor_cifrado)
    return v[-4:] if v else None


def cliente_da_config(cfg: WellhubConfig) -> cli.ClienteWellhub:
    """Cliente já com a credencial. Levanta `ErroWellhub` se faltar gym id ou chave."""
    chave = decifrar(cfg.api_key_cifrado)
    if not chave or not cfg.gym_id:
        raise ErroWellhub("Cadastre o gym id e a chave de API do Wellhub.")
    return cli.novo_cliente().configurar(ambiente=cfg.ambiente, api_key=chave, gym_id=cfg.gym_id)


def testar_conexao(cfg: WellhubConfig) -> int:
    """Lista as classes do gym (chamada autenticada e sem efeito). Devolve quantas classes existem."""
    c = cliente_da_config(cfg)
    try:
        return len(c.listar_classes())
    except Exception as exc:  # noqa: BLE001 - traduzido para mensagem segura
        raise cli.traduzir_http(exc) from None
    finally:
        c.fechar()


# ------------------------------------------------------------------------------------------------ alunos
class _Rejeitar(Exception):
    def __init__(self, motivo: str, mensagem: str):
        super().__init__(mensagem)
        self.motivo, self.mensagem = motivo, mensagem


class _Descartar(Exception):
    pass


def aluno_do_gympass(db: Session, gympass: str) -> Aluno | None:
    v = db.scalar(select(WellhubAluno).where(WellhubAluno.gympass_id == gympass)) if gympass else None
    return db.get(Aluno, v.aluno_id) if v else None


def vincular(db: Session, aluno: Aluno, gympass: str, cfg: WellhubConfig) -> None:
    v = db.scalar(select(WellhubAluno).where(WellhubAluno.aluno_id == aluno.id))
    if v is None:
        db.add(WellhubAluno(aluno_id=aluno.id, gympass_id=gympass, config_id=cfg.id))
    else:
        v.config_id = cfg.id
    db.flush()


def achar_ou_criar_aluno(db: Session, cfg: WellhubConfig, payload: dict) -> Aluno:
    """Pelo Gympass ID; senão pelo CPF (se o Wellhub mandar); senão cria (se a configuração permitir)."""
    gympass = r.gympass_id(payload)
    if not gympass:
        raise ErroWellhub("Gympass ID (unique_token) não informado no evento.")
    if not re.fullmatch(r"[0-9A-Za-z-]{4,20}", gympass):
        raise ErroWellhub("Gympass ID inválido no evento.")
    aluno = aluno_do_gympass(db, gympass)
    if aluno:
        return aluno
    cpf = r.documento_do_usuario(payload)
    cpf = cpf if len(cpf) == 11 and validar_cpf(cpf) else ""
    if cpf:
        aluno = db.scalar(select(Aluno).where(Aluno.cpf == cpf))
        if aluno and db.scalar(select(WellhubAluno).where(WellhubAluno.aluno_id == aluno.id)) is None:
            vincular(db, aluno, gympass, cfg)
            audit.registrar(db, usuario=None, acao="wellhub.aluno_vincular", entidade="aluno", entidade_id=aluno.id,
                            descricao=f"Aluno {aluno.nome} vinculado ao Wellhub pelo CPF")
            return aluno
    if not cfg.criar_aluno_automatico:
        raise ErroWellhub("Aluno do Wellhub não encontrado e a criação automática está desligada.")
    u = r.usuario_do_evento(payload)
    email = r._txt(u.get("email"), 200)
    aluno = Aluno(
        nome=r.nome_do_usuario(payload) or "Aluno Wellhub", cpf=cpf or None, sem_cpf=not cpf,
        email=email if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) else None,
        unidade_id=cfg.unidade_id, status=StatusAluno.ATIVO, codigo_legado=proximo_codigo(db, "aluno"),
    )
    db.add(aluno)
    db.flush()
    bruto = r._txt(u.get("phone_number") or u.get("phone"), 30)
    canonico = normalizar_telefone_br(bruto)
    if canonico:
        db.add(AlunoTelefone(aluno_id=aluno.id, ordem=1, numero=canonico, numero_original=bruto))
    vincular(db, aluno, gympass, cfg)
    audit.registrar(db, usuario=None, acao="wellhub.aluno_criar", entidade="aluno", entidade_id=aluno.id,
                    descricao=f"Aluno {aluno.nome} criado automaticamente pelo Wellhub")
    return aluno


# ------------------------------------------------------------------------------------------------ check-ins
def registrar_checkin(db: Session, cfg: WellhubConfig, gympass: str, aluno_id: int | None, quando: datetime, *,
                      origem: str, reserva_id: int | None = None, produto: str | None = None) -> WellhubCheckin:
    """Um check-in por aluno, por dia, por unidade (o Wellhub também conta no máximo um acesso validado por visita)."""
    dia = hoje_de_negocio(quando)
    ck = db.scalar(select(WellhubCheckin).where(WellhubCheckin.config_id == cfg.id, WellhubCheckin.gympass_id == gympass,
                                                WellhubCheckin.dia == dia))
    if ck is None:
        ck = WellhubCheckin(config_id=cfg.id, gympass_id=gympass, dia=dia, ocorrido_em=quando, origem=origem,
                            validado=False)
        db.add(ck)
    ck.aluno_id = aluno_id or ck.aluno_id
    ck.reserva_id = reserva_id or ck.reserva_id
    ck.produto = produto or ck.produto
    db.flush()
    return ck


@dataclass
class ResultadoValidacao:
    """Resposta de `validar_checkin` para o controle de acesso.

    - `aplicavel`: False quando o aluno NÃO é do Wellhub (o controle de acesso segue a regra normal dele).
    - `ok`: True = pode entrar (check-in validado no Wellhub, agora ou antes, hoje).
    """

    aplicavel: bool
    ok: bool
    mensagem: str
    gympass_id: str | None = None
    checkin_id: int | None = None
    ja_validado: bool = False


def _config_do_aluno(db: Session, aluno: Aluno, vinculo: WellhubAluno) -> WellhubConfig | None:
    cfg = db.get(WellhubConfig, vinculo.config_id) if vinculo.config_id else None
    return cfg or db.scalar(select(WellhubConfig).where(WellhubConfig.unidade_id == aluno.unidade_id))


def validar_checkin(db: Session, aluno_id: int, *, agora: datetime | None = None, commit: bool = True) -> ResultadoValidacao:
    """Valida no Wellhub (Access Control `POST /access/v1/validate`) a entrada de hoje do aluno.

    Assinatura estável para o módulo de controle de acesso. Não levanta exceção: devolve `ResultadoValidacao`.
    Idempotente no dia: se já validou hoje, não chama o Wellhub de novo. Faz commit (desligue com `commit=False`).
    """
    agora = agora or agora_utc()
    aluno = db.get(Aluno, aluno_id)
    vinculo = db.scalar(select(WellhubAluno).where(WellhubAluno.aluno_id == aluno_id)) if aluno else None
    if aluno is None or vinculo is None:
        return ResultadoValidacao(False, False, "Aluno não é do Wellhub.")
    g = vinculo.gympass_id
    cfg = _config_do_aluno(db, aluno, vinculo)
    if cfg is None or not cfg.ativo:
        return ResultadoValidacao(True, False, "Integração com o Wellhub desligada ou não configurada nesta unidade.", g)
    hoje = hoje_de_negocio(agora)
    ck = db.scalar(select(WellhubCheckin).where(WellhubCheckin.config_id == cfg.id, WellhubCheckin.gympass_id == g,
                                                WellhubCheckin.dia == hoje))
    if ck is not None and ck.validado:
        return ResultadoValidacao(True, True, "Check-in Wellhub já validado hoje.", g, ck.id, ja_validado=True)
    try:
        c = cliente_da_config(cfg)
    except ErroWellhub as e:
        return ResultadoValidacao(True, False, str(e), g)
    try:
        c.validar_acesso(g)
    except Exception as exc:  # noqa: BLE001
        import httpx

        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (400, 404, 422):
            msg = ("O Wellhub não encontrou check-in deste aluno hoje. Peça para ele fazer o check-in no app do Wellhub "
                   "e tente de novo.")
        else:
            msg = str(cli.traduzir_http(exc, "Validação do check-in"))
        if ck is not None:
            ck.erro_validacao = msg[:300]
        audit.registrar(db, usuario=None, acao="wellhub.checkin_validar", entidade="aluno", entidade_id=aluno.id,
                        descricao=f"Validação de check-in Wellhub recusada ({aluno.nome})")
        if commit:
            db.commit()
        return ResultadoValidacao(True, False, msg, g, ck.id if ck else None)
    finally:
        c.fechar()
    ck = registrar_checkin(db, cfg, g, aluno.id, agora, origem="validacao")
    ck.validado, ck.validado_em, ck.erro_validacao = True, agora, None
    audit.registrar(db, usuario=None, acao="wellhub.checkin_validar", entidade="aluno", entidade_id=aluno.id,
                    descricao=f"Check-in Wellhub validado ({aluno.nome})")
    db.flush()
    cid = ck.id
    if commit:
        db.commit()
    return ResultadoValidacao(True, True, "Check-in Wellhub validado.", g, cid)


# ------------------------------------------------------------------------------------------------ execução
@dataclass
class Resultado:
    evento_id: int
    resultado: str  # processado | cancelado | rejeitado | descartado | erro | duplicado
    reserva_id: int | None = None
    mensagem: str | None = None


def _sessao_do_slot(db: Session, cfg: WellhubConfig, sid: str) -> AulaSessao:
    from app.modules.wellhub.models import WellhubMapeamento

    s = db.scalar(select(WellhubSlot).join(WellhubMapeamento, WellhubMapeamento.id == WellhubSlot.mapeamento_id)
                  .where(WellhubSlot.slot_id == sid, WellhubMapeamento.config_id == cfg.id))
    if s is None or s.aula_sessao_id is None or s.situacao != "publicado":
        raise ErroWellhub(f"O horário (slot {sid or '?'}) não foi publicado por este sistema. Publique a grade e reprocesse.")
    sessao = db.get(AulaSessao, s.aula_sessao_id)
    if sessao is None:
        raise ErroWellhub("A aula deste horário não existe mais na agenda.")
    return sessao


def _reservar(db: Session, cfg: WellhubConfig, payload: dict, ev: WellhubEvento) -> tuple[str, int | None]:
    numero = r.booking_number(payload)
    if not numero:
        raise ErroWellhub("Reserva sem número (booking_number) no evento.")
    wr = db.scalar(select(WellhubReserva).where(WellhubReserva.booking_number == numero))
    if wr is not None and wr.situacao == "reservada" and wr.reserva_id:
        return "processado", wr.reserva_id  # reprocessar: a reserva já existe, só falta (re)enviar a resposta
    if wr is not None and wr.situacao == "rejeitada":
        return "rejeitado", None
    sessao = _sessao_do_slot(db, cfg, r.slot_id(payload))
    aluno = achar_ou_criar_aluno(db, cfg, payload)
    ev.aluno_id = aluno.id
    reserva = db.scalar(select(Reserva).where(Reserva.aluno_id == aluno.id, Reserva.aula_sessao_id == sessao.id))
    try:
        if reserva is None:
            reserva = agenda.criar_reserva(db, aluno.id, sessao.id)
            acao = "wellhub.reserva_criar"
        elif StatusReserva(reserva.status) != StatusReserva.RESERVADA:
            agenda._trocar_status(db, reserva, StatusReserva.RESERVADA)  # pega a vaga (pode falhar por lotação)
            reserva.desmarcada_em = None
            reserva.reposicao_ate = None
            acao = "wellhub.reserva_reativar"
        else:
            acao = None
    except agenda.Conflito as exc:
        if "capacidade" in (exc.dados or {}):
            raise _Rejeitar(cli.MOTIVO_LOTADA, exc.mensagem) from None
        raise
    db.flush()
    if wr is None:
        wr = WellhubReserva(config_id=cfg.id, booking_number=numero)
        db.add(wr)
    wr.slot_id, wr.reserva_id, wr.aluno_id, wr.situacao = r.slot_id(payload), reserva.id, aluno.id, "reservada"
    db.flush()
    if acao:
        audit.registrar(db, usuario=None, acao=acao, entidade="reserva", entidade_id=reserva.id,
                        descricao=f"Reserva do aluno {aluno.id} na aula de {sessao.data:%d/%m/%Y} "
                                  f"{sessao.hora_inicio:%H:%M} (Wellhub)")
    return "processado", reserva.id


def _cancelar(db: Session, cfg: WellhubConfig, payload: dict, *, tardio: bool) -> tuple[str, int | None]:
    numero = r.booking_number(payload)
    if not numero:
        raise ErroWellhub("Cancelamento sem número da reserva (booking_number).")
    wr = db.scalar(select(WellhubReserva).where(WellhubReserva.booking_number == numero))
    if wr is None or wr.reserva_id is None:
        return "cancelado", None  # nada a cancelar (não cria aluno nem aula)
    reserva = db.get(Reserva, wr.reserva_id)
    if reserva is not None and StatusReserva(reserva.status) == StatusReserva.RESERVADA:
        agenda._trocar_status(db, reserva, StatusReserva.CANCELADA)  # libera a vaga; sem reposição (Wellhub)
        reserva.desmarcada_em = agora_utc()
        db.flush()
        audit.registrar(db, usuario=None, acao="wellhub.reserva_cancelar", entidade="reserva", entidade_id=reserva.id,
                        descricao=f"Reserva cancelada pelo Wellhub{' (fora do prazo)' if tardio else ''} "
                                  f"(aluno {reserva.aluno_id})")
    wr.situacao = "cancelada_tarde" if tardio else "cancelada"
    db.flush()
    return "cancelado", wr.reserva_id


def _checkin(db: Session, cfg: WellhubConfig, payload: dict, ev: WellhubEvento, *, de_reserva: bool) -> tuple[str, int | None]:
    quando = r.instante_do_evento(payload, ev.recebido_em)
    reserva_id = None
    if de_reserva:
        numero = r.booking_number(payload)
        wr = db.scalar(select(WellhubReserva).where(WellhubReserva.booking_number == numero)) if numero else None
        if wr is None or wr.reserva_id is None:
            raise ErroWellhub("Check-in de reserva desconhecida (booking_number não encontrado).")
        reserva = db.get(Reserva, wr.reserva_id)
        if reserva is not None and StatusReserva(reserva.status) in (StatusReserva.RESERVADA, StatusReserva.PENDENTE):
            agenda.aplicar_acao_presenca(db, reserva.id, "chegou", agora=quando)
        reserva_id = wr.reserva_id
        aluno = db.get(Aluno, wr.aluno_id) if wr.aluno_id else achar_ou_criar_aluno(db, cfg, payload)
    else:
        aluno = achar_ou_criar_aluno(db, cfg, payload)
    gympass = r.gympass_id(payload) or (db.scalar(select(WellhubAluno.gympass_id).where(WellhubAluno.aluno_id == aluno.id))
                                        if aluno else "")
    if not gympass:
        raise ErroWellhub("Gympass ID (unique_token) não informado no evento.")
    ev.aluno_id = aluno.id if aluno else None
    produto = r._txt(r._d(r._d(r.dados_do_evento(payload).get("gym")).get("product")).get("description"), 150) or None
    registrar_checkin(db, cfg, gympass, ev.aluno_id, quando, origem="reserva" if de_reserva else "webhook",
                      reserva_id=reserva_id, produto=produto)
    return "processado", reserva_id


def _executar(db: Session, cfg: WellhubConfig, payload: dict, ev: WellhubEvento) -> tuple[str, int | None]:
    tipo = r.tipo_do_evento(payload)
    if tipo == r.RESERVA_PEDIDA:
        return _reservar(db, cfg, payload, ev)
    if tipo in (r.RESERVA_CANCELADA, r.RESERVA_CANCELADA_TARDE):
        return _cancelar(db, cfg, payload, tardio=tipo == r.RESERVA_CANCELADA_TARDE)
    if tipo in (r.CHECKIN, r.CHECKIN_RESERVA):
        return _checkin(db, cfg, payload, ev, de_reserva=tipo == r.CHECKIN_RESERVA)
    raise _Descartar(f"Tipo de evento não tratado: {tipo or '(vazio)'}.")


def _responder_reserva(db: Session, cfg: WellhubConfig, numero: str, *, aceitar: bool, motivo: str | None) -> str | None:
    """PATCH no Wellhub. Devolve a mensagem de erro (ou None se deu certo) e grava o que foi enviado."""
    wr = db.scalar(select(WellhubReserva).where(WellhubReserva.booking_number == numero))
    alvo = "reservado" if aceitar else "rejeitado"
    if wr is not None and wr.resposta_enviada == alvo:
        return None
    try:
        c = cliente_da_config(cfg)
    except ErroWellhub as e:
        return f"A resposta ao Wellhub não foi enviada: {e}"
    try:
        c.responder_reserva(numero, aceitar=aceitar, motivo=motivo)
    except Exception as exc:  # noqa: BLE001
        return str(cli.traduzir_http(exc, "A resposta da reserva ao Wellhub falhou"))
    finally:
        c.fechar()
    if wr is None:
        wr = WellhubReserva(config_id=cfg.id, booking_number=numero, situacao="rejeitada")
        db.add(wr)
    wr.resposta_enviada, wr.resposta_em = alvo, agora_utc()
    return None


def processar(db: Session, cfg: WellhubConfig, payload: dict, *, origem: str = "webhook",
              evento: WellhubEvento | None = None) -> Resultado:
    """Grava o evento e processa. Idempotente pela chave do evento. Faz commit."""
    agora = agora_utc()
    chave = r.chave_do_evento(payload)
    ev = evento or db.scalar(select(WellhubEvento).where(WellhubEvento.chave == chave))
    if ev is not None and evento is None and ev.resultado in r.RESULTADOS_FINAIS:
        return Resultado(ev.id, "duplicado", ev.reserva_id, "Evento já processado.")
    if ev is None:
        ev = WellhubEvento(chave=chave, recebido_em=agora, tentativas=0)
        db.add(ev)
    ev.config_id, ev.tipo = cfg.id, r.tipo_do_evento(payload)[:40] or "(vazio)"
    ev.gympass_id, ev.booking_number, ev.slot_id = r.gympass_id(payload) or None, r.booking_number(payload) or None, \
        r.slot_id(payload) or None
    ev.payload, ev.origem, ev.erro, ev.processado_em = payload, origem, None, None
    ev.tentativas = (ev.tentativas or 0) + 1
    db.flush()

    resultado, reserva_id, mensagem, rejeicao = "erro", None, None, None
    try:
        with agenda.savepoint(db):
            resultado, reserva_id = _executar(db, cfg, payload, ev)
    except _Rejeitar as exc:
        resultado, mensagem, rejeicao = "rejeitado", exc.mensagem, exc.motivo
    except _Descartar as exc:
        resultado, mensagem = "descartado", str(exc)
    except ErroWellhub as exc:
        resultado, mensagem = "erro", str(exc)
    except agenda.ErroAgenda as exc:
        resultado, mensagem = "erro", exc.mensagem
    except Exception:  # noqa: BLE001 - o evento fica registrado com erro genérico (sem expor detalhe interno)
        log.exception("Falha inesperada ao processar evento do Wellhub (evento %s)", ev.id)
        resultado, mensagem = "erro", "Falha inesperada ao processar o evento."
    if ev.aluno_id is not None and db.get(Aluno, ev.aluno_id) is None:
        ev.aluno_id = None  # o aluno criado foi desfeito junto com o savepoint
    ev.resultado, ev.erro, ev.reserva_id = resultado, mensagem, reserva_id
    db.flush()

    # resposta ao Wellhub (só pedidos de reserva)
    numero = r.booking_number(payload)
    if ev.tipo == r.RESERVA_PEDIDA and numero and resultado in ("processado", "rejeitado"):
        falha = _responder_reserva(db, cfg, numero, aceitar=resultado == "processado", motivo=rejeicao)
        if falha:
            prefixo = "Reserva feita aqui, mas " if resultado == "processado" else "Aula lotada, mas "
            ev.resultado, ev.erro = "erro", prefixo + falha[0].lower() + falha[1:]
        elif resultado == "rejeitado" and ev.erro:
            ev.erro = f"Recusada no Wellhub ({rejeicao}): {mensagem}"
    if ev.resultado in r.RESULTADOS_FINAIS:
        ev.processado_em = agora_utc()
    db.commit()
    resultado_final = Resultado(ev.id, ev.resultado, ev.reserva_id, ev.erro)
    if ev.tipo == r.CHECKIN and ev.resultado == "processado" and ev.aluno_id and cfg.validar_checkin_automatico:
        validar_checkin(db, ev.aluno_id)  # estúdio sem catraca: valida na chegada do aviso (opção da configuração)
    return resultado_final


def reprocessar(db: Session, ev: WellhubEvento) -> Resultado:
    cfg = db.get(WellhubConfig, ev.config_id) if ev.config_id else None
    if cfg is None:
        raise ErroWellhub("A configuração do Wellhub deste evento não existe mais.")
    payload = ev.payload if isinstance(ev.payload, dict) else {}
    return processar(db, cfg, payload, origem="reprocessar", evento=ev)
