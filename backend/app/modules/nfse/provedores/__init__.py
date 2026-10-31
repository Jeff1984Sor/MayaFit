"""Registro dos provedores e descoberta do provedor pelo município (código IBGE)."""

from __future__ import annotations

from app.modules.nfse.provedores.base import Provedor
from app.modules.nfse.provedores.nacional import ProvedorNacional
from app.modules.nfse.provedores.sao_paulo import ProvedorSaoPaulo

PROVEDORES: dict[str, type[Provedor]] = {"nacional": ProvedorNacional, "sao_paulo": ProvedorSaoPaulo}

MUNICIPIO_SP = "3550308"

# Capitais que mantêm emissor próprio (não aderiram ao Emissor Nacional para emissão). O MayaFit ainda não fala com
# esses sistemas: a tela avisa e sugere conferir com a prefeitura. Lista a revisar periodicamente (ver progresso).
PROPRIO_NAO_SUPORTADO: dict[str, str] = {
    "3304557": "Rio de Janeiro (Nota Carioca)",
    "3106200": "Belo Horizonte (BHISS Digital)",
    "4106902": "Curitiba (ISS Curitiba)",
    "4314902": "Porto Alegre (NFS-e POA)",
}


def descobrir(codigo_municipio: str | None) -> dict:
    """Qual provedor atende o município do estúdio. Sem rede: tabela local (SP e emissores próprios conhecidos)."""
    cod = (codigo_municipio or "").strip()
    if cod == MUNICIPIO_SP:
        return {"provedor": "sao_paulo", "suportado": True,
                "mensagem": "São Paulo emite pelo sistema próprio da Prefeitura (NFS-e layout 2). Você vai precisar do CCM."}
    if cod in PROPRIO_NAO_SUPORTADO:
        return {"provedor": "nacional", "suportado": False,
                "mensagem": f"{PROPRIO_NAO_SUPORTADO[cod]} usa emissor próprio. Confirme com a prefeitura se o "
                            "Emissor Nacional já é aceito; se não, fale com a MayaCorp."}
    return {"provedor": "nacional", "suportado": True,
            "mensagem": "Seu município usa o Padrão Nacional (Emissor Nacional da NFS-e). MEI e Simples emitem por ele."}
