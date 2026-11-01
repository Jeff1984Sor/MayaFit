"""Regras de aplicação do CRM de vendas (a rota só orquestra; regras puras em `crm.regras`).

INTERFACE ESTÁVEL PARA OUTROS MÓDULOS (site do estúdio, integrações):

    criar_lead(db, *, nome, telefone, email, origem="site", interesse=None, mensagem=None,
               quer_aula_experimental=False) -> CrmLead

Recebe um contato de fora (formulário do site etc.). Se já existe um lead ABERTO com o mesmo telefone ou e-mail,
não duplica: acrescenta uma interação ao lead existente (e completa telefone/e-mail que faltavam). Cria o funil
padrão se o estúdio ainda não tiver um, agenda a tarefa de primeiro contato, audita como "Robô" e faz commit.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import agora
from app.core.deps import Contexto
from app.core.models import Identidade, Usuario
from app.domain.telefone import normalizar_telefone_br
from app.modules.alunos import schemas as alunos_sc
from app.modules.alunos import servico as alunos_servico
from app.modules.alunos.models import Aluno, AlunoTelefone
from app.modules.cadastros.models import Profissional, Unidade
from app.modules.crm import regras
from app.modules.crm import schemas as sc
from app.modules.crm.models import (
    CrmEtapa,
    CrmInteracao,
    CrmLead,
    CrmMotivoPerda,
    CrmMovimento,
    CrmTarefa,
    MarcoEtapa,
    OrigemLead,
    SituacaoLead,
    StatusAulaExperimental,
    TipoEtapa,
    TipoInteracao,
)

ETAPAS_PADRAO: list[dict] = [
    {"nome": "Novo contato", "ordem": 1, "cor": "#7C8FFF", "tipo": TipoEtapa.ABERTA, "marco": None, "dias_alerta": 1},
    {"nome": "Aula experimental agendada", "ordem": 2, "cor": "#F5A623", "tipo": TipoEtapa.ABERTA, "marco": MarcoEtapa.AULA_AGENDADA, "dias_alerta": 7},
    {"nome": "Fez aula experimental", "ordem": 3, "cor": "#1E2D6B", "tipo": TipoEtapa.ABERTA, "marco": MarcoEtapa.AULA_REALIZADA, "dias_alerta": 2},
    {"nome": "Proposta", "ordem": 4, "cor": "#8B5CF6", "tipo": TipoEtapa.ABERTA, "marco": MarcoEtapa.PROPOSTA, "dias_alerta": 3},
    {"nome": "Matriculado", "ordem": 1000, "cor": "#1A8F5E", "tipo": TipoEtapa.GANHO, "marco": None, "dias_alerta": 0},
    {"nome": "Perdido", "ordem": 1001, "cor": "#C94343", "tipo": TipoEtapa.PERDIDO, "marco": None, "dias_alerta": 0},
]
MOTIVOS_PADRAO = ["Preço", "Horário não atende", "Distância / localização", "Escolheu outro estúdio",
                  "Sem resposta", "Problema de saúde", "Só queria a aula experimental", "Outro"]
ORDEM_GANHO, ORDEM_PERDIDO = 1000, 1001


def erro(codigo: int, mensagem: str) -> HTTPException:
    return HTTPException(codigo, mensagem)


# ------------------------------------------------------------------------------------------------ funil padrão
def garantir_padrao(db: Session) -> None:
    """Cria as etapas e os motivos padrão quando o estúdio ainda não tem nenhum (idempotente; só flush)."""
    if db.scalar(select(func.count()).select_from(CrmEtapa)) == 0:
        db.add_all([CrmEtapa(**e) for e in ETAPAS_PADRAO])
    if db.scalar(select(func.count()).select_from(CrmMotivoPerda)) == 0:
        db.add_all([CrmMotivoPerda(nome=n, ordem=i) for i, n in enumerate(MOTIVOS_PADRAO, start=1)])
    db.flush()


def etapas(db: Session) -> list[CrmEtapa]:
    garantir_padrao(db)
    return list(db.scalars(select(CrmEtapa).order_by(CrmEtapa.ordem, CrmEtapa.id)))


def _etapa_tipo(db: Session, tipo: TipoEtapa) -> CrmEtapa:
    return next(e for e in etapas(db) if e.tipo == tipo)


def _primeira_aberta(db: Session) -> CrmEtapa:
    return next(e for e in etapas(db) if e.tipo == TipoEtapa.ABERTA)


def _etapa_marco(db: Session, marco: MarcoEtapa) -> CrmEtapa | None:
    return next((e for e in etapas(db) if e.marco == marco and e.tipo == TipoEtapa.ABERTA), None)


def _obter_etapa(db: Session, etapa_id: int) -> CrmEtapa:
    e = db.get(CrmEtapa, etapa_id)
    if not e:
        raise erro(404, "Etapa não encontrada.")
    return e


def nome_estudio(db: Session) -> str:
    ident = db.get(Identidade, 1)
    return ident.nome_exibicao if ident and ident.nome_exibicao else "estúdio"


# ------------------------------------------------------------------------------------------------ peças comuns
def _registrar_movimento(db: Session, lead: CrmLead, origem: CrmEtapa | None, destino: CrmEtapa, usuario: Usuario | None) -> None:
    db.add(CrmMovimento(lead_id=lead.id, etapa_origem_id=origem.id if origem else None, etapa_destino_id=destino.id,
                        usuario_id=usuario.id if usuario else None))


def _interacao_sistema(db: Session, lead: CrmLead, texto: str, usuario: Usuario | None = None) -> None:
    db.add(CrmInteracao(lead_id=lead.id, tipo=TipoInteracao.SISTEMA, descricao=texto, usuario_id=usuario.id if usuario else None))


def _tarefa_automatica(db: Session, lead: CrmLead, titulo: str, vence_em: datetime, descricao: str | None = None) -> CrmTarefa:
    t = CrmTarefa(lead_id=lead.id, titulo=titulo[:150], descricao=descricao, vence_em=vence_em,
                  responsavel_id=lead.responsavel_id, automatica=True)
    db.add(t)
    return t


def _validar_usuario(db: Session, usuario_id: int | None) -> None:
    if usuario_id is None:
        return
    u = db.get(Usuario, usuario_id)
    if not u or not u.ativo:
        raise erro(422, "Responsável não encontrado ou inativo.")


def _buscar_aberto_duplicado(db: Session, telefone: str | None, email: str | None, ignorar_id: int | None = None) -> CrmLead | None:
    condicoes = []
    if telefone:
        condicoes.append(CrmLead.telefone == telefone)
    if email:
        condicoes.append(func.lower(CrmLead.email) == email)
    if not condicoes:
        return None
    q = select(CrmLead).where(CrmLead.situacao == SituacaoLead.ABERTO, or_(*condicoes)).order_by(CrmLead.id)
    if ignorar_id:
        q = q.where(CrmLead.id != ignorar_id)
    return db.scalars(q).first()


def _novo_lead(db: Session, usuario: Usuario | None, *, nome: str, telefone: str | None, email: str | None, origem: OrigemLead,
               etapa: CrmEtapa | None = None, **campos) -> CrmLead:
    etapa = etapa or _primeira_aberta(db)
    if etapa.tipo != TipoEtapa.ABERTA:
        raise erro(422, "Um lead novo entra numa etapa aberta do funil.")
    lead = CrmLead(nome=nome.strip()[:150], telefone=telefone, email=email, origem=origem, etapa_id=etapa.id,
                   etapa_desde=agora(), situacao=SituacaoLead.ABERTO, tags=[], **campos)
    db.add(lead)
    db.flush()
    _registrar_movimento(db, lead, None, etapa, usuario)
    return lead


# ------------------------------------------------------------------------------------------------ interface estável
def criar_lead(
    db: Session,
    *,
    nome: str,
    telefone: str | None,
    email: str | None,
    origem: str = "site",
    interesse: str | None = None,
    mensagem: str | None = None,
    quer_aula_experimental: bool = False,
) -> CrmLead:
    """Contato vindo de fora (site do estúdio). Ver docstring do módulo. Faz commit e devolve o lead (novo ou existente)."""
    nome = " ".join((nome or "").split())
    if len(nome) < 2:
        raise ValueError("Informe o nome do contato.")
    tel = regras.normalizar_telefone(telefone)
    mail = regras.normalizar_email(email)
    if not tel and not mail:
        raise ValueError("Informe um telefone ou um e-mail para contato.")
    org = regras.normalizar_origem(origem)
    interesse = (interesse or "").strip()[:150] or None
    mensagem = (mensagem or "").strip()[:4000] or None
    garantir_padrao(db)
    rotulo = regras.ROTULO_ORIGEM[org]
    texto = f"Novo contato pelo canal {rotulo}." + (f" Interesse: {interesse}." if interesse else "") + \
        (" Quer agendar uma aula experimental." if quer_aula_experimental else "") + (f"\nMensagem: {mensagem}" if mensagem else "")
    agora_ = agora()

    lead = _buscar_aberto_duplicado(db, tel, mail)
    if lead:
        lead.telefone = lead.telefone or tel
        lead.email = lead.email or mail
        lead.interesse = lead.interesse or interesse
        _interacao_sistema(db, lead, "Entrou em contato de novo. " + texto)
        acao, descricao = "crm.lead.recontato", f"Lead {lead.nome} entrou em contato de novo ({rotulo})"
    else:
        lead = _novo_lead(db, None, nome=nome, telefone=tel, email=mail, origem=org, interesse=interesse)
        _interacao_sistema(db, lead, texto)
        acao, descricao = "crm.lead.criar", f"Lead {lead.nome} recebido ({rotulo})"
    if quer_aula_experimental and "Quer aula experimental" not in (lead.tags or []):
        lead.tags = regras.normalizar_tags([*(lead.tags or []), "Quer aula experimental"])
    pendente = db.scalar(select(func.count()).select_from(CrmTarefa).where(CrmTarefa.lead_id == lead.id, CrmTarefa.concluida.is_(False)))
    if not pendente:
        titulo = f"Agendar aula experimental com {regras.primeiro_nome(lead.nome)}" if quer_aula_experimental \
            else f"Fazer o primeiro contato com {regras.primeiro_nome(lead.nome)}"
        _tarefa_automatica(db, lead, titulo, regras.horario_comercial(agora_, minutos=15), "Contato recebido pelo " + rotulo)
    lead.ultima_interacao_em = agora_
    db.flush()
    audit.registrar(db, usuario=None, acao=acao, entidade="crm_lead", entidade_id=lead.id, descricao=descricao)
    db.commit()
    return lead


# ------------------------------------------------------------------------------------------------ montagem das saídas
def _usuarios(db: Session, ids) -> dict[int, Usuario]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u for u in db.scalars(select(Usuario).where(Usuario.id.in_(ids)))}


def _mini(u: Usuario | None) -> sc.UsuarioMini | None:
    return sc.UsuarioMini(id=u.id, nome=u.nome) if u else None


def _tarefas_por_lead(db: Session, lead_ids: list[int], agora_: datetime) -> dict[int, tuple[int, bool]]:
    if not lead_ids:
        return {}
    out: dict[int, tuple[int, bool]] = {}
    linhas = db.execute(
        select(CrmTarefa.lead_id, func.count(), func.min(CrmTarefa.vence_em))
        .where(CrmTarefa.lead_id.in_(lead_ids), CrmTarefa.concluida.is_(False))
        .group_by(CrmTarefa.lead_id)
    ).all()
    for lead_id, qtd, primeira in linhas:
        if primeira is not None and primeira.tzinfo is None:
            primeira = primeira.replace(tzinfo=UTC)
        out[lead_id] = (qtd, bool(primeira and primeira < agora_))
    return out


def _cartoes(db: Session, leads: list[CrmLead]) -> list[sc.LeadCartao]:
    agora_ = agora()
    mapa_etapas = {e.id: e for e in etapas(db)}
    usuarios = _usuarios(db, [lead.responsavel_id for lead in leads])
    tarefas = _tarefas_por_lead(db, [lead.id for lead in leads], agora_)
    out = []
    for lead in leads:
        etapa = mapa_etapas.get(lead.etapa_id)
        dias_etapa = regras.dias_entre(lead.etapa_desde, agora_) or 0
        qtd, atrasada = tarefas.get(lead.id, (0, False))
        out.append(sc.LeadCartao(
            id=lead.id, nome=lead.nome, telefone=lead.telefone,
            telefone_formatado=alunos_servico.formatar_telefone(lead.telefone) if lead.telefone else None,
            email=lead.email, origem=lead.origem, interesse=lead.interesse,
            responsavel=_mini(usuarios.get(lead.responsavel_id)), valor_estimado=lead.valor_estimado, tags=list(lead.tags or []),
            etapa_id=lead.etapa_id, situacao=lead.situacao, dias_na_etapa=dias_etapa,
            parado=regras.esta_parado(dias_etapa, etapa.dias_alerta if etapa else 0, lead.situacao),
            temperatura=regras.temperatura(
                situacao=lead.situacao, dias_sem_contato=regras.dias_entre(lead.ultima_interacao_em, agora_),
                dias_na_etapa=regras.dias_entre(lead.criado_em, agora_) or 0, aula_status=lead.aula_experimental_status,
                aula_em=lead.aula_experimental_em, agora=agora_),
            aula_experimental_em=lead.aula_experimental_em, aula_experimental_status=lead.aula_experimental_status,
            tarefas_pendentes=qtd, tarefa_atrasada=atrasada, whatsapp_url=regras.link_whatsapp(lead.telefone),
            criado_em=lead.criado_em, ultima_interacao_em=lead.ultima_interacao_em, aluno_id=lead.aluno_id,
        ))
    return out


def tarefa_out(t: CrmTarefa, usuarios: dict[int, Usuario], leads: dict[int, CrmLead], agora_: datetime) -> sc.TarefaOut:
    lead = leads.get(t.lead_id) if t.lead_id else None
    return sc.TarefaOut(
        id=t.id, titulo=t.titulo, descricao=t.descricao, vence_em=t.vence_em, responsavel=_mini(usuarios.get(t.responsavel_id)),
        concluida=t.concluida, concluida_em=t.concluida_em, situacao=regras.classificar_tarefa(t.vence_em, t.concluida, agora_),
        automatica=t.automatica, lead_id=t.lead_id, lead_nome=lead.nome if lead else None,
        lead_telefone=alunos_servico.formatar_telefone(lead.telefone) if lead and lead.telefone else None,
        whatsapp_url=regras.link_whatsapp(lead.telefone) if lead else None,
    )


def _tarefas_out(db: Session, tarefas: list[CrmTarefa]) -> list[sc.TarefaOut]:
    agora_ = agora()
    usuarios = _usuarios(db, [t.responsavel_id for t in tarefas])
    lead_ids = {t.lead_id for t in tarefas if t.lead_id}
    leads = {lead.id: lead for lead in db.scalars(select(CrmLead).where(CrmLead.id.in_(lead_ids)))} if lead_ids else {}
    return [tarefa_out(t, usuarios, leads, agora_) for t in tarefas]


def etapa_out(e: CrmEtapa, leads: int = 0) -> sc.EtapaOut:
    return sc.EtapaOut(id=e.id, nome=e.nome, ordem=e.ordem, cor=e.cor, tipo=e.tipo, marco=e.marco, dias_alerta=e.dias_alerta, leads=leads)


def ficha(ctx: Contexto, lead: CrmLead) -> sc.LeadFicha:
    db = ctx.db
    agora_ = agora()
    cartao = _cartoes(db, [lead])[0]
    mapa_etapas = {e.id: e for e in etapas(db)}
    etapa = mapa_etapas[lead.etapa_id]
    interacoes = list(db.scalars(select(CrmInteracao).where(CrmInteracao.lead_id == lead.id)
                                 .order_by(CrmInteracao.ocorrido_em.desc(), CrmInteracao.id.desc())))
    tarefas = list(db.scalars(select(CrmTarefa).where(CrmTarefa.lead_id == lead.id)
                              .order_by(CrmTarefa.concluida, CrmTarefa.vence_em)))
    movimentos = list(db.scalars(select(CrmMovimento).where(CrmMovimento.lead_id == lead.id).order_by(CrmMovimento.em, CrmMovimento.id)))
    usuarios = _usuarios(db, [i.usuario_id for i in interacoes] + [m.usuario_id for m in movimentos])
    motivo = db.get(CrmMotivoPerda, lead.motivo_perda_id) if lead.motivo_perda_id else None
    prof = db.get(Profissional, lead.aula_experimental_profissional_id) if lead.aula_experimental_profissional_id else None
    aluno = db.get(Aluno, lead.aluno_id) if lead.aluno_id else None
    abertas = [e for e in mapa_etapas.values() if e.tipo == TipoEtapa.ABERTA]
    contatos = [i for i in interacoes if i.tipo != TipoInteracao.SISTEMA]
    estudio = nome_estudio(db)
    msgs = regras.mensagens_whatsapp(nome=lead.nome, estudio=estudio, interesse=lead.interesse, marco=etapa.marco,
                                     situacao=lead.situacao, aula_status=lead.aula_experimental_status, aula_em=lead.aula_experimental_em)
    return sc.LeadFicha(
        **cartao.model_dump(),
        indicado_por=lead.indicado_por, observacoes=lead.observacoes, etapa_nome=etapa.nome,
        motivo_perda_id=lead.motivo_perda_id, motivo_perda=motivo.nome if motivo else None,
        motivo_perda_detalhe=lead.motivo_perda_detalhe, perdido_em=lead.perdido_em, ganho_em=lead.ganho_em,
        aula_experimental_profissional_id=lead.aula_experimental_profissional_id,
        aula_experimental_profissional=prof.nome if prof else None,
        aula_experimental_unidade_id=lead.aula_experimental_unidade_id, aula_experimental_obs=lead.aula_experimental_obs,
        sugestao=regras.sugestao_proxima_acao(
            situacao=lead.situacao, marco=etapa.marco, primeira_etapa=bool(abertas) and min(abertas, key=lambda e: e.ordem).id == etapa.id,
            tem_interacao=bool(contatos), aula_status=lead.aula_experimental_status, aula_em=lead.aula_experimental_em,
            dias_sem_contato=regras.dias_entre(contatos[0].ocorrido_em if contatos else None, agora_),
            tem_telefone=bool(lead.telefone), agora=agora_),
        mensagens=[sc.MensagemPronta(titulo=m["titulo"], texto=m["texto"], url=regras.link_whatsapp(lead.telefone, m["texto"])) for m in msgs],
        interacoes=[sc.InteracaoOut(id=i.id, tipo=i.tipo, descricao=i.descricao, usuario=_mini(usuarios.get(i.usuario_id)),
                                    ocorrido_em=i.ocorrido_em) for i in interacoes],
        tarefas=_tarefas_out(db, tarefas),
        movimentos=[sc.MovimentoOut(
            de=mapa_etapas[m.etapa_origem_id].nome if m.etapa_origem_id in mapa_etapas else None,
            para=mapa_etapas[m.etapa_destino_id].nome if m.etapa_destino_id in mapa_etapas else None,
            usuario=usuarios[m.usuario_id].nome if m.usuario_id in usuarios else None, em=m.em) for m in movimentos],
        aluno_nome=aluno.nome if aluno else None,
    )


# ------------------------------------------------------------------------------------------------ leads (CRUD)
def obter_lead(ctx: Contexto, lead_id: int) -> CrmLead:
    lead = ctx.db.get(CrmLead, lead_id)
    if not lead:
        raise erro(404, "Lead não encontrado.")
    return lead


def criar_lead_equipe(ctx: Contexto, dados: sc.LeadIn) -> CrmLead:
    db = ctx.db
    garantir_padrao(db)
    if not dados.nome:
        raise erro(422, "Informe o nome do lead.")
    tel = regras.normalizar_telefone(dados.telefone)
    mail = regras.normalizar_email(dados.email)
    dup = _buscar_aberto_duplicado(db, tel, mail)
    if dup:
        raise erro(409, f"Já existe um lead aberto com este telefone ou e-mail: {dup.nome} (#{dup.id}).")
    _validar_usuario(db, dados.responsavel_id)
    etapa = _obter_etapa(db, dados.etapa_id) if dados.etapa_id else None
    lead = _novo_lead(
        db, ctx.usuario, nome=dados.nome, telefone=tel, email=mail, origem=dados.origem or OrigemLead.OUTROS, etapa=etapa,
        indicado_por=dados.indicado_por, interesse=dados.interesse, responsavel_id=dados.responsavel_id if "responsavel_id" in dados.model_fields_set else ctx.usuario.id,
        valor_estimado=dados.valor_estimado, observacoes=dados.observacoes,
    )
    lead.tags = regras.normalizar_tags(dados.tags)
    _interacao_sistema(db, lead, f"Lead cadastrado por {ctx.usuario.nome}.", ctx.usuario)
    db.flush()
    ctx.auditar("crm.lead.criar", "crm_lead", lead.id, descricao=f"Lead {lead.nome} cadastrado", depois=audit.snapshot(lead))
    db.commit()
    return lead


_CAMPOS_EDITAVEIS = ("nome", "origem", "indicado_por", "interesse", "responsavel_id", "valor_estimado", "observacoes")


def atualizar_lead(ctx: Contexto, lead: CrmLead, dados: sc.LeadIn) -> CrmLead:
    db = ctx.db
    enviados = dados.model_fields_set
    antes = audit.snapshot(lead)
    if "nome" in enviados and not dados.nome:
        raise erro(422, "Informe o nome do lead.")
    if "origem" in enviados and dados.origem is None:
        enviados = enviados - {"origem"}
    if "responsavel_id" in enviados:
        _validar_usuario(db, dados.responsavel_id)
    for campo in _CAMPOS_EDITAVEIS:
        if campo in enviados:
            setattr(lead, campo, getattr(dados, campo))
    if "telefone" in enviados or "email" in enviados:
        tel = regras.normalizar_telefone(dados.telefone) if "telefone" in enviados else lead.telefone
        mail = regras.normalizar_email(dados.email) if "email" in enviados else lead.email
        if lead.situacao == SituacaoLead.ABERTO:
            dup = _buscar_aberto_duplicado(db, tel, mail, ignorar_id=lead.id)
            if dup:
                raise erro(409, f"Já existe outro lead aberto com este telefone ou e-mail: {dup.nome} (#{dup.id}).")
        lead.telefone, lead.email = tel, mail
    if "tags" in enviados:
        lead.tags = regras.normalizar_tags(dados.tags)
    if "etapa_id" in enviados and dados.etapa_id and dados.etapa_id != lead.etapa_id:
        mover(ctx, lead, sc.MoverIn(etapa_id=dados.etapa_id), commit=False)
    db.flush()
    ant, dep = audit.diff(antes, audit.snapshot(lead))
    if ant or dep:
        ctx.auditar("crm.lead.alterar", "crm_lead", lead.id, descricao=f"Lead {lead.nome} alterado", antes=ant, depois=dep)
    db.commit()
    return lead


def excluir_lead(ctx: Contexto, lead: CrmLead) -> None:
    ctx.auditar("crm.lead.excluir", "crm_lead", lead.id, descricao=f"Lead {lead.nome} excluído", antes=audit.snapshot(lead))
    ctx.db.delete(lead)
    ctx.db.commit()


def _concluir_pendentes(db: Session, lead: CrmLead) -> int:
    pendentes = list(db.scalars(select(CrmTarefa).where(CrmTarefa.lead_id == lead.id, CrmTarefa.concluida.is_(False))))
    for t in pendentes:
        t.concluida, t.concluida_em = True, agora()
    return len(pendentes)


def mover(ctx: Contexto, lead: CrmLead, dados: sc.MoverIn, *, commit: bool = True) -> CrmLead:
    """Muda a etapa. Perdido exige motivo; Matriculado marca o ganho. Encerrar o lead conclui as tarefas pendentes."""
    db = ctx.db
    destino = _obter_etapa(db, dados.etapa_id)
    origem = db.get(CrmEtapa, lead.etapa_id)
    if destino.id == lead.etapa_id:
        return lead
    antes = {"etapa": origem.nome if origem else None, "situacao": lead.situacao.value}
    agora_ = agora()
    if destino.tipo == TipoEtapa.PERDIDO:
        motivo = db.get(CrmMotivoPerda, dados.motivo_perda_id) if dados.motivo_perda_id else None
        if not motivo or not motivo.ativo:
            raise erro(422, "Escolha o motivo da perda.")
        lead.situacao, lead.perdido_em, lead.ganho_em = SituacaoLead.PERDIDO, agora_, None
        lead.motivo_perda_id = motivo.id
        lead.motivo_perda_detalhe = (dados.motivo_perda_detalhe or "").strip() or None
        texto = f"Marcado como perdido: {motivo.nome}" + (f" ({lead.motivo_perda_detalhe})" if lead.motivo_perda_detalhe else "") + "."
        _concluir_pendentes(db, lead)
    elif destino.tipo == TipoEtapa.GANHO:
        lead.situacao, lead.ganho_em, lead.perdido_em = SituacaoLead.GANHO, agora_, None
        lead.motivo_perda_id = lead.motivo_perda_detalhe = None
        texto = "Matriculado!"
        _concluir_pendentes(db, lead)
    else:
        if lead.situacao != SituacaoLead.ABERTO:
            dup = _buscar_aberto_duplicado(db, lead.telefone, lead.email.lower() if lead.email else None, ignorar_id=lead.id)
            if dup:
                raise erro(409, f"Não dá para reabrir: já existe um lead aberto com este contato ({dup.nome}, #{dup.id}).")
        lead.situacao, lead.perdido_em, lead.ganho_em = SituacaoLead.ABERTO, None, None
        lead.motivo_perda_id = lead.motivo_perda_detalhe = None
        texto = f"Movido de \"{origem.nome if origem else '—'}\" para \"{destino.nome}\"."
    lead.etapa_id, lead.etapa_desde = destino.id, agora_
    _registrar_movimento(db, lead, origem, destino, ctx.usuario)
    _interacao_sistema(db, lead, texto, ctx.usuario)
    db.flush()
    ctx.auditar("crm.lead.mover", "crm_lead", lead.id, descricao=f"{lead.nome}: {antes['etapa']} -> {destino.nome}",
                antes=antes, depois={"etapa": destino.nome, "situacao": lead.situacao.value})
    if commit:
        db.commit()
    return lead


def reabrir(ctx: Contexto, lead: CrmLead) -> CrmLead:
    if lead.situacao == SituacaoLead.ABERTO:
        return lead
    db = ctx.db
    # volta para a última etapa aberta em que esteve (senão, a primeira)
    abertas = {e.id for e in etapas(db) if e.tipo == TipoEtapa.ABERTA}
    ultima = db.scalar(select(CrmMovimento.etapa_origem_id).where(
        CrmMovimento.lead_id == lead.id, CrmMovimento.etapa_origem_id.in_(abertas)).order_by(CrmMovimento.em.desc(), CrmMovimento.id.desc()))
    return mover(ctx, lead, sc.MoverIn(etapa_id=ultima or _primeira_aberta(db).id))


# ------------------------------------------------------------------------------------------------ funil (Kanban) e lista
def _filtros(q: str | None, responsavel_id: int | None, origem: OrigemLead | None, tag: str | None = None):
    conds = []
    if q and q.strip():
        termo = q.strip()
        digitos = "".join(c for c in termo if c.isdigit())
        ors = [CrmLead.nome.ilike(f"%{termo}%"), CrmLead.email.ilike(f"%{termo}%"), CrmLead.interesse.ilike(f"%{termo}%")]
        if len(digitos) >= 4:
            ors.append(CrmLead.telefone.like(f"%{digitos}%"))
        conds.append(or_(*ors))
    if responsavel_id:
        conds.append(CrmLead.responsavel_id == responsavel_id)
    if origem:
        conds.append(CrmLead.origem == origem)
    return conds


def funil(ctx: Contexto, *, q: str | None = None, responsavel_id: int | None = None, origem: OrigemLead | None = None,
          dias_encerrados: int = 30) -> sc.Funil:
    db = ctx.db
    lista_etapas = etapas(db)
    limite = agora() - timedelta(days=dias_encerrados)
    conds = _filtros(q, responsavel_id, origem)
    leads = list(db.scalars(select(CrmLead).where(*conds, or_(
        CrmLead.situacao == SituacaoLead.ABERTO,
        (CrmLead.situacao == SituacaoLead.GANHO) & (CrmLead.ganho_em >= limite),
        (CrmLead.situacao == SituacaoLead.PERDIDO) & (CrmLead.perdido_em >= limite),
    )).order_by(CrmLead.etapa_desde.desc(), CrmLead.id.desc())))
    cartoes = _cartoes(db, leads)
    por_etapa: dict[int, list[sc.LeadCartao]] = defaultdict(list)
    for c in cartoes:
        por_etapa[c.etapa_id].append(c)
    colunas = []
    for e in lista_etapas:
        itens = por_etapa.get(e.id, [])
        colunas.append(sc.ColunaFunil(etapa=etapa_out(e, len(itens)), leads=itens, total=len(itens),
                                      valor_total=regras.somar(i.valor_estimado for i in itens)))
    db.commit()  # garantir_padrao pode ter criado o funil
    return sc.Funil(colunas=colunas)


def listar(ctx: Contexto, *, q: str | None, situacao: str, etapa_id: int | None, origem: OrigemLead | None,
           responsavel_id: int | None, tag: str | None, ordem: str, pagina: int, por_pagina: int) -> sc.ListaLeads:
    db = ctx.db
    garantir_padrao(db)
    conds = _filtros(q, responsavel_id, origem)
    if etapa_id:
        conds.append(CrmLead.etapa_id == etapa_id)
    contagens = {"abertos": 0, "ganhos": 0, "perdidos": 0, "todos": 0}
    for sit, qtd in db.execute(select(CrmLead.situacao, func.count()).where(*conds).group_by(CrmLead.situacao)).all():
        chave = {SituacaoLead.ABERTO: "abertos", SituacaoLead.GANHO: "ganhos", SituacaoLead.PERDIDO: "perdidos"}[sit]
        contagens[chave] = qtd
        contagens["todos"] += qtd
    mapa = {"abertos": SituacaoLead.ABERTO, "ganhos": SituacaoLead.GANHO, "perdidos": SituacaoLead.PERDIDO}
    if situacao in mapa:
        conds.append(CrmLead.situacao == mapa[situacao])
    consulta = select(CrmLead).where(*conds)
    ordens = {
        "recentes": (CrmLead.criado_em.desc(), CrmLead.id.desc()), "antigos": (CrmLead.criado_em, CrmLead.id),
        "nome": (CrmLead.nome, CrmLead.id), "valor": (CrmLead.valor_estimado.desc().nullslast(), CrmLead.id),
        "contato": (CrmLead.ultima_interacao_em.asc().nullsfirst(), CrmLead.id),
    }
    consulta = consulta.order_by(*ordens.get(ordem, ordens["recentes"]))
    if tag:
        # tags ficam em JSON: filtro em Python (volume de leads de um estúdio é pequeno)
        todos = [lead for lead in db.scalars(consulta) if tag.lower() in {t.lower() for t in (lead.tags or [])}]
        total, pagina_leads = len(todos), todos[(pagina - 1) * por_pagina: pagina * por_pagina]
    else:
        total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        pagina_leads = list(db.scalars(consulta.offset((pagina - 1) * por_pagina).limit(por_pagina)))
    db.commit()
    return sc.ListaLeads(itens=_cartoes(db, pagina_leads), total=total, pagina=pagina, por_pagina=por_pagina, contagens=contagens)


# ------------------------------------------------------------------------------------------------ interações
def registrar_interacao(ctx: Contexto, lead: CrmLead, dados: sc.InteracaoIn) -> CrmInteracao:
    quando = dados.ocorrido_em or agora()
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=UTC)
    if quando > agora() + timedelta(minutes=5):
        raise erro(422, "A interação não pode ser no futuro. Para algo a fazer, crie uma tarefa.")
    i = CrmInteracao(lead_id=lead.id, tipo=dados.tipo, descricao=dados.descricao.strip(), usuario_id=ctx.usuario.id, ocorrido_em=quando)
    ctx.db.add(i)
    if not lead.ultima_interacao_em or quando > lead.ultima_interacao_em:
        lead.ultima_interacao_em = quando
    ctx.db.flush()
    ctx.auditar("crm.interacao.criar", "crm_lead", lead.id, descricao=f"{dados.tipo.value} registrada em {lead.nome}")
    ctx.db.commit()
    return i


def excluir_interacao(ctx: Contexto, lead: CrmLead, interacao_id: int) -> None:
    i = ctx.db.get(CrmInteracao, interacao_id)
    if not i or i.lead_id != lead.id:
        raise erro(404, "Interação não encontrada.")
    if i.tipo == TipoInteracao.SISTEMA:
        raise erro(409, "Registros automáticos do histórico não podem ser excluídos.")
    ctx.auditar("crm.interacao.excluir", "crm_lead", lead.id, descricao=f"Interação excluída de {lead.nome}", antes=audit.snapshot(i))
    ctx.db.delete(i)
    ctx.db.commit()


# ------------------------------------------------------------------------------------------------ aula experimental
def _avancar_ate(ctx: Contexto, lead: CrmLead, marco: MarcoEtapa) -> None:
    """Move o lead para a etapa do marco se ele ainda estiver numa etapa aberta anterior."""
    alvo = _etapa_marco(ctx.db, marco)
    atual = ctx.db.get(CrmEtapa, lead.etapa_id)
    if alvo and atual and lead.situacao == SituacaoLead.ABERTO and atual.ordem < alvo.ordem:
        mover(ctx, lead, sc.MoverIn(etapa_id=alvo.id), commit=False)


def agendar_aula_experimental(ctx: Contexto, lead: CrmLead, dados: sc.AulaExperimentalIn) -> CrmLead:
    db = ctx.db
    if lead.situacao != SituacaoLead.ABERTO:
        raise erro(409, "Reabra o lead para agendar uma aula experimental.")
    quando = dados.data_hora if dados.data_hora.tzinfo else dados.data_hora.replace(tzinfo=regras.FUSO)
    if quando < agora() - timedelta(hours=12):
        raise erro(422, "Escolha uma data e hora a partir de hoje.")
    if dados.profissional_id and not db.get(Profissional, dados.profissional_id):
        raise erro(422, "Profissional não encontrado.")
    if dados.unidade_id and not db.get(Unidade, dados.unidade_id):
        raise erro(422, "Unidade não encontrada.")
    remarcando = lead.aula_experimental_status == StatusAulaExperimental.AGENDADA
    lead.aula_experimental_em = quando
    lead.aula_experimental_status = StatusAulaExperimental.AGENDADA
    lead.aula_experimental_profissional_id = dados.profissional_id
    lead.aula_experimental_unidade_id = dados.unidade_id
    lead.aula_experimental_obs = (dados.observacao or "").strip() or None
    # lembretes automáticos antigos (de confirmação/agendamento) saem; entra o novo
    for t in db.scalars(select(CrmTarefa).where(CrmTarefa.lead_id == lead.id, CrmTarefa.concluida.is_(False), CrmTarefa.automatica.is_(True))):
        t.concluida, t.concluida_em = True, agora()
    if dados.criar_lembrete:
        lembrete = max(quando - timedelta(days=1), agora())
        _tarefa_automatica(db, lead, f"Confirmar aula experimental de {regras.primeiro_nome(lead.nome)}",
                           regras.horario_comercial(lembrete) if lembrete < quando else lembrete,
                           "Mande a mensagem pronta de confirmação pelo WhatsApp.")
    prof = db.get(Profissional, dados.profissional_id) if dados.profissional_id else None
    local = quando.astimezone(regras.FUSO)
    _interacao_sistema(db, lead, ("Aula experimental remarcada para " if remarcando else "Aula experimental agendada para ")
                       + f"{local:%d/%m/%Y às %H:%M}" + (f" com {prof.nome}" if prof else "") + ".", ctx.usuario)
    _avancar_ate(ctx, lead, MarcoEtapa.AULA_AGENDADA)
    db.flush()
    ctx.auditar("crm.aula_experimental.agendar", "crm_lead", lead.id, descricao=f"Aula experimental de {lead.nome} em {local:%d/%m/%Y %H:%M}")
    db.commit()
    return lead


def resultado_aula_experimental(ctx: Contexto, lead: CrmLead, dados: sc.ResultadoAulaIn) -> CrmLead:
    db = ctx.db
    if lead.aula_experimental_status not in (StatusAulaExperimental.AGENDADA, StatusAulaExperimental.FALTOU):
        raise erro(409, "Não há aula experimental agendada para este lead.")
    obs = (dados.observacao or "").strip()
    for t in db.scalars(select(CrmTarefa).where(CrmTarefa.lead_id == lead.id, CrmTarefa.concluida.is_(False), CrmTarefa.automatica.is_(True))):
        t.concluida, t.concluida_em = True, agora()
    if dados.compareceu:
        lead.aula_experimental_status = StatusAulaExperimental.REALIZADA
        _interacao_sistema(db, lead, "Fez a aula experimental." + (f" {obs}" if obs else ""), ctx.usuario)
        _tarefa_automatica(db, lead, f"Enviar proposta para {regras.primeiro_nome(lead.nome)}", regras.horario_comercial(agora(), minutos=120))
        _avancar_ate(ctx, lead, MarcoEtapa.AULA_REALIZADA)
    else:
        lead.aula_experimental_status = StatusAulaExperimental.FALTOU
        _interacao_sistema(db, lead, "Não compareceu à aula experimental." + (f" {obs}" if obs else ""), ctx.usuario)
        _tarefa_automatica(db, lead, f"Remarcar aula experimental de {regras.primeiro_nome(lead.nome)}", regras.horario_comercial(agora(), minutos=60))
    lead.ultima_interacao_em = agora()
    db.flush()
    ctx.auditar("crm.aula_experimental.resultado", "crm_lead", lead.id,
                descricao=f"{lead.nome}: {'compareceu' if dados.compareceu else 'faltou'} à aula experimental")
    db.commit()
    return lead


# ------------------------------------------------------------------------------------------------ converter em aluno
def preparo_conversao(ctx: Contexto, lead: CrmLead) -> sc.PreparoConversao:
    db = ctx.db
    unidades = [sc.OpcaoSimples(id=u.id, nome=u.nome) for u in db.scalars(select(Unidade).where(Unidade.ativo.is_(True)).order_by(Unidade.nome))]
    parecidos: dict[int, sc.AlunoParecido] = {}
    if lead.telefone:
        for a in db.scalars(select(Aluno).join(AlunoTelefone, AlunoTelefone.aluno_id == Aluno.id).where(AlunoTelefone.numero == lead.telefone).limit(5)):
            parecidos[a.id] = sc.AlunoParecido(id=a.id, nome=a.nome, motivo="mesmo telefone")
    if lead.email:
        for a in db.scalars(select(Aluno).where(func.lower(Aluno.email) == lead.email.lower()).limit(5)):
            parecidos.setdefault(a.id, sc.AlunoParecido(id=a.id, nome=a.nome, motivo="mesmo e-mail"))
    for a in db.scalars(select(Aluno).where(func.lower(Aluno.nome) == lead.nome.lower()).limit(5)):
        parecidos.setdefault(a.id, sc.AlunoParecido(id=a.id, nome=a.nome, motivo="mesmo nome"))
    return sc.PreparoConversao(unidades=unidades, parecidos=list(parecidos.values()),
                               pode_criar_aluno=ctx.pode("alunos.editar") and not ctx.somente_proprias_aulas())


def converter(ctx: Contexto, lead: CrmLead, dados: sc.ConverterIn) -> sc.ConverterOut:
    """Cria o aluno pelo serviço do módulo alunos (ou vincula a um existente) e marca o lead como Matriculado."""
    db = ctx.db
    if lead.aluno_id:
        raise erro(409, "Este lead já foi convertido em aluno.")
    criado = False
    if dados.aluno_id:
        ctx.exigir("alunos.ver")
        aluno = alunos_servico.obter_aluno(ctx, dados.aluno_id)
    else:
        ctx.exigir("alunos.editar")
        if not dados.unidade_id:
            raise erro(422, "Escolha a unidade do aluno.")
        tel = regras.normalizar_telefone(lead.telefone)
        campos: dict = {"nome": lead.nome, "unidade_id": dados.unidade_id, "data_nascimento": dados.data_nascimento}
        campos.update({"cpf": dados.cpf} if dados.cpf else {"sem_cpf": True})
        if tel and normalizar_telefone_br(tel):
            campos["telefones"] = [{"numero": tel, "principal": True}]
        try:
            entrada = alunos_sc.AlunoIn(**campos, email=lead.email)
        except ValidationError:
            entrada = alunos_sc.AlunoIn(**campos)  # e-mail do lead inválido para o cadastro: segue sem ele
        aluno = alunos_servico.criar_aluno(ctx, entrada)  # audita e faz commit
        criado = True
    ganho = _etapa_tipo(db, TipoEtapa.GANHO)
    lead.aluno_id = aluno.id
    if lead.etapa_id != ganho.id:
        mover(ctx, lead, sc.MoverIn(etapa_id=ganho.id), commit=False)
    _interacao_sistema(db, lead, ("Convertido no aluno " if criado else "Vinculado ao aluno ") + f"{aluno.nome} (#{aluno.id}).", ctx.usuario)
    db.flush()
    ctx.auditar("crm.lead.converter", "crm_lead", lead.id, descricao=f"Lead {lead.nome} virou o aluno #{aluno.id}",
                depois={"aluno_id": aluno.id, "criado": criado})
    db.commit()
    return sc.ConverterOut(lead_id=lead.id, aluno_id=aluno.id, aluno_nome=aluno.nome, criado=criado)


# ------------------------------------------------------------------------------------------------ tarefas
def _fim_do_dia_local(agora_: datetime) -> datetime:
    hoje = regras.dia_local(agora_)
    return datetime.combine(hoje + timedelta(days=1), time.min, tzinfo=regras.FUSO).astimezone(UTC)


def listar_tarefas(ctx: Contexto, *, escopo: str, situacao: str, lead_id: int | None = None) -> sc.ListaTarefas:
    db = ctx.db
    agora_ = agora()
    fim_hoje = _fim_do_dia_local(agora_)
    conds = []
    if escopo == "minhas":
        conds.append(or_(CrmTarefa.responsavel_id == ctx.usuario.id, CrmTarefa.responsavel_id.is_(None)))
    if lead_id:
        conds.append(CrmTarefa.lead_id == lead_id)
    pend = [*conds, CrmTarefa.concluida.is_(False)]
    contagens = {
        "atrasadas": db.scalar(select(func.count()).select_from(CrmTarefa).where(*pend, CrmTarefa.vence_em < agora_)) or 0,
        "hoje": db.scalar(select(func.count()).select_from(CrmTarefa).where(*pend, CrmTarefa.vence_em >= agora_, CrmTarefa.vence_em < fim_hoje)) or 0,
        "futuras": db.scalar(select(func.count()).select_from(CrmTarefa).where(*pend, CrmTarefa.vence_em >= fim_hoje)) or 0,
        "concluidas_hoje": db.scalar(select(func.count()).select_from(CrmTarefa).where(
            *conds, CrmTarefa.concluida.is_(True), CrmTarefa.concluida_em >= fim_hoje - timedelta(days=1))) or 0,
    }
    if situacao == "concluidas":
        consulta = select(CrmTarefa).where(*conds, CrmTarefa.concluida.is_(True)).order_by(CrmTarefa.concluida_em.desc()).limit(100)
    else:
        q = pend
        if situacao == "hoje":
            q = [*pend, CrmTarefa.vence_em < fim_hoje]
        elif situacao == "atrasadas":
            q = [*pend, CrmTarefa.vence_em < agora_]
        consulta = select(CrmTarefa).where(*q).order_by(CrmTarefa.vence_em, CrmTarefa.id).limit(300)
    return sc.ListaTarefas(itens=_tarefas_out(db, list(db.scalars(consulta))), contagens=contagens)


def obter_tarefa(ctx: Contexto, tarefa_id: int) -> CrmTarefa:
    t = ctx.db.get(CrmTarefa, tarefa_id)
    if not t:
        raise erro(404, "Tarefa não encontrada.")
    return t


def _vence(v: datetime) -> datetime:
    return v if v.tzinfo else v.replace(tzinfo=regras.FUSO)


def criar_tarefa(ctx: Contexto, dados: sc.TarefaIn) -> CrmTarefa:
    db = ctx.db
    lead = obter_lead(ctx, dados.lead_id) if dados.lead_id else None
    responsavel = dados.responsavel_id if "responsavel_id" in dados.model_fields_set else ctx.usuario.id
    _validar_usuario(db, responsavel)
    t = CrmTarefa(lead_id=lead.id if lead else None, titulo=dados.titulo.strip(), descricao=dados.descricao,
                  vence_em=_vence(dados.vence_em), responsavel_id=responsavel, criado_por_id=ctx.usuario.id)
    db.add(t)
    db.flush()
    ctx.auditar("crm.tarefa.criar", "crm_tarefa", t.id, descricao=f"Tarefa \"{t.titulo}\"" + (f" ({lead.nome})" if lead else ""))
    db.commit()
    return t


def editar_tarefa(ctx: Contexto, t: CrmTarefa, dados: sc.TarefaIn) -> CrmTarefa:
    antes = audit.snapshot(t)
    if "responsavel_id" in dados.model_fields_set:
        _validar_usuario(ctx.db, dados.responsavel_id)
        t.responsavel_id = dados.responsavel_id
    t.titulo, t.descricao, t.vence_em = dados.titulo.strip(), dados.descricao, _vence(dados.vence_em)
    ctx.db.flush()
    ant, dep = audit.diff(antes, audit.snapshot(t))
    ctx.auditar("crm.tarefa.alterar", "crm_tarefa", t.id, descricao=f"Tarefa \"{t.titulo}\" alterada", antes=ant, depois=dep)
    ctx.db.commit()
    return t


def concluir_tarefa(ctx: Contexto, t: CrmTarefa, concluida: bool = True) -> CrmTarefa:
    if t.concluida == concluida:
        return t
    t.concluida, t.concluida_em = concluida, agora() if concluida else None
    if concluida and t.lead_id:
        lead = ctx.db.get(CrmLead, t.lead_id)
        if lead:
            _interacao_sistema(ctx.db, lead, f"Tarefa concluída: {t.titulo}.", ctx.usuario)
    ctx.auditar("crm.tarefa.concluir" if concluida else "crm.tarefa.reabrir", "crm_tarefa", t.id, descricao=f"Tarefa \"{t.titulo}\"")
    ctx.db.commit()
    return t


def excluir_tarefa(ctx: Contexto, t: CrmTarefa) -> None:
    ctx.auditar("crm.tarefa.excluir", "crm_tarefa", t.id, descricao=f"Tarefa \"{t.titulo}\" excluída", antes=audit.snapshot(t))
    ctx.db.delete(t)
    ctx.db.commit()


# ------------------------------------------------------------------------------------------------ configurações: etapas
def listar_etapas(ctx: Contexto) -> list[sc.EtapaOut]:
    db = ctx.db
    lista = etapas(db)
    contagem = dict(db.execute(select(CrmLead.etapa_id, func.count()).group_by(CrmLead.etapa_id)).all())
    db.commit()
    return [etapa_out(e, contagem.get(e.id, 0)) for e in lista]


def _marco_unico(db: Session, etapa: CrmEtapa) -> None:
    if etapa.marco:
        for outra in etapas(db):
            if outra.id != etapa.id and outra.marco == etapa.marco:
                outra.marco = None


def criar_etapa(ctx: Contexto, dados: sc.EtapaIn) -> CrmEtapa:
    db = ctx.db
    abertas = [e for e in etapas(db) if e.tipo == TipoEtapa.ABERTA]
    if len(abertas) >= 15:
        raise erro(422, "O funil já tem 15 etapas abertas. Simplifique antes de criar outra.")
    e = CrmEtapa(nome=dados.nome.strip(), cor=dados.cor, marco=dados.marco, dias_alerta=dados.dias_alerta,
                 tipo=TipoEtapa.ABERTA, ordem=max((x.ordem for x in abertas), default=0) + 1)
    db.add(e)
    db.flush()
    _marco_unico(db, e)
    ctx.auditar("crm.etapa.criar", "crm_etapa", e.id, descricao=f"Etapa \"{e.nome}\" criada", depois=audit.snapshot(e))
    db.commit()
    return e


def editar_etapa(ctx: Contexto, e: CrmEtapa, dados: sc.EtapaIn) -> CrmEtapa:
    antes = audit.snapshot(e)
    e.nome, e.cor, e.dias_alerta = dados.nome.strip(), dados.cor, dados.dias_alerta
    e.marco = dados.marco if e.tipo == TipoEtapa.ABERTA else None
    _marco_unico(ctx.db, e)
    ctx.db.flush()
    ant, dep = audit.diff(antes, audit.snapshot(e))
    ctx.auditar("crm.etapa.alterar", "crm_etapa", e.id, descricao=f"Etapa \"{e.nome}\" alterada", antes=ant, depois=dep)
    ctx.db.commit()
    return e


def reordenar_etapas(ctx: Contexto, ids: list[int]) -> None:
    abertas = {e.id: e for e in etapas(ctx.db) if e.tipo == TipoEtapa.ABERTA}
    if sorted(ids) != sorted(abertas):
        raise erro(422, "Envie todas as etapas abertas, na nova ordem (Matriculado e Perdido ficam sempre no fim).")
    for i, eid in enumerate(ids, start=1):
        abertas[eid].ordem = i
    ctx.auditar("crm.etapa.ordenar", "crm_etapa", None, descricao="Ordem das etapas do funil alterada", depois={"ids": ids})
    ctx.db.commit()


def excluir_etapa(ctx: Contexto, e: CrmEtapa, mover_para_id: int | None) -> None:
    db = ctx.db
    if e.tipo != TipoEtapa.ABERTA:
        raise erro(409, "As etapas Matriculado e Perdido são fixas: dá para renomear, mas não excluir.")
    abertas = [x for x in etapas(db) if x.tipo == TipoEtapa.ABERTA]
    if len(abertas) <= 1:
        raise erro(409, "O funil precisa de pelo menos uma etapa aberta.")
    leads = list(db.scalars(select(CrmLead).where(CrmLead.etapa_id == e.id)))
    if leads:
        destino = db.get(CrmEtapa, mover_para_id) if mover_para_id else None
        if not destino or destino.id == e.id or destino.tipo != TipoEtapa.ABERTA:
            raise erro(409, f"Há {len(leads)} lead(s) nesta etapa. Escolha para qual etapa aberta eles vão.")
        for lead in leads:
            lead.etapa_id, lead.etapa_desde = destino.id, agora()
            _registrar_movimento(db, lead, e, destino, ctx.usuario)
            _interacao_sistema(db, lead, f"A etapa \"{e.nome}\" foi excluída; o lead foi para \"{destino.nome}\".", ctx.usuario)
    db.flush()
    ctx.auditar("crm.etapa.excluir", "crm_etapa", e.id, descricao=f"Etapa \"{e.nome}\" excluída ({len(leads)} lead(s) movidos)", antes=audit.snapshot(e))
    db.delete(e)
    db.commit()


# ------------------------------------------------------------------------------------------------ configurações: motivos
def listar_motivos(ctx: Contexto) -> list[sc.MotivoOut]:
    db = ctx.db
    garantir_padrao(db)
    usos = dict(db.execute(select(CrmLead.motivo_perda_id, func.count()).where(CrmLead.motivo_perda_id.is_not(None)).group_by(CrmLead.motivo_perda_id)).all())
    lista = list(db.scalars(select(CrmMotivoPerda).order_by(CrmMotivoPerda.ativo.desc(), CrmMotivoPerda.ordem, CrmMotivoPerda.nome)))
    db.commit()
    return [sc.MotivoOut(id=m.id, nome=m.nome, ativo=m.ativo, usos=usos.get(m.id, 0)) for m in lista]


def criar_motivo(ctx: Contexto, dados: sc.MotivoIn) -> CrmMotivoPerda:
    db = ctx.db
    if db.scalar(select(CrmMotivoPerda).where(func.lower(CrmMotivoPerda.nome) == dados.nome.strip().lower())):
        raise erro(409, "Já existe um motivo com este nome.")
    m = CrmMotivoPerda(nome=dados.nome.strip(), ativo=dados.ativo,
                       ordem=(db.scalar(select(func.max(CrmMotivoPerda.ordem))) or 0) + 1)
    db.add(m)
    db.flush()
    ctx.auditar("crm.motivo.criar", "crm_motivo_perda", m.id, descricao=f"Motivo de perda \"{m.nome}\" criado")
    db.commit()
    return m


def editar_motivo(ctx: Contexto, m: CrmMotivoPerda, dados: sc.MotivoIn) -> CrmMotivoPerda:
    antes = audit.snapshot(m)
    m.nome, m.ativo = dados.nome.strip(), dados.ativo
    ctx.db.flush()
    ant, dep = audit.diff(antes, audit.snapshot(m))
    ctx.auditar("crm.motivo.alterar", "crm_motivo_perda", m.id, descricao=f"Motivo \"{m.nome}\" alterado", antes=ant, depois=dep)
    ctx.db.commit()
    return m


def excluir_motivo(ctx: Contexto, m: CrmMotivoPerda) -> str:
    """Motivo sem uso é excluído; em uso, é desativado (o histórico dos relatórios continua com o nome)."""
    usos = ctx.db.scalar(select(func.count()).select_from(CrmLead).where(CrmLead.motivo_perda_id == m.id)) or 0
    if usos:
        m.ativo = False
        ctx.auditar("crm.motivo.desativar", "crm_motivo_perda", m.id, descricao=f"Motivo \"{m.nome}\" desativado ({usos} uso(s))")
        ctx.db.commit()
        return f"O motivo está em {usos} lead(s) perdido(s); foi desativado em vez de excluído."
    ctx.auditar("crm.motivo.excluir", "crm_motivo_perda", m.id, descricao=f"Motivo \"{m.nome}\" excluído")
    ctx.db.delete(m)
    ctx.db.commit()
    return "Motivo excluído."


# ------------------------------------------------------------------------------------------------ opções e resumo
def opcoes(ctx: Contexto) -> sc.Opcoes:
    db = ctx.db
    usuarios = [u for u in db.scalars(select(Usuario).where(Usuario.ativo.is_(True), Usuario.acesso_sistema.is_(True), Usuario.suporte.is_not(True)).order_by(Usuario.nome))
                if u.pode("crm.ver")]
    tags: dict[str, str] = {}
    for lista in db.scalars(select(CrmLead.tags).where(CrmLead.situacao == SituacaoLead.ABERTO).limit(2000)):
        for t in lista or []:
            tags.setdefault(t.lower(), t)
    saida = sc.Opcoes(
        etapas=listar_etapas(ctx), motivos=listar_motivos(ctx),
        origens=[{"valor": o.value, "rotulo": regras.ROTULO_ORIGEM[o]} for o in OrigemLead],
        usuarios=[sc.UsuarioMini(id=u.id, nome=u.nome) for u in usuarios],
        profissionais=[sc.OpcaoSimples(id=p.id, nome=p.nome) for p in db.scalars(select(Profissional).where(Profissional.ativo.is_(True)).order_by(Profissional.nome))],
        unidades=[sc.OpcaoSimples(id=u.id, nome=u.nome) for u in db.scalars(select(Unidade).where(Unidade.ativo.is_(True)).order_by(Unidade.nome))],
        tags=sorted(tags.values(), key=str.lower), estudio=nome_estudio(db),
    )
    return saida


def resumo(ctx: Contexto) -> sc.Resumo:
    db = ctx.db
    garantir_padrao(db)
    agora_ = agora()
    fim_hoje = _fim_do_dia_local(agora_)
    inicio_hoje = fim_hoje - timedelta(days=1)
    abertos = list(db.scalars(select(CrmLead).where(CrmLead.situacao == SituacaoLead.ABERTO)))
    mapa = {e.id: e for e in etapas(db)}
    parados = sum(1 for lead in abertos if regras.esta_parado(regras.dias_entre(lead.etapa_desde, agora_) or 0,
                                                               mapa[lead.etapa_id].dias_alerta if lead.etapa_id in mapa else 0, lead.situacao))
    minhas = [or_(CrmTarefa.responsavel_id == ctx.usuario.id, CrmTarefa.responsavel_id.is_(None)), CrmTarefa.concluida.is_(False)]
    atrasadas = db.scalar(select(func.count()).select_from(CrmTarefa).where(*minhas, CrmTarefa.vence_em < agora_)) or 0
    hoje = db.scalar(select(func.count()).select_from(CrmTarefa).where(*minhas, CrmTarefa.vence_em >= agora_, CrmTarefa.vence_em < fim_hoje)) or 0
    aulas_hoje = sum(1 for lead in abertos if lead.aula_experimental_status == StatusAulaExperimental.AGENDADA
                     and lead.aula_experimental_em and inicio_hoje <= lead.aula_experimental_em < fim_hoje)
    limite30 = agora_ - timedelta(days=30)
    ganhos30 = db.scalar(select(func.count()).select_from(CrmLead).where(CrmLead.situacao == SituacaoLead.GANHO, CrmLead.ganho_em >= limite30)) or 0
    perdidos30 = db.scalar(select(func.count()).select_from(CrmLead).where(CrmLead.situacao == SituacaoLead.PERDIDO, CrmLead.perdido_em >= limite30)) or 0
    novos7 = sum(1 for lead in abertos if lead.criado_em >= agora_ - timedelta(days=7)) + (db.scalar(
        select(func.count()).select_from(CrmLead).where(CrmLead.situacao != SituacaoLead.ABERTO, CrmLead.criado_em >= agora_ - timedelta(days=7))) or 0)
    quentes_proposta = sum(1 for lead in abertos if lead.aula_experimental_status == StatusAulaExperimental.REALIZADA
                           and mapa.get(lead.etapa_id) and mapa[lead.etapa_id].marco != MarcoEtapa.PROPOSTA)
    if atrasadas:
        destaque = f"Você tem {atrasadas} tarefa(s) atrasada(s). Comece por elas."
    elif aulas_hoje:
        destaque = f"{aulas_hoje} aula(s) experimental(is) hoje: confirme a presença pelo WhatsApp."
    elif quentes_proposta:
        destaque = f"{quentes_proposta} lead(s) já fizeram a aula experimental e esperam proposta."
    elif parados:
        destaque = f"{parados} lead(s) parados há mais tempo que o combinado na etapa. Que tal um follow-up?"
    elif ganhos30:
        destaque = f"{ganhos30} matrícula(s) nos últimos 30 dias. Bom trabalho!"
    else:
        destaque = None
    db.commit()
    return sc.Resumo(
        abertos=len(abertos), novos_7_dias=novos7, valor_em_negociacao=regras.somar(lead.valor_estimado for lead in abertos),
        tarefas_hoje=hoje, tarefas_atrasadas=atrasadas, parados=parados, aulas_experimentais_hoje=aulas_hoje,
        conversoes_30_dias=ganhos30, taxa_conversao_30_dias=regras.percentual(ganhos30, ganhos30 + perdidos30), destaque=destaque,
    )


# ------------------------------------------------------------------------------------------------ relatório
def _instante(d: date, fim: bool = False) -> datetime:
    return datetime.combine(d + timedelta(days=1) if fim else d, time.min, tzinfo=regras.FUSO).astimezone(UTC)


def relatorio(ctx: Contexto, de: date, ate: date) -> sc.Relatorio:
    """Coorte: leads que ENTRARAM no período (`de`..`ate`, datas locais). Perdas por motivo: leads PERDIDOS no período."""
    db = ctx.db
    if ate < de:
        raise erro(422, "A data final deve ser depois da inicial.")
    if (ate - de).days > 731:
        raise erro(422, "Escolha um período de até dois anos.")
    ini, fim = _instante(de), _instante(ate, fim=True)
    lista_etapas = etapas(db)
    leads = list(db.scalars(select(CrmLead).where(CrmLead.criado_em >= ini, CrmLead.criado_em < fim)))
    ids = [lead.id for lead in leads]
    visitadas: dict[int, set[int]] = defaultdict(set)
    for lead in leads:
        visitadas[lead.id].add(lead.etapa_id)
    if ids:
        for lead_id, destino in db.execute(select(CrmMovimento.lead_id, CrmMovimento.etapa_destino_id).where(CrmMovimento.lead_id.in_(ids))).all():
            if destino:
                visitadas[lead_id].add(destino)
    escada = regras.etapas_do_funil([regras.EtapaInfo(e.id, e.nome, e.ordem, e.tipo.value, e.cor) for e in lista_etapas])
    ganho_id = next((e.id for e in escada if e.tipo == "GANHO"), None)
    degraus = []
    for lead in leads:
        d = regras.degrau_alcancado(escada, visitadas[lead.id])
        if lead.situacao == SituacaoLead.GANHO and ganho_id:
            d = len(escada) - 1  # matriculado conta como tendo passado por todas as etapas
        degraus.append(max(d, 0))
    funil_ = [sc.RelatorioEtapa(**x) for x in regras.conversao_por_etapa(escada, degraus)]

    ganhos = [lead for lead in leads if lead.situacao == SituacaoLead.GANHO]
    perdidos_coorte = [lead for lead in leads if lead.situacao == SituacaoLead.PERDIDO]
    por_origem = []
    for o in OrigemLead:
        grupo = [lead for lead in leads if lead.origem == o]
        if not grupo:
            continue
        g = [lead for lead in grupo if lead.situacao == SituacaoLead.GANHO]
        p = [lead for lead in grupo if lead.situacao == SituacaoLead.PERDIDO]
        por_origem.append(sc.RelatorioOrigem(
            origem=o, rotulo=regras.ROTULO_ORIGEM[o], total=len(grupo), ganhos=len(g), perdidos=len(p),
            abertos=len(grupo) - len(g) - len(p), taxa_conversao=regras.percentual(len(g), len(grupo)),
            tempo_medio_dias=regras.media_dias(lead.ganho_em - lead.criado_em for lead in g if lead.ganho_em)))
    por_origem.sort(key=lambda r: (-r.total, r.rotulo))

    motivos = {m.id: m.nome for m in db.scalars(select(CrmMotivoPerda))}
    contagem: dict[int | None, int] = defaultdict(int)
    for mid in db.scalars(select(CrmLead.motivo_perda_id).where(CrmLead.situacao == SituacaoLead.PERDIDO, CrmLead.perdido_em >= ini, CrmLead.perdido_em < fim)):
        contagem[mid] += 1
    total_perdas = sum(contagem.values())
    por_motivo = sorted(
        (sc.RelatorioMotivo(motivo_id=mid, motivo=motivos.get(mid, "Sem motivo"), quantidade=q, pct=regras.percentual(q, total_perdas))
         for mid, q in contagem.items()), key=lambda r: -r.quantidade)

    candidatas = [r for r in por_origem if r.total >= 3 and r.ganhos > 0]
    melhor = max(candidatas, key=lambda r: (r.taxa_conversao, r.total), default=None)
    gargalo = None
    passos = [(funil_[i - 1], funil_[i]) for i in range(1, len(funil_)) if funil_[i - 1].quantidade > 0]
    if passos and len(leads) >= 5:
        a, b = min(passos, key=lambda p: p[1].pct_anterior)
        gargalo = f"Maior perda entre \"{a.etapa}\" e \"{b.etapa}\": só {b.pct_anterior:.0f}% avançam."
    return sc.Relatorio(
        de=de, ate=ate, total_leads=len(leads), ganhos=len(ganhos), perdidos=len(perdidos_coorte),
        abertos=len(leads) - len(ganhos) - len(perdidos_coorte), taxa_conversao=regras.percentual(len(ganhos), len(leads)),
        tempo_medio_dias=regras.media_dias(lead.ganho_em - lead.criado_em for lead in ganhos if lead.ganho_em),
        valor_ganho=regras.somar(lead.valor_estimado for lead in ganhos), funil=funil_, por_origem=por_origem,
        perdidos_por_motivo=por_motivo,
        melhor_origem=f"{melhor.rotulo} converte {melhor.taxa_conversao:.0f}% dos leads." if melhor else None,
        gargalo=gargalo,
    )

