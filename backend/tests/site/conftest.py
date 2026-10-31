"""Fixtures do site: cadastros sintéticos de um estúdio (nada de dado real)."""

import struct
import zlib
from datetime import time
from decimal import Decimal

import pytest

import app.modules.site.models  # noqa: F401
from app.modules import registrar_modelos
from app.modules.cadastros.models import HorarioStudio, Plano, Profissional, TipoServico, Unidade
from tests.conftest import auth, criar_usuario, entrar

registrar_modelos()


def png_bytes(w: int = 4, h: int = 4) -> bytes:
    def chunk(tipo: bytes, dados: bytes) -> bytes:
        c = struct.pack(">I", len(dados)) + tipo + dados
        return c + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture
def estudio(db):
    """Unidade, duas modalidades, três planos, dois profissionais e uma grade fixa."""
    un = Unidade(nome="Matriz", capacidade=4)
    pil, fun = TipoServico(nome="Pilates"), TipoServico(nome="Funcional")
    db.add_all([un, pil, fun])
    db.flush()
    p1 = Plano(nome="Pilates 2x", tipo_servico_id=pil.id, valor=Decimal("390.00"), aulas_por_semana=2)
    p2 = Plano(nome="Pilates 3x", tipo_servico_id=pil.id, valor=Decimal("490.00"), aulas_por_semana=3)
    p3 = Plano(nome="Funcional livre", tipo_servico_id=fun.id, valor=Decimal("250.00"), aulas_por_semana=5)
    ana, bruno = Profissional(nome="Ana Beatriz Lima", celular="11988887777"), Profissional(nome="Bruno Costa")
    db.add_all([p1, p2, p3, ana, bruno])
    db.flush()
    db.add_all([
        HorarioStudio(unidade_id=un.id, tipo_servico_id=pil.id, profissional_id=ana.id, dia_semana=0,
                      hora_inicio=time(7), hora_fim=time(8)),
        HorarioStudio(unidade_id=un.id, tipo_servico_id=fun.id, profissional_id=bruno.id, dia_semana=2,
                      hora_inicio=time(18), hora_fim=time(19)),
    ])
    db.commit()
    return {"un": un, "pil": pil, "fun": fun, "planos": [p1, p2, p3], "ana": ana, "bruno": bruno}


@pytest.fixture
def h_admin(client, admin):
    return auth(entrar(client, "admin").json()["access_token"])


@pytest.fixture
def h_prof(client, db):
    criar_usuario(db, "Professor", email="prof@exemplo.com", login="prof")
    return auth(entrar(client, "prof").json()["access_token"])


@pytest.fixture
def h_sec(client, db):
    criar_usuario(db, "Secretária", email="sec@exemplo.com", login="sec")
    return auth(entrar(client, "sec").json()["access_token"])


def publicar(client, h, conteudo=None, tema="aurora"):
    """Salva (opcional) e publica o site; devolve o estado do editor."""
    if conteudo is not None:
        r = client.put("/api/site", json={"tema": tema, "conteudo": conteudo}, headers=h)
        assert r.status_code == 200, r.text
    r = client.post("/api/site/publicar", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


CONTATO_OK = {"nome": "Visitante Teste", "telefone": "(11) 98888-1234", "email": "visita@exemplo.com",
              "interesse": "Pilates", "mensagem": "Quero conhecer", "quer_aula_experimental": True,
              "consentimento": True, "website": "", "tempo_ms": 8000}
