"""Integração Wellhub (antigo Gympass): configuração, mapeamento, horários publicados, alunos, reservas, eventos e check-ins.

Revision ID: 0140_wellhub
Revises: 0001_pilates_inicial
"""

import sqlalchemy as sa

import app.core.db  # noqa: F401  (UtcDateTime)
from alembic import op

revision = "0140_wellhub"
down_revision = "0001_pilates_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('wellhub_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('ambiente', sa.String(length=10), nullable=False),
    sa.Column('gym_id', sa.String(length=40), nullable=True),
    sa.Column('api_key_cifrado', sa.Text(), nullable=True),
    sa.Column('webhook_secret_cifrado', sa.Text(), nullable=True),
    sa.Column('criar_aluno_automatico', sa.Boolean(), nullable=False),
    sa.Column('validar_checkin_automatico', sa.Boolean(), nullable=False),
    sa.Column('servico_padrao_id', sa.Integer(), nullable=True),
    sa.Column('valor_repasse_checkin', sa.Numeric(precision=15, scale=2), nullable=True),
    sa.Column('sync_ativo', sa.Boolean(), nullable=False),
    sa.Column('sync_dias', sa.Integer(), nullable=False),
    sa.Column('sync_ultimo_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('sync_ultimo_resumo', sa.String(length=300), nullable=True),
    sa.Column('sync_ultimo_ok', sa.Boolean(), nullable=True),
    sa.Column('teste_ultimo_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('teste_ultimo_ok', sa.Boolean(), nullable=True),
    sa.Column('falhas_assinatura', sa.Integer(), nullable=False),
    sa.Column('falha_assinatura_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['servico_padrao_id'], ['tipo_servico.id'], name=op.f('fk_wellhub_config_servico_padrao_id_tipo_servico'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidade.id'], name=op.f('fk_wellhub_config_unidade_id_unidade'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wellhub_config')),
    sa.UniqueConstraint('unidade_id', name=op.f('uq_wellhub_config_unidade_id'))
    )
    op.create_index(op.f('ix_wellhub_config_gym_id'), 'wellhub_config', ['gym_id'], unique=False)
    op.create_table('wellhub_aluno',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('aluno_id', sa.Integer(), nullable=False),
    sa.Column('gympass_id', sa.String(length=20), nullable=False),
    sa.Column('config_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['aluno_id'], ['aluno.id'], name=op.f('fk_wellhub_aluno_aluno_id_aluno'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['config_id'], ['wellhub_config.id'], name=op.f('fk_wellhub_aluno_config_id_wellhub_config'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wellhub_aluno')),
    sa.UniqueConstraint('aluno_id', name=op.f('uq_wellhub_aluno_aluno_id')),
    sa.UniqueConstraint('gympass_id', name=op.f('uq_wellhub_aluno_gympass_id'))
    )
    op.create_table('wellhub_mapeamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('config_id', sa.Integer(), nullable=False),
    sa.Column('tipo_servico_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.String(length=40), nullable=True),
    sa.Column('class_id', sa.String(length=40), nullable=True),
    sa.Column('nome_classe', sa.String(length=150), nullable=True),
    sa.Column('descricao', sa.Text(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['config_id'], ['wellhub_config.id'], name=op.f('fk_wellhub_mapeamento_config_id_wellhub_config'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tipo_servico_id'], ['tipo_servico.id'], name=op.f('fk_wellhub_mapeamento_tipo_servico_id_tipo_servico'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wellhub_mapeamento')),
    sa.UniqueConstraint('config_id', 'tipo_servico_id', name=op.f('uq_wellhub_mapeamento_config_id'))
    )
    op.create_index(op.f('ix_wellhub_mapeamento_config_id'), 'wellhub_mapeamento', ['config_id'], unique=False)
    op.create_table('wellhub_slot',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('mapeamento_id', sa.Integer(), nullable=False),
    sa.Column('aula_sessao_id', sa.Integer(), nullable=True),
    sa.Column('slot_id', sa.String(length=40), nullable=False),
    sa.Column('capacidade_publicada', sa.Integer(), nullable=False),
    sa.Column('reservadas_publicadas', sa.Integer(), nullable=False),
    sa.Column('publicado_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('situacao', sa.String(length=12), nullable=False),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['aula_sessao_id'], ['aula_sessao.id'], name=op.f('fk_wellhub_slot_aula_sessao_id_aula_sessao'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['mapeamento_id'], ['wellhub_mapeamento.id'], name=op.f('fk_wellhub_slot_mapeamento_id_wellhub_mapeamento'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wellhub_slot')),
    sa.UniqueConstraint('aula_sessao_id', name=op.f('uq_wellhub_slot_aula_sessao_id'))
    )
    op.create_index(op.f('ix_wellhub_slot_mapeamento_id'), 'wellhub_slot', ['mapeamento_id'], unique=False)
    op.create_index(op.f('ix_wellhub_slot_slot_id'), 'wellhub_slot', ['slot_id'], unique=False)
    op.create_table('wellhub_checkin',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('config_id', sa.Integer(), nullable=False),
    sa.Column('aluno_id', sa.Integer(), nullable=True),
    sa.Column('gympass_id', sa.String(length=20), nullable=False),
    sa.Column('dia', sa.Date(), nullable=False),
    sa.Column('ocorrido_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('origem', sa.String(length=12), nullable=False),
    sa.Column('validado', sa.Boolean(), nullable=False),
    sa.Column('validado_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('erro_validacao', sa.String(length=300), nullable=True),
    sa.Column('reserva_id', sa.Integer(), nullable=True),
    sa.Column('produto', sa.String(length=150), nullable=True),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['aluno_id'], ['aluno.id'], name=op.f('fk_wellhub_checkin_aluno_id_aluno'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['config_id'], ['wellhub_config.id'], name=op.f('fk_wellhub_checkin_config_id_wellhub_config'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reserva_id'], ['reserva.id'], name=op.f('fk_wellhub_checkin_reserva_id_reserva'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wellhub_checkin')),
    sa.UniqueConstraint('config_id', 'gympass_id', 'dia', name=op.f('uq_wellhub_checkin_config_id'))
    )
    op.create_index(op.f('ix_wellhub_checkin_aluno_id'), 'wellhub_checkin', ['aluno_id'], unique=False)
    op.create_index('ix_wellhub_checkin_dia', 'wellhub_checkin', ['dia'], unique=False)
    op.create_table('wellhub_evento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chave', sa.String(length=80), nullable=False),
    sa.Column('config_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=40), nullable=False),
    sa.Column('gympass_id', sa.String(length=20), nullable=True),
    sa.Column('booking_number', sa.String(length=60), nullable=True),
    sa.Column('slot_id', sa.String(length=40), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('recebido_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('processado_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('resultado', sa.String(length=20), nullable=False),
    sa.Column('erro', sa.Text(), nullable=True),
    sa.Column('tentativas', sa.Integer(), nullable=False),
    sa.Column('origem', sa.String(length=12), nullable=False),
    sa.Column('reserva_id', sa.Integer(), nullable=True),
    sa.Column('aluno_id', sa.Integer(), nullable=True),
    sa.Column('ignorado', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['aluno_id'], ['aluno.id'], name=op.f('fk_wellhub_evento_aluno_id_aluno'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['config_id'], ['wellhub_config.id'], name=op.f('fk_wellhub_evento_config_id_wellhub_config'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reserva_id'], ['reserva.id'], name=op.f('fk_wellhub_evento_reserva_id_reserva'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wellhub_evento')),
    sa.UniqueConstraint('chave', name=op.f('uq_wellhub_evento_chave'))
    )
    op.create_index(op.f('ix_wellhub_evento_config_id'), 'wellhub_evento', ['config_id'], unique=False)
    op.create_index('ix_wellhub_evento_recebido_em', 'wellhub_evento', ['recebido_em'], unique=False)
    op.create_index('ix_wellhub_evento_resultado', 'wellhub_evento', ['resultado'], unique=False)
    op.create_table('wellhub_reserva',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('config_id', sa.Integer(), nullable=False),
    sa.Column('booking_number', sa.String(length=60), nullable=False),
    sa.Column('slot_id', sa.String(length=40), nullable=True),
    sa.Column('reserva_id', sa.Integer(), nullable=True),
    sa.Column('aluno_id', sa.Integer(), nullable=True),
    sa.Column('situacao', sa.String(length=20), nullable=False),
    sa.Column('resposta_enviada', sa.String(length=20), nullable=True),
    sa.Column('resposta_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['aluno_id'], ['aluno.id'], name=op.f('fk_wellhub_reserva_aluno_id_aluno'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['config_id'], ['wellhub_config.id'], name=op.f('fk_wellhub_reserva_config_id_wellhub_config'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reserva_id'], ['reserva.id'], name=op.f('fk_wellhub_reserva_reserva_id_reserva'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wellhub_reserva')),
    sa.UniqueConstraint('booking_number', name=op.f('uq_wellhub_reserva_booking_number'))
    )
    op.create_index(op.f('ix_wellhub_reserva_aluno_id'), 'wellhub_reserva', ['aluno_id'], unique=False)
    op.create_index(op.f('ix_wellhub_reserva_config_id'), 'wellhub_reserva', ['config_id'], unique=False)
    op.create_index(op.f('ix_wellhub_reserva_reserva_id'), 'wellhub_reserva', ['reserva_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_wellhub_reserva_reserva_id'), table_name='wellhub_reserva')
    op.drop_index(op.f('ix_wellhub_reserva_config_id'), table_name='wellhub_reserva')
    op.drop_index(op.f('ix_wellhub_reserva_aluno_id'), table_name='wellhub_reserva')
    op.drop_table('wellhub_reserva')
    op.drop_index('ix_wellhub_evento_resultado', table_name='wellhub_evento')
    op.drop_index('ix_wellhub_evento_recebido_em', table_name='wellhub_evento')
    op.drop_index(op.f('ix_wellhub_evento_config_id'), table_name='wellhub_evento')
    op.drop_table('wellhub_evento')
    op.drop_index('ix_wellhub_checkin_dia', table_name='wellhub_checkin')
    op.drop_index(op.f('ix_wellhub_checkin_aluno_id'), table_name='wellhub_checkin')
    op.drop_table('wellhub_checkin')
    op.drop_index(op.f('ix_wellhub_slot_slot_id'), table_name='wellhub_slot')
    op.drop_index(op.f('ix_wellhub_slot_mapeamento_id'), table_name='wellhub_slot')
    op.drop_table('wellhub_slot')
    op.drop_index(op.f('ix_wellhub_mapeamento_config_id'), table_name='wellhub_mapeamento')
    op.drop_table('wellhub_mapeamento')
    op.drop_table('wellhub_aluno')
    op.drop_index(op.f('ix_wellhub_config_gym_id'), table_name='wellhub_config')
    op.drop_table('wellhub_config')
