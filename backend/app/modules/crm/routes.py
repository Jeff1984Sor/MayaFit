"""Rotas do CRM de vendas: funil (Kanban), leads, interações, aula experimental, conversão em aluno, tarefas,
configurações (etapas e motivos de perda) e relatório. Todas em "crm.*": GET=ver, DELETE=excluir, demais=editar."""

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Query, status

from app.core.deps import Ctx
from app.core.permissoes import adicionar_regras
from app.core.schemas import Mensagem
from app.modules.crm import schemas as sc
from app.modules.crm import servico
from app.modules.crm.models import CrmEtapa, CrmMotivoPerda, OrigemLead

router = APIRouter(prefix="/crm", tags=["crm"])

adicionar_regras([("*", r"/crm", "crm.*")])


# ------------------------------------------------------------------------------------------------ painel
@router.get("/resumo", response_model=sc.Resumo)
def resumo(ctx: Ctx):
    """Indicadores do topo do funil e a frase de destaque do dia."""
    return servico.resumo(ctx)


@router.get("/opcoes", response_model=sc.Opcoes)
def opcoes(ctx: Ctx):
    return servico.opcoes(ctx)


@router.get("/funil", response_model=sc.Funil)
def funil(
    ctx: Ctx, q: str = Query("", max_length=100), responsavel_id: int | None = None, origem: OrigemLead | None = None,
    dias_encerrados: int = Query(30, ge=1, le=365),
):
    """Kanban: leads abertos de cada etapa e os ganhos/perdidos dos últimos `dias_encerrados` dias."""
    return servico.funil(ctx, q=q, responsavel_id=responsavel_id, origem=origem, dias_encerrados=dias_encerrados)


# ------------------------------------------------------------------------------------------------ leads
@router.get("/leads", response_model=sc.ListaLeads)
def listar(
    ctx: Ctx,
    q: str = Query("", max_length=100),
    situacao: Literal["abertos", "ganhos", "perdidos", "todos"] = "abertos",
    etapa_id: int | None = None,
    origem: OrigemLead | None = None,
    responsavel_id: int | None = None,
    tag: str | None = Query(None, max_length=30),
    ordem: Literal["recentes", "antigos", "nome", "valor", "contato"] = "recentes",
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=100),
):
    return servico.listar(ctx, q=q, situacao=situacao, etapa_id=etapa_id, origem=origem, responsavel_id=responsavel_id,
                          tag=tag, ordem=ordem, pagina=pagina, por_pagina=por_pagina)


@router.post("/leads", response_model=sc.LeadFicha, status_code=status.HTTP_201_CREATED)
def criar(dados: sc.LeadIn, ctx: Ctx):
    return servico.ficha(ctx, servico.criar_lead_equipe(ctx, dados))


@router.get("/leads/{lead_id}", response_model=sc.LeadFicha)
def ler(lead_id: int, ctx: Ctx):
    return servico.ficha(ctx, servico.obter_lead(ctx, lead_id))


@router.put("/leads/{lead_id}", response_model=sc.LeadFicha)
def atualizar(lead_id: int, dados: sc.LeadIn, ctx: Ctx):
    lead = servico.obter_lead(ctx, lead_id)
    return servico.ficha(ctx, servico.atualizar_lead(ctx, lead, dados))


@router.delete("/leads/{lead_id}", response_model=Mensagem)
def excluir(lead_id: int, ctx: Ctx):
    servico.excluir_lead(ctx, servico.obter_lead(ctx, lead_id))
    return Mensagem(mensagem="Lead excluído.")


@router.post("/leads/{lead_id}/mover", response_model=sc.LeadFicha)
def mover(lead_id: int, dados: sc.MoverIn, ctx: Ctx):
    lead = servico.obter_lead(ctx, lead_id)
    return servico.ficha(ctx, servico.mover(ctx, lead, dados))


