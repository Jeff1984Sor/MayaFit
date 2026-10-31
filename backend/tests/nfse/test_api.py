"""Fluxos completos pela API (modo simulado, sem rede): configuração, certificado, emissão avulsa, lote a partir de
recebimentos, idempotência, retentativa com consulta, cancelamento, e-mail, permissões, worker e demonstração."""

from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import settings
from app.core.models import Auditoria
from app.modules.nfse import certificado as certs
from app.modules.nfse import demo, servico, tarefas
from app.modules.nfse.models import ConfigNfse, Modo, NotaEvento, NotaFiscal, StatusNota
from app.modules.nfse.provedores.base import FalhaComunicacao
from app.modules.nfse.provedores.nacional import simulador
from tests.nfse.conftest import CNPJ, configurar

A = "/api/nfse"


# ------------------------------------------------------------------------------------------------- configuração
def test_configuracao_inicial_lista_pendencias(client, adm):
    r = client.get(f"{A}/configuracao", headers=adm)
    assert r.status_code == 200
    d = r.json()
    assert d["modo"] == "simulado" and d["provedor"] == "nacional"
    campos = {p["campo"] for p in d["pendencias"]}
    assert {"ativo", "cnpj", "codigo_municipio"} <= campos
    assert d["certificado"]["situacao"] == "ausente"


def test_salvar_configuracao_calcula_codigo_nacional_e_audita(client, adm, db):
    corpo = {"ativo": True, "provedor": "nacional", "modo": "simulado", "cnpj": "11.222.333/0001-81",
             "razao_social": "Estudio", "codigo_municipio": "3509502", "regime": "simples", "item_lista_servico": "04.08",
             "aliquota_iss": "3.00", "serie": "001", "proximo_numero": 10, "percentual_tributos_sn": "6.00"}
    r = client.put(f"{A}/configuracao", json=corpo, headers=adm)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["cnpj"] == CNPJ and d["codigo_tributacao_nacional"] == "040801" and d["serie"] == "1"
    assert not [p for p in d["pendencias"] if p["nivel"] == "erro"]
    assert db.scalar(select(func.count()).select_from(Auditoria).where(Auditoria.entidade == "nfse_config")) == 1


def test_configuracao_recusa_cnpj_invalido(client, adm):
    r = client.put(f"{A}/configuracao", json={"cnpj": "11222333000180"}, headers=adm)
    assert r.status_code == 422


def test_modo_producao_fora_do_servidor_de_producao_e_pendencia(client, adm, db):
    configurar(db, modo=Modo.producao)
    d = client.get(f"{A}/configuracao", headers=adm).json()
    assert d["emissao_real_liberada"] is False
    assert any(p["campo"] == "modo" and p["nivel"] == "erro" for p in d["pendencias"])


def test_certificado_a1_cifrado_validade_e_cnpj(client, adm, db):
    configurar(db)
    pfx = certs.gerar_autoassinado(cnpj=CNPJ, razao="ESTUDIO TESTE", senha="segredo", dias=20)
    r = client.post(f"{A}/configuracao/certificado", data={"senha": "segredo"},
                    files={"arquivo": ("cert.pfx", pfx, "application/x-pkcs12")}, headers=adm)
    assert r.status_code == 200, r.text
    c = r.json()["certificado"]
    assert c["configurado"] and c["cnpj"] == CNPJ and c["cnpj_confere"] is True
    assert c["situacao"] == "vencendo" and c["titular"] == "ESTUDIO TESTE"
    cfg = db.get(ConfigNfse, 1)
    db.refresh(cfg)
    assert pfx not in cfg.certificado_pfx_cifrado and b"segredo" not in cfg.certificado_senha_cifrada
    assert "segredo" not in r.text
    aud = db.scalars(select(Auditoria).where(Auditoria.acao == "certificado")).all()
    assert aud and all("segredo" not in (a.descricao or "") for a in aud)


