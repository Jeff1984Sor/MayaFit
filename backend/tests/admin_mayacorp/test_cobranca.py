"""Cobrança pelo Mercado Pago (falso): configuração, mensalidades, webhook com assinatura, Meu plano, régua,
fim do teste e suspensão por atraso."""

import hashlib
import hmac
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.controle import cobranca, mercadopago
from app.controle.models import Cliente, Cobranca, SessaoControle
from tests.admin_mayacorp.conftest import criar_estudio, plano

PAGAMENTO = {"ref": ""}
CHAMADAS: list = []


class MPFalso(mercadopago.MercadoPago):
    def _chamar(self, metodo, caminho, json=None, chave=None):
        CHAMADAS.append((metodo, caminho, json))
        if caminho == "/users/me":
            return {"id": 1, "email": "contato@mayafit.com.br"}
        if caminho == "/checkout/preferences":
            ref = json["external_reference"]
            return {"id": f"pref-{ref}", "init_point": f"https://www.mercadopago.com.br/{ref}"}
        if caminho.startswith("/v1/payments/"):
            return {"id": 555, "status": "approved", "external_reference": PAGAMENTO["ref"],
                    "payment_type_id": "pix", "date_approved": "2026-11-05T10:00:00.000-03:00"}
        if caminho == "/preapproval" and metodo == "POST":
            return {"id": "pre-1", "status": "pending", "init_point": "https://www.mercadopago.com.br/assinar"}
        if caminho.startswith("/preapproval/"):
            return {"id": "pre-1", "status": "authorized"}
        if caminho.startswith("/authorized_payments/"):
            return {"preapproval_id": "pre-1", "transaction_amount": 89.9, "debit_date": "2026-11-10T09:00:00Z",
                    "payment": {"id": 777, "status": "approved"}}
        raise AssertionError(caminho)


@pytest.fixture
def mp(monkeypatch):
    CHAMADAS.clear()
    monkeypatch.setattr(mercadopago, "MercadoPago", MPFalso)
    monkeypatch.setattr(cobranca, "MercadoPago", MPFalso)
    return CHAMADAS


