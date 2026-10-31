"""Admin MayaFit: guarda, estúdios (ficha, status, domínios, extras, uso), usuários, planos, indicação, contratos."""

from datetime import date, timedelta

from sqlalchemy import select

from app.controle.models import Cliente, Cobranca, EventoCliente, SessaoControle
from tests.admin_mayacorp.conftest import criar_estudio, plano
from tests.conftest import auth, criar_usuario, entrar


def test_guarda_so_mayacorp_e_administrador(client, db, fundacao, adm):
    assert client.get("/api/admin/clientes", headers=adm).status_code == 200
    criar_usuario(db, "Secretária", email="sec@x.com.br", login="sec")
    sec = auth(entrar(client, "sec").json()["access_token"])
    r = client.get("/api/admin/clientes", headers=sec)
    assert r.status_code == 403 and r.json()["detail"] == "Área exclusiva do admin MayaFit."
    fundacao.entrar_no("studio-x")  # num estúdio cliente o admin não abre, nem para o administrador
    assert client.get("/api/admin/resumo", headers=adm).status_code == 403
    fundacao.atual = None  # modo de um banco só
    assert client.get("/api/admin/planos", headers=adm).status_code == 403
    assert client.get("/api/admin/planos").status_code == 401


def test_planos_padrao_e_edicao(client, fundacao, adm):
    lista = client.get("/api/admin/planos", headers=adm).json()
    assert [(p["nome"], p["preco_mensal"], p["usuarios"], p["alunos_ativos"]) for p in lista] == [
        ("Essencial", "49.90", 2, 60), ("Estúdio", "89.90", 5, 150), ("Pro", "149.90", 10, 350),
        ("Rede", "289.90", 25, None)]
    assert lista[0]["preco_aluno_excedente"] == "0.50" and lista[0]["preco_usuario_adicional"] == "14.90"
    pro = lista[2]
    corpo = {**pro, "preco_mensal": "159.90", "recursos": ["gestao", "ia"]}
    r = client.put(f"/api/admin/planos/{pro['id']}", headers=adm, json=corpo)
    assert r.status_code == 200 and r.json()["preco_mensal"] == "159.90"
    assert client.put(f"/api/admin/planos/{pro['id']}", headers=adm,
                      json={**corpo, "recursos": ["robo"]}).status_code == 400
    assert client.post("/api/admin/planos", headers=adm, json={**corpo, "nome": "rede"}).status_code == 409
    assert {x["chave"] for x in client.get("/api/admin/extras", headers=adm).json()} == {"receita_saude", "etl",
                                                                                         "catraca"}
    assert len(client.get("/api/admin/recursos", headers=adm).json()) == 10


def test_novo_estudio_com_teste_de_60_dias(client, fundacao, adm, emails_admin):
    est = plano(client, adm, "Estúdio")
    novo = criar_estudio(client, adm, plano_id=est["id"], extras=["etl", "inventado"],
                         dominios=["app.lumina.test"])
    assert novo["slug"] == "pilates-lumina" and novo["status"] == "teste"
    assert novo["teste_ate"] == (date.today() + timedelta(days=60)).isoformat()
    assert novo["documento"] == "12345678000195" and novo["extras"] == ["etl"] and novo["valor"] == "89.90"
    assert novo["convite"].endswith("tk-pilates-lumina")
    assert [d["host"] for d in novo["dominios"]] == ["pilates-lumina.mayafit.test", "app.lumina.test"]
    assert novo["dominios"][0]["padrao"] is True and novo["dominio_padrao"] == "pilates-lumina.mayafit.test"
    assert fundacao.provisionados[0]["primeiro_acesso"] is True and fundacao.provisionados[0]["dias_teste"] == 60
    para, assunto, corpo, _ = emails_admin[0]
    assert para == ["ana@lumina.com.br"] and "Bem-vindo ao MayaFit" in assunto and "60 dias de teste" in corpo
    assert "Equipe MayaFit" in corpo and "tk-pilates-lumina" in corpo
    with SessaoControle() as ctl:  # em teste nada é cobrado
        assert ctl.scalar(select(Cobranca.id)) is None
        assert [e.tipo for e in ctl.scalars(select(EventoCliente))] == ["criado"]
    assert client.post("/api/admin/clientes", headers=adm,
                       json={"nome": "Pilates Lumina", "admin_email": "x@y.com.br"}).status_code == 400  # slug repetido
    # sem teste: a 1ª mensalidade já nasce (vence em 3 dias)
    sem = criar_estudio(client, adm, nome="Studio Sem Teste", slug="sem-teste", plano_id=est["id"], dias_teste=0)
    assert sem["status"] == "ativo"
    cobs = client.get("/api/admin/cobrancas", headers=adm, params={"cliente_id": sem["id"]}).json()
    assert [(k["valor"], k["vencimento"]) for k in cobs] == [("89.90", (date.today() + timedelta(days=3)).isoformat())]


