"""Regras do controle de acesso (check-in na recepção / catraca). Funções PURAS, sem banco: testadas em tests/acesso.

Quando um aluno PODE entrar (na ordem em que a regra decide):

1. Cadastro ATIVO. Inativo nunca entra ("Cadastro inativo. Procure a recepção.").
2. Financeiro: a parcela em aberto mais antiga já vencida há MAIS de `tolerancia_atraso_dias` bloqueia
   ("Mensalidade em atraso desde 05/10"). Dentro da tolerância entra, com um aviso gentil.
3. Aula marcada HOJE dentro da janela (`janela_antes_min` antes até `janela_depois_min` depois do início) libera.
   Reserva de contrato exige o contrato vigente; reserva sem contrato (aula avulsa, experimental, TotalPass/Wellhub)
   vale por si (foi paga/autorizada à parte).
4. Plano de ACESSO LIVRE (academia) com contrato vigente: entra a qualquer hora dentro do horário de funcionamento
   da unidade, mesmo sem aula marcada.
5. Senão nega com o motivo mais útil: aula mais tarde ("Sua aula é às 18:00. A entrada libera a partir das 17:30."),
   aula que já passou da janela, sem contrato vigente ou simplesmente "Sem aula marcada agora".

O check-in registra presença na aula escolhida (ver `modules/acesso/servico.py`, que usa a regra da agenda).
"""

from __future__ import annotations

import hmac
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")

# códigos estáveis (o frontend e os relatórios agrupam por eles)
OK_AULA = "aula"
OK_LIVRE = "acesso_livre"
OK_MANUAL = "manual"
NEG_INATIVO = "aluno_inativo"
NEG_ATRASO = "mensalidade_atrasada"
NEG_SEM_CONTRATO = "sem_contrato"
NEG_CEDO = "antes_da_janela"
NEG_TARDE = "depois_da_janela"
NEG_SEM_AULA = "sem_aula"
NEG_FORA_HORARIO = "fora_do_horario"
NEG_NAO_RECONHECIDO = "nao_reconhecido"
NEG_SEM_PROVA_VIDA = "sem_prova_de_vida"
NEG_CREDENCIAL = "credencial_invalida"

ROTULO_CODIGO = {
    OK_AULA: "Aula marcada",
    OK_LIVRE: "Acesso livre",
    OK_MANUAL: "Liberação manual",
    NEG_INATIVO: "Cadastro inativo",
    NEG_ATRASO: "Mensalidade em atraso",
    NEG_SEM_CONTRATO: "Sem contrato vigente",
    NEG_CEDO: "Antes do horário",
    NEG_TARDE: "Horário da aula já passou",
    NEG_SEM_AULA: "Sem aula marcada",
    NEG_FORA_HORARIO: "Fora do horário de funcionamento",
    NEG_NAO_RECONHECIDO: "Rosto não reconhecido",
    NEG_SEM_PROVA_VIDA: "Sem prova de vida",
    NEG_CREDENCIAL: "CPF/código, PIN ou QR inválido",
}


# ------------------------------------------------------------------------------------------------------ entradas
@dataclass(frozen=True)
class ConfigRegra:
    tolerancia_atraso_dias: int = 5
    janela_antes_min: int = 30
    janela_depois_min: int = 15


@dataclass(frozen=True)
class AlunoRef:
    id: int
    nome: str
    ativo: bool = True
    data_nascimento: date | None = None


@dataclass(frozen=True)
class ContratoRef:
    id: int
    inicio: date
    fim: date
    plano_nome: str = ""
    acesso_livre: bool = False

    def vigente(self, hoje: date) -> bool:
        return self.inicio <= hoje <= self.fim


@dataclass(frozen=True)
class AulaRef:
    reserva_id: int
    sessao_id: int
    dia: date
    inicio: time
    fim: time
    servico: str = ""
    profissional: str | None = None
    contrato_id: int | None = None

    def inicio_dt(self) -> datetime:
        return datetime.combine(self.dia, self.inicio, tzinfo=FUSO)

    def fim_dt(self) -> datetime:
        return datetime.combine(self.dia, self.fim, tzinfo=FUSO)


