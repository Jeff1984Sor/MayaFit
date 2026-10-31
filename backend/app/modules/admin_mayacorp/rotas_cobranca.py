"""Cobrança dos estúdios (Mercado Pago): telas do admin, notificações do MP (públicas) e o "Meu plano" do estúdio.

Porte de app/controle/routes_cobranca.py do MayaJus (mesmos caminhos e respostas).
"""

import logging
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.controle import cobranca, eventos, planos, ponte
from app.controle.mercadopago import ErroMercadoPago, assinatura_valida
from app.controle.models import Cliente, Cobranca, Plano, SessaoControle
from app.core.deps import Ctx
from app.core.ratelimit import limitar
from app.core.segredos import cifrar_texto
from app.modules.admin_mayacorp import schemas as sc
from app.modules.admin_mayacorp.servico import Painel, cliente, d, erro, plano_out, uso_out

log = logging.getLogger(__name__)

admin = APIRouter(prefix="/admin", tags=["admin MayaFit"])
publico = APIRouter(prefix="/public", tags=["público"])
meu = APIRouter(prefix="/meu-plano", tags=["meu plano"])

ROTULO = {"pendente": "Em aberto", "paga": "Paga", "cancelada": "Cancelada"}
ERROS = (ErroMercadoPago, cobranca.RegraCobranca)


def _mp():
    """O Mercado Pago é lido do módulo na hora (os testes trocam a classe)."""
    from app.controle import mercadopago

    return mercadopago.MercadoPago


def cob_out(k: Cobranca) -> dict:
    vencida = k.status == "pendente" and k.vencimento < date.today()
    return {"id": k.id, "cliente_id": k.cliente_id, "cliente_nome": k.cliente.nome, "tipo": k.tipo,
            "competencia": k.competencia, "descricao": k.descricao, "itens": k.itens or [], "valor": d(k.valor),
            "vencimento": k.vencimento, "status": "vencida" if vencida else k.status,
            "status_rotulo": "Vencida" if vencida else ROTULO.get(k.status, k.status), "link": k.link,
            "pago_em": k.pago_em, "forma_paga": k.forma_paga, "avisos": k.avisos or [], "criado_em": k.criado_em}


def _cfg_out(cfg) -> dict:
    from app.core.segredos import mascarar

    return {"conectado": bool(cfg.mp_token_cifrado), "segredo_definido": bool(cfg.mp_segredo_cifrado),
            "token_final": mascarar(cobranca.token(cfg)) if cfg.mp_token_cifrado else None,
            "conta": cfg.mp_conta, "dia_vencimento": cfg.dia_vencimento, "gerar_automatico": cfg.gerar_automatico,
            "regua": cfg.regua or [], "url_notificacao": cobranca.url_notificacao()}


# ================================================================ admin: configuração
@admin.get("/cobranca/config")
def ler_config(ctx: Painel):
    with SessaoControle() as db:
        cfg = cobranca.config(db)
        db.commit()
        return _cfg_out(cfg)


@admin.put("/cobranca/config")
def salvar_config(dados: sc.ConfigCobrancaIn, ctx: Painel):
    with SessaoControle() as db:
        cfg = cobranca.config(db)
        if dados.token and dados.token.strip():
            t = dados.token.strip()
            try:
                conta = _mp()(t).conta()
            except ErroMercadoPago as e:
                erro(e)
            cfg.mp_token_cifrado = cifrar_texto(t)
            cfg.mp_conta = conta.get("email") or conta.get("nickname") or str(conta.get("id"))
        if dados.segredo and dados.segredo.strip():
            cfg.mp_segredo_cifrado = cifrar_texto(dados.segredo.strip())
        cfg.dia_vencimento = dados.dia_vencimento
        cfg.gerar_automatico = dados.gerar_automatico
        cfg.regua = sorted({max(-30, min(60, x)) for x in dados.regua})
        db.commit()
        # a auditoria registra a troca, nunca o valor do token/segredo
        ctx.auditar("admin.cobranca.config", "controle_config", cfg.id,
                    descricao="Mercado Pago" + (" (token novo)" if dados.token else "")
                    + (" (assinatura secreta nova)" if dados.segredo else ""))
        ctx.db.commit()
        return _cfg_out(cfg)


@admin.post("/cobranca/config/testar")
def testar(ctx: Painel):
    with SessaoControle() as db:
        try:
            conta = cobranca.mp(cobranca.config(db)).conta()
        except ERROS as e:
            erro(e)
        return {"ok": True, "conta": conta.get("email") or conta.get("nickname"), "id": conta.get("id")}