def test_ficha_status_dominios_e_linha_do_tempo(client, fundacao, adm, emails_admin):
    novo = criar_estudio(client, adm)
    cid = novo["id"]
    pro = plano(client, adm, "Pro")
    # o PUT grava a ficha inteira (campo ausente = vazio), como no MayaJus
    ficha = {"nome": "Pilates Lumina", "documento": "12.345.678/0001-95", "plano_id": pro["id"], "ciclo": "anual",
             "extras": ["catraca"]}
    r = client.put(f"/api/admin/clientes/{cid}", headers=adm, json=ficha)
    assert r.status_code == 200 and r.json()["plano"]["nome"] == "Pro" and r.json()["valor"] == "1499.00"
    assert client.put(f"/api/admin/clientes/{cid}", headers=adm, json={**ficha, "documento": "123"}).status_code == 400
    assert client.put(f"/api/admin/clientes/{cid}", headers=adm,
                      json={**ficha, "indicado_por_id": cid}).status_code == 400  # não indica a si mesmo
    r = client.post(f"/api/admin/clientes/{cid}/status", headers=adm, json={"status": "inativo"})
    assert r.json()["status"] == "inativo" and r.json()["status_rotulo"] == "Inativo (sem acesso)"
    assert client.get("/api/admin/clientes", headers=adm, params={"status": "inativo"}).json()[0]["id"] == cid
    assert client.get("/api/admin/clientes", headers=adm, params={"q": "12.345.678"}).json()[0]["id"] == cid
    # domínios
    r = client.post(f"/api/admin/clientes/{cid}/dominios", headers=adm, json={"host": "Sistema.Lumina.test"})
    assert r.status_code == 201 and "sistema.lumina.test" in [d["host"] for d in r.json()["dominios"]]
    assert client.post(f"/api/admin/clientes/{cid}/dominios", headers=adm,
                       json={"host": "sistema.lumina.test"}).status_code == 400
    doms = {d["host"]: d["id"] for d in r.json()["dominios"]}
    assert client.delete(f"/api/admin/clientes/{cid}/dominios/{doms['pilates-lumina.mayafit.test']}",
                         headers=adm).status_code == 400  # o endereço padrão fica
    r = client.delete(f"/api/admin/clientes/{cid}/dominios/{doms['sistema.lumina.test']}", headers=adm)
    assert [d["host"] for d in r.json()["dominios"]] == ["pilates-lumina.mayafit.test"]
    linha = client.get(f"/api/admin/clientes/{cid}/eventos", headers=adm).json()
    textos = [e["descricao"] for e in linha]
    assert textos[-1].startswith("Estúdio criado") and linha[0]["descricao"] == "Endereço removido: sistema.lumina.test"
    assert "Plano: sem plano (mensal) → Pro (anual)" in textos
    assert "Extras liberados: Integração com catraca (avulsa, para quem não tem o plano Rede)" in textos
    assert "Status: Em teste → Inativo (sem acesso)" in textos
    assert all(e["usuario"] == "Usuário Full" for e in linha)


def test_uso_foto_ou_coleta(client, fundacao, adm):
    cid = criar_estudio(client, adm, plano_id=plano(client, adm, "Essencial")["id"])["id"]
    fundacao.uso["pilates-lumina"] = {"alunos_ativos": 70, "usuarios": 3, "aulas_mes": 300}
    u = client.get(f"/api/admin/clientes/{cid}/uso", headers=adm).json()  # sem foto: coleta agora
    assert (u["alunos_ativos"], u["limite_alunos"], u["alunos_excedentes"]) == (70, 60, 10)
    assert (u["usuarios_excedentes"], u["valor_excedente"]) == (1, "19.90")  # 10 × 0,50 + 1 × 14,90
    with SessaoControle() as ctl:
        ctl.get(Cliente, cid).uso = {"alunos_ativos": 20, "usuarios": 1}
        ctl.commit()
    assert client.get(f"/api/admin/clientes/{cid}/uso", headers=adm).json()["alunos_ativos"] == 20  # foto do worker


