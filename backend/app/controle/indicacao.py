"""Desconto por indicação: cada estúdio indicado que está ativo (pagando) dá X% na mensalidade de quem indicou,
somando até o teto da política, que nunca passa de 10%."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select

from app.controle.models import Cliente, PoliticaComercial

TETO = Decimal(10)  # regra da MayaCorp: desconto por indicação nunca acima de 10% da mensalidade


def politica(db) -> PoliticaComercial:
    p = db.get(PoliticaComercial, 1)
    if p is None:
        p = PoliticaComercial(id=1, desconto_por_indicacao=Decimal("5.00"), desconto_maximo=TETO)
        db.add(p)
        db.flush()
    return p


def indicacoes_ativas(db, c: Cliente) -> int:
    if c.id is None:
        return 0
    return db.scalar(select(func.count(Cliente.id)).where(
        Cliente.indicado_por_id == c.id, Cliente.status == "ativo", Cliente.tipo == "estudio")) or 0


def percentual(n_indicados: int, por_indicacao: Decimal, maximo: Decimal) -> Decimal:
    """Regra pura: n × % por indicação, limitado ao máximo da política e ao teto de 10%."""
    return min(Decimal(n_indicados) * Decimal(por_indicacao), Decimal(maximo), TETO)


def desconto(db, c: Cliente) -> tuple[int, Decimal]:
    """(indicados ativos, % de desconto)."""
    pol = politica(db)
    n = indicacoes_ativas(db, c)
    return n, percentual(n, pol.desconto_por_indicacao, pol.desconto_maximo)


def aplicar(valor: Decimal | None, pct: Decimal) -> Decimal | None:
    if valor is None:
        return None
    return (Decimal(valor) * (100 - Decimal(pct)) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
