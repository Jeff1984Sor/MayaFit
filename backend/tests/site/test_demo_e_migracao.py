"""Demo idempotente e migração do site."""

from pathlib import Path

from app.modules.site.demo import popular_demo
from app.modules.site.models import SiteConfig
from app.modules.site.servico import pagina_publica


def test_demo_publica_um_site_completo_e_e_idempotente(db, estudio):
    cfg = popular_demo(db)
    assert cfg.publicado and cfg.publicado_em
    p = pagina_publica(db)
    assert p is not None
    assert len(p.conteudo.depoimentos.itens) == 3
    assert {x.nome for x in p.dados.profissionais} == {"Ana Beatriz Lima", "Bruno Costa"}
    assert p.mapa_embed

    antes = dict(cfg.conteudo)
    popular_demo(db)
    popular_demo(db)
    assert db.query(SiteConfig).count() == 1
    assert db.get(SiteConfig, 1).conteudo == antes


def test_demo_nao_sobrescreve_site_do_estudio(db, estudio):
    from app.modules.site import servico

    cfg = servico.obter_config(db)
    cfg.conteudo = {**cfg.conteudo, "hero": {"titulo": "Meu título"}}
    servico.publicar(db, type("U", (), {"id": None})())
    db.commit()
    popular_demo(db)
    assert db.get(SiteConfig, 1).conteudo["hero"]["titulo"] == "Meu título"


def test_migracao_encadeada_na_fila():
    txt = (Path(__file__).parents[2] / "alembic" / "versions" / "0120_site.py").read_text(encoding="utf-8")
    assert 'revision = "0120_site"' in txt and 'down_revision = "0110_crm"' in txt  # fila única definida na integração
    assert "site_config" in txt and "site_contato" in txt