def test_usuarios_do_estudio(client, db, fundacao, adm, emails_admin):
    cid = criar_estudio(client, adm)["id"]
    r = client.post(f"/api/admin/clientes/{cid}/usuarios", headers=adm,
                    json={"nome": "Beto", "email": "Beto@lumina.com.br", "perfil": "Secretária"})
    assert r.status_code == 201, r.text
    beto = r.json()
    assert beto["login"] == "beto" and beto["perfil"] == "Secretária" and "/redefinir-senha?token=" in beto["convite"]
    assert client.post(f"/api/admin/clientes/{cid}/usuarios", headers=adm,
                       json={"nome": "Outro", "email": "beto@lumina.com.br"}).status_code == 409
    lista = client.get(f"/api/admin/clientes/{cid}/usuarios", headers=adm).json()
    assert {u["login"] for u in lista} >= {"jeff", "beto"} and "ultimo_acesso" in lista[0]
    assert client.post(f"/api/admin/clientes/{cid}/usuarios/{beto['id']}/convite", headers=adm).status_code == 200
    # zerar a senha de quem já entra
    criar_usuario(db, "Full", email="carla@lumina.com.br", login="carla")
    carla = next(u for u in client.get(f"/api/admin/clientes/{cid}/usuarios", headers=adm).json()
                 if u["login"] == "carla")
    r = client.post(f"/api/admin/clientes/{cid}/usuarios/{carla['id']}/zerar-senha", headers=adm)
    assert r.status_code == 200 and entrar(client, "carla").status_code == 401
    token = r.json()["link"].split("token=")[1]
    assert client.post("/api/auth/reset", json={"token": token, "senha": "Nova@Senha9"}).status_code == 200
    assert entrar(client, "carla", "Nova@Senha9").status_code == 200
    assert any("foi zerada" in a for _, a, _, _ in emails_admin)
    r = client.post(f"/api/admin/clientes/{cid}/usuarios/{carla['id']}/ativo", headers=adm, json={"ativo": False})
    assert r.json()["ativo"] is False


def test_senha_do_suporte(client, db, fundacao, adm):
    cid = criar_estudio(client, adm)["id"]
    assert client.get("/api/admin/suporte", headers=adm).json() == {"senha_definida": False}
    assert client.post(f"/api/admin/clientes/{cid}/suporte/zerar-senha", headers=adm).status_code == 400
    assert client.put("/api/admin/suporte", headers=adm, json={"senha": "somenteletras"}).status_code == 400
    assert client.put("/api/admin/suporte", headers=adm, json={"senha": "Suporte#Teste1"}).status_code == 200
    assert client.post(f"/api/admin/clientes/{cid}/suporte/zerar-senha", headers=adm).status_code == 404
    criar_usuario(db, "Full", email="suporte@mayafit.com.br", login="suporte.pilates-lumina", senha="Outra@Senha1")
    r = client.post(f"/api/admin/clientes/{cid}/suporte/zerar-senha", headers=adm)
    assert r.status_code == 200 and r.json()["login"] == "suporte.pilates-lumina"
    assert entrar(client, "suporte.pilates-lumina", "Suporte#Teste1").status_code == 200
    lista = client.get(f"/api/admin/clientes/{cid}/usuarios", headers=adm).json()
    assert next(u for u in lista if u["login"] == "suporte.pilates-lumina")["suporte"] is True


def test_reenviar_boas_vindas_e_acesso(client, db, fundacao, adm, emails_admin):
    cid = criar_estudio(client, adm)["id"]
    # o único usuário com senha no banco de testes é o "jeff" (administrador): conta como master já criado
    assert client.post(f"/api/admin/clientes/{cid}/boas-vindas", headers=adm).status_code == 400
    r = client.post(f"/api/admin/clientes/{cid}/reenviar-acesso", headers=adm)
    assert r.json() == {"tipo": "redefinir_senha", "enviado_para": ["jeff@mayacorp.com.br"]}
    assert entrar(client, "jeff").status_code == 200  # a senha atual continua valendo


