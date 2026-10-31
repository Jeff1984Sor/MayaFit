"""Regras puras do admin, com números: mensalidade, uso, indicação, saúde, contrato e assinatura do Mercado Pago."""

import hashlib
import hmac
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.controle import cobranca, contratos, indicacao, planos, saude
from app.controle.mercadopago import assinatura_valida


def _plano(**kw):
    base = dict(nome="Estúdio", preco_mensal=Decimal("89.90"), preco_anual=Decimal("899.00"), usuarios=5,
                alunos_ativos=150, preco_aluno_excedente=Decimal("0.50"), preco_usuario_adicional=Decimal("14.90"))
    return SimpleNamespace(**{**base, **kw})


def test_planos_padrao():
    nomes = [(n, m, a, u, al) for n, m, a, u, al, _ in planos.PADRAO]
    assert nomes == [("Essencial", "49.90", "499.00", 2, 60), ("Estúdio", "89.90", "899.00", 5, 150),
                     ("Pro", "149.90", "1499.00", 10, 350), ("Rede", "289.90", "2899.00", 25, None)]
    recursos = {n: r for n, *_, r in planos.PADRAO}
    assert recursos["Essencial"] == ["gestao", "site", "crm"]
    assert recursos["Estúdio"] == ["gestao", "site", "crm", "app_aluno", "whatsapp", "checkin", "integracoes"]
    assert recursos["Pro"] == [*recursos["Estúdio"], "ia", "nfse"] and "catraca" not in recursos["Pro"]
    assert set(recursos["Rede"]) == set(planos.RECURSOS) and "catraca" in planos.EXTRAS
    assert planos.DIAS_TESTE_PADRAO == 60
    assert (planos.PRECO_ALUNO_EXCEDENTE, planos.PRECO_USUARIO_ADICIONAL) == (Decimal("0.50"), Decimal("14.90"))


def test_uso_contra_os_limites():
    u = cobranca.calcular_uso(_plano(), {"alunos_ativos": 163, "usuarios": 6, "aulas_mes": 900})
    assert (u["alunos_excedentes"], u["usuarios_excedentes"], u["valor_excedente"]) == (13, 1, Decimal("21.40"))
    rede = cobranca.calcular_uso(_plano(alunos_ativos=None, usuarios=None), {"alunos_ativos": 900, "usuarios": 40})
    assert rede["valor_excedente"] == Decimal("0.00")  # ilimitado
    assert cobranca.calcular_uso(None, {})["valor_excedente"] == Decimal(0)


def test_mensalidade_com_excedentes_e_indicacao():
    """Estúdio R$ 89,90 · 163 alunos (limite 150) · 6 usuários (limite 5) · 1 indicado ativo (5%)."""
    p = _plano()
    u = cobranca.calcular_uso(p, {"alunos_ativos": 163, "usuarios": 6})
    itens = cobranca.montar_itens(plano=p, ciclo="mensal", mes_ano="11/2026", incluir_plano=True, indicados=1,
                                  pct=Decimal(5), uso_calc=u)
    assert [(i["descricao"], i["valor"]) for i in itens] == [
        ("Plano Estúdio (mensalidade 11/2026)", "89.90"),
        ("Desconto por indicação (1 indicado(s), 5%)", "-4.49"),
        ("13 aluno(s) ativo(s) além do plano (163 de 150)", "6.50"),
        ("1 usuário(s) adicional(is)", "14.90"),
    ]
    assert cobranca.total(itens) == Decimal("106.81")
    # no cartão o plano já é debitado pela assinatura: só os excedentes
    so_exc = cobranca.montar_itens(plano=p, ciclo="mensal", mes_ano="11/2026", incluir_plano=False, indicados=1,
                                   pct=Decimal(5), uso_calc=u)
    assert cobranca.total(so_exc) == Decimal("21.40")
    anual = cobranca.montar_itens(plano=p, ciclo="anual", mes_ano="11/2026", incluir_plano=True, indicados=0,
                                  pct=Decimal(0), uso_calc=None)
    assert [(i["descricao"], i["valor"]) for i in anual] == [("Plano Estúdio (anuidade 11/2026)", "899.00")]


