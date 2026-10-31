"""Controle de acesso: configuração, consentimento e descritores faciais (cifrados), PIN, catracas, dispositivos
(totem/agente), registros de acesso e fila de comandos do agente local.

Revision ID: 0130_acesso
Revises: 0120_site
"""

import sqlalchemy as sa

import app.core.db  # noqa: F401  (UtcDateTime)
from alembic import op

revision = "0130_acesso"
down_revision = "0120_site"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('acesso_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tolerancia_atraso_dias', sa.Integer(), nullable=False),
    sa.Column('janela_antes_min', sa.Integer(), nullable=False),
    sa.Column('janela_depois_min', sa.Integer(), nullable=False),
    sa.Column('permanencia_livre_min', sa.Integer(), nullable=False),
    sa.Column('planos_livres', sa.JSON(), nullable=True),
    sa.Column('limiar_similaridade', sa.Float(), nullable=False),
    sa.Column('margem_ambiguidade', sa.Float(), nullable=False),
    sa.Column('exigir_prova_vida', sa.Boolean(), nullable=False),
    sa.Column('exigir_pin', sa.Boolean(), nullable=False),
    sa.Column('registrar_presenca', sa.Boolean(), nullable=False),
    sa.Column('termo_biometria', sa.Text(), nullable=True),
    sa.Column('mensagem_boas_vindas', sa.String(length=200), nullable=True),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_acesso_config'))
    )
    op.create_table('acesso_catraca',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=True),
    sa.Column('driver', sa.Enum('controlid', 'henry', 'simulado', name='drivercatraca', native_enum=False, length=20), nullable=False),
    sa.Column('modo', sa.Enum('totem', 'agente', 'servidor', name='modoacionamento', native_enum=False, length=10), nullable=False),
    sa.Column('host', sa.String(length=200), nullable=True),
    sa.Column('porta', sa.Integer(), nullable=True),
    sa.Column('usar_https', sa.Boolean(), nullable=False),
    sa.Column('usuario', sa.String(length=120), nullable=True),
    sa.Column('senha_cifrada', sa.LargeBinary(), nullable=True),
    sa.Column('senha_final', sa.String(length=4), nullable=True),
    sa.Column('sentido_entrada', sa.String(length=20), nullable=False),
    sa.Column('acao_liberacao', sa.String(length=20), nullable=False),
    sa.Column('porta_rele', sa.Integer(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('ultimo_teste_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('ultimo_teste_ok', sa.Boolean(), nullable=True),
    sa.Column('ultimo_teste_detalhe', sa.String(length=300), nullable=True),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidade.id'], name=op.f('fk_acesso_catraca_unidade_id_unidade'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_acesso_catraca'))
    )
    op.create_table('acesso_consentimento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('aluno_id', sa.Integer(), nullable=False),
    sa.Column('texto_termo', sa.Text(), nullable=False),
    sa.Column('hash_termo', sa.String(length=64), nullable=False),
    sa.Column('coletado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('coletado_por_id', sa.Integer(), nullable=True),
    sa.Column('coletado_por_nome', sa.String(length=150), nullable=False),
    sa.Column('canal', sa.String(length=20), nullable=False),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('revogado_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('revogado_por_nome', sa.String(length=150), nullable=True),
    sa.Column('motivo_revogacao', sa.String(length=300), nullable=True),
    sa.ForeignKeyConstraint(['aluno_id'], ['aluno.id'], name=op.f('fk_acesso_consentimento_aluno_id_aluno'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['coletado_por_id'], ['usuario.id'], name=op.f('fk_acesso_consentimento_coletado_por_id_usuario'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_acesso_consentimento'))
    )
    op.create_index(op.f('ix_acesso_consentimento_aluno_id'), 'acesso_consentimento', ['aluno_id'], unique=False)
    op.create_table('acesso_credencial',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('aluno_id', sa.Integer(), nullable=False),
    sa.Column('pin_hash', sa.String(length=200), nullable=True),
    sa.Column('tentativas_erradas', sa.Integer(), nullable=False),
    sa.Column('bloqueado_ate', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('codigo_cadastro_hash', sa.String(length=64), nullable=True),
    sa.Column('codigo_cadastro_expira', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('codigo_cadastro_por_id', sa.Integer(), nullable=True),
    sa.Column('codigo_cadastro_por_nome', sa.String(length=150), nullable=True),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['aluno_id'], ['aluno.id'], name=op.f('fk_acesso_credencial_aluno_id_aluno'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['codigo_cadastro_por_id'], ['usuario.id'], name=op.f('fk_acesso_credencial_codigo_cadastro_por_id_usuario'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_acesso_credencial')),
    sa.UniqueConstraint('aluno_id', name=op.f('uq_acesso_credencial_aluno_id'))
    )
    op.create_table('acesso_dispositivo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('tipo', sa.Enum('totem', 'agente', name='tipodispositivo', native_enum=False, length=10), nullable=False),
    sa.Column('unidade_id', sa.Integer(), nullable=True),
    sa.Column('catraca_id', sa.Integer(), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=True),
    sa.Column('token_final', sa.String(length=4), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('revogado_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('ultimo_contato', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('criado_por_nome', sa.String(length=150), nullable=True),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['catraca_id'], ['acesso_catraca.id'], name=op.f('fk_acesso_dispositivo_catraca_id_acesso_catraca'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['unidade_id'], ['unidade.id'], name=op.f('fk_acesso_dispositivo_unidade_id_unidade'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_acesso_dispositivo')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_acesso_dispositivo_token_hash'))
    )
    op.create_table('acesso_descritor',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('aluno_id', sa.Integer(), nullable=False),
    sa.Column('consentimento_id', sa.Integer(), nullable=False),
    sa.Column('descritor_cifrado', sa.LargeBinary(), nullable=False),
    sa.Column('dimensao', sa.Integer(), nullable=False),
    sa.Column('modelo', sa.String(length=40), nullable=False),
    sa.Column('origem', sa.String(length=20), nullable=False),
    sa.Column('qualidade', sa.Float(), nullable=True),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('criado_por_nome', sa.String(length=150), nullable=True),
    sa.ForeignKeyConstraint(['aluno_id'], ['aluno.id'], name=op.f('fk_acesso_descritor_aluno_id_aluno'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['consentimento_id'], ['acesso_consentimento.id'], name=op.f('fk_acesso_descritor_consentimento_id_acesso_consentimento'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_acesso_descritor'))
    )
    op.create_index(op.f('ix_acesso_descritor_aluno_id'), 'acesso_descritor', ['aluno_id'], unique=False)
    op.create_table('acesso_registro',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('aluno_id', sa.Integer(), nullable=True),
    sa.Column('aluno_nome', sa.String(length=150), nullable=True),
    sa.Column('permitido', sa.Boolean(), nullable=False),
    sa.Column('codigo', sa.String(length=40), nullable=False),
    sa.Column('motivo', sa.String(length=300), nullable=False),
    sa.Column('metodo', sa.Enum('facial', 'cpf', 'codigo', 'qr', 'manual', name='metodoacesso', native_enum=False, length=10), nullable=False),
    sa.Column('sentido', sa.Enum('entrada', 'saida', name='sentido', native_enum=False, length=10), nullable=False),
    sa.Column('dispositivo_id', sa.Integer(), nullable=True),
    sa.Column('dispositivo_nome', sa.String(length=120), nullable=True),
    sa.Column('catraca_id', sa.Integer(), nullable=True),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('usuario_nome', sa.String(length=150), nullable=True),
    sa.Column('reserva_id', sa.Integer(), nullable=True),
    sa.Column('aula_descricao', sa.String(length=200), nullable=True),
    sa.Column('presenca_registrada', sa.Boolean(), nullable=False),
    sa.Column('similaridade', sa.Float(), nullable=True),
    sa.Column('previsto_sair', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('catraca_status', sa.String(length=20), nullable=True),
    sa.Column('catraca_detalhe', sa.String(length=300), nullable=True),
    sa.Column('qr_nonce', sa.String(length=40), nullable=True),
    sa.ForeignKeyConstraint(['aluno_id'], ['aluno.id'], name=op.f('fk_acesso_registro_aluno_id_aluno'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['catraca_id'], ['acesso_catraca.id'], name=op.f('fk_acesso_registro_catraca_id_acesso_catraca'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['dispositivo_id'], ['acesso_dispositivo.id'], name=op.f('fk_acesso_registro_dispositivo_id_acesso_dispositivo'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reserva_id'], ['reserva.id'], name=op.f('fk_acesso_registro_reserva_id_reserva'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], name=op.f('fk_acesso_registro_usuario_id_usuario'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_acesso_registro')),
    sa.UniqueConstraint('qr_nonce', name=op.f('uq_acesso_registro_qr_nonce'))
    )
    op.create_index('ix_acesso_registro_aluno_em', 'acesso_registro', ['aluno_id', 'em'], unique=False)
    op.create_index('ix_acesso_registro_em', 'acesso_registro', ['em'], unique=False)
    op.create_table('acesso_comando',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('catraca_id', sa.Integer(), nullable=False),
    sa.Column('acao', sa.String(length=20), nullable=False),
    sa.Column('sentido', sa.String(length=20), nullable=False),
    sa.Column('registro_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('criado_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('expira_em', app.core.db.UtcDateTime(timezone=True), nullable=False),
    sa.Column('entregue_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('concluido_em', app.core.db.UtcDateTime(timezone=True), nullable=True),
    sa.Column('resultado', sa.String(length=300), nullable=True),
    sa.ForeignKeyConstraint(['catraca_id'], ['acesso_catraca.id'], name=op.f('fk_acesso_comando_catraca_id_acesso_catraca'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['registro_id'], ['acesso_registro.id'], name=op.f('fk_acesso_comando_registro_id_acesso_registro'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_acesso_comando'))
    )
    op.create_index(op.f('ix_acesso_comando_catraca_id'), 'acesso_comando', ['catraca_id'], unique=False)
    op.create_index('ix_acesso_comando_status', 'acesso_comando', ['status', 'catraca_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_acesso_comando_status', table_name='acesso_comando')
    op.drop_index(op.f('ix_acesso_comando_catraca_id'), table_name='acesso_comando')
    op.drop_table('acesso_comando')
    op.drop_index('ix_acesso_registro_em', table_name='acesso_registro')
    op.drop_index('ix_acesso_registro_aluno_em', table_name='acesso_registro')
    op.drop_table('acesso_registro')
    op.drop_index(op.f('ix_acesso_descritor_aluno_id'), table_name='acesso_descritor')
    op.drop_table('acesso_descritor')
    op.drop_table('acesso_dispositivo')
    op.drop_table('acesso_credencial')
    op.drop_index(op.f('ix_acesso_consentimento_aluno_id'), table_name='acesso_consentimento')
    op.drop_table('acesso_consentimento')
    op.drop_table('acesso_catraca')
    op.drop_table('acesso_config')
