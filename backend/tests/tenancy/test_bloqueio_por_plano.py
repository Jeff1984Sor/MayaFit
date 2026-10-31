"""Regra P8: recurso fora do plano responde 403 dizendo o plano que libera; sem plano ou com um banco só, tudo passa."""

from sqlalchemy import select

from app.core.recursos_http import recurso_da_rota
from tests.tenancy.conftest import HOST_ALFA, HOST_BETA, bearer, entrar


def _plano(slug: str, nome: str | None, extras: list[str] | None = None) -> None:
    from app.controle import planos, service
    from app.controle.models import Cliente, Plano, SessaoControle

    with SessaoControle() as db:
        planos.garantir_padrao(db)
        c = db.scalar(select(Cliente).where(Cliente.slug == slug))
        c.plano_id = db.scalar(select(Plano.id).where(Plano.nome == nome)) if nome else None
        c.extras = extras or []
        db.commit()
    service.limpar_cache()


def test_mapa_de_rotas():
    assert recurso_da_rota("/api/crm/leads") == "crm"
    assert recurso_da_rota("/api/site-publico/pagina") == "site"
    assert recurso_da_rota("/api/acesso/catracas/1/liberar") == "catraca"
    assert recurso_da_rota("/api/acesso/painel") == "checkin"
    assert recurso_da_rota("/api/aluno-app/acesso/qr") == "checkin"
    assert recurso_da_rota("/api/aluno-app/aulas") == "app_aluno"
    assert recurso_da_rota("/api/webhooks/wellhub") == "integracoes"
    assert recurso_da_rota("/api/nfse/notas") == "nfse"
    assert recurso_da_rota("/api/alunos") is None and recurso_da_rota("/api/config/ia") is None


def test_um_banco_so_nao_bloqueia(client, token_admin):
    assert client.get("/api/nfse/painel", headers={"Authorization": f"Bearer {token_admin}"}).status_code != 403


def test_plano_essencial_bloqueia_nfse_e_libera_crm(multi, client):
    _plano("alfa", "Essencial")
    try:
        h = bearer(entrar(client, "ana", host=HOST_ALFA))
        assert client.get("/api/crm/resumo", headers=h).status_code == 200
        r = client.get("/api/nfse/painel", headers=h)
        assert r.status_code == 403
        assert r.json()["recurso"] == "nfse" and r.json()["plano"] == "Pro" and "plano Pro" in r.json()["detail"]
        assert client.get("/api/acesso/painel", headers=h).json()["plano"] == "Estúdio"
        me = client.get("/api/auth/me", headers=h).json()
        assert set(me["estudio"]["recursos"]) == {"gestao", "site", "crm"}
        # extra liberado à parte vale mesmo fora do plano
        _plano("alfa", "Essencial", extras=["nfse"])
        assert client.get("/api/nfse/painel", headers=h).status_code != 403
    finally:
        _plano("alfa", None)


def test_sem_plano_libera_tudo(multi, client):
    h = bearer(entrar(client, "ana", host=HOST_BETA))
    assert client.get("/api/nfse/painel", headers=h).status_code != 403
