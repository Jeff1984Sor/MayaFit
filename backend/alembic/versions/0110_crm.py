"""CRM de vendas: etapas do funil, motivos de perda, leads, interacoes, tarefas e historico de etapas.

Revision ID: 0110_crm
Revises: 0002_usuario_suporte
"""

import sqlalchemy as sa
from alembic import op

import app.core.db  # noqa: F401  (UtcDateTime)

revision = "0110_crm"
down_revision = "0002_usuario_suporte"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('crm_etapa',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=60), nullable=False),
    sa.Column('ordem', sa.Integer(), nullable=False),
    sa.Column('cor', sa.String(length=9), nullable=False),
    sa.Column('tipo', sa.Enum('ABERTA', 'GANHO', 'PERDIDO', name='tipoetapa', native_enum=False, length=10), nullable=False),
    sa.Column('marco', sa.Enum('AULA_AGENDADA', 'AULA_REALIZADA', 'PROPOSTA', name='marcoetapa', native_enum=False, length=20), nullable=True),
    sa.Column('dias_alerta', sa.Integer(), nullable=False),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_crm_etapa'))
    )
    op.create_table('crm_motivo_perda',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=80), nullable=False),
    sa.Column('ordem', sa.Integer(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_crm_motivo_perda'))
    )
    op.create_table('crm_lead',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=150), nullable=False),
    sa.Column('telefone', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('origem', sa.Enum('SITE', 'INSTAGRAM', 'INDICACAO', 'WELLHUB', 'TOTALPASS', 'PASSANTE', 'WHATSAPP', 'OUTROS', name='origemlead', native_enum=False, length=20), nullable=False),
    sa.Column('indicado_por', sa.String(length=150), nullable=True),
    sa.Column('interesse', sa.String(length=150), nullable=True),
    sa.Column('responsavel_id', sa.Integer(), nullable=True),
    sa.Column('valor_estimado', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('etapa_id', sa.Integer(), nullable=False),
    sa.Column('etapa_desde', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('situacao', sa.Enum('ABERTO', 'GANHO', 'PERDIDO', name='situacaolead', native_enum=False, length=10), nullable=False),
    sa.Column('motivo_perda_id', sa.Integer(), nullable=True),
    sa.Column('motivo_perda_detalhe', sa.String(length=300), nullable=True),
    sa.Column('perdido_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('ganho_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('aluno_id', sa.Integer(), nullable=True),
    sa.Column('ultima_interacao_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('aula_experimental_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('aula_experimental_status', sa.Enum('AGENDADA', 'REALIZADA', 'FALTOU', 'CANCELADA', name='statusaulaexperimental', native_enum=False, length=12), nullable=True),
    sa.Column('aula_experimental_profissional_id', sa.Integer(), nullable=True),
    sa.Column('aula_experimental_unidade_id', sa.Integer(), nullable=True),
    sa.Column('aula_experimental_obs', sa.String(length=300), nullable=True),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['aluno_id'], ['aluno.id'], name=op.f('fk_crm_lead_aluno_id_aluno'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['aula_experimental_profissional_id'], ['profissional.id'], name=op.f('fk_crm_lead_aula_experimental_profissional_id_profissional'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['aula_experimental_unidade_id'], ['unidade.id'], name=op.f('fk_crm_lead_aula_experimental_unidade_id_unidade'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['etapa_id'], ['crm_etapa.id'], name=op.f('fk_crm_lead_etapa_id_crm_etapa')),
    sa.ForeignKeyConstraint(['motivo_perda_id'], ['crm_motivo_perda.id'], name=op.f('fk_crm_lead_motivo_perda_id_crm_motivo_perda'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['responsavel_id'], ['usuario.id'], name=op.f('fk_crm_lead_responsavel_id_usuario'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_crm_lead'))
    )
    op.create_index(op.f('ix_crm_lead_email'), 'crm_lead', ['email'], unique=False)
    op.create_index(op.f('ix_crm_lead_etapa_id'), 'crm_lead', ['etapa_id'], unique=False)
    op.create_index(op.f('ix_crm_lead_nome'), 'crm_lead', ['nome'], unique=False)
    op.create_index(op.f('ix_crm_lead_origem'), 'crm_lead', ['origem'], unique=False)
    op.create_index(op.f('ix_crm_lead_responsavel_id'), 'crm_lead', ['responsavel_id'], unique=False)
    op.create_index(op.f('ix_crm_lead_situacao'), 'crm_lead', ['situacao'], unique=False)
    op.create_index('ix_crm_lead_situacao_etapa', 'crm_lead', ['situacao', 'etapa_id'], unique=False)
    op.create_index(op.f('ix_crm_lead_telefone'), 'crm_lead', ['telefone'], unique=False)
    op.create_table('crm_interacao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lead_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.Enum('LIGACAO', 'WHATSAPP', 'VISITA', 'EMAIL', 'NOTA', 'SISTEMA', name='tipointeracao', native_enum=False, length=10), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('ocorrido_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['lead_id'], ['crm_lead.id'], name=op.f('fk_crm_interacao_lead_id_crm_lead'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], name=op.f('fk_crm_interacao_usuario_id_usuario'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_crm_interacao'))
    )
    op.create_index(op.f('ix_crm_interacao_lead_id'), 'crm_interacao', ['lead_id'], unique=False)
    op.create_table('crm_movimento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lead_id', sa.Integer(), nullable=False),
    sa.Column('etapa_origem_id', sa.Integer(), nullable=True),
    sa.Column('etapa_destino_id', sa.Integer(), nullable=True),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['etapa_destino_id'], ['crm_etapa.id'], name=op.f('fk_crm_movimento_etapa_destino_id_crm_etapa'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['etapa_origem_id'], ['crm_etapa.id'], name=op.f('fk_crm_movimento_etapa_origem_id_crm_etapa'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lead_id'], ['crm_lead.id'], name=op.f('fk_crm_movimento_lead_id_crm_lead'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], name=op.f('fk_crm_movimento_usuario_id_usuario'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_crm_movimento'))
    )
    op.create_index(op.f('ix_crm_movimento_em'), 'crm_movimento', ['em'], unique=False)
    op.create_index(op.f('ix_crm_movimento_lead_id'), 'crm_movimento', ['lead_id'], unique=False)
    op.create_table('crm_tarefa',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lead_id', sa.Integer(), nullable=True),
    sa.Column('titulo', sa.String(length=150), nullable=False),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('vence_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('responsavel_id', sa.Integer(), nullable=True),
    sa.Column('concluida', sa.Boolean(), nullable=False),
    sa.Column('concluida_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('criado_por_id', sa.Integer(), nullable=True),
    sa.Column('automatica', sa.Boolean(), nullable=False),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['criado_por_id'], ['usuario.id'], name=op.f('fk_crm_tarefa_criado_por_id_usuario'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lead_id'], ['crm_lead.id'], name=op.f('fk_crm_tarefa_lead_id_crm_lead'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['responsavel_id'], ['usuario.id'], name=op.f('fk_crm_tarefa_responsavel_id_usuario'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_crm_tarefa'))
    )
    op.create_index(op.f('ix_crm_tarefa_concluida'), 'crm_tarefa', ['concluida'], unique=False)
    op.create_index(op.f('ix_crm_tarefa_lead_id'), 'crm_tarefa', ['lead_id'], unique=False)
    op.create_index(op.f('ix_crm_tarefa_responsavel_id'), 'crm_tarefa', ['responsavel_id'], unique=False)
    op.create_index(op.f('ix_crm_tarefa_vence_em'), 'crm_tarefa', ['vence_em'], unique=False)


def downgrade() -> None:
    op.drop_table("crm_tarefa")
    op.drop_table("crm_movimento")
    op.drop_table("crm_interacao")
    op.drop_table("crm_lead")
    op.drop_table("crm_motivo_perda")
    op.drop_table("crm_etapa")
