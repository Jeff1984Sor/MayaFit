"""Serviço do controle de acesso: monta os dados da regra (`app.domain.acesso`), identifica o aluno (rosto, CPF/código
+ PIN, QR do app), registra a tentativa, marca a presença na aula (pela função da agenda) e aciona a catraca.

CONTRATO para outros módulos (assinaturas estáveis, testadas em tests/acesso):

- ``avaliar_acesso(db, aluno, agora, unidade_id=None) -> Decisao``: só decide (não grava nada).
- ``checkin(db, aluno, *, metodo, agora, dispositivo=None, usuario=None, ...) -> (RegistroAcesso, Decisao, Acionamento)``.
- ``presentes_agora(db, agora)``: quem está no estúdio agora.

Nada aqui faz ``commit``: quem chama controla a transação (como na agenda).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import struct
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import segredos
from app.core.config import settings
from app.core.db import agora as agora_utc
from app.core.models import Usuario
from app.core.security import hash_senha, verificar_senha
from app.domain import acesso as dom
from app.modules.acesso import drivers
from app.modules.acesso.drivers.base import DadosCatraca
from app.modules.acesso.models import (
    AcessoConfig,
    Catraca,
    ComandoCatraca,
    ConsentimentoBiometria,
    CredencialAluno,
    DescritorFacial,
    Dispositivo,
    MetodoAcesso,
    ModoAcionamento,
    RegistroAcesso,
    Sentido,
)
from app.modules.agenda import servico as agenda_servico
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.alunos.models import Aluno, StatusAluno
from app.modules.cadastros.models import HorarioFuncionamento, Plano, Profissional, TipoServico
from app.modules.contratos.models import Contrato
from app.modules.financeiro.models import ContaReceber, StatusReceber

log = logging.getLogger(__name__)

MAX_DESCRITORES_POR_ALUNO = 5
MAX_ERROS_PIN = 5
BLOQUEIO_PIN = timedelta(minutes=15)
VALIDADE_CODIGO_TOTEM = timedelta(minutes=15)
VALIDADE_QR_S = 90
VALIDADE_COMANDO = timedelta(seconds=30)
ONLINE_SE_CONTATO_EM = timedelta(minutes=2)
PREFIXO_TOKEN = "mfdisp_"
STATUS_DA_AULA = (StatusReserva.RESERVADA, StatusReserva.PENDENTE, StatusReserva.CONCLUIDA)

TERMO_PADRAO = (
    "TERMO DE CONSENTIMENTO PARA USO DE BIOMETRIA FACIAL\n\n"
    "Autorizo o estúdio a coletar e tratar o meu dado biométrico facial (dado pessoal sensível, art. 11 da Lei "
    "13.709/2018 — LGPD) com a ÚNICA finalidade de identificar a minha entrada no estúdio (check-in e liberação da "
    "catraca) e registrar a presença nas aulas.\n\n"
    "Estou ciente de que: (1) não é guardada nenhuma foto, apenas uma representação numérica do rosto, cifrada; "
    "(2) o dado não é compartilhado com terceiros; (3) posso usar outra forma de entrada (CPF/código com PIN ou QR "
    "do aplicativo) se não quiser a biometria; (4) posso revogar este consentimento a qualquer momento na recepção, "
    "e a biometria é apagada na hora; (5) o dado é apagado também quando eu deixar de ser aluno."
)


class ErroAcesso(Exception):
    status = 400

    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        if status is not None:
            self.status = status


# --------------------------------------------------------------------------------------------------- configuração
def obter_config(db: Session) -> AcessoConfig:
    cfg = db.get(AcessoConfig, 1)
    if cfg is None:
        cfg = AcessoConfig(id=1, planos_livres=[], termo_biometria=TERMO_PADRAO, tolerancia_atraso_dias=5,
                           janela_antes_min=30, janela_depois_min=15, permanencia_livre_min=90, limiar_similaridade=0.6,
                           margem_ambiguidade=0.03, exigir_prova_vida=True, exigir_pin=True, registrar_presenca=True)
        db.add(cfg)
        db.flush()
    if not cfg.termo_biometria:
        cfg.termo_biometria = TERMO_PADRAO
    return cfg


def config_regra(cfg: AcessoConfig) -> dom.ConfigRegra:
    return dom.ConfigRegra(cfg.tolerancia_atraso_dias, cfg.janela_antes_min, cfg.janela_depois_min)


# --------------------------------------------------------------------------------------------- dados para a regra
def _hoje_local(agora: datetime) -> date:
    return dom.local(agora).date()


def dados_da_regra(db: Session, aluno: Aluno, agora: datetime, unidade_id: int | None = None) -> dict:
    """Busca no banco tudo que `dom.decidir_acesso` precisa (contratos, aulas de hoje, parcelas, funcionamento)."""
    cfg = obter_config(db)
    hoje = _hoje_local(agora)
    livres = set(cfg.planos_livres or [])

    contratos = []
    for c, plano_nome in db.execute(
        select(Contrato, Plano.nome).join(Plano, Plano.id == Contrato.plano_id).where(Contrato.aluno_id == aluno.id)
    ).all():
        contratos.append(dom.ContratoRef(c.id, c.data_inicio, c.data_fim, plano_nome or "", c.plano_id in livres))

    aulas = []
    q = (
        select(Reserva, AulaSessao, TipoServico.nome, Profissional.nome)
        .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
        .join(TipoServico, TipoServico.id == AulaSessao.tipo_servico_id)
        .outerjoin(Profissional, Profissional.id == AulaSessao.profissional_id)
        .where(Reserva.aluno_id == aluno.id, AulaSessao.data == hoje, Reserva.status.in_(STATUS_DA_AULA))
    )
    for r, s, servico_nome, prof_nome in db.execute(q).all():
        aulas.append(dom.AulaRef(r.id, s.id, s.data, s.hora_inicio, s.hora_fim, servico_nome or "", prof_nome, r.contrato_id))

    vencimentos = list(db.scalars(
        select(ContaReceber.vencimento).where(ContaReceber.aluno_id == aluno.id, ContaReceber.status == StatusReceber.ABERTO,
                                              ContaReceber.vencimento < hoje)
    ))

    un = unidade_id or aluno.unidade_id
    janelas = [
        dom.Janela(h.hora_inicio, h.hora_fim)
        for h in db.scalars(select(HorarioFuncionamento).where(
            HorarioFuncionamento.unidade_id == un, HorarioFuncionamento.dia_semana == hoje.weekday(),
            HorarioFuncionamento.ativo.is_(True)))
    ]
    return {
        "aluno": dom.AlunoRef(aluno.id, aluno.nome, StatusAluno(aluno.status) == StatusAluno.ATIVO, aluno.data_nascimento),
        "contratos": contratos,
        "aulas_hoje": aulas,
        "vencimentos_em_aberto": vencimentos,
        "funcionamento_hoje": janelas,
        "config": config_regra(cfg),
        "permanencia_livre_min": cfg.permanencia_livre_min,
    }


def avaliar_acesso(db: Session, aluno: Aluno, agora: datetime | None = None, unidade_id: int | None = None) -> dom.Decisao:
    agora = agora or agora_utc()
    return dom.decidir_acesso(agora=agora, **dados_da_regra(db, aluno, agora, unidade_id))


# ------------------------------------------------------------------------------------------------------ catraca
def dados_catraca(c: Catraca) -> DadosCatraca:
    senha = None
    if c.senha_cifrada:
        try:
            senha = segredos.decifrar_texto(c.senha_cifrada)
        except segredos.SegredoInvalido:
            senha = None
    return DadosCatraca(id=c.id, nome=c.nome, host=c.host, porta=c.porta, usar_https=c.usar_https, usuario=c.usuario,
                        senha=senha, sentido_entrada=c.sentido_entrada, acao_liberacao=c.acao_liberacao, porta_rele=c.porta_rele)


@dataclass
class Acionamento:
    catraca_id: int | None
    catraca_nome: str | None
    modo: str | None
    status: str  # liberada | falhou | pendente | sem_catraca
    mensagem: str = ""
    plano: drivers.PlanoNavegador | None = None
    comando_id: int | None = None


def acionar_catraca(db: Session, catraca: Catraca | None, *, sentido: str = "entrada", acao: str = "liberar",
                    registro: RegistroAcesso | None = None, agora: datetime | None = None) -> Acionamento:
    """Libera (ou testa) a catraca conforme o modo: servidor chama já; agente enfileira; totem recebe o plano HTTP."""
    if catraca is None or not catraca.ativo:
        a = Acionamento(None, None, None, "sem_catraca", "Sem catraca configurada para este ponto.")
    else:
        driver = drivers.obter(catraca.driver)
        dados = dados_catraca(catraca)
        modo = ModoAcionamento(catraca.modo)
        if modo == ModoAcionamento.servidor:
            r = driver.status(dados) if acao == "status" else driver.liberar(dados, sentido)  # type: ignore[arg-type]
            a = Acionamento(catraca.id, catraca.nome, modo.value, ("liberada" if acao == "liberar" else "ok") if r.ok else "falhou", r.mensagem)
        elif modo == ModoAcionamento.agente:
            momento = agora or agora_utc()
            cmd = ComandoCatraca(catraca_id=catraca.id, acao=acao, sentido=sentido, registro_id=registro.id if registro else None,
                                 status="pendente", criado_em=momento, expira_em=momento + VALIDADE_COMANDO)
            db.add(cmd)
            db.flush()
            a = Acionamento(catraca.id, catraca.nome, modo.value, "pendente", "Comando enviado ao agente local.", comando_id=cmd.id)
        else:
            plano = driver.plano_navegador(dados, acao, sentido)  # type: ignore[arg-type]
            if plano is None:
                a = Acionamento(catraca.id, catraca.nome, modo.value, "falhou",
                                "Este driver não pode ser acionado pelo navegador do totem. Use o agente local.")
            elif not plano.passos:  # simulado: nada a chamar
                r = driver.status(dados) if acao == "status" else driver.liberar(dados, sentido)  # type: ignore[arg-type]
                a = Acionamento(catraca.id, catraca.nome, modo.value, ("liberada" if acao == "liberar" else "ok") if r.ok else "falhou", r.mensagem)
            else:
                a = Acionamento(catraca.id, catraca.nome, modo.value, "pendente", "Acionando a catraca pela rede local.", plano=plano)
    if registro is not None:
        registro.catraca_id = a.catraca_id
        registro.catraca_status = a.status
        registro.catraca_detalhe = a.mensagem[:300]
    return a


def catraca_do_dispositivo(db: Session, dispositivo: Dispositivo | None) -> Catraca | None:
    if dispositivo is None or dispositivo.catraca_id is None:
        return None
    return db.get(Catraca, dispositivo.catraca_id)


# ----------------------------------------------------------------------------------------------------- check-in
def _descricao_aula(a: dom.AulaRef | None) -> str | None:
    if a is None:
        return None
    partes = [a.servico or "Aula", f"{dom.hhmm(a.inicio)}–{dom.hhmm(a.fim)}"]
    if a.profissional:
        partes.append(f"com {a.profissional.split()[0]}")
    return " · ".join(partes)


def _registrar_presenca(db: Session, decisao: dom.Decisao, agora: datetime) -> bool:
    """Marca "chegou" na reserva pela regra da agenda (grava `confirmada_em`). Falha de lotação não impede a entrada."""
    if decisao.aula is None:
        return False
    reserva = db.get(Reserva, decisao.aula.reserva_id)
    if reserva is None:
        return False
    if StatusReserva(reserva.status) == StatusReserva.RESERVADA and reserva.confirmada_em is not None:
        return True  # já tinha chegado (reentrada)
    if StatusReserva(reserva.status) == StatusReserva.CONCLUIDA:
        return True
    try:
        with agenda_servico.savepoint(db):
            agenda_servico.aplicar_acao_presenca(db, reserva.id, "chegou", agora=agora)
        return True
    except agenda_servico.ErroAgenda as e:  # ex.: aula lotada ao transformar PENDENTE em RESERVADA
        log.warning("Presença não registrada na reserva %s: %s", reserva.id, e)
        decisao.avisos.append("Não consegui marcar sua presença na aula. Avise a recepção.")
        return False


def novo_registro(db: Session, *, aluno: Aluno | None, permitido: bool, codigo: str, motivo: str, metodo: MetodoAcesso,
                  agora: datetime, dispositivo: Dispositivo | None = None, usuario: Usuario | None = None,
                  sentido: str = "entrada", similaridade: float | None = None) -> RegistroAcesso:
    reg = RegistroAcesso(
        em=agora, aluno_id=aluno.id if aluno else None, aluno_nome=aluno.nome if aluno else None, permitido=permitido,
        codigo=codigo, motivo=motivo[:300], metodo=metodo, sentido=Sentido(sentido),
        dispositivo_id=dispositivo.id if dispositivo else None, dispositivo_nome=dispositivo.nome if dispositivo else None,
        usuario_id=usuario.id if usuario else None, usuario_nome=usuario.nome if usuario else None,
        similaridade=round(similaridade, 4) if similaridade is not None else None,
    )
    db.add(reg)
    db.flush()
    return reg


def checkin(db: Session, aluno: Aluno, *, metodo: MetodoAcesso, agora: datetime | None = None,
            dispositivo: Dispositivo | None = None, similaridade: float | None = None,
            qr_nonce: str | None = None) -> tuple[RegistroAcesso, dom.Decisao, Acionamento | None]:
    """Decide, registra, marca presença (se permitido) e aciona a catraca do dispositivo."""
    agora = agora or agora_utc()
    cfg = obter_config(db)
    decisao = avaliar_acesso(db, aluno, agora, dispositivo.unidade_id if dispositivo else None)
    reg = novo_registro(db, aluno=aluno, permitido=decisao.permitido, codigo=decisao.codigo, motivo=decisao.motivo,
                        metodo=metodo, agora=agora, dispositivo=dispositivo, similaridade=similaridade)
    reg.aula_descricao = _descricao_aula(decisao.aula)
    acion = None
    if decisao.permitido:
        reg.reserva_id = decisao.aula.reserva_id if decisao.aula else None
        reg.previsto_sair = decisao.previsto_sair.astimezone(UTC) if decisao.previsto_sair else None
        reg.qr_nonce = qr_nonce
        if cfg.registrar_presenca:
            reg.presenca_registrada = _registrar_presenca(db, decisao, agora)
        acion = acionar_catraca(db, catraca_do_dispositivo(db, dispositivo), registro=reg, agora=agora)
    db.flush()
    return reg, decisao, acion


def titulo_da_decisao(cfg: AcessoConfig, d: dom.Decisao) -> str:
    nome = d.primeiro_nome or ""
    if not d.permitido:
        return f"{nome}, não consegui liberar" if nome else "Acesso não liberado"
    if d.aniversario:
        return f"Feliz aniversário, {nome}!"
    modelo = (cfg.mensagem_boas_vindas or "").strip()
    if modelo:
        return modelo.replace("{nome}", nome)
    return f"Olá, {nome}! Boa aula." if d.aula else f"Olá, {nome}! Bom treino."


# ----------------------------------------------------------------------------------------- biometria (descritores)
def _empacotar(vetor: list[float]) -> bytes:
    return struct.pack(f"<{len(vetor)}f", *vetor)


def _desempacotar(dados: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(dados) // 4}f", dados))


def cifrar_descritor(vetor: list[float]) -> bytes:
    return segredos.cifrar(_empacotar(vetor))


def decifrar_descritor(dados: bytes) -> list[float]:
    return _desempacotar(segredos.decifrar(dados))


def consentimento_ativo(db: Session, aluno_id: int) -> ConsentimentoBiometria | None:
    return db.scalar(select(ConsentimentoBiometria).where(
        ConsentimentoBiometria.aluno_id == aluno_id, ConsentimentoBiometria.revogado_em.is_(None)
    ).order_by(ConsentimentoBiometria.id.desc()))


def registrar_consentimento(db: Session, aluno: Aluno, *, texto: str, coletado_por: Usuario | None, coletado_por_nome: str | None = None,
                            canal: str = "recepcao", ip: str | None = None, agora: datetime | None = None) -> ConsentimentoBiometria:
    atual = consentimento_ativo(db, aluno.id)
    h = hashlib.sha256(texto.encode()).hexdigest()
    if atual is not None and atual.hash_termo == h:
        return atual
    if atual is not None:  # termo mudou: o novo aceite substitui o antigo (os descritores passam para o novo)
        atual.revogado_em = agora or agora_utc()
        atual.revogado_por_nome = "Substituído por novo aceite"
        atual.motivo_revogacao = "Novo termo aceito"
    c = ConsentimentoBiometria(aluno_id=aluno.id, texto_termo=texto, hash_termo=h, coletado_em=agora or agora_utc(),
                               coletado_por_id=coletado_por.id if coletado_por else None,
                               coletado_por_nome=coletado_por_nome or (coletado_por.nome if coletado_por else "Sistema"),
                               canal=canal, ip=ip)
    db.add(c)
    db.flush()
    if atual is not None:
        for d in db.scalars(select(DescritorFacial).where(DescritorFacial.aluno_id == aluno.id)):
            d.consentimento_id = c.id
    return c


def adicionar_descritores(db: Session, aluno: Aluno, vetores: list[list[float]], *, origem: str, criado_por_nome: str | None,
                          qualidade: float | None = None) -> list[DescritorFacial]:
    cons = consentimento_ativo(db, aluno.id)
    if cons is None:
        raise ErroAcesso("Registre o consentimento do aluno antes de cadastrar o rosto (LGPD).", 409)
    try:
        normalizados = [dom.normalizar_descritor(v) for v in vetores]
    except dom.DescritorInvalido as e:
        raise ErroAcesso(str(e), 422) from None
    dims = {len(v) for v in normalizados}
    if len(dims) != 1:
        raise ErroAcesso("Descritores com tamanhos diferentes.", 422)
    dim = dims.pop()
    existentes = []
    for e in db.scalars(select(DescritorFacial).where(DescritorFacial.aluno_id == aluno.id).order_by(DescritorFacial.id)):
        if e.dimensao != dim:  # trocou de modelo: os antigos não servem para comparar
            db.delete(e)
        else:
            existentes.append(e)
    sobra = len(existentes) + len(normalizados) - MAX_DESCRITORES_POR_ALUNO
    for velho in existentes[: max(sobra, 0)]:
        db.delete(velho)
    novos = [DescritorFacial(aluno_id=aluno.id, consentimento_id=cons.id, descritor_cifrado=cifrar_descritor(v), dimensao=len(v),
                             origem=origem, qualidade=qualidade, criado_por_nome=criado_por_nome) for v in normalizados]
    db.add_all(novos)
    db.flush()
    return novos


def apagar_biometria(db: Session, aluno: Aluno, *, por_nome: str, motivo: str, agora: datetime | None = None) -> int:
    """Apaga TODOS os descritores e revoga o consentimento ativo. Devolve quantos descritores saíram."""
    n = 0
    for d in db.scalars(select(DescritorFacial).where(DescritorFacial.aluno_id == aluno.id)):
        db.delete(d)
        n += 1
    cons = consentimento_ativo(db, aluno.id)
    if cons is not None:
        cons.revogado_em = agora or agora_utc()
        cons.revogado_por_nome = por_nome
        cons.motivo_revogacao = motivo[:300]
    db.flush()
    return n


def vetores_cadastrados(db: Session) -> list[tuple[int, list[float]]]:
    """(aluno_id, vetor) de alunos ATIVOS com consentimento ativo. Decifra só em memória."""
    q = (
        select(DescritorFacial.aluno_id, DescritorFacial.descritor_cifrado)
        .join(Aluno, Aluno.id == DescritorFacial.aluno_id)
        .join(ConsentimentoBiometria, ConsentimentoBiometria.id == DescritorFacial.consentimento_id)
        .where(Aluno.status == StatusAluno.ATIVO, ConsentimentoBiometria.revogado_em.is_(None))
    )
    out = []
    for aluno_id, cifrado in db.execute(q).all():
        try:
            out.append((aluno_id, decifrar_descritor(cifrado)))
        except segredos.SegredoInvalido:
            log.error("Descritor do aluno %s não pôde ser decifrado (MASTER_KEY?)", aluno_id)
    return out


def identificar_rosto(db: Session, descritor: list[float]) -> dom.Correspondencia:
    cfg = obter_config(db)
    try:
        consulta = dom.normalizar_descritor(descritor)
    except dom.DescritorInvalido as e:
        raise ErroAcesso(str(e), 422) from None
    cadastrados = [(a, v) for a, v in vetores_cadastrados(db) if len(v) == len(consulta)]
    return dom.melhor_correspondencia(consulta, cadastrados, limiar=cfg.limiar_similaridade, margem=cfg.margem_ambiguidade)


# --------------------------------------------------------------------------------------------- PIN e documento
def _credencial(db: Session, aluno_id: int, criar: bool = False) -> CredencialAluno | None:
    c = db.scalar(select(CredencialAluno).where(CredencialAluno.aluno_id == aluno_id))
    if c is None and criar:
        c = CredencialAluno(aluno_id=aluno_id, tentativas_erradas=0)
        db.add(c)
        db.flush()
    return c


def definir_pin(db: Session, aluno: Aluno, pin: str) -> None:
    if not dom.pin_valido(pin):
        raise ErroAcesso("PIN fraco: use de 4 a 6 dígitos, sem sequência (1234) nem repetição (1111).", 422)
    c = _credencial(db, aluno.id, criar=True)
    c.pin_hash = hash_senha(pin)
    c.tentativas_erradas = 0
    c.bloqueado_ate = None
    db.flush()


def remover_pin(db: Session, aluno: Aluno) -> None:
    c = _credencial(db, aluno.id)
    if c is not None:
        c.pin_hash = None
        db.flush()


def aluno_por_documento(db: Session, documento: str) -> Aluno | None:
    d = dom.so_digitos(documento)
    if not d:
        return None
    if len(d) == 11:
        a = db.scalar(select(Aluno).where(Aluno.cpf == d))
        if a is not None:
            return a
    if len(d) <= 9:
        return db.scalar(select(Aluno).where(Aluno.codigo_legado == int(d)))
    return None


def conferir_pin(db: Session, aluno: Aluno, pin: str | None, agora: datetime | None = None) -> None:
    """Levanta ErroAcesso se o PIN for exigido e estiver errado/ausente. Erros seguidos bloqueiam por 15 minutos."""
    cfg = obter_config(db)
    c = _credencial(db, aluno.id)
    if not cfg.exigir_pin and not (c and c.pin_hash):
        return
    if c is None or not c.pin_hash:
        raise ErroAcesso("Você ainda não tem PIN. Peça para a recepção cadastrar.", 403)
    momento = agora or agora_utc()
    if c.bloqueado_ate and c.bloqueado_ate > momento:
        raise ErroAcesso("Muitas tentativas com PIN errado. Aguarde alguns minutos ou procure a recepção.", 429)
    if not pin or not verificar_senha(pin, c.pin_hash):
        c.tentativas_erradas = (c.tentativas_erradas or 0) + 1
        if c.tentativas_erradas >= MAX_ERROS_PIN:
            c.bloqueado_ate = momento + BLOQUEIO_PIN
            c.tentativas_erradas = 0
        db.flush()
        raise ErroAcesso("CPF/código ou PIN incorretos.", 401)
    c.tentativas_erradas = 0
    c.bloqueado_ate = None


# ----------------------------------------------------------------------------------------- código de cadastro no totem
def _hash_codigo(aluno_id: int, codigo: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"cadastro-totem:{aluno_id}:{codigo}".encode(), "sha256").hexdigest()


def gerar_codigo_totem(db: Session, aluno: Aluno, usuario: Usuario, agora: datetime | None = None) -> tuple[str, datetime]:
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    expira = (agora or agora_utc()) + VALIDADE_CODIGO_TOTEM
    c = _credencial(db, aluno.id, criar=True)
    c.codigo_cadastro_hash = _hash_codigo(aluno.id, codigo)
    c.codigo_cadastro_expira = expira
    c.codigo_cadastro_por_id = usuario.id
    c.codigo_cadastro_por_nome = usuario.nome
    db.flush()
    return codigo, expira


def conferir_codigo_totem(db: Session, documento: str, codigo: str, agora: datetime | None = None) -> tuple[Aluno, CredencialAluno]:
    aluno = aluno_por_documento(db, documento)
    c = _credencial(db, aluno.id) if aluno else None
    momento = agora or agora_utc()
    if (aluno is None or c is None or not c.codigo_cadastro_hash or not c.codigo_cadastro_expira
            or c.codigo_cadastro_expira < momento
            or not hmac.compare_digest(c.codigo_cadastro_hash, _hash_codigo(aluno.id, codigo))):
        raise ErroAcesso("Código inválido ou vencido. Peça um novo código na recepção.", 403)
    if StatusAluno(aluno.status) != StatusAluno.ATIVO:
        raise ErroAcesso("Cadastro inativo. Procure a recepção.", 403)
    return aluno, c


# ------------------------------------------------------------------------------------------------------ QR do app
def _chave_qr() -> bytes:
    return hashlib.sha256(f"acesso-qr:{settings.jwt_secret}".encode()).digest()


def emitir_qr(aluno_id: int, agora: datetime | None = None) -> tuple[str, datetime]:
    momento = agora or agora_utc()
    expira = int(momento.timestamp()) + VALIDADE_QR_S
    return dom.assinar_qr(_chave_qr(), aluno_id, expira, secrets.token_hex(6)), datetime.fromtimestamp(expira, UTC)


def ler_qr(db: Session, valor: str, agora: datetime | None = None) -> tuple[Aluno, str]:
    momento = agora or agora_utc()
    lido = dom.ler_qr(_chave_qr(), valor, int(momento.timestamp()))
    if lido is None:
        raise ErroAcesso("QR inválido ou vencido. Abra o app de novo para gerar outro.", 401)
    aluno_id, nonce = lido
    if db.scalar(select(RegistroAcesso.id).where(RegistroAcesso.qr_nonce == nonce)) is not None:
        raise ErroAcesso("Este QR já foi usado. Abra o app de novo para gerar outro.", 401)
    aluno = db.get(Aluno, aluno_id)
    if aluno is None:
        raise ErroAcesso("QR inválido ou vencido. Abra o app de novo para gerar outro.", 401)
    return aluno, nonce


# ------------------------------------------------------------------------------------------------------ dispositivos
def hash_token(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def novo_token(d: Dispositivo) -> str:
    valor = PREFIXO_TOKEN + secrets.token_urlsafe(32)
    d.token_hash = hash_token(valor)
    d.token_final = valor[-4:]
    return valor


def autenticar_dispositivo(db: Session, valor: str | None, tipo: str | None = None, agora: datetime | None = None) -> Dispositivo | None:
    if not valor or not valor.startswith(PREFIXO_TOKEN):
        return None
    h = hash_token(valor)
    d = db.scalar(select(Dispositivo).where(Dispositivo.token_hash == h, Dispositivo.ativo.is_(True)))
    if d is None or not d.token_hash or not hmac.compare_digest(d.token_hash, h):
        return None
    if tipo and d.tipo != tipo:
        return None
    momento = agora or agora_utc()
    if d.ultimo_contato is None or momento - d.ultimo_contato > timedelta(seconds=30):
        d.ultimo_contato = momento
        db.commit()
    return d


def online(d: Dispositivo, agora: datetime | None = None) -> bool:
    return bool(d.ativo and d.ultimo_contato and (agora or agora_utc()) - d.ultimo_contato <= ONLINE_SE_CONTATO_EM)


# ------------------------------------------------------------------------------------------------------ agente local
def comandos_pendentes(db: Session, agente: Dispositivo, agora: datetime | None = None) -> list[tuple[ComandoCatraca, Catraca]]:
    """Comandos pendentes das catracas em modo agente (da unidade do agente, ou todas se ele não tiver unidade).
    Marca como entregues; os vencidos viram "expirado" (giro atrasado é pior que giro nenhum)."""
    momento = agora or agora_utc()
    q = select(ComandoCatraca, Catraca).join(Catraca, Catraca.id == ComandoCatraca.catraca_id).where(
        ComandoCatraca.status == "pendente", Catraca.modo == ModoAcionamento.agente)
    if agente.catraca_id:
        q = q.where(Catraca.id == agente.catraca_id)
    elif agente.unidade_id:
        q = q.where(Catraca.unidade_id == agente.unidade_id)
    out = []
    for cmd, cat in db.execute(q.order_by(ComandoCatraca.id)).all():
        if cmd.expira_em < momento:
            cmd.status = "expirado"
            _refletir_no_registro(db, cmd, False, "O agente local não buscou o comando a tempo.")
            continue
        cmd.status = "entregue"
        cmd.entregue_em = momento
        out.append((cmd, cat))
    db.flush()
    return out


def _refletir_no_registro(db: Session, cmd: ComandoCatraca, ok: bool, mensagem: str) -> None:
    if cmd.registro_id:
        reg = db.get(RegistroAcesso, cmd.registro_id)
        if reg is not None:
            reg.catraca_status = "liberada" if ok else "falhou"
            reg.catraca_detalhe = mensagem[:300]


def concluir_comando(db: Session, agente: Dispositivo, comando_id: int, ok: bool, mensagem: str, agora: datetime | None = None) -> ComandoCatraca:
    cmd = db.get(ComandoCatraca, comando_id)
    if cmd is None or cmd.status not in ("entregue", "pendente"):
        raise ErroAcesso("Comando não encontrado.", 404)
    cat = db.get(Catraca, cmd.catraca_id)
    if agente.catraca_id and agente.catraca_id != cmd.catraca_id or (agente.unidade_id and cat and cat.unidade_id
                                                                     and cat.unidade_id != agente.unidade_id):
        raise ErroAcesso("Comando não encontrado.", 404)
    cmd.status = "ok" if ok else "erro"
    cmd.concluido_em = agora or agora_utc()
    cmd.resultado = mensagem[:300]
    if cmd.acao == "status" and cat is not None:
        cat.ultimo_teste_em, cat.ultimo_teste_ok, cat.ultimo_teste_detalhe = cmd.concluido_em, ok, mensagem[:300]
    _refletir_no_registro(db, cmd, ok, mensagem)
    db.flush()
    return cmd


# ------------------------------------------------------------------------------------------------------ painel
def inicio_do_dia_utc(agora: datetime) -> datetime:
    hoje = _hoje_local(agora)
    return datetime.combine(hoje, time.min, tzinfo=dom.FUSO).astimezone(UTC)


def presentes_agora(db: Session, agora: datetime | None = None) -> list[RegistroAcesso]:
    """Última ENTRADA permitida de cada aluno hoje, ainda dentro do tempo previsto e sem saída registrada depois."""
    momento = agora or agora_utc()
    inicio = inicio_do_dia_utc(momento)
    regs = list(db.scalars(select(RegistroAcesso).where(RegistroAcesso.em >= inicio, RegistroAcesso.em <= momento,
                                                         RegistroAcesso.aluno_id.is_not(None)).order_by(RegistroAcesso.em)))
    ultimo: dict[int, RegistroAcesso] = {}
    for r in regs:
        if r.sentido == Sentido.saida:
            ultimo.pop(r.aluno_id, None)
        elif r.permitido:
            ultimo[r.aluno_id] = r
    return sorted((r for r in ultimo.values() if r.previsto_sair is None or r.previsto_sair > momento),
                  key=lambda r: r.em, reverse=True)


def contagens_do_dia(db: Session, agora: datetime | None = None) -> dict:
    momento = agora or agora_utc()
    inicio = inicio_do_dia_utc(momento)
    base = select(RegistroAcesso).where(RegistroAcesso.em >= inicio, RegistroAcesso.sentido == Sentido.entrada)
    entradas = db.scalar(select(func.count()).select_from(base.where(RegistroAcesso.permitido.is_(True)).subquery())) or 0
    negados = db.scalar(select(func.count()).select_from(base.where(RegistroAcesso.permitido.is_(False)).subquery())) or 0
    alunos = db.scalar(select(func.count(func.distinct(RegistroAcesso.aluno_id))).where(
        RegistroAcesso.em >= inicio, RegistroAcesso.permitido.is_(True), RegistroAcesso.sentido == Sentido.entrada)) or 0
    por_metodo = {str(getattr(m, "value", m)): n for m, n in db.execute(
        select(RegistroAcesso.metodo, func.count()).where(RegistroAcesso.em >= inicio, RegistroAcesso.permitido.is_(True),
                                                          RegistroAcesso.sentido == Sentido.entrada).group_by(RegistroAcesso.metodo)).all()}
    return {"entradas_hoje": entradas, "negados_hoje": negados, "alunos_hoje": alunos, "por_metodo": por_metodo}


# ------------------------------------------------------------------------------------------------------ LGPD (rotina)
def apagar_biometria_de_inativos(db: Session, agora: datetime | None = None) -> int:
    """Cumpre o termo: quem deixa de ser aluno (cadastro INATIVO) tem a biometria apagada. Devolve quantos alunos."""
    ids = list(db.scalars(select(DescritorFacial.aluno_id).join(Aluno, Aluno.id == DescritorFacial.aluno_id)
                          .where(Aluno.status == StatusAluno.INATIVO).distinct()))
    for aluno_id in ids:
        apagar_biometria(db, db.get(Aluno, aluno_id), por_nome="Rotina automática",
                         motivo="Aluno inativo (termo de consentimento)", agora=agora)
    return len(ids)
