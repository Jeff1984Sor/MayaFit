"""Dados de demonstração: idempotentes e coerentes com o funil e o relatório."""

from sqlalchemy import func, select

from app.modules.crm.demo import popular_demo
from app.modules.crm.models import CrmLead


def test_popular_demo_idempotente_e_relatorio(db, client, h):
    assert popular_demo(db) == 16
    assert popular_demo(db) == 0
    assert db.scalar(select(func.count()).select_from(CrmLead)) == 16
    colunas = {c["etapa"]["nome"]: c["total"] for c in client.get("/api/crm/funil", headers=h).json()["colunas"]}
    assert colunas["Proposta"] == 2 and colunas["Matriculado"] == 2  # a matrícula de 41 dias atrás sai do Kanban (30 dias)
    r = client.get("/api/crm/relatorio", headers=h).json()
    assert r["total_leads"] == 16 and r["ganhos"] == 3 and r["perdidos"] == 3
    assert r["funil"][-1]["quantidade"] == 3 and r["tempo_medio_dias"] is not None
    assert sum(x["quantidade"] for x in r["perdidos_por_motivo"]) == 3
    resumo = client.get("/api/crm/resumo", headers=h).json()
    assert resumo["abertos"] == 10 and resumo["destaque"]
