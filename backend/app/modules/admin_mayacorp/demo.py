"""Dados de DEMONSTRAÇÃO do admin MayaFit (só no banco de controle; nada de dado real).

    uv run python -m app.modules.admin_mayacorp.demo            # popular (idempotente) + bancos dos estúdios
    uv run python -m app.modules.admin_mayacorp.demo --remover  # apagar os estúdios de demonstração

Cria estúdios fictícios (slug "demo-*", observação "[DEMO]") em todos os status, com plano, foto de uso, 12 meses de
mensalidades (pagas, em aberto e vencidas), linha do tempo, indicação e solicitações do site — o bastante para o
Início, a lista e a ficha mostrarem números. `criar_bancos()` dá a cada um o banco próprio (tabelas, identidade,
perfis, Suporte, dono e equipe) com os dados de base da demonstração (`app.demo_base`), do tamanho do `uso` que o
admin mostra: assim a coleta de uso e o worker funcionam neles como num estúdio de verdade.
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
# banco próprio de cada um (`criar_bancos`): alunos cadastrados (~90% ficam ativos; 20 a 150, na proporção do uso acima)
# e usuários com acesso (dono + equipe, até o tamanho da equipe do perfil)
BANCOS = {
    "demo-pilates-lumina": (140, 5),
    "demo-studio-equilibrio": (150, 7),
    "demo-corpo-em-movimento": (60, 2),
    "demo-forca-funcional": (150, 6),
    "demo-respira-pilates": (40, 3),
    "demo-alongar": (20, 1),
}
SECRETARIA = "Rita Campos"

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


def criar_bancos(senha: str | None = None, *, dominio_base: str | None = None, hoje: date | None = None) -> dict:
    """Banco próprio para cada estúdio de demonstração (idempotente): cria e migra o banco, identidade, perfis, Suporte,
    o dono (login "dono"), a equipe (professores com o nome dos profissionais + secretária) e os dados de base
    (`app.demo_base.popular_base`, perfil funcional para os de funcional). Sem `senha`, os usuários nascem com convite.
    Com `dominio_base`, o estúdio ganha também o endereço `<slug>.<dominio_base>`. Devolve as contagens por estúdio."""
    import zlib

    from app.controle import service
    from app.core import perfis, tenancy
    from app.core.db import SessionLocal
    from app.core.models import Usuario
    from app.core.security import hash_senha
    from app.demo_base import PERFIS, popular_base
    from app.seed import base as base_do_estudio

    with SessaoControle() as db:
        demos = [(c.slug, c.nome, c.banco, c.responsavel) for c in db.scalars(
            select(Cliente).where(Cliente.slug.like(f"{PREFIXO}%"), Cliente.observacao.like(f"{MARCA_DEMO}%")).order_by(Cliente.id))]
        if dominio_base:
            for c in db.scalars(select(Cliente).where(Cliente.slug.in_([d[0] for d in demos]))):
                host = f"{c.slug}.{dominio_base}"
                if not db.scalar(select(Dominio.id).where(Dominio.host == host)):
                    service.adicionar_dominio(db, c, host)
            db.commit()
    feitos: dict[str, dict] = {}
    for slug, nome, banco, responsavel in demos:
        if slug not in BANCOS or not banco:
            continue
        alunos, usuarios = BANCOS[slug]
        perfil = "funcional" if "funcional" in slug else "pilates"
        service.criar_banco(banco)
        esc = tenancy.Estudio(slug=slug, banco=banco, mayacorp=False)
        service.migrar(esc)
        with tenancy.usando(esc), SessionLocal() as s:
            base_do_estudio(s, nome=nome)
            if not s.scalar(select(Usuario.id).where(Usuario.suporte.is_(True))):
                service._usuario_suporte(s, slug)
            if not s.scalar(select(Usuario.id).where(Usuario.login == "dono")):
                service._primeiro_admin(s, responsavel or f"Responsável {nome}", f"dono@{slug}.exemplo", "dono", senha)
                padrao = perfis.garantir_padrao(s)
                profs = [p[0] for p in PERFIS[perfil]["profissionais"] if p[4]]
                equipe = [(profs[0], "Professor"), (SECRETARIA, "Secretária"), *((p, "Professor") for p in profs[1:])]
                for nome_u, perfil_u in equipe[: max(usuarios - 1, 0)]:
                    login = nome_u.split()[0].lower().translate(str.maketrans("áéíóúâêôãõç", "aeiouaeoaoc"))
                    s.add(Usuario(nome=nome_u, email=f"{login}@{slug}.exemplo", login=login, perfil_acesso_id=padrao[perfil_u].id,
                                  senha_hash=hash_senha(senha) if senha else None, convite_pendente=not senha))
            s.commit()
            feitos[slug] = popular_base(s, perfil=perfil, alunos=alunos, hoje=hoje, semente=zlib.crc32(slug.encode()),
                                        unidades=2 if alunos >= 100 else 1)
        service.sincronizar_todos(slug)
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
        print(criar_bancos())