def test_certificado_senha_errada(client, adm):
    pfx = certs.gerar_autoassinado(senha="certa")
    r = client.post(f"{A}/configuracao/certificado", data={"senha": "errada"},
                    files={"arquivo": ("c.pfx", pfx, "application/x-pkcs12")}, headers=adm)
    assert r.status_code == 422 and "senha" in r.json()["detail"]


def test_certificado_de_outro_cnpj_bloqueia(client, adm, db):
    configurar(db)
    pfx = certs.gerar_autoassinado(cnpj="99888777000105", senha="x")
    d = client.post(f"{A}/configuracao/certificado", data={"senha": "x"},
                    files={"arquivo": ("c.pfx", pfx, "application/x-pkcs12")}, headers=adm).json()
    assert d["certificado"]["cnpj_confere"] is False
    assert any(p["campo"] == "certificado" and p["nivel"] == "erro" for p in d["pendencias"])


def test_descobrir_municipio_pelo_cep(client, adm, monkeypatch):
    monkeypatch.setattr("app.modules.alunos.servico.consultar_viacep",
                        lambda cep: {"ibge": "3550308", "localidade": "São Paulo", "uf": "SP"})
    d = client.get(f"{A}/configuracao/municipio", params={"cep": "01310-100"}, headers=adm).json()
    assert d["codigo_municipio"] == "3550308" and d["provedor"] == "sao_paulo"


def test_testar_configuracao_simulado(client, adm, db):
    configurar(db)
    r = client.post(f"{A}/configuracao/testar", headers=adm)
    assert r.status_code == 200 and "validada no schema oficial" in r.json()["mensagem"]


# ------------------------------------------------------------------------------------------------- emissão avulsa
def test_emissao_avulsa_para_aluno(client, adm, db, cenario, emails):
    configurar(db)
    r = client.post(f"{A}/notas", json={"tomador": {"tipo": "aluno", "aluno_id": cenario.maria.id},
                                        "valor": "300.00", "descricao": "Pilates 2x"}, headers=adm)
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["status"] == "emitida" and n["chave_acesso"] and len(n["chave_acesso"]) == 50
    assert n["valor_iss"] == "6.00" and n["tomador_documento"] == cenario.maria.cpf
    assert "Maria Souza" in n["discriminacao"] and "R$ 300,00" in n["discriminacao"]
    assert n["tem_xml_enviado"] and n["tem_pdf"]
    assert [e["tipo"] for e in n["eventos"]] == ["fila", "envio", "emitida", "email"]
    assert emails and emails[0][0] == ["maria@exemplo.com"]
    pdf = client.get(f"{A}/notas/{n['id']}/pdf", headers=adm)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    xml = client.get(f"{A}/notas/{n['id']}/xml", headers=adm)
    assert xml.status_code == 200 and b"<DPS" in xml.content


def test_emissao_avulsa_exige_cpf_valido(client, adm, db, cenario):
    configurar(db)
    r = client.post(f"{A}/notas", json={"tomador": {"tipo": "aluno", "aluno_id": cenario.sem_cpf.id}, "valor": "10"},
                    headers=adm)
    assert r.status_code == 422 and "CPF" in r.json()["detail"]


def test_emissao_avulsa_para_empresa(client, adm, db):
    configurar(db, enviar_email_aluno=False)
    r = client.post(f"{A}/notas", json={"tomador": {"tipo": "empresa", "documento": "11.222.333/0001-81",
                                                    "nome": "Empresa Parceira"}, "valor": "1000",
                                        "discriminacao": "Aulas in company"}, headers=adm)
    assert r.status_code == 201 and r.json()["status"] == "emitida"
    assert r.json()["discriminacao"] == "Aulas in company"


def test_emissao_bloqueada_com_configuracao_incompleta(client, adm, db, cenario):
    r = client.post(f"{A}/notas", json={"tomador": {"tipo": "aluno", "aluno_id": cenario.maria.id}, "valor": "10"},
                    headers=adm)
    assert r.status_code == 409 and "Configuração incompleta" in r.json()["detail"]


