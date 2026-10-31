"""Rotas do Wellhub.

- `router` (`/api/wellhub/*`, protegido): ver = `integracoes.ver`; alterar = `integracoes.editar` (perfil Full).
- `router_publico`: webhook `POST /api/webhooks/wellhub` (autenticação própria: assinatura HMAC `X-Gympass-Signature`
  do corpo cru com o segredo cadastrado; sem assinatura válida nada é gravado).
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.db import agora as agora_utc
from app.core.db import get_db
from app.core.deps import Ctx
from app.core.permissoes import adicionar_regras
from app.domain.financeiro import hoje_de_negocio
from app.modules.agenda.models import Reserva
from app.modules.wellhub import eventos, grade, servico
from app.modules.wellhub import regras as r
from app.modules.wellhub import schemas as sc
from app.modules.wellhub.models import WellhubConfig

log = logging.getLogger(__name__)

adicionar_regras([
    ("GET", r"/wellhub(/|$)", "integracoes.ver"),
    ("*", r"/wellhub(/|$)", "integracoes.editar"),
])

router = APIRouter(prefix="/wellhub", tags=["wellhub"])
router_publico = APIRouter()

U = "/unidades/{unidade_id:int}"


# --------------------------------------------------------------------------------------------- configuração
@router.get("", response_model=sc.TelaOut)
def tela(ctx: Ctx):
    return servico.tela(ctx)


@router.put(U, response_model=sc.ConfigOut)
def salvar(unidade_id: int, dados: sc.ConfigIn, ctx: Ctx):
    return servico.salvar(ctx, unidade_id, dados)


@router.post(U + "/segredo-webhook", response_model=sc.SegredoGeradoOut)
def gerar_segredo(unidade_id: int, ctx: Ctx):
    """Gera um segredo novo (o anterior deixa de valer). O valor aparece só nesta resposta."""
    return servico.gerar_segredo_webhook(ctx, unidade_id)


@router.post(U + "/testar-conexao", response_model=sc.TesteOut)
def testar_conexao(unidade_id: int, ctx: Ctx):
    return servico.testar_conexao(ctx, unidade_id)


@router.post(U + "/testar-webhook", response_model=sc.TesteOut)
def testar_webhook(unidade_id: int, ctx: Ctx):
    return servico.testar_webhook(ctx, unidade_id)


@router.post(U + "/produtos", response_model=list[sc.ProdutoOut])
def produtos(unidade_id: int, ctx: Ctx):
    """POST de propósito: consulta o Wellhub (efeito externo) e só quem configura pode."""
    return servico.listar_produtos(ctx, unidade_id)


@router.put(U + "/mapeamentos", response_model=sc.ConfigOut)
def mapeamentos(unidade_id: int, dados: sc.MapeamentosIn, ctx: Ctx):
    return servico.salvar_mapeamentos(ctx, unidade_id, dados)


@router.post(U + "/grade/previa", response_model=sc.ResumoGradeOut)
def grade_previa(unidade_id: int, ctx: Ctx):
    return servico.publicar_grade(ctx, unidade_id, previa=True)


@router.post(U + "/grade/publicar", response_model=sc.ResumoGradeOut)
def grade_publicar(unidade_id: int, ctx: Ctx):
    return servico.publicar_grade(ctx, unidade_id, previa=False)


# --------------------------------------------------------------------------------------------- painel e relatório
@router.get(U + "/painel", response_model=sc.PainelOut)
def painel(unidade_id: int, ctx: Ctx):
    return servico.painel(ctx, unidade_id)


def _mes_padrao(ano: int | None, mes: int | None) -> tuple[int, int]:
    hoje = hoje_de_negocio(agora_utc())
    return ano or hoje.year, mes or hoje.month


@router.get("/relatorio", response_model=sc.RelatorioOut)
def relatorio(ctx: Ctx, ano: int | None = Query(None, ge=2020, le=2100), mes: int | None = Query(None, ge=1, le=12),
              unidade_id: int | None = Query(None, ge=1)):
    a, m = _mes_padrao(ano, mes)
    return servico.relatorio_mensal(ctx, ano=a, mes=m, unidade_id=unidade_id)


@router.get("/relatorio.csv")
def relatorio_csv(ctx: Ctx, ano: int | None = Query(None, ge=2020, le=2100), mes: int | None = Query(None, ge=1, le=12),
                  unidade_id: int | None = Query(None, ge=1)):
    a, m = _mes_padrao(ano, mes)
    texto = servico.relatorio_csv(ctx, ano=a, mes=m, unidade_id=unidade_id)
    return Response(texto, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="wellhub-checkins-{a}-{m:02d}.csv"'})


# --------------------------------------------------------------------------------------------- eventos
@router.get("/eventos", response_model=sc.ListaEventosOut)
def listar_eventos(ctx: Ctx,
                   resultado: str | None = Query(None, pattern="^(processado|cancelado|rejeitado|descartado|erro|pendente|ignorado)$"),
                   tipo: str | None = Query(None, max_length=40), q: str | None = Query(None, max_length=60),
                   unidade_id: int | None = Query(None, ge=1),
                   pagina: int = Query(1, ge=1), por_pagina: int = Query(25, ge=1, le=100)):
    return servico.listar_eventos(ctx, unidade_id=unidade_id, resultado=resultado, tipo=tipo, q=q, pagina=pagina,
                                  por_pagina=por_pagina)


@router.get("/eventos/{evento_id:int}", response_model=sc.EventoDetalheOut)
def detalhe_evento(evento_id: int, ctx: Ctx):
    return servico.detalhe_evento(ctx, evento_id)


@router.post("/eventos/{evento_id:int}/reprocessar", response_model=sc.ReprocessarOut)
def reprocessar(evento_id: int, ctx: Ctx):
    return servico.reprocessar_evento(ctx, evento_id)


@router.post("/eventos/{evento_id:int}/conferido", response_model=sc.EventoOut)
def conferido(evento_id: int, ctx: Ctx, desfazer: bool = Query(False)):
    return servico.ignorar_evento(ctx, evento_id, not desfazer)


# --------------------------------------------------------------------------------------------- check-in manual
@router.get("/alunos")
def buscar_alunos(ctx: Ctx, q: str = Query("", max_length=80)) -> list[dict]:
    return servico.buscar_alunos(ctx, q)


@router.post("/validar-checkin", response_model=sc.ValidacaoOut)
def validar_checkin(dados: sc.ValidarCheckinIn, ctx: Ctx):
    return servico.validar_checkin_manual(ctx, dados.aluno_id)


# --------------------------------------------------------------------------------------------- webhook
LIMITE_WEBHOOK_POR_IP = 300  # por minuto
LIMITE_FALHAS_WEBHOOK_POR_IP = 20  # por 5 minutos
TAMANHO_MAXIMO_WEBHOOK = 256 * 1024


async def _corpo_cru(request: Request) -> bytes:
    tamanho = request.headers.get("content-length")
    if tamanho and tamanho.isdigit() and int(tamanho) > TAMANHO_MAXIMO_WEBHOOK:
        raise HTTPException(413, "Payload grande demais.")
    corpo = await request.body()
    if len(corpo) > TAMANHO_MAXIMO_WEBHOOK:
        raise HTTPException(413, "Payload grande demais.")
    return corpo


def autenticar_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    corpo: Annotated[bytes, Depends(_corpo_cru)],
    x_gympass_signature: Annotated[str | None, Header(alias="X-Gympass-Signature")] = None,
) -> list[int]:
    """Assinatura OBRIGATÓRIA: HMAC-SHA1 do corpo cru com o segredo de cada configuração (tempo constante, sem curto-circuito).

    Devolve os ids das configurações cujo segredo confere. Falhas contam no rate limit e no alerta do painel."""
    ratelimit.verificar(request, "webhook-wellhub", LIMITE_WEBHOOK_POR_IP, 60, db=db)
    configs = list(db.scalars(select(WellhubConfig).where(WellhubConfig.webhook_secret_cifrado.is_not(None))))
    segredos = [(c, eventos.decifrar(c.webhook_secret_cifrado)) for c in configs]
    segredos = [(c, s) for c, s in segredos if s]
    if not segredos:
        raise HTTPException(403, "Webhook do Wellhub não configurado: cadastre o segredo em Configurações > Integrações.")
    if not x_gympass_signature:
        ratelimit.verificar(request, "webhook-wellhub-falha", LIMITE_FALHAS_WEBHOOK_POR_IP, 300, db=db)
        raise HTTPException(401, "Assinatura ausente.")
    conferem = [c.id for c, s in segredos if r.assinatura_confere(s, corpo, x_gympass_signature)]
    if not conferem:
        ratelimit.verificar(request, "webhook-wellhub-falha", LIMITE_FALHAS_WEBHOOK_POR_IP, 300, db=db)
        _contar_falha(db, corpo, [c for c, _ in segredos])
        raise HTTPException(403, "Assinatura inválida.")
    return conferem


def _contar_falha(db: Session, corpo: bytes, configs: list[WellhubConfig]) -> None:
    """Registra a falha na configuração do gym citado no corpo (se der para saber) para o alerta do painel."""
    try:
        gym = r.gym_id(json.loads(corpo)) if corpo else ""
    except (ValueError, AttributeError):
        gym = ""
    alvo = [c for c in configs if gym and c.gym_id == gym] or (configs if len(configs) == 1 else [])
    agora = agora_utc()
    for c in alvo:
        recente = c.falha_assinatura_em and (agora - c.falha_assinatura_em).total_seconds() < 86400
        c.falhas_assinatura = (c.falhas_assinatura or 0) + 1 if recente else 1
        c.falha_assinatura_em = agora
    if alvo:
        db.commit()


@router_publico.post("/webhooks/wellhub", tags=["wellhub (webhook)"])
def webhook_wellhub(
    db: Annotated[Session, Depends(get_db)],
    config_ids: Annotated[list[int], Depends(autenticar_webhook)],
    corpo: Annotated[bytes, Depends(_corpo_cru)],
):
    try:
        payload = json.loads(corpo)
    except ValueError:
        return JSONResponse({"detail": "JSON inválido."}, status_code=422)
    if not isinstance(payload, dict):
        return JSONResponse({"detail": "O corpo precisa ser um objeto JSON."}, status_code=422)
    configs = list(db.scalars(select(WellhubConfig).where(WellhubConfig.id.in_(config_ids)).order_by(WellhubConfig.id)))
    gym = r.gym_id(payload)
    cfg = next((c for c in configs if gym and c.gym_id == gym), None)
    if cfg is None and len(configs) == 1 and (not gym or not configs[0].gym_id):
        cfg = configs[0]
    if cfg is None and len(configs) == 1 and gym and configs[0].gym_id != gym:
        return JSONResponse({"detail": "O gym do evento não é o desta unidade."}, status_code=400)
    if cfg is None:
        return JSONResponse({"detail": "Não foi possível identificar a unidade (gym) do evento."}, status_code=400)
    if not cfg.ativo:
        return JSONResponse({"ok": True, "aviso": "Integração desativada."}, status_code=202)
    res = eventos.processar(db, cfg, payload, origem="webhook")
    if res.resultado in ("processado", "cancelado") and res.reserva_id             and r.tipo_do_evento(payload) in (r.RESERVA_PEDIDA, r.RESERVA_CANCELADA, r.RESERVA_CANCELADA_TARDE):
        reserva = db.get(Reserva, res.reserva_id)
        if reserva is not None:
            grade.atualizar_vagas_do_slot(db, cfg, reserva.aula_sessao_id)  # melhor esforço
    if res.resultado == "duplicado":
        return {"ok": True, "duplicado": True, "evento_id": res.evento_id}
    if res.resultado == "descartado":
        return JSONResponse({"ok": True, "descartado": res.mensagem, "evento_id": res.evento_id}, status_code=202)
    if res.resultado == "erro":
        # 200 de propósito: o evento ficou registrado e é reprocessado pela tela; um 4xx/5xx faria o Wellhub repetir à toa
        return {"ok": False, "evento_id": res.evento_id, "resultado": "erro", "erro": res.mensagem}
    return {"ok": True, "evento_id": res.evento_id, "resultado": res.resultado, "reserva_id": res.reserva_id}
