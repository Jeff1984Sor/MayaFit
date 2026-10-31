"""Planos do MayaFit e os recursos que cada um libera. Toda funcionalidade nova entra em RECURSOS (e no admin).

Portado do MayaJus (app/controle/planos.py): "robôs" viraram EXTRAS (módulos liberados estúdio a estúdio) e o limite
de notas por mês virou o limite de alunos ativos.
"""

from decimal import Decimal

from sqlalchemy import select

from app.controle.models import Plano

# chave → rótulo exibido no admin e no "Meu plano"
RECURSOS: dict[str, str] = {
    "gestao": "Agenda, alunos, contratos e financeiro",
    "site": "Site do estúdio (grátis)",
    "crm": "CRM de vendas (funil de leads e aula experimental)",
    "app_aluno": "App do aluno",
    "whatsapp": "Avisos por WhatsApp",
    "checkin": "Check-in por reconhecimento facial",
    "integracoes": "Integrações (TotalPass, Wellhub, API)",
    "ia": "Assistente de IA",
    "nfse": "Nota fiscal de serviço (NFS-e)",
    "catraca": "Integração com catraca",
}

# módulos extras, liberados estúdio a estúdio na ficha do admin (Estúdios › Ficha › Extras liberados)
EXTRAS: dict[str, str] = {
    "receita_saude": "Recibos Receita Saúde",
    "etl": "Migração de dados do sistema antigo",
    "catraca": "Integração com catraca (avulsa, para quem não tem o plano Rede)",
}

ESSENCIAL = ["gestao", "site", "crm"]
ESTUDIO = [*ESSENCIAL, "app_aluno", "whatsapp", "checkin", "integracoes"]
PRO = [*ESTUDIO, "ia", "nfse"]
TODOS = list(RECURSOS)

# teste grátis padrão de um estúdio novo (pelo admin e pela aprovação do cadastro do site): 2 meses
DIAS_TESTE_PADRAO = 60

PRECO_ALUNO_EXCEDENTE = Decimal("0.50")  # por aluno ativo acima do limite do plano
PRECO_USUARIO_ADICIONAL = Decimal("14.90")  # por usuário acima do limite do plano

PADRAO = [
    # nome, mensal, anual, usuários, alunos ativos (None = ilimitado), recursos
    ("Essencial", "49.90", "499.00", 2, 60, ESSENCIAL),
    ("Estúdio", "89.90", "899.00", 5, 150, ESTUDIO),
    ("Pro", "149.90", "1499.00", 10, 350, PRO),
    ("Rede", "289.90", "2899.00", 25, None, TODOS),
]


def garantir_padrao(db) -> None:
    """Na primeira vez cria a tabela de planos da MayaCorp (depois ela é editada no admin)."""
    if db.scalar(select(Plano.id).limit(1)):
        return
    for ordem, (nome, mensal, anual, usuarios, alunos, recursos) in enumerate(PADRAO):
        db.add(Plano(nome=nome, preco_mensal=Decimal(mensal), preco_anual=Decimal(anual), usuarios=usuarios,
                     alunos_ativos=alunos, preco_aluno_excedente=PRECO_ALUNO_EXCEDENTE,
                     preco_usuario_adicional=PRECO_USUARIO_ADICIONAL, recursos=list(recursos), ativo=True, ordem=ordem))
    db.commit()
