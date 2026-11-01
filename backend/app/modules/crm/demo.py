"""Dados de demonstração do CRM (sintéticos). `popular_demo(db)` é idempotente: roda uma vez por banco.

Monta um funil vivo: leads em todas as etapas, aulas experimentais (hoje, amanhã, uma que faltou), propostas,
matrículas e perdas com motivo espalhadas pelos últimos 60 dias, interações, tarefas atrasadas e de hoje.
Nenhum dado real: nomes inventados, telefones da faixa 11 90000-xxxx e e-mails @exemplo.com.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import agora
from app.modules.alunos.models import Aluno
from app.modules.crm import regras, servico
from app.modules.crm.models import (
    CrmEtapa,
    CrmInteracao,
    CrmLead,
    CrmMotivoPerda,
    CrmMovimento,
    CrmTarefa,
    OrigemLead,
    SituacaoLead,
    StatusAulaExperimental,
    TipoEtapa,
    TipoInteracao,
)

MARCA = "@demo.exemplo.com"

# (nome, origem, interesse, etapa, dias atrás, valor, extra)
_LEADS = [
    ("Mariana Lopes", OrigemLead.INSTAGRAM, "Pilates", "Novo contato", 0, 389, {"tarefa": ("Fazer o primeiro contato", -0.1)}),
    ("Rafael Prado", OrigemLead.SITE, "Funcional", "Novo contato", 1, 299, {"tarefa": ("Retornar formulário do site", -1)}),
    ("Juliana Reis", OrigemLead.WELLHUB, "Pilates", "Novo contato", 4, 0, {}),
    ("Patrícia Gomes", OrigemLead.INDICACAO, "Pilates", "Aula experimental agendada", 3, 420, {"aula_horas": 3, "indicado_por": "Fernanda (aluna)"}),
    ("Lucas Andrade", OrigemLead.INSTAGRAM, "Funcional", "Aula experimental agendada", 2, 299, {"aula_horas": 26}),
    ("Beatriz Melo", OrigemLead.PASSANTE, "Pilates", "Aula experimental agendada", 6, 389, {"aula_status": "FALTOU", "aula_horas": -48}),
    ("Camila Duarte", OrigemLead.SITE, "Pilates", "Fez aula experimental", 5, 420, {"aula_status": "REALIZADA", "aula_horas": -20}),
    ("Thiago Nunes", OrigemLead.TOTALPASS, "Funcional", "Fez aula experimental", 9, 299, {"aula_status": "REALIZADA", "aula_horas": -96}),
    ("Renata Costa", OrigemLead.INDICACAO, "Pilates", "Proposta", 7, 520, {"tarefa": ("Follow-up da proposta", 2)}),
    ("Gustavo Lima", OrigemLead.WHATSAPP, "Pilates", "Proposta", 12, 389, {}),
    ("Fernanda Alves", OrigemLead.INDICACAO, "Pilates", "Matriculado", 20, 420, {"ganho_dias": 12}),
    ("Eduardo Pires", OrigemLead.INSTAGRAM, "Funcional", "Matriculado", 35, 299, {"ganho_dias": 25}),
    ("Sofia Martins", OrigemLead.SITE, "Pilates", "Matriculado", 50, 389, {"ganho_dias": 41}),
    ("Aline Ramos", OrigemLead.INSTAGRAM, "Pilates", "Perdido", 25, 389, {"motivo": "Preço"}),
    ("Marcelo Teixeira", OrigemLead.SITE, "Funcional", "Perdido", 40, 299, {"motivo": "Horário não atende"}),
    ("Larissa Freitas", OrigemLead.WELLHUB, "Pilates", "Perdido", 15, 0, {"motivo": "Só queria a aula experimental"}),
]

_CONVERSAS = [
    (TipoInteracao.WHATSAPP, "Mandei a mensagem de boas-vindas e os horários da semana."),
    (TipoInteracao.LIGACAO, "Conversamos por 5 minutos: quer treinar de manhã, 2x por semana."),
    (TipoInteracao.VISITA, "Veio conhecer o estúdio e gostou dos aparelhos."),
    (TipoInteracao.NOTA, "Tem uma lesão antiga no joelho: avisar o professor."),
]


def popular_demo(db: Session) -> int:
    """Cria os dados de demonstração se ainda não existirem. Devolve quantos leads criou (0 = já havia)."""
    if db.scalar(select(CrmLead.id).where(CrmLead.email.like(f"%{MARCA}")).limit(1)):
        return 0
    servico.garantir_padrao(db)
    etapas = {e.nome: e for e in db.scalars(select(CrmEtapa))}
    if not all(nome in etapas for _, _, _, nome, _, _, _ in _LEADS):
        return 0  # funil personalizado: não mexe
    motivos = {m.nome: m for m in db.scalars(select(CrmMotivoPerda))}
    abertas = sorted((e for e in etapas.values() if e.tipo == TipoEtapa.ABERTA), key=lambda e: e.ordem)
    agora_ = agora()
    criados = 0
    for i, (nome, origem, interesse, nome_etapa, dias, valor, extra) in enumerate(_LEADS):
        etapa = etapas[nome_etapa]
        criado = agora_ - timedelta(days=dias, hours=i)
        lead = CrmLead(
            nome=nome, telefone=f"55119000{i:05d}", email=f"{nome.split()[0].lower()}{MARCA}", origem=origem, interesse=interesse,
            valor_estimado=Decimal(valor) if valor else None, tags=["Demonstração"], etapa_id=etapa.id, situacao=SituacaoLead.ABERTO,
            indicado_por=extra.get("indicado_por"), criado_em=criado, etapa_desde=criado,
        )
        db.add(lead)
        db.flush()
        # caminho pelo funil até a etapa atual (base do relatório de conversão)
        caminho: list[CrmEtapa] = []
        if etapa.tipo == TipoEtapa.ABERTA:
            caminho = [e for e in abertas if e.ordem <= etapa.ordem]
        elif etapa.tipo == TipoEtapa.GANHO:
            caminho = [*abertas, etapa]
        else:
            caminho = [*abertas[: 1 + i % 3], etapa]
        anterior = None
        for passo, e in enumerate(caminho):
            quando = min(criado + timedelta(days=passo * max(dias, 1) / max(len(caminho), 1)), agora_)
            db.add(CrmMovimento(lead_id=lead.id, etapa_origem_id=anterior.id if anterior else None, etapa_destino_id=e.id, em=quando))
            anterior = e
            lead.etapa_desde = quando
        if etapa.tipo == TipoEtapa.GANHO:
            lead.situacao, lead.ganho_em = SituacaoLead.GANHO, agora_ - timedelta(days=extra.get("ganho_dias", 1))
            lead.etapa_desde = lead.ganho_em
            # o aluno da matrícula (os dados de base da demonstração criam os leads convertidos com o mesmo nome)
            lead.aluno_id = db.scalar(select(Aluno.id).where(Aluno.nome == nome).limit(1))
        elif etapa.tipo == TipoEtapa.PERDIDO:
            motivo = motivos.get(extra.get("motivo", "")) or next(iter(motivos.values()))
            lead.situacao, lead.perdido_em, lead.motivo_perda_id = SituacaoLead.PERDIDO, criado + timedelta(days=3), motivo.id
            lead.etapa_desde = lead.perdido_em
        if "aula_horas" in extra:
            lead.aula_experimental_em = _hora_cheia(agora_ + timedelta(hours=extra["aula_horas"]))
            lead.aula_experimental_status = StatusAulaExperimental(extra.get("aula_status", "AGENDADA"))
        db.add(CrmInteracao(lead_id=lead.id, tipo=TipoInteracao.SISTEMA, ocorrido_em=criado,
                            descricao=f"Novo contato pelo canal {regras.ROTULO_ORIGEM[origem]}. Interesse: {interesse}."))
        if dias >= 1:
            tipo, texto = _CONVERSAS[i % len(_CONVERSAS)]
            quando = criado + timedelta(hours=2)
            db.add(CrmInteracao(lead_id=lead.id, tipo=tipo, descricao=texto, ocorrido_em=quando))
            lead.ultima_interacao_em = quando
        if "tarefa" in extra:
            titulo, em_dias = extra["tarefa"]
            db.add(CrmTarefa(lead_id=lead.id, titulo=f"{titulo}: {nome.split()[0]}", vence_em=agora_ + timedelta(days=em_dias), automatica=False))
        if lead.aula_experimental_status == StatusAulaExperimental.AGENDADA and extra["aula_horas"] > 0:
            db.add(CrmTarefa(lead_id=lead.id, titulo=f"Confirmar aula experimental de {nome.split()[0]}",
                             vence_em=max(lead.aula_experimental_em - timedelta(days=1), agora_ + timedelta(minutes=30)), automatica=True))
        criados += 1
    db.commit()
    return criados


def _hora_cheia(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)