@router.post("/leads/{lead_id}/reabrir", response_model=sc.LeadFicha)
def reabrir(lead_id: int, ctx: Ctx):
    return servico.ficha(ctx, servico.reabrir(ctx, servico.obter_lead(ctx, lead_id)))


@router.post("/leads/{lead_id}/interacoes", response_model=sc.LeadFicha, status_code=status.HTTP_201_CREATED)
def registrar_interacao(lead_id: int, dados: sc.InteracaoIn, ctx: Ctx):
    lead = servico.obter_lead(ctx, lead_id)
    servico.registrar_interacao(ctx, lead, dados)
    return servico.ficha(ctx, lead)


@router.delete("/leads/{lead_id}/interacoes/{interacao_id}", response_model=Mensagem)
def excluir_interacao(lead_id: int, interacao_id: int, ctx: Ctx):
    servico.excluir_interacao(ctx, servico.obter_lead(ctx, lead_id), interacao_id)
    return Mensagem(mensagem="Interação excluída.")


@router.post("/leads/{lead_id}/aula-experimental", response_model=sc.LeadFicha)
def agendar_aula(lead_id: int, dados: sc.AulaExperimentalIn, ctx: Ctx):
    lead = servico.obter_lead(ctx, lead_id)
    return servico.ficha(ctx, servico.agendar_aula_experimental(ctx, lead, dados))


@router.post("/leads/{lead_id}/aula-experimental/resultado", response_model=sc.LeadFicha)
def resultado_aula(lead_id: int, dados: sc.ResultadoAulaIn, ctx: Ctx):
    lead = servico.obter_lead(ctx, lead_id)
    return servico.ficha(ctx, servico.resultado_aula_experimental(ctx, lead, dados))


@router.get("/leads/{lead_id}/conversao", response_model=sc.PreparoConversao)
def preparo_conversao(lead_id: int, ctx: Ctx):
    """Unidades e alunos parecidos (mesmo telefone, e-mail ou nome) para converter sem duplicar."""
    return servico.preparo_conversao(ctx, servico.obter_lead(ctx, lead_id))


@router.post("/leads/{lead_id}/converter", response_model=sc.ConverterOut)
def converter(lead_id: int, dados: sc.ConverterIn, ctx: Ctx):
    """Cria o aluno (exige também alunos.editar) ou vincula a um aluno existente, e marca o lead como Matriculado."""
    return servico.converter(ctx, servico.obter_lead(ctx, lead_id), dados)


# ------------------------------------------------------------------------------------------------ tarefas
@router.get("/tarefas", response_model=sc.ListaTarefas)
def listar_tarefas(
    ctx: Ctx,
    escopo: Literal["minhas", "todas"] = "minhas",
    situacao: Literal["hoje", "atrasadas", "pendentes", "concluidas"] = "hoje",
    lead_id: int | None = None,
):
    """`hoje` = vencem até o fim do dia (inclui as atrasadas). `minhas` = do usuário ou sem responsável."""
    return servico.listar_tarefas(ctx, escopo=escopo, situacao=situacao, lead_id=lead_id)


@router.post("/tarefas", response_model=sc.TarefaOut, status_code=status.HTTP_201_CREATED)
def criar_tarefa(dados: sc.TarefaIn, ctx: Ctx):
    t = servico.criar_tarefa(ctx, dados)
    return servico._tarefas_out(ctx.db, [t])[0]


@router.put("/tarefas/{tarefa_id}", response_model=sc.TarefaOut)
def editar_tarefa(tarefa_id: int, dados: sc.TarefaIn, ctx: Ctx):
    t = servico.editar_tarefa(ctx, servico.obter_tarefa(ctx, tarefa_id), dados)
    return servico._tarefas_out(ctx.db, [t])[0]


@router.post("/tarefas/{tarefa_id}/concluir", response_model=sc.TarefaOut)
def concluir_tarefa(tarefa_id: int, ctx: Ctx):
    t = servico.concluir_tarefa(ctx, servico.obter_tarefa(ctx, tarefa_id), True)
    return servico._tarefas_out(ctx.db, [t])[0]


