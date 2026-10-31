"""Driver Control iD (iDBlock, iDAccess, iDFlex, iDFace) pela API HTTP REST "Access API" documentada publicamente
(https://www.controlid.com.br/docs/access-api-pt/).

Fluxo usado (o mesmo no servidor, no agente local e no navegador do totem):

1. ``POST /login.fcgi`` com ``{"login": ..., "password": ...}`` -> ``{"session": "..."}``
2. Liberar: ``POST /execute_actions.fcgi?session=...`` com
   - catraca (iDBlock): ``{"actions": [{"action": "catra", "parameters": "allow=clockwise"}]}``
     (``clockwise`` | ``anticlockwise`` | ``both``);
   - porta/relé (iDAccess, iDFlex, iDFace): ``{"actions": [{"action": "door", "parameters": "door=1"}]}``.
3. Status: ``POST /system_information.fcgi?session=...`` (devolve serial, versão de firmware, rede...).
4. ``POST /logout.fcgi?session=...``.

PRECISA SER VALIDADO NO EQUIPAMENTO REAL (ver docs/progresso-acesso.md): nomes exatos dos parâmetros do iDBlock na
versão de firmware do cliente, se a sessão expira entre giros, o sentido físico de entrada, HTTPS e CORS do aparelho
(para o caminho pelo navegador do totem).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from app.modules.acesso.drivers.base import (
    DadosCatraca,
    Driver,
    ErroDriver,
    PassoHttp,
    PlanoNavegador,
    Resultado,
    SentidoGiro,
    giro_do_sentido,
)

#: fábrica do cliente HTTP (os testes trocam por um com ``httpx.MockTransport``; nunca acessam a rede)
_fabrica: Callable[[DadosCatraca], httpx.Client] | None = None


def definir_fabrica_cliente(fn: Callable[[DadosCatraca], httpx.Client] | None) -> None:
    global _fabrica
    _fabrica = fn


def _cliente(d: DadosCatraca) -> httpx.Client:
    if _fabrica is not None:
        return _fabrica(d)
    # equipamentos de rede local usam certificado autoassinado quando o HTTPS está ligado
    return httpx.Client(base_url=d.url_base, timeout=d.timeout_s, verify=False)  # noqa: S501


def acoes_liberar(d: DadosCatraca, sentido: SentidoGiro) -> list[dict]:
    if d.acao_liberacao == "door":
        return [{"action": "door", "parameters": f"door={d.porta_rele}"}]
    return [{"action": "catra", "parameters": f"allow={giro_do_sentido(d.sentido_entrada, sentido)}"}]


class ControlId(Driver):
    nome = "controlid"
    rotulo = "Control iD (iDBlock / iDAccess / iDFlex)"
    suporta_navegador = True

    def _sessao(self, c: httpx.Client, d: DadosCatraca) -> str:
        if not d.host:
            raise ErroDriver("Informe o IP da catraca.")
        try:
            r = c.post("/login.fcgi", json={"login": d.usuario or "admin", "password": d.senha or ""})
        except httpx.HTTPError as e:
            raise ErroDriver(f"A catraca não respondeu em {d.url_base} ({e.__class__.__name__}).") from None
        if r.status_code in (401, 403):
            raise ErroDriver("Usuário ou senha da catraca recusados.")
        if r.status_code >= 400:
            raise ErroDriver(f"A catraca recusou o login (HTTP {r.status_code}).")
        try:
            sessao = r.json().get("session")
        except ValueError:
            sessao = None
        if not sessao:
            raise ErroDriver("A catraca não devolveu a sessão. Confira usuário e senha.")
        return sessao

    def _post(self, c: httpx.Client, caminho: str, sessao: str, corpo: dict | None = None) -> httpx.Response:
        try:
            r = c.post(caminho, params={"session": sessao}, json=corpo or {})
        except httpx.HTTPError as e:
            raise ErroDriver(f"Falha de comunicação com a catraca ({e.__class__.__name__}).") from None
        if r.status_code >= 400:
            raise ErroDriver(f"A catraca respondeu com erro (HTTP {r.status_code}).")
        return r

    def _sair(self, c: httpx.Client, sessao: str) -> None:
        try:
            c.post("/logout.fcgi", params={"session": sessao})
        except httpx.HTTPError:
            pass

    def liberar(self, dispositivo: DadosCatraca, sentido: SentidoGiro = "entrada") -> Resultado:
        try:
            with _cliente(dispositivo) as c:
                sessao = self._sessao(c, dispositivo)
                try:
                    self._post(c, "/execute_actions.fcgi", sessao, {"actions": acoes_liberar(dispositivo, sentido)})
                finally:
                    self._sair(c, sessao)
        except ErroDriver as e:
            return Resultado(False, str(e))
        return Resultado(True, "Giro liberado.", {"sentido": sentido})

    def status(self, dispositivo: DadosCatraca) -> Resultado:
        try:
            with _cliente(dispositivo) as c:
                sessao = self._sessao(c, dispositivo)
                try:
                    r = self._post(c, "/system_information.fcgi", sessao)
                finally:
                    self._sair(c, sessao)
        except ErroDriver as e:
            return Resultado(False, str(e))
        try:
            info = r.json()
        except ValueError:
            info = {}
        serial = info.get("serial") or info.get("device_id")
        versao = info.get("version")
        partes = [p for p in (f"serial {serial}" if serial else "", f"firmware {versao}" if versao else "") if p]
        return Resultado(True, "Conectado" + (f" ({', '.join(partes)})" if partes else "") + ".",
                         {k: info.get(k) for k in ("serial", "version", "device_id") if k in info})

    def plano_navegador(self, dispositivo: DadosCatraca, acao: str = "liberar", sentido: SentidoGiro = "entrada") -> PlanoNavegador:
        base = dispositivo.url_base
        passos = [PassoHttp("POST", f"{base}/login.fcgi", {"login": dispositivo.usuario or "admin", "password": dispositivo.senha or ""},
                            extrair="session")]
        if acao == "status":
            passos.append(PassoHttp("POST", f"{base}/system_information.fcgi?session={{sessao}}", {}))
        else:
            passos.append(PassoHttp("POST", f"{base}/execute_actions.fcgi?session={{sessao}}",
                                    {"actions": acoes_liberar(dispositivo, sentido)}))
        passos.append(PassoHttp("POST", f"{base}/logout.fcgi?session={{sessao}}", {}))
        return PlanoNavegador(self.nome, passos, "Control iD: login, ação e logout pela rede local.")
