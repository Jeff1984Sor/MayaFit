"""Dados de DEMONSTRAÇÃO do controle de acesso (sintéticos). Chamado pelo coordenador: ``popular_demo(db)``.

Idempotente: cria (uma vez) a configuração, uma catraca SIMULADA, um totem de demonstração ligado a ela e um
histórico de acessos das últimas duas semanas com os alunos ativos que já existirem (inclusive alguns "no estúdio
agora", para o painel ao vivo). Não cria biometria (dado sensível não entra em demonstração) nem token de totem (o
token aparece só na tela, ao clicar em "Gerar novo token").
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import agora as agora_utc
from app.domain import acesso as dom
from app.modules.acesso import servico as srv
from app.modules.acesso.models import (
    Catraca,
    Dispositivo,
    DriverCatraca,
    MetodoAcesso,
    ModoAcionamento,
    RegistroAcesso,
    Sentido,
    TipoDispositivo,
)
from app.modules.alunos.models import Aluno, StatusAluno

NOME_CATRACA = "Catraca da recepção (demonstração)"
NOME_TOTEM = "Totem da recepção (demonstração)"

_NEGADOS = [
    (dom.NEG_ATRASO, "Mensalidade em atraso desde {venc}. Procure a recepção."),
    (dom.NEG_CEDO, "Sua aula de Pilates é às {hora}. A entrada libera a partir das {abre}."),
    (dom.NEG_SEM_AULA, "Sem aula marcada agora."),
    (dom.NEG_NAO_RECONHECIDO, "Não reconheci você. Tente de novo ou use o CPF."),
]
_AULAS = ["Pilates", "Funcional", "Pilates", "Alongamento"]


def popular_demo(db: Session, *, agora: datetime | None = None, semente: int = 42) -> dict:
    agora = agora or agora_utc()
    srv.obter_config(db)
    cat = db.scalar(select(Catraca).where(Catraca.nome == NOME_CATRACA))
    if cat is None:
        cat = Catraca(nome=NOME_CATRACA, driver=DriverCatraca.simulado, modo=ModoAcionamento.totem, sentido_entrada="clockwise",
                      acao_liberacao="catra", porta_rele=1, ativo=True)
        db.add(cat)
        db.flush()
    totem = db.scalar(select(Dispositivo).where(Dispositivo.nome == NOME_TOTEM))
    if totem is None:
        totem = Dispositivo(nome=NOME_TOTEM, tipo=TipoDispositivo.totem, catraca_id=cat.id, ativo=True, criado_por_nome="Demonstração")
        db.add(totem)
        db.flush()

    criados = 0
    ja_tem = db.scalar(select(RegistroAcesso.id).where(RegistroAcesso.dispositivo_id == totem.id).limit(1)) is not None
    alunos = list(db.scalars(select(Aluno).where(Aluno.status == StatusAluno.ATIVO).order_by(Aluno.id).limit(14)))
    if not ja_tem and alunos:
        rnd = random.Random(semente)
        hoje_local = dom.local(agora).date()
        for dias_atras in range(14, -1, -1):
            dia = hoje_local - timedelta(days=dias_atras)
            if dia.weekday() == 6:
                continue
            for aluno in rnd.sample(alunos, k=min(len(alunos), rnd.randint(4, 9))):
                hora = rnd.choice([6, 7, 7, 8, 9, 12, 17, 18, 18, 19, 20])
                inicio = datetime(dia.year, dia.month, dia.day, hora, 0, tzinfo=dom.FUSO)
                em = inicio - timedelta(minutes=rnd.randint(2, 25))
                if em.astimezone(UTC) > agora:
                    continue
                criados += _registro(db, rnd, aluno, em, inicio, totem, cat)
        # gente "no estúdio agora" para o painel ao vivo
        for i, aluno in enumerate(alunos[:3]):
            em = agora - timedelta(minutes=5 + 12 * i)
            reg = RegistroAcesso(em=em, aluno_id=aluno.id, aluno_nome=aluno.nome, permitido=True, codigo=dom.OK_AULA,
                                 motivo="Aula de Pilates (demonstração)", metodo=[MetodoAcesso.facial, MetodoAcesso.qr, MetodoAcesso.cpf][i],
                                 sentido=Sentido.entrada, dispositivo_id=totem.id, dispositivo_nome=totem.nome, catraca_id=cat.id,
                                 aula_descricao="Pilates (demonstração)", previsto_sair=agora + timedelta(minutes=50 - 10 * i),
                                 catraca_status="liberada", catraca_detalhe="Giro liberado (simulado).")
            db.add(reg)
            criados += 1
    db.flush()
    return {"catraca_id": cat.id, "totem_id": totem.id, "registros_criados": criados}


def _registro(db: Session, rnd: random.Random, aluno: Aluno, em: datetime, inicio: datetime, totem: Dispositivo, cat: Catraca) -> int:
    aula = rnd.choice(_AULAS)
    permitido = rnd.random() > 0.12
    metodo = rnd.choices([MetodoAcesso.facial, MetodoAcesso.qr, MetodoAcesso.cpf, MetodoAcesso.codigo], [6, 2, 1, 1])[0]
    if permitido:
        codigo, motivo = dom.OK_AULA, f"Aula de {aula} às {inicio.strftime('%H:%M')}"
    else:
        codigo, modelo = rnd.choice(_NEGADOS)
        motivo = modelo.format(venc=(em - timedelta(days=12)).strftime("%d/%m"), hora=inicio.strftime("%H:%M"),
                               abre=(inicio - timedelta(minutes=30)).strftime("%H:%M"))
    db.add(RegistroAcesso(
        em=em.astimezone(UTC), aluno_id=None if codigo == dom.NEG_NAO_RECONHECIDO else aluno.id,
        aluno_nome=None if codigo == dom.NEG_NAO_RECONHECIDO else aluno.nome, permitido=permitido, codigo=codigo, motivo=motivo,
        metodo=metodo, sentido=Sentido.entrada, dispositivo_id=totem.id, dispositivo_nome=totem.nome,
        catraca_id=cat.id if permitido else None, aula_descricao=f"{aula} · {inicio.strftime('%H:%M')}" if permitido else None,
        previsto_sair=(inicio + timedelta(minutes=65)).astimezone(UTC) if permitido else None,
        catraca_status="liberada" if permitido else None, similaridade=round(rnd.uniform(0.72, 0.95), 4) if metodo == MetodoAcesso.facial else None,
    ))
    return 1
