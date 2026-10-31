"""Publicação da grade no Wellhub: serviço mapeado → classe; aula (sessão) dos próximos N dias → slot com vagas.

`sincronizar_grade(db, cfg, previa=True)` não chama a rede: devolve o que SERIA feito (usado no "Testar" do passo
da grade). Vagas publicadas = capacidade efetiva da aula e reservas ativas (TODAS, não só as do Wellhub), para o
Wellhub nunca vender vaga que o estúdio já ocupou.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import agora as agora_utc
from app.domain.financeiro import hoje_de_negocio
from app.domain.status_aula import momento_da_sessao
from app.modules.agenda import servico as agenda
from app.modules.agenda.models import AulaSessao
from app.modules.cadastros.models import Profissional, TipoServico
from app.modules.wellhub import cliente as cli
from app.modules.wellhub import regras as r
from app.modules.wellhub.cliente import ErroWellhub
from app.modules.wellhub.eventos import cliente_da_config
from app.modules.wellhub.models import WellhubConfig, WellhubMapeamento, WellhubSlot

log = logging.getLogger(__name__)
HORAS_CANCELAMENTO = 6  # mesma regra de aviso da agenda (decisão de 25/10/2026). A CONFIRMAR se o Wellhub aceita.
MAX_MENSAGENS = 8


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _produto(valor: str | None):
    return int(valor) if valor and valor.isdigit() else valor


def dados_da_classe(m: WellhubMapeamento, servico: TipoServico) -> dict:
    return {"name": (m.nome_classe or servico.nome)[:150], "description": m.descricao or "", "notes": "",
            "bookable": True, "visible": True, "product_id": _produto(m.product_id), "reference": f"mayafit-{servico.id}"}


def dados_do_slot(db: Session, m: WellhubMapeamento, sessao: AulaSessao, vagas: r.Vagas, agora: datetime) -> dict:
    inicio = momento_da_sessao(sessao.data, sessao.hora_inicio)
    fim = momento_da_sessao(sessao.data, sessao.hora_fim)
    instrutores = []
    if sessao.profissional_id:
        p = db.get(Profissional, sessao.profissional_id)
        if p:
            instrutores.append({"name": p.nome[:100], "substitute": False})
    return {
        "occur_date": _iso(inicio), "length_in_minutes": max(int((fim - inicio).total_seconds() // 60), 1),
        "total_capacity": vagas.capacidade, "total_booked": vagas.reservadas, "product_id": _produto(m.product_id),
        "booking_window": {"opens_at": _iso(agora), "closes_at": _iso(inicio)},
        "cancellable_until": _iso(inicio - timedelta(hours=HORAS_CANCELAMENTO)),
        "instructors": instrutores, "virtual": False,
    }


def _novo_resumo(previa: bool) -> dict:
    return {"previa": previa, "classes_criadas": 0, "slots_criados": 0, "slots_atualizados": 0, "slots_removidos": 0,
            "sem_mudanca": 0, "erros": 0, "mensagens": []}


def _erro(resumo: dict, msg: str) -> None:
    resumo["erros"] += 1
    if len(resumo["mensagens"]) < MAX_MENSAGENS:
        resumo["mensagens"].append(msg)


def _credencial_recusada(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403)


def sincronizar_grade(db: Session, cfg: WellhubConfig, *, previa: bool = False, hoje: date | None = None,
                      agora: datetime | None = None) -> dict:
    """Publica classes e slots. Erros por item entram no resumo; credencial recusada interrompe (`ErroWellhub`)."""
    agora = agora or agora_utc()
    hoje = hoje or hoje_de_negocio(agora)
    ate = hoje + timedelta(days=max(int(cfg.sync_dias or 7), 1) - 1)
    resumo = _novo_resumo(previa)
    mapeamentos = list(db.scalars(select(WellhubMapeamento).where(WellhubMapeamento.config_id == cfg.id,
                                                                    WellhubMapeamento.ativo.is_(True))
                                  .order_by(WellhubMapeamento.id)))
    if not mapeamentos:
        raise ErroWellhub("Nenhum serviço ligado a um produto do Wellhub. Faça o mapeamento antes de publicar.")
    c = None if previa else cliente_da_config(cfg)
    try:
        for m in mapeamentos:
            servico = db.get(TipoServico, m.tipo_servico_id)
            if servico is None:
                continue
            if not m.product_id:
                _erro(resumo, f"{servico.nome}: informe o produto do Wellhub.")
                continue
            if not m.class_id:
                if previa:
                    resumo["classes_criadas"] += 1
                else:
                    try:
                        m.class_id = c.criar_classe(dados_da_classe(m, servico))
                        db.commit()
                        resumo["classes_criadas"] += 1
                    except Exception as exc:  # noqa: BLE001
                        if _credencial_recusada(exc):
                            raise
                        _erro(resumo, str(cli.traduzir_http(exc, f"{servico.nome} (classe)")))
                        continue
            elif not previa and cfg.sync_ultimo_em and m.atualizado_em and m.atualizado_em > cfg.sync_ultimo_em:
                try:  # mapeamento alterado depois da última publicação: atualiza nome/produto da classe
                    c.atualizar_classe(m.class_id, dados_da_classe(m, servico))
                except Exception as exc:  # noqa: BLE001
                    if _credencial_recusada(exc):
                        raise
                    _erro(resumo, str(cli.traduzir_http(exc, f"{servico.nome} (atualizar classe)")))
            _publicar_sessoes(db, c, m, servico, hoje, ate, agora, resumo, previa)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise cli.traduzir_http(exc, "Publicação da grade") from None
    finally:
        if c is not None:
            c.fechar()
    return resumo


def _publicar_sessoes(db, c, m: WellhubMapeamento, servico: TipoServico, hoje: date, ate: date, agora: datetime,
                      resumo: dict, previa: bool) -> None:
    unidade_id = db.get(WellhubConfig, m.config_id).unidade_id
    sessoes = list(db.scalars(select(AulaSessao).where(
        AulaSessao.unidade_id == unidade_id, AulaSessao.tipo_servico_id == m.tipo_servico_id,
        AulaSessao.data >= hoje, AulaSessao.data <= ate).order_by(AulaSessao.data, AulaSessao.hora_inicio)))
    futuras = {s.id: s for s in sessoes if momento_da_sessao(s.data, s.hora_inicio) > agora}
    todos = list(db.scalars(select(WellhubSlot).where(WellhubSlot.mapeamento_id == m.id,
                                                      WellhubSlot.situacao == "publicado").order_by(WellhubSlot.id)))
    publicados = {p.aula_sessao_id: p for p in todos if p.aula_sessao_id is not None}
    for sid, sessao in futuras.items():
        atual = r.vagas_para_publicar(agenda.capacidade_da_sessao(db, sessao), sessao.reservas_ativas)
        pub = publicados.get(sid)
        antes = r.Vagas(pub.capacidade_publicada, pub.reservadas_publicadas) if pub else None
        acao = r.acao_do_slot(antes, atual)
        quando = f"{servico.nome} {sessao.data:%d/%m} {sessao.hora_inicio:%H:%M}"
        if acao == "manter":
            resumo["sem_mudanca"] += 1
            continue
        if previa:
            resumo["slots_criados" if acao == "criar" else "slots_atualizados"] += 1
            continue
        try:
            if acao == "criar":
                novo = c.criar_slot(m.class_id, dados_do_slot(db, m, sessao, atual, agora))
                db.add(WellhubSlot(mapeamento_id=m.id, aula_sessao_id=sessao.id, slot_id=novo, situacao="publicado",
                                   capacidade_publicada=atual.capacidade, reservadas_publicadas=atual.reservadas,
                                   publicado_em=agora_utc()))
                resumo["slots_criados"] += 1
            else:
                c.atualizar_vagas(m.class_id, pub.slot_id, atual.capacidade, atual.reservadas)
                pub.capacidade_publicada, pub.reservadas_publicadas, pub.publicado_em = \
                    atual.capacidade, atual.reservadas, agora_utc()
                resumo["slots_atualizados"] += 1
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            if _credencial_recusada(exc):
                raise
            _erro(resumo, str(cli.traduzir_http(exc, quando)))
    # horários publicados cuja aula foi excluída ou mudou de serviço/unidade: sai do Wellhub
    for pub in todos:
        if pub.aula_sessao_id in futuras:
            continue
        sessao = db.get(AulaSessao, pub.aula_sessao_id) if pub.aula_sessao_id else None
        if sessao is not None:
            if momento_da_sessao(sessao.data, sessao.hora_inicio) <= agora or sessao.data > ate:
                continue  # já passou (fica como histórico) ou está além da janela
            if sessao.tipo_servico_id == m.tipo_servico_id and sessao.unidade_id == unidade_id:
                continue
        if previa:
            resumo["slots_removidos"] += 1
            continue
        try:
            c.remover_slot(m.class_id, pub.slot_id)
            pub.situacao, pub.aula_sessao_id = "removido", None  # libera a aula para outro mapeamento
            db.commit()
            resumo["slots_removidos"] += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            if _credencial_recusada(exc):
                raise
            _erro(resumo, str(cli.traduzir_http(exc, f"remover horário {pub.slot_id}")))


def resumo_texto(resumo: dict) -> str:
    base = (f"{resumo['classes_criadas']} classe(s) criada(s), {resumo['slots_criados']} horário(s) publicado(s), "
            f"{resumo['slots_atualizados']} atualizado(s), {resumo['slots_removidos']} removido(s), "
            f"{resumo['sem_mudanca']} sem mudança, {resumo['erros']} erro(s)")
    return ("Prévia: " + base if resumo.get("previa") else base)[:300]


def registrar_sync(db: Session, cfg: WellhubConfig, texto: str, ok: bool) -> None:
    cfg.sync_ultimo_em, cfg.sync_ultimo_resumo, cfg.sync_ultimo_ok = agora_utc(), texto[:300], ok
    db.commit()


def atualizar_vagas_do_slot(db: Session, cfg: WellhubConfig, aula_sessao_id: int) -> None:
    """Depois de uma reserva/cancelamento, reenvia as vagas daquela aula (melhor esforço: a sincronização corrige)."""
    pub = db.scalar(select(WellhubSlot).where(WellhubSlot.aula_sessao_id == aula_sessao_id,
                                              WellhubSlot.situacao == "publicado"))
    sessao = db.get(AulaSessao, aula_sessao_id)
    if pub is None or sessao is None:
        return
    m = db.get(WellhubMapeamento, pub.mapeamento_id)
    if m is None or not m.class_id:
        return
    atual = r.vagas_para_publicar(agenda.capacidade_da_sessao(db, sessao), sessao.reservas_ativas)
    if atual == r.Vagas(pub.capacidade_publicada, pub.reservadas_publicadas):
        return
    try:
        c = cliente_da_config(cfg)
    except ErroWellhub:
        return
    try:
        c.atualizar_vagas(m.class_id, pub.slot_id, atual.capacidade, atual.reservadas)
        pub.capacidade_publicada, pub.reservadas_publicadas, pub.publicado_em = atual.capacidade, atual.reservadas, agora_utc()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.warning("Não foi possível atualizar as vagas do horário %s no Wellhub", pub.slot_id)
    finally:
        c.fechar()
