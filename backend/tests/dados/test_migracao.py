"""A migração inicial provisória reproduz o esquema dos modelos (SQLite) e renderiza para PostgreSQL."""

import importlib.util
import io
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.core.db import Base
from app.modules import registrar_modelos

ARQUIVO = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0001_esquema_inicial.py"


@pytest.fixture(scope="module")
def migracao():
    registrar_modelos()
    spec = importlib.util.spec_from_file_location("migracao_0001", ARQUIVO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seguintes():
    """As migrations depois da 0001 (ex.: 0002_usuario_suporte), em ordem, para o esquema bater com os modelos."""
    mods = []
    for arq in sorted(ARQUIVO.parent.glob("0*.py")):
        if arq == ARQUIVO:
            continue
        spec = importlib.util.spec_from_file_location(f"migracao_{arq.stem}", arq)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mods.append(mod)
    return mods


def _esquema(eng):
    insp = inspect(eng)
    saida = {}
    for t in insp.get_table_names():
        saida[t] = {
            "colunas": {c["name"]: c["nullable"] for c in insp.get_columns(t)},
            "uniques": sorted(u["name"] for u in insp.get_unique_constraints(t)),
            "fks": sorted(f["name"] for f in insp.get_foreign_keys(t)),
            "indices": sorted(i["name"] for i in insp.get_indexes(t) if not i["name"].startswith("sqlite_")),
        }
    return saida


@pytest.mark.filterwarnings("ignore:Skipped unsupported reflection")
def test_upgrade_igual_ao_create_all_e_downgrade_limpa(migracao):
    via_alembic = create_engine("sqlite://")
    with via_alembic.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migracao.upgrade()
            for m in _seguintes():
                m.upgrade()
    via_modelos = create_engine("sqlite://")
    Base.metadata.create_all(via_modelos)
    a, b = _esquema(via_alembic), _esquema(via_modelos)
    assert a.keys() == b.keys()
    for tabela in b:
        assert a[tabela]["colunas"] == b[tabela]["colunas"], tabela
        assert a[tabela]["uniques"] == b[tabela]["uniques"], tabela
        assert a[tabela]["indices"] == b[tabela]["indices"], tabela
    with via_alembic.connect() as c:  # índice por expressão: o inspector do SQLite não o reflete
        assert (
            c.exec_driver_sql(
                "select count(*) from sqlite_master where type='index' and name='uq_aula_sessao_slot'"
            ).scalar()
            == 1
        )
    with via_alembic.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            for m in reversed(_seguintes()):
                m.downgrade()
            migracao.downgrade()
    assert inspect(via_alembic).get_table_names() == []


def test_renderiza_para_postgresql(migracao):
    buf = io.StringIO()
    ctx = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buf})
    with Operations.context(ctx):
        migracao.upgrade()
    sql = buf.getvalue()
    assert (
        "CREATE UNIQUE INDEX uq_aula_sessao_slot ON aula_sessao (unidade_id, tipo_servico_id, coalesce(profissional_id, 0), data, hora_inicio)"
        in sql
    )
    assert "CONSTRAINT uq_aluno_cpf UNIQUE (cpf)" in sql
    assert "CONSTRAINT ck_aluno_cpf_coerente_com_sem_cpf CHECK" in sql
    assert "CONSTRAINT uq_reserva_aluno_aula_sessao UNIQUE (aluno_id, aula_sessao_id)" in sql
    assert "CONSTRAINT fk_reserva_contrato_id_contrato FOREIGN KEY(contrato_id) REFERENCES contrato (id)" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql and "NUMERIC(15, 2)" in sql and "SERIAL" in sql
    assert "UNIQUE (dedupe_key)" in sql or "uq_whatsapp_agendamento_log_dedupe_key" in sql


def test_migracao_nao_usa_default_numerico_em_booleano():
    """PostgreSQL recusa `BOOLEAN DEFAULT 1` (só o SQLite aceita): o primeiro deploy real quebrou por isso."""
    import re

    texto = ARQUIVO.read_text(encoding="utf-8")
    assert not re.search(r"sa\.Boolean\(\), server_default=sa\.text\('[01]'\)", texto)

