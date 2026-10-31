"""Espelho da NFS-e em PDF (reportlab).

O documento oficial é o DANFSe do ADN (Padrão Nacional) ou a página da Prefeitura (SP); este espelho acompanha o
e-mail ao aluno e é o único PDF nos modos simulado/teste, sempre marcado "SEM VALOR FISCAL" nesses casos.
"""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.modules.nfse import regras
from app.modules.nfse.models import ConfigNfse, NotaFiscal

NAVY = colors.HexColor("#1E2D6B")
CINZA = colors.HexColor("#5B6378")


def _quebrar(texto: str, largura: int = 95) -> list[str]:
    linhas: list[str] = []
    for par in (texto or "").splitlines() or [""]:
        atual = ""
        for palavra in par.split():
            if len(atual) + len(palavra) + 1 > largura:
                linhas.append(atual)
                atual = palavra
            else:
                atual = f"{atual} {palavra}".strip()
        linhas.append(atual)
    return linhas


def espelho(nota: NotaFiscal, cfg: ConfigNfse, nome_estudio: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    larg, alt = A4
    sem_valor = nota.modo != "producao"
    c.setTitle(f"NFS-e {nota.numero_nfse or nota.numero_dps}")

    c.setFillColor(NAVY)
    c.rect(0, alt - 30 * mm, larg, 30 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(15 * mm, alt - 14 * mm, "Nota Fiscal de Serviço Eletrônica")
    c.setFont("Helvetica", 10)
    c.drawString(15 * mm, alt - 21 * mm, f"Espelho para conferência · {nome_estudio}")
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(larg - 15 * mm, alt - 14 * mm, f"Nº {nota.numero_nfse or '—'}")
    c.setFont("Helvetica", 9)
    c.drawRightString(larg - 15 * mm, alt - 21 * mm, f"DPS/RPS {nota.serie}-{nota.numero_dps}")

    if sem_valor:
        c.saveState()
        c.setFillColor(colors.HexColor("#C94343"))
        c.setFont("Helvetica-Bold", 44)
        c.translate(larg / 2, alt / 2)
        c.rotate(30)
        c.setFillAlpha(0.15)
        c.drawCentredString(0, 0, "SEM VALOR FISCAL")
        c.restoreState()

    y = alt - 42 * mm

    def bloco(titulo: str, linhas: list[tuple[str, str]]):
        nonlocal y
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(15 * mm, y, titulo.upper())
        y -= 6 * mm
        for rotulo, valor in linhas:
            c.setFillColor(CINZA)
            c.setFont("Helvetica", 8)
            c.drawString(15 * mm, y, rotulo)
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 10)
            c.drawString(55 * mm, y, str(valor or "—")[:90])
            y -= 5.5 * mm
        y -= 3 * mm

    bloco("Prestador", [
        ("Razão social", cfg.razao_social), ("CNPJ", regras.formatar_documento(cfg.cnpj)),
        ("Inscrição municipal", cfg.inscricao_municipal), ("Município", f"{cfg.municipio_nome or ''} {cfg.uf or ''}".strip()),
    ])
    bloco("Tomador", [
        ("Nome", nota.tomador_nome), ("CPF/CNPJ", regras.formatar_documento(nota.tomador_documento)),
        ("E-mail", nota.tomador_email),
    ])
    bloco("Serviço", [
        ("Item LC 116", f"{nota.item_lista_servico} (trib. nacional {nota.codigo_tributacao_nacional})"),
        ("Competência", regras.competencia_texto(nota.competencia)),
        ("Emitida em", f"{nota.emitida_em:%d/%m/%Y %H:%M}" if nota.emitida_em else None),
        ("Chave de acesso", nota.chave_acesso), ("Código de verificação", nota.codigo_verificacao),
    ])
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, y, "DISCRIMINAÇÃO")
    y -= 6 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    for linha in _quebrar(nota.discriminacao)[:25]:
        c.drawString(15 * mm, y, linha)
        y -= 4.5 * mm
    y -= 4 * mm
    bloco("Valores", [
        ("Valor do serviço", regras.brl(nota.valor_servico)), ("Deduções", regras.brl(nota.deducoes)),
        ("Alíquota ISS", f"{nota.aliquota:.2f}%".replace(".", ",")),
        ("ISS", regras.brl(nota.valor_iss) + (" (retido pelo tomador)" if nota.iss_retido else "")),
    ])
    if nota.link_oficial:
        c.setFillColor(CINZA)
        c.setFont("Helvetica", 8)
        c.drawString(15 * mm, 18 * mm, "Consulte a nota oficial em:")
        c.setFillColor(NAVY)
        c.drawString(15 * mm, 14 * mm, nota.link_oficial[:120])
    c.setFillColor(CINZA)
    c.setFont("Helvetica", 7)
    c.drawRightString(larg - 15 * mm, 8 * mm, "Gerado pelo MayaFit · MayaCorp")
    c.showPage()
    c.save()
    return buf.getvalue()