# ================================================================ admin: cobranças
@admin.get("/cobrancas")
def listar(ctx: Painel, status: str | None = None, cliente_id: int | None = None):
    with SessaoControle() as db:
        q = select(Cobranca).order_by(Cobranca.vencimento.desc(), Cobranca.id.desc())
        if cliente_id:
            q = q.where(Cobranca.cliente_id == cliente_id)
        if status == "vencida":
            q = q.where(Cobranca.status == "pendente", Cobranca.vencimento < date.today())
        elif status == "pendente":
            q = q.where(Cobranca.status == "pendente", Cobranca.vencimento >= date.today())
        elif status:
            q = q.where(Cobranca.status == status)
        return [cob_out(k) for k in db.scalars(q.limit(500))]


@admin.get("/cobrancas/resumo")
def resumo(ctx: Painel):
    hoje = date.today()
    with SessaoControle() as db:
        todas = list(db.scalars(select(Cobranca).where(Cobranca.status != "cancelada")))
    aberto = sum((k.valor for k in todas if k.status == "pendente" and k.vencimento >= hoje), Decimal(0))
    vencido = sum((k.valor for k in todas if k.status == "pendente" and k.vencimento < hoje), Decimal(0))
    recebido = sum((k.valor for k in todas if k.status == "paga" and k.pago_em
                    and (k.pago_em.year, k.pago_em.month) == (hoje.year, hoje.month)), Decimal(0))
    return {"em_aberto": d(aberto), "vencido": d(vencido), "recebido_mes": d(recebido),
            "inadimplentes": len({k.cliente_id for k in todas if k.status == "pendente" and k.vencimento < hoje})}


def _enviar(db, k: Cobranca) -> list[str]:
    try:
        return cobranca.enviar_cobranca(db, k)
    except ERROS as e:
        db.rollback()
        erro(e)


def _cob(db, kid: int) -> Cobranca:
    k = db.get(Cobranca, kid)
    if not k:
        raise HTTPException(404, "Cobrança não encontrada.")
    return k


@admin.post("/cobrancas/avulsa", status_code=201)
def criar_avulsa(dados: sc.AvulsaIn, ctx: Painel):
    with SessaoControle() as db:
        c = cliente(db, dados.cliente_id)
        try:
            k = cobranca.avulsa(db, c, dados.descricao, dados.valor, dados.vencimento)
            cobranca.criar_link(db, k)
        except ERROS as e:
            db.rollback()
            erro(e)
        if dados.enviar:
            _enviar(db, k)
        eventos.registrar(db, c.id, "cobranca", f"Cobrança avulsa: {k.descricao} ({cobranca.moeda(k.valor)})",
                          usuario=ctx.usuario.nome)
        db.commit()
        ctx.auditar("admin.cobranca.avulsa", "controle_cobranca", k.id, descricao=f"{c.nome}: {k.descricao} {k.valor}")
        ctx.db.commit()
        return cob_out(k)


@admin.post("/cobrancas/gerar")
def gerar(dados: sc.GerarIn, ctx: Painel):
    """Mensalidades do mês para todos os estúdios ativos/suspensos (as que já existem ficam como estão)."""
    ano, mes = map(int, dados.competencia.split("-"))
    criadas, erros = [], []
    with SessaoControle() as db:
        estudios = list(db.scalars(select(Cliente).where(Cliente.tipo == "estudio",
                                                         Cliente.status.in_(cobranca.COBRAVEIS))))
        for c in estudios:
            try:
                k = cobranca.gerar_mensalidade(db, c, ano, mes)
                if k and dados.enviar:
                    cobranca.enviar_cobranca(db, k)
                db.commit()
                if k:
                    criadas.append(c.nome)
            except Exception as e:  # um estúdio com problema não para os outros
                db.rollback()
                erros.append(f"{c.nome}: {e}")
    ctx.auditar("admin.cobranca.gerar", "controle_cobranca", None, descricao=f"{dados.competencia}: {len(criadas)}")
    ctx.db.commit()
    return {"criadas": criadas, "erros": erros}


@admin.post("/cobrancas/{kid}/enviar")
def reenviar(kid: int, ctx: Painel):
    with SessaoControle() as db:
        k = _cob(db, kid)
        if k.status != "pendente":
            raise HTTPException(400, "Só cobranças em aberto podem ser enviadas.")
        para = _enviar(db, k)
        db.commit()
        ctx.auditar("admin.cobranca.enviar", "controle_cobranca", k.id, descricao=", ".join(para))
        ctx.db.commit()
        return {**cob_out(k), "enviado_para": para}


@admin.post("/cobrancas/{kid}/baixa")
def baixa_manual(kid: int, dados: sc.BaixaIn, ctx: Painel):
    with SessaoControle() as db:
        k = _cob(db, kid)
        if k.status == "cancelada":
            raise HTTPException(400, "Cobrança cancelada.")
        cobranca.dar_baixa(k, dados.forma or "manual", usuario=ctx.usuario.nome)
        db.commit()
        ctx.auditar("admin.cobranca.baixa", "controle_cobranca", k.id, descricao=f"{k.cliente.nome}: {k.valor}")
        ctx.db.commit()
        return cob_out(k)


