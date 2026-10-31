"""Rotas do controle de acesso.

- ``router`` (login da equipe): painel, histórico/relatório, biometria (LGPD), PIN, catracas, dispositivos, configuração.
- ``router_publico`` (autenticação PRÓPRIA, ver `rotas_totem.py`): totem (`/api/totem/*`, token do dispositivo),
  agente local (`/api/catraca-agente/*`, token do dispositivo) e QR do app do aluno (`/api/aluno-app/acesso/qr`).
"""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select

from app.core.audit import snapshot
from app.core.db import agora as agora_utc
from app.core.deps import Ctx
from app.core.permissoes import adicionar_regras
from app.core.schemas import Mensagem
from app.domain import acesso as dom
from app.modules.acesso import drivers
from app.modules.acesso import schemas as sc
from app.modules.acesso import servico as srv
from app.modules.acesso.models import (
    Catraca,
    ConsentimentoBiometria,
    CredencialAluno,
    DescritorFacial,
    Dispositivo,
    MetodoAcesso,
    RegistroAcesso,
    Sentido,
    TipoDispositivo,
)
from app.modules.acesso.rotas_totem import acionamento_out, router_publico  # noqa: F401  (descoberto pelo main)
from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
from app.modules.alunos import servico as alunos_srv
from app.modules.alunos.models import Aluno, StatusAluno
from app.modules.cadastros.models import Plano, TipoServico, Unidade

adicionar_regras([
    ("POST", r"/acesso/liberar$", "acesso.liberar_manual"),
    ("POST", r"/acesso/catracas/\d+/liberar$", "acesso.liberar_manual"),
    ("POST", r"/acesso/registros/\d+/catraca$", "acesso.liberar_manual"),
    ("POST", r"/acesso/presentes/\d+/saida$", "acesso.liberar_manual"),
    ("GET", r"/acesso", "acesso.ver"),
    ("*", r"/acesso", "acesso.configurar"),
])

router = APIRouter(prefix="/acesso", tags=["acesso"])


def _agora() -> datetime:
    """Relógio da API (os testes congelam)."""
    return agora_utc()


def _erro(e: srv.ErroAcesso) -> HTTPException:
    return HTTPException(e.status, e.mensagem)


def _aluno(ctx: Ctx, aluno_id: int) -> Aluno:
    a = ctx.db.get(Aluno, aluno_id)
    if a is None:
        raise HTTPException(404, "Aluno não encontrado.")
    return a


def _registro_out(r: RegistroAcesso) -> sc.RegistroOut:
    return sc.RegistroOut.model_validate(r)


# ---------------------------------------------------------------------------------------------------- configuração
@router.get("/config", response_model=sc.ConfigOut)
def ler_config(ctx: Ctx):
    cfg = srv.obter_config(ctx.db)
    ctx.db.commit()
    valores = {k: getattr(cfg, k) for k in sc.ConfigIn.model_fields}
    valores["planos_livres"] = valores["planos_livres"] or []
    return sc.ConfigOut(**valores)


@router.put("/config", response_model=sc.ConfigOut)
def salvar_config(dados: sc.ConfigIn, ctx: Ctx):
    cfg = srv.obter_config(ctx.db)
    antes = snapshot(cfg)
    planos = set(ctx.db.scalars(select(Plano.id).where(Plano.id.in_(dados.planos_livres or [-1]))))
    if set(dados.planos_livres) - planos:
        raise HTTPException(422, "Plano de acesso livre inválido.")
    for k, v in dados.model_dump().items():
        setattr(cfg, k, v)
    ctx.db.flush()
    ctx.auditar("editar", "acesso_config", 1, "Configuração do controle de acesso alterada", antes=antes, depois=snapshot(cfg))
    ctx.db.commit()
    return ler_config(ctx)


@router.get("/opcoes", response_model=sc.OpcoesOut)
def opcoes(ctx: Ctx):
    db = ctx.db
    return sc.OpcoesOut(
        unidades=[sc.OpcaoOut(id=u.id, nome=u.nome) for u in db.scalars(select(Unidade).where(Unidade.ativo.is_(True)).order_by(Unidade.nome))],
        planos=[sc.OpcaoOut(id=p.id, nome=p.nome) for p in db.scalars(select(Plano).where(Plano.ativo.is_(True)).order_by(Plano.nome))],
        drivers=[sc.DriverOut(nome=d.nome, rotulo=d.rotulo, suporta_navegador=d.suporta_navegador) for d in drivers.DRIVERS.values()],
        catracas=[sc.OpcaoOut(id=c.id, nome=c.nome) for c in db.scalars(select(Catraca).order_by(Catraca.nome))],
    )


