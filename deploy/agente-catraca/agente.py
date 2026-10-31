"""Agente local de catraca do MayaFit (OPCIONAL).

Para quando o navegador do totem não consegue falar com a catraca (HTTPS/CORS) ou o equipamento não fala HTTP
(Henry/Topdata). Roda num computador da recepção, na MESMA rede da catraca, e faz polling seguro no servidor:

    GET  {servidor}/api/catraca-agente/comandos               (cabeçalho X-Dispositivo-Token)
    POST {servidor}/api/catraca-agente/comandos/{id}/resultado  {"ok": true, "mensagem": "..."}

Só conexões de SAÍDA (https) — nada a abrir no roteador. O token é o de um dispositivo do tipo "agente" cadastrado em
Controle de acesso › Catracas e totens (revogável). Sem dependências: só a biblioteca padrão do Python 3.10+.

Uso:
    set MAYAFIT_SERVIDOR=https://estudio.mayafit.com.br
    set MAYAFIT_TOKEN=mfdisp_...
    python agente.py

Serviço no Windows: NSSM (`nssm install MayaFitCatraca python C:\\mayafit\\agente.py`) ou Agendador de Tarefas.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request

SERVIDOR = os.environ.get("MAYAFIT_SERVIDOR", "").rstrip("/")
TOKEN = os.environ.get("MAYAFIT_TOKEN", "")
INTERVALO_S = float(os.environ.get("MAYAFIT_INTERVALO", "1.0"))
TIMEOUT_CATRACA_S = 4.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("agente-catraca")

# equipamentos de rede local usam certificado autoassinado quando o HTTPS está ligado
_SSL_LOCAL = ssl.create_default_context()
_SSL_LOCAL.check_hostname = False
_SSL_LOCAL.verify_mode = ssl.CERT_NONE


def _json(url: str, corpo: dict | None = None, *, cabecalhos: dict | None = None, timeout: float = 10, contexto=None) -> tuple[int, dict]:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method="POST" if dados is not None else "GET",
                                 headers={"Content-Type": "application/json", **(cabecalhos or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=contexto) as r:
            texto = r.read().decode() or "{}"
            return r.status, json.loads(texto) if texto.strip().startswith("{") or texto.strip().startswith("[") else {}
    except urllib.error.HTTPError as e:
        return e.code, {}


# ---------------------------------------------------------------------------------------------------- drivers
def giro(sentido_entrada: str, sentido: str) -> str:
    if sentido_entrada == "both":
        return "both"
    if sentido == "entrada":
        return sentido_entrada
    return "anticlockwise" if sentido_entrada == "clockwise" else "clockwise"


def controlid(c: dict, acao: str, sentido: str) -> tuple[bool, str]:
    """Mesmo fluxo do driver do servidor (app/modules/acesso/drivers/controlid.py)."""
    base = f"{'https' if c.get('usar_https') else 'http'}://{c['host']}{':' + str(c['porta']) if c.get('porta') else ''}"
    ctx = _SSL_LOCAL if c.get("usar_https") else None
    try:
        st, j = _json(f"{base}/login.fcgi", {"login": c.get("usuario") or "admin", "password": c.get("senha") or ""},
                      timeout=TIMEOUT_CATRACA_S, contexto=ctx)
        sessao = j.get("session")
        if st >= 400 or not sessao:
            return False, "Usuário ou senha da catraca recusados."
        if acao == "status":
            st, info = _json(f"{base}/system_information.fcgi?session={sessao}", {}, timeout=TIMEOUT_CATRACA_S, contexto=ctx)
            msg = f"Conectado (serial {info.get('serial', '?')})." if st < 400 else f"Erro HTTP {st}."
        else:
            if c.get("acao_liberacao") == "door":
                acoes = [{"action": "door", "parameters": f"door={c.get('porta_rele') or 1}"}]
            else:
                acoes = [{"action": "catra", "parameters": f"allow={giro(c.get('sentido_entrada', 'clockwise'), sentido)}"}]
            st, _ = _json(f"{base}/execute_actions.fcgi?session={sessao}", {"actions": acoes}, timeout=TIMEOUT_CATRACA_S, contexto=ctx)
            msg = "Giro liberado." if st < 400 else f"Erro HTTP {st}."
        _json(f"{base}/logout.fcgi?session={sessao}", {}, timeout=TIMEOUT_CATRACA_S, contexto=ctx)
        return st < 400, msg
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, f"A catraca não respondeu ({e.__class__.__name__})."


def henry(c: dict, acao: str, sentido: str) -> tuple[bool, str]:
    # ESQUELETO: implementar com o protocolo TCP/SDK do fabricante (ver drivers/henry.py no servidor)
    return False, "Driver Henry/Topdata ainda não implementado no agente."


def simulado(c: dict, acao: str, sentido: str) -> tuple[bool, str]:
    return True, "Giro liberado (simulado no agente)."


DRIVERS = {"controlid": controlid, "henry": henry, "simulado": simulado}


# ---------------------------------------------------------------------------------------------------- laço
def ciclo() -> None:
    cab = {"X-Dispositivo-Token": TOKEN}
    st, comandos = _json(f"{SERVIDOR}/api/catraca-agente/comandos", cabecalhos=cab)
    if st == 401:
        raise SystemExit("Token recusado (revogado?). Gere um novo em Catracas e totens.")
    if st >= 400:
        log.warning("Servidor respondeu %s", st)
        return
    for cmd in comandos if isinstance(comandos, list) else []:
        cat = cmd["catraca"]
        ok, msg = DRIVERS.get(cat.get("driver"), simulado)(cat, cmd["acao"], cmd["sentido"])
        log.info("Comando %s (%s, %s) em %s: %s", cmd["id"], cmd["acao"], cmd["sentido"], cat.get("nome"), msg)
        _json(f"{SERVIDOR}/api/catraca-agente/comandos/{cmd['id']}/resultado", {"ok": ok, "mensagem": msg[:300]}, cabecalhos=cab)


def main() -> None:
    if not SERVIDOR.startswith("https://") and "localhost" not in SERVIDOR:
        raise SystemExit("Defina MAYAFIT_SERVIDOR com https://")
    if not TOKEN.startswith("mfdisp_"):
        raise SystemExit("Defina MAYAFIT_TOKEN com o token do dispositivo (tipo agente).")
    log.info("Agente de catraca ligado em %s", SERVIDOR)
    while True:
        try:
            ciclo()
        except SystemExit:
            raise
        except Exception as e:  # rede caiu etc.: tenta de novo
            log.warning("Falha no ciclo: %s", e)
            time.sleep(5)
        time.sleep(INTERVALO_S)


if __name__ == "__main__":
    main()