@router.post("/tarefas/{tarefa_id}/reabrir", response_model=sc.TarefaOut)
def reabrir_tarefa(tarefa_id: int, ctx: Ctx):
    t = servico.concluir_tarefa(ctx, servico.obter_tarefa(ctx, tarefa_id), False)
    return servico._tarefas_out(ctx.db, [t])[0]


@router.delete("/tarefas/{tarefa_id}", response_model=Mensagem)
def excluir_tarefa(tarefa_id: int, ctx: Ctx):
    servico.excluir_tarefa(ctx, servico.obter_tarefa(ctx, tarefa_id))
    return Mensagem(mensagem="Tarefa excluída.")


# ------------------------------------------------------------------------------------------------ configurações
def _etapa(ctx, etapa_id: int) -> CrmEtapa:
    return servico._obter_etapa(ctx.db, etapa_id)


def _motivo(ctx, motivo_id: int) -> CrmMotivoPerda:
    m = ctx.db.get(CrmMotivoPerda, motivo_id)
    if not m:
        raise servico.erro(404, "Motivo não encontrado.")
    return m


@router.get("/etapas", response_model=list[sc.EtapaOut])
def listar_etapas(ctx: Ctx):
    return servico.listar_etapas(ctx)


@router.post("/etapas", response_model=sc.EtapaOut, status_code=status.HTTP_201_CREATED)
def criar_etapa(dados: sc.EtapaIn, ctx: Ctx):
    return servico.etapa_out(servico.criar_etapa(ctx, dados))


@router.put("/etapas/ordem", response_model=list[sc.EtapaOut])
def reordenar_etapas(dados: sc.OrdemIn, ctx: Ctx):
    servico.reordenar_etapas(ctx, dados.ids)
    return servico.listar_etapas(ctx)


@router.put("/etapas/{etapa_id}", response_model=sc.EtapaOut)
def editar_etapa(etapa_id: int, dados: sc.EtapaIn, ctx: Ctx):
    return servico.etapa_out(servico.editar_etapa(ctx, _etapa(ctx, etapa_id), dados))


@router.delete("/etapas/{etapa_id}", response_model=Mensagem)
def excluir_etapa(etapa_id: int, ctx: Ctx, mover_para_id: int | None = None):
    servico.excluir_etapa(ctx, _etapa(ctx, etapa_id), mover_para_id)
    return Mensagem(mensagem="Etapa excluída.")


@router.get("/motivos", response_model=list[sc.MotivoOut])
def listar_motivos(ctx: Ctx):
    return servico.listar_motivos(ctx)


@router.post("/motivos", response_model=sc.MotivoOut, status_code=status.HTTP_201_CREATED)
def criar_motivo(dados: sc.MotivoIn, ctx: Ctx):
    m = servico.criar_motivo(ctx, dados)
    return sc.MotivoOut(id=m.id, nome=m.nome, ativo=m.ativo)


@router.put("/motivos/{motivo_id}", response_model=sc.MotivoOut)
def editar_motivo(motivo_id: int, dados: sc.MotivoIn, ctx: Ctx):
    m = servico.editar_motivo(ctx, _motivo(ctx, motivo_id), dados)
    return sc.MotivoOut(id=m.id, nome=m.nome, ativo=m.ativo)


@router.delete("/motivos/{motivo_id}", response_model=Mensagem)
def excluir_motivo(motivo_id: int, ctx: Ctx):
    return Mensagem(mensagem=servico.excluir_motivo(ctx, _motivo(ctx, motivo_id)))


# ------------------------------------------------------------------------------------------------ relatório
@router.get("/relatorio", response_model=sc.Relatorio)
def relatorio(ctx: Ctx, de: date | None = None, ate: date | None = None):
    """Padrão: últimos 90 dias. Conversão por etapa e por origem sobre os leads que entraram no período."""
    hoje = date.today()
    ate = ate or hoje
    de = de or (ate - timedelta(days=89))
    return servico.relatorio(ctx, de, ate)