# ---------------------------------------------------------------------------------------------------- painel
@router.get("/painel", response_model=sc.PainelOut)
def painel(ctx: Ctx):
    db = ctx.db
    agora = _agora()
    hoje = dom.local(agora).date()
    presentes = []
    for r in srv.presentes_agora(db, agora):
        a = db.get(Aluno, r.aluno_id) if r.aluno_id else None
        presentes.append(sc.PresenteOut(
            registro_id=r.id, aluno_id=r.aluno_id, nome=r.aluno_nome or "Aluno", primeiro_nome=dom.primeiro_nome(r.aluno_nome or ""),
            foto_url=alunos_srv.foto_url(a) if a else None, entrou_em=r.em, previsto_sair=r.previsto_sair, aula=r.aula_descricao,
            metodo=str(getattr(r.metodo, "value", r.metodo)), aniversario=dom.faz_aniversario(a.data_nascimento if a else None, hoje),
        ))
    ultimos = [_registro_out(r) for r in db.scalars(select(RegistroAcesso).order_by(RegistroAcesso.em.desc(), RegistroAcesso.id.desc()).limit(15))]
    equipamentos = [sc.EquipamentoStatusOut(id=d.id, nome=d.nome, tipo=str(getattr(d.tipo, "value", d.tipo)), online=srv.online(d, agora),
                                            detalhe=None) for d in db.scalars(select(Dispositivo).where(Dispositivo.ativo.is_(True)).order_by(Dispositivo.nome))]
    equipamentos += [sc.EquipamentoStatusOut(id=c.id, nome=c.nome, tipo="catraca", online=c.ultimo_teste_ok, detalhe=c.ultimo_teste_detalhe)
                     for c in db.scalars(select(Catraca).where(Catraca.ativo.is_(True)).order_by(Catraca.nome))]
    # próximas aulas de hoje (quem ainda vai chegar)
    agora_local = dom.local(agora)
    desde = max(agora_local - timedelta(minutes=15), datetime.combine(hoje, time.min, tzinfo=dom.FUSO)).time()
    proximas = []
    q = (select(AulaSessao, TipoServico.nome, func.count(Reserva.id))
         .join(TipoServico, TipoServico.id == AulaSessao.tipo_servico_id)
         .join(Reserva, Reserva.aula_sessao_id == AulaSessao.id)
         .where(AulaSessao.data == hoje, AulaSessao.hora_inicio >= desde,
                Reserva.status.in_((StatusReserva.RESERVADA, StatusReserva.PENDENTE)))
         .group_by(AulaSessao.id, TipoServico.nome).order_by(AulaSessao.hora_inicio).limit(6))
    for s, nome, n in db.execute(q).all():
        chegaram = db.scalar(select(func.count(Reserva.id)).where(Reserva.aula_sessao_id == s.id, Reserva.confirmada_em.is_not(None),
                                                                 Reserva.status == StatusReserva.RESERVADA)) or 0
        proximas.append({"sessao_id": s.id, "servico": nome, "inicio": s.hora_inicio.strftime("%H:%M"), "fim": s.hora_fim.strftime("%H:%M"),
                         "reservas": n, "chegaram": chegaram})
    ctx.db.commit()
    return sc.PainelOut(agora=agora, presentes=presentes, ultimos=ultimos, equipamentos=equipamentos, proximas_aulas=proximas,
                        **srv.contagens_do_dia(db, agora))


@router.post("/presentes/{registro_id:int}/saida", response_model=Mensagem)
def marcar_saida(registro_id: int, dados: sc.SaidaIn, ctx: Ctx):
    r = ctx.db.get(RegistroAcesso, registro_id)
    if r is None or not r.aluno_id:
        raise HTTPException(404, "Registro não encontrado.")
    a = ctx.db.get(Aluno, r.aluno_id)
    reg = srv.novo_registro(ctx.db, aluno=a, permitido=True, codigo="saida", motivo=dados.motivo or "Saída registrada pela recepção",
                            metodo=MetodoAcesso.manual, agora=_agora(), usuario=ctx.usuario, sentido="saida")
    ctx.auditar("saida", "acesso_registro", reg.id, f"Saída de {r.aluno_nome} registrada")
    ctx.db.commit()
    return Mensagem(mensagem="Saída registrada.")


# ---------------------------------------------------------------------------------------------------- histórico
def _filtros(q, de: date | None, ate: date | None, permitido: bool | None, metodo: str | None, busca: str | None):
    if de:
        q = q.where(RegistroAcesso.em >= datetime.combine(de, time.min, tzinfo=dom.FUSO))
    if ate:
        q = q.where(RegistroAcesso.em < datetime.combine(ate + timedelta(days=1), time.min, tzinfo=dom.FUSO))
    if permitido is not None:
        q = q.where(RegistroAcesso.permitido.is_(permitido))
    if metodo:
        q = q.where(RegistroAcesso.metodo == MetodoAcesso(metodo))
    if busca:
        termo = f"%{busca.strip()}%"
        q = q.where(or_(RegistroAcesso.aluno_nome.ilike(termo), RegistroAcesso.motivo.ilike(termo)))
    return q


