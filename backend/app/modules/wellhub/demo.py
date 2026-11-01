"""Dados de demonstração do Wellhub (o coordenador chama `popular_demo(db)` no seed; idempotente).

Cria, na primeira unidade ativa: configuração em SANDBOX (sem chave de API: nada sai para a rede), o primeiro serviço
ativo ligado a um produto, três alunos Wellhub sintéticos, check-ins do mês (validados e pendentes) e alguns eventos
(processados, um rejeitado por lotação e um com erro para o alerta aparecer no painel).
Dados 100% sintéticos (nenhum dado real de aluno).
"""

from __future__ import annotations

import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import agora as agora_utc
from app.domain.financeiro import hoje_de_negocio
from app.domain.status_aula import momento_da_sessao
from app.modules.alunos.models import Aluno, StatusAluno
from app.modules.cadastros.models import TipoServico, Unidade, proximo_codigo
from app.modules.wellhub.eventos import cifrar
from app.modules.wellhub.models import (
    WellhubAluno,
    WellhubCheckin,
    WellhubConfig,
    WellhubEvento,
    WellhubMapeamento,
)

GYM_DEMO = "DEMO-0001"
ALUNOS_DEMO = (("Bruna Demo Wellhub", "9990000000001"), ("Caio Demo Wellhub", "9990000000002"),
               ("Dora Demo Wellhub", "9990000000003"))


def popular_demo(db: Session, *, agora: datetime | None = None) -> dict:
    """Idempotente: se a configuração de demonstração já existe, não faz nada. Faz commit."""
    if db.scalar(select(WellhubConfig).where(WellhubConfig.gym_id == GYM_DEMO)) is not None:
        return {"criado": False, "motivo": "Demonstração do Wellhub já existe."}
    unidade = db.scalars(select(Unidade).where(Unidade.ativo.is_(True)).order_by(Unidade.id)).first()
    servico = db.scalars(select(TipoServico).where(TipoServico.ativo.is_(True)).order_by(TipoServico.id)).first()
    if unidade is None or servico is None:
        return {"criado": False, "motivo": "Cadastre uma unidade e um serviço antes da demonstração do Wellhub."}
    if db.scalar(select(WellhubConfig).where(WellhubConfig.unidade_id == unidade.id)) is not None:
        return {"criado": False, "motivo": "A unidade já tem uma configuração real do Wellhub."}
    agora = agora or agora_utc()
    hoje = hoje_de_negocio(agora)
    cfg = WellhubConfig(unidade_id=unidade.id, ativo=True, ambiente="sandbox", gym_id=GYM_DEMO,
                        webhook_secret_cifrado=cifrar("demo-" + secrets.token_urlsafe(24)), criar_aluno_automatico=True,
                        validar_checkin_automatico=False, valor_repasse_checkin=Decimal("12.50"), sync_ativo=False,
                        sync_dias=7, falhas_assinatura=0, teste_ultimo_ok=None)
    db.add(cfg)
    db.flush()
    db.add(WellhubMapeamento(config_id=cfg.id, tipo_servico_id=servico.id, product_id="DEMO-PROD", class_id=None,
                             nome_classe=servico.nome, ativo=True))
    alunos = []
    for nome, gid in ALUNOS_DEMO:
        existente = db.scalar(select(WellhubAluno).where(WellhubAluno.gympass_id == gid))
        if existente is not None:
            alunos.append((existente.aluno_id, gid))
            continue
        a = Aluno(nome=nome, cpf=None, sem_cpf=True, unidade_id=unidade.id, status=StatusAluno.ATIVO,
                  codigo_legado=proximo_codigo(db, "aluno"))
        db.add(a)
        db.flush()
        db.add(WellhubAluno(aluno_id=a.id, gympass_id=gid, config_id=cfg.id))
        alunos.append((a.id, gid))
    db.flush()
    checkins = 0
    inicio = hoje.replace(day=1)
    dia = inicio
    while dia <= hoje:
        for k, (aluno_id, gid) in enumerate(alunos):
            # padrão determinístico: ~1 em cada 3 dias por aluno; o 1º aluno sempre vem hoje (no dia 1º o mês não fica zerado)
            if (dia.day + k) % 3 == 0 or (dia == hoje and k == 0):
                quando = momento_da_sessao(dia, time(7 + k * 2, 0))
                validado = dia < hoje or k == 0
                db.add(WellhubCheckin(config_id=cfg.id, aluno_id=aluno_id, gympass_id=gid, dia=dia, ocorrido_em=quando,
                                      origem="demo", validado=validado, validado_em=quando + timedelta(minutes=2) if validado else None))
                checkins += 1
        dia += timedelta(days=1)
    base = agora - timedelta(hours=3)
    eventos = [
        ("checkin", "processado", None, alunos[0]),
        ("booking-requested", "processado", None, alunos[1]),
        ("booking-requested", "rejeitado", "Recusada no Wellhub (CLASS_IS_FULL): Capacidade excedida (aula lotada).", alunos[2]),
        ("booking-requested", "erro", "O horário (slot DEMO-SLOT-9) não foi publicado por este sistema. Publique a grade e "
                                      "reprocesse.", alunos[0]),
    ]
    for n, (tipo, resultado, erro, (aluno_id, gid)) in enumerate(eventos):
        payload = {"event_type": tipo, "event_data": {"user": {"unique_token": gid, "name": "Demo"},
                                                      "slot": {"id": f"DEMO-SLOT-{n}", "gym_id": GYM_DEMO,
                                                               "booking_number": f"DEMO-BK-{n}"},
                                                      "timestamp": int((base + timedelta(minutes=n * 20)).timestamp())},
                   "demo": True}
        db.add(WellhubEvento(chave=f"demo:{cfg.id}:{n}", config_id=cfg.id, tipo=tipo, gympass_id=gid,
                             booking_number=f"DEMO-BK-{n}" if tipo != "checkin" else None, slot_id=f"DEMO-SLOT-{n}",
                             payload=payload, recebido_em=base + timedelta(minutes=n * 20),
                             processado_em=None if resultado == "erro" else base + timedelta(minutes=n * 20, seconds=2),
                             resultado=resultado, erro=erro, tentativas=1, origem="demo", aluno_id=aluno_id, ignorado=False))
    db.commit()
    return {"criado": True, "config_id": cfg.id, "alunos": len(alunos), "checkins": checkins, "eventos": len(eventos)}
