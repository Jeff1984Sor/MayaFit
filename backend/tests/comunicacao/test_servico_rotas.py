"""Serviço de envio, histórico, cobrança, enviador de contrato/termo, notificador real e permissões por perfil."""
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.core import notificador as notif
from app.core.models import Auditoria
from app.modules.alunos.models import WhatsappMensagem
from app.modules.comunicacao import servico as svc
from app.modules.financeiro.servico import ErroDeNegocio, cobrador_disponivel
from tests.comunicacao.conftest import SESSAO_CAIDA, TOKEN, conta, contrato, reservar


def historico(db):
    db.expire_all()
    return list(db.scalars(select(WhatsappMensagem).order_by(WhatsappMensagem.id)))


# ------------------------------------------------------------------------------------------------ envio ao aluno
def test_enviar_mensagem_ao_aluno_grava_historico_sem_segredo(client, full, cenario, falso, db):
    r = client.post(f"/api/whatsapp/alunos/{cenario.maria.id}/enviar", json={"texto": "Oi {aluno}, bem-vinda à {unidade}!"}, headers=full)
    assert r.status_code == 200, r.text
    assert falso.textos == [("5511999990001", "Oi Maria Souza, bem-vinda à Matriz!")]
    m = historico(db)[0]
    assert m.status == "sent" and m.tipo == "manual" and m.direcao.value == "enviada" and m.telefone == "5511999990001"
    assert TOKEN not in (m.resposta_payload or "")
    assert any(a.acao == "whatsapp.enviar" for a in db.scalars(select(Auditoria)))


def test_aluno_sem_celular_valido_nao_envia(client, full, cenario, falso):
    for a in (cenario.sem_tel, cenario.fixo):
        r = client.post(f"/api/whatsapp/alunos/{a.id}/enviar", json={"texto": "x"}, headers=full)
        assert r.status_code == 422 and "celular" in r.json()["detail"]
    assert falso.chamadas == 0


def test_falha_do_provedor_e_registrada_e_devolve_erro(client, full, cenario, falso, db):
    falso.roteiro = [SESSAO_CAIDA]
    r = client.post(f"/api/whatsapp/alunos/{cenario.maria.id}/enviar", json={"texto": "x"}, headers=full)
    assert r.status_code == 502 and "desconectada" in r.json()["detail"]
    m = historico(db)[0]
    assert m.status == "failed" and "not connected" in m.resposta_payload.lower()


def test_sem_configuracao_da_unidade_responde_409(client, full, cenario, falso, db):
    svc.obter_config(db, cenario.un.id).credencial_cifrado = None
    db.commit()
    r = client.post(f"/api/whatsapp/alunos/{cenario.maria.id}/enviar", json={"texto": "x"}, headers=full)
    assert r.status_code == 409 and "configurado" in r.json()["detail"]


def test_envio_manual_funciona_com_a_chave_geral_desligada(client, full, cenario, falso, db):
    assert not svc.envio_automatico_ativo(db)
    assert client.post(f"/api/whatsapp/alunos/{cenario.maria.id}/enviar", json={"texto": "x"}, headers=full).status_code == 200