_METODO = "^(facial|cpf|codigo|qr|manual)$"


@router.get("/registros", response_model=sc.ListaRegistrosOut)
def registros(ctx: Ctx, de: date | None = None, ate: date | None = None, permitido: bool | None = None,
              metodo: str | None = Query(None, pattern=_METODO), q: str | None = Query(None, max_length=100),
              pagina: int = Query(1, ge=1), por_pagina: int = Query(25, ge=1, le=200)):
    base = _filtros(select(RegistroAcesso), de, ate, permitido, metodo, q)
    total = ctx.db.scalar(select(func.count()).select_from(base.subquery())) or 0
    itens = ctx.db.scalars(base.order_by(RegistroAcesso.em.desc(), RegistroAcesso.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina))
    return sc.ListaRegistrosOut(itens=[_registro_out(r) for r in itens], total=total, pagina=pagina, por_pagina=por_pagina)


@router.get("/registros.csv")
def registros_csv(ctx: Ctx, de: date | None = None, ate: date | None = None, permitido: bool | None = None,
                  metodo: str | None = Query(None, pattern=_METODO), q: str | None = Query(None, max_length=100)):
    base = _filtros(select(RegistroAcesso), de, ate, permitido, metodo, q).order_by(RegistroAcesso.em).limit(50000)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Data/hora", "Aluno", "Resultado", "Motivo", "Método", "Sentido", "Dispositivo", "Aula", "Presença", "Catraca", "Liberado por"])
    for r in ctx.db.scalars(base):
        w.writerow([dom.local(r.em).strftime("%d/%m/%Y %H:%M:%S"), r.aluno_nome or "", "Permitido" if r.permitido else "Negado", r.motivo,
                    str(getattr(r.metodo, "value", r.metodo)), str(getattr(r.sentido, "value", r.sentido)), r.dispositivo_nome or "",
                    r.aula_descricao or "", "sim" if r.presenca_registrada else "", r.catraca_status or "", r.usuario_nome or ""])
    ctx.auditar("exportar", "acesso_registro", None, "Exportou o histórico de acessos (CSV)")
    ctx.db.commit()
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="acessos.csv"'})


@router.get("/relatorio", response_model=sc.RelatorioOut)
def relatorio(ctx: Ctx, de: date | None = None, ate: date | None = None):
    hoje = dom.local(_agora()).date()
    ate = ate or hoje
    de = de or (ate - timedelta(days=29))
    if de > ate:
        raise HTTPException(422, "A data inicial é depois da final.")
    if (ate - de).days > 366:
        raise HTTPException(422, "Período máximo: um ano.")
    regs = list(ctx.db.scalars(_filtros(select(RegistroAcesso), de, ate, None, None, None).where(RegistroAcesso.sentido == Sentido.entrada)))
    por_dia: dict[date, list[int]] = {de + timedelta(days=i): [0, 0] for i in range((ate - de).days + 1)}
    por_hora = Counter()
    metodo = Counter()
    motivos = Counter()
    freq: dict[int, list] = defaultdict(lambda: ["", set()])
    for r in regs:
        local = dom.local(r.em)
        d = por_dia.setdefault(local.date(), [0, 0])
        if r.permitido:
            d[0] += 1
            por_hora[local.hour] += 1
            metodo[str(getattr(r.metodo, "value", r.metodo))] += 1
            if r.aluno_id:
                freq[r.aluno_id][0] = r.aluno_nome or ""
                freq[r.aluno_id][1].add(local.date())
        else:
            d[1] += 1
            motivos[r.codigo] += 1
    mais = sorted(({"aluno_id": k, "nome": v[0], "dias": len(v[1])} for k, v in freq.items()), key=lambda x: (-x["dias"], x["nome"]))[:10]
    permitidos = sum(v[0] for v in por_dia.values())
    return sc.RelatorioOut(
        de=de, ate=ate, total=len(regs), permitidos=permitidos, negados=len(regs) - permitidos, alunos_unicos=len(freq),
        por_dia=[{"dia": k.isoformat(), "permitidos": v[0], "negados": v[1]} for k, v in sorted(por_dia.items())],
        por_hora=[{"hora": h, "total": por_hora.get(h, 0)} for h in range(5, 24)],
        por_metodo=[{"metodo": k, "total": v} for k, v in metodo.most_common()],
        motivos_negacao=[{"codigo": k, "rotulo": dom.ROTULO_CODIGO.get(k, k), "total": v} for k, v in motivos.most_common()],
        mais_frequentes=mais,
    )


