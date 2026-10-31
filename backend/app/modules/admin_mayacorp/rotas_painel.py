"""Início do admin (indicadores) e a parte "viva" da ficha do estúdio: linha do tempo, saúde e ações de um clique
(estender teste, suspender, reativar, reenviar acesso)."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.controle import cobranca, eventos, indicacao, ponte, saude
from app.controle.models import Cliente, Cobranca, EventoCliente, SessaoControle, Solicitacao
from app.core.db import SessionLocal, agora
from app.modules.admin_mayacorp import schemas as sc
from app.modules.admin_mayacorp.servico import STATUS, Painel, cliente, d

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin MayaFit"])


def _hoje() -> date:
    return date.today()


def _mes(dt) -> str:
    return f"{dt:%Y-%m}"


# ================================================================ Início
def mrr_do(db, c: Cliente) -> tuple[Decimal, Decimal]:
    """(plano mensalizado com desconto, excedentes do mês pela foto de uso) de um estúdio cobrável."""
    if c.status not in cobranca.COBRAVEIS or not c.plano:
        return Decimal(0), Decimal(0)
    _, pct = indicacao.desconto(db, c)
    bruto = c.plano.preco_anual / 12 if c.ciclo == "anual" else c.plano.preco_mensal
    return indicacao.aplicar(bruto, pct), cobranca.calcular_uso(c.plano, c.uso)["valor_excedente"]


@router.get("/resumo")
def resumo(ctx: Painel):
    """Tudo do Início numa chamada: estúdios por status, MRR, crescimento, churn, cobranças, receita de 12 meses,
    funil das solicitações e testes que vencem em 7 dias."""
    hoje = _hoje()
    meses = saude.meses_ate(hoje, 12)
    mes_atual, mes_anterior = meses[-1], meses[-2]
    fim_mes = (hoje.replace(day=1) + timedelta(days=32)).replace(day=1)
    with SessaoControle() as db:
        estudios = list(db.scalars(select(Cliente).where(Cliente.tipo == "estudio")))
        por_status = {k: 0 for k in STATUS}
        mrr_planos = mrr_exc = Decimal(0)
        for c in estudios:
            por_status[c.status] = por_status.get(c.status, 0) + 1
            p, e = mrr_do(db, c)
            mrr_planos += p
            mrr_exc += e
        # crescimento e churn (saída = status → inativo, pela linha do tempo)
        novos = {m: 0 for m in meses}
        for c in estudios:
            if c.criado_em and _mes(c.criado_em) in novos:
                novos[_mes(c.criado_em)] += 1
        saidas = {m: set() for m in meses}
        evs = db.scalars(select(EventoCliente).where(EventoCliente.tipo == "status",
                                                     EventoCliente.criado_em >= agora() - timedelta(days=400)))
        nomes = {c.id: c for c in estudios}
        for ev in evs:
            m = _mes(ev.criado_em)
            if m in saidas and (ev.dados or {}).get("para") == "inativo":
                saidas[m].add(ev.cliente_id)
        saiu_mes = [nomes[i] for i in sorted(saidas[mes_atual]) if i in nomes]
        pagantes = por_status.get("ativo", 0) + por_status.get("suspenso", 0)
        # cobranças
        pendentes = list(db.scalars(select(Cobranca).where(Cobranca.status == "pendente")))
        vencidas = [k for k in pendentes if k.vencimento < hoje]
        do_mes = [k for k in pendentes if hoje <= k.vencimento < fim_mes]
        receita = {m: Decimal(0) for m in meses}
        for k in db.scalars(select(Cobranca).where(Cobranca.status == "paga", Cobranca.pago_em.is_not(None))):
            if _mes(k.pago_em) in receita:
                receita[_mes(k.pago_em)] += k.valor
        # funil das solicitações do site
        sols = list(db.scalars(select(Solicitacao)))
        por_cli = {c.id: c for c in estudios}
        aprovadas = [s for s in sols if s.status == "aprovada"]
        convertidas = [s for s in aprovadas if s.cliente_id in por_cli
                       and por_cli[s.cliente_id].status in cobranca.COBRAVEIS]
        em_teste = [s for s in aprovadas if s.cliente_id in por_cli and por_cli[s.cliente_id].status == "teste"]
        acabando = sorted((c for c in estudios if c.status == "teste" and c.teste_ate
                           and hoje <= c.teste_ate <= hoje + timedelta(days=saude.TESTE_ACABANDO_DIAS)),
                          key=lambda c: c.teste_ate)
        return {
            "clientes": len(estudios), "por_status": por_status,
            "novos_mes": novos[mes_atual], "churn_mes": len(saiu_mes),
            "mrr": d(mrr_planos + mrr_exc), "mrr_planos": d(mrr_planos), "mrr_excedentes": d(mrr_exc),
            "crescimento": {
                "novos_mes": novos[mes_atual], "novos_mes_anterior": novos[mes_anterior],
                "variacao": novos[mes_atual] - novos[mes_anterior],
                "serie": [{"mes": m, "novos": novos[m], "saidas": len(saidas[m])} for m in meses],
            },
            "churn": {
                "saidas_mes": len(saiu_mes), "taxa_mes": saude.taxa(len(saiu_mes), pagantes + len(saiu_mes)),
                "estudios": [{"id": c.id, "slug": c.slug, "nome": c.nome} for c in saiu_mes],
            },
            "cobrancas": {
                "vencidas": {"quantidade": len(vencidas), "valor": d(sum((k.valor for k in vencidas), Decimal(0)))},
                "pendentes_mes": {"quantidade": len(do_mes), "valor": d(sum((k.valor for k in do_mes), Decimal(0)))},
                "recebido_mes": d(receita[mes_atual]),
                "inadimplentes": len({k.cliente_id for k in vencidas}),
            },
            "receita_por_mes": [{"mes": m, "valor": d(receita[m])} for m in meses],
            "solicitacoes_novas": sum(1 for s in sols if s.status == "nova"),
            "funil": {
                "recebidas": len(sols), "novas": sum(1 for s in sols if s.status == "nova"),
                "recusadas": sum(1 for s in sols if s.status == "recusada"), "aprovadas": len(aprovadas),
                "em_teste": len(em_teste), "convertidas": len(convertidas),
                "taxa_conversao": saude.taxa(len(convertidas), len(sols)),
            },
            "testes_vencendo": [{"id": c.id, "slug": c.slug, "nome": c.nome, "teste_ate": c.teste_ate,
                                 "dias": (c.teste_ate - hoje).days} for c in acabando],
        }


# ================================================================ ficha: linha do tempo e saúde
@router.get("/clientes/{cid}/eventos")
def linha_do_tempo(cid: int, ctx: Painel, tipo: str | None = None, limite: int = 200):
    with SessaoControle() as db:
        cliente(db, cid)
        q = select(EventoCliente).where(EventoCliente.cliente_id == cid)
        if tipo:
            q = q.where(EventoCliente.tipo == tipo)
        q = q.order_by(EventoCliente.criado_em.desc(), EventoCliente.id.desc()).limit(max(1, min(limite, 500)))
        return [eventos.out(e) for e in db.scalars(q)]


def ultimo_acesso(est, slug: str):
    """Último acesso de alguém do estúdio (o usuário Suporte não conta)."""
    from app.core.models import Usuario

    try:
        with ponte.usando(est), SessionLocal() as s:
            return s.scalar(select(func.max(Usuario.ultimo_acesso)).where(
                func.lower(func.coalesce(Usuario.login, "")) != f"suporte.{slug}"))
    except Exception:  # banco do estúdio fora do ar não derruba a ficha
        log.exception("Último acesso de %s não foi lido", slug)
        return None


@router.get("/clientes/{cid}/saude")
def saude_do_estudio(cid: int, ctx: Painel):
    hoje = _hoje()
    with SessaoControle() as db:
        c = cliente(db, cid)
        u = cobranca.uso(c)
        vencidas = list(db.scalars(select(Cobranca).where(Cobranca.cliente_id == c.id, Cobranca.status == "pendente",
                                                          Cobranca.vencimento < hoje)))
        est, slug, status, teste_ate = ponte.estudio_de(c), c.slug, c.status, c.teste_ate
    ultimo = ultimo_acesso(est, slug)
    dias_sem = (agora() - ultimo).days if ultimo else None
    pct_a = saude.percentual(u["alunos_ativos"], u["limite_alunos"])
    pct_u = saude.percentual(u["usuarios"], u["limite_usuarios"])
    atraso = max(((hoje - k.vencimento).days for k in vencidas), default=0)
    s = saude.avaliar(hoje=hoje, status=status, teste_ate=teste_ate, dias_sem_acesso=dias_sem, pct_alunos=pct_a,
                      pct_usuarios=pct_u, vencidas=len(vencidas), maior_atraso_dias=atraso)
    return {
        "nivel": s.nivel, "rotulo": {"boa": "Saudável", "atencao": "Atenção", "risco": "Em risco"}[s.nivel],
        "motivos": s.motivos,
        "acesso": {"ultimo_acesso": ultimo, "dias_sem_acesso": dias_sem},
        "uso": {**u, "valor_excedente": d(u["valor_excedente"]), "pct_alunos": pct_a, "pct_usuarios": pct_u},
        "inadimplencia": {"vencidas": len(vencidas), "valor": d(sum((k.valor for k in vencidas), Decimal(0))),
                          "maior_atraso_dias": atraso},
        "teste": {"teste_ate": teste_ate, "dias_restantes": (teste_ate - hoje).days if teste_ate and status == "teste"
                  else None},
    }


# ================================================================ ações de um clique
@router.post("/clientes/{cid}/estender-teste")
def estender_teste(cid: int, dados: sc.EstenderTesteIn, ctx: Painel):
    """Mais N dias de teste. Vale para quem está em teste ou para quem acabou de sair dele sem pagar nada (a
    mensalidade em aberto é cancelada e volta a nascer no fim do novo teste)."""
    from app.modules.admin_mayacorp.servico import cliente_out

    hoje = _hoje()
    with SessaoControle() as db:
        c = cliente(db, cid)
        if c.status != "teste":
            pagou = db.scalar(select(Cobranca.id).where(Cobranca.cliente_id == c.id, Cobranca.status == "paga"))
            if c.status == "inativo" or pagou:
                raise HTTPException(400, "Só dá para estender o teste de quem está em teste ou ainda não pagou nada.")
            for k in db.scalars(select(Cobranca).where(Cobranca.cliente_id == c.id, Cobranca.status == "pendente",
                                                       Cobranca.tipo == "mensalidade")):
                k.status = "cancelada"
        base = max(c.teste_ate or hoje, hoje)
        novo_fim = base + timedelta(days=dados.dias)
        antes = c.status
        c.status, c.teste_ate = "teste", novo_fim
        eventos.registrar(db, c.id, "teste", f"Teste estendido em {dados.dias} dia(s), até {novo_fim:%d/%m/%Y}",
                          usuario=ctx.usuario.nome, dados={"dias": dados.dias, "ate": novo_fim.isoformat()})
        if antes != "teste":
            eventos.mudou_status(db, c.id, antes, "teste", usuario=ctx.usuario.nome, motivo="teste estendido")
        db.commit()
        ponte.limpar_cache()
        ctx.auditar("admin.estudio.estender_teste", "controle_cliente", c.id,
                    descricao=f"{c.nome}: +{dados.dias} dias (até {novo_fim:%d/%m/%Y})")
        ctx.db.commit()
        return cliente_out(c)


@router.post("/clientes/{cid}/suspender")
def suspender(cid: int, dados: sc.MotivoIn, ctx: Painel):
    """Suspenso continua entrando, mas a equipe do estúdio vê o aviso."""
    from app.modules.admin_mayacorp.rotas_estudios import aplicar_status

    with SessaoControle() as db:
        if cliente(db, cid).status == "inativo":
            raise HTTPException(400, "Estúdio inativo: use Reativar.")
    return aplicar_status(cid, "suspenso", ctx, motivo=dados.motivo or "")


@router.post("/clientes/{cid}/reativar")
def reativar(cid: int, dados: sc.MotivoIn, ctx: Painel):
    from app.modules.admin_mayacorp.rotas_estudios import aplicar_status

    with SessaoControle() as db:
        if cliente(db, cid).status in ("ativo", "teste"):
            raise HTTPException(400, "O estúdio já está com acesso normal.")
    return aplicar_status(cid, "ativo", ctx, motivo=dados.motivo or "")


@router.post("/clientes/{cid}/reenviar-acesso")
def reenviar_acesso(cid: int, ctx: Painel):
    """Sem usuário master ainda: novo link de primeiro acesso. Com master: link para criar senha nova para cada
    administrador do estúdio (a senha atual continua valendo até ele trocar)."""
    from app.controle import emails
    from app.core import auth_service
    from app.core.models import Usuario
    from app.modules.admin_mayacorp.rotas_estudios import reenviar_boas_vindas

    with SessaoControle() as db:
        c = cliente(db, cid)
        est, slug, nome = ponte.estudio_de(c), c.slug, c.nome
    enviados: list[tuple[str, str, str]] = []
    with ponte.usando(est), SessionLocal() as s:
        admins = [u for u in s.scalars(select(Usuario).where(Usuario.ativo, Usuario.senha_hash.is_not(None)))
                  if u.administrador and (u.login or "").lower() != f"suporte.{slug}"]
        for u in admins:
            enviados.append((u.nome, u.email, auth_service.criar_link_email(s, u)))
        s.commit()
    if not enviados:
        r = reenviar_boas_vindas(cid, ctx)
        return {"tipo": "primeiro_acesso", "enviado_para": [r["enviado_para"]], "link": r["link"]}
    for pessoa, email, link in enviados:
        emails.enviar_email([email], f"Seu acesso ao MayaFit — {nome}",
                            f"Olá, {pessoa}.\n\nA equipe MayaFit reenviou o seu acesso ao MayaFit do {nome}. Seu login "
                            "continua o mesmo. Se não lembra a senha, crie uma nova neste link:\n"
                            f"{link}\n\nO link só pode ser usado uma vez. Se não precisar, ignore este e-mail.\n\n"
                            "Equipe MayaFit")
    with SessaoControle() as db:
        eventos.registrar(db, cid, "acesso", "Link de acesso reenviado para " + ", ".join(e for _, e, _ in enviados),
                          usuario=ctx.usuario.nome)
        db.commit()
    ctx.auditar("admin.estudio.reenviar_acesso", "controle_cliente", cid,
                descricao=f"{nome}: " + ", ".join(e for _, e, _ in enviados))
    ctx.db.commit()
    return {"tipo": "redefinir_senha", "enviado_para": [e for _, e, _ in enviados]}
