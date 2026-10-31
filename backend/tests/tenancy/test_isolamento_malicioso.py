"""Isolamento entre estúdios sob ataque: tokens forjados/adulterados, token de um estúdio no endereço de outro, slug
forjado no link de redefinição, primeiro acesso reaproveitado, token do app do aluno trocado de estúdio, host falso."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core import tenancy
from app.core.config import settings
from tests.conftest import SENHA
from tests.tenancy.conftest import HOST_ALFA, HOST_BETA, bearer, entrar


def _assinar(payload: dict, segredo: str | None = None) -> str:
    agora = datetime.now(UTC)
    base = {"iat": agora, "exp": agora + timedelta(minutes=10), "jti": "x" * 32}
    return jwt.encode({**base, **payload}, segredo or settings.jwt_secret, algorithm="HS256")


def _payload(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def test_token_sem_estudio_nao_vale_no_modo_multi(multi, client):
    """Token legítimo na assinatura mas sem `est` (ex.: emitido antes de ligar o modo multi) não abre estúdio nenhum."""
    p = _payload(entrar(client, "ana", host=HOST_ALFA).json()["access_token"])
    p.pop("est")
    sem = {"Authorization": f"Bearer {_assinar(p)}"}
    assert client.get("/api/auth/me", headers=sem).status_code == 401
    assert client.get("/api/auth/me", headers={**sem, "X-Forwarded-Host": HOST_ALFA}).status_code == 401
    assert client.get("/api/auth/me", headers={**sem, "X-Forwarded-Host": HOST_BETA}).status_code == 401


def test_token_adulterado_ou_com_outra_chave(multi, client):
    token = entrar(client, "ana", host=HOST_ALFA).json()["access_token"]
    cab, corpo, sig = token.split(".")
    # troca o estúdio no corpo sem reassinar: a assinatura não confere
    import base64
    import json

    p = _payload(token)
    p["est"] = "beta"
    corpo_falso = base64.urlsafe_b64encode(json.dumps(p, default=str).encode()).rstrip(b"=").decode()
    for falso in (f"{cab}.{corpo_falso}.{sig}", _assinar({**p, "est": "beta"}, segredo="outra-chave-" + "x" * 32)):
        h = {"Authorization": f"Bearer {falso}"}
        assert client.get("/api/auth/me", headers=h).status_code == 401
        assert client.get("/api/auth/me", headers={**h, "X-Forwarded-Host": HOST_BETA}).status_code == 401


def test_token_do_alfa_no_endereco_do_beta_so_ve_o_alfa(multi, client):
    alfa = entrar(client, "ana", host=HOST_ALFA).json()
    h = {"Authorization": f"Bearer {alfa['access_token']}", "X-Forwarded-Host": HOST_BETA, "Host": HOST_BETA}
    usuarios = {u["email"] for u in client.get("/api/config/usuarios", headers=h).json()}
    assert "ana@alfa.com" in usuarios and not any(e.endswith("@beta.com") for e in usuarios)
    # o refresh também fica no estúdio do token, qualquer que seja o endereço
    r = client.post("/api/auth/refresh", json={"refresh_token": alfa["refresh_token"]}, headers={"X-Forwarded-Host": HOST_BETA})
    assert r.status_code == 200 and r.json()["usuario"]["estudio"]["slug"] == "alfa"


def test_token_de_estudio_que_ficou_inativo(multi, client):
    beta = entrar(client, "bia").json()
    try:
        multi.definir_status("beta", "inativo")
        assert client.post("/api/auth/refresh", json={"refresh_token": beta["refresh_token"]}).status_code == 401
        # nem caindo no endereço de outro estúdio ativo
        h = {"Authorization": f"Bearer {beta['access_token']}", "X-Forwarded-Host": HOST_ALFA}
        assert client.get("/api/auth/me", headers=h).status_code == 401
    finally:
        multi.definir_status("beta", "teste")


def test_slug_forjado_no_link_de_redefinicao(multi, client, emails):
    client.post("/api/auth/forgot", json={"identificador": "carlos"})
    token = emails[-1][2].split("token=")[1].split()[0]
    slug, aleatorio = token.split(".", 1)
    assert slug == "alfa"
    for forjado in (f"beta.{aleatorio}", f"inexistente.{aleatorio}", aleatorio, f"alfa.{aleatorio}x", "."):
        r = client.post("/api/auth/reset", json={"token": forjado, "senha": "Outra@Senha9"})
        assert r.status_code == 400, forjado
    # as tentativas forjadas não consomem o link verdadeiro
    assert client.post("/api/auth/reset", json={"token": token, "senha": SENHA}).status_code == 200


def test_codigo_whatsapp_e_forgot_no_login_ambiguo_nao_revelam(multi, client):
    a = client.post("/api/auth/forgot", json={"identificador": "ana"})
    b = client.post("/api/auth/forgot", json={"identificador": "ninguem"})
    assert a.json() == b.json() and a.status_code == b.status_code == 200
    r = client.post("/api/auth/reset-codigo", json={"identificador": "ana", "codigo": "123456", "senha": SENHA})
    assert r.status_code == 400


def test_primeiro_acesso_forjado_ou_reaproveitado(multi, client):
    from app.core.security import criar_token

    # link para um estúdio que já tem administrador: não cria um segundo master
    with tenancy.usando(multi.por_slug("alfa")):
        tk = criar_token("alfa", "primeiro", {"email": "intruso@x.com"})
    dados = {"token": tk, "nome": "Intruso", "email": "intruso@x.com", "login": "intruso", "senha": SENHA}
    assert client.post("/api/auth/primeiro-acesso", json=dados).status_code == 409
    # sem estúdio no token, com outro tipo de token ou assinado com outra chave: inválido
    sem_est = _assinar({"sub": "beta", "typ": "primeiro"})
    access = entrar(client, "ana", host=HOST_ALFA).json()["access_token"]
    outra = _assinar({"sub": "beta", "typ": "primeiro", "est": "beta"}, segredo="outra-chave-" + "y" * 32)
    for t in (sem_est, access, outra):
        assert client.post("/api/auth/primeiro-acesso", json={**dados, "token": t}).status_code == 400
        assert client.get("/api/auth/primeiro-acesso", params={"token": t}).status_code in (400, 401)


def test_token_do_app_do_aluno_preso_ao_estudio(multi, client):
    from app.modules.app_aluno import servico as srv

    with tenancy.usando(multi.por_slug("alfa")):
        tokens = srv.emitir_tokens(1)
    p = _payload(tokens["access_token"])
    assert p["est"] == "alfa"
    # o mesmo aluno_id no banco do beta: o token do alfa não serve lá
    with tenancy.usando(multi.por_slug("beta")), pytest.raises(srv.NaoAutenticado):
        srv.decodificar(tokens["access_token"], srv.TIPO_ACCESS)
    p.pop("est")
    sem_est = jwt.encode(p, settings.jwt_secret, algorithm="HS256")
    with tenancy.usando(multi.por_slug("beta")), pytest.raises(srv.NaoAutenticado):
        srv.decodificar(sem_est, srv.TIPO_ACCESS)
    r = client.get("/api/aluno-app/me", headers={"Authorization": f"Bearer {sem_est}", "X-Forwarded-Host": HOST_BETA})
    assert r.status_code == 401
    # token da equipe não serve no app do aluno (e vice-versa), mesmo no estúdio certo
    equipe = bearer(entrar(client, "ana", host=HOST_ALFA))
    assert client.get("/api/aluno-app/me", headers=equipe).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 401


def test_host_falso(multi, client):
    # Host fora da lista e fora do controle: recusado antes de qualquer rota
    assert client.get("/api/public/identidade", headers={"Host": "beta.mayafit.test.evil.com"}).status_code == 400
    # X-Forwarded-Host desconhecido não escolhe estúdio nenhum (e nada abre banco)
    assert client.get("/api/public/identidade", headers={"X-Forwarded-Host": "evil.com"}).status_code == 401
    # no endereço do beta, o login do alfa não entra
    assert entrar(client, "carlos", host=HOST_BETA).status_code == 401