# ---------------------------------------------------------------------------------------------------- biometria
def _cons_out(c: ConsentimentoBiometria | None) -> sc.ConsentimentoOut | None:
    return sc.ConsentimentoOut.model_validate(c) if c else None


def _aluno_acesso(ctx: Ctx, a: Aluno, n_desc: int | None = None, pin: bool | None = None) -> dict:
    db = ctx.db
    if n_desc is None:
        n_desc = db.scalar(select(func.count(DescritorFacial.id)).where(DescritorFacial.aluno_id == a.id)) or 0
    if pin is None:
        pin = db.scalar(select(CredencialAluno.id).where(CredencialAluno.aluno_id == a.id, CredencialAluno.pin_hash.is_not(None))) is not None
    return {"id": a.id, "nome": a.nome, "cpf": alunos_srv.mascarar_cpf(a.cpf), "codigo": a.codigo_legado,
            "ativo": StatusAluno(a.status) == StatusAluno.ATIVO, "foto_url": alunos_srv.foto_url(a),
            "consentimento": _cons_out(srv.consentimento_ativo(db, a.id)), "descritores": n_desc, "pin_definido": pin}


@router.get("/alunos", response_model=sc.ListaAlunosAcessoOut)
def alunos(ctx: Ctx, q: str | None = Query(None, max_length=100), situacao: str = Query("todos", pattern="^(todos|com_biometria|sem_biometria)$"),
           pagina: int = Query(1, ge=1), por_pagina: int = Query(20, ge=1, le=100)):
    db = ctx.db
    com_bio = select(DescritorFacial.aluno_id).distinct()
    base = select(Aluno).where(Aluno.status == StatusAluno.ATIVO)
    if q:
        d = dom.so_digitos(q)
        conds = [Aluno.nome.ilike(f"%{q.strip()}%")]
        if d:
            conds.append(Aluno.cpf.like(f"%{d}%"))
            if len(d) <= 9:
                conds.append(Aluno.codigo_legado == int(d))
        base = base.where(or_(*conds))
    total_com = db.scalar(select(func.count()).select_from(select(Aluno.id).where(Aluno.status == StatusAluno.ATIVO, Aluno.id.in_(com_bio)).subquery())) or 0
    total_ativos = db.scalar(select(func.count(Aluno.id)).where(Aluno.status == StatusAluno.ATIVO)) or 0
    if situacao == "com_biometria":
        base = base.where(Aluno.id.in_(com_bio))
    elif situacao == "sem_biometria":
        base = base.where(Aluno.id.not_in(com_bio))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    itens = [sc.AlunoAcessoOut(**_aluno_acesso(ctx, a)) for a in db.scalars(base.order_by(Aluno.nome).offset((pagina - 1) * por_pagina).limit(por_pagina))]
    return sc.ListaAlunosAcessoOut(itens=itens, total=total, pagina=pagina, por_pagina=por_pagina, com_biometria=total_com,
                                   sem_biometria=max(total_ativos - total_com, 0))


@router.get("/alunos/{aluno_id:int}", response_model=sc.AlunoAcessoDetalheOut)
def aluno_detalhe(aluno_id: int, ctx: Ctx):
    db = ctx.db
    a = _aluno(ctx, aluno_id)
    descs = list(db.scalars(select(DescritorFacial).where(DescritorFacial.aluno_id == a.id).order_by(DescritorFacial.id)))
    hist = list(db.scalars(select(ConsentimentoBiometria).where(ConsentimentoBiometria.aluno_id == a.id).order_by(ConsentimentoBiometria.id.desc())))
    ult = list(db.scalars(select(RegistroAcesso).where(RegistroAcesso.aluno_id == a.id).order_by(RegistroAcesso.em.desc()).limit(10)))
    cfg = srv.obter_config(db)
    db.commit()
    return sc.AlunoAcessoDetalheOut(**_aluno_acesso(ctx, a, len(descs)), lista_descritores=[sc.DescritorOut.model_validate(d) for d in descs],
                                    historico_consentimentos=[sc.ConsentimentoOut.model_validate(c) for c in hist],
                                    termo_atual=cfg.termo_biometria or srv.TERMO_PADRAO, ultimos_acessos=[_registro_out(r) for r in ult])


