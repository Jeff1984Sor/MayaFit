"""Regras fiscais da NFS-e como funções puras (testadas em tests/nfse/test_regras.py).

Nada aqui fala com banco ou rede. Dinheiro sempre `Decimal`, arredondamento comercial (ROUND_HALF_UP) em centavos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from app.domain.documentos import so_digitos, validar_cpf

FUSO = ZoneInfo("America/Sao_Paulo")
CENTAVO = Decimal("0.01")
ZERO = Decimal("0")

# Regimes aceitos na configuração e como cada um aparece na DPS nacional (opSimpNac)
REGIMES = {
    "mei": "MEI (Microempreendedor Individual)",
    "simples": "Simples Nacional (ME/EPP)",
    "presumido": "Lucro Presumido",
    "real": "Lucro Real",
}
OP_SIMPLES_NACIONAL = {"mei": "2", "simples": "3", "presumido": "1", "real": "1"}

# Sugestões da lista de serviços da LC 116/2003 para estúdios (o contador confirma).
SERVICOS_SUGERIDOS = [
    {
        "item": "06.04",
        "tributacao_nacional": "060401",
        "descricao": "Ginástica, dança, esportes, natação, artes marciais e demais atividades físicas",
        "indicado_para": "Pilates, funcional, academia, dança, yoga, artes marciais",
    },
    {
        "item": "04.08",
        "tributacao_nacional": "040801",
        "descricao": "Terapia ocupacional, fisioterapia e fonoaudiologia",
        "indicado_para": "Fisioterapia, pilates clínico/terapêutico feito por fisioterapeuta",
    },
    {
        "item": "04.09",
        "tributacao_nacional": "040901",
        "descricao": "Terapias de qualquer espécie destinadas ao tratamento físico, orgânico e mental",
        "indicado_para": "Terapias complementares",
    },
    {
        "item": "08.02",
        "tributacao_nacional": "080201",
        "descricao": "Instrução, treinamento, orientação pedagógica e educacional, avaliação de conhecimentos de qualquer natureza",
        "indicado_para": "Cursos e formações de instrutores",
    },
]

VARIAVEIS_DISCRIMINACAO = {
    "{aluno}": "Nome do aluno (tomador)",
    "{cpf}": "CPF do tomador formatado",
    "{descricao}": "Descrição do recebimento",
    "{competencia}": "Competência (MM/AAAA)",
    "{vencimento}": "Vencimento do recebimento",
    "{pagamento}": "Data do pagamento",
    "{valor}": "Valor no formato R$ 1.234,50",
    "{estudio}": "Nome do estúdio",
}
DISCRIMINACAO_PADRAO = "Aulas de {descricao} - {aluno} - competência {competencia}. Valor {valor}."


# ------------------------------------------------------------------------------------------------- dinheiro
def centavos(v: Decimal | int | str) -> Decimal:
    return Decimal(v).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def brl(v: Decimal | int | str | None) -> str:
    """`Decimal("1234.5")` -> `R$ 1.234,50`."""
    q = centavos(v or 0)
    s = f"{q:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


@dataclass(frozen=True)
class CalculoIss:
    base: Decimal
    aliquota: Decimal  # percentual (2.00 = 2%)
    valor_iss: Decimal
    valor_liquido: Decimal  # o que o estúdio recebe (desconta o ISS só quando retido pelo tomador)
    recolhido_no_das: bool  # MEI/Simples: o ISS vai na guia única; o valor é estimativa


def calcular_iss(
    valor: Decimal, aliquota: Decimal, *, deducoes: Decimal = ZERO, regime: str = "simples", retido: bool = False
) -> CalculoIss:
    """ISS = (valor - deduções) x alíquota, arredondado em centavos (meio para cima).

    - Alíquota do ISS fica entre 2% e 5% (LC 116, art. 8º-A e art. 8º, II); fora disso é erro de cadastro.
    - MEI recolhe valor fixo no DAS-MEI: o ISS da nota é zero.
    - Simples Nacional: o ISS está dentro do DAS; o valor calculado é uma estimativa para o painel.
    """
    valor = centavos(valor)
    deducoes = centavos(deducoes)
    if valor < 0 or deducoes < 0:
        raise ValueError("Valor e deduções não podem ser negativos.")
    if deducoes > valor:
        raise ValueError("As deduções não podem passar do valor do serviço.")
    base = valor - deducoes
    if regime == "mei":
        return CalculoIss(base, ZERO, ZERO, valor, True)
    aliq = Decimal(aliquota)
    if aliq < 2 or aliq > 5:
        raise ValueError("A alíquota do ISS deve estar entre 2% e 5%.")
    iss = centavos(base * aliq / 100)
    liquido = valor - iss if retido else valor
    return CalculoIss(base, aliq, iss, liquido, regime == "simples")


# ------------------------------------------------------------------------------------------------- documentos
def validar_cnpj(cnpj: str | None) -> bool:
    d = so_digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        soma = sum(int(d[i]) * pesos[i] for i in range(tamanho))
        dv = 11 - soma % 11
        if (0 if dv >= 10 else dv) != int(d[tamanho]):
            return False
    return True


def documento_valido(doc: str | None) -> bool:
    d = so_digitos(doc)
    return validar_cpf(d) if len(d) == 11 else validar_cnpj(d) if len(d) == 14 else False


def formatar_documento(doc: str | None) -> str:
    d = so_digitos(doc)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return doc or ""


def sem_acento(texto: str | None) -> str:
    """Prefeitura de SP recusa acentos em razão social e discriminação."""
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().replace("\r", "")


def limpar_texto(texto: str | None) -> str:
    """Remove caracteres de controle (exceto quebra de linha) e espaços nas pontas: o XSD nacional recusa."""
    t = re.sub(r"[\x00-\x09\x0b-\x1f\x7f]", " ", texto or "")
    return re.sub(r"[ ]{2,}", " ", t).strip()


# ------------------------------------------------------------------------------------------------- serviço
def codigo_tributacao_nacional(item_lc116: str, desdobro: str = "01") -> str:
    """`"06.04"` -> `"060401"` (item 2 + subitem 2 + desdobro nacional 2)."""
    d = so_digitos(item_lc116)
    if len(d) == 6:
        return d
    if len(d) in (3, 4):
        d = d.zfill(4)
        return d + desdobro.zfill(2)
    raise ValueError("Código de serviço da LC 116 inválido (use o formato 06.04).")


def renderizar_discriminacao(modelo: str | None, variaveis: dict[str, str]) -> str:
    """Troca as variáveis `{nome}` conhecidas; as desconhecidas ficam como estão (a tela avisa)."""
    texto = modelo or DISCRIMINACAO_PADRAO
    for chave, valor in variaveis.items():
        texto = texto.replace("{" + chave + "}", valor or "")
    return limpar_texto(texto)[:2000]


def variaveis_desconhecidas(modelo: str | None) -> list[str]:
    return sorted(set(re.findall(r"\{[a-z_]+\}", modelo or "")) - set(VARIAVEIS_DISCRIMINACAO))


def competencia_texto(d: date) -> str:
    return f"{d:%m/%Y}"


# ------------------------------------------------------------------------------------------------- chaves
def chave_recebimento(conta_receber_id: int) -> str:
    """Chave de idempotência: um recebimento gera no máximo UMA nota viva (UNIQUE no banco)."""
    return f"rec:{conta_receber_id}"


def chave_liberada(chave: str, nota_id: int) -> str:
    """Quando a nota é cancelada (ou descartada), a chave vira histórico e libera uma nova emissão."""
    return f"{chave}:x{nota_id}"


def id_dps(*, municipio: str, cnpj: str, serie: str, numero: int) -> str:
    """Identificador da DPS nacional: "DPS" + cLocEmi(7) + tpInsc(1) + inscrição(14) + série(5) + nDPS(15) = 45."""
    doc = so_digitos(cnpj)
    tp = "2" if len(doc) == 14 else "1"
    return f"DPS{so_digitos(municipio).zfill(7)}{tp}{doc.zfill(14)}{so_digitos(serie).zfill(5)}{str(numero).zfill(15)}"


def proxima_tentativa(tentativas: int, agora: datetime) -> datetime:
    """Falha de comunicação: 1, 5, 15, 30, 60 min e depois a cada 2 h."""
    minutos = [1, 5, 15, 30, 60]
    return agora + timedelta(minutes=minutos[tentativas - 1] if 0 < tentativas <= len(minutos) else 120)


MAX_TENTATIVAS = 8


# ------------------------------------------------------------------------------------------------- certificado
def situacao_certificado(valido_ate: date | None, hoje: date) -> dict:
    if valido_ate is None:
        return {"situacao": "ausente", "dias": None, "mensagem": "Nenhum certificado A1 enviado."}
    dias = (valido_ate - hoje).days
    if dias < 0:
        return {"situacao": "vencido", "dias": dias, "mensagem": f"Certificado vencido em {valido_ate:%d/%m/%Y}."}
    if dias <= 30:
        return {"situacao": "vencendo", "dias": dias,
                "mensagem": f"Certificado vence em {dias} dia(s) ({valido_ate:%d/%m/%Y}). Renove para não parar a emissão."}
    return {"situacao": "valido", "dias": dias, "mensagem": f"Válido até {valido_ate:%d/%m/%Y}."}


def agora_local(agora: datetime) -> datetime:
    return agora.astimezone(FUSO)


def dh_emissao(agora: datetime) -> str:
    """Data/hora da DPS no fuso do Brasil, sem frações e com deslocamento `-03:00` (formato do XSD nacional).

    Recuamos 1 minuto: relógio do servidor adiantado gera rejeição "data de emissão posterior ao processamento".
    """
    local = agora_local(agora - timedelta(minutes=1)).replace(microsecond=0)
    off = local.utcoffset() or timedelta(0)
    horas = int(off.total_seconds() // 3600)
    return local.strftime("%Y-%m-%dT%H:%M:%S") + f"{'-' if horas < 0 else '+'}{abs(horas):02d}:00"