# ------------------------------------------------------------------------------------------------ histórico
def test_historico_com_filtros(client, full, cenario, falso, db):
    for a, t in ((cenario.maria, "um"), (cenario.joao, "dois")):
        client.post(f"/api/whatsapp/alunos/{a.id}/enviar", json={"texto": t}, headers=full)
    falso.roteiro = [SESSAO_CAIDA]
    client.post(f"/api/whatsapp/alunos/{cenario.maria.id}/enviar", json={"texto": "falha"}, headers=full)
    tudo = client.get("/api/whatsapp/mensagens", headers=full).json()
    assert tudo["total"] == 3
    assert client.get(f"/api/whatsapp/mensagens?aluno_id={cenario.joao.id}", headers=full).json()["total"] == 1
    assert client.get("/api/whatsapp/mensagens?status=failed", headers=full).json()["total"] == 1
    assert client.get("/api/whatsapp/mensagens?tipo=comunicado", headers=full).json()["total"] == 0
    from datetime import datetime
    from zoneinfo import ZoneInfo

    hoje_sp = datetime.now(ZoneInfo("America/Sao_Paulo")).date()  # o filtro é pelo dia de Brasília (servidor em UTC)
    hoje = hoje_sp.isoformat()
    assert client.get(f"/api/whatsapp/mensagens?de={hoje}&ate={hoje}", headers=full).json()["total"] == 3
    amanha = (hoje_sp + timedelta(days=2)).isoformat()
    assert client.get(f"/api/whatsapp/mensagens?de={amanha}", headers=full).json()["total"] == 0
    assert client.get("/api/whatsapp/mensagens?q=Lima", headers=full).json()["total"] == 1
    falha = next(i for i in tudo["itens"] if i["status"] == "failed")
    assert falha["detalhe"] and falha["tipo_rotulo"] == "Mensagem manual"


def test_conversa_da_ficha_em_ordem_cronologica(client, full, cenario, falso):
    for t in ("primeira", "segunda"):
        client.post(f"/api/whatsapp/alunos/{cenario.maria.id}/enviar", json={"texto": t}, headers=full)
    msgs = client.get(f"/api/whatsapp/alunos/{cenario.maria.id}/mensagens", headers=full).json()
    assert [m["mensagem"] for m in msgs] == ["primeira", "segunda"]
    assert client.get("/api/whatsapp/alunos/9999/mensagens", headers=full).status_code == 404


# ------------------------------------------------------------------------------------------------ enviar agora (painel)
def test_enviar_agora_manda_o_lembrete_da_aula(client, secretaria, cenario, falso, db):
    r = reservar(db, cenario, cenario.maria)
    p = client.get(f"/api/whatsapp/reservas/{r.id}/previa", headers=secretaria).json()
    assert "Maria Souza" in p["mensagem"] and p["tem_celular"]
    out = client.post(f"/api/whatsapp/reservas/{r.id}/enviar-agora", headers=secretaria)
    assert out.status_code == 200 and falso.textos[0][1] == p["mensagem"]
    assert historico(db)[0].tipo == "lembrete_aluno"


def test_enviar_agora_recusa_aula_cancelada(client, full, cenario, falso, db):
    r = reservar(db, cenario, cenario.maria)
    r.status = "CANCELADA"
    db.commit()
    assert client.post(f"/api/whatsapp/reservas/{r.id}/enviar-agora", headers=full).status_code == 409
    assert client.post("/api/whatsapp/reservas/9999/enviar-agora", headers=full).status_code == 404
    assert falso.chamadas == 0


# ------------------------------------------------------------------------------------------------ aviso ao aluno
def test_aviso_ao_aluno_previa_e_envio(client, secretaria, cenario, falso):
    corpo = {"aluno_id": cenario.maria.id, "texto": "Olá {aluno}, aviso da {unidade}."}
    p = client.post("/api/comunicacao/aviso-aluno/previa", json=corpo, headers=secretaria).json()
    assert p["mensagem"] == "Olá Maria Souza, aviso da Matriz." and p["tem_celular"] and falso.chamadas == 0
    assert client.post("/api/comunicacao/aviso-aluno", json=corpo, headers=secretaria).status_code == 200
    assert falso.textos[0][1] == p["mensagem"]
    sem = client.post("/api/comunicacao/aviso-aluno", json={"aluno_id": cenario.sem_tel.id, "texto": "x"}, headers=secretaria)
    assert sem.status_code == 422


def test_variavel_desconhecida_permanece_escrita(client, full, cenario, falso):
    client.post("/api/comunicacao/aviso-aluno", json={"aluno_id": cenario.maria.id, "texto": "Oi {aluno} {xyz}"}, headers=full)
    assert falso.textos[0][1] == "Oi Maria Souza {xyz}"