@router.get("/alunos/{aluno_id:int}/decisao")
def simular_decisao(aluno_id: int, ctx: Ctx):
    """Mostra o que a regra decidiria AGORA para o aluno (sem registrar nada). Ajuda a recepção a explicar o motivo."""
    d = srv.avaliar_acesso(ctx.db, _aluno(ctx, aluno_id), _agora())
    ctx.db.commit()
    return {"permitido": d.permitido, "codigo": d.codigo, "motivo": d.motivo, "avisos": d.avisos,
            "aula": srv._descricao_aula(d.aula), "aniversario": d.aniversario}


@router.post("/alunos/{aluno_id:int}/consentimento", response_model=sc.ConsentimentoOut, status_code=201)
def consentir(aluno_id: int, dados: sc.ConsentimentoIn, ctx: Ctx):
    a = _aluno(ctx, aluno_id)
    cfg = srv.obter_config(ctx.db)
    c = srv.registrar_consentimento(ctx.db, a, texto=cfg.termo_biometria or srv.TERMO_PADRAO, coletado_por=ctx.usuario, ip=ctx.ip, agora=_agora())
    ctx.auditar("consentimento", "aluno", a.id, f"Consentimento de biometria facial registrado para {a.nome} (termo {c.hash_termo[:8]})")
    ctx.db.commit()
    return sc.ConsentimentoOut.model_validate(c)


@router.post("/alunos/{aluno_id:int}/descritores", response_model=list[sc.DescritorOut], status_code=201)
def cadastrar_rosto(aluno_id: int, dados: sc.DescritoresIn, ctx: Ctx):
    a = _aluno(ctx, aluno_id)
    cfg = srv.obter_config(ctx.db)
    pv = dados.prova_vida
    if cfg.exigir_prova_vida and not (pv and dom.prova_de_vida_ok(pv.piscou, pv.real, pv.live)):
        raise HTTPException(422, "Não detectei prova de vida (piscar ou movimento). Tente de novo, com boa luz.")
    try:
        novos = srv.adicionar_descritores(ctx.db, a, dados.descritores, origem="recepcao", criado_por_nome=ctx.usuario.nome, qualidade=dados.qualidade)
    except srv.ErroAcesso as e:
        raise _erro(e) from None
    ctx.auditar("cadastrar_biometria", "aluno", a.id, f"{len(novos)} descritor(es) facial(is) cadastrado(s) para {a.nome}")
    ctx.db.commit()
    return [sc.DescritorOut.model_validate(d) for d in novos]


@router.delete("/alunos/{aluno_id:int}/descritores/{descritor_id:int}", response_model=Mensagem)
def apagar_descritor(aluno_id: int, descritor_id: int, ctx: Ctx):
    d = ctx.db.get(DescritorFacial, descritor_id)
    if d is None or d.aluno_id != aluno_id:
        raise HTTPException(404, "Descritor não encontrado.")
    ctx.db.delete(d)
    ctx.auditar("apagar_biometria", "aluno", aluno_id, f"Descritor facial {descritor_id} apagado")
    ctx.db.commit()
    return Mensagem(mensagem="Descritor apagado.")


@router.post("/alunos/{aluno_id:int}/biometria/apagar", response_model=Mensagem)
def apagar_biometria(aluno_id: int, dados: sc.ApagarBiometriaIn, ctx: Ctx):
    a = _aluno(ctx, aluno_id)
    n = srv.apagar_biometria(ctx.db, a, por_nome=ctx.usuario.nome, motivo=dados.motivo, agora=_agora())
    ctx.auditar("apagar_biometria", "aluno", a.id, f"Biometria facial de {a.nome} apagada ({n} descritores) e consentimento revogado: {dados.motivo}")
    ctx.db.commit()
    return Mensagem(mensagem=f"Biometria apagada ({n} descritor(es)). O consentimento foi revogado.")


@router.put("/alunos/{aluno_id:int}/pin", response_model=Mensagem)
def definir_pin(aluno_id: int, dados: sc.PinIn, ctx: Ctx):
    a = _aluno(ctx, aluno_id)
    try:
        srv.definir_pin(ctx.db, a, dados.pin)
    except srv.ErroAcesso as e:
        raise _erro(e) from None
    ctx.auditar("definir_pin", "aluno", a.id, f"PIN de acesso definido para {a.nome}")
    ctx.db.commit()
    return Mensagem(mensagem="PIN definido.")


@router.delete("/alunos/{aluno_id:int}/pin", response_model=Mensagem)
def remover_pin(aluno_id: int, ctx: Ctx):
    a = _aluno(ctx, aluno_id)
    srv.remover_pin(ctx.db, a)
    ctx.auditar("remover_pin", "aluno", a.id, f"PIN de acesso removido de {a.nome}")
    ctx.db.commit()
    return Mensagem(mensagem="PIN removido.")