def test_rejeicao_mapeada_correcao_e_reenvio(client, adm, db, cenario):
    configurar(db, enviar_email_aluno=False)
    r = client.post(f"{A}/notas", json={"tomador": {"tipo": "pessoa", "documento": "52998224725", "nome": "Ana"},
                                        "valor": "50", "discriminacao": "Aula [REJEITAR]"}, headers=adm)
    n = r.json()
    assert n["status"] == "rejeitada"
    assert n["erros"][0]["codigo"] == "E0310" and n["erros"][0]["acao"]
    r = client.patch(f"{A}/notas/{n['id']}", json={"discriminacao": "Aula avulsa de Pilates"}, headers=adm)
    assert r.status_code == 200
    r = client.post(f"{A}/notas/{n['id']}/reprocessar", headers=adm)
    assert r.json()["status"] == "emitida" and r.json()["numero_dps"] == n["numero_dps"]  # mesmo número


# ------------------------------------------------------------------------------------------------- recebimentos
def test_lista_recebimentos_pagos_com_situacao(client, adm, db, cenario):
    configurar(db)
    itens = client.get(f"{A}/recebimentos", params={"situacao": "todos"}, headers=adm).json()
    ids = {i["id"] for i in itens}
    assert ids == {cenario.r1.id, cenario.r2.id, cenario.r3.id}  # o aberto fica de fora
    sem = next(i for i in itens if i["id"] == cenario.r3.id)
    assert "CPF" in sem["problema"]


def test_lote_a_partir_de_recebimentos_e_idempotente(client, adm, db, cenario):
    configurar(db, enviar_email_aluno=False)
    ids = [cenario.r1.id, cenario.r2.id, cenario.r3.id, cenario.aberto.id]
    r = client.post(f"{A}/recebimentos/emitir", json={"ids": ids}, headers=adm)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["criadas"] == 2 and d["processadas_agora"] == 2
    assert {i["id"] for i in d["ignoradas"]} == {cenario.r3.id, cenario.aberto.id}
    assert all(n["status"] == "emitida" for n in d["notas"])
    # de novo: nada duplica
    d2 = client.post(f"{A}/recebimentos/emitir", json={"ids": ids}, headers=adm).json()
    assert d2["criadas"] == 0 and d2["ja_existiam"] == 2
    assert db.scalar(select(func.count()).select_from(NotaFiscal)) == 2
    # agora ninguém aparece como "sem nota"
    sem = client.get(f"{A}/recebimentos", headers=adm).json()
    assert {i["id"] for i in sem} == {cenario.r3.id}


def test_raio_x_de_recebimentos(client, adm, db, cenario):
    configurar(db)
    d = client.post(f"{A}/raio-x", json={"recebimentos": [cenario.r1.id, cenario.r3.id]}, headers=adm).json()
    assert d["pode_emitir"] is False
    titulos = {a["titulo"] for a in d["achados"]}
    assert "CPF obrigatório" in titulos and "Ambiente de teste" in titulos
    assert d["valor_total"] == "500.00" and d["iss_estimado"] == "10.00"
    assert db.scalar(select(func.count()).select_from(NotaFiscal)) == 0  # raio-x não grava


def test_raio_x_avisa_nota_em_dobro_e_ja_existente(client, adm, db, cenario):
    configurar(db, enviar_email_aluno=False)
    client.post(f"{A}/recebimentos/emitir", json={"ids": [cenario.r1.id]}, headers=adm)
    d = client.post(f"{A}/raio-x", json={"recebimentos": [cenario.r1.id]}, headers=adm).json()
    assert any(a["titulo"] == "Já existe nota" for a in d["achados"])
    d = client.post(f"{A}/raio-x", json={"avulsa": {"tomador": {"tipo": "aluno", "aluno_id": cenario.maria.id},
                                                    "valor": "300.00"}}, headers=adm).json()
    assert any(a["titulo"] == "Possível nota em dobro" for a in d["achados"])
    assert d["pode_emitir"] is True


