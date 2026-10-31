"""Página pública: só o que o estúdio escolheu mostrar e nenhum dado de aluno."""

from datetime import date, time

from app.modules.agenda.models import AulaSessao
from app.modules.alunos.models import Aluno
from app.modules.cadastros.models import HorarioStudio
from tests.site.conftest import publicar


def _conteudo(client, h):
    return client.get("/api/site", headers=h).json()["conteudo"]


def test_filtros_do_estudio_valem_no_publico(client, h_admin, estudio):
    c = _conteudo(client, h_admin)
    c["planos"]["ocultos"] = [estudio["planos"][1].id]
    c["planos"]["mostrar_precos"] = False
    for i in c["modalidades"]["itens"]:
        i["mostrar"] = i["tipo_servico_id"] != estudio["fun"].id
    for i in c["equipe"]["itens"]:
        if i["profissional_id"] == estudio["ana"].id:
            i.update(mostrar=True, cargo="Fisioterapeuta", bio="Bio da Ana")
        else:
            i["bio"] = "bio que não pode vazar"
    publicar(client, h_admin, c)

    p = client.get("/api/site-publico/pagina").json()
    assert [m["nome"] for m in p["dados"]["modalidades"]] == ["Pilates"]
    # plano oculto e plano de modalidade escondida não aparecem; preço escondido
    assert [(x["nome"], x["valor"]) for x in p["dados"]["planos"]] == [("Pilates 2x", None)]
    assert [x["nome"] for x in p["dados"]["profissionais"]] == ["Ana Beatriz Lima"]
    assert [i["profissional_id"] for i in p["conteudo"]["equipe"]["itens"]] == [estudio["ana"].id]
    assert "bio que não pode vazar" not in str(p)
    assert p["conteudo"]["planos"]["ocultos"] == []
    # grade: só modalidades visíveis, professor pelo primeiro nome
    assert p["dados"]["grade"] == [
        {"dia_semana": 0, "hora_inicio": "07:00:00", "hora_fim": "08:00:00", "modalidade": "Pilates", "professor": "Ana"}
    ]


def test_precos_aparecem_por_padrao_e_professor_nao_marcado_fica_anonimo(client, h_admin, estudio):
    publicar(client, h_admin)
    p = client.get("/api/site-publico/pagina").json()
    assert {x["valor"] for x in p["dados"]["planos"]} == {"390.00", "490.00", "250.00"}
    assert p["dados"]["profissionais"] == []  # ninguém marcado
    assert all(h["professor"] is None for h in p["dados"]["grade"])
    assert len(p["dados"]["grade"]) == 2


def test_grade_sem_grade_fixa_usa_aulas_dos_proximos_dias(client, h_admin, estudio, db):
    db.query(HorarioStudio).delete()
    hoje = date.today()
    db.add(AulaSessao(unidade_id=estudio["un"].id, tipo_servico_id=estudio["pil"].id, data=hoje,
                      hora_inicio=time(9), hora_fim=time(10)))
    db.commit()
    publicar(client, h_admin)
    g = client.get("/api/site-publico/pagina").json()["dados"]["grade"]
    assert g == [{"dia_semana": hoje.weekday(), "hora_inicio": "09:00:00", "hora_fim": "10:00:00",
                  "modalidade": "Pilates", "professor": None}]


def test_nenhum_dado_de_aluno_no_site(client, h_admin, estudio, db):
    db.add(Aluno(nome="Fulana Aluna Secreta", cpf="52998224725", unidade_id=estudio["un"].id))
    db.commit()
    publicar(client, h_admin)
    texto = client.get("/api/site-publico/pagina").text
    assert "Fulana" not in texto and "52998224725" not in texto
    assert "11988887777" not in texto  # celular do profissional também não sai


def test_identidade_e_mapa(client, h_admin, estudio, db):
    from app.core.models import Identidade

    db.add(Identidade(id=1, nome_exibicao="Estúdio Equilíbrio", cor_destaque="#1a8f5e"))
    db.commit()
    c = _conteudo(client, h_admin)
    c["localizacao"]["endereco"] = "Rua das Flores, 100"
    publicar(client, h_admin, c)
    p = client.get("/api/site-publico/pagina").json()
    assert p["identidade"] == {"nome": "Estúdio Equilíbrio", "cor": "#1a8f5e", "logo_url": None}
    assert p["mapa_embed"].endswith("output=embed") and "Rua%20das%20Flores" in p["mapa_link"]


def test_pagina_publica_tem_rate_limit(client, h_admin, estudio, monkeypatch):
    from app.core import ratelimit

    publicar(client, h_admin)
    monkeypatch.setattr(ratelimit.memoria, "registrar", lambda *a, **k: 30.0)
    r = client.get("/api/site-publico/pagina")
    assert r.status_code == 429
