"""Editor do site: rascunho, publicação, fotos, permissões e auditoria."""

from sqlalchemy import select

from app.core.models import Auditoria
from tests.site.conftest import png_bytes, publicar


def test_primeira_visita_cria_rascunho_com_dados_do_estudio(client, h_admin, estudio):
    r = client.get("/api/site", headers=h_admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["publicado"] is False and d["tema"] == "aurora"
    assert {i["tipo_servico_id"] for i in d["conteudo"]["modalidades"]["itens"]} == {estudio["pil"].id, estudio["fun"].id}
    assert {p["nome"] for p in d["dados"]["planos"]} == {"Pilates 2x", "Pilates 3x", "Funcional livre"}
    assert len(d["dados"]["profissionais"]) == 2  # o editor vê todos para poder marcar
    assert d["endereco"]["principal"] == "testserver"
    assert d["conteudo"]["secoes"][0] == {"tipo": "hero", "ativa": True}


def test_salvar_publicar_alterar_e_descartar(client, h_admin, estudio, db):
    d = client.get("/api/site", headers=h_admin).json()
    c = d["conteudo"]
    c["hero"]["titulo"] = "Primeira versão"
    publicado = publicar(client, h_admin, c, tema="zen")
    assert publicado["publicado"] is True and publicado["alteracoes_pendentes"] is False
    assert client.get("/api/site-publico/pagina").json()["tema"] == "zen"

    c["hero"]["titulo"] = "Rascunho novo"
    r = client.put("/api/site", json={"tema": "energia", "conteudo": c}, headers=h_admin)
    assert r.json()["alteracoes_pendentes"] is True
    pub = client.get("/api/site-publico/pagina").json()
    assert pub["conteudo"]["hero"]["titulo"] == "Primeira versão" and pub["tema"] == "zen"  # público não muda

    r = client.post("/api/site/descartar", headers=h_admin)
    assert r.json()["conteudo"]["hero"]["titulo"] == "Primeira versão" and r.json()["tema"] == "zen"

    acoes = set(db.scalars(select(Auditoria.acao)))
    assert {"site.salvar", "site.publicar", "site.descartar"} <= acoes


def test_despublicar_tira_do_ar(client, h_admin, estudio):
    assert client.get("/api/site-publico/pagina").status_code == 404
    publicar(client, h_admin)
    assert client.get("/api/site-publico/pagina").status_code == 200
    r = client.post("/api/site/despublicar", headers=h_admin)
    assert r.json()["publicado"] is False
    assert client.get("/api/site-publico/pagina").status_code == 404


def test_descartar_sem_publicacao_da_409(client, h_admin):
    client.get("/api/site", headers=h_admin)
    assert client.post("/api/site/descartar", headers=h_admin).status_code == 409


def test_publicar_sem_secao_ligada_e_recusado(client, h_admin, estudio):
    c = client.get("/api/site", headers=h_admin).json()["conteudo"]
    for s in c["secoes"]:
        s["ativa"] = False
    client.put("/api/site", json={"tema": "aurora", "conteudo": c}, headers=h_admin)
    r = client.post("/api/site/publicar", headers=h_admin)
    assert r.status_code == 422 and "seção" in r.json()["detail"]


def test_upload_de_foto_e_rota_publica_da_imagem(client, h_admin, estudio):
    r = client.post("/api/site/imagens", files={"arquivo": ("hero.png", png_bytes(), "image/png")}, headers=h_admin)
    assert r.status_code == 200, r.text
    foto, url = r.json()["foto"], r.json()["url"]
    assert foto.startswith("site/") and url.startswith("/site-publico/imagens/")
    img = client.get("/api" + url)
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")
    assert "immutable" in img.headers["cache-control"]

    c = client.get("/api/site", headers=h_admin).json()["conteudo"]
    c["hero"]["foto"] = foto
    c["galeria"]["fotos"] = [{"foto": foto, "legenda": "Sala"}]
    assert client.put("/api/site", json={"tema": "aurora", "conteudo": c}, headers=h_admin).status_code == 200


def test_upload_recusa_arquivo_que_nao_e_imagem(client, h_admin):
    r = client.post("/api/site/imagens", files={"arquivo": ("x.png", b"<svg></svg>", "image/png")}, headers=h_admin)
    assert r.status_code == 400


def test_foto_inexistente_no_conteudo_e_recusada(client, h_admin):
    c = client.get("/api/site", headers=h_admin).json()["conteudo"]
    c["hero"]["foto"] = "site/" + "c" * 32 + ".png"
    r = client.put("/api/site", json={"tema": "aurora", "conteudo": c}, headers=h_admin)
    assert r.status_code == 422


def test_rota_publica_de_imagem_nao_serve_outros_arquivos(client):
    assert client.get("/api/site-publico/imagens/..%2F..%2F.env").status_code == 404
    assert client.get("/api/site-publico/imagens/logo.png").status_code == 404
    assert client.get("/api/site-publico/imagens/" + "d" * 32 + ".png").status_code == 404


def test_permissoes(client, h_prof, h_sec):
    assert client.get("/api/site").status_code == 401
    for h in (h_prof, h_sec):  # perfis padrão sem `site.*`: só Full (ou perfil dado pela matriz)
        assert client.get("/api/site", headers=h).status_code == 403
        assert client.post("/api/site/publicar", headers=h).status_code == 403


def test_perfil_so_com_ver_nao_publica(client, db, estudio):
    from app.core.models import PerfilAcesso
    from tests.conftest import auth, criar_usuario, entrar

    u = criar_usuario(db, "Professor", email="leitor@exemplo.com", login="leitor")
    p = PerfilAcesso(nome="Só site", permissoes=["site.ver"], administrador=False)
    db.add(p)
    db.flush()
    u.perfil_acesso_id = p.id
    db.commit()
    h = auth(entrar(client, "leitor").json()["access_token"])
    assert client.get("/api/site", headers=h).status_code == 200
    assert client.post("/api/site/publicar", headers=h).status_code == 403
    assert client.get("/api/site/contatos", headers=h).status_code == 200