# ------------------------------------------------------------------------------------------------ cobrança (financeiro)
def test_cobranca_por_whatsapp_pelo_financeiro(client, full, cenario, falso, db):
    assert cobrador_disponivel()
    c = contrato(db, cenario, cenario.maria, date(2026, 1, 1), date(2027, 1, 1))
    cobr = conta(db, cenario.maria, c, date.today() - timedelta(days=5), "250.00")
    r = client.post(f"/api/financeiro/receber/{cobr.id}/cobrar-whatsapp", headers=full)
    assert r.status_code == 200, r.text
    texto = falso.textos[0][1]
    assert "R$ 250,00" in texto and "ainda não consta" in texto  # texto de atraso
    assert historico(db)[0].tipo == "cobranca"


def test_cobranca_a_vencer_usa_o_texto_de_vencimento(client, full, cenario, falso, db):
    c = contrato(db, cenario, cenario.maria, date(2026, 1, 1), date(2027, 1, 1))
    cobr = conta(db, cenario.maria, c, date.today() + timedelta(days=3))
    assert client.post(f"/api/financeiro/receber/{cobr.id}/cobrar-whatsapp", headers=full).status_code == 200
    assert "vence em breve" in falso.textos[0][1]


def test_cobranca_sem_telefone_e_erro_de_negocio(client, full, cenario, falso, db):
    c = contrato(db, cenario, cenario.sem_tel, date(2026, 1, 1), date(2027, 1, 1))
    cobr = conta(db, cenario.sem_tel, c, date.today() - timedelta(days=1))
    r = client.post(f"/api/financeiro/receber/{cobr.id}/cobrar-whatsapp", headers=full)
    assert r.status_code == 422 and falso.chamadas == 0


# ------------------------------------------------------------------------------------------------ contrato / termo
def test_enviador_de_contrato_e_termo(cenario, falso, db):
    env = svc.registrar_enviador()
    assert env is svc.registrar_enviador()
    texto = env.enviar_link_contrato(db, cenario.maria, "https://app.exemplo.com/c/abc", contrato_id=None)
    assert "Maria Souza" in texto and "https://app.exemplo.com/c/abc" in texto
    env.enviar_link_termo(db, cenario.maria, "https://app.exemplo.com/t/xyz")
    env.enviar_documento_por_url(db, cenario.maria, "https://arquivos.exemplo.com/c.pdf?assinatura=segredo", "contrato.pdf", "Seu contrato")
    db.commit()
    assert falso.documentos == [("5511999990001", "https://arquivos.exemplo.com/c.pdf?assinatura=segredo", "contrato.pdf", "Seu contrato")]
    tipos = [m.tipo for m in historico(db)]
    assert tipos == ["contract_link", "image_term_link", "contract_pdf"]
    assert "assinatura=segredo" not in " ".join(m.mensagem for m in historico(db))  # a URL assinada não vai para o histórico


def test_enviador_levanta_erro_claro_quando_nao_envia(cenario, falso, db):
    with pytest.raises(ErroDeNegocio):
        svc.registrar_enviador().enviar_link_contrato(db, cenario.sem_tel, "https://x")


def test_enviar_documento_por_url_publica(cenario, falso, db):
    res = svc.enviar_documento_por_url(db, cenario.joao, "https://arquivos.exemplo.com/t.pdf", "termo.pdf", "Termo")
    assert res.ok and res.status == "sent"


# ------------------------------------------------------------------------------------------------ notificador real
def test_notificador_real_envia_codigo_pelo_whatsapp(cenario, falso, db):
    n = svc.NotificadorWhatsapp()
    assert n.enviar_texto("(11) 99999-0001", "Seu código é 123456") is True
    assert falso.textos == [("5511999990001", "Seu código é 123456")]
    assert historico(db) == []  # o código não é guardado no histórico


def test_notificador_nao_envia_para_fixo_nem_sem_config(cenario, falso, db):
    assert svc.NotificadorWhatsapp().enviar_texto("1133334444", "x") is False
    svc.obter_config(db, cenario.un.id).credencial_cifrado = None
    db.commit()
    assert svc.NotificadorWhatsapp().enviar_texto("11999990001", "x") is False
    assert falso.chamadas == 0


