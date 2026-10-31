"""Códigos de rejeição da Sefin Nacional traduzidos para português claro + ação.

Mapeamento INICIAL: códigos confirmados em relatos da produção restrita (E0010, E0015, E0717, E1228, E1235,
E2404, E999) e regras do ANEXO I. Conferir a tabela completa do ANEXO I (aba de regras de negócio) durante a
homologação. Código desconhecido cai na heurística por palavras-chave e, por fim, no texto do provedor.
"""

from __future__ import annotations

from app.modules.nfse.provedores.base import ErroNota

_CONFIG = "Abrir Configurações › NFS-e"

MAPA: dict[str, tuple[str, str, str | None]] = {
    "E0010": ("A série da DPS está fora da faixa permitida para este tipo de emissor.",
              "Ajuste a série em Configurações › NFS-e (aplicativo próprio usa série numérica entre 1 e 49999).", "serie"),
    "E0015": ("A competência da nota é posterior à data de emissão.",
              "Use uma competência igual ou anterior a hoje e emita de novo.", "competencia"),
    "E0717": ("A Sefin Nacional não recebeu a assinatura digital da nota.",
              "Confira o certificado A1 em Configurações › NFS-e e tente de novo.", "certificado"),
    "E1228": ("O XML foi montado com prefixo de namespace, que a Sefin não aceita.",
              "Erro interno do MayaFit: avise o suporte MayaCorp com o número da nota.", None),
    "E1235": ("O identificador da DPS não confere com os dados do prestador.",
              "Confira CNPJ, município (IBGE) e série em Configurações › NFS-e.", "configuracao"),
    "E2404": ("Ainda não existe nota gerada para esta DPS.",
              "Nenhuma ação: o MayaFit reenvia sozinho.", None),
    "E999": ("A Sefin Nacional devolveu um erro não catalogado.",
             "Tente novamente em alguns minutos. Se repetir, confira se o município aderiu ao Emissor Nacional.", None),
}

# (palavras que precisam aparecer, mensagem, ação, campo)
HEURISTICAS: list[tuple[tuple[str, ...], str, str, str | None]] = [
    (("assinatura",), "A assinatura digital da nota não foi aceita.",
     "Confira se o certificado A1 é do CNPJ do estúdio e está dentro da validade.", "certificado"),
    (("certificado",), "O certificado digital não foi aceito.",
     "Envie novamente o certificado A1 (.pfx) em Configurações › NFS-e.", "certificado"),
    (("cpf", "tomador"), "O CPF do aluno (tomador) está incorreto ou não existe na Receita.",
     "Corrija o CPF no cadastro do aluno e reenvie a nota.", "tomador.documento"),
    (("cnpj", "tomador"), "O CNPJ do tomador está incorreto.", "Corrija o CNPJ e reenvie a nota.", "tomador.documento"),
    (("convênio",), "O município do estúdio não está conveniado ao Emissor Nacional.",
     "Confirme com a prefeitura se a emissão é pelo Padrão Nacional ou por sistema próprio.", "configuracao"),
    (("convenio",), "O município do estúdio não está conveniado ao Emissor Nacional.",
     "Confirme com a prefeitura se a emissão é pelo Padrão Nacional ou por sistema próprio.", "configuracao"),
    (("alíquota",), "A alíquota do ISS não confere com a parametrização do município.",
     "Desmarque 'Informar alíquota na DPS' ou corrija a alíquota em Configurações › NFS-e.", "aliquota"),
    (("aliquota",), "A alíquota do ISS não confere com a parametrização do município.",
     "Desmarque 'Informar alíquota na DPS' ou corrija a alíquota em Configurações › NFS-e.", "aliquota"),
    (("código de tributação",), "O código de serviço não é aceito pelo município.",
     "Confira com o contador o item da LC 116 (06.04 atividades físicas, 04.08 fisioterapia).", "servico"),
    (("cadastro", "contribuinte"), "O CNPJ do estúdio não está habilitado no Cadastro Nacional de Contribuintes da NFS-e.",
     "Peça à prefeitura/contador a habilitação para emitir pelo Padrão Nacional.", "configuracao"),
    (("já", "gerada"), "Esta DPS já virou nota.", "Abra a nota existente: o MayaFit busca o número sozinho.", None),
    (("simples nacional",), "O regime do Simples Nacional informado não confere com a Receita.",
     "Confira o regime tributário em Configurações › NFS-e.", "regime"),
]


def humanizar(codigo: str | None, descricao: str, complemento: str | None = None) -> ErroNota:
    tecnico = f"{codigo or ''} {descricao}{(' - ' + complemento) if complemento else ''}".strip()
    if codigo and codigo.upper() in MAPA:
        m, a, campo = MAPA[codigo.upper()]
        return ErroNota(m, a, codigo=codigo, campo=campo, tecnico=tecnico)
    d = f"{descricao} {complemento or ''}".lower()
    for palavras, m, a, campo in HEURISTICAS:
        if all(p in d for p in palavras):
            return ErroNota(m, a, codigo=codigo, campo=campo, tecnico=tecnico)
    return ErroNota(
        f"A Sefin Nacional recusou a nota: {descricao}",
        "Corrija o dado indicado e reenvie. Se não souber o que fazer, envie o print ao suporte MayaCorp.",
        codigo=codigo, tecnico=tecnico,
    )
