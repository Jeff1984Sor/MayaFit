"""Painel (check-ins do mês, valor estimado de repasse, alertas, passos do assistente) e relatório mensal de check-ins."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.db import agora as agora_utc
from app.domain.financeiro import hoje_de_negocio
from app.modules.agenda.models import AulaSessao
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import Unidade
from app.modules.wellhub import regras as r
from app.modules.wellhub.models import (
    WellhubCheckin,
    WellhubConfig,
    WellhubEvento,
    WellhubMapeamento,
    WellhubReserva,
    WellhubSlot,
)


def intervalo_do_mes(ano: int, mes: int) -> tuple[date, date]:
    inicio = date(ano, mes, 1)
    fim = date(ano + (mes == 12), mes % 12 + 1, 1)
    return inicio, fim


def mes_anterior(ano: int, mes: int) -> tuple[int, int]:
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def _inicio_utc(d: date) -> datetime:
    from app.domain.status_aula import momento_da_sessao

    return momento_da_sessao(d, datetime.min.time())


def estado(db: Session, cfg: WellhubConfig | None) -> r.EstadoConfig:
    if cfg is None:
        return r.EstadoConfig()
    maps = list(db.scalars(select(WellhubMapeamento).where(WellhubMapeamento.config_id == cfg.id,
                                                           WellhubMapeamento.ativo.is_(True))))
    slots = db.scalar(select(func.count()).select_from(WellhubSlot).join(
        WellhubMapeamento, WellhubMapeamento.id == WellhubSlot.mapeamento_id).where(
        WellhubMapeamento.config_id == cfg.id, WellhubSlot.situacao == "publicado")) or 0
    return r.EstadoConfig(
        existe=True, ativo=cfg.ativo, gym_id=bool(cfg.gym_id), api_key=bool(cfg.api_key_cifrado),
        webhook_secret=bool(cfg.webhook_secret_cifrado), teste_ok=cfg.teste_ultimo_ok,
        mapeamentos_com_produto=sum(1 for m in maps if m.product_id), mapeamentos_publicados=sum(1 for m in maps if m.class_id),
        sync_ok=cfg.sync_ultimo_ok, slots_publicados=slots,
        valor_repasse=cfg.valor_repasse_checkin is not None and cfg.valor_repasse_checkin > 0,
    )


def _contar_checkins(db: Session, config_ids: list[int], inicio: date, fim: date) -> tuple[int, int]:
    if not config_ids:
        return 0, 0
    base = select(func.count()).select_from(WellhubCheckin).where(
        WellhubCheckin.config_id.in_(config_ids), WellhubCheckin.dia >= inicio, WellhubCheckin.dia < fim)
    total = db.scalar(base) or 0
    validados = db.scalar(base.where(WellhubCheckin.validado.is_(True))) or 0
    return total, validados


def painel(db: Session, cfg: WellhubConfig | None, *, agora: datetime | None = None) -> dict:
    agora = agora or agora_utc()
    hoje = hoje_de_negocio(agora)
    inicio, fim = intervalo_do_mes(hoje.year, hoje.month)
    ia, ib = intervalo_do_mes(*mes_anterior(hoje.year, hoje.month))
    ids = [cfg.id] if cfg else []
    total, validados = _contar_checkins(db, ids, inicio, fim)
    _, validados_ant = _contar_checkins(db, ids, ia, ib)
    valor = r.valor_estimado(validados, cfg.valor_repasse_checkin if cfg else None)
    e = estado(db, cfg)

    def contar(modelo, *cond):
        return (db.scalar(select(func.count()).select_from(modelo).where(*cond)) or 0) if cfg else 0

    desde_mes = _inicio_utc(inicio)
    reservas = contar(WellhubReserva, WellhubReserva.config_id == (cfg.id if cfg else 0), WellhubReserva.criado_em >= desde_mes,
                      WellhubReserva.situacao != "rejeitada")
    rejeitadas = contar(WellhubReserva, WellhubReserva.config_id == (cfg.id if cfg else 0), WellhubReserva.criado_em >= desde_mes,
                        WellhubReserva.situacao == "rejeitada")
    cancel = contar(WellhubReserva, WellhubReserva.config_id == (cfg.id if cfg else 0), WellhubReserva.criado_em >= desde_mes,
                    WellhubReserva.situacao.in_(("cancelada", "cancelada_tarde")))
    erros = contar(WellhubEvento, WellhubEvento.config_id == (cfg.id if cfg else 0), WellhubEvento.resultado == "erro",
                   WellhubEvento.ignorado.is_(False))
    sem_resposta = contar(WellhubEvento, WellhubEvento.config_id == (cfg.id if cfg else 0), WellhubEvento.resultado == "erro",
                          WellhubEvento.ignorado.is_(False), WellhubEvento.tipo == r.RESERVA_PEDIDA,
                          WellhubEvento.recebido_em >= agora - timedelta(minutes=15))
    pendentes_antigos = contar(WellhubCheckin, WellhubCheckin.config_id == (cfg.id if cfg else 0),
                               WellhubCheckin.validado.is_(False), WellhubCheckin.dia < hoje, WellhubCheckin.dia >= inicio)
    slots_futuros = 0
    if cfg:
        slots_futuros = db.scalar(select(func.count()).select_from(WellhubSlot)
                                  .join(WellhubMapeamento, WellhubMapeamento.id == WellhubSlot.mapeamento_id)
                                  .join(AulaSessao, AulaSessao.id == WellhubSlot.aula_sessao_id)
                                  .where(WellhubMapeamento.config_id == cfg.id, WellhubSlot.situacao == "publicado",
                                         AulaSessao.data >= hoje)) or 0
    falhas_24h = cfg.falhas_assinatura if cfg and cfg.falha_assinatura_em and cfg.falha_assinatura_em >= agora - timedelta(
        hours=24) else 0
    alertas = r.montar_alertas(
        ativo=bool(cfg and cfg.ativo), configurada=cfg is not None, eventos_com_erro=erros, falhas_assinatura_24h=falhas_24h,
        sync_ok=cfg.sync_ultimo_ok if cfg else None, sync_resumo=cfg.sync_ultimo_resumo if cfg else None,
        teste_ok=cfg.teste_ultimo_ok if cfg else None, checkins_sem_validacao=pendentes_antigos,
        reservas_sem_resposta=sem_resposta)
    serie = []
    if cfg:
        linhas = db.execute(select(WellhubCheckin.dia, func.count(), func.sum(case((WellhubCheckin.validado.is_(True), 1), else_=0)))
                            .where(WellhubCheckin.config_id == cfg.id, WellhubCheckin.dia >= inicio, WellhubCheckin.dia < fim)
                            .group_by(WellhubCheckin.dia)).all()
        por_dia = {d: (int(t or 0), int(v or 0)) for d, t, v in linhas}
        d = inicio
        while d <= hoje and d < fim:
            t, v = por_dia.get(d, (0, 0))
            serie.append({"dia": d, "total": t, "validados": v})
            d += timedelta(days=1)
    return {
        "mes": f"{hoje:%Y-%m}",
        "checkins_mes": total, "checkins_validados_mes": validados, "checkins_pendentes_mes": total - validados,
        "variacao_checkins": r.variacao(validados, validados_ant), "valor_repasse_checkin": cfg.valor_repasse_checkin if cfg else None,
        "valor_estimado_mes": valor, "reservas_mes": reservas, "rejeitadas_mes": rejeitadas, "cancelamentos_mes": cancel,
        "eventos_com_erro": erros, "slots_futuros": slots_futuros,
        "passos": [p.__dict__ for p in r.passos_do_assistente(e)],
        "alertas": [a.__dict__ for a in alertas], "serie": serie,
    }


def relatorio_mensal(db: Session, *, ano: int, mes: int, unidade_id: int | None = None) -> dict:
    inicio, fim = intervalo_do_mes(ano, mes)
    q = select(WellhubConfig)
    if unidade_id:
        q = q.where(WellhubConfig.unidade_id == unidade_id)
    configs = list(db.scalars(q))
    ids = [c.id for c in configs]
    nomes_un = {u.id: u.nome for u in db.scalars(select(Unidade))}
    linhas = list(db.scalars(select(WellhubCheckin).where(WellhubCheckin.config_id.in_(ids or [0]), WellhubCheckin.dia >= inicio,
                                                          WellhubCheckin.dia < fim)
                             .order_by(WellhubCheckin.dia, WellhubCheckin.ocorrido_em, WellhubCheckin.id)))
    alunos = {a.id: a.nome for a in db.scalars(select(Aluno).where(Aluno.id.in_({c.aluno_id for c in linhas if c.aluno_id} or {0})))}
    por_cfg = {c.id: c for c in configs}
    por_unidade: dict[int, dict] = {}
    por_aluno: dict[str, dict] = {}
    por_dia: dict[date, dict] = {}
    for ck in linhas:
        cfg = por_cfg[ck.config_id]
        u = por_unidade.setdefault(cfg.unidade_id, {"unidade_id": cfg.unidade_id, "unidade_nome": nomes_un.get(cfg.unidade_id, "?"),
                                                    "total": 0, "validados": 0, "valor_unitario": cfg.valor_repasse_checkin,
                                                    "valor_estimado": Decimal("0.00")})
        u["total"] += 1
        a = por_aluno.setdefault(ck.gympass_id, {"aluno_id": ck.aluno_id, "aluno_nome": alunos.get(ck.aluno_id, "Aluno não identificado"),
                                                 "gympass_id": r.mascarar_gympass(ck.gympass_id), "total": 0, "validados": 0,
                                                 "ultimo": ck.dia})
        a["total"] += 1
        a["ultimo"] = max(a["ultimo"], ck.dia)
        dd = por_dia.setdefault(ck.dia, {"dia": ck.dia, "total": 0, "validados": 0})
        dd["total"] += 1
        if ck.validado:
            u["validados"] += 1
            a["validados"] += 1
            dd["validados"] += 1
    for u in por_unidade.values():
        u["valor_estimado"] = r.valor_estimado(u["validados"], u["valor_unitario"])
    total = len(linhas)
    validados = sum(1 for c in linhas if c.validado)
    pa, pm = mes_anterior(ano, mes)
    _, validados_ant = _contar_checkins(db, ids, *intervalo_do_mes(pa, pm))
    return {
        "ano": ano, "mes": mes, "total": total, "validados": validados, "pendentes": total - validados,
        "valor_estimado": sum((u["valor_estimado"] for u in por_unidade.values()), Decimal("0.00")),
        "validados_mes_anterior": validados_ant, "variacao": r.variacao(validados, validados_ant),
        "alunos_distintos": len(por_aluno),
        "por_unidade": sorted(por_unidade.values(), key=lambda x: x["unidade_nome"]),
        "por_dia": sorted(por_dia.values(), key=lambda x: x["dia"]),
        "por_aluno": sorted(por_aluno.values(), key=lambda x: (-x["validados"], -x["total"], x["aluno_nome"])),
    }


def relatorio_csv(db: Session, *, ano: int, mes: int, unidade_id: int | None = None) -> str:
    """Uma linha por check-in, com o Gympass ID completo (para conferir com o extrato de repasse do Wellhub)."""
    inicio, fim = intervalo_do_mes(ano, mes)
    q = select(WellhubConfig)
    if unidade_id:
        q = q.where(WellhubConfig.unidade_id == unidade_id)
    configs = {c.id: c for c in db.scalars(q)}
    nomes_un = {u.id: u.nome for u in db.scalars(select(Unidade))}
    linhas = list(db.scalars(select(WellhubCheckin).where(WellhubCheckin.config_id.in_(list(configs) or [0]),
                                                          WellhubCheckin.dia >= inicio, WellhubCheckin.dia < fim)
                             .order_by(WellhubCheckin.dia, WellhubCheckin.id)))
    alunos = {a.id: a.nome for a in db.scalars(select(Aluno).where(Aluno.id.in_({c.aluno_id for c in linhas if c.aluno_id} or {0})))}
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["data", "unidade", "aluno", "gympass_id", "origem", "validado", "validado_em", "valor_estimado"])
    for ck in linhas:
        cfg = configs[ck.config_id]
        valor = cfg.valor_repasse_checkin if ck.validado and cfg.valor_repasse_checkin else Decimal("0.00")
        w.writerow([f"{ck.dia:%d/%m/%Y}", nomes_un.get(cfg.unidade_id, ""), _seguro(alunos.get(ck.aluno_id, "")), ck.gympass_id,
                    ck.origem, "sim" if ck.validado else "não",
                    ck.validado_em.astimezone(_fuso()).strftime("%d/%m/%Y %H:%M") if ck.validado_em else "",
                    f"{valor:.2f}".replace(".", ",")])
    return "﻿" + buf.getvalue()


def _seguro(texto: str) -> str:
    """Evita injeção de fórmula ao abrir o CSV numa planilha."""
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") else texto


def _fuso():
    from zoneinfo import ZoneInfo

    return ZoneInfo("America/Sao_Paulo")
