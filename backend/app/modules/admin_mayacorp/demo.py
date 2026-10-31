"""Dados de DEMONSTRAÇÃO do admin MayaFit (só no banco de controle; nada de dado real).

    uv run python -m app.modules.admin_mayacorp.demo            # popular (idempotente)
    uv run python -m app.modules.admin_mayacorp.demo --remover  # apagar os estúdios de demonstração

Cria estúdios fictícios (slug "demo-*", observação "[DEMO]") em todos os status, com plano, foto de uso, 12 meses de
mensalidades (pagas, em aberto e vencidas), linha do tempo, indicação e solicitações do site — o bastante para o
Início, a lista e a ficha mostrarem números. Os bancos desses estúdios NÃO são criados: telas que abrem o banco do
estúdio (Usuários, último acesso) mostram vazio para eles.
"""

import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.controle import cobranca, eventos, planos
from app.controle.models import (
    Cliente,
    Cobranca,
    ContratoCliente,
    Dominio,
    EventoCliente,
    Plano,
    SessaoControle,
    Solicitacao,
)

PREFIXO = "demo-"
MARCA_DEMO = "[DEMO]"

# slug, nome, plano, ciclo, status, meses desde a criação, alunos ativos, usuários, situação da cobrança atual
ESTUDIOS = [
    ("demo-pilates-lumina", "Pilates Lumina", "Estúdio", "mensal", "ativo", 11, 163, 5, "paga"),
    ("demo-studio-equilibrio", "Studio Equilíbrio", "Pro", "anual", "ativo", 9, 290, 8, "paga"),
    ("demo-corpo-em-movimento", "Corpo em Movimento", "Essencial", "mensal", "ativo", 6, 58, 2, "pendente"),
    ("demo-forca-funcional", "Força Funcional", "Rede", "mensal", "suspenso", 8, 520, 21, "vencida"),
    ("demo-respira-pilates", "Respira Pilates", "Estúdio", "mensal", "teste", 1, 40, 3, None),
    ("demo-alongar", "Alongar Studio", "Essencial", "mensal", "inativo", 5, 12, 1, None),
]

SOLICITACOES = [
    ("Ateliê do Movimento", "Marina Duarte", "marina@ateliedomovimento.exemplo", "nova", 85),
    ("Pilates Vila Nova", "Carlos Teixeira", "carlos@pilatesvilanova.exemplo", "nova", 140),
    ("Studio Alma", "Beatriz Rocha", "bia@studioalma.exemplo", "recusada", 10),
]


def _meses_atras(hoje: date, n: int) -> date:
    ano, mes = hoje.year, hoje.month - n
    while mes <= 0:
        ano, mes = ano - 1, mes + 12
    return date(ano, mes, 1)


def _instante(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 13, 0, tzinfo=UTC)