@admin.post("/cobrancas/{kid}/cancelar")
def cancelar(kid: int, ctx: Painel):
    with SessaoControle() as db:
        k = _cob(db, kid)
        if k.status == "paga":
            raise HTTPException(400, "Cobrança já paga não pode ser cancelada.")
        k.status = "cancelada"
        eventos.registrar(db, k.cliente_id, "cobranca", f"{k.descricao} cancelada", usuario=ctx.usuario.nome)
        db.commit()
        ctx.auditar("admin.cobranca.cancelar", "controle_cobranca", k.id, descricao=f"{k.cliente.nome}: {k.descricao}")
        ctx.db.commit()
        return cob_out(k)


# ================================================================ admin: forma de pagamento do estúdio
def _pagamento_out(c: Cliente) -> dict:
    return {"forma_pagamento": c.forma_pagamento, "assinatura_id": c.mp_assinatura_id,
            "assinatura_status": c.mp_assinatura_status}


@admin.get("/clientes/{cid}/pagamento")
def ler_pagamento(cid: int, ctx: Painel):
    with SessaoControle() as db:
        return _pagamento_out(cliente(db, cid))


@admin.put("/clientes/{cid}/pagamento")
def forma_pagamento(cid: int, dados: sc.FormaIn, ctx: Painel):
    with SessaoControle() as db:
        c = cliente(db, cid)
        c.forma_pagamento = dados.forma_pagamento
        db.commit()
        ctx.auditar("admin.estudio.pagamento", "controle_cliente", c.id, descricao=dados.forma_pagamento)
        ctx.db.commit()
        return _pagamento_out(c)


@admin.post("/clientes/{cid}/assinatura")
def criar_assinatura(cid: int, ctx: Painel):
    """Link para o estúdio cadastrar o cartão (vai por e-mail para o financeiro)."""
    with SessaoControle() as db:
        c = cliente(db, cid)
        try:
            link = cobranca.assinar_cartao(db, c)
        except ERROS as e:
            db.rollback()
            erro(e)
        eventos.registrar(db, c.id, "pagamento", "Link da assinatura no cartão enviado", usuario=ctx.usuario.nome)
        db.commit()
        cobranca.enviar_email([c.email_financeiro], "MayaFit — cadastre o cartão para a mensalidade",
                              f"Olá, {c.responsavel or c.nome}.\n\nPara a mensalidade do MayaFit ser debitada todo mês "
                              f"no cartão, cadastre-o neste link do Mercado Pago:\n{link}\n\nEquipe MayaFit")
        ctx.auditar("admin.estudio.assinatura", "controle_cliente", c.id, descricao=c.nome)
        ctx.db.commit()
        return {**_pagamento_out(c), "link": link}


# ================================================================ notificações do Mercado Pago (públicas)
@publico.post("/mercadopago", dependencies=[Depends(limitar("mercadopago", 300, 60))])
async def notificacao(request: Request):
    """O Mercado Pago avisa aqui (pagamento, assinatura, débito da assinatura).

    Com a assinatura secreta cadastrada, aviso sem x-signature válido é ignorado. E nada é aceito às cegas: o
    pagamento é sempre relido na API do Mercado Pago com o nosso token."""
    try:
        corpo = await request.json()
    except ValueError:
        corpo = {}
    if not isinstance(corpo, dict):
        corpo = {}
    qp = request.query_params
    tipo = corpo.get("type") or qp.get("type") or qp.get("topic") or ""
    recurso = str((corpo.get("data") or {}).get("id") or qp.get("data.id") or qp.get("id") or "")
    if not (tipo and recurso):
        return {"ok": True}
    with SessaoControle() as db:
        cfg = cobranca.config(db)
        seg = cobranca.segredo(cfg)
        if seg and not assinatura_valida(seg, request.headers.get("x-signature"), request.headers.get("x-request-id"),
                                         qp.get("data.id") or recurso):
            log.warning("Notificação do Mercado Pago sem assinatura válida (%s %s): ignorada", tipo, recurso)
            return {"ok": True}
        try:
            resultado = cobranca.processar_notificacao(db, tipo, recurso)
            db.commit()
        except ERROS as e:
            db.rollback()
            log.warning("Notificação %s %s: %s", tipo, recurso, e)
            raise HTTPException(503, "Tente de novo.") from e
    log.info("Mercado Pago: %s", resultado)
    return {"ok": True}