@router.post("/alunos/{aluno_id:int}/codigo-totem", response_model=sc.CodigoTotemOut)
def codigo_totem(aluno_id: int, ctx: Ctx):
    """Código de uso único (15 min) para o aluno cadastrar o rosto no próprio totem: é a confirmação da recepção."""
    a = _aluno(ctx, aluno_id)
    codigo, expira = srv.gerar_codigo_totem(ctx.db, a, ctx.usuario, _agora())
    ctx.auditar("codigo_totem", "aluno", a.id, f"Código para cadastro do rosto no totem gerado para {a.nome}")
    ctx.db.commit()
    return sc.CodigoTotemOut(codigo=codigo, expira_em=expira)


# ---------------------------------------------------------------------------------------------------- liberação manual
@router.post("/liberar", response_model=sc.CheckinOut)
def liberar_manual(dados: sc.LiberarIn, ctx: Ctx, catraca_id: int | None = Query(None)):
    """Liberação manual (com motivo, auditada). Sem catraca: só registra a entrada (ex.: recepção sem catraca)."""
    return _liberar(ctx, catraca_id, dados)


@router.post("/catracas/{catraca_id:int}/liberar", response_model=sc.CheckinOut)
def liberar_catraca(catraca_id: int, dados: sc.LiberarIn, ctx: Ctx):
    return _liberar(ctx, catraca_id, dados)


def _liberar(ctx: Ctx, catraca_id: int | None, dados: sc.LiberarIn) -> sc.CheckinOut:
    db = ctx.db
    cat = db.get(Catraca, catraca_id) if catraca_id else None
    if catraca_id and cat is None:
        raise HTTPException(404, "Catraca não encontrada.")
    a = _aluno(ctx, dados.aluno_id) if dados.aluno_id else None
    agora = _agora()
    reg = srv.novo_registro(db, aluno=a, permitido=True, codigo=dom.OK_MANUAL, motivo=f"Liberação manual: {dados.motivo}",
                            metodo=MetodoAcesso.manual, agora=agora, usuario=ctx.usuario, sentido=dados.sentido)
    if a is not None and dados.sentido == "entrada":
        reg.previsto_sair = agora + timedelta(minutes=srv.obter_config(db).permanencia_livre_min)
    acion = srv.acionar_catraca(db, cat, sentido=dados.sentido, registro=reg, agora=agora) if cat else None
    ctx.auditar("liberar_manual", "acesso_registro", reg.id,
                f"Liberação manual{' da catraca ' + cat.nome if cat else ''}{' para ' + a.nome if a else ''}: {dados.motivo}")
    db.commit()
    return sc.CheckinOut(permitido=True, codigo=dom.OK_MANUAL, motivo=reg.motivo, titulo="Liberado manualmente",
                         primeiro_nome=dom.primeiro_nome(a.nome) if a else None, registro_id=reg.id, acionamento=acionamento_out(acion))


@router.post("/registros/{registro_id:int}/catraca", response_model=Mensagem)
def resultado_catraca(registro_id: int, dados: sc.ResultadoCatracaIn, ctx: Ctx):
    """O navegador da recepção executou o plano na rede local e informa o resultado."""
    r = ctx.db.get(RegistroAcesso, registro_id)
    if r is None:
        raise HTTPException(404, "Registro não encontrado.")
    r.catraca_status = "liberada" if dados.ok else "falhou"
    r.catraca_detalhe = (dados.detalhe or "")[:300]
    ctx.db.commit()
    return Mensagem(mensagem="Resultado registrado.")


# ---------------------------------------------------------------------------------------------------- catracas
def _catraca_out(db, c: Catraca) -> sc.CatracaOut:
    un = db.get(Unidade, c.unidade_id) if c.unidade_id else None
    return sc.CatracaOut(id=c.id, nome=c.nome, unidade_id=c.unidade_id, unidade_nome=un.nome if un else None, driver=str(getattr(c.driver, "value", c.driver)),
                         modo=str(getattr(c.modo, "value", c.modo)), host=c.host, porta=c.porta, usar_https=c.usar_https, usuario=c.usuario,
                         senha_definida=c.senha_cifrada is not None, senha_final=c.senha_final, sentido_entrada=c.sentido_entrada,
                         acao_liberacao=c.acao_liberacao, porta_rele=c.porta_rele, ativo=c.ativo, ultimo_teste_em=c.ultimo_teste_em,
                         ultimo_teste_ok=c.ultimo_teste_ok, ultimo_teste_detalhe=c.ultimo_teste_detalhe)


def _obter_catraca(ctx: Ctx, catraca_id: int) -> Catraca:
    c = ctx.db.get(Catraca, catraca_id)
    if c is None:
        raise HTTPException(404, "Catraca não encontrada.")
    return c


