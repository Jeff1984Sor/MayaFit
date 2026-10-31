"""Um banco por estúdio: identificação (host, catálogo), isolamento de dados e arquivos, status, worker,
provisionamento (Suporte + primeiro acesso) e catálogo de logins."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core import tenancy
from app.core.auth_service import MSG_LOGIN
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import Usuario
from tests.conftest import SENHA
from tests.tenancy.conftest import HOST_ALFA, HOST_BETA, SENHA_SUPORTE, bearer, controle_proprio, entrar


def _logins(slug: str) -> set[str]:
    from app.controle.models import Cliente, Login, SessaoControle

    with SessaoControle() as db:
        return set(db.scalars(select(Login.chave).join(Cliente).where(Cliente.slug == slug)))


def test_sem_controle_e_um_banco_so():
    assert tenancy.multi() is False
    assert tenancy.recursos() is None and tenancy.claims() == {}
    assert tenancy.pasta_base() == Path(settings.storage_dir)


def test_login_pelo_endereco_e_dados_isolados(multi, client):
    alfa = bearer(entrar(client, "ana", host=HOST_ALFA))
    beta = bearer(entrar(client, "ana", host=HOST_BETA))
    me_a = client.get("/api/auth/me", headers=alfa).json()
    me_b = client.get("/api/auth/me", headers=beta).json()
    assert (me_a["nome"], me_a["estudio"]["slug"], me_a["estudio"]["nome"]) == ("Ana Alfa", "alfa", "Studio Alfa")
    assert (me_b["nome"], me_b["estudio"]["status"]) == ("Ana Beta", "teste")
    assert me_b["estudio"]["teste_ate"] and me_a["estudio"]["mayacorp"] is False and me_a["estudio"]["recursos"] == []

    # o que um estúdio cadastra o outro não vê (os ids até coincidem: são bancos diferentes)
    r = client.post("/api/config/usuarios", headers=alfa, json={
        "nome": "Exclusivo Alfa", "email": "exclusivo@alfa.com", "login": "exclusivo", "perfil_acesso_id":
        me_a["perfil_acesso_id"], "acesso_sistema": False})
    assert r.status_code == 201, r.text
    nomes = lambda h: {u["nome"] for u in client.get("/api/config/usuarios", headers=h).json()}  # noqa: E731
    assert "Exclusivo Alfa" in nomes(alfa) and "Exclusivo Alfa" not in nomes(beta)

    # a marca pública sai do banco do endereço
    assert client.get("/api/public/identidade", headers={"Host": HOST_ALFA}).json()["nome_exibicao"] == "Studio Alfa"
    assert client.get("/api/public/identidade", headers={"X-Forwarded-Host": HOST_BETA}).json()["nome_exibicao"] == "Studio Beta"
    # no endereço do estúdio só valem os logins dele
    assert entrar(client, "carlos", host=HOST_BETA).status_code == 401


def test_login_pelo_catalogo_e_login_ambiguo(multi, client):
    carlos = bearer(entrar(client, "carlos"))  # sem endereço de estúdio: o catálogo diz que é do alfa
    assert client.get("/api/auth/me", headers=carlos).json()["estudio"]["slug"] == "alfa"
    assert client.get("/api/auth/me", headers=bearer(entrar(client, "BIA"))).json()["estudio"]["slug"] == "beta"
    # "ana" existe nos dois: no endereço principal falha com a MESMA mensagem de senha errada (não revela nada)
    ambiguo = entrar(client, "ana")
    errado = entrar(client, "carlos", senha="Errada@123")
    inexistente = entrar(client, "ninguem")
    assert ambiguo.status_code == errado.status_code == inexistente.status_code == 401
    assert ambiguo.json()["detail"] == errado.json()["detail"] == inexistente.json()["detail"] == MSG_LOGIN


def test_token_de_um_estudio_nao_serve_no_outro(multi, client):
    alfa = bearer(entrar(client, "ana", host=HOST_ALFA))
    # o token manda: no endereço do beta, o token do alfa continua vendo SÓ o alfa
    me = client.get("/api/auth/me", headers={**alfa, "X-Forwarded-Host": HOST_BETA}).json()
    assert me["estudio"]["slug"] == "alfa" and me["nome"] == "Ana Alfa"
    # sem token nem endereço de estúdio, nenhuma rota abre banco
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer invalido"}).status_code == 401
    assert client.get("/api/public/identidade").status_code == 401
    # host desconhecido nem chega à API
    assert client.get("/api/health", headers={"Host": "intruso.exemplo.com"}).status_code == 400


def test_estudio_inativo_nao_entra_e_suspenso_entra(multi, client):
    beta = bearer(entrar(client, "bia"))
    try:
        multi.definir_status("beta", "inativo")
        assert client.get("/api/auth/me", headers=beta).status_code == 401
        assert entrar(client, "bia").status_code == 401
        assert entrar(client, "bia", host=HOST_BETA).status_code == 401
        # no endereço do inativo, "ana" não cai no catálogo (que acharia a ana do alfa)
        assert entrar(client, "ana", host=HOST_BETA).status_code == 401
        assert entrar(client, "ana").status_code == 200  # no endereço principal: agora só o alfa tem "ana"
        multi.definir_status("beta", "suspenso")
        assert client.get("/api/auth/me", headers=bearer(entrar(client, "bia"))).json()["estudio"]["status"] == "suspenso"
    finally:
        multi.definir_status("beta", "teste")


def test_arquivos_separados_por_estudio(multi):
    from app.core import storage

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    with tenancy.usando(multi.por_slug("alfa")):
        assert storage.raiz() == (Path(settings.storage_dir) / "estudios" / "alfa").resolve()
        rel = storage.salvar("usuarios", "foto.png", png)
        assert storage.existe(rel)
    with tenancy.usando(multi.por_slug("beta")):
        assert storage.raiz() == (Path(settings.storage_dir) / "estudios" / "beta").resolve()
        assert not storage.existe(rel)


def test_worker_roda_cada_tarefa_em_cada_estudio(multi):
    from app import worker

    vistos, globais = [], []
    worker.registrar_tarefa("teste-por-estudio", 60, lambda: vistos.append(tenancy.atual().slug))
    worker.registrar_tarefa("teste-global", 60, lambda: globais.append(tenancy.atual()), global_=True)
    try:
        feitas = worker.executar_pendentes(agora_s=1e9)
        assert sorted(vistos) == ["alfa", "beta"] and globais == [None]
        assert {"teste-por-estudio@alfa", "teste-por-estudio@beta", "teste-global"} <= set(feitas)
        worker.executar_pendentes(agora_s=1e9 + 1)  # ninguém venceu de novo
        assert len(vistos) == 2 and len(globais) == 1
        # estúdio inativo sai da volta seguinte
        multi.definir_status("beta", "inativo")
        worker.executar_pendentes(agora_s=1e9 + 120)
        assert sorted(vistos) == ["alfa", "alfa", "beta"]
    finally:
        multi.definir_status("beta", "teste")
        worker.TAREFAS[:] = [t for t in worker.TAREFAS if not t.nome.startswith("teste-")]


def test_uso_gravado_no_controle(multi):
    from app.controle.models import Cliente, SessaoControle

    assert multi.coletar_uso(multi.por_slug("alfa")) == {"alunos_ativos": 0, "usuarios": 2, "aulas_mes": 0} or \
        multi.coletar_uso(multi.por_slug("alfa"))["usuarios"] >= 2  # o Suporte não conta
    assert multi.gravar_uso_todos() == 2
    with SessaoControle() as db:
        uso = db.scalar(select(Cliente.uso).where(Cliente.slug == "beta"))
    assert set(uso) == {"alunos_ativos", "usuarios", "aulas_mes", "em"} and uso["usuarios"] == 2


def test_provisionar_cria_suporte_e_primeiro_acesso_uma_vez(multi, client, monkeypatch):
    monkeypatch.setattr(settings, "dominio_base", "mayafit.test")
    cliente, link = multi.provisionar("gama", "Studio Gama", admin_email="dono@gama.com", primeiro_acesso=True)
    assert cliente.status == "ativo" and link.startswith("http://gama.mayafit.test:3000/primeiro-acesso?token=")
    assert multi.por_host("gama.mayafit.test") == multi.por_slug("gama")  # subdomínio padrão entrou sozinho
    with tenancy.usando(multi.por_slug("gama")), SessionLocal() as db:
        sup = db.scalar(select(Usuario).where(Usuario.suporte.is_(True)))
        assert (sup.login, sup.email, sup.administrador) == ("suporte.gama", "suporte+gama@mayacorp.com.br", True)
        assert db.scalar(select(Usuario.id).where(Usuario.suporte.is_(False))) is None  # o master ainda não existe
    # o Suporte entra com a senha definida no admin
    assert client.get("/api/auth/me", headers=bearer(entrar(client, "suporte.gama", SENHA_SUPORTE))).json()["estudio"]["slug"] == "gama"

    token = link.split("token=")[1]
    info = client.get("/api/auth/primeiro-acesso", params={"token": token})
    assert info.json() == {"estudio": "Studio Gama", "email": "dono@gama.com"}, info.text
    dados = {"token": token, "nome": "Dono Gama", "email": "dono@gama.com", "login": "dono", "senha": SENHA}
    assert client.post("/api/auth/primeiro-acesso", json={**dados, "login": "suporte.gama"}).status_code == 409
    r = client.post("/api/auth/primeiro-acesso", json=dados)
    assert r.status_code == 200, r.text
    assert r.json()["usuario"]["administrador"] is True and r.json()["usuario"]["estudio"]["slug"] == "gama"
    # o link vale uma vez só
    assert client.post("/api/auth/primeiro-acesso", json={**dados, "login": "outro", "email": "o@gama.com"}).status_code == 409
    assert client.get("/api/auth/primeiro-acesso", params={"token": token}).status_code == 409
    assert "dono" in _logins("gama") and "suporte.gama" in _logins("gama")
    assert client.get("/api/auth/me", headers=bearer(entrar(client, "dono"))).json()["nome"] == "Dono Gama"


def test_provisionar_com_erro_nao_deixa_estudio_pela_metade(multi, monkeypatch):
    def quebra(_esc):
        raise RuntimeError("falhou a migration")

    monkeypatch.setattr(multi, "migrar", quebra)
    with pytest.raises(RuntimeError):
        multi.provisionar("delta", "Studio Delta", admin_email="x@delta.com", admin_senha=SENHA)
    from app.controle.models import Cliente, SessaoControle

    with SessaoControle() as db:
        assert db.scalar(select(Cliente.id).where(Cliente.slug == "delta")) is None
    with pytest.raises(multi.RegraControle):
        multi.provisionar("Delta X", "x", admin_email="x@delta.com")


def test_convite_e_reset_por_link_levam_o_estudio(multi, client, emails):
    assert client.post("/api/auth/forgot", json={"identificador": "carlos"}).status_code == 200
    (para, _, corpo), = emails
    token = corpo.split("token=")[1].split()[0]
    assert para == ["carlos@alfa.com"] and token.startswith("alfa.")
    assert f"http://{HOST_ALFA}:3000/redefinir-senha?token=" in corpo  # o link abre no endereço do estúdio
    # o link funciona no endereço principal: o estúdio vem do próprio token
    assert client.post("/api/auth/reset", json={"token": token, "senha": "Nova@Senha9"}).status_code == 200
    assert client.get("/api/auth/me", headers=bearer(entrar(client, "carlos", "Nova@Senha9"))).status_code == 200
    with tenancy.usando(multi.por_slug("alfa")), SessionLocal() as db:
        from app.core.security import hash_senha

        db.scalar(select(Usuario).where(Usuario.login == "carlos")).senha_hash = hash_senha(SENHA)
        db.commit()


def test_refresh_acha_o_estudio_pelo_token(multi, client):
    r = entrar(client, "bia")
    novo = client.post("/api/auth/refresh", json={"refresh_token": r.json()["refresh_token"]})
    assert novo.status_code == 200 and novo.json()["usuario"]["estudio"]["slug"] == "beta"


def test_sincronia_do_catalogo(multi):
    from app.core import perfis

    esc = multi.por_slug("beta")
    with tenancy.usando(esc), SessionLocal() as db:
        u = Usuario(nome="Novo", email="novo@beta.com", login="novo", perfil_acesso_id=perfis.garantir_padrao(db)["Full"].id)
        db.add(u)
        db.commit()
        assert "novo" in _logins("beta")
        u.login = "renomeado"
        db.commit()
        assert "renomeado" in _logins("beta") and "novo" not in _logins("beta")
        u.ativo = False
        db.commit()
        assert "renomeado" not in _logins("beta")
        db.delete(u)
        db.commit()
    assert multi.sincronizar_todos("beta") >= 3
    assert {"ana", "bia", "suporte.beta"} <= _logins("beta")


def test_registra_o_estudio_do_banco_principal():
    from sqlalchemy.orm import Session

    from app.controle import service
    from app.core.models import Identidade

    with Session(tenancy.engine_do(None)) as db:  # o banco principal (DATABASE_URL), direto
        db.add(Identidade(id=1, nome_exibicao="Estúdio Mayris"))
        db.add(Usuario(nome="Ana", email="ana@mayris.com", login="ana.mayris"))
        db.commit()
    with controle_proprio():
        assert service.registrar_principal_se_faltar() == "estudio-mayris"
        assert service.registrar_principal_se_faltar() is None
        assert service.por_slug("estudio-mayris").banco is None
        assert service.por_login("ana.mayris").slug == "estudio-mayris"
        with tenancy.usando(service.por_slug("estudio-mayris")):
            assert tenancy.pasta_base() == Path(settings.storage_dir)  # o principal continua em storage/


def test_email_com_html_e_imagem_embutida():
    import email
    from pathlib import Path

    from app.core import email as mail
    from app.core import storage

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    assert mail.enviar(["x@y.com"], "Teste HTML", "texto puro", html='<p>Oi <img src="cid:logo"></p>',
                       imagens={"logo": (png, "image/png")})
    eml = max((storage.raiz() / "outbox").glob("*.eml"), key=lambda p: p.stat().st_mtime)
    msg = email.message_from_bytes(Path(eml).read_bytes())
    tipos = [p.get_content_type() for p in msg.walk()]
    assert tipos[:2] == ["multipart/alternative", "text/plain"] and "multipart/related" in tipos
    assert "text/html" in tipos and "image/png" in tipos
