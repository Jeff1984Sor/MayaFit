"""Descoberta do município (código IBGE) pelo CEP ou pelo próprio código, e do provedor que o atende.

CEP -> ViaCEP (devolve o campo `ibge`), reaproveitando `alunos.servico.consultar_viacep`. Código -> API de
localidades do IBGE. Os testes substituem as duas funções (nunca vão à internet).
"""

from __future__ import annotations

import httpx

from app.domain.documentos import so_digitos
from app.modules.alunos import servico as alunos_servico
from app.modules.nfse import provedores


class MunicipioIndisponivel(Exception):
    pass


def consultar_ibge(codigo: str) -> dict | None:
    try:
        r = httpx.get(f"https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo}", timeout=5.0)
        r.raise_for_status()
        d = r.json()
    except (httpx.HTTPError, ValueError):
        raise MunicipioIndisponivel() from None
    if not isinstance(d, dict) or not d.get("nome"):
        return None
    uf = (((d.get("microrregiao") or {}).get("mesorregiao") or {}).get("UF") or {}).get("sigla")
    return {"nome": d["nome"], "uf": uf}


def descobrir(*, cep: str | None = None, codigo: str | None = None) -> dict:
    nome = uf = None
    cod = so_digitos(codigo) or None
    if cep:
        d = so_digitos(cep)
        if len(d) != 8:
            raise ValueError("CEP inválido: informe 8 dígitos.")
        try:
            dados = alunos_servico.consultar_viacep(d)
        except alunos_servico.CepIndisponivel:
            raise MunicipioIndisponivel() from None
        if not dados:
            raise ValueError("CEP não encontrado.")
        cod, nome, uf = so_digitos(dados.get("ibge")) or None, dados.get("localidade"), dados.get("uf")
    elif cod:
        if len(cod) != 7:
            raise ValueError("O código IBGE do município tem 7 dígitos.")
        try:
            achado = consultar_ibge(cod)
        except MunicipioIndisponivel:
            achado = None  # segue só com o código
        if achado:
            nome, uf = achado["nome"], achado["uf"]
    else:
        raise ValueError("Informe o CEP do estúdio ou o código IBGE do município.")
    return {"codigo_municipio": cod, "municipio_nome": nome, "uf": uf, **provedores.descobrir(cod)}