def test_indicacao_da_desconto(client, fundacao, adm):
    est = plano(client, adm, "Estúdio")
    a = criar_estudio(client, adm, plano_id=est["id"], dias_teste=0)
    b = criar_estudio(client, adm, nome="Studio B", slug="studio-b", dias_teste=0, admin_email="b@b.com.br",
                      indicado_por_id=a["id"])
    assert b["indicado_por"]["nome"] == "Pilates Lumina"
    ficha = client.get(f"/api/admin/clientes/{a['id']}", headers=adm).json()
    assert (ficha["indicacoes_ativas"], ficha["desconto_percentual"], ficha["valor_com_desconto"]) == (
        1, "5.00", "85.41")
    assert client.put("/api/admin/politica-indicacao", headers=adm,
                      json={"desconto_por_indicacao": "8", "desconto_maximo": "10"}).status_code == 200
    assert client.get(f"/api/admin/clientes/{a['id']}", headers=adm).json()["valor_com_desconto"] == "82.71"
    assert client.put("/api/admin/politica-indicacao", headers=adm,
                      json={"desconto_por_indicacao": "5", "desconto_maximo": "15"}).status_code == 422


def test_contratos(client, fundacao, adm, emails_admin):
    cid = criar_estudio(client, adm, plano_id=plano(client, adm, "Pro")["id"], inicio_contrato="2026-11-01")["id"]
    m = client.post("/api/admin/modelos-contrato", headers=adm, json={
        "nome": "Licença MayaFit", "corpo": "CONTRATANTE: {{cliente_nome}}, CNPJ {{cliente_documento}}.\n\nPlano "
        "{{plano}} ({{ciclo}}): R$ {{valor}} a partir de {{data_inicio}}, até {{alunos_ativos}} alunos. {{nada}}"}).json()
    assert m["variaveis_desconhecidas"] == ["nada"]
    k = client.post(f"/api/admin/clientes/{cid}/contratos", headers=adm, json={"modelo_id": m["id"]}).json()
    assert "Pilates Lumina, CNPJ 12.345.678/0001-95" in k["corpo"]
    assert "Plano Pro (mensal): R$ 149,90 a partir de 01/11/2026, até 350 alunos." in k["corpo"]
    assert client.get(f"/api/admin/contratos/{k['id']}/pdf", headers=adm).content[:5] == b"%PDF-"
    r = client.post(f"/api/admin/contratos/{k['id']}/enviar", headers=adm, json={"para": ["fin@lumina.com.br"]})
    assert r.json()["status"] == "enviado"
    assert emails_admin[-1][3][0][0] == f"contrato-{k['id']}.pdf"
    assert client.put(f"/api/admin/contratos/{k['id']}", headers=adm,
                      json={"titulo": "x x", "corpo": "y" * 20}).status_code == 400
    assert client.post(f"/api/admin/contratos/{k['id']}/status", headers=adm,
                       json={"status": "assinado"}).json()["status"] == "assinado"
    assert [x["cliente_nome"] for x in client.get("/api/admin/contratos", headers=adm).json()] == ["Pilates Lumina"]
    tipos = [e["tipo"] for e in client.get(f"/api/admin/clientes/{cid}/eventos", headers=adm).json()]
    assert tipos.count("contrato") == 3


def test_ia_no_admin(client, fundacao, adm, monkeypatch):
    from types import SimpleNamespace

    from app.core import ia

    resposta = {}
    monkeypatch.setattr(ia, "provedor_ativo", lambda db: SimpleNamespace(nome="gemini", modelo="t", chave="k"))
    monkeypatch.setattr(ia, "gerar_json", lambda p, sistema, usuario, anexo=None: resposta["r"])
    resposta["r"] = {"nome": "Studio Ramos", "documento": "11.222.333/0001-81", "email_financeiro": "nao-e-email"}
    r = client.post("/api/admin/ia/ficha", headers=adm, json={"texto": "Studio Ramos CNPJ 11.222.333/0001-81"}).json()
    assert r["campos"] == {"nome": "Studio Ramos", "documento": "11222333000181"}
    resposta["r"] = {"corpo": "CONTRATANTE: {{cliente_nome}} no plano {{plano}}. " * 3 + "{{inventada}}"}
    r = client.post("/api/admin/ia/contrato", headers=adm, json={"instrucao": "simples"}).json()
    assert r["variaveis_desconhecidas"] == ["inventada"]
    assert client.post("/api/admin/ia/contrato", headers=adm, json={}).status_code == 400
    monkeypatch.setattr(ia, "provedor_ativo", lambda db: (_ for _ in ()).throw(ia.IAIndisponivel("IA desligada.")))
    r = client.post("/api/admin/ia/ficha", headers=adm, json={"texto": "x" * 20})
    assert r.status_code == 400 and r.json()["detail"] == "IA desligada."
