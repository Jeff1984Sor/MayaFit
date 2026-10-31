"""Tradução dos códigos de retorno da Prefeitura de SP para português claro + ação sugerida (seção 7.4).

Porte do MayaJus (prefeitura_sp/erros.py), textos adaptados para estúdio (aluno = tomador).

Mapeamento inicial: os códigos devem ser conferidos com a tabela de erros do Manual v3.3.4 e
das NTs 003/004 durante a homologação. Códigos desconhecidos caem no texto genérico + descrição técnica.
"""

from dataclasses import dataclass

from app.modules.nfse.provedores.base import ErroNota


@dataclass(frozen=True)
class ErroHumano:
    mensagem: str
    acao: str
    campo: str | None = None


MAPA: dict[int, ErroHumano] = {
    1057: ErroHumano(
        "O certificado não conseguiu assinar esta nota.",
        "Verifique se ele está válido em Configurações › NFS-e.",
    ),
    1206: ErroHumano(
        "A assinatura do recibo não confere.",
        "Confira se o certificado ativo é da empresa emissora.",
    ),
    1101: ErroHumano("O CNPJ do tomador está incorreto.", "Corrija o CNPJ e reenvie a nota.", "tomador.documento"),
    1102: ErroHumano("O CPF do aluno (tomador) está incorreto.", "Corrija o CPF no cadastro do aluno e reenvie a nota.", "tomador.documento"),
    1112: ErroHumano("O CEP do tomador não existe.", "Corrija o CEP e reenvie.", "tomador.endereco"),
    1209: ErroHumano("Este recibo já virou nota.", "Nenhuma ação: o MayaFit busca a nota existente.", None),
    1211: ErroHumano(
        "O código de serviço não é permitido para a empresa.",
        "Confira com o contador o código de serviço municipal (5 dígitos) em Configurações › NFS-e.",
        "servico",
    ),
    1214: ErroHumano("A alíquota informada não confere com o código de serviço.", "Corrija a alíquota.", "aliquota"),
    1223: ErroHumano("A data do recibo está fora do período permitido.", "Corrija a competência.", "competencia"),
    1301: ErroHumano("O CCM da empresa emissora não está habilitado para emitir NFS-e.", "Fale com o contador."),
    1306: ErroHumano("O certificado não pertence ao CNPJ remetente.", "Ative o certificado correto."),
    1601: ErroHumano(
        "A Prefeitura não aceitou os campos de IBS/CBS.",
        "Revise NBS, cClassTrib e cIndOp em Configurações › NFS-e (defina com o contador).",
        "class_trib",
    ),
    1602: ErroHumano("O código NBS informado não existe.", "Corrija o NBS em Configurações › NFS-e.", "nbs"),
    1603: ErroHumano("A classificação tributária (cClassTrib) não combina com o CST.", "Revise os parâmetros IBS/CBS em Configurações › NFS-e.", "class_trib"),
    1404: ErroHumano("Esta nota já está cancelada.", "Nenhuma ação necessária."),
    1405: ErroHumano(
        "O prazo de cancelamento desta nota já passou.",
        "Cancele pelo portal da Prefeitura com processo administrativo, ou emita nota de substituição.",
    ),
}


def humanizar(codigo: int | None, descricao_tecnica: str) -> ErroHumano:
    if codigo is not None and codigo in MAPA:
        return MAPA[codigo]
    d = descricao_tecnica.lower()
    if "assinatura" in d:
        return MAPA[1057]
    if "cnpj" in d and "tomador" in d:
        return MAPA[1101]
    if "cpf" in d and "tomador" in d:
        return MAPA[1102]
    if "já convertido" in d or "ja convertido" in d:
        return MAPA[1209]
    return ErroHumano(
        f"A Prefeitura recusou este recibo: {descricao_tecnica}",
        "Corrija os dados indicados e reenvie. Se persistir, fale com a MayaCorp.",
    )


def erro_nota(codigo: int | None, descricao: str) -> ErroNota:
    h = humanizar(codigo, descricao)
    return ErroNota(h.mensagem, h.acao, codigo=str(codigo) if codigo is not None else None, campo=h.campo,
                    tecnico=f"{codigo or ''} {descricao}".strip())
