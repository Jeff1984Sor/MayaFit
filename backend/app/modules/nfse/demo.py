"""Dados de demonstração da NFS-e (dados SINTÉTICOS; o coordenador chama `popular_demo(db)` a partir do seed).

Idempotente: configura o modo SIMULADO só se a NFS-e ainda não foi configurada e cria as notas de exemplo pelas
chaves `demo:<n>` (rodar de novo não duplica nada). Passa pelo fluxo real (XML montado, assinado, validado no XSD
e "enviado" ao simulador), então o detalhe de cada nota mostra XML, linha do tempo e raio-x de verdade.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.nfse import regras, servico
from app.modules.nfse.models import Modo, NotaFiscal, Provedor, StatusNota

CNPJ_DEMO = "11222333000181"  # CNPJ sintético (dígitos verificadores válidos)


def _cpf(base: int) -> str:
    d = [int(c) for c in f"{base:09d}"]
    for _ in range(2):
        s = sum(v * w for v, w in zip(d, range(len(d) + 1, 1, -1), strict=False))
        d.append((s * 10 % 11) % 10)
    return "".join(map(str, d))


# (nome, base do CPF, valor, meses atrás, descrição, destino)
EXEMPLOS = [
    ("Ana Beatriz Rocha", 201000001, "320.00", 0, "Pilates 2x por semana", "emitida"),
    ("Carlos Eduardo Lima", 201000002, "450.00", 0, "Pilates 3x por semana", "emitida"),
    ("Fernanda Alves", 201000003, "280.00", 0, "Funcional 2x por semana", "emitida"),
    ("Gustavo Pereira", 201000004, "320.00", 1, "Pilates 2x por semana", "emitida"),
    ("Helena Martins", 201000005, "520.00", 1, "Pilates individual", "emitida"),
    ("Igor Santana", 201000006, "320.00", 2, "Pilates 2x por semana", "emitida"),
    ("Juliana Castro", 0, "390.00", 0, "Pilates 2x por semana", "rejeitada"),  # CPF inválido
    ("Marcos Vieira", 201000008, "300.00", 0, "Funcional 3x por semana", "cancelada"),
    ("Patrícia Gomes", 201000009, "350.00", 0, "Pilates 2x por semana", "pendente"),
]


def popular_demo(db: Session) -> dict:
    cfg = servico.obter_config(db)
    if not cfg.cnpj:
        cfg.ativo = True
        cfg.provedor = Provedor.nacional
        cfg.modo = Modo.simulado
        cfg.cnpj = CNPJ_DEMO
        cfg.razao_social = "Estudio Demonstracao Ltda"
        cfg.inscricao_municipal = "123456"
        cfg.codigo_municipio = "3509502"
        cfg.municipio_nome = "Campinas"
        cfg.uf = "SP"
        cfg.regime = "simples"
        cfg.item_lista_servico = "06.04"
        cfg.codigo_tributacao_nacional = "060401"
        cfg.aliquota_iss = Decimal("2.00")
        cfg.percentual_tributos_sn = Decimal("6.00")
        cfg.enviar_email_aluno = False
        cfg.discriminacao_modelo = regras.DISCRIMINACAO_PADRAO
        db.commit()
    if cfg.modo != Modo.simulado:
        return {"criadas": 0, "motivo": "NFS-e já configurada fora do modo simulado: a demonstração não mexe."}

    hoje = servico.hoje()
    criadas = 0
    for i, (nome, base, valor, meses, desc, destino) in enumerate(EXEMPLOS, start=1):
        chave = f"demo:{i}"
        if db.scalar(select(NotaFiscal.id).where(NotaFiscal.chave_emissao.like(f"{chave}%"))):
            continue
        comp = (hoje.replace(day=1) - timedelta(days=28 * meses)).replace(day=1)
        cpf = _cpf(base) if base else "12345678900"  # CPF com dígito errado: o simulador recusa (raio-x)
        r = servico.Rascunho(
            chave=chave, origem="demo", tomador_tipo="pessoa", tomador_nome=nome, tomador_documento=cpf,
            tomador_email=None, valor=Decimal(valor), competencia=comp,
            discriminacao=regras.renderizar_discriminacao(cfg.discriminacao_modelo, {
                "aluno": nome, "descricao": desc, "competencia": regras.competencia_texto(comp),
                "valor": regras.brl(valor), "cpf": regras.formatar_documento(cpf)}),
        )
        nota, criada = servico.enfileirar(db, r)
        db.commit()
        criadas += int(criada)
        if destino == "pendente":
            continue  # fica na fila (o worker envia na próxima passada)
        servico.processar(db, nota)
        if destino == "cancelada" and nota.status == StatusNota.emitida:
            servico.cancelar(db, nota, "1", "Emitida em duplicidade (exemplo de cancelamento)", None)
    db.commit()
    criadas += _notas_de_recebimentos(db)
    return {"criadas": criadas}


def _notas_de_recebimentos(db: Session, quantas: int = 8) -> int:
    """Notas dos últimos recebimentos PAGOS de alunos (quando o estúdio já tem financeiro): o mesmo fluxo da tela
    "Emitir pelos recebimentos". Idempotente pela chave do recebimento."""
    from app.modules.financeiro.models import ContaReceber, StatusReceber

    pagos = db.scalars(select(ContaReceber).where(ContaReceber.status == StatusReceber.PAGO, ContaReceber.contrato_id.is_not(None))
                       .order_by(ContaReceber.pagamento.desc(), ContaReceber.id.desc()).limit(quantas)).all()
    criadas = 0
    for conta in pagos:
        if servico.nota_do_recebimento(db, conta.id) is not None:
            continue
        try:
            nota = servico.enfileirar_recebimento(db, conta.id, origem="recebimento")
        except HTTPException:  # recebimento com pendência (ex.: aluno sem CPF): fica para a tela mostrar
            db.rollback()
            continue
        db.commit()
        servico.processar(db, nota)
        db.commit()
        criadas += 1
    return criadas
