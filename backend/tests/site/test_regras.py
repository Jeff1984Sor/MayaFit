"""Regras puras do site (fotos, mapa, WhatsApp, anti-spam, conteúdo inicial)."""

import pytest
from pydantic import ValidationError

from app.modules.site import regras
from app.modules.site.schemas import TIPOS_SECAO, ContatoIn, ConteudoSite


def test_foto_so_aceita_arquivo_do_editor():
    assert regras.foto_valida("site/" + "a" * 32 + ".jpg")
    assert not regras.foto_valida("site/../../.env")
    assert not regras.foto_valida("alunos/" + "a" * 32 + ".jpg")
    assert not regras.foto_valida("https://exemplo.com/x.jpg")
    assert regras.url_foto("site/" + "b" * 32 + ".webp") == "/site-publico/imagens/" + "b" * 32 + ".webp"


@pytest.mark.parametrize("valor,embed,link", [
    ('<iframe src="https://www.google.com/maps/embed?pb=!1m18" width="600"></iframe>', True, False),
    ("https://www.google.com/maps/embed?pb=abc", True, False),
    ("https://maps.app.goo.gl/AbCdEf123", False, True),
    ("https://www.google.com.br/maps/place/Av.+Paulista", False, True),
])
def test_mapa_aceita_google(valor, embed, link):
    m = regras.extrair_mapa(valor)
    assert m is not None
    assert bool(m.embed) is embed and bool(m.link) is link


@pytest.mark.parametrize("valor", [
    "http://www.google.com/maps/embed?pb=1",  # sem https
    '<iframe src="https://evil.com/maps/embed"></iframe>',
    "https://google.com.evil.com/maps",
    "javascript:alert(1)",
    "https://www.google.com/search?q=x",
])
def test_mapa_recusa_o_resto(valor):
    assert regras.extrair_mapa(valor) is None


def test_mapa_da_pagina_gera_pelo_endereco():
    m = regras.mapa_da_pagina("", "Rua A, 10 - São Paulo")
    assert m.embed.startswith("https://www.google.com/maps?q=Rua%20A") and m.embed.endswith("output=embed")
    assert "query=Rua%20A" in m.link
    vazio = regras.mapa_da_pagina("", "")
    assert vazio.embed is None and vazio.link is None
    m2 = regras.mapa_da_pagina("https://maps.app.goo.gl/x1", "Rua B")
    assert m2.link == "https://maps.app.goo.gl/x1" and "Rua%20B" in m2.embed


def test_numero_whatsapp():
    assert regras.numero_whatsapp("(11) 98888-1234") == "5511988881234"
    assert regras.numero_whatsapp("+55 11 3333-4444") == "551133334444"
    assert regras.numero_whatsapp("123") is None


def test_anti_spam():
    assert regras.avaliar_spam("http://spam", 9000) == "honeypot"
    assert regras.avaliar_spam("", 800) == "rapido"
    assert regras.avaliar_spam("", None) is None
    assert regras.avaliar_spam("", 5000) is None


def test_conteudo_padrao_e_valido_e_completo():
    c = ConteudoSite.model_validate(regras.conteudo_padrao("Estúdio Teste", [(1, "Pilates")], [7]))
    assert [s.tipo for s in c.secoes] == list(TIPOS_SECAO)
    assert c.modalidades.itens[0].tipo_servico_id == 1
    assert c.equipe.itens[0].mostrar is False  # ninguém aparece sem o estúdio marcar
    assert "Estúdio Teste" in c.hero.subtitulo


def test_secoes_repetidas_ou_faltando_sao_normalizadas():
    c = ConteudoSite.model_validate({"secoes": [{"tipo": "faq"}, {"tipo": "faq", "ativa": False}, {"tipo": "hero"}]})
    tipos = [s.tipo for s in c.secoes]
    assert tipos[:2] == ["faq", "hero"] and len(tipos) == len(TIPOS_SECAO)
    assert c.secoes[0].ativa is True and c.secoes[-1].ativa is False


def test_conteudo_recusa_foto_mapa_e_rede_invalidos():
    with pytest.raises(ValidationError):
        ConteudoSite.model_validate({"hero": {"foto": "../segredo.png"}})
    with pytest.raises(ValidationError):
        ConteudoSite.model_validate({"localizacao": {"mapa": "https://evil.com"}})
    with pytest.raises(ValidationError):
        ConteudoSite.model_validate({"contato": {"instagram": "javascript:alert(1)"}})
    with pytest.raises(ValidationError):
        ConteudoSite.model_validate({"contato": {"whatsapp": "123"}})


def test_contato_exige_telefone_ou_email():
    with pytest.raises(ValidationError):
        ContatoIn(nome="Fulano", consentimento=True)
    assert ContatoIn(nome="Fulano", email="", telefone="11988887777").email is None
