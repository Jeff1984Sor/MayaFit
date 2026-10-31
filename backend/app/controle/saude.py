"""Saúde do estúdio (ficha do admin) e indicadores do Início. Regras puras, testadas com números."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# limiares (regras de negócio do admin; ver docs/progresso-admin.md, seção Especificação)
DIAS_SEM_ACESSO_ATENCAO = 7
DIAS_SEM_ACESSO_RISCO = 14
ATRASO_RISCO_DIAS = 15
USO_ATENCAO_PCT = 90
TESTE_ACABANDO_DIAS = 7


@dataclass
class Saude:
    nivel: str  # boa | atencao | risco
    motivos: list[str]


def percentual(valor: int | None, limite: int | None) -> int | None:
    """Uso em % do limite (inteiro, arredondado). Limite vazio = ilimitado → None."""
    if not limite:
        return None
    return int((Decimal(valor or 0) * 100 / Decimal(limite)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def avaliar(*, hoje: date, status: str, teste_ate: date | None, dias_sem_acesso: int | None,
            pct_alunos: int | None, pct_usuarios: int | None, vencidas: int, maior_atraso_dias: int) -> Saude:
    """Risco: suspenso/inativo, atraso ≥ 15 dias ou sem acesso há 14+ dias (ou nunca acessou fora do teste).
    Atenção: alguma cobrança vencida, sem acesso há 7+ dias, uso ≥ 90% de um limite (ou acima) ou teste acabando
    em até 7 dias. Senão, boa."""
    risco: list[str] = []
    atencao: list[str] = []
    if status in ("suspenso", "inativo"):
        risco.append("Estúdio suspenso" if status == "suspenso" else "Estúdio inativo (sem acesso)")
    if vencidas and maior_atraso_dias >= ATRASO_RISCO_DIAS:
        risco.append(f"Cobrança vencida há {maior_atraso_dias} dias")
    elif vencidas:
        atencao.append(f"{vencidas} cobrança(s) vencida(s)")
    if dias_sem_acesso is None:
        (atencao if status == "teste" else risco).append("Ninguém do estúdio entrou ainda")
    elif dias_sem_acesso >= DIAS_SEM_ACESSO_RISCO:
        risco.append(f"Sem acesso há {dias_sem_acesso} dias")
    elif dias_sem_acesso >= DIAS_SEM_ACESSO_ATENCAO:
        atencao.append(f"Sem acesso há {dias_sem_acesso} dias")
    for rotulo, pct in (("alunos ativos", pct_alunos), ("usuários", pct_usuarios)):
        if pct is not None and pct > 100:
            atencao.append(f"Acima do limite de {rotulo} do plano ({pct}%)")
        elif pct is not None and pct >= USO_ATENCAO_PCT:
            atencao.append(f"Perto do limite de {rotulo} do plano ({pct}%)")
    if status == "teste" and teste_ate and 0 <= (teste_ate - hoje).days <= TESTE_ACABANDO_DIAS:
        atencao.append(f"Teste acaba em {(teste_ate - hoje).days} dia(s)")
    if risco:
        return Saude("risco", risco + atencao)
    if atencao:
        return Saude("atencao", atencao)
    return Saude("boa", [])


def taxa(parte: int, todo: int) -> str:
    """Percentual com 1 casa, em texto ("12.5"). Sem base → "0.0"."""
    if not todo:
        return "0.0"
    return f"{(Decimal(parte) * 100 / Decimal(todo)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}"


def meses_ate(hoje: date, n: int = 12) -> list[str]:
    """Os n meses terminando no mês de hoje, do mais antigo ao atual ("AAAA-MM")."""
    ano, mes = hoje.year, hoje.month
    out = []
    for _ in range(n):
        out.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    return out[::-1]