@dataclass(frozen=True)
class Janela:
    """Horário de funcionamento da unidade (no dia de hoje)."""

    inicio: time
    fim: time


@dataclass
class Decisao:
    permitido: bool
    codigo: str
    motivo: str
    aula: AulaRef | None = None
    contrato: ContratoRef | None = None
    avisos: list[str] = field(default_factory=list)
    aniversario: bool = False
    primeiro_nome: str = ""
    #: até quando a pessoa provavelmente fica no estúdio (painel "quem está aqui agora")
    previsto_sair: datetime | None = None


# ------------------------------------------------------------------------------------------------------ utilidades
def local(momento: datetime) -> datetime:
    """Instante no fuso de negócio (datetime sem fuso é tratado como já estando em Brasília)."""
    return momento.replace(tzinfo=FUSO) if momento.tzinfo is None else momento.astimezone(FUSO)


def ddmm(d: date) -> str:
    return d.strftime("%d/%m")


def hhmm(t: time) -> str:
    return t.strftime("%H:%M")


def primeiro_nome(nome: str) -> str:
    partes = (nome or "").strip().split()
    return partes[0].capitalize() if partes else ""


def faz_aniversario(nascimento: date | None, hoje: date) -> bool:
    if not nascimento:
        return False
    if nascimento.month == 2 and nascimento.day == 29 and not _bissexto(hoje.year):
        return hoje.month == 2 and hoje.day == 28
    return (nascimento.month, nascimento.day) == (hoje.month, hoje.day)


def _bissexto(ano: int) -> bool:
    return ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)


def atraso_mais_antigo(vencimentos_em_aberto: Iterable[date], hoje: date) -> date | None:
    """Vencimento mais antigo entre as parcelas ABERTAS já vencidas (vencimento < hoje)."""
    vencidas = [v for v in vencimentos_em_aberto if v < hoje]
    return min(vencidas) if vencidas else None


def janela_da_aula(aula: AulaRef, cfg: ConfigRegra) -> tuple[datetime, datetime]:
    ini = aula.inicio_dt()
    return ini - timedelta(minutes=cfg.janela_antes_min), ini + timedelta(minutes=cfg.janela_depois_min)


def dentro_do_funcionamento(janelas: Sequence[Janela], agora_local: datetime) -> Janela | None:
    t = agora_local.time()
    return next((j for j in janelas if j.inicio <= t <= j.fim), None)