def _aplicar_catraca(ctx: Ctx, c: Catraca, dados: sc.CatracaIn) -> None:
    if dados.unidade_id and ctx.db.get(Unidade, dados.unidade_id) is None:
        raise HTTPException(422, "Unidade inválida.")
    if dados.driver != "simulado" and not dados.host:
        raise HTTPException(422, "Informe o IP (ou nome) da catraca na rede local.")
    if dados.driver == "henry" and dados.modo == "totem":
        raise HTTPException(422, "Catraca Henry/Topdata não pode ser acionada pelo navegador do totem: use o agente local.")
    for k, v in dados.model_dump(exclude={"senha"}).items():
        setattr(c, k, v)
    if dados.senha:
        c.senha_cifrada = srv.segredos.cifrar_texto(dados.senha)
        c.senha_final = dados.senha[-4:] if len(dados.senha) >= 8 else None


@router.get("/catracas", response_model=list[sc.CatracaOut])
def listar_catracas(ctx: Ctx):
    return [_catraca_out(ctx.db, c) for c in ctx.db.scalars(select(Catraca).order_by(Catraca.nome))]


@router.post("/catracas", response_model=sc.CatracaOut, status_code=201)
def criar_catraca(dados: sc.CatracaIn, ctx: Ctx):
    c = Catraca()
    _aplicar_catraca(ctx, c, dados)
    ctx.db.add(c)
    ctx.db.flush()
    ctx.auditar("criar", "acesso_catraca", c.id, f"Catraca {c.nome} cadastrada", depois=snapshot(c))
    ctx.db.commit()
    return _catraca_out(ctx.db, c)


@router.put("/catracas/{catraca_id:int}", response_model=sc.CatracaOut)
def editar_catraca(catraca_id: int, dados: sc.CatracaIn, ctx: Ctx):
    c = _obter_catraca(ctx, catraca_id)
    antes = snapshot(c)
    _aplicar_catraca(ctx, c, dados)
    ctx.db.flush()
    depois = snapshot(c)
    if dados.senha:
        depois["senha"] = "(alterada)"
    ctx.auditar("editar", "acesso_catraca", c.id, f"Catraca {c.nome} alterada", antes=antes, depois=depois)
    ctx.db.commit()
    return _catraca_out(ctx.db, c)


@router.delete("/catracas/{catraca_id:int}", response_model=Mensagem)
def excluir_catraca(catraca_id: int, ctx: Ctx):
    c = _obter_catraca(ctx, catraca_id)
    ctx.auditar("excluir", "acesso_catraca", c.id, f"Catraca {c.nome} excluída", antes=snapshot(c))
    ctx.db.delete(c)
    ctx.db.commit()
    return Mensagem(mensagem="Catraca excluída.")


@router.post("/catracas/{catraca_id:int}/testar", response_model=sc.TesteOut)
def testar_catraca(catraca_id: int, ctx: Ctx):
    """Servidor: testa já. Agente: envia comando de status. Totem: devolve o plano para ESTE navegador testar na rede local."""
    c = _obter_catraca(ctx, catraca_id)
    agora = _agora()
    a = srv.acionar_catraca(ctx.db, c, acao="status", agora=agora)
    if a.status in ("ok", "falhou") and a.plano is None:
        c.ultimo_teste_em, c.ultimo_teste_ok, c.ultimo_teste_detalhe = agora, a.status == "ok", a.mensagem[:300]
    ctx.auditar("testar", "acesso_catraca", c.id, f"Teste de conexão da catraca {c.nome}: {a.mensagem}")
    ctx.db.commit()
    ok = None if a.status == "pendente" else a.status == "ok"
    return sc.TesteOut(ok=ok, mensagem=a.mensagem, acionamento=acionamento_out(a))


@router.post("/catracas/{catraca_id:int}/teste-navegador", response_model=Mensagem)
def resultado_teste_navegador(catraca_id: int, dados: sc.ResultadoCatracaIn, ctx: Ctx):
    c = _obter_catraca(ctx, catraca_id)
    c.ultimo_teste_em, c.ultimo_teste_ok, c.ultimo_teste_detalhe = _agora(), dados.ok, (dados.detalhe or "")[:300]
    ctx.db.commit()
    return Mensagem(mensagem="Resultado do teste registrado.")


# ---------------------------------------------------------------------------------------------------- dispositivos
def _disp_out(db, d: Dispositivo, token: str | None = None):
    un = db.get(Unidade, d.unidade_id) if d.unidade_id else None
    cat = db.get(Catraca, d.catraca_id) if d.catraca_id else None
    base = dict(id=d.id, nome=d.nome, tipo=str(getattr(d.tipo, "value", d.tipo)), unidade_id=d.unidade_id, unidade_nome=un.nome if un else None,
                catraca_id=d.catraca_id, catraca_nome=cat.nome if cat else None, token_final=d.token_final, ativo=d.ativo,
                revogado_em=d.revogado_em, ultimo_contato=d.ultimo_contato, online=srv.online(d, _agora()), criado_em=d.criado_em,
                criado_por_nome=d.criado_por_nome)
    return sc.DispositivoComTokenOut(**base, token=token) if token else sc.DispositivoOut(**base)


