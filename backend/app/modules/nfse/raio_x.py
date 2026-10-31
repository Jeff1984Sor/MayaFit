"""Raio-x ANTES de emitir: confere configuração, tomadores, valores e histórico e devolve uma nota de saúde (0–100)
com cada achado em português claro + ação. Erros bloqueiam o botão Emitir; avisos só pedem atenção.

Checagens (numeradas no docs/progresso-nfse.md, seção "Regras fiscais"):
- configuração: pendências do assistente (CNPJ, município, CCM, certificado, modo x servidor...)
- tomador: CPF/CNPJ obrigatório e válido; nome; e-mail quando o envio automático está ligado
- valor > 0; competência não pode ser futura; discriminação até 2000 caracteres
- duplicidade: recebimento já com nota viva (erro) · mesmo tomador e mesmo valor com nota no mês (aviso)
- ISS estimado do lote (Decimal) e totais
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.financeiro.models import ContaReceber
from app.modules.nfse import regras, servico
from app.modules.nfse.models import NotaFiscal, StatusNota


def _achado(nivel: str, titulo: str, mensagem: str, acao: str, *, link: str | None = None,
            itens: list[int] | None = None) -> dict[str, Any]:
    return {"nivel": nivel, "titulo": titulo, "mensagem": mensagem, "acao": acao, "link": link, "itens": itens or []}


def analisar(db: Session, rascunhos: list[servico.Rascunho]) -> dict[str, Any]:
    cfg = servico.obter_config(db)
    achados: list[dict[str, Any]] = []
    for p in servico.pendencias_config(cfg):
        achados.append(_achado(p["nivel"], "Configuração", p["mensagem"], p["acao"], link=p["link"]))

    sem_doc, doc_invalido, sem_email, futuras, longas, zeradas, ja_tem, dobro = [], [], [], [], [], [], [], []
    h = servico.hoje()
    ini_mes = h.replace(day=1)
    for i, r in enumerate(rascunhos):
        for p in r.problemas:
            achados.append(_achado(p["nivel"], r.tomador_nome, p["mensagem"], p["acao"], link=p.get("link"), itens=[i]))
        if not r.tomador_documento:
            sem_doc.append(i)
        elif not regras.documento_valido(r.tomador_documento):
            doc_invalido.append(i)
        if cfg.enviar_email_aluno and not r.tomador_email:
            sem_email.append(i)
        if r.competencia > h:
            futuras.append(i)
        if len(r.discriminacao or "") > 2000 or not (r.discriminacao or "").strip():
            longas.append(i)
        if r.valor <= 0:
            zeradas.append(i)
        if r.conta_receber_id and (n := servico.nota_do_recebimento(db, r.conta_receber_id)) and n.status != StatusNota.cancelada:
            ja_tem.append((i, n))
        elif r.tomador_documento:
            parecida = db.scalar(select(NotaFiscal).where(
                NotaFiscal.tomador_documento == r.tomador_documento, NotaFiscal.valor_servico == regras.centavos(r.valor),
                NotaFiscal.status == StatusNota.emitida, NotaFiscal.competencia >= ini_mes).limit(1))
            if parecida:
                dobro.append((i, parecida))

    def nomes(idx: list[int]) -> str:
        lista = [rascunhos[i].tomador_nome for i in idx]
        return ", ".join(lista[:4]) + (f" e mais {len(lista) - 4}" if len(lista) > 4 else "")

    if sem_doc:
        achados.append(_achado("erro", "CPF obrigatório", f"Sem CPF/CNPJ: {nomes(sem_doc)}.",
                               "Cadastre o CPF no cadastro do aluno e volte aqui.",
                               link=f"/alunos/{rascunhos[sem_doc[0]].aluno_id}" if rascunhos[sem_doc[0]].aluno_id else None,
                               itens=sem_doc))
    if doc_invalido:
        achados.append(_achado("erro", "CPF/CNPJ inválido", f"Documento com dígito verificador errado: {nomes(doc_invalido)}.",
                               "Corrija o CPF/CNPJ: a prefeitura recusaria a nota.", itens=doc_invalido))
    if zeradas:
        achados.append(_achado("erro", "Valor", "Nota sem valor.", "Informe um valor maior que zero.", itens=zeradas))
    if futuras:
        achados.append(_achado("erro", "Competência futura", f"Competência posterior a hoje: {nomes(futuras)}.",
                               "Use o mês do serviço já prestado (no máximo o mês atual).", itens=futuras))
    if longas:
        achados.append(_achado("erro", "Discriminação", "Discriminação vazia ou com mais de 2000 caracteres.",
                               "Ajuste o texto (ou o modelo em Configurações › NFS-e).", itens=longas))
    if ja_tem:
        i, n = ja_tem[0]
        achados.append(_achado("erro", "Já existe nota", f"{len(ja_tem)} recebimento(s) já têm nota "
                               f"({rascunhos[i].tomador_nome}: {servico.ROTULO_STATUS.get(str(n.status), n.status)}).",
                               "Abra a nota existente; para emitir outra, cancele a anterior.", link=f"/nfse/{n.id}",
                               itens=[x for x, _ in ja_tem]))
    if dobro:
        i, n = dobro[0]
        achados.append(_achado("aviso", "Possível nota em dobro", f"{rascunhos[i].tomador_nome} já recebeu a NFS-e "
                               f"nº {n.numero_nfse or n.numero_dps} com o mesmo valor ({regras.brl(n.valor_servico)}) neste mês.",
                               "Confira antes de emitir.", link=f"/nfse/{n.id}", itens=[x for x, _ in dobro]))
    if sem_email:
        achados.append(_achado("aviso", "Sem e-mail", f"{len(sem_email)} tomador(es) sem e-mail: a nota não será enviada "
                               f"por e-mail ({nomes(sem_email)}).", "Cadastre o e-mail do aluno se quiser o envio.",
                               itens=sem_email))
    if str(cfg.modo) != "producao":
        achados.append(_achado("info", "Ambiente de teste",
                               "Modo " + ("simulado (nada sai do servidor)" if str(cfg.modo) == "simulado" else
                                          "Teste/homologação") + ": as notas NÃO têm valor fiscal.",
                               "Quando tudo estiver certo, mude para Produção em Configurações › NFS-e.",
                               link="/configuracoes/nfse"))

    total = sum((regras.centavos(r.valor) for r in rascunhos), Decimal("0"))
    iss = Decimal("0")
    if cfg.regime != "mei":
        for r in rascunhos:
            try:
                iss += regras.calcular_iss(r.valor, cfg.aliquota_iss, regime=cfg.regime).valor_iss
            except ValueError:
                pass
    erros = sum(1 for a in achados if a["nivel"] == "erro")
    avisos = sum(1 for a in achados if a["nivel"] == "aviso")
    score = max(0, 100 - erros * 25 - avisos * 8)
    frase = ("Tudo certo. Pode emitir." if erros == 0 and avisos == 0 else
             "Pode emitir, mas vale olhar os avisos." if erros == 0 else
             "Corrija os erros antes de emitir.")
    return {
        "score": score, "frase": frase, "pode_emitir": erros == 0, "achados": achados, "quantidade": len(rascunhos),
        "valor_total": total, "iss_estimado": iss, "iss_no_das": cfg.regime in ("mei", "simples"),
        "aliquota": cfg.aliquota_iss, "modo": str(cfg.modo), "provedor": str(cfg.provedor),
        "previa": [{"tomador": r.tomador_nome, "documento": regras.formatar_documento(r.tomador_documento),
                    "valor": regras.centavos(r.valor), "competencia": r.competencia, "discriminacao": r.discriminacao}
                   for r in rascunhos[:5]],
    }


def de_recebimentos(db: Session, ids: list[int]) -> list[servico.Rascunho]:
    cfg = servico.obter_config(db)
    contas = db.scalars(select(ContaReceber).where(ContaReceber.id.in_(ids))).all()
    return [servico.rascunho_de_recebimento(db, cfg, c) for c in contas]