def popular_demo(hoje: date | None = None) -> dict:
    """Idempotente: o que já existe (por slug / competência / e-mail) fica como está."""
    hoje = hoje or date.today()
    feitos = {"estudios": 0, "cobrancas": 0, "solicitacoes": 0}
    with SessaoControle() as db:
        planos.garantir_padrao(db)
        por_nome = {p.nome: p for p in db.scalars(select(Plano))}
        cfg = cobranca.config(db)
        dia = cfg.dia_vencimento
        criados: dict[str, Cliente] = {}
        for slug, nome, plano, ciclo, status, idade, alunos, usuarios, situacao in ESTUDIOS:
            c = db.scalar(select(Cliente).where(Cliente.slug == slug))
            if c is None:
                inicio = _meses_atras(hoje, idade)
                p = por_nome.get(plano)
                c = Cliente(slug=slug, nome=nome, banco=f"mayafit_{slug.replace('-', '_')}", status=status,
                            tipo="estudio", plano_id=p.id if p else None, ciclo=ciclo, inicio_contrato=inicio,
                            responsavel=f"Responsável {nome}", email_financeiro=f"financeiro@{slug}.exemplo",
                            telefone="(11) 90000-0000", observacao=f"{MARCA_DEMO} estúdio de demonstração",
                            criado_em=_instante(inicio), extras=["receita_saude"] if plano == "Pro" else [],
                            teste_ate=hoje + timedelta(days=5) if status == "teste" else None,
                            uso={"alunos_ativos": alunos, "usuarios": usuarios, "aulas_mes": alunos * 6,
                                 "em": _instante(hoje).isoformat()})
                c.dominios.append(Dominio(host=f"{slug}.mayafit.exemplo"))
                db.add(c)
                db.flush()
                ev = eventos.registrar(db, c.id, "criado", f"Estúdio criado ({plano}, {ciclo})", usuario="Demonstração")
                ev.criado_em = _instante(inicio)
                if status in ("suspenso", "inativo"):
                    ev = eventos.registrar(db, c.id, "status", f"Status: Ativo → {eventos.STATUS[status]}",
                                           usuario="Demonstração", dados={"de": "ativo", "para": status})
                    ev.criado_em = _instante(hoje.replace(day=1))
                feitos["estudios"] += 1
            criados[slug] = c
            if status in ("teste",) or not c.plano:
                continue
            # 12 meses de mensalidades (as anteriores pagas; a do mês conforme a situação)
            meses = min(idade, 11) if status != "inativo" else min(idade, 11)
            for n in range(meses, -1, -1):
                ref = _meses_atras(hoje, n)
                if status == "inativo" and n == 0:
                    break
                comp = f"{ref:%Y-%m}"
                if db.scalar(select(Cobranca.id).where(Cobranca.cliente_id == c.id, Cobranca.tipo == "mensalidade",
                                                       Cobranca.competencia == comp)):
                    continue
                if ciclo == "anual" and ref.month != c.inicio_contrato.month:
                    continue
                valor = c.plano.preco_anual if ciclo == "anual" else c.plano.preco_mensal
                venc = date(ref.year, ref.month, min(dia, 28))
                atual = n == 0
                st = (situacao if atual else "paga") or "paga"
                if st == "vencida":
                    st, venc = "pendente", hoje - timedelta(days=20)
                elif st == "pendente":
                    venc = max(venc, hoje + timedelta(days=3))
                if not atual and status == "suspenso" and n == 1:
                    st, venc = "pendente", hoje - timedelta(days=35)
                k = Cobranca(cliente_id=c.id, tipo="mensalidade", competencia=comp,
                             descricao=f"MayaFit {ref:%m/%Y}", valor=Decimal(valor), vencimento=venc, status=st,
                             itens=[{"descricao": f"Plano {c.plano.nome} ({'anuidade' if ciclo == 'anual' else 'mensalidade'}"
                                                  f" {ref:%m/%Y})", "valor": f"{Decimal(valor):.2f}"}],
                             avisos=[], forma_paga="Pix" if st == "paga" else None,
                             pago_em=_instante(min(venc, hoje)) if st == "paga" else None,
                             link=f"https://www.mercadopago.com.br/demo/{slug}/{comp}" if st == "pendente" else None)
                db.add(k)
                feitos["cobrancas"] += 1
        # indicação: o Lumina indicou o Equilíbrio (ativo → 5% de desconto para o Lumina)
        eq, lu = criados.get("demo-studio-equilibrio"), criados.get("demo-pilates-lumina")
        if eq and lu and eq.indicado_por_id is None:
            eq.indicado_por_id = lu.id
        for nome, resp, email, status, alunos in SOLICITACOES:
            if db.scalar(select(Solicitacao.id).where(Solicitacao.email == email)):
                continue
            db.add(Solicitacao(nome=nome, responsavel=resp, email=email, telefone="(11) 98888-0000",
                               plano_id=por_nome["Estúdio"].id if "Estúdio" in por_nome else None, ciclo="mensal",
                               alunos=alunos, status=status, mensagem=f"{MARCA_DEMO} solicitação de demonstração"))
            feitos["solicitacoes"] += 1
        # a solicitação que virou o estúdio em teste
        rp = criados.get("demo-respira-pilates")
        if rp and not db.scalar(select(Solicitacao.id).where(Solicitacao.cliente_id == rp.id)):
            db.add(Solicitacao(nome=rp.nome, responsavel=rp.responsavel or "", email=rp.email_financeiro or "",
                               telefone=rp.telefone, plano_id=rp.plano_id, ciclo="mensal", alunos=40,
                               status="aprovada", cliente_id=rp.id, mensagem=f"{MARCA_DEMO} veio pelo site"))
            feitos["solicitacoes"] += 1
        db.commit()
    return feitos


def remover_demo() -> int:
    """Apaga os estúdios de demonstração (e, em cascata, cobranças, eventos, domínios) e as solicitações demo."""
    with SessaoControle() as db:
        demos = list(db.scalars(select(Cliente).where(Cliente.slug.like(f"{PREFIXO}%"),
                                                      Cliente.observacao.like(f"{MARCA_DEMO}%"))))
        for s in db.scalars(select(Solicitacao).where(Solicitacao.mensagem.like(f"{MARCA_DEMO}%"))):
            db.delete(s)
        for c in demos:
            for modelo in (Cobranca, EventoCliente, ContratoCliente):
                for k in db.scalars(select(modelo).where(modelo.cliente_id == c.id)):
                    db.delete(k)
            db.delete(c)
        db.commit()
        return len(demos)


if __name__ == "__main__":
    if "--remover" in sys.argv:
        print(f"{remover_demo()} estúdio(s) de demonstração removido(s).")
    else:
        print(popular_demo())
