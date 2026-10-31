import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

from app import seed
from app.core.models import ConfigEmail, Identidade, PerfilAcesso, Usuario
from app.limpar_dados import MANTER_PADRAO, carregar_modelos, tabelas_a_limpar
from tests.conftest import SENHA, auth, criar_usuario, entrar


def test_seed_e_idempotente_e_cria_identidade_e_perfis(db):
    seed.base(db)
    seed.base(db)
    assert db.scalar(select(Identidade.nome_exibicao)) == "Estúdio Demonstração"
    nomes = sorted(db.scalars(select(PerfilAcesso.nome)))
    assert nomes == sorted(["Full", "Professor", "Secretária"])
    assert db.get(ConfigEmail, 1) is not None
    assert not list(db.scalars(select(Usuario)))  # a base não cria usuário


def test_seed_nao_sobrescreve_o_que_o_administrador_editou(db):
    seed.base(db)
    db.scalar(select(Identidade)).nome_exibicao = "Meu Studio"
    p = db.scalar(select(PerfilAcesso).where(PerfilAcesso.nome == "Professor"))
    p.permissoes = ["agenda.ver"]
    db.commit()
    seed.base(db)
    assert db.scalar(select(Identidade.nome_exibicao)) == "Meu Studio"
    assert db.scalar(select(PerfilAcesso.permissoes).where(PerfilAcesso.nome == "Professor")) == ["agenda.ver"]


def test_admin_de_demonstracao_usa_a_senha_informada_e_e_idempotente(client, db):
    seed.base(db)
    u = seed.admin_demonstracao(db, email="admin@pilates.local", login="admin", senha=SENHA)
    assert u and u.senha_hash.startswith("$argon2") and SENHA not in u.senha_hash
    assert seed.admin_demonstracao(db, email="admin@pilates.local", login="admin", senha="Outra@Senha1") is None
    assert entrar(client, "admin", SENHA).status_code == 200


def test_nao_ha_senha_fixa_no_codigo():
    import re

    raiz = Path(seed.__file__).parent
    suspeitos = []
    for arq in raiz.rglob("*.py"):
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"""(senha|password|secret)\w*\s*=\s*["'][^"']{6,}["']""", linha, re.I) and "_DEV" not in linha:
                suspeitos.append(f"{arq.name}:{n}: {linha.strip()}")
    assert not suspeitos, suspeitos


def test_limpar_dados_deriva_tabelas_dos_metadados():
    carregar_modelos()
    nomes = [t.name for t in tabelas_a_limpar(set())]
    assert "auditoria" in nomes and "refresh_token" in nomes and "recuperacao_senha" in nomes
    assert not MANTER_PADRAO & set(nomes)  # usuários, perfis, identidade e configs preservados
    # filhos antes dos pais: auditoria (FK usuario) não pode vir depois de usuario, e usuario não é apagado
    assert tabelas_a_limpar({"auditoria"}) and "auditoria" not in [t.name for t in tabelas_a_limpar({"auditoria"})]


def test_limpar_dados_recusa_sem_confirmacao():
    r = subprocess.run([sys.executable, "-m", "app.limpar_dados"], capture_output=True, text=True,
                       cwd=Path(seed.__file__).parents[1])
    assert r.returncode != 0 and "Nada foi apagado" in (r.stderr + r.stdout)


# ---------------------------------------------------------------------------------------------- usuários / identidade (API)
def test_identidade_publica_padrao_e_editada(client, db, token_admin):
    assert client.get("/api/public/identidade").json()["nome_exibicao"] == "MayaFit"  # padrão neutro sem banco populado
    seed.base(db)
    assert client.get("/api/public/identidade").json()["nome_exibicao"] == "Estúdio Demonstração"
    h = auth(token_admin)
    r = client.put("/api/config/identidade", headers=h, json={"nome_exibicao": "Outro Studio", "cor_destaque": "#6B1F3A"})
    assert r.status_code == 200
    assert client.get("/api/public/identidade").json() == {"nome_exibicao": "Outro Studio", "logo_url": None, "cor_destaque": "#6B1F3A"}
    assert client.put("/api/config/identidade", headers=h, json={"nome_exibicao": "X", "cor_destaque": "vermelho"}).status_code == 422