# ------------------------------------------------------------------------------------------------- fila e retentativa
def test_falha_de_comunicacao_consulta_antes_de_reenviar(db, cenario):
    """A primeira chamada CHEGA à Sefin (nota gerada) mas a resposta se perde. Na retentativa o MayaFit consulta a
    DPS e encontra a nota: nenhum segundo POST, nenhuma nota em dobro."""
    configurar(db, enviar_email_aluno=False)
    posts = []

    def transporte(metodo, url, **k):
        resp = simulador.transporte(metodo, url, **k)
        if metodo == "POST" and url.endswith("/nfse"):
            posts.append(url)
            if len(posts) == 1:
                raise FalhaComunicacao("timeout depois de entregue")
        return resp

    servico.definir_transporte(transporte)
    nota = servico.enfileirar_recebimento(db, cenario.r1.id)
    db.commit()
    servico.processar(db, nota)
    assert nota.status == StatusNota.pendente and nota.falha_comunicacao and nota.tentativas == 1
    assert nota.proxima_tentativa_em is not None
    servico.processar(db, nota)
    assert nota.status == StatusNota.emitida and nota.chave_acesso
    assert len(posts) == 1
    tipos = [e.tipo for e in db.scalars(select(NotaEvento).where(NotaEvento.nota_id == nota.id))]
    assert "falha_comunicacao" in tipos and "consulta" in tipos


def test_falhas_seguidas_viram_falha_definitiva(db, cenario, monkeypatch):
    configurar(db)

    def fora_do_ar(*a, **k):
        raise FalhaComunicacao("fora do ar")

    servico.definir_transporte(fora_do_ar)
    nota = servico.enfileirar_recebimento(db, cenario.r1.id)
    db.commit()
    for _ in range(8):
        nota.status = StatusNota.pendente if nota.status == StatusNota.pendente else nota.status
        servico.processar(db, nota)
    assert nota.status == StatusNota.falha and nota.erros[0]["codigo"] == "COMUNICACAO"


def test_worker_processa_fila_e_emissao_automatica(db, cenario):
    configurar(db, emissao_automatica=True, automatica_desde=cenario.hoje, enviar_email_aluno=False)
    tarefas.automatica()
    db.expire_all()
    notas = db.scalars(select(NotaFiscal)).all()
    assert {n.conta_receber_id for n in notas} == {cenario.r1.id, cenario.r2.id}  # sem CPF fica de fora
    assert all(n.status == StatusNota.emitida for n in notas)
    tarefas.automatica()  # idempotente
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(NotaFiscal)) == 2
    tarefas.fila()
    tarefas.certificado()


def test_automatica_desligada_nao_emite(db, cenario):
    configurar(db, emissao_automatica=False)
    assert servico.emitir_automaticas(db) == 0


def test_emissao_real_bloqueada_fora_de_prod(db, cenario, monkeypatch):
    configurar(db)
    nota = servico.enfileirar_recebimento(db, cenario.r1.id)
    nota.modo = Modo.producao
    db.commit()
    servico.processar(db, nota)
    assert nota.status == StatusNota.rejeitada and "bloqueada" in nota.erros[0]["mensagem"]
    assert settings.ambiente != "prod"


def test_nota_presa_em_processando_e_destravada(db, cenario):
    configurar(db)
    nota = servico.enfileirar_recebimento(db, cenario.r1.id)
    nota.status = StatusNota.processando
    db.commit()
    assert servico.destravar_processando(db, minutos=-1) == 1
    assert nota.status == StatusNota.pendente and nota.falha_comunicacao


# ------------------------------------------------------------------------------------------------- cancelamento
def test_cancelamento_libera_nova_emissao_do_recebimento(client, adm, db, cenario):
    configurar(db, enviar_email_aluno=False)
    n = client.post(f"{A}/recebimentos/emitir", json={"ids": [cenario.r1.id]}, headers=adm).json()["notas"][0]
    r = client.post(f"{A}/notas/{n['id']}/cancelar", json={"codigo": "1", "motivo": "curto"}, headers=adm)
    assert r.status_code == 422
    r = client.post(f"{A}/notas/{n['id']}/cancelar",
                    json={"codigo": "1", "motivo": "Valor lançado errado no recebimento"}, headers=adm)
    assert r.status_code == 200 and r.json()["status"] == "cancelada"
    assert r.json()["chave_emissao"].startswith(f"rec:{cenario.r1.id}:x")
    d = client.post(f"{A}/recebimentos/emitir", json={"ids": [cenario.r1.id]}, headers=adm).json()
    assert d["criadas"] == 1
    r = client.post(f"{A}/notas/{n['id']}/cancelar",
                    json={"codigo": "1", "motivo": "Valor lançado errado no recebimento"}, headers=adm)
    assert r.status_code == 409


