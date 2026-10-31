"""Catracas: drivers (Control iD com HTTP falso, simulado, Henry esqueleto), modos totem/agente/servidor, liberação manual."""

import json
from datetime import timedelta

import httpx
from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.acesso.drivers import DadosCatraca, controlid, obter
from app.modules.acesso.drivers import simulado as sim
from app.modules.acesso.drivers.base import giro_do_sentido
from app.modules.acesso.models import Catraca, ComandoCatraca, RegistroAcesso
from tests.acesso.conftest import AGORA, PROVA_VIDA, cadastrar_rosto, criar_totem, h, vetor


class ControlIdFalso:
    """Imita a Access API da Control iD (login.fcgi, execute_actions.fcgi, system_information.fcgi, logout.fcgi)."""

    def __init__(self, senha="segredo1"):
        self.senha = senha
        self.chamadas: list[tuple[str, dict, dict]] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        corpo = json.loads(req.content or b"{}")
        self.chamadas.append((req.url.path, dict(req.url.params), corpo))
        if req.url.path == "/login.fcgi":
            if corpo.get("password") != self.senha:
                return httpx.Response(401, json={"error": "invalid"})
            return httpx.Response(200, json={"session": "S123"})
        if req.url.params.get("session") != "S123":
            return httpx.Response(401)
        if req.url.path == "/system_information.fcgi":
            return httpx.Response(200, json={"serial": "0M0300/1234", "version": "4.2.1"})
        return httpx.Response(200, json={})


def instalar(falso):
    controlid.definir_fabrica_cliente(lambda d: httpx.Client(base_url=d.url_base, transport=httpx.MockTransport(falso)))


DADOS = DadosCatraca(id=1, nome="Recepção", host="192.168.0.50", porta=80, usuario="admin", senha="segredo1")


def test_controlid_liberar_faz_login_execute_actions_e_logout():
    falso = ControlIdFalso()
    instalar(falso)
    r = obter("controlid").liberar(DADOS, "entrada")
    assert r.ok, r.mensagem
    caminhos = [c[0] for c in falso.chamadas]
    assert caminhos == ["/login.fcgi", "/execute_actions.fcgi", "/logout.fcgi"]
    assert falso.chamadas[0][2] == {"login": "admin", "password": "segredo1"}
    assert falso.chamadas[1][2] == {"actions": [{"action": "catra", "parameters": "allow=clockwise"}]}
    assert obter("controlid").liberar(DADOS, "saida").ok
    assert falso.chamadas[4][2]["actions"][0]["parameters"] == "allow=anticlockwise"


def test_controlid_porta_rele_e_status():
    falso = ControlIdFalso()
    instalar(falso)
    porta = DadosCatraca(id=1, nome="Porta", host="10.0.0.2", usuario="admin", senha="segredo1", acao_liberacao="door", porta_rele=2)
    assert obter("controlid").liberar(porta).ok
    assert falso.chamadas[1][2] == {"actions": [{"action": "door", "parameters": "door=2"}]}
    st = obter("controlid").status(DADOS)
    assert st.ok and "0M0300/1234" in st.mensagem and "4.2.1" in st.mensagem


def test_controlid_senha_errada_e_fora_do_ar():
    instalar(ControlIdFalso(senha="outra"))
    r = obter("controlid").liberar(DADOS)
    assert not r.ok and "recusados" in r.mensagem

    def caiu(req):
        raise httpx.ConnectError("sem rota")

    instalar(caiu)
    r = obter("controlid").status(DADOS)
    assert not r.ok and "não respondeu" in r.mensagem


def test_plano_para_o_navegador_do_totem():
    p = obter("controlid").plano_navegador(DADOS, "liberar", "entrada")
    assert [s.url for s in p.passos] == ["http://192.168.0.50:80/login.fcgi", "http://192.168.0.50:80/execute_actions.fcgi?session={sessao}",
                                         "http://192.168.0.50:80/logout.fcgi?session={sessao}"]
    assert p.passos[0].extrair == "session"
    assert obter("henry").plano_navegador(DADOS) is None
    assert not obter("henry").liberar(DADOS).ok