# ---------------------------------------------------------------------------------------------------- a decisão
def decidir_acesso(
    *,
    aluno: AlunoRef,
    agora: datetime,
    contratos: Sequence[ContratoRef] = (),
    aulas_hoje: Sequence[AulaRef] = (),
    vencimentos_em_aberto: Iterable[date] = (),
    funcionamento_hoje: Sequence[Janela] = (),
    config: ConfigRegra = ConfigRegra(),
    permanencia_livre_min: int = 90,
) -> Decisao:
    """Decide se o aluno entra AGORA. `agora` com fuso (ou ingênuo = Brasília). Ver regras no topo do módulo."""
    momento = local(agora)
    hoje = momento.date()
    nome1 = primeiro_nome(aluno.nome)

    def nega(codigo: str, motivo: str) -> Decisao:
        return Decisao(False, codigo, motivo, primeiro_nome=nome1, aniversario=faz_aniversario(aluno.data_nascimento, hoje))

    if not aluno.ativo:
        return nega(NEG_INATIVO, "Cadastro inativo. Procure a recepção.")

    avisos: list[str] = []
    atraso = atraso_mais_antigo(vencimentos_em_aberto, hoje)
    if atraso is not None:
        dias = (hoje - atraso).days
        if dias > max(config.tolerancia_atraso_dias, 0):
            return nega(NEG_ATRASO, f"Mensalidade em atraso desde {ddmm(atraso)}. Procure a recepção.")
        avisos.append(f"Sua mensalidade venceu em {ddmm(atraso)}. Quando puder, passe na recepção.")

    vigentes = [c for c in contratos if c.vigente(hoje)]
    por_id = {c.id: c for c in vigentes}
    aulas = sorted((a for a in aulas_hoje if a.dia == hoje), key=lambda a: a.inicio)

    # 3. aula marcada dentro da janela (a mais próxima do início ganha)
    candidatas = []
    for a in aulas:
        ini, fim = janela_da_aula(a, config)
        if ini <= momento <= fim and (a.contrato_id is None or a.contrato_id in por_id):
            candidatas.append(a)
    if candidatas:
        aula = min(candidatas, key=lambda a: abs((a.inicio_dt() - momento).total_seconds()))
        return Decisao(
            True, OK_AULA, f"Aula de {aula.servico or 'hoje'} às {hhmm(aula.inicio)}", aula=aula,
            contrato=por_id.get(aula.contrato_id) if aula.contrato_id else None, avisos=avisos,
            aniversario=faz_aniversario(aluno.data_nascimento, hoje), primeiro_nome=nome1,
            previsto_sair=aula.fim_dt() + timedelta(minutes=15),
        )

    # 4. plano de acesso livre dentro do horário de funcionamento
    livres = [c for c in vigentes if c.acesso_livre]
    if livres:
        janela = dentro_do_funcionamento(funcionamento_hoje, momento)
        if janela is not None:
            sair = min(momento + timedelta(minutes=permanencia_livre_min), datetime.combine(hoje, janela.fim, tzinfo=FUSO))
            return Decisao(True, OK_LIVRE, f"Acesso livre ({livres[0].plano_nome})".replace(" ()", ""), contrato=livres[0],
                           avisos=avisos, aniversario=faz_aniversario(aluno.data_nascimento, hoje), primeiro_nome=nome1,
                           previsto_sair=sair)
        proxima = next((j for j in sorted(funcionamento_hoje, key=lambda j: j.inicio) if j.inicio > momento.time()), None)
        if proxima:
            return nega(NEG_FORA_HORARIO, f"Fora do horário de funcionamento. Abrimos às {hhmm(proxima.inicio)}.")
        return nega(NEG_FORA_HORARIO, "Fora do horário de funcionamento.")

    # 5. o melhor motivo para negar
    futuras = [a for a in aulas if janela_da_aula(a, config)[0] > momento]
    passadas = [a for a in aulas if janela_da_aula(a, config)[1] < momento]
    if futuras:
        a = futuras[0]
        abre = janela_da_aula(a, config)[0]
        return nega(NEG_CEDO, f"Sua aula de {a.servico or 'hoje'} é às {hhmm(a.inicio)}. A entrada libera a partir das {abre.strftime('%H:%M')}.")
    if passadas:
        a = passadas[-1]
        fecha = janela_da_aula(a, config)[1]
        return nega(NEG_TARDE, f"O horário de entrada da sua aula das {hhmm(a.inicio)} terminou às {fecha.strftime('%H:%M')}. Procure a recepção.")
    if not vigentes:
        anteriores = [c for c in contratos if c.fim < hoje]
        if anteriores:
            ultimo = max(anteriores, key=lambda c: c.fim)
            return nega(NEG_SEM_CONTRATO, f"Seu contrato terminou em {ultimo.fim.strftime('%d/%m/%Y')}. Procure a recepção para renovar.")
        return nega(NEG_SEM_CONTRATO, "Sem contrato vigente. Procure a recepção.")
    return nega(NEG_SEM_AULA, "Sem aula marcada agora.")


# ------------------------------------------------------------------------------------------- reconhecimento facial
class DescritorInvalido(ValueError):
    pass


DIMENSAO_MIN = 64
DIMENSAO_MAX = 2048


def normalizar_descritor(valores: Sequence[float]) -> list[float]:
    """Valida (tamanho, números finitos, não nulo) e devolve o vetor com norma 1 (cosseno vira produto escalar)."""
    if not (DIMENSAO_MIN <= len(valores) <= DIMENSAO_MAX):
        raise DescritorInvalido(f"Descritor com tamanho inválido ({len(valores)}).")
    try:
        v = [float(x) for x in valores]
    except (TypeError, ValueError):
        raise DescritorInvalido("Descritor com valores inválidos.") from None
    if not all(math.isfinite(x) for x in v):
        raise DescritorInvalido("Descritor com valores inválidos.")
    norma = math.sqrt(sum(x * x for x in v))
    if norma < 1e-9:
        raise DescritorInvalido("Descritor vazio.")
    return [x / norma for x in v]