def _obter_disp(ctx: Ctx, dispositivo_id: int) -> Dispositivo:
    d = ctx.db.get(Dispositivo, dispositivo_id)
    if d is None:
        raise HTTPException(404, "Dispositivo não encontrado.")
    return d


def _validar_refs_disp(ctx: Ctx, unidade_id: int | None, catraca_id: int | None) -> None:
    if unidade_id and ctx.db.get(Unidade, unidade_id) is None:
        raise HTTPException(422, "Unidade inválida.")
    if catraca_id and ctx.db.get(Catraca, catraca_id) is None:
        raise HTTPException(422, "Catraca inválida.")


@router.get("/dispositivos", response_model=list[sc.DispositivoOut])
def listar_dispositivos(ctx: Ctx):
    return [_disp_out(ctx.db, d) for d in ctx.db.scalars(select(Dispositivo).order_by(Dispositivo.ativo.desc(), Dispositivo.nome))]


@router.post("/dispositivos", response_model=sc.DispositivoComTokenOut, status_code=201)
def criar_dispositivo(dados: sc.DispositivoIn, ctx: Ctx):
    _validar_refs_disp(ctx, dados.unidade_id, dados.catraca_id)
    d = Dispositivo(nome=dados.nome.strip(), tipo=TipoDispositivo(dados.tipo), unidade_id=dados.unidade_id, catraca_id=dados.catraca_id,
                    ativo=True, criado_por_nome=ctx.usuario.nome)
    token = srv.novo_token(d)
    ctx.db.add(d)
    ctx.db.flush()
    ctx.auditar("criar", "acesso_dispositivo", d.id, f"Dispositivo {d.nome} ({dados.tipo}) cadastrado; token gerado (final {d.token_final})")
    ctx.db.commit()
    return _disp_out(ctx.db, d, token)


@router.patch("/dispositivos/{dispositivo_id:int}", response_model=sc.DispositivoOut)
def editar_dispositivo(dispositivo_id: int, dados: sc.DispositivoEditarIn, ctx: Ctx):
    d = _obter_disp(ctx, dispositivo_id)
    _validar_refs_disp(ctx, dados.unidade_id, dados.catraca_id)
    antes = snapshot(d)
    campos = dados.model_dump(exclude_unset=True)
    for k, v in campos.items():
        setattr(d, k, v)
    ctx.db.flush()
    ctx.auditar("editar", "acesso_dispositivo", d.id, f"Dispositivo {d.nome} alterado", antes={k: antes.get(k) for k in campos},
                depois={k: snapshot(d).get(k) for k in campos})
    ctx.db.commit()
    return _disp_out(ctx.db, d)


@router.post("/dispositivos/{dispositivo_id:int}/regenerar", response_model=sc.DispositivoComTokenOut)
def regenerar_dispositivo(dispositivo_id: int, ctx: Ctx):
    d = _obter_disp(ctx, dispositivo_id)
    token = srv.novo_token(d)
    d.ativo, d.revogado_em = True, None
    ctx.auditar("regenerar_token", "acesso_dispositivo", d.id, f"Token do dispositivo {d.nome} regenerado (final {d.token_final}); o anterior deixou de valer")
    ctx.db.commit()
    return _disp_out(ctx.db, d, token)


@router.post("/dispositivos/{dispositivo_id:int}/revogar", response_model=sc.DispositivoOut)
def revogar_dispositivo(dispositivo_id: int, ctx: Ctx):
    d = _obter_disp(ctx, dispositivo_id)
    d.ativo, d.revogado_em, d.token_hash = False, _agora(), None
    ctx.auditar("revogar", "acesso_dispositivo", d.id, f"Dispositivo {d.nome} revogado: o token deixou de valer")
    ctx.db.commit()
    return _disp_out(ctx.db, d)


@router.delete("/dispositivos/{dispositivo_id:int}", response_model=Mensagem)
def excluir_dispositivo(dispositivo_id: int, ctx: Ctx):
    d = _obter_disp(ctx, dispositivo_id)
    ctx.auditar("excluir", "acesso_dispositivo", d.id, f"Dispositivo {d.nome} excluído")
    ctx.db.delete(d)
    ctx.db.commit()
    return Mensagem(mensagem="Dispositivo excluído.")
