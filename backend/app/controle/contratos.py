"""Contrato da MayaCorp com o estúdio: modelo com {{variaveis}} → texto final → PDF → e-mail."""

import re
from datetime import date
from decimal import Decimal
from io import BytesIO

from app.controle.models import Cliente

VARIAVEIS: dict[str, str] = {
    "cliente_nome": "Nome do estúdio",
    "cliente_documento": "CNPJ/CPF do estúdio",
    "responsavel": "Responsável pelo contrato",
    "email_financeiro": "E-mail do financeiro",
    "plano": "Plano contratado",
    "ciclo": "Mensal ou anual",
    "valor": "Valor do ciclo (R$)",
    "valor_mensal": "Valor mensal do plano (R$)",
    "valor_anual": "Valor anual do plano (R$)",
    "usuarios": "Usuários incluídos",
    "alunos_ativos": "Alunos ativos incluídos",
    "aluno_excedente": "Valor por aluno ativo além do plano (R$)",
    "usuario_adicional": "Valor do usuário adicional (R$)",
    "desconto_indicacao": "Desconto por indicação (%)",
    "valor_com_desconto": "Valor do ciclo com o desconto (R$)",
    "data_inicio": "Início do contrato",
    "data_hoje": "Data de hoje",
}

_VAR = re.compile(r"{{\s*([a-z_]+)\s*}}")


def brl(v: Decimal | None) -> str:
    """1234.5 → "1.234,50" (sem o "R$", que o modelo escreve)."""
    if v is None:
        return ""
    return f"{Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_documento(d: str | None) -> str:
    d = re.sub(r"\D", "", d or "")
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return d


def valores(c: Cliente) -> dict[str, str]:
    from sqlalchemy.orm import object_session

    from app.controle import indicacao

    p = c.plano
    anual = c.ciclo == "anual"
    db = object_session(c)
    _, pct = indicacao.desconto(db, c) if db is not None else (0, Decimal(0))
    ciclo = (p.preco_anual if anual else p.preco_mensal) if p else None
    return {
        "cliente_nome": c.nome, "cliente_documento": formatar_documento(c.documento), "responsavel": c.responsavel or "",
        "email_financeiro": c.email_financeiro or "", "plano": p.nome if p else "", "ciclo": "anual" if anual else "mensal",
        "valor": brl(ciclo), "valor_mensal": brl(p.preco_mensal if p else None),
        "valor_anual": brl(p.preco_anual if p else None),
        "usuarios": (str(p.usuarios) if p.usuarios else "ilimitados") if p else "",
        "alunos_ativos": (str(p.alunos_ativos) if p.alunos_ativos else "ilimitados") if p else "",
        "aluno_excedente": brl(p.preco_aluno_excedente if p else None),
        "usuario_adicional": brl(p.preco_usuario_adicional if p else None),
        "desconto_indicacao": f"{pct:.2f}".rstrip("0").rstrip(".").replace(".", ","),
        "valor_com_desconto": brl(indicacao.aplicar(ciclo, pct)),
        "data_inicio": f"{c.inicio_contrato:%d/%m/%Y}" if c.inicio_contrato else "",
        "data_hoje": f"{date.today():%d/%m/%Y}",
    }


def preencher(corpo: str, c: Cliente) -> tuple[str, list[str]]:
    """Texto final e as variáveis que ficaram sem valor (para o admin conferir antes de enviar)."""
    vals = valores(c)
    vazias: list[str] = []

    def troca(m: re.Match) -> str:
        chave = m.group(1)
        if chave not in vals:
            return m.group(0)
        if not vals[chave]:
            vazias.append(chave)
        return vals[chave]

    return _VAR.sub(troca, corpo), sorted(set(vazias))


def desconhecidas(corpo: str) -> list[str]:
    return sorted({m for m in _VAR.findall(corpo) if m not in VARIAVEIS})


def pdf(titulo: str, corpo: str, emitente: str) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    base = getSampleStyleSheet()
    titulo_st = ParagraphStyle("t", parent=base["Title"], fontSize=14, spaceAfter=6 * mm)
    texto_st = ParagraphStyle("p", parent=base["BodyText"], fontSize=10, leading=14, spaceAfter=3 * mm)
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm,
                            bottomMargin=20 * mm, title=titulo, author=emitente)
    story = [Paragraph(escape(titulo), titulo_st)]
    for bloco in re.split(r"\n\s*\n", corpo.strip()):
        story.append(Paragraph(escape(bloco).replace("\n", "<br/>"), texto_st))
    story.append(Spacer(1, 4 * mm))

    def rodape(canvas, d):
        canvas.setFont("Helvetica", 7)
        canvas.drawString(22 * mm, 10 * mm, f"{emitente} · {titulo} · página {d.page}")

    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()