def test_desconto_por_indicacao_tem_teto():
    assert indicacao.percentual(1, Decimal(5), Decimal(10)) == Decimal(5)
    assert indicacao.percentual(3, Decimal(5), Decimal(10)) == Decimal(10)
    assert indicacao.percentual(3, Decimal(8), Decimal(15)) == Decimal(10)  # teto da MayaCorp: 10%
    assert indicacao.aplicar(Decimal("149.90"), Decimal(10)) == Decimal("134.91")
    assert indicacao.aplicar(None, Decimal(5)) is None


def test_saude_do_estudio():
    hoje = date(2026, 11, 10)
    ok = saude.avaliar(hoje=hoje, status="ativo", teste_ate=None, dias_sem_acesso=1, pct_alunos=50, pct_usuarios=40,
                       vencidas=0, maior_atraso_dias=0)
    assert (ok.nivel, ok.motivos) == ("boa", [])
    at = saude.avaliar(hoje=hoje, status="teste", teste_ate=date(2026, 11, 13), dias_sem_acesso=8, pct_alunos=95,
                       pct_usuarios=None, vencidas=0, maior_atraso_dias=0)
    assert at.nivel == "atencao" and at.motivos == [
        "Sem acesso há 8 dias", "Perto do limite de alunos ativos do plano (95%)", "Teste acaba em 3 dia(s)"]
    ri = saude.avaliar(hoje=hoje, status="ativo", teste_ate=None, dias_sem_acesso=2, pct_alunos=109, pct_usuarios=100,
                       vencidas=1, maior_atraso_dias=20)
    assert ri.nivel == "risco" and ri.motivos[0] == "Cobrança vencida há 20 dias"
    assert saude.avaliar(hoje=hoje, status="ativo", teste_ate=None, dias_sem_acesso=None, pct_alunos=None,
                         pct_usuarios=None, vencidas=0, maior_atraso_dias=0).nivel == "risco"  # ninguém entrou
    assert saude.percentual(163, 150) == 109 and saude.percentual(10, None) is None
    assert saude.taxa(1, 8) == "12.5" and saude.taxa(0, 0) == "0.0"
    assert saude.meses_ate(date(2026, 2, 5), 3) == ["2025-12", "2026-01", "2026-02"]


def test_contrato_preenche_variaveis():
    from app.controle.models import Cliente, Plano

    p = Plano(**{k: v for k, v in vars(_plano()).items()})
    c = Cliente(nome="Pilates Lumina", documento="12345678000195", responsavel="Ana", email_financeiro=None,
                plano=p, ciclo="anual", inicio_contrato=date(2026, 11, 1))
    corpo, vazias = contratos.preencher("{{cliente_nome}} ({{cliente_documento}}): plano {{plano}} {{ciclo}} de R$ "
                                        "{{valor}}, até {{alunos_ativos}} alunos; excedente R$ {{aluno_excedente}}. "
                                        "{{email_financeiro}} {{inventada}}", c)
    assert corpo.startswith("Pilates Lumina (12.345.678/0001-95): plano Estúdio anual de R$ 899,00, até 150 alunos; "
                            "excedente R$ 0,50.")
    assert "{{inventada}}" in corpo and vazias == ["email_financeiro"]
    assert contratos.desconhecidas("{{plano}} {{xyz}}") == ["xyz"]
    assert contratos.brl(Decimal("1234.5")) == "1.234,50"


def test_assinatura_do_mercado_pago():
    v1 = hmac.new(b"s3gr3d0", b"id:555;request-id:r1;ts:1;", hashlib.sha256).hexdigest()
    assert assinatura_valida("s3gr3d0", f"ts=1,v1={v1}", "r1", "555")
    assert not assinatura_valida("s3gr3d0", "ts=1,v1=errado", "r1", "555")
    assert not assinatura_valida("s3gr3d0", None, "r1", "555")
