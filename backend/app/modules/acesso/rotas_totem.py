"""Rotas com autenticação PRÓPRIA do controle de acesso (listadas em `permissoes.PUBLICAS_AUTENTICACAO_PROPRIA`).

- ``/api/totem/*``: o totem da recepção, autenticado pelo token do DISPOSITIVO (cabeçalho ``X-Dispositivo-Token``;
  o BFF do totem guarda o token em cookie httpOnly e o injeta). Token revogável, guardado só como SHA-256.
- ``/api/catraca-agente/*``: o agente local opcional (``deploy/agente-catraca``), mesmo esquema de token (tipo agente).
- ``/api/aluno-app/acesso/qr``: QR de entrada do app do aluno (sessão do ALUNO), válido por 90 s e de uso único.

O servidor NUNCA recebe foto: só o descritor numérico do momento, que é comparado e descartado (não é gravado).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit, ratelimit
from app.core.db import agora as agora_utc
from app.core.db import get_db
from app.core.models import Identidade, Usuario
from app.core.schemas import Mensagem
from app.domain import acesso as dom
from app.modules.acesso import schemas as sc
from app.modules.acesso import servico as srv
from app.modules.acesso.models import (
    Catraca,
    DescritorFacial,
    Dispositivo,
    MetodoAcesso,
    RegistroAcesso,
    TipoDispositivo,
)
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import Unidade

DB = Annotated[Session, Depends(get_db)]

LIM_TOTEM_POR_MIN = 120
LIM_DOCUMENTO_POR_MIN = 20
LIM_CADASTRO_POR_MIN = 10
LIM_FALHA_TOKEN = 20  # por 5 minutos e IP


def _agora() -> datetime:
    """Relógio (os testes congelam)."""
    return agora_utc()


def _dispositivo(tipo: TipoDispositivo):
    def dep(request: Request, db: DB, x_dispositivo_token: Annotated[str | None, Header(alias="X-Dispositivo-Token")] = None) -> Dispositivo:
        d = srv.autenticar_dispositivo(db, x_dispositivo_token, tipo.value, _agora())
        if d is None:
            ratelimit.verificar(request, "acesso-dispositivo-falha", LIM_FALHA_TOKEN, 300, db=db)
            raise HTTPException(401, "Dispositivo não pareado ou revogado. Peça para a recepção parear de novo.")
        ratelimit.verificar(request, f"acesso-{tipo.value}", LIM_TOTEM_POR_MIN, 60, chave=f"d{d.id}", db=db)
        return d

    return dep


Totem = Annotated[Dispositivo, Depends(_dispositivo(TipoDispositivo.totem))]
Agente = Annotated[Dispositivo, Depends(_dispositivo(TipoDispositivo.agente))]

router_publico = APIRouter()
totem = APIRouter(prefix="/totem", tags=["acesso (totem)"])
agente = APIRouter(prefix="/catraca-agente", tags=["acesso (agente local)"])
app_aluno = APIRouter(prefix="/aluno-app/acesso", tags=["acesso (app do aluno)"])


def _erro(e: srv.ErroAcesso) -> HTTPException:
    return HTTPException(e.status, e.mensagem)


def acionamento_out(a: srv.Acionamento | None) -> sc.AcionamentoOut | None:
    if a is None:
        return None
    plano = None
    if a.plano is not None:
        plano = sc.PlanoOut(driver=a.plano.driver, descricao=a.plano.descricao,
                            passos=[sc.PassoOut(metodo=p.metodo, url=p.url, corpo=p.corpo, extrair=p.extrair) for p in a.plano.passos])
    return sc.AcionamentoOut(catraca_id=a.catraca_id, catraca_nome=a.catraca_nome, modo=a.modo, status=a.status, mensagem=a.mensagem,
                             plano=plano, comando_id=a.comando_id)


def _resposta(db: Session, reg: RegistroAcesso, d: dom.Decisao, acion: srv.Acionamento | None) -> sc.CheckinOut:
    cfg = srv.obter_config(db)
    aula = None
    if d.aula is not None:
        aula = sc.AulaOut(servico=d.aula.servico, inicio=d.aula.inicio, fim=d.aula.fim, profissional=d.aula.profissional)
    return sc.CheckinOut(permitido=d.permitido, codigo=d.codigo, motivo=d.motivo, titulo=srv.titulo_da_decisao(cfg, d),
                         primeiro_nome=d.primeiro_nome or None, aniversario=d.aniversario and d.permitido, avisos=d.avisos, aula=aula,
                         registro_id=reg.id, presenca_registrada=reg.presenca_registrada, acionamento=acionamento_out(acion))


def _negado(db: Session, disp: Dispositivo, metodo: MetodoAcesso, codigo: str, motivo: str, *, aluno: Aluno | None = None,
            similaridade: float | None = None, registrar: bool = True) -> sc.CheckinOut:
    reg_id = None
    if registrar:
        reg = srv.novo_registro(db, aluno=aluno, permitido=False, codigo=codigo, motivo=motivo, metodo=metodo, agora=_agora(),
                                dispositivo=disp, similaridade=similaridade)
        reg_id = reg.id
    db.commit()
    return sc.CheckinOut(permitido=False, codigo=codigo, motivo=motivo, titulo="Acesso não liberado",
                         primeiro_nome=dom.primeiro_nome(aluno.nome) if aluno else None, registro_id=reg_id)


# ------------------------------------------------------------------------------------------------------ totem
@totem.get("/me", response_model=sc.TotemMeOut)
def totem_me(disp: Totem, db: DB):
    cfg = srv.obter_config(db)
    ident = db.scalar(select(Identidade).limit(1))
    un = db.get(Unidade, disp.unidade_id) if disp.unidade_id else None
    cat = db.get(Catraca, disp.catraca_id) if disp.catraca_id else None
    n = db.scalar(select(func.count(func.distinct(DescritorFacial.aluno_id)))) or 0
    db.commit()
    return sc.TotemMeOut(dispositivo=disp.nome, unidade=un.nome if un else None,
                         estudio=(getattr(ident, "nome_exibicao", None) or "Estúdio") if ident else "Estúdio",
                         cor=getattr(ident, "cor_destaque", None) if ident else None, exigir_prova_vida=cfg.exigir_prova_vida,
                         exigir_pin=cfg.exigir_pin, tem_catraca=bool(cat and cat.ativo), modo_catraca=str(getattr(cat.modo, "value", cat.modo)) if cat else None,
                         biometria_cadastrada=n)


@totem.post("/identificar/facial", response_model=sc.CheckinOut)
def identificar_facial(dados: sc.IdentificarFacialIn, disp: Totem, db: DB):
    cfg = srv.obter_config(db)
    pv = dados.prova_vida
    if cfg.exigir_prova_vida and not (pv and dom.prova_de_vida_ok(pv.piscou, pv.real, pv.live)):
        # não registra: o totem só chama com rosto estável; sem prova de vida pede para piscar
        return _negado(db, disp, MetodoAcesso.facial, dom.NEG_SEM_PROVA_VIDA, "Pisque devagar olhando para a câmera.", registrar=False)
    try:
        corr = srv.identificar_rosto(db, dados.descritor)
    except srv.ErroAcesso as e:
        raise _erro(e) from None
    if not corr.reconhecido:
        return _negado(db, disp, MetodoAcesso.facial, dom.NEG_NAO_RECONHECIDO, corr.motivo or "Não reconheci você.", similaridade=corr.similaridade)
    aluno = db.get(Aluno, corr.aluno_id)
    reg, dec, acion = srv.checkin(db, aluno, metodo=MetodoAcesso.facial, agora=_agora(), dispositivo=disp, similaridade=corr.similaridade)
    out = _resposta(db, reg, dec, acion)
    db.commit()
    return out


@totem.post("/identificar/documento", response_model=sc.CheckinOut)
def identificar_documento(dados: sc.IdentificarDocumentoIn, request: Request, disp: Totem, db: DB):
    ratelimit.verificar(request, "acesso-documento", LIM_DOCUMENTO_POR_MIN, 60, chave=f"d{disp.id}", db=db)
    aluno = srv.aluno_por_documento(db, dados.documento)
    metodo = MetodoAcesso.cpf if len(dom.so_digitos(dados.documento)) == 11 else MetodoAcesso.codigo
    if aluno is None:
        return _negado(db, disp, metodo, dom.NEG_CREDENCIAL, "CPF/código ou PIN incorretos.")
    try:
        srv.conferir_pin(db, aluno, dados.pin, _agora())
    except srv.ErroAcesso as e:
        db.commit()  # guarda a contagem de erros do PIN
        return _negado(db, disp, metodo, dom.NEG_CREDENCIAL, e.mensagem, aluno=aluno)
    reg, dec, acion = srv.checkin(db, aluno, metodo=metodo, agora=_agora(), dispositivo=disp)
    out = _resposta(db, reg, dec, acion)
    db.commit()
    return out


@totem.post("/identificar/qr", response_model=sc.CheckinOut)
def identificar_qr(dados: sc.IdentificarQrIn, disp: Totem, db: DB):
    try:
        aluno, nonce = srv.ler_qr(db, dados.qr, _agora())
    except srv.ErroAcesso as e:
        return _negado(db, disp, MetodoAcesso.qr, dom.NEG_CREDENCIAL, e.mensagem)
    reg, dec, acion = srv.checkin(db, aluno, metodo=MetodoAcesso.qr, agora=_agora(), dispositivo=disp, qr_nonce=nonce)
    out = _resposta(db, reg, dec, acion)
    db.commit()
    return out


@totem.post("/registros/{registro_id:int}/catraca", response_model=Mensagem)
def totem_resultado_catraca(registro_id: int, dados: sc.ResultadoCatracaIn, disp: Totem, db: DB):
    """O navegador do totem executou o plano na rede local e informa se a catraca liberou."""
    r = db.get(RegistroAcesso, registro_id)
    if r is None or r.dispositivo_id != disp.id:
        raise HTTPException(404, "Registro não encontrado.")
    r.catraca_status = "liberada" if dados.ok else "falhou"
    r.catraca_detalhe = (dados.detalhe or "")[:300]
    db.commit()
    return Mensagem(mensagem="Resultado registrado.")


@totem.post("/cadastro/iniciar", response_model=sc.CadastroTotemInicioOut)
def cadastro_iniciar(dados: sc.CadastroTotemInicioIn, request: Request, disp: Totem, db: DB):
    ratelimit.verificar(request, "acesso-cadastro-totem", LIM_CADASTRO_POR_MIN, 60, chave=f"d{disp.id}", db=db)
    try:
        aluno, _ = srv.conferir_codigo_totem(db, dados.documento, dados.codigo, _agora())
    except srv.ErroAcesso as e:
        raise _erro(e) from None
    cfg = srv.obter_config(db)
    db.commit()
    return sc.CadastroTotemInicioOut(primeiro_nome=dom.primeiro_nome(aluno.nome), termo=cfg.termo_biometria or srv.TERMO_PADRAO)


@totem.post("/cadastro/concluir", response_model=Mensagem)
def cadastro_concluir(dados: sc.CadastroTotemConcluirIn, request: Request, disp: Totem, db: DB):
    ratelimit.verificar(request, "acesso-cadastro-totem", LIM_CADASTRO_POR_MIN, 60, chave=f"d{disp.id}", db=db)
    agora = _agora()
    try:
        aluno, cred = srv.conferir_codigo_totem(db, dados.documento, dados.codigo, agora)
    except srv.ErroAcesso as e:
        raise _erro(e) from None
    cfg = srv.obter_config(db)
    pv = dados.prova_vida
    if cfg.exigir_prova_vida and not (pv and dom.prova_de_vida_ok(pv.piscou, pv.real, pv.live)):
        raise HTTPException(422, "Não detectei prova de vida. Pisque devagar olhando para a câmera e tente de novo.")
    usuario = db.get(Usuario, cred.codigo_cadastro_por_id) if cred.codigo_cadastro_por_id else None
    quem = f"{cred.codigo_cadastro_por_nome or 'Recepção'} (código no totem {disp.nome})"
    srv.registrar_consentimento(db, aluno, texto=cfg.termo_biometria or srv.TERMO_PADRAO, coletado_por=usuario, coletado_por_nome=quem,
                                canal="totem", ip=ratelimit.ip_do_cliente(request), agora=agora)
    try:
        novos = srv.adicionar_descritores(db, aluno, dados.descritores, origem="totem", criado_por_nome=quem)
    except srv.ErroAcesso as e:
        db.rollback()
        raise _erro(e) from None
    cred.codigo_cadastro_hash = None  # uso único
    cred.codigo_cadastro_expira = None
    audit.registrar(db, usuario=usuario, acao="cadastrar_biometria", entidade="aluno", entidade_id=aluno.id,
                    descricao=f"Consentimento aceito e {len(novos)} descritor(es) cadastrados no totem {disp.nome} para {aluno.nome}",
                    ip=ratelimit.ip_do_cliente(request))
    db.commit()
    return Mensagem(mensagem=f"Pronto, {dom.primeiro_nome(aluno.nome)}! Seu rosto foi cadastrado.")


# ------------------------------------------------------------------------------------------------------ agente
@agente.get("/comandos", response_model=list[sc.ComandoOut])
def agente_comandos(ag: Agente, db: DB):
    """Comandos pendentes (o agente chama a cada 1–2 s). Inclui o acesso à catraca (rede local) com a senha decifrada."""
    out = []
    for cmd, cat in srv.comandos_pendentes(db, ag, _agora()):
        dados = srv.dados_catraca(cat)
        out.append(sc.ComandoOut(id=cmd.id, acao=cmd.acao, sentido=cmd.sentido, expira_em=cmd.expira_em, catraca={
            "id": cat.id, "nome": cat.nome, "driver": str(getattr(cat.driver, "value", cat.driver)), "host": dados.host, "porta": dados.porta,
            "usar_https": dados.usar_https, "usuario": dados.usuario, "senha": dados.senha, "sentido_entrada": dados.sentido_entrada,
            "acao_liberacao": dados.acao_liberacao, "porta_rele": dados.porta_rele}))
    db.commit()
    return out


@agente.post("/comandos/{comando_id:int}/resultado", response_model=Mensagem)
def agente_resultado(comando_id: int, dados: sc.ResultadoComandoIn, ag: Agente, db: DB):
    try:
        srv.concluir_comando(db, ag, comando_id, dados.ok, dados.mensagem, _agora())
    except srv.ErroAcesso as e:
        raise _erro(e) from None
    db.commit()
    return Mensagem(mensagem="Resultado registrado.")


# ------------------------------------------------------------------------------------------------------ app do aluno
_bearer = HTTPBearer(auto_error=False)


def _aluno_do_app(db: DB, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> Aluno:
    from app.modules.app_aluno import servico as app_srv

    if cred is None:
        raise HTTPException(401, "Entre com seu CPF para continuar.")
    try:
        return app_srv.aluno_do_token(db, cred.credentials, app_srv.TIPO_ACCESS)
    except app_srv.ErroAluno as e:
        raise HTTPException(e.status, e.mensagem) from None


@app_aluno.get("/qr", response_model=sc.QrOut, dependencies=[Depends(ratelimit.limitar("aluno-app-qr", 60, 60))])
def qr_do_aluno(aluno: Annotated[Aluno, Depends(_aluno_do_app)]):
    """QR de entrada: o app mostra e renova a cada minuto. Vale 90 s e uma única entrada."""
    valor, expira = srv.emitir_qr(aluno.id, _agora())
    return sc.QrOut(qr=valor, expira_em=expira)


router_publico.include_router(totem)
router_publico.include_router(agente)
router_publico.include_router(app_aluno)