def test_giro_por_sentido():
    assert giro_do_sentido("clockwise", "entrada") == "clockwise"
    assert giro_do_sentido("clockwise", "saida") == "anticlockwise"
    assert giro_do_sentido("anticlockwise", "saida") == "clockwise"
    assert giro_do_sentido("both", "saida") == "both"


# ------------------------------------------------------------------------------------------------ cadastro e telas
def nova_catraca(client, full, **extra) -> dict:
    corpo = {"nome": "Catraca recepção", "driver": "controlid", "modo": "totem", "host": "192.168.0.50", "porta": 80,
             "usuario": "admin", "senha": "segredo1", "sentido_entrada": "clockwise"}
    corpo.update(extra)
    r = client.post("/api/acesso/catracas", headers=full, json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def test_senha_da_catraca_cifrada_e_somente_escrita(client, db, full):
    c = nova_catraca(client, full)
    assert "senha" not in c and c["senha_definida"] is True and c["senha_final"] == "redo1"[-4:]
    row = db.get(Catraca, c["id"])
    assert row.senha_cifrada.startswith(b"gAAAA") and b"segredo1" not in row.senha_cifrada
    corpo = {k: c[k] for k in ("nome", "driver", "modo", "host", "porta", "usuario", "sentido_entrada")}
    r = client.put(f"/api/acesso/catracas/{c['id']}", headers=full, json={**corpo, "senha": None, "nome": "Catraca 1"})
    assert r.status_code == 200 and r.json()["senha_definida"]
    auds = list(db.scalars(select(Auditoria).where(Auditoria.entidade == "acesso_catraca")))
    assert auds and all("segredo1" not in json.dumps(a.depois_json or {}) for a in auds)


def test_henry_pelo_totem_e_recusado(client, full):
    r = client.post("/api/acesso/catracas", headers=full, json={"nome": "Henry", "driver": "henry", "modo": "totem", "host": "10.0.0.9"})
    assert r.status_code == 422


def test_testar_conexao_modo_servidor(client, db, full):
    instalar(ControlIdFalso())
    c = nova_catraca(client, full, modo="servidor")
    j = client.post(f"/api/acesso/catracas/{c['id']}/testar", headers=full).json()
    assert j["ok"] is True and "Conectado" in j["mensagem"]
    assert client.get("/api/acesso/catracas", headers=full).json()[0]["ultimo_teste_ok"] is True


def test_testar_conexao_modo_totem_devolve_plano_para_este_navegador(client, full):
    c = nova_catraca(client, full)
    j = client.post(f"/api/acesso/catracas/{c['id']}/testar", headers=full).json()
    assert j["ok"] is None and len(j["acionamento"]["plano"]["passos"]) == 3
    r = client.post(f"/api/acesso/catracas/{c['id']}/teste-navegador", headers=full, json={"ok": False, "detalhe": "CORS"})
    assert r.status_code == 200
    assert client.get("/api/acesso/catracas", headers=full).json()[0]["ultimo_teste_detalhe"] == "CORS"


def test_checkin_no_totem_com_catraca_controlid_devolve_plano_e_recebe_resultado(client, db, full, cenario):
    c = nova_catraca(client, full)
    t = criar_totem(client, full, catraca_id=c["id"])
    cadastrar_rosto(client, full, cenario.ana.id, vetor(1))
    j = client.post("/api/totem/identificar/facial", headers=h(t), json={"descritor": vetor(1), "prova_vida": PROVA_VIDA}).json()
    ac = j["acionamento"]
    assert ac["status"] == "pendente" and ac["modo"] == "totem" and ac["plano"]["passos"][1]["corpo"]["actions"][0]["action"] == "catra"
    assert client.post(f"/api/totem/registros/{j['registro_id']}/catraca", headers=h(t), json={"ok": True}).status_code == 200
    assert db.get(RegistroAcesso, j["registro_id"]).catraca_status == "liberada"
    outro = criar_totem(client, full)
    assert client.post(f"/api/totem/registros/{j['registro_id']}/catraca", headers=h(outro), json={"ok": True}).status_code == 404


def test_catraca_simulada_libera_na_hora(client, full, cenario):
    sim.GIROS.clear()
    c = nova_catraca(client, full, driver="simulado", host=None, usuario=None, senha=None)
    t = criar_totem(client, full, catraca_id=c["id"])
    client.put(f"/api/acesso/alunos/{cenario.ana.id}/pin", headers=full, json={"pin": "2580"})
    j = client.post("/api/totem/identificar/documento", headers=h(t), json={"documento": "4321", "pin": "2580"}).json()
    assert j["acionamento"]["status"] == "liberada"
    assert sim.GIROS == [(c["id"], "entrada")]


def test_negado_nao_aciona_catraca(client, full, cenario):
    sim.GIROS.clear()
    c = nova_catraca(client, full, driver="simulado", host=None)
    t = criar_totem(client, full, catraca_id=c["id"])
    client.put(f"/api/acesso/alunos/{cenario.bruno.id}/pin", headers=full, json={"pin": "2580"})
    j = client.post("/api/totem/identificar/documento", headers=h(t), json={"documento": cenario.bruno.cpf, "pin": "2580"}).json()
    assert j["permitido"] is False and j["acionamento"] is None and sim.GIROS == []


# ------------------------------------------------------------------------------------------------ agente local
def test_agente_local_busca_executa_e_devolve(client, db, full, cenario, relogio):
    c = nova_catraca(client, full, modo="agente")
    ag = criar_totem(client, full, tipo="agente")
    r = client.post(f"/api/acesso/catracas/{c['id']}/liberar", headers=full, json={"motivo": "Aluna esqueceu o celular", "aluno_id": cenario.ana.id})
    assert r.status_code == 200
    reg_id = r.json()["registro_id"]
    assert r.json()["acionamento"]["status"] == "pendente"
    cmds = client.get("/api/catraca-agente/comandos", headers=h(ag)).json()
    assert len(cmds) == 1 and cmds[0]["catraca"]["senha"] == "segredo1" and cmds[0]["sentido"] == "entrada"
    assert client.get("/api/catraca-agente/comandos", headers=h(ag)).json() == []  # já entregue
    ok = client.post(f"/api/catraca-agente/comandos/{cmds[0]['id']}/resultado", headers=h(ag), json={"ok": True, "mensagem": "Giro liberado."})
    assert ok.status_code == 200
    db.expire_all()
    assert db.get(RegistroAcesso, reg_id).catraca_status == "liberada"
    # comando velho expira em vez de girar atrasado
    client.post(f"/api/acesso/catracas/{c['id']}/liberar", headers=full, json={"motivo": "Teste de expiração"})
    relogio.agora = AGORA + timedelta(minutes=2)
    assert client.get("/api/catraca-agente/comandos", headers=h(ag)).json() == []
    assert db.scalar(select(ComandoCatraca).where(ComandoCatraca.status == "expirado")) is not None


def test_liberacao_manual_exige_motivo_permissao_e_audita(client, db, full, secretaria, cenario):
    assert client.post("/api/acesso/liberar", headers=full, json={"motivo": ""}).status_code == 422
    assert client.post("/api/acesso/liberar", headers=secretaria, json={"motivo": "Visita"}).status_code == 403
    r = client.post("/api/acesso/liberar", headers=full, json={"motivo": "Aluna sem celular", "aluno_id": cenario.ana.id})
    assert r.status_code == 200 and r.json()["permitido"]
    reg = db.get(RegistroAcesso, r.json()["registro_id"])
    assert reg.metodo == "manual" and reg.usuario_nome == "Usuário Full" and "Aluna sem celular" in reg.motivo
    aud = db.scalar(select(Auditoria).where(Auditoria.acao == "liberar_manual"))
    assert aud and "Aluna sem celular" in aud.descricao