# ================================================================ "Meu plano" (no estúdio, só administradores)
def _meu_cliente(db, ctx) -> Cliente:
    est = ponte.atual()
    if est is None or getattr(est, "mayacorp", False):
        raise HTTPException(404, "Não encontrado.")
    if not ctx.usuario.administrador:
        raise HTTPException(403, "Só o administrador do estúdio vê e altera o plano.")
    c = db.scalar(select(Cliente).where(Cliente.slug == est.slug))
    if not c:
        raise HTTPException(404, "Não encontrado.")
    return c


@meu.get("")
def meu_plano(ctx: Ctx):
    with SessaoControle() as db:
        c = _meu_cliente(db, ctx)
        planos.garantir_padrao(db)
        disponiveis = db.scalars(select(Plano).where(Plano.ativo).order_by(Plano.ordem, Plano.id))
        abertas = db.scalars(select(Cobranca).where(Cobranca.cliente_id == c.id, Cobranca.status == "pendente")
                             .order_by(Cobranca.vencimento))
        pagas = db.scalars(select(Cobranca).where(Cobranca.cliente_id == c.id, Cobranca.status == "paga")
                           .order_by(Cobranca.pago_em.desc()).limit(12))
        return {
            "nome": c.nome, "status": c.status, "teste_ate": c.teste_ate, "ciclo": c.ciclo,
            "plano": plano_out(c.plano), "valor": d(cobranca.valor_do_plano(db, c)),
            "forma_pagamento": c.forma_pagamento, "assinatura_status": c.mp_assinatura_status,
            "pode_alterar": ctx.usuario.administrador,
            "uso": uso_out(cobranca.uso(c)),
            "extras": [{"chave": k, "rotulo": planos.EXTRAS.get(k, k)} for k in c.extras or []],
            "planos": [plano_out(p) for p in disponiveis],
            "recursos": [{"chave": k, "rotulo": v} for k, v in planos.RECURSOS.items()],
            "em_aberto": [cob_out(k) for k in abertas], "pagas": [cob_out(k) for k in pagas],
        }


@meu.put("")
def trocar_plano(dados: sc.TrocaPlanoIn, ctx: Ctx):
    """Upgrade ou downgrade: os limites mudam na hora; a cobrança nova vale a partir da próxima mensalidade."""
    with SessaoControle() as db:
        c = _meu_cliente(db, ctx)
        p = db.get(Plano, dados.plano_id)
        if not p or not p.ativo:
            raise HTTPException(400, "Plano não disponível.")
        if c.forma_pagamento == "cartao" and dados.ciclo == "anual":
            raise HTTPException(400, "A assinatura no cartão é mensal. Para o plano anual, fale com a equipe MayaFit.")
        u = cobranca.uso(c)
        if p.usuarios and u["usuarios"] > p.usuarios:
            raise HTTPException(400, f"O plano {p.nome} vai até {p.usuarios} usuário(s) e o estúdio tem "
                                     f"{u['usuarios']} com acesso. Desative alguns em Configurações › Usuários.")
        antes = c.plano.nome if c.plano else "sem plano"
        c.plano_id, c.ciclo = p.id, dados.ciclo
        db.flush()
        db.refresh(c)
        try:
            cobranca.plano_mudou(db, c)
        except ERROS as e:
            db.rollback()
            erro(e)
        eventos.registrar(db, c.id, "plano", f"Plano trocado pelo estúdio: {antes} → {p.nome} ({dados.ciclo})",
                          usuario=ctx.usuario.nome)
        db.commit()
        ponte.limpar_cache()
    ctx.auditar("meu_plano.trocar", "controle_cliente", c.id, descricao=f"{antes} → {p.nome} ({dados.ciclo})")
    ctx.db.commit()
    return meu_plano(ctx)


@meu.post("/cartao")
def meu_cartao(ctx: Ctx):
    with SessaoControle() as db:
        c = _meu_cliente(db, ctx)
        try:
            link = cobranca.assinar_cartao(db, c)
        except ERROS as e:
            db.rollback()
            erro(e)
        eventos.registrar(db, c.id, "pagamento", "Estúdio pediu a assinatura no cartão", usuario=ctx.usuario.nome)
        db.commit()
    ctx.auditar("meu_plano.cartao", "controle_cliente", c.id, descricao="assinatura no cartão")
    ctx.db.commit()
    return {"link": link}


@meu.post("/cobrancas/{kid}/link")
def meu_link(kid: int, ctx: Ctx):
    with SessaoControle() as db:
        c = _meu_cliente(db, ctx)
        k = db.get(Cobranca, kid)
        if not k or k.cliente_id != c.id or k.status != "pendente":
            raise HTTPException(404, "Cobrança não encontrada.")
        try:
            link = cobranca.criar_link(db, k)
        except ERROS as e:
            db.rollback()
            erro(e)
        db.commit()
        return {"link": link}