def test_notificador_falha_devolve_false(cenario, falso):
    falso.roteiro = [SESSAO_CAIDA]
    assert svc.NotificadorWhatsapp().enviar_texto("11999990001", "x") is False


def test_notificador_do_core_ja_e_o_real_e_recuperacao_de_senha_usa_o_whatsapp(client, cenario, falso, db):
    from tests.conftest import criar_usuario

    assert isinstance(notif.get_notificador(), svc.NotificadorWhatsapp)
    criar_usuario(db, "Secretária", email="rec@exemplo.com", telefone="(11) 98888-7777")
    assert client.post("/api/auth/forgot-codigo", json={"identificador": "rec"}).status_code == 200
    assert falso.textos and falso.textos[0][0] == "5511988887777"


def test_otp_do_app_do_aluno_usa_o_mesmo_notificador(cenario, falso):
    """O app do aluno envia o OTP por `notificador.get_notificador().enviar_texto(telefone, texto)`."""
    assert notif.get_notificador().enviar_texto("5511999990002", "Código 654321") is True
    assert falso.textos[0] == ("5511999990002", "Código 654321")


# ------------------------------------------------------------------------------------------------ permissões
ROTAS_VER = ["/api/whatsapp/mensagens", "/api/whatsapp/status", "/api/whatsapp/automaticos", "/api/comunicacao/comunicados"]


def test_professor_nao_acessa_nada_de_comunicacao(client, professor, cenario):
    for url in ROTAS_VER:
        assert client.get(url, headers=professor).status_code == 403, url
    corpo = {"texto": "x", "publico": "todos"}
    assert client.post("/api/comunicacao/comunicados", json=corpo, headers=professor).status_code == 403
    assert client.post("/api/comunicacao/comunicados/previa", json=corpo, headers=professor).status_code == 403
    assert client.post(f"/api/whatsapp/alunos/{cenario.maria.id}/enviar", json={"texto": "x"}, headers=professor).status_code == 403
    assert client.post("/api/whatsapp/reservas/1/enviar-agora", headers=professor).status_code == 403
    assert client.post("/api/comunicacao/aviso-aluno", json={"aluno_id": 1, "texto": "x"}, headers=professor).status_code == 403


def test_secretaria_ve_e_envia_mas_nao_configura(client, secretaria, cenario, falso):
    for url in ROTAS_VER:
        assert client.get(url, headers=secretaria).status_code == 200, url
    assert client.post(f"/api/whatsapp/alunos/{cenario.maria.id}/enviar", json={"texto": "x"}, headers=secretaria).status_code == 200


def test_sem_login_401(client):
    for url in ROTAS_VER:
        assert client.get(url).status_code == 401


def test_perfil_somente_leitura_nao_envia(client, db, cenario):
    from app.core import perfis
    from tests.conftest import criar_usuario, entrar

    p = perfis.garantir_padrao(db)["Secretária"]
    p.permissoes = ["whatsapp.ver", "comunicacao.ver"]
    db.commit()
    criar_usuario(db, "Secretária", email="leitor@x.com")
    h = {"Authorization": "Bearer " + entrar(client, "leitor@x.com").json()["access_token"]}
    assert client.get("/api/whatsapp/mensagens", headers=h).status_code == 200
    assert client.post(f"/api/whatsapp/alunos/{cenario.maria.id}/enviar", json={"texto": "x"}, headers=h).status_code == 403
    assert client.post("/api/comunicacao/comunicados", json={"texto": "x", "publico": "todos"}, headers=h).status_code == 403
    assert db.scalar(select(func.count()).select_from(WhatsappMensagem)) == 0


def test_tarefas_registradas_no_worker():
    import app.modules.comunicacao.tarefas  # noqa: F401
    from app.worker import TAREFAS

    por_nome = {t.nome: t.intervalo_s for t in TAREFAS}
    assert por_nome["whatsapp-avisos-automaticos"] == 300 and por_nome["comunicados-envio"] == 5
