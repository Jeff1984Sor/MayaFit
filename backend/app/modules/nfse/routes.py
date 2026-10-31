"""Rotas da NFS-e (`/api/nfse/*`). Login exigido no include; permissões do recurso `nfse`:

- `nfse.ver`        painel, lista, detalhe, PDF/XML, configuração (sem segredos)
- `nfse.emitir`     raio-x, emissão avulsa e por recebimentos, correção, reenvio, e-mail, busca de tomador
- `nfse.cancelar`   cancelamento (com motivo)
- `nfse.configurar` assistente fiscal, certificado A1, teste de conexão
Professor não tem nenhuma (perfil padrão sem financeiro).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select

from app.core.deps import Ctx
from app.core.permissoes import adicionar_regras
from app.core.schemas import Mensagem
from app.domain.documentos import so_digitos
from app.modules.alunos.models import Aluno
from app.modules.alunos.servico import mascarar_cpf
from app.modules.nfse import municipios, provedores, raio_x, regras, servico
from app.modules.nfse import schemas as sc
from app.modules.nfse.models import NotaFiscal
from app.modules.nfse.provedores.base import ErroConfiguracao, FalhaComunicacao

router = APIRouter(prefix="/nfse", tags=["nfse"])

adicionar_regras([
    ("*", r"/nfse/configuracao/(certificado|testar)", "nfse.configurar"),
    ("GET", r"/nfse/configuracao/municipio", "nfse.configurar"),
    ("PUT", r"/nfse/configuracao$", "nfse.configurar"),
    ("POST", r"/nfse/notas/\d+/cancelar$", "nfse.cancelar"),
    ("GET", r"/nfse/(recebimentos|tomadores)", "nfse.emitir"),
    ("POST", r"/nfse/", "nfse.emitir"),
    ("PATCH", r"/nfse/notas/\d+$", "nfse.emitir"),
    ("GET", r"/nfse(/|$)", "nfse.ver"),
])


def _decimais_como_texto(obj):
    """Dinheiro sai como texto ("300.00"), igual aos endpoints com response_model (nunca float)."""
    if isinstance(obj, Decimal):
        return f"{obj:.2f}"
    if isinstance(obj, dict):
        return {k: _decimais_como_texto(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimais_como_texto(v) for v in obj]
    return obj


def _nota(ctx: Ctx, nota_id: int) -> NotaFiscal:
    n = ctx.db.get(NotaFiscal, nota_id)
    if n is None:
        raise HTTPException(404, "Nota não encontrada.")
    return n


# ================================================================================================ painel e lista
@router.get("/painel")
def painel(ctx: Ctx):
    return _decimais_como_texto(servico.painel(ctx.db))


@router.get("/notas", response_model=sc.ListaNotas)
def listar(ctx: Ctx, status: str | None = Query(None, pattern="^(pendente|processando|emitida|validada|rejeitada|falha|cancelada|atencao)$"),
           q: str | None = Query(None, max_length=100), de: date | None = None, ate: date | None = None,
           origem: str | None = Query(None, pattern="^(avulsa|recebimento|automatica|demo)$"),
           pagina: int = Query(1, ge=1), por_pagina: int = Query(25, ge=1, le=100)):
    return servico.listar(ctx.db, status=status, q=q, de=de, ate=ate, origem=origem, pagina=pagina, por_pagina=por_pagina)


@router.get("/notas/{nota_id:int}", response_model=sc.NotaDetalhe)
def detalhe(nota_id: int, ctx: Ctx):
    return servico.detalhe(ctx.db, _nota(ctx, nota_id))


@router.get("/notas/{nota_id:int}/xml")
def baixar_xml(nota_id: int, ctx: Ctx, tipo: str = Query("enviado", pattern="^(enviado|retorno)$")):
    n = _nota(ctx, nota_id)
    xml = n.xml_enviado if tipo == "enviado" else n.xml_retorno
    if not xml:
        raise HTTPException(404, "Esta nota não tem esse XML.")
    nome = f"nfse-{n.serie}-{n.numero_dps}-{tipo}.xml"
    return Response(xml.encode("utf-8"), media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"', "X-Content-Type-Options": "nosniff"})


@router.get("/notas/{nota_id:int}/pdf")
def baixar_pdf(nota_id: int, ctx: Ctx):
    n = _nota(ctx, nota_id)
    if str(n.status) not in ("emitida", "validada", "cancelada"):
        raise HTTPException(409, "O PDF fica disponível depois da emissão.")
    return Response(servico.pdf_da_nota(ctx.db, n), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="nfse-{n.numero_nfse or n.numero_dps}.pdf"',
                             "X-Content-Type-Options": "nosniff"})


# ================================================================================================ emissão
@router.post("/raio-x")
def analisar(dados: sc.RaioXIn, ctx: Ctx):
    cfg = servico.obter_config(ctx.db)
    if dados.avulsa:
        rascunhos = [servico.rascunho_avulso(ctx.db, cfg, dados.avulsa)]
    elif dados.recebimentos:
        rascunhos = raio_x.de_recebimentos(ctx.db, dados.recebimentos)
    else:
        raise HTTPException(422, "Informe a nota avulsa ou os recebimentos.")
    resultado = raio_x.analisar(ctx.db, rascunhos)
    ctx.db.rollback()  # o raio-x não grava nada (nem a configuração padrão)
    return _decimais_como_texto(resultado)


@router.post("/notas", response_model=sc.NotaDetalhe, status_code=201)
def emitir_avulsa(dados: sc.NotaAvulsaIn, ctx: Ctx):
    cfg = servico.obter_config(ctx.db)
    bloqueios = servico.pendencias_bloqueantes(cfg)
    if bloqueios:
        raise HTTPException(409, f"Configuração incompleta: {bloqueios[0]['mensagem']} {bloqueios[0]['acao']}")
    r = servico.rascunho_avulso(ctx.db, cfg, dados)
    if not regras.documento_valido(r.tomador_documento):
        raise HTTPException(422, "CPF/CNPJ do tomador ausente ou inválido: a nota exige um documento válido.")
    nota, criada = servico.enfileirar(ctx.db, r, usuario_id=ctx.usuario.id)
    if not criada:
        raise HTTPException(409, f"Este recebimento já tem a nota #{nota.id} ({servico.ROTULO_STATUS.get(str(nota.status))}).")
    ctx.auditar("emitir", "nfse", nota.id, f"NFS-e avulsa para {nota.tomador_nome} ({regras.brl(nota.valor_servico)})")
    ctx.db.commit()
    servico.processar(ctx.db, nota)
    ctx.db.refresh(nota)
    return servico.detalhe(ctx.db, nota)


@router.get("/recebimentos", response_model=list[sc.RecebimentoOut])
def recebimentos(ctx: Ctx, de: date | None = None, ate: date | None = None,
                 situacao: str = Query("sem_nota", pattern="^(sem_nota|com_nota|todos)$"),
                 q: str | None = Query(None, max_length=100)):
    return servico.recebimentos(ctx.db, de=de, ate=ate, situacao=situacao, q=q)


@router.post("/recebimentos/emitir", response_model=sc.LoteOut)
def emitir_recebimentos(dados: sc.RecebimentosIn, ctx: Ctx):
    res = servico.emitir_lote(ctx.db, dados.ids, ctx.usuario.id)
    ctx.auditar("emitir_lote", "nfse", res["lote"], f"{res['criadas']} nota(s) a partir de recebimentos")
    ctx.db.commit()
    return res


@router.patch("/notas/{nota_id:int}", response_model=sc.NotaDetalhe)
def corrigir(nota_id: int, dados: sc.CorrecaoIn, ctx: Ctx):
    if dados.tomador_documento and not regras.documento_valido(dados.tomador_documento):
        raise HTTPException(422, "CPF/CNPJ inválido.")
    n = servico.corrigir(ctx.db, _nota(ctx, nota_id), dados, ctx.usuario.id)
    ctx.auditar("corrigir", "nfse", n.id, "Correção de nota rejeitada")
    ctx.db.commit()
    return servico.detalhe(ctx.db, n)


@router.post("/notas/{nota_id:int}/reprocessar", response_model=sc.NotaDetalhe)
def reprocessar(nota_id: int, ctx: Ctx):
    n = servico.reprocessar(ctx.db, _nota(ctx, nota_id), ctx.usuario.id)
    return servico.detalhe(ctx.db, n)


@router.post("/notas/{nota_id:int}/consultar", response_model=sc.NotaDetalhe)
def consultar(nota_id: int, ctx: Ctx):
    """Pergunta ao provedor se a nota existe (útil depois de falha de comunicação)."""
    n = _nota(ctx, nota_id)
    if str(n.status) not in ("pendente", "falha", "rejeitada"):
        return servico.detalhe(ctx.db, n)
    cfg = servico.obter_config(ctx.db)
    try:
        prov = servico.provedor_para(cfg, modo=str(n.modo), provedor=str(n.provedor))
        achada = prov.consultar(servico.dados_da_nota(n, cfg))
    except ErroConfiguracao as e:
        raise HTTPException(409, str(e)) from None
    except FalhaComunicacao:
        raise HTTPException(503, "O provedor não respondeu. Tente de novo em alguns minutos.") from None
    if achada:
        servico._aplicar(ctx.db, n, achada, cfg)
        ctx.db.commit()
        servico._pos_emissao(ctx.db, n, cfg, prov)
    else:
        servico.evento(ctx.db, n, "consulta", "Consulta ao provedor: nenhuma nota encontrada para esta DPS/RPS.",
                       ctx.usuario.id)
    ctx.db.commit()
    return servico.detalhe(ctx.db, n)


@router.post("/notas/{nota_id:int}/cancelar", response_model=sc.NotaDetalhe)
def cancelar(nota_id: int, dados: sc.CancelarIn, ctx: Ctx):
    n = _nota(ctx, nota_id)
    ctx.auditar("cancelar", "nfse", n.id, f"Cancelamento: {dados.motivo}")
    n = servico.cancelar(ctx.db, n, dados.codigo, dados.motivo, ctx.usuario.id)
    return servico.detalhe(ctx.db, n)


@router.post("/notas/{nota_id:int}/email", response_model=Mensagem)
def reenviar_email(nota_id: int, ctx: Ctx):
    n = _nota(ctx, nota_id)
    if str(n.status) not in ("emitida", "validada"):
        raise HTTPException(409, "Só notas emitidas podem ser enviadas por e-mail.")
    ok = servico.enviar_email(ctx.db, n)
    ctx.db.commit()
    if not ok:
        raise HTTPException(502, "Não foi possível enviar o e-mail. Confira Configurações › E-mail.")
    return Mensagem(mensagem=f"Nota enviada para {n.tomador_email}.")


@router.get("/tomadores", response_model=list[sc.TomadorBusca])
def buscar_tomadores(ctx: Ctx, q: str = Query(..., min_length=2, max_length=100)):
    dig = so_digitos(q)
    conds = [Aluno.nome.ilike(f"%{q.strip()}%")]
    if len(dig) >= 3:
        conds.append(Aluno.cpf.like(f"{dig}%"))
    alunos = ctx.db.scalars(select(Aluno).where(or_(*conds)).order_by(Aluno.nome).limit(10)).all()
    return [{"id": a.id, "nome": a.nome, "cpf_mascarado": mascarar_cpf(a.cpf), "tem_cpf": bool(a.cpf),
             "email": a.email} for a in alunos]


# ================================================================================================ configuração
@router.get("/configuracao", response_model=sc.ConfigOut)
def ver_config(ctx: Ctx):
    cfg = servico.obter_config(ctx.db)
    ctx.db.commit()
    return servico.config_out(ctx.db, cfg)


@router.put("/configuracao", response_model=sc.ConfigOut)
def salvar_config(dados: sc.ConfigIn, ctx: Ctx):
    cfg = servico.obter_config(ctx.db)
    alterados = servico.salvar_config(ctx.db, cfg, dados.model_dump())
    if alterados:
        ctx.auditar("configurar", "nfse_config", 1, "Configuração fiscal alterada: " + ", ".join(alterados))
    ctx.db.commit()
    return servico.config_out(ctx.db, cfg)


@router.get("/configuracao/municipio", response_model=sc.MunicipioOut)
def descobrir_municipio(ctx: Ctx, cep: str | None = Query(None, max_length=9), codigo: str | None = Query(None, max_length=7)):
    try:
        return municipios.descobrir(cep=cep, codigo=codigo)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    except municipios.MunicipioIndisponivel:
        raise HTTPException(502, "Não foi possível consultar o CEP agora. Informe o código IBGE do município.") from None


@router.post("/configuracao/certificado", response_model=sc.ConfigOut)
async def enviar_certificado(ctx: Ctx, senha: str = Form(..., max_length=200), arquivo: UploadFile = File(...)):
    nome = (arquivo.filename or "").lower()
    if not nome.endswith((".pfx", ".p12")):
        raise HTTPException(422, "Envie o arquivo do certificado A1 (.pfx ou .p12).")
    conteudo = await arquivo.read(200_001)
    cfg = servico.obter_config(ctx.db)
    info = servico.salvar_certificado(cfg, conteudo, senha)
    # auditoria registra a troca, nunca o arquivo nem a senha
    ctx.auditar("certificado", "nfse_config", 1, f"Certificado A1 enviado: {info.titular} (válido até {info.valido_ate:%d/%m/%Y})")
    ctx.db.commit()
    return servico.config_out(ctx.db, cfg)


@router.delete("/configuracao/certificado", response_model=sc.ConfigOut)
def remover_certificado(ctx: Ctx):
    cfg = servico.obter_config(ctx.db)
    servico.remover_certificado(cfg)
    ctx.auditar("certificado", "nfse_config", 1, "Certificado A1 removido")
    ctx.db.commit()
    return servico.config_out(ctx.db, cfg)


@router.post("/configuracao/testar", response_model=Mensagem)
def testar(ctx: Ctx):
    cfg = servico.obter_config(ctx.db)
    if not cfg.cnpj or not cfg.codigo_municipio:
        raise HTTPException(409, "Preencha CNPJ e município antes de testar.")
    try:
        msg = servico.provedor_para(cfg).testar()
    except ErroConfiguracao as e:
        raise HTTPException(409, str(e)) from None
    except FalhaComunicacao as e:
        raise HTTPException(502, f"Sem resposta do provedor: {str(e)[:200]}") from None
    ctx.auditar("testar", "nfse_config", 1, msg[:200])
    ctx.db.commit()
    return Mensagem(mensagem=msg)


@router.get("/configuracao/opcoes")
def opcoes(ctx: Ctx):
    return {
        "servicos": regras.SERVICOS_SUGERIDOS, "variaveis": regras.VARIAVEIS_DISCRIMINACAO,
        "regimes": regras.REGIMES, "discriminacao_padrao": regras.DISCRIMINACAO_PADRAO,
        "motivos_cancelamento": {"1": "Erro na emissão", "2": "Serviço não prestado", "9": "Outros"},
        "provedores": {k: v.rotulo for k, v in provedores.PROVEDORES.items()},
    }
