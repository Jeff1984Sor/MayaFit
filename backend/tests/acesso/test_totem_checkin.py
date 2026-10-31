"""Totem: pareamento por token do dispositivo, check-in facial/CPF+PIN/QR, presença na aula e LGPD."""

from datetime import date, timedelta

from sqlalchemy import select

from app.core.models import Auditoria
from app.modules.acesso import servico as srv
from app.modules.acesso.models import ConsentimentoBiometria, DescritorFacial, Dispositivo, RegistroAcesso
from app.modules.agenda.models import Reserva
from tests.acesso.conftest import AGORA, PROVA_VIDA, cadastrar_rosto, criar_totem, h, parcela, ruido, vetor

ROSTO_ANA = vetor(1)
ROSTO_BRUNO = vetor(2)


# ------------------------------------------------------------------------------------------------ dispositivo
def test_token_do_dispositivo_guardado_so_como_hash_e_revogavel(client, db, full, cenario):
    t = criar_totem(client, full)
    token = t["X-Dispositivo-Token"]
    assert token.startswith("mfdisp_")
    d = db.get(Dispositivo, t["_id"])
    assert d.token_hash != token and len(d.token_hash) == 64 and d.token_final == token[-4:]
    assert client.get("/api/totem/me", headers=h(t)).status_code == 200
    assert client.get("/api/acesso/dispositivos", headers=full).json()[0].get("token") is None

    assert client.post(f"/api/acesso/dispositivos/{t['_id']}/revogar", headers=full).status_code == 200
    r = client.get("/api/totem/me", headers=h(t))
    assert r.status_code == 401 and "pareado" in r.json()["detail"]
    novo = client.post(f"/api/acesso/dispositivos/{t['_id']}/regenerar", headers=full).json()["token"]
    assert client.get("/api/totem/me", headers={"X-Dispositivo-Token": novo}).status_code == 200
    assert client.get("/api/totem/me", headers=h(t)).status_code == 401


def test_totem_sem_token_ou_token_de_agente_nao_entra(client, full, cenario):
    assert client.get("/api/totem/me").status_code == 401
    ag = criar_totem(client, full, tipo="agente")
    assert client.get("/api/totem/me", headers=h(ag)).status_code == 401
    assert client.get("/api/catraca-agente/comandos", headers=h(ag)).status_code == 200


def test_token_da_equipe_nao_abre_o_totem(client, full, cenario):
    assert client.get("/api/totem/me", headers=full).status_code == 401


# ------------------------------------------------------------------------------------------------ facial
def test_checkin_facial_reconhece_registra_presenca_e_nao_guarda_o_descritor(client, db, full, cenario):
    cadastrar_rosto(client, full, cenario.ana.id, ROSTO_ANA)
    cadastrar_rosto(client, full, cenario.bruno.id, ROSTO_BRUNO)
    t = criar_totem(client, full)
    r = client.post("/api/totem/identificar/facial", headers=h(t), json={"descritor": ruido(ROSTO_ANA, 0.2), "prova_vida": PROVA_VIDA})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["permitido"] is True
    assert j["primeiro_nome"] == "Ana"
    assert j["aniversario"] is True and j["titulo"] == "Feliz aniversário, Ana!"
    assert j["aula"]["servico"] == "Pilates" and j["aula"]["inicio"] == "09:00:00"
    assert j["presenca_registrada"] is True
    assert j["acionamento"]["status"] == "sem_catraca"
    db.expire_all()
    res = db.get(Reserva, cenario.reserva.id)
    assert res.confirmada_em is not None  # presença pela regra da agenda
    reg = db.get(RegistroAcesso, j["registro_id"])
    assert reg.metodo == "facial" and reg.similaridade > 0.9 and reg.reserva_id == res.id
    # só os 2 descritores cadastrados existem: o do momento não foi gravado
    assert db.scalar(select(DescritorFacial.id).where(DescritorFacial.aluno_id == cenario.ana.id)) is not None
    assert len(list(db.scalars(select(DescritorFacial)))) == 2


def test_descritor_cifrado_no_banco(client, db, full, cenario):
    cadastrar_rosto(client, full, cenario.ana.id, ROSTO_ANA)
    d = db.scalar(select(DescritorFacial))
    assert d.descritor_cifrado.startswith(b"gAAAA")  # Fernet
    assert d.dimensao == 128
    v = srv.decifrar_descritor(d.descritor_cifrado)
    assert abs(sum(x * x for x in v) - 1) < 1e-3


def test_rosto_desconhecido_e_negado_e_registrado(client, db, full, cenario):
    cadastrar_rosto(client, full, cenario.ana.id, ROSTO_ANA)
    t = criar_totem(client, full)
    j = client.post("/api/totem/identificar/facial", headers=h(t), json={"descritor": vetor(77), "prova_vida": PROVA_VIDA}).json()
    assert j["permitido"] is False and j["codigo"] == "nao_reconhecido"
    reg = db.get(RegistroAcesso, j["registro_id"])
    assert reg.aluno_id is None and not reg.permitido


