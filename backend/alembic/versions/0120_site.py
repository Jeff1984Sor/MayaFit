"""Site grátis do estúdio: configuração (rascunho/publicado) e contatos recebidos.

Revision ID: 0120_site
Revises: 0001_pilates_inicial
"""

import sqlalchemy as sa
from alembic import op

import app.core.db

revision = "0120_site"
down_revision = "0001_pilates_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tema", sa.String(length=20), nullable=False),
        sa.Column("conteudo", sa.JSON(), nullable=False),
        sa.Column("tema_publicado", sa.String(length=20), nullable=True),
        sa.Column("conteudo_publicado", sa.JSON(), nullable=True),
        sa.Column("publicado", sa.Boolean(), nullable=False),
        sa.Column("publicado_em", app.core.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("publicado_por_id", sa.Integer(), nullable=True),
        sa.Column("criado_em", app.core.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", app.core.db.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["publicado_por_id"], ["usuario.id"], name=op.f("fk_site_config_publicado_por_id_usuario"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_site_config")),
    )
    op.create_table(
        "site_contato",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("telefone", sa.String(length=30), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("interesse", sa.String(length=120), nullable=True),
        sa.Column("mensagem", sa.Text(), nullable=True),
        sa.Column("quer_aula_experimental", sa.Boolean(), nullable=False),
        sa.Column("consentimento_em", app.core.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("consentimento_texto", sa.String(length=300), nullable=False),
        sa.Column("enviado_crm", sa.Boolean(), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=True),
        sa.Column("erro_crm", sa.String(length=300), nullable=True),
        sa.Column("lido", sa.Boolean(), nullable=False),
        sa.Column("criado_em", app.core.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", app.core.db.UtcDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_site_contato")),
    )


def downgrade() -> None:
    op.drop_table("site_contato")
    op.drop_table("site_config")