# ------------------------------------------------------------------------------------------------- listas e painel
def test_lista_filtros_e_painel(client, adm, db, cenario):
    configurar(db, enviar_email_aluno=False)
    client.post(f"{A}/recebimentos/emitir", json={"ids": [cenario.r1.id, cenario.r2.id]}, headers=adm)
    client.post(f"{A}/notas", json={"tomador": {"tipo": "pessoa", "documento": "52998224725", "nome": "Ana"},
                                    "valor": "50", "discriminacao": "x [REJEITAR]"}, headers=adm)
    d = client.get(f"{A}/notas", headers=adm).json()
    assert d["total"] == 3 and d["contagens"] == {"emitida": 2, "rejeitada": 1}
    assert client.get(f"{A}/notas", params={"status": "atencao"}, headers=adm).json()["total"] == 1
    assert client.get(f"{A}/notas", params={"q": "Maria"}, headers=adm).json()["total"] == 1
    p = client.get(f"{A}/painel", headers=adm).json()
    assert p["notas_mes"] == 2 and Decimal(p["valor_mes"]) == Decimal("750.50")
    assert Decimal(p["iss_estimado_mes"]) == Decimal("15.01") and p["iss_no_das"] is True
    assert p["recebimentos_sem_nota"] == 1 and len(p["serie"]) == 6
    assert any("atenção" in x["mensagem"] for x in p["pendencias"])


# ------------------------------------------------------------------------------------------------- permissões
def test_professor_e_secretaria_nao_acessam_por_padrao(client, professor, secretaria):
    for h in (professor, secretaria):
        assert client.get(f"{A}/painel", headers=h).status_code == 403
        assert client.get(f"{A}/notas", headers=h).status_code == 403
        assert client.put(f"{A}/configuracao", json={}, headers=h).status_code == 403


def test_sem_login(client):
    assert client.get(f"{A}/notas").status_code == 401


def test_permissoes_por_acao():
    from app.core.permissoes import TODAS, permissao_da_rota

    assert {"nfse.ver", "nfse.emitir", "nfse.cancelar", "nfse.configurar"} <= TODAS
    assert permissao_da_rota("GET", "/api/nfse/notas") == (True, "nfse.ver")
    assert permissao_da_rota("POST", "/api/nfse/notas") == (True, "nfse.emitir")
    assert permissao_da_rota("POST", "/api/nfse/notas/1/cancelar") == (True, "nfse.cancelar")
    assert permissao_da_rota("PUT", "/api/nfse/configuracao") == (True, "nfse.configurar")
    assert permissao_da_rota("POST", "/api/nfse/configuracao/certificado") == (True, "nfse.configurar")
    assert permissao_da_rota("DELETE", "/api/nfse/configuracao/certificado") == (True, "nfse.configurar")
    assert permissao_da_rota("GET", "/api/nfse/recebimentos") == (True, "nfse.emitir")
    assert permissao_da_rota("GET", "/api/nfse/configuracao") == (True, "nfse.ver")


# ------------------------------------------------------------------------------------------------- demonstração
def test_popular_demo_idempotente(db):
    r1 = demo.popular_demo(db)
    assert r1["criadas"] == len(demo.EXEMPLOS)
    status = {n.chave_emissao.split(":x")[0]: n.status for n in db.scalars(select(NotaFiscal))}
    assert StatusNota.rejeitada in status.values() and StatusNota.cancelada in status.values()
    assert StatusNota.pendente in status.values()
    assert demo.popular_demo(db)["criadas"] == 0
    assert db.scalar(select(func.count()).select_from(NotaFiscal)) == len(demo.EXEMPLOS)