def test_sem_prova_de_vida_pede_para_piscar(client, full, cenario):
    cadastrar_rosto(client, full, cenario.ana.id, ROSTO_ANA)
    t = criar_totem(client, full)
    j = client.post("/api/totem/identificar/facial", headers=h(t), json={"descritor": ROSTO_ANA}).json()
    assert j["permitido"] is False and j["codigo"] == "sem_prova_de_vida" and "Pisque" in j["motivo"]


def test_mensalidade_atrasada_nega_com_motivo(client, db, full, cenario):
    parcela(db, cenario.ana, date(2026, 10, 5), cenario.contrato)
    db.commit()
    cadastrar_rosto(client, full, cenario.ana.id, ROSTO_ANA)
    t = criar_totem(client, full)
    j = client.post("/api/totem/identificar/facial", headers=h(t), json={"descritor": ROSTO_ANA, "prova_vida": PROVA_VIDA}).json()
    assert j["permitido"] is False
    assert j["motivo"] == "Mensalidade em atraso desde 05/10. Procure a recepção."
    db.expire_all()
    assert db.get(Reserva, cenario.reserva.id).confirmada_em is None


def test_cedo_demais_explica_horario(client, full, cenario, relogio):
    relogio.agora = AGORA - timedelta(minutes=40)  # 08:10
    cadastrar_rosto(client, full, cenario.ana.id, ROSTO_ANA)
    t = criar_totem(client, full)
    j = client.post("/api/totem/identificar/facial", headers=h(t), json={"descritor": ROSTO_ANA, "prova_vida": PROVA_VIDA}).json()
    assert j["permitido"] is False and "08:30" in j["motivo"]


# ------------------------------------------------------------------------------------------------ LGPD
def test_sem_consentimento_nao_cadastra_rosto(client, full, cenario):
    r = client.post(f"/api/acesso/alunos/{cenario.ana.id}/descritores", headers=full, json={"descritores": [ROSTO_ANA], "prova_vida": PROVA_VIDA})
    assert r.status_code == 409 and "consentimento" in r.json()["detail"]


def test_consentimento_registra_termo_quem_e_quando(client, db, full, cenario):
    r = client.post(f"/api/acesso/alunos/{cenario.ana.id}/consentimento", headers=full, json={"aceite": True})
    assert r.status_code == 201
    c = db.scalar(select(ConsentimentoBiometria))
    assert c.coletado_por_nome == "Usuário Full" and "LGPD" in c.texto_termo and len(c.hash_termo) == 64
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "consentimento")) is not None


def test_apagar_biometria_remove_descritores_e_revoga(client, db, full, cenario):
    cadastrar_rosto(client, full, cenario.ana.id, ROSTO_ANA)
    r = client.post(f"/api/acesso/alunos/{cenario.ana.id}/biometria/apagar", headers=full, json={"motivo": "Pedido da aluna"})
    assert r.status_code == 200 and "1 descritor" in r.json()["mensagem"]
    assert db.scalar(select(DescritorFacial)) is None
    c = db.scalar(select(ConsentimentoBiometria))
    db.refresh(c)
    assert c.revogado_em is not None and c.motivo_revogacao == "Pedido da aluna"
    t = criar_totem(client, full)
    j = client.post("/api/totem/identificar/facial", headers=h(t), json={"descritor": ROSTO_ANA, "prova_vida": PROVA_VIDA}).json()
    assert j["permitido"] is False
    det = client.get(f"/api/acesso/alunos/{cenario.ana.id}", headers=full).json()
    assert det["consentimento"] is None and det["descritores"] == 0 and len(det["historico_consentimentos"]) == 1


def test_maximo_de_descritores_substitui_os_mais_antigos(client, db, full, cenario):
    client.post(f"/api/acesso/alunos/{cenario.ana.id}/consentimento", headers=full, json={"aceite": True})
    for i in range(3):
        r = client.post(f"/api/acesso/alunos/{cenario.ana.id}/descritores", headers=full,
                        json={"descritores": [ruido(ROSTO_ANA, 0.1, i), ruido(ROSTO_ANA, 0.1, 10 + i)], "prova_vida": PROVA_VIDA})
        assert r.status_code == 201
    assert len(list(db.scalars(select(DescritorFacial)))) == srv.MAX_DESCRITORES_POR_ALUNO


