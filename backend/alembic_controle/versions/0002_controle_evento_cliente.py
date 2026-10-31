"""Controle: linha do tempo da ficha do estúdio (evento_cliente), usada pelo Admin MayaFit e pelo churn.

Revision ID: 0002_controle_evento_cliente
Revises: 0001_controle_inicial
"""

import sqlalchemy as sa
from alembic import op

import app.core.db

revision = "0002_controle_evento_cliente"
down_revision = "0001_controle_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evento_cliente",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("descricao", sa.String(length=500), nullable=False),
        sa.Column("dados", sa.JSON(), nullable=False),
        sa.Column("usuario", sa.String(length=150), nullable=True),
        sa.Column("criado_em", app.core.db.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cliente_id"], ["cliente.id"], name=op.f("fk_evento_cliente_cliente_id_cliente"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evento_cliente")),
    )
    op.create_index(op.f("ix_evento_cliente_cliente_id"), "evento_cliente", ["cliente_id"], unique=False)
    op.create_index(op.f("ix_evento_cliente_tipo"), "evento_cliente", ["tipo"], unique=False)
    op.create_index(op.f("ix_evento_cliente_criado_em"), "evento_cliente", ["criado_em"], unique=False)


def downgrade() -> None:
    op.drop_table("evento_cliente")