def test_crud_de_usuario_com_e_sem_login(client, db, token_admin, emails):
    h = auth(token_admin)
    perfil = client.get("/api/config/perfis", headers=h).json()
    pid = next(p["id"] for p in perfil if p["nome"] == "Professor")
    r = client.post("/api/config/usuarios", headers=h, json={"nome": "Ana Prof", "email": "ana@exemplo.com", "login": "ana", "perfil_acesso_id": pid})
    assert r.status_code == 201 and r.json()["convite_pendente"] is True
    assert emails and "redefinir-senha?token=" in emails[0][2]  # convite por link
    # profissional sem login: não recebe convite e não consegue entrar
    r = client.post("/api/config/usuarios", headers=h, json={"nome": "Bia", "email": "bia@exemplo.com", "perfil_acesso_id": pid,
                                                             "acesso_sistema": False})
    assert r.status_code == 201 and len(emails) == 1
    assert db.scalar(select(Usuario.senha_hash).where(Usuario.email == "bia@exemplo.com")) is None
    # e-mail duplicado
    assert client.post("/api/config/usuarios", headers=h, json={"nome": "Dup", "email": "ANA@exemplo.com", "login": "dup",
                                                                "perfil_acesso_id": pid}).status_code == 409
    # perfil obrigatório e existente
    assert client.post("/api/config/usuarios", headers=h, json={"nome": "Sem", "email": "s@exemplo.com", "login": "sem"}).status_code == 404
    lista = client.get("/api/config/usuarios", headers=h).json()
    assert {u["email"] for u in lista} >= {"ana@exemplo.com", "bia@exemplo.com"}


def test_admin_define_senha_do_usuario_e_derruba_sessoes(client, db, token_admin):
    u = criar_usuario(db, "Professor", email="p@exemplo.com")
    antigo = entrar(client, "p@exemplo.com").json()["access_token"]
    h = auth(token_admin)
    assert client.post(f"/api/config/usuarios/{u.id}/definir-senha", headers=h, json={"senha": "fraca"}).status_code == 400
    assert client.post(f"/api/config/usuarios/{u.id}/definir-senha", headers=h, json={"senha": "Nova@Senha5"}).status_code == 200
    assert client.get("/api/auth/me", headers=auth(antigo)).status_code == 401
    assert entrar(client, "p@exemplo.com", "Nova@Senha5").status_code == 200


def test_me_patch_e_preferencias(client, admin, token_admin):
    h = auth(token_admin)
    r = client.patch("/api/auth/me", headers=h, json={"nome": "Novo Nome", "telefone": "11999990000"})
    assert r.status_code == 200 and r.json()["nome"] == "Novo Nome"
    r = client.put("/api/auth/me/preferencias", headers=h, json={"menu_recolhido": ["Financeiro"]})
    assert r.json()["preferencias"] == {"menu_recolhido": ["Financeiro"]}
    r = client.get("/api/auth/me", headers=h).json()
    assert "senha_hash" not in r and "token_version" not in r and r["administrador"] is True


def test_cabecalhos_de_seguranca_e_host_invalido(client):
    r = client.get("/api/health")
    assert r.json()["ok"] is True
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert client.get("/api/health", headers={"Host": "evil.example.com"}).status_code == 400


def test_worker_executa_tarefas_vencidas_e_isola_falhas():
    from app import worker

    chamadas = []
    antes = list(worker.TAREFAS)
    worker.TAREFAS.clear()
    worker.registrar_tarefa("a", 10, lambda: chamadas.append("a"))
    worker.registrar_tarefa("quebra", 10, lambda: 1 / 0)
    worker.registrar_tarefa("b", 100, lambda: chamadas.append("b"))
    try:
        assert worker.executar_pendentes(agora_s=0) == ["a", "b"]  # a que quebrou não derruba as outras
        assert worker.executar_pendentes(agora_s=5) == []
        assert worker.executar_pendentes(agora_s=11) == ["a"]
    finally:
        worker.TAREFAS[:] = antes


def test_criar_usuario_com_acesso_exige_login(client, db, token_admin):
    h = auth(token_admin)
    pid = next(p["id"] for p in client.get("/api/config/perfis", headers=h).json() if p["nome"] == "Professor")
    r = client.post("/api/config/usuarios", headers=h, json={"nome": "Sem Login", "email": "sl@exemplo.com", "perfil_acesso_id": pid})
    assert r.status_code == 422
    # login com "@" é recusado
    r = client.post("/api/config/usuarios", headers=h, json={"nome": "Email", "email": "e@exemplo.com", "login": "e@exemplo.com", "perfil_acesso_id": pid})
    assert r.status_code == 422
