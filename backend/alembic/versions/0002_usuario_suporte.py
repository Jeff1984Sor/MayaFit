"""Usuário Suporte da MayaCorp (um banco por estúdio): coluna usuario.suporte.

Revision ID: 0002_usuario_suporte
Revises: 0001_pilates_inicial
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_usuario_suporte"
down_revision = "0001_pilates_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usuario") as batch:
        batch.add_column(sa.Column("suporte", sa.Boolean(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("usuario") as batch:
        batch.drop_column("suporte")
