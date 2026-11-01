"""Dados de base da demonstração (`app.demo_base.popular_base`): quantidade mínima, coerência pelas regras e idempotência."""

from datetime import date, timedelta

from sqlalchemy import func, select

from app.demo_base import contagens, popular_base
from app.domain.financeiro import hoje_de_negocio
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.agenda.servico import capacidade_da_sessao
from app.modules.alunos.models import Aluno, StatusAluno
from app.modules.app_aluno.models import ReposicaoPedido, StatusPedido
from app.modules.cadastros.models import Plano
from app.modules.contratos.models import Contrato, StatusAssinatura
from app.modules.financeiro.models import ContaReceber, StatusReceber


def _n(db, modelo, *cond) -> int:
    return db.scalar(select(func.count()).select_from(modelo).where(*cond)) or 0


def test_popular_base_coerente_e_idempotente(db):
    from app.core.db import agora

    hoje = hoje_de_negocio(agora())
    r = popular_base(db, perfil="pilates", alunos=30)
    assert r["alunos"] == 30
    assert r["alunos_ativos"] >= 20
    assert r["contratos"] >= 25 and r["reservas"] >= 300 and r["contas_receber"] >= 30
    assert r["contas_pagar"] > 0 and r["movimentos"] > 0 and r["comissoes"] > 0

    # todo aluno com contrato vigente tem plano (e o plano existe)
    vigentes = db.scalars(select(Contrato).where(Contrato.data_inicio <= hoje, Contrato.data_fim >= hoje)).all()
    assert vigentes
    assert all(c.plano_id and db.get(Plano, c.plano_id) for c in vigentes)
    assert all(db.get(Aluno, c.aluno_id).status == StatusAluno.ATIVO for c in vigentes)
    assert _n(db, Contrato, Contrato.status_assinatura == StatusAssinatura.NAO_ASSINADO, Contrato.data_fim >= hoje) >= 1
    assert _n(db, Contrato, Contrato.status_assinatura != StatusAssinatura.NAO_ASSINADO) >= 20

    # reservas futuras não passam da capacidade (e o contador bate com as reservas)
    futuras = db.scalars(select(AulaSessao).where(AulaSessao.data > hoje)).all()
    assert futuras
    for s in futuras:
        ativas = _n(db, Reserva, Reserva.aula_sessao_id == s.id, Reserva.status == StatusReserva.RESERVADA)
        assert ativas == s.reservas_ativas <= capacidade_da_sessao(db, s)
    # passado: presença, falta e desmarcação; nada RESERVADA em aula que já acabou ontem
    ontem = hoje - timedelta(days=1)
    passadas = select(AulaSessao.id).where(AulaSessao.data <= ontem)
    assert _n(db, Reserva, Reserva.aula_sessao_id.in_(passadas), Reserva.status == StatusReserva.RESERVADA) == 0
    for st in (StatusReserva.CONCLUIDA, StatusReserva.FALTOU_SEM_AVISAR, StatusReserva.CANCELADA):
        assert _n(db, Reserva, Reserva.aula_sessao_id.in_(passadas), Reserva.status == st) > 0
    assert _n(db, ReposicaoPedido, ReposicaoPedido.status == StatusPedido.PENDENTE) >= 1

    # financeiro: pagos com data de pagamento, abertos e atrasados
    assert _n(db, ContaReceber, ContaReceber.status == StatusReceber.PAGO, ContaReceber.pagamento.is_(None)) == 0
    assert _n(db, ContaReceber, ContaReceber.status == StatusReceber.PAGO) > 0
    assert _n(db, ContaReceber, ContaReceber.status == StatusReceber.ABERTO, ContaReceber.vencimento < hoje) > 0
    assert _n(db, ContaReceber, ContaReceber.status == StatusReceber.ABERTO, ContaReceber.vencimento >= hoje) > 0
    assert _n(db, ContaReceber, ContaReceber.pagamento > hoje) == 0

    # aniversariantes nesta semana
    nascimentos = db.scalars(select(Aluno.data_nascimento)).all()
    semana = {((hoje + timedelta(days=k)).month, (hoje + timedelta(days=k)).day) for k in range(8)}
    assert any((d.month, d.day) in semana for d in nascimentos if isinstance(d, date))

    # segunda chamada: não duplica nada
    antes = contagens(db)
    depois = popular_base(db, perfil="pilates", alunos=30)
    depois.pop("geracao", None)
    assert depois == antes
