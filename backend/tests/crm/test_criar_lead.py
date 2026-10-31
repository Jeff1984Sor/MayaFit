"""Interface estável `servico.criar_lead` (chamada pelo site do estúdio)."""

import pytest
from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.crm import servico
from app.modules.crm.models import CrmInteracao, CrmLead, CrmTarefa, OrigemLead, SituacaoLead, TipoInteracao


def test_cria_lead_novo_com_funil_padrao_tarefa_e_auditoria(db):
    lead = servico.criar_lead(db, nome="  Ana   Souza ", telefone="(11) 98765-4321", email="Ana@Exemplo.com",
                              interesse="Pilates", mensagem="Tenho dor nas costas")
    assert lead.id and lead.nome == "Ana Souza"
    assert lead.telefone == "5511987654321"
    assert lead.email == "ana@exemplo.com"
    assert lead.origem == OrigemLead.SITE and lead.situacao == SituacaoLead.ABERTO
    assert [e.nome for e in servico.etapas(db)][0] == "Novo contato"
    assert lead.etapa_id == servico.etapas(db)[0].id
    interacoes = db.scalars(select(CrmInteracao).where(CrmInteracao.lead_id == lead.id)).all()
    assert len(interacoes) == 1 and interacoes[0].tipo == TipoInteracao.SISTEMA
    assert "Tenho dor nas costas" in interacoes[0].descricao and "Pilates" in interacoes[0].descricao
    tarefas = db.scalars(select(CrmTarefa).where(CrmTarefa.lead_id == lead.id)).all()
    assert len(tarefas) == 1 and tarefas[0].automatica and "primeiro contato" in tarefas[0].titulo
    aud = db.scalars(select(Auditoria).where(Auditoria.acao == "crm.lead.criar")).all()
    assert len(aud) == 1 and aud[0].usuario_nome == "Robô"


def test_dedup_por_telefone_acrescenta_interacao(db):
    a = servico.criar_lead(db, nome="Ana", telefone="11987654321", email=None)
    b = servico.criar_lead(db, nome="Ana S.", telefone="+55 (11) 98765-4321", email="ana@x.com", mensagem="Voltei!",
                           quer_aula_experimental=True)
    assert a.id == b.id
    assert db.scalar(select(CrmLead.id).where(CrmLead.id != a.id)) is None
    db.refresh(b)
    assert b.nome == "Ana" and b.email == "ana@x.com"  # completa o que faltava, não troca o nome
    assert "Quer aula experimental" in b.tags
    textos = [i.descricao for i in db.scalars(select(CrmInteracao).where(CrmInteracao.lead_id == a.id))]
    assert len(textos) == 2 and any("Voltei!" in t and "de novo" in t for t in textos)
    # a tarefa de primeiro contato ainda está pendente: não cria outra
    assert len(db.scalars(select(CrmTarefa).where(CrmTarefa.lead_id == a.id)).all()) == 1
    assert db.scalars(select(Auditoria).where(Auditoria.acao == "crm.lead.recontato")).first()


def test_dedup_por_email_ignora_maiusculas(db):
    a = servico.criar_lead(db, nome="Bruno", telefone=None, email="bruno@x.com")
    b = servico.criar_lead(db, nome="Bruno", telefone=None, email="BRUNO@X.COM ")
    assert a.id == b.id


def test_lead_encerrado_nao_bloqueia_novo_lead(db):
    a = servico.criar_lead(db, nome="Caio", telefone="11912345678", email=None)
    a.situacao = SituacaoLead.PERDIDO
    db.commit()
    b = servico.criar_lead(db, nome="Caio", telefone="11912345678", email=None, origem="Instagram")
    assert b.id != a.id and b.origem == OrigemLead.INSTAGRAM


def test_quer_aula_experimental_cria_tarefa_de_agendar(db):
    lead = servico.criar_lead(db, nome="Duda", telefone=None, email="duda@x.com", origem="Gympass", quer_aula_experimental=True)
    assert lead.origem == OrigemLead.WELLHUB
    assert "Quer aula experimental" in lead.tags
    t = db.scalars(select(CrmTarefa).where(CrmTarefa.lead_id == lead.id)).one()
    assert t.titulo.startswith("Agendar aula experimental")


@pytest.mark.parametrize("nome,tel,email", [("", "11987654321", None), ("Ana", None, None), ("Ana", " ", "sem-arroba")])
def test_validacoes(db, nome, tel, email):
    with pytest.raises(ValueError):
        servico.criar_lead(db, nome=nome, telefone=tel, email=email)


def test_lead_do_site_aparece_no_funil_da_equipe(db, client, h):
    servico.criar_lead(db, nome="Eva Site", telefone="21999998888", email=None)
    colunas = client.get("/api/crm/funil", headers=h).json()["colunas"]
    assert colunas[0]["etapa"]["nome"] == "Novo contato"
    assert [c["nome"] for c in colunas[0]["leads"]] == ["Eva Site"]
    assert colunas[0]["leads"][0]["whatsapp_url"] == "https://wa.me/5521999998888"