# ------------------------------------------------------------------------------------------------ CPF/código + PIN
def test_documento_com_pin(client, db, full, cenario):
    t = criar_totem(client, full)
    cpf = cenario.ana.cpf
    j = client.post("/api/totem/identificar/documento", headers=h(t), json={"documento": cpf, "pin": "2580"}).json()
    assert j["permitido"] is False and "não tem PIN" in j["motivo"]
    assert client.put(f"/api/acesso/alunos/{cenario.ana.id}/pin", headers=full, json={"pin": "1234"}).status_code == 422
    assert client.put(f"/api/acesso/alunos/{cenario.ana.id}/pin", headers=full, json={"pin": "2580"}).status_code == 200
    j = client.post("/api/totem/identificar/documento", headers=h(t), json={"documento": "4321", "pin": "2580"}).json()
    assert j["permitido"] is True and j["primeiro_nome"] == "Ana"
    assert db.get(RegistroAcesso, j["registro_id"]).metodo == "codigo"
    j = client.post("/api/totem/identificar/documento", headers=h(t), json={"documento": cpf, "pin": "9999"}).json()
    assert j["permitido"] is False and j["motivo"] == "CPF/código ou PIN incorretos."
    j = client.post("/api/totem/identificar/documento", headers=h(t), json={"documento": "00000000000", "pin": "2580"}).json()
    assert j["permitido"] is False and j["motivo"] == "CPF/código ou PIN incorretos."


def test_pin_errado_cinco_vezes_bloqueia(client, full, cenario):
    t = criar_totem(client, full)
    client.put(f"/api/acesso/alunos/{cenario.ana.id}/pin", headers=full, json={"pin": "2580"})
    for _ in range(5):
        client.post("/api/totem/identificar/documento", headers=h(t), json={"documento": "4321", "pin": "1357"})
    j = client.post("/api/totem/identificar/documento", headers=h(t), json={"documento": "4321", "pin": "2580"}).json()
    assert j["permitido"] is False and "Muitas tentativas" in j["motivo"]


# ------------------------------------------------------------------------------------------------ QR do app
def test_qr_do_app_uso_unico(client, db, full, cenario):
    from app.modules.app_aluno import servico as app_srv

    access = app_srv.emitir_tokens(cenario.ana.id)["access_token"]
    r = client.get("/api/aluno-app/acesso/qr", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.text
    valor = r.json()["qr"]
    assert valor.startswith("MFQR1.")
    t = criar_totem(client, full)
    j = client.post("/api/totem/identificar/qr", headers=h(t), json={"qr": valor}).json()
    assert j["permitido"] is True and db.get(RegistroAcesso, j["registro_id"]).metodo == "qr"
    j2 = client.post("/api/totem/identificar/qr", headers=h(t), json={"qr": valor}).json()
    assert j2["permitido"] is False and "já foi usado" in j2["motivo"]


def test_qr_vencido(client, full, cenario):
    valor, _ = srv.emitir_qr(cenario.ana.id, AGORA - timedelta(minutes=5))
    t = criar_totem(client, full)
    j = client.post("/api/totem/identificar/qr", headers=h(t), json={"qr": valor}).json()
    assert j["permitido"] is False and "vencido" in j["motivo"]


def test_rota_qr_do_app_exige_sessao_do_aluno(client, full):
    assert client.get("/api/aluno-app/acesso/qr").status_code == 401
    assert client.get("/api/aluno-app/acesso/qr", headers=full).status_code == 401


# ------------------------------------------------------------------------------------------------ cadastro no totem
def test_cadastro_do_rosto_no_totem_com_codigo_da_recepcao(client, db, full, cenario):
    t = criar_totem(client, full)
    codigo = client.post(f"/api/acesso/alunos/{cenario.ana.id}/codigo-totem", headers=full).json()["codigo"]
    assert client.post("/api/totem/cadastro/iniciar", headers=h(t), json={"documento": "4321", "codigo": "000000" if codigo != "000000" else "111111"}).status_code == 403
    ini = client.post("/api/totem/cadastro/iniciar", headers=h(t), json={"documento": cenario.ana.cpf, "codigo": codigo})
    assert ini.status_code == 200 and ini.json()["primeiro_nome"] == "Ana" and "LGPD" in ini.json()["termo"]
    r = client.post("/api/totem/cadastro/concluir", headers=h(t), json={"documento": cenario.ana.cpf, "codigo": codigo, "aceite": True,
                                                                       "descritores": [ROSTO_ANA, ruido(ROSTO_ANA, 0.1)], "prova_vida": PROVA_VIDA})
    assert r.status_code == 200, r.text
    c = db.scalar(select(ConsentimentoBiometria))
    assert c.canal == "totem" and c.coletado_por_nome.startswith("Usuário Full")
    assert len(list(db.scalars(select(DescritorFacial)))) == 2
    # uso único
    assert client.post("/api/totem/cadastro/iniciar", headers=h(t), json={"documento": cenario.ana.cpf, "codigo": codigo}).status_code == 403
    j = client.post("/api/totem/identificar/facial", headers=h(t), json={"descritor": ruido(ROSTO_ANA, 0.15, 5), "prova_vida": PROVA_VIDA}).json()
    assert j["permitido"] is True


def test_codigo_do_totem_vence(client, full, cenario, relogio):
    t = criar_totem(client, full)
    codigo = client.post(f"/api/acesso/alunos/{cenario.ana.id}/codigo-totem", headers=full).json()["codigo"]
    relogio.agora = AGORA + timedelta(minutes=16)
    assert client.post("/api/totem/cadastro/iniciar", headers=h(t), json={"documento": "4321", "codigo": codigo}).status_code == 403