def _conectar(client, adm, **extra):
    corpo = {"token": "APP_USR-123456", "dia_vencimento": 10, "gerar_automatico": True, "regua": [-3, 0, 3], **extra}
    r = client.put("/api/admin/cobranca/config", headers=adm, json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _ativo(client, adm, nome="Pilates Lumina", slug="pilates-lumina", plano_nome="Estúdio", **extra):
    return criar_estudio(client, adm, nome=nome, slug=slug, plano_id=plano(client, adm, plano_nome)["id"],
                         dias_teste=0, admin_email=f"ana@{slug}.com.br", email_financeiro=f"fin@{slug}.com.br",
                         **extra)


def test_config_e_mensalidade_e_webhook(client, fundacao, adm, mp, emails_admin):
    assert client.get("/api/admin/cobranca/config", headers=adm).json()["conectado"] is False
    cfg = _conectar(client, adm)
    assert cfg["conectado"] and cfg["conta"] == "contato@mayafit.com.br" and cfg["token_final"] == "••••••3456"
    assert cfg["url_notificacao"] == "https://admin.mayafit.test/api/public/mercadopago"
    assert client.post("/api/admin/cobranca/config/testar", headers=adm).json()["ok"] is True
    est = _ativo(client, adm)
    fundacao.uso["pilates-lumina"] = {"alunos_ativos": 160, "usuarios": 5}
    # a 1ª mensalidade nasceu com o estúdio (sem teste) e já foi por e-mail
    primeira = client.get("/api/admin/cobrancas", headers=adm, params={"cliente_id": est["id"]}).json()
    assert len(primeira) == 1 and primeira[0]["link"].startswith("https://www.mercadopago.com.br/cob:")
    assert any("Pague por Pix" in corpo for _, _, corpo, _ in emails_admin)
    # mensalidade de um mês seguinte: plano + 10 alunos excedentes; idempotente
    r = client.post("/api/admin/cobrancas/gerar", headers=adm, json={"competencia": "2027-01", "enviar": True})
    assert r.json()["criadas"] == ["Pilates Lumina"], r.text
    assert client.post("/api/admin/cobrancas/gerar", headers=adm,
                       json={"competencia": "2027-01", "enviar": False}).json()["criadas"] == []
    cob = next(k for k in client.get("/api/admin/cobrancas", headers=adm).json() if k["competencia"] == "2027-01")
    assert cob["valor"] == "94.90" and [i["valor"] for i in cob["itens"]] == ["89.90", "5.00"]
    # o Mercado Pago avisa o pagamento: baixa (relida na API, não no aviso)
    PAGAMENTO["ref"] = f"cob:{cob['id']}"
    assert client.post("/api/public/mercadopago", json={"type": "payment", "data": {"id": "555"}}).status_code == 200
    cob = next(k for k in client.get("/api/admin/cobrancas", headers=adm).json() if k["id"] == cob["id"])
    assert cob["status"] == "paga" and cob["forma_paga"] == "Pix"
    assert any("pagamento recebido" in a for _, a, _, _ in emails_admin)
    # resumo das cobranças
    res = client.get("/api/admin/cobrancas/resumo", headers=adm).json()
    assert res["em_aberto"] == "89.90" and res["vencido"] == "0.00"


def test_assinatura_secreta_do_webhook(client, fundacao, adm, mp):
    _conectar(client, adm, segredo="s3gr3d0")
    est = _ativo(client, adm)
    r = client.post("/api/admin/cobrancas/avulsa", headers=adm, json={
        "cliente_id": est["id"], "descricao": "Implantação", "valor": "300.00", "vencimento": "2026-12-20"})
    assert r.status_code == 201, r.text
    av = r.json()
    PAGAMENTO["ref"] = f"cob:{av['id']}"
    # sem assinatura ou com assinatura errada: ignorado (200 para o MP não insistir)
    client.post("/api/public/mercadopago", json={"type": "payment", "data": {"id": "555"}})
    client.post("/api/public/mercadopago?data.id=555&type=payment", json={"type": "payment", "data": {"id": "555"}},
                headers={"x-signature": "ts=1,v1=errado", "x-request-id": "r1"})
    assert next(k for k in client.get("/api/admin/cobrancas", headers=adm).json()
                if k["id"] == av["id"])["status"] == "pendente"
    v1 = hmac.new(b"s3gr3d0", b"id:555;request-id:r1;ts:1;", hashlib.sha256).hexdigest()
    client.post("/api/public/mercadopago?data.id=555&type=payment", json={"type": "payment", "data": {"id": "555"}},
                headers={"x-signature": f"ts=1,v1={v1}", "x-request-id": "r1"})
    assert next(k for k in client.get("/api/admin/cobrancas", headers=adm).json()
                if k["id"] == av["id"])["status"] == "paga"


def test_baixa_manual_cancelar_e_reenviar(client, fundacao, adm, mp, emails_admin):
    _conectar(client, adm)
    est = _ativo(client, adm)
    k = client.get("/api/admin/cobrancas", headers=adm, params={"cliente_id": est["id"]}).json()[0]
    r = client.post(f"/api/admin/cobrancas/{k['id']}/enviar", headers=adm)
    assert r.json()["enviado_para"] == ["fin@pilates-lumina.com.br"]
    assert client.post(f"/api/admin/cobrancas/{k['id']}/baixa", headers=adm,
                       json={"forma": "transferência"}).json()["status"] == "paga"
    assert client.post(f"/api/admin/cobrancas/{k['id']}/cancelar", headers=adm).status_code == 400
    assert client.post(f"/api/admin/cobrancas/{k['id']}/enviar", headers=adm).status_code == 400


def test_meu_plano_do_estudio(client, fundacao, adm, mp):
    _conectar(client, adm)
    est = _ativo(client, adm, plano_nome="Essencial")
    fundacao.uso["pilates-lumina"] = {"alunos_ativos": 50, "usuarios": 2}
    assert client.get("/api/meu-plano", headers=adm).status_code == 404  # o admin não tem "Meu plano"
    fundacao.entrar_no("pilates-lumina")
    meu = client.get("/api/meu-plano", headers=adm).json()
    assert meu["plano"]["nome"] == "Essencial" and meu["valor"] == "49.90" and meu["pode_alterar"] is True
    assert meu["uso"]["limite_alunos"] == 60 and len(meu["em_aberto"]) == 1
    estudio = next(p for p in meu["planos"] if p["nome"] == "Estúdio")
    r = client.put("/api/meu-plano", headers=adm, json={"plano_id": estudio["id"], "ciclo": "mensal"})
    assert r.status_code == 200 and r.json()["plano"]["nome"] == "Estúdio", r.text
    r = client.post("/api/meu-plano/cartao", headers=adm)
    assert r.json()["link"] == "https://www.mercadopago.com.br/assinar", r.text
    k = meu["em_aberto"][0]
    assert client.post(f"/api/meu-plano/cobrancas/{k['id']}/link", headers=adm).json()["link"] == k["link"]
    # downgrade com mais usuários que o plano permite é barrado
    fundacao.uso.clear()
    with SessaoControle() as ctl:
        ctl.get(Cliente, est["id"]).uso = {"alunos_ativos": 50, "usuarios": 4}
        ctl.commit()
    essencial = next(p for p in meu["planos"] if p["nome"] == "Essencial")
    r = client.put("/api/meu-plano", headers=adm, json={"plano_id": essencial["id"]})
    assert r.status_code == 400 and "vai até 2 usuário(s)" in r.json()["detail"]
    # débito da assinatura vira cobrança paga
    fundacao.entrar_no(None)
    client.post("/api/public/mercadopago", json={"type": "subscription_authorized_payment", "data": {"id": "9"}})
    cartao = [k for k in client.get("/api/admin/cobrancas", headers=adm).json() if k["tipo"] == "cartao"]
    assert [(k["competencia"], k["valor"], k["status"]) for k in cartao] == [("2026-11", "89.90", "paga")]


def test_meu_plano_so_administrador(client, db, fundacao, adm):
    from tests.conftest import auth, criar_usuario, entrar

    _ativo(client, adm)
    criar_usuario(db, "Secretária", email="sec@lumina.com.br", login="sec")
    sec = auth(entrar(client, "sec").json()["access_token"])
    fundacao.entrar_no("pilates-lumina")
    assert client.get("/api/meu-plano", headers=sec).status_code == 403


def test_regua_fim_do_teste_e_suspensao(client, fundacao, adm, mp, emails_admin):
    _conectar(client, adm)
    est = _ativo(client, adm)
    r = client.post("/api/admin/cobrancas/avulsa", headers=adm, json={
        "cliente_id": est["id"], "descricao": "Treinamento", "valor": "200.00", "vencimento": "2026-11-01",
        "enviar": False})
    kid = r.json()["id"]
    assert cobranca.rotina_diaria(date(2026, 11, 6))["avisos"] >= 1
    with SessaoControle() as ctl:
        assert ctl.get(Cobranca, kid).avisos == [-3, 0, 3]  # um e-mail só, com o passo mais recente
    # 30 dias de atraso → suspenso (com aviso); antes disso, não; pagou → volta a ativo
    assert cobranca.suspender_atrasados(date(2026, 11, 16)) == []
    assert cobranca.suspender_atrasados(date(2026, 12, 1)) == ["pilates-lumina"]
    assert client.get(f"/api/admin/clientes/{est['id']}", headers=adm).json()["status"] == "suspenso"
    assert any("acesso suspenso" in a for _, a, _, _ in emails_admin)
    with SessaoControle() as ctl:
        for k in ctl.scalars(select(Cobranca).where(Cobranca.cliente_id == est["id"])):
            k.vencimento = min(k.vencimento, date.today() - timedelta(days=1))
        ctl.commit()
    for k in client.get("/api/admin/cobrancas", headers=adm, params={"cliente_id": est["id"]}).json():
        client.post(f"/api/admin/cobrancas/{k['id']}/baixa", headers=adm, json={})
    assert client.get(f"/api/admin/clientes/{est['id']}", headers=adm).json()["status"] == "ativo"
    # teste que acabou: vira ativo e a 1ª mensalidade nasce (vence em 3 dias)
    t = criar_estudio(client, adm, nome="Studio Teste", slug="studio-teste", admin_email="t@teste.com.br",
                      plano_id=plano(client, adm, "Pro")["id"], dias_teste=10)
    assert client.get("/api/admin/cobrancas", headers=adm, params={"cliente_id": t["id"]}).json() == []
    hoje = date.today() + timedelta(days=11)
    assert cobranca.encerrar_testes(hoje) == {"encerrados": 1, "cobrancas": 1}
    cobs = client.get("/api/admin/cobrancas", headers=adm, params={"cliente_id": t["id"]}).json()
    assert [(k["valor"], k["vencimento"]) for k in cobs] == [("149.90", (hoje + timedelta(days=3)).isoformat())]
    linha = [e["descricao"] for e in client.get(f"/api/admin/clientes/{t['id']}/eventos", headers=adm).json()]
    assert linha[0].startswith("1ª mensalidade gerada") and any("Em teste → Ativo" in x for x in linha)
