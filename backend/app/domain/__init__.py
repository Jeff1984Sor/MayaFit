"""Regras de negócio do MayaFit (estúdios) como funções puras.

Cada módulo cita o arquivo/linha do sistema antigo (Django) de onde a regra foi extraída e tem
testes de caracterização ("golden master") em ``backend/tests/domain/`` com valores gerados rodando o
código antigo de verdade. Nada aqui acessa banco, FastAPI, Django ou relógio: quem chama passa ``agora``/``hoje``.

Mapa regra -> módulo (ver docs/MIGRACAO.md):
R1 precos · R2 parcelas · R3 capacidade · R4 reposicao · R5/R6 status_aula · R7 financeiro ·
R8 receita_saude · R9 whatsapp_avisos · R10 tokens_legados · R13 contratos · R16 documentos/telefone ·
R17 comissao · agenda (geração de slots, bloqueios, agenda do contrato).
"""
