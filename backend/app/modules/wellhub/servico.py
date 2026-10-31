"""Regras de aplicação das telas do Wellhub (todas recebem o `Contexto`) e a função estável para outros módulos.

ESTÁVEL para o módulo de controle de acesso:
    `validar_checkin(db, aluno_id) -> ResultadoValidacao`  (ver `eventos.validar_checkin`)

Segredos: cifrados, somente escrita; a auditoria registra QUE mudou, nunca o valor.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.core import audit
from app.core.db import agora as agora_utc
from app.core.deps import Contexto
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import TipoServico, Unidade
from app.modules.wellhub import cliente as cli
from app.modules.wellhub import eventos, grade, relatorio
from app.modules.wellhub import regras as r
from app.modules.wellhub import schemas as sc
from app.modules.wellhub.cliente import ErroWellhub
from app.modules.wellhub.eventos import ResultadoValidacao, validar_checkin  # noqa: F401  (API estável)
from app.modules.wellhub.models import (
    WellhubAluno,
    WellhubConfig,
    WellhubEvento,
    WellhubMapeamento,
    WellhubSlot,
)

WEBHOOK_CAMINHO = "/api/webhooks/wellhub"
CAMPOS_PUBLICOS = ("ativo", "ambiente", "gym_id", "criar_aluno_automatico", "validar_checkin_automatico",
                   "servico_padrao_id", "valor_repasse_checkin", "sync_ativo", "sync_dias")
SEGREDOS = ("api_key", "webhook_secret")


def erro(codigo: int, mensagem: str) -> HTTPException:
    return HTTPException(codigo, mensagem)


# ------------------------------------------------------------------------------------------------ configuração
def _seg(valor: str | None) -> sc.SegredoOut:
    return sc.SegredoOut(definido=bool(valor), final=eventos.final_do_segredo(valor))


def _mapeamentos_out(ctx: Contexto, c: WellhubConfig | None) -> list[sc.MapeamentoOut]:
    if c is None:
        return []
    nomes = {s.id: s.nome for s in ctx.db.scalars(select(TipoServico))}
    contagem = dict(ctx.db.execute(select(WellhubSlot.mapeamento_id, func.count()).where(WellhubSlot.situacao == "publicado")
                                   .group_by(WellhubSlot.mapeamento_id)).all())
    return [sc.MapeamentoOut(id=m.id, tipo_servico_id=m.tipo_servico_id, servico_nome=nomes.get(m.tipo_servico_id, "?"),
                             product_id=m.product_id, class_id=m.class_id, nome_classe=m.nome_classe, descricao=m.descricao,
                             ativo=m.ativo, slots_publicados=contagem.get(m.id, 0))
            for m in ctx.db.scalars(select(WellhubMapeamento).where(WellhubMapeamento.config_id == c.id)
                                    .order_by(WellhubMapeamento.id))]


def config_out(ctx: Contexto, u: Unidade, c: WellhubConfig | None) -> sc.ConfigOut:
    return sc.ConfigOut(
        unidade_id=u.id, unidade_nome=u.nome, configurada=c is not None, ativo=bool(c and c.ativo),
        ambiente=(c.ambiente if c else "sandbox"), gym_id=c.gym_id if c else None,
        criar_aluno_automatico=c.criar_aluno_automatico if c else True,
        validar_checkin_automatico=bool(c and c.validar_checkin_automatico),
        servico_padrao_id=c.servico_padrao_id if c else None, valor_repasse_checkin=c.valor_repasse_checkin if c else None,
        sync_ativo=bool(c and c.sync_ativo), sync_dias=c.sync_dias if c else 7,
        sync_ultimo_em=c.sync_ultimo_em if c else None, sync_ultimo_resumo=c.sync_ultimo_resumo if c else None,
        sync_ultimo_ok=c.sync_ultimo_ok if c else None, teste_ultimo_em=c.teste_ultimo_em if c else None,
        teste_ultimo_ok=c.teste_ultimo_ok if c else None,
        api_key=_seg(c.api_key_cifrado if c else None), webhook_secret=_seg(c.webhook_secret_cifrado if c else None),
        mapeamentos=_mapeamentos_out(ctx, c),
    )


def tela(ctx: Contexto) -> sc.TelaOut:
    db = ctx.db
    unidades = list(db.scalars(select(Unidade).where(Unidade.ativo.is_(True)).order_by(Unidade.nome, Unidade.id)))
    configs = {c.unidade_id: c for c in db.scalars(select(WellhubConfig))}
    servicos = db.scalars(select(TipoServico).where(TipoServico.ativo.is_(True)).order_by(TipoServico.nome))
    return sc.TelaOut(webhook_caminho=WEBHOOK_CAMINHO, configuracoes=[config_out(ctx, u, configs.get(u.id)) for u in unidades],
                      servicos=[sc.ServicoOpcao(id=s.id, nome=s.nome) for s in servicos])


def config_da_unidade(ctx: Contexto, unidade_id: int, *, criar: bool = False) -> tuple[Unidade, WellhubConfig | None]:
    u = ctx.db.get(Unidade, unidade_id)
    if u is None:
        raise erro(404, "Unidade não encontrada.")
    c = ctx.db.scalar(select(WellhubConfig).where(WellhubConfig.unidade_id == unidade_id))
    if c is None and criar:
        c = WellhubConfig(unidade_id=unidade_id, ativo=False, ambiente="sandbox", criar_aluno_automatico=True,
                          validar_checkin_automatico=False, sync_ativo=False, sync_dias=7, falhas_assinatura=0)
        ctx.db.add(c)
        ctx.db.flush()
    return u, c


def _exigir(ctx: Contexto, unidade_id: int) -> tuple[Unidade, WellhubConfig]:
    u, c = config_da_unidade(ctx, unidade_id)
    if c is None:
        raise erro(409, "Salve a configuração do Wellhub desta unidade primeiro.")
    return u, c


def _fotografia(c: WellhubConfig) -> dict:
    snap = {k: (str(v) if isinstance(v, Decimal) else v) for k in CAMPOS_PUBLICOS for v in [getattr(c, k)]}
    snap.update({f"{k}_definido": bool(getattr(c, f"{k}_cifrado")) for k in SEGREDOS})
    return snap


def salvar(ctx: Contexto, unidade_id: int, dados: sc.ConfigIn) -> sc.ConfigOut:
    u, c = config_da_unidade(ctx, unidade_id, criar=True)
    assert c is not None
    antes = _fotografia(c)
    enviados = dados.model_fields_set
    if "servico_padrao_id" in enviados and dados.servico_padrao_id is not None \
            and ctx.db.get(TipoServico, dados.servico_padrao_id) is None:
        raise erro(422, "Serviço padrão não encontrado.")
    for campo in CAMPOS_PUBLICOS:
        if campo in enviados and (getattr(dados, campo) is not None or campo in ("servico_padrao_id", "valor_repasse_checkin",
                                                                                  "gym_id")):
            valor = getattr(dados, campo)
            if campo == "gym_id":
                valor = (valor or "").strip() or None
            setattr(c, campo, valor)
    if "gym_id" in enviados and c.gym_id:
        outro = ctx.db.scalar(select(WellhubConfig).where(WellhubConfig.gym_id == c.gym_id, WellhubConfig.id != c.id))
        if outro is not None:
            raise erro(409, "Este gym id já está em outra unidade.")
    alterados = []
    for nome in SEGREDOS:
        novo = (getattr(dados, nome) or "").strip()
        if nome in dados.limpar:
            setattr(c, f"{nome}_cifrado", None)
            alterados.append(f"{nome}: removido")
        elif novo:
            if nome == "webhook_secret" and len(novo) < 16:
                raise erro(422, "O segredo do webhook precisa ter ao menos 16 caracteres.")
            setattr(c, f"{nome}_cifrado", eventos.cifrar(novo))
            alterados.append(f"{nome}: alterado")
            if nome == "api_key":
                c.teste_ultimo_ok, c.teste_ultimo_em = None, None  # credencial nova: precisa testar de novo
    if "ambiente" in enviados or "gym_id" in enviados:
        if antes["ambiente"] != c.ambiente or antes["gym_id"] != c.gym_id:
            c.teste_ultimo_ok, c.teste_ultimo_em = None, None
    if c.sync_ativo and not (c.api_key_cifrado and c.gym_id):
        raise erro(422, "Para ligar a publicação automática da grade, cadastre o gym id e a chave de API.")
    if c.ativo and not c.webhook_secret_cifrado:
        raise erro(422, "Para ativar a integração, cadastre o segredo do webhook (sem ele nenhuma chamada é aceita).")
    ctx.db.flush()
    a, d = audit.diff(antes, _fotografia(c))
    ctx.auditar("wellhub.configurar", "wellhub_config", c.id, antes=a, depois=d,
                descricao=f"Wellhub da unidade {u.nome}" + (f" ({'; '.join(alterados)})" if alterados else ""))
    ctx.db.commit()
    return config_out(ctx, u, c)


def gerar_segredo_webhook(ctx: Contexto, unidade_id: int) -> sc.SegredoGeradoOut:
    u, c = config_da_unidade(ctx, unidade_id, criar=True)
    assert c is not None
    valor = "whs_" + secrets.token_urlsafe(32)
    c.webhook_secret_cifrado = eventos.cifrar(valor)
    ctx.auditar("wellhub.gerar_segredo_webhook", "wellhub_config", c.id,
                descricao=f"Novo segredo do webhook gerado para a unidade {u.nome} (final {valor[-4:]})")
    ctx.db.commit()
    return sc.SegredoGeradoOut(valor=valor, final=valor[-4:])


# ------------------------------------------------------------------------------------------------ testes (assistente)
def testar_conexao(ctx: Contexto, unidade_id: int) -> sc.TesteOut:
    u, c = _exigir(ctx, unidade_id)
    try:
        n = eventos.testar_conexao(c)
    except ErroWellhub as e:
        c.teste_ultimo_ok, c.teste_ultimo_em = False, agora_utc()
        ctx.auditar("wellhub.testar_conexao", "wellhub_config", c.id, descricao=f"Teste de conexão falhou ({u.nome})")
        ctx.db.commit()
        raise erro(502, str(e)) from None
    c.teste_ultimo_ok, c.teste_ultimo_em = True, agora_utc()
    ctx.auditar("wellhub.testar_conexao", "wellhub_config", c.id, descricao=f"Teste de conexão OK ({u.nome})")
    ctx.db.commit()
    amb = "produção" if c.ambiente == "producao" else "sandbox"
    return sc.TesteOut(ok=True, mensagem=f"Conexão com o Wellhub ({amb}) OK: a chave foi aceita. {n} classe(s) no gym.",
                       detalhes={"classes": n})


def testar_webhook(ctx: Contexto, unidade_id: int) -> sc.TesteOut:
    """Assina um evento de exemplo com o segredo salvo e confere pelo MESMO código do webhook (sem rede)."""
    _, c = _exigir(ctx, unidade_id)
    segredo = eventos.decifrar(c.webhook_secret_cifrado)
    if not segredo:
        raise erro(422, "Cadastre o segredo do webhook antes de testar.")
    corpo = b'{"event_type":"checkin","event_data":{"user":{"unique_token":"0000000000000"},"teste":true}}'
    assinatura = r.assinar(segredo, corpo)
    ok = r.assinatura_confere(segredo, corpo, assinatura) and not r.assinatura_confere(segredo, corpo + b" ", assinatura)
    return sc.TesteOut(ok=ok, mensagem=("Segredo salvo e verificação da assinatura (X-Gympass-Signature) funcionando. "
                                        "Cadastre o endereço e o mesmo segredo no Wellhub.") if ok else
                       "A verificação da assinatura falhou.", detalhes={"cabecalho": "X-Gympass-Signature",
                                                                         "algoritmo": "HMAC-SHA1 (hex maiúsculo)"})


def listar_produtos(ctx: Contexto, unidade_id: int) -> list[sc.ProdutoOut]:
    _, c = _exigir(ctx, unidade_id)
    cl = None
    try:
        cl = eventos.cliente_da_config(c)
        itens = cl.listar_produtos()
    except ErroWellhub as e:
        raise erro(502, str(e)) from None
    except Exception as exc:  # noqa: BLE001
        raise erro(502, str(cli.traduzir_http(exc, "Busca de produtos"))) from None
    finally:
        if cl is not None:
            cl.fechar()
    saida = []
    for p in itens:
        pid = str(p.get("product_id") or p.get("id") or "").strip()
        if pid:
            saida.append(sc.ProdutoOut(id=pid[:40], nome=str(p.get("name") or p.get("description") or pid)[:150]))
    return saida


def salvar_mapeamentos(ctx: Contexto, unidade_id: int, dados: sc.MapeamentosIn) -> sc.ConfigOut:
    u, c = config_da_unidade(ctx, unidade_id, criar=True)
    assert c is not None
    ids = [i.tipo_servico_id for i in dados.itens]
    if len(ids) != len(set(ids)):
        raise erro(422, "Cada serviço só pode aparecer uma vez no mapeamento.")
    existentes = {s.id for s in ctx.db.scalars(select(TipoServico).where(TipoServico.id.in_(ids or [0])))}
    if set(ids) - existentes:
        raise erro(422, "Serviço não encontrado.")
    atuais = {m.tipo_servico_id: m for m in ctx.db.scalars(select(WellhubMapeamento).where(WellhubMapeamento.config_id == c.id))}
    mudancas = []
    for item in dados.itens:
        m = atuais.pop(item.tipo_servico_id, None)
        produto = (item.product_id or "").strip() or None
        if m is None:
            m = WellhubMapeamento(config_id=c.id, tipo_servico_id=item.tipo_servico_id)
            ctx.db.add(m)
            mudancas.append(f"+{item.tipo_servico_id}")
        elif m.product_id != produto:
            mudancas.append(f"~{item.tipo_servico_id}")  # a classe já publicada é atualizada na próxima publicação
        m.product_id, m.nome_classe, m.descricao, m.ativo = produto, (item.nome_classe or "").strip() or None, \
            (item.descricao or "").strip() or None, item.ativo
    for m in atuais.values():  # serviço tirado da lista: desativa (mantém histórico de horários publicados)
        if m.ativo:
            m.ativo = False
            mudancas.append(f"-{m.tipo_servico_id}")
    ctx.db.flush()
    ctx.auditar("wellhub.mapear", "wellhub_config", c.id,
                descricao=f"Mapeamento de serviços do Wellhub ({u.nome}): {len(dados.itens)} serviço(s)",
                depois={"mudancas": mudancas})
    ctx.db.commit()
    return config_out(ctx, u, c)


def publicar_grade(ctx: Contexto, unidade_id: int, *, previa: bool) -> sc.ResumoGradeOut:
    u, c = _exigir(ctx, unidade_id)
    try:
        resumo = grade.sincronizar_grade(ctx.db, c, previa=previa)
    except ErroWellhub as e:
        if not previa:
            grade.registrar_sync(ctx.db, c, f"Erro: {e}", False)
        raise erro(502 if not previa or "mapeamento" not in str(e) else 422, str(e)) from None
    texto = grade.resumo_texto(resumo)
    if not previa:
        grade.registrar_sync(ctx.db, c, texto, resumo["erros"] == 0)
        ctx.auditar("wellhub.publicar_grade", "wellhub_config", c.id, descricao=f"Grade publicada ({u.nome}): {texto}")
        ctx.db.commit()
    return sc.ResumoGradeOut(resumo=texto, **resumo)


# ------------------------------------------------------------------------------------------------ eventos
def _nomes(ctx: Contexto, evs: list[WellhubEvento]) -> tuple[dict, dict]:
    alunos = {a.id: a.nome for a in ctx.db.scalars(select(Aluno).where(Aluno.id.in_({e.aluno_id for e in evs if e.aluno_id} or {0})))}
    cfgs = {c.id: c.unidade_id for c in ctx.db.scalars(select(WellhubConfig))}
    unidades = {u.id: u.nome for u in ctx.db.scalars(select(Unidade))}
    return alunos, {cid: unidades.get(uid) for cid, uid in cfgs.items()}


def evento_out(e: WellhubEvento, alunos: dict, unidades: dict, *, detalhe: bool = False):
    base = dict(
        id=e.id, recebido_em=e.recebido_em, processado_em=e.processado_em, tipo=e.tipo,
        tipo_rotulo=r.ROTULO_TIPO.get(e.tipo, e.tipo), unidade_nome=unidades.get(e.config_id),
        gympass_mascarado=r.mascarar_gympass(e.gympass_id), booking_number=e.booking_number, slot_id=e.slot_id,
        aluno_id=e.aluno_id, aluno_nome=alunos.get(e.aluno_id), resultado=e.resultado, erro=e.erro,
        tentativas=e.tentativas or 0, origem=e.origem, reserva_id=e.reserva_id, ignorado=bool(e.ignorado),
        pode_reprocessar=e.resultado in ("erro", "pendente"),
    )
    if detalhe:
        return sc.EventoDetalheOut(**base, payload=_payload_seguro(e.payload))
    return sc.EventoOut(**base)


def _payload_seguro(p) -> dict | None:
    """Mostra o payload com e-mail/telefone/documento mascarados (LGPD)."""
    if not isinstance(p, dict):
        return None

    def limpar(v, chave=""):
        if isinstance(v, dict):
            return {k: limpar(x, k) for k, x in v.items()}
        if isinstance(v, list):
            return [limpar(x) for x in v]
        if chave in ("email", "phone", "phone_number", "document", "cpf", "document_number") and v:
            s = str(v)
            return "•" * max(len(s) - 3, 0) + s[-3:]
        if chave in ("unique_token", "gympass_id") and v:
            return r.mascarar_gympass(str(v))
        return v

    return limpar(p)


def listar_eventos(ctx: Contexto, *, unidade_id: int | None, resultado: str | None, tipo: str | None, q: str | None,
                   pagina: int, por_pagina: int) -> sc.ListaEventosOut:
    consulta = select(WellhubEvento)
    if unidade_id:
        consulta = consulta.join(WellhubConfig, WellhubConfig.id == WellhubEvento.config_id).where(
            WellhubConfig.unidade_id == unidade_id)
    if resultado == "erro":
        consulta = consulta.where(WellhubEvento.resultado == "erro", WellhubEvento.ignorado.is_(False))
    elif resultado == "ignorado":
        consulta = consulta.where(WellhubEvento.ignorado.is_(True))
    elif resultado:
        consulta = consulta.where(WellhubEvento.resultado == resultado)
    if tipo:
        consulta = consulta.where(WellhubEvento.tipo == tipo)
    if q and q.strip():
        termo = q.strip()
        consulta = consulta.where(or_(WellhubEvento.booking_number == termo, WellhubEvento.gympass_id == termo,
                                      WellhubEvento.slot_id == termo))
    total = ctx.db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    itens = list(ctx.db.scalars(consulta.order_by(WellhubEvento.recebido_em.desc(), WellhubEvento.id.desc())
                                .offset((pagina - 1) * por_pagina).limit(por_pagina)))
    alunos, unidades = _nomes(ctx, itens)
    return sc.ListaEventosOut(total=total, pagina=pagina, por_pagina=por_pagina,
                              itens=[evento_out(e, alunos, unidades) for e in itens])


def _evento(ctx: Contexto, evento_id: int) -> WellhubEvento:
    e = ctx.db.get(WellhubEvento, evento_id)
    if e is None:
        raise erro(404, "Evento não encontrado.")
    return e


def detalhe_evento(ctx: Contexto, evento_id: int) -> sc.EventoDetalheOut:
    e = _evento(ctx, evento_id)
    alunos, unidades = _nomes(ctx, [e])
    return evento_out(e, alunos, unidades, detalhe=True)


def reprocessar_evento(ctx: Contexto, evento_id: int) -> sc.ReprocessarOut:
    e = _evento(ctx, evento_id)
    if e.resultado not in ("erro", "pendente"):
        raise erro(409, "Só eventos com erro ou pendentes podem ser reprocessados.")
    try:
        res = eventos.reprocessar(ctx.db, e)
    except ErroWellhub as exc:
        raise erro(409, str(exc)) from None
    e = ctx.db.get(WellhubEvento, evento_id)
    if res.resultado in r.RESULTADOS_FINAIS:
        e.ignorado = False
    ctx.auditar("wellhub.reprocessar_evento", "wellhub_evento", e.id,
                descricao=f"Evento {r.ROTULO_TIPO.get(e.tipo, e.tipo)} reprocessado: {res.resultado}")
    ctx.db.commit()
    alunos, unidades = _nomes(ctx, [e])
    return sc.ReprocessarOut(resultado=res.resultado, mensagem=res.mensagem, evento=evento_out(e, alunos, unidades))


def ignorar_evento(ctx: Contexto, evento_id: int, ignorar: bool) -> sc.EventoOut:
    e = _evento(ctx, evento_id)
    if e.resultado != "erro":
        raise erro(409, "Só eventos com erro podem ser marcados como conferidos.")
    e.ignorado = ignorar
    ctx.auditar("wellhub.ignorar_evento", "wellhub_evento", e.id,
                descricao=("Erro marcado como conferido" if ignorar else "Erro voltou para os alertas") + f" (evento {e.id})")
    ctx.db.commit()
    alunos, unidades = _nomes(ctx, [e])
    return evento_out(e, alunos, unidades)


# ------------------------------------------------------------------------------------------------ painel e relatório
def painel(ctx: Contexto, unidade_id: int, agora: datetime | None = None) -> sc.PainelOut:
    u, c = config_da_unidade(ctx, unidade_id)
    dados = relatorio.painel(ctx.db, c, agora=agora)
    ultimos = list(ctx.db.scalars(select(WellhubEvento).where(WellhubEvento.config_id == (c.id if c else 0))
                                  .order_by(WellhubEvento.recebido_em.desc(), WellhubEvento.id.desc()).limit(6)))
    alunos, unidades = _nomes(ctx, ultimos)
    return sc.PainelOut(unidade_id=u.id, unidade_nome=u.nome, configurada=c is not None, ativo=bool(c and c.ativo),
                        ambiente=c.ambiente if c else "sandbox", ultimos_eventos=[evento_out(e, alunos, unidades) for e in ultimos],
                        **dados)


def relatorio_mensal(ctx: Contexto, *, ano: int, mes: int, unidade_id: int | None) -> sc.RelatorioOut:
    return sc.RelatorioOut(**relatorio.relatorio_mensal(ctx.db, ano=ano, mes=mes, unidade_id=unidade_id))


def relatorio_csv(ctx: Contexto, *, ano: int, mes: int, unidade_id: int | None) -> str:
    ctx.auditar("wellhub.exportar_relatorio", "wellhub_checkin", None, descricao=f"Relatório Wellhub {mes:02d}/{ano} exportado")
    ctx.db.commit()
    return relatorio.relatorio_csv(ctx.db, ano=ano, mes=mes, unidade_id=unidade_id)


# ------------------------------------------------------------------------------------------------ check-in manual
def buscar_alunos(ctx: Contexto, q: str) -> list[dict]:
    termo = (q or "").strip()
    consulta = select(Aluno, WellhubAluno.gympass_id).join(WellhubAluno, WellhubAluno.aluno_id == Aluno.id)
    if termo:
        like = "%" + termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        consulta = consulta.where(or_(Aluno.nome.ilike(like, escape="\\"), WellhubAluno.gympass_id == termo))
    return [{"aluno_id": a.id, "nome": a.nome, "gympass_id": r.mascarar_gympass(g)}
            for a, g in ctx.db.execute(consulta.order_by(Aluno.nome).limit(10)).all()]


def validar_checkin_manual(ctx: Contexto, aluno_id: int) -> sc.ValidacaoOut:
    if ctx.db.get(Aluno, aluno_id) is None:
        raise erro(404, "Aluno não encontrado.")
    res = validar_checkin(ctx.db, aluno_id)
    ctx.auditar("wellhub.validar_checkin_manual", "aluno", aluno_id,
                descricao=f"Validação manual de check-in Wellhub: {'OK' if res.ok else 'recusada'}")
    ctx.db.commit()
    return sc.ValidacaoOut(aplicavel=res.aplicavel, ok=res.ok, mensagem=res.mensagem, ja_validado=res.ja_validado)