def similaridade(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosseno entre dois vetores JÁ normalizados (1 = idênticos, 0 = sem relação)."""
    if len(a) != len(b):
        return -1.0
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


@dataclass(frozen=True)
class Correspondencia:
    aluno_id: int | None
    similaridade: float
    segunda: float  # melhor similaridade de OUTRO aluno (ambiguidade)
    motivo: str = ""

    @property
    def reconhecido(self) -> bool:
        return self.aluno_id is not None


def melhor_correspondencia(
    consulta: Sequence[float],
    cadastrados: Iterable[tuple[int, Sequence[float]]],
    *,
    limiar: float,
    margem: float = 0.03,
) -> Correspondencia:
    """Compara o descritor do momento com os cadastrados (aluno_id, vetor normalizado).

    Reconhece quando a melhor similaridade passa do `limiar` E fica pelo menos `margem` acima da melhor de outro aluno
    (dois alunos parecidos demais = não reconhece; melhor negar do que liberar a pessoa errada)."""
    melhor_por_aluno: dict[int, float] = {}
    for aluno_id, vetor in cadastrados:
        s = similaridade(consulta, vetor)
        if s > melhor_por_aluno.get(aluno_id, -2.0):
            melhor_por_aluno[aluno_id] = s
    if not melhor_por_aluno:
        return Correspondencia(None, 0.0, 0.0, "Nenhum rosto cadastrado.")
    ordem = sorted(melhor_por_aluno.items(), key=lambda kv: kv[1], reverse=True)
    top_id, top = ordem[0]
    segunda = ordem[1][1] if len(ordem) > 1 else 0.0
    if top < limiar:
        return Correspondencia(None, top, segunda, "Não reconheci você. Tente de novo ou use o CPF.")
    if top - segunda < margem:
        return Correspondencia(None, top, segunda, "Não consegui ter certeza de quem é. Use o CPF ou o QR do app.")
    return Correspondencia(top_id, top, segunda)


# --------------------------------------------------------------------------------------------- QR do app do aluno
PREFIXO_QR = "MFQR1"


def assinar_qr(chave: bytes, aluno_id: int, expira_epoch: int, nonce: str) -> str:
    corpo = f"{PREFIXO_QR}.{aluno_id}.{expira_epoch}.{nonce}"
    sig = hmac.new(chave, corpo.encode(), "sha256").hexdigest()[:32]
    return f"{corpo}.{sig}"


def ler_qr(chave: bytes, valor: str, agora_epoch: int) -> tuple[int, str] | None:
    """(aluno_id, nonce) de um QR válido e dentro do prazo, ou None."""
    partes = (valor or "").strip().split(".")
    if len(partes) != 5 or partes[0] != PREFIXO_QR:
        return None
    _, aluno, expira, nonce, sig = partes
    if not (aluno.isdigit() and expira.isdigit()) or not nonce:
        return None
    esperado = assinar_qr(chave, int(aluno), int(expira), nonce).rsplit(".", 1)[1]
    if not hmac.compare_digest(esperado, sig):
        return None
    if int(expira) < agora_epoch:
        return None
    return int(aluno), nonce


# --------------------------------------------------------------------------------------------- PIN e documento
def so_digitos(texto: str | None) -> str:
    return "".join(c for c in (texto or "") if c.isdigit())


def pin_valido(pin: str) -> bool:
    """PIN de 4 a 6 dígitos, sem sequência óbvia (1234, 0000...)."""
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        return False
    if len(set(pin)) == 1:
        return False
    return pin not in "0123456789" and pin not in "9876543210"


def prova_de_vida_ok(piscou: bool, real: float | None, live: float | None, minimo: float = 0.5) -> bool:
    """Prova de vida básica feita no navegador: piscou OU os modelos antispoof ("rosto real") e liveness passaram.

    Atenção: roda no cliente (totem autenticado). Impede foto impressa/tela na frente da câmera comum; não substitui
    câmera com sensor de profundidade."""
    return bool(piscou) or ((real or 0.0) >= minimo and (live or 0.0) >= minimo)
