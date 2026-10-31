"""Serviço da NFS-e: configuração, fila de emissão (idempotente), cancelamento, e-mail e consultas.

Assinaturas estáveis para outros módulos (não reimplementar):
- `nota_do_recebimento(db, conta_receber_id) -> NotaFiscal | None`: a nota viva de um recebimento.
- `enfileirar_recebimento(db, conta_receber_id, *, origem="recebimento", usuario_id=None) -> NotaFiscal`:
  põe o recebimento PAGO na fila (idempotente pela chave `rec:<id>`). Não faz commit.
- `processar_fila(db, limite=20) -> int`: chamado pelo worker.

Fluxo de uma nota: `pendente` -> `processando` -> `emitida` | `validada` | `rejeitada` | (falha de comunicação:
volta a `pendente` com retentativa crescente e, na próxima vez, CONSULTA o provedor antes de reenviar) -> `falha`
depois de `MAX_TENTATIVAS`. Cancelada libera a chave para nova emissão.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import email as email_core
from app.core import segredos, storage
from app.core.config import settings
from app.core.db import agora
from app.core.models import Identidade
from app.domain.documentos import so_digitos
from app.domain.financeiro import hoje_de_negocio
from app.modules import registrar_modelos
from app.modules.alunos.models import Aluno, AlunoEndereco
from app.modules.financeiro.models import ContaReceber, StatusReceber
from app.modules.nfse import certificado as certs
from app.modules.nfse import pdf, provedores, regras
from app.modules.nfse.models import ConfigNfse, Modo, NotaEvento, NotaFiscal, OrigemNota, Provedor, StatusNota
from app.modules.nfse.provedores.base import (
    DadosNota,
    ErroConfiguracao,
    ErroNota,
    FalhaComunicacao,
    Prestador,
    Tomador,
    Transporte,
)

registrar_modelos()
log = logging.getLogger(__name__)

storage.registrar_categoria("nfse", "nfse.ver", {".pdf"}, 10)

ROTULO_STATUS = {
    "pendente": "Na fila", "processando": "Enviando", "emitida": "Emitida", "validada": "Validada (teste)",
    "rejeitada": "Rejeitada", "falha": "Falha de comunicação", "cancelada": "Cancelada",
}
VIVAS = (StatusNota.pendente, StatusNota.processando, StatusNota.emitida, StatusNota.validada, StatusNota.rejeitada,
         StatusNota.falha)

# Transporte HTTP alternativo (testes). None = o próprio do provedor (httpx com TLS mútuo ou simulador).
_transporte_teste: Transporte | None = None


def definir_transporte(t: Transporte | None) -> None:
    global _transporte_teste
    _transporte_teste = t


def erro(status: int, mensagem: str) -> HTTPException:
    return HTTPException(status, mensagem)


def hoje() -> date:
    return hoje_de_negocio(agora())


# ================================================================================================ configuração
def obter_config(db: Session) -> ConfigNfse:
    cfg = db.get(ConfigNfse, 1)
    if cfg is None:
        cfg = ConfigNfse(id=1, discriminacao_modelo=regras.DISCRIMINACAO_PADRAO)
        db.add(cfg)
        db.flush()
    return cfg


def emissao_real_liberada(cfg: ConfigNfse) -> bool:
    """Nota de verdade só com AMBIENTE=prod no servidor E modo Produção escolhido na tela."""
    return settings.ambiente == "prod" and cfg.modo == Modo.producao


def info_certificado(cfg: ConfigNfse, ref: date | None = None) -> dict[str, Any]:
    s = regras.situacao_certificado(cfg.certificado_valido_ate, ref or hoje())
    return {
        "configurado": cfg.certificado_pfx_cifrado is not None, "titular": cfg.certificado_titular,
        "cnpj": cfg.certificado_cnpj, "emissor": cfg.certificado_emissor, "valido_de": cfg.certificado_valido_de,
        "valido_ate": cfg.certificado_valido_ate, **s,
        "cnpj_confere": (cfg.certificado_cnpj[:8] == (cfg.cnpj or "")[:8]) if cfg.certificado_cnpj and cfg.cnpj else None,
    }


def pendencias_config(cfg: ConfigNfse, ref: date | None = None) -> list[dict[str, Any]]:
    """O que impede (erro) ou recomenda revisão (aviso) antes de emitir. Usado no assistente, no painel e no raio-x."""
    p: list[dict[str, Any]] = []

    def add(nivel, campo, mensagem, acao):
        p.append({"nivel": nivel, "campo": campo, "mensagem": mensagem, "acao": acao, "link": "/configuracoes/nfse"})

    if not cfg.ativo:
        add("erro", "ativo", "A emissão de NFS-e está desligada.", "Conclua o assistente e ligue a emissão.")
    if not regras.validar_cnpj(cfg.cnpj):
        add("erro", "cnpj", "CNPJ do estúdio ausente ou inválido.", "Informe o CNPJ no passo 1 do assistente.")
    if not cfg.razao_social:
        add("erro", "razao_social", "Razão social não informada.", "Informe a razão social no passo 1.")
    if not cfg.codigo_municipio or len(cfg.codigo_municipio) != 7:
        add("erro", "codigo_municipio", "Município (código IBGE) não informado.", "Busque o município pelo CEP no passo 1.")
    if cfg.provedor == Provedor.sao_paulo:
        if len(so_digitos(cfg.inscricao_municipal)) != 8:
            add("erro", "inscricao_municipal", "São Paulo exige o CCM (inscrição municipal de 8 dígitos).",
                "Informe o CCM no passo 1.")
        if len(so_digitos(cfg.codigo_servico_municipal)) != 5:
            add("erro", "codigo_servico_municipal", "Informe o código de serviço da Prefeitura de SP (5 dígitos).",
                "Peça ao contador o código usado pelo estúdio (passo 2).")
        ex = cfg.parametros_extras or {}
        faltando = [k for k in ("nbs", "class_trib", "ind_operacao") if not so_digitos(ex.get(k) or (cfg.nbs if k == "nbs" else None))]
        if faltando:
            add("erro", "parametros_extras", "Faltam parâmetros IBS/CBS do layout 2 (NBS, cClassTrib, cIndOp).",
                "Defina com o contador e preencha no passo 2 (São Paulo exige desde 2026).")
    if cfg.regime != "mei" and not (Decimal("2") <= Decimal(cfg.aliquota_iss or 0) <= Decimal("5")):
        add("erro", "aliquota_iss", "A alíquota do ISS deve ficar entre 2% e 5%.", "Corrija a alíquota no passo 2.")
    if cfg.regime == "simples" and cfg.provedor == Provedor.nacional and cfg.percentual_tributos_sn is None:
        add("aviso", "percentual_tributos_sn", "Sem o percentual aproximado de tributos do Simples (Lei 12.741).",
            "Informe a alíquota efetiva do DAS no passo 2 (o contador sabe).")
    cert = info_certificado(cfg, ref)
    if cfg.modo != Modo.simulado:
        if cert["situacao"] == "ausente":
            add("erro", "certificado", "Fora do modo simulado é preciso o certificado A1 (.pfx).", "Envie o certificado no passo 3.")
        elif cert["situacao"] == "vencido":
            add("erro", "certificado", cert["mensagem"], "Renove o certificado com a certificadora e envie o novo .pfx.")
    if cert["situacao"] == "vencendo":
        add("aviso", "certificado", cert["mensagem"], "Providencie a renovação e envie o novo .pfx no passo 3.")
    if cert.get("cnpj_confere") is False:
        add("erro", "certificado", "O certificado é de outro CNPJ.", "Envie o certificado A1 do CNPJ do estúdio.")
    if cfg.modo == Modo.producao and settings.ambiente != "prod":
        add("erro", "modo", "Modo Produção escolhido, mas este servidor não é o de produção.",
            "Use Teste (homologação) aqui; a emissão real só acontece no servidor de produção.")
    desconhecidas = regras.variaveis_desconhecidas(cfg.discriminacao_modelo)
    if desconhecidas:
        add("aviso", "discriminacao_modelo", f"Variáveis desconhecidas na discriminação: {', '.join(desconhecidas)}.",
            "Use só as variáveis listadas no passo 4.")
    return p


def config_out(db: Session, cfg: ConfigNfse) -> dict[str, Any]:
    prov = provedores.PROVEDORES[cfg.provedor.value if hasattr(cfg.provedor, "value") else cfg.provedor]
    return {
        **{c: getattr(cfg, c) for c in (
            "ativo", "cnpj", "razao_social", "inscricao_municipal", "codigo_municipio", "municipio_nome", "uf", "email",
            "telefone", "regime", "item_lista_servico", "codigo_tributacao_nacional", "codigo_servico_municipal", "nbs",
            "aliquota_iss", "iss_retido", "informar_aliquota", "percentual_tributos_sn", "discriminacao_modelo", "serie",
            "proximo_numero", "parametros_extras", "emissao_automatica", "automatica_desde", "enviar_email_aluno")},
        "provedor": str(cfg.provedor), "modo": str(cfg.modo),
        "certificado": info_certificado(cfg), "emissao_real_liberada": emissao_real_liberada(cfg),
        "ambiente_servidor": settings.ambiente, "pendencias": pendencias_config(cfg), "provedor_rotulo": prov.rotulo,
    }


def salvar_config(db: Session, cfg: ConfigNfse, dados: dict[str, Any]) -> list[str]:
    """Aplica os campos e devolve a lista de campos alterados (para a auditoria, sem segredos)."""
    if dados.get("cnpj") and not regras.validar_cnpj(dados["cnpj"]):
        raise erro(422, "CNPJ inválido.")
    if dados.get("codigo_municipio") and len(dados["codigo_municipio"]) != 7:
        raise erro(422, "O código IBGE do município tem 7 dígitos.")
    try:
        dados["codigo_tributacao_nacional"] = regras.codigo_tributacao_nacional(dados.get("item_lista_servico") or "06.04")
    except ValueError as e:
        raise erro(422, str(e)) from None
    if dados.get("emissao_automatica") and not dados.get("automatica_desde"):
        dados["automatica_desde"] = hoje()
    usadas = db.scalar(select(func.max(NotaFiscal.numero_dps)).where(NotaFiscal.serie == dados.get("serie", cfg.serie)))
    if usadas and dados.get("proximo_numero", cfg.proximo_numero) <= usadas:
        dados["proximo_numero"] = usadas + 1  # nunca reaproveitar número de DPS/RPS já usado
    alterados = []
    for k, v in dados.items():
        if getattr(cfg, k) != v:
            alterados.append(k)
            setattr(cfg, k, v)
    return alterados


def salvar_certificado(cfg: ConfigNfse, pfx: bytes, senha: str) -> certs.InfoCertificado:
    if not pfx or len(pfx) > 200_000:
        raise erro(422, "Envie o arquivo .pfx do certificado A1 (até 200 KB).")
    try:
        carregado = certs.carregar_pfx(pfx, senha)
    except certs.CertificadoInvalido as e:
        raise erro(422, str(e)) from None
    info = certs.info(carregado)
    if info.valido_ate < hoje():
        raise erro(422, f"Este certificado venceu em {info.valido_ate:%d/%m/%Y}. Envie um certificado válido.")
    cfg.certificado_pfx_cifrado, cfg.certificado_senha_cifrada = certs.cifrar(pfx, senha)
    cfg.certificado_titular = info.titular[:200]
    cfg.certificado_cnpj = info.cnpj
    cfg.certificado_emissor = info.emissor[:200]
    cfg.certificado_valido_de = info.valido_de
    cfg.certificado_valido_ate = info.valido_ate
    cfg.certificado_enviado_em = agora()
    if not cfg.cnpj and info.cnpj:
        cfg.cnpj = info.cnpj
    if not cfg.razao_social and info.titular:
        cfg.razao_social = info.titular[:150]
    return info


def remover_certificado(cfg: ConfigNfse) -> None:
    for c in ("certificado_pfx_cifrado", "certificado_senha_cifrada", "certificado_titular", "certificado_cnpj",
              "certificado_emissor", "certificado_valido_de", "certificado_valido_ate", "certificado_enviado_em"):
        setattr(cfg, c, None)


# ================================================================================================ provedor
def prestador_de(cfg: ConfigNfse) -> Prestador:
    extras = dict(cfg.parametros_extras or {})
    if cfg.nbs:
        extras.setdefault("nbs", cfg.nbs)
    return Prestador(cnpj=cfg.cnpj or "", razao_social=cfg.razao_social or "", inscricao_municipal=cfg.inscricao_municipal,
                     codigo_municipio=cfg.codigo_municipio or "", regime=cfg.regime, email=cfg.email,
                     telefone=cfg.telefone, extras=extras)


def provedor_para(cfg: ConfigNfse, *, modo: str | None = None, provedor: str | None = None):
    modo = str(modo or cfg.modo)
    cert = None
    if cfg.certificado_pfx_cifrado and cfg.certificado_senha_cifrada:
        try:
            cert = certs.abrir(cfg.certificado_pfx_cifrado, cfg.certificado_senha_cifrada)
        except (segredos.SegredoInvalido, certs.CertificadoInvalido) as e:
            if modo != "simulado":
                raise ErroConfiguracao("Não foi possível abrir o certificado guardado. Envie o .pfx novamente.") from e
    classe = provedores.PROVEDORES[str(provedor or cfg.provedor)]
    return classe(prestador_de(cfg), modo=modo, cert=cert, transporte=_transporte_teste)


def dados_da_nota(nota: NotaFiscal, cfg: ConfigNfse) -> DadosNota:
    return DadosNota(
        serie=nota.serie, numero=nota.numero_dps, competencia=nota.competencia, discriminacao=nota.discriminacao,
        item_lista_servico=nota.item_lista_servico, codigo_tributacao_nacional=nota.codigo_tributacao_nacional,
        codigo_servico_municipal=nota.codigo_servico_municipal, valor=Decimal(nota.valor_servico),
        deducoes=Decimal(nota.deducoes or 0), aliquota=Decimal(nota.aliquota), iss_retido=nota.iss_retido,
        tomador=Tomador(nota.tomador_documento, nota.tomador_nome, nota.tomador_email, nota.tomador_endereco),
        nbs=cfg.nbs, informar_aliquota=cfg.informar_aliquota, percentual_tributos_sn=cfg.percentual_tributos_sn,
        chave_acesso=nota.chave_acesso, numero_nfse=nota.numero_nfse, id_dps=nota.id_dps,
    )


# ================================================================================================ rascunho
@dataclass
class Rascunho:
    """Uma nota antes de entrar na fila (resultado da preparação; o raio-x analisa uma lista deles)."""

    chave: str
    origem: str
    tomador_tipo: str
    tomador_nome: str
    tomador_documento: str | None
    tomador_email: str | None
    valor: Decimal
    competencia: date
    discriminacao: str
    aluno_id: int | None = None
    conta_receber_id: int | None = None
    tomador_endereco: dict[str, Any] | None = None
    problemas: list[dict[str, Any]] = field(default_factory=list)


def _nome_estudio(db: Session) -> str:
    ident = db.get(Identidade, 1)
    return ident.nome_exibicao if ident else "Estúdio"


def _endereco_aluno(db: Session, aluno_id: int) -> dict[str, Any] | None:
    e = db.scalar(select(AlunoEndereco).where(AlunoEndereco.aluno_id == aluno_id))
    if not e:
        return None
    return {"cep": e.cep, "logradouro": e.logradouro, "numero": e.numero, "bairro": e.bairro, "cidade": e.cidade}


def _variaveis(db: Session, *, nome: str, doc: str | None, descricao: str | None, competencia: date, valor: Decimal,
               conta: ContaReceber | None = None) -> dict[str, str]:
    return {
        "aluno": nome, "cpf": regras.formatar_documento(doc), "descricao": descricao or "aulas",
        "competencia": regras.competencia_texto(competencia), "valor": regras.brl(valor),
        "estudio": _nome_estudio(db),
        "vencimento": f"{conta.vencimento:%d/%m/%Y}" if conta and conta.vencimento else "",
        "pagamento": f"{conta.pagamento:%d/%m/%Y}" if conta and conta.pagamento else "",
    }


def _competencia_da_conta(conta: ContaReceber) -> date:
    c = conta.competencia or ""
    if len(c) == 7 and c[4] == "-" and c[5:].isdigit() and 1 <= int(c[5:]) <= 12:
        return date(int(c[:4]), int(c[5:]), 1)
    return conta.pagamento or conta.vencimento


def rascunho_de_recebimento(db: Session, cfg: ConfigNfse, conta: ContaReceber, origem: str = "recebimento") -> Rascunho:
    aluno = db.get(Aluno, conta.aluno_id)
    competencia = min(_competencia_da_conta(conta), hoje())
    nome = aluno.nome if aluno else "Aluno"
    doc = aluno.cpf if aluno else None
    r = Rascunho(
        chave=regras.chave_recebimento(conta.id), origem=origem, tomador_tipo="aluno", tomador_nome=nome,
        tomador_documento=doc, tomador_email=aluno.email if aluno else None, valor=Decimal(conta.valor),
        competencia=competencia, aluno_id=conta.aluno_id, conta_receber_id=conta.id,
        tomador_endereco=_endereco_aluno(db, conta.aluno_id),
        discriminacao=regras.renderizar_discriminacao(cfg.discriminacao_modelo, _variaveis(
            db, nome=nome, doc=doc, descricao=conta.descricao, competencia=competencia, valor=conta.valor, conta=conta)),
    )
    if conta.status != StatusReceber.PAGO:
        r.problemas.append({"nivel": "erro", "mensagem": "Recebimento ainda não está pago.",
                            "acao": "Dê baixa no recebimento antes de emitir a nota.", "link": "/financeiro/receber"})
    return r


def rascunho_avulso(db: Session, cfg: ConfigNfse, dados) -> Rascunho:
    t = dados.tomador
    aluno = None
    doc, nome, email_t, endereco = t.documento, t.nome, t.email, t.endereco
    if t.tipo == "aluno":
        if not t.aluno_id or not (aluno := db.get(Aluno, t.aluno_id)):
            raise erro(422, "Escolha o aluno (tomador) da nota.")
        doc = doc or aluno.cpf
        nome = nome or aluno.nome
        email_t = email_t or aluno.email
        endereco = endereco or _endereco_aluno(db, aluno.id)
    if not nome:
        raise erro(422, "Informe o nome do tomador.")
    competencia = dados.competencia or hoje()
    conta = db.get(ContaReceber, dados.conta_receber_id) if dados.conta_receber_id else None
    discriminacao = regras.limpar_texto(dados.discriminacao) if dados.discriminacao else regras.renderizar_discriminacao(
        cfg.discriminacao_modelo, _variaveis(db, nome=nome, doc=doc, descricao=dados.descricao, competencia=competencia,
                                             valor=dados.valor, conta=conta))
    return Rascunho(
        chave=regras.chave_recebimento(conta.id) if conta else f"avulsa:{uuid.uuid4().hex}", origem="avulsa",
        tomador_tipo=t.tipo, tomador_nome=nome, tomador_documento=doc, tomador_email=email_t,
        tomador_endereco=endereco, valor=Decimal(dados.valor), competencia=competencia, discriminacao=discriminacao,
        aluno_id=aluno.id if aluno else None, conta_receber_id=conta.id if conta else None,
    )


# ================================================================================================ fila
def evento(db: Session, nota: NotaFiscal, tipo: str, descricao: str, usuario_id: int | None = None) -> None:
    db.add(NotaEvento(nota_id=nota.id, tipo=tipo, descricao=descricao[:500], usuario_id=usuario_id, criado_em=agora()))


def nota_do_recebimento(db: Session, conta_receber_id: int) -> NotaFiscal | None:
    return db.scalar(select(NotaFiscal).where(NotaFiscal.chave_emissao == regras.chave_recebimento(conta_receber_id)))


def _reservar_numero(db: Session) -> tuple[ConfigNfse, int]:
    cfg = db.scalar(select(ConfigNfse).where(ConfigNfse.id == 1).with_for_update())
    if cfg is None:
        cfg = obter_config(db)
    numero = cfg.proximo_numero
    cfg.proximo_numero = numero + 1
    return cfg, numero


def enfileirar(db: Session, r: Rascunho, *, lote: str | None = None, usuario_id: int | None = None) -> tuple[NotaFiscal, bool]:
    """Cria a nota na fila. Idempotente: se a chave já existe, devolve (nota existente, False). Não faz commit."""
    existente = db.scalar(select(NotaFiscal).where(NotaFiscal.chave_emissao == r.chave))
    if existente:
        return existente, False
    cfg, numero = _reservar_numero(db)
    calc = regras.calcular_iss(r.valor, Decimal(cfg.aliquota_iss or 0) if cfg.regime != "mei" else Decimal("0"),
                               regime=cfg.regime, retido=cfg.iss_retido)
    nota = NotaFiscal(
        chave_emissao=r.chave, origem=OrigemNota(r.origem), lote=lote, conta_receber_id=r.conta_receber_id,
        aluno_id=r.aluno_id, criado_por_id=usuario_id, provedor=cfg.provedor, modo=cfg.modo,
        status=StatusNota.pendente, serie=cfg.serie, numero_dps=numero,
        id_dps=regras.id_dps(municipio=cfg.codigo_municipio or "0", cnpj=cfg.cnpj or "0", serie=cfg.serie, numero=numero)
        if cfg.provedor == Provedor.nacional else None,
        tomador_tipo=r.tomador_tipo, tomador_documento=so_digitos(r.tomador_documento) or None,
        tomador_nome=r.tomador_nome[:150], tomador_email=r.tomador_email, tomador_endereco=r.tomador_endereco,
        competencia=r.competencia, discriminacao=r.discriminacao, item_lista_servico=cfg.item_lista_servico,
        codigo_tributacao_nacional=cfg.codigo_tributacao_nacional, codigo_servico_municipal=cfg.codigo_servico_municipal,
        valor_servico=regras.centavos(r.valor), deducoes=Decimal("0"), aliquota=calc.aliquota, valor_iss=calc.valor_iss,
        iss_retido=cfg.iss_retido, regime=cfg.regime, proxima_tentativa_em=agora(),
    )
    try:
        with db.begin_nested():
            db.add(nota)
            db.flush()
    except IntegrityError:  # corrida: outra requisição/worker criou a mesma chave
        existente = db.scalar(select(NotaFiscal).where(NotaFiscal.chave_emissao == r.chave))
        if existente:
            return existente, False
        raise
    evento(db, nota, "fila", f"Entrou na fila ({r.origem}). DPS/RPS {nota.serie}-{nota.numero_dps}.", usuario_id)
    return nota, True


def enfileirar_recebimento(db: Session, conta_receber_id: int, *, origem: str = "recebimento",
                           usuario_id: int | None = None) -> NotaFiscal:
    conta = db.get(ContaReceber, conta_receber_id)
    if conta is None:
        raise erro(404, "Recebimento não encontrado.")
    r = rascunho_de_recebimento(db, obter_config(db), conta, origem)
    if r.problemas:
        raise erro(409, r.problemas[0]["mensagem"])
    return enfileirar(db, r, usuario_id=usuario_id)[0]


def _aplicar(db: Session, nota: NotaFiscal, res, cfg: ConfigNfse) -> None:
    if res.xml_enviado:
        nota.xml_enviado = res.xml_enviado
    if res.xml_retorno:
        nota.xml_retorno = res.xml_retorno
    nota.alertas = [a.como_dict() for a in res.alertas] or nota.alertas
    if res.id_dps:
        nota.id_dps = res.id_dps
    nota.falha_comunicacao = False
    nota.proxima_tentativa_em = None
    if res.situacao in ("emitida", "validada"):
        nota.status = StatusNota(res.situacao)
        nota.numero_nfse = res.numero_nfse
        nota.codigo_verificacao = res.codigo_verificacao
        nota.chave_acesso = res.chave_acesso
        nota.link_oficial = res.link_oficial
        nota.emitida_em = res.emitida_em or agora()
        nota.erros = []
        if res.situacao == "emitida":
            evento(db, nota, "emitida", f"NFS-e nº {res.numero_nfse or '?'} emitida"
                   + (" (TESTE, sem valor fiscal)." if nota.modo != Modo.producao else "."))
        else:
            evento(db, nota, "validada", "Homologação: a Prefeitura validou a nota (nenhuma nota foi gerada).")
    else:
        nota.status = StatusNota.rejeitada
        nota.erros = [e.como_dict() for e in res.erros]
        evento(db, nota, "rejeitada", "Recusada: " + "; ".join(e.mensagem for e in res.erros[:3]))


def _pos_emissao(db: Session, nota: NotaFiscal, cfg: ConfigNfse, prov) -> None:
    """PDF (DANFSe oficial quando houver, senão o espelho) e e-mail ao aluno. Falhas aqui não desfazem a emissão."""
    try:
        oficial = prov.danfse(dados_da_nota(nota, cfg)) if prov else None
    except Exception:  # noqa: BLE001 - DANFSe é opcional; o espelho cobre
        log.warning("DANFSe indisponível para a nota %s", nota.id)
        oficial = None
    try:
        conteudo = oficial or pdf.espelho(nota, cfg, _nome_estudio(db))
        nota.pdf_path = storage.salvar("nfse", "nota.pdf", conteudo, subpasta=f"{nota.competencia:%Y-%m}",
                                       nome_base=f"nfse_{nota.id}", substituir=True)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao gerar o PDF da nota %s", nota.id)
    if cfg.enviar_email_aluno and nota.tomador_email and nota.status == StatusNota.emitida:
        enviar_email(db, nota, cfg)


def processar(db: Session, nota: NotaFiscal) -> NotaFiscal:
    """Envia UMA nota pendente. Faz commit (antes de falar com o provedor e depois)."""
    if nota.status != StatusNota.pendente:
        return nota
    cfg = obter_config(db)
    if nota.modo == Modo.producao and settings.ambiente != "prod":
        nota.status = StatusNota.rejeitada
        nota.erros = [ErroNota("Emissão real bloqueada: este servidor não é o de produção.",
                               "Mude para o modo Teste em Configurações › NFS-e e emita de novo.").como_dict()]
        evento(db, nota, "bloqueada", "Emissão real bloqueada fora de AMBIENTE=prod.")
        db.commit()
        return nota
    try:
        prov = provedor_para(cfg, modo=str(nota.modo), provedor=str(nota.provedor))
    except ErroConfiguracao as e:
        nota.status = StatusNota.rejeitada
        nota.erros = [ErroNota(str(e), "Abra Configurações › NFS-e.", campo="certificado").como_dict()]
        evento(db, nota, "rejeitada", str(e))
        db.commit()
        return nota
    nota.status = StatusNota.processando
    nota.tentativas += 1
    db.commit()
    dados = dados_da_nota(nota, cfg)
    try:
        res = None
        if nota.falha_comunicacao:  # a anterior pode ter chegado: consulta antes de reenviar (nada de nota em dobro)
            res = prov.consultar(dados)
            if res:
                evento(db, nota, "consulta", "Após falha de comunicação, a nota foi encontrada no provedor.")
        if res is None:
            evento(db, nota, "envio", f"Enviada ao provedor (tentativa {nota.tentativas}).")
            res = prov.emitir(dados)
    except FalhaComunicacao as e:
        nota.falha_comunicacao = True
        if nota.tentativas >= regras.MAX_TENTATIVAS:
            nota.status = StatusNota.falha
            nota.proxima_tentativa_em = None
            nota.erros = [ErroNota("A prefeitura/Sefin não respondeu depois de várias tentativas.",
                                   "Confira se o serviço está no ar e clique em 'Tentar de novo'.",
                                   codigo="COMUNICACAO", tecnico=str(e)[:300]).como_dict()]
            evento(db, nota, "falha", "Desistiu após falhas de comunicação seguidas.")
        else:
            nota.status = StatusNota.pendente
            nota.proxima_tentativa_em = regras.proxima_tentativa(nota.tentativas, agora())
            nota.erros = [ErroNota("Sem resposta do provedor; vamos tentar de novo sozinhos.",
                                   "Nenhuma ação: antes de reenviar, o MayaFit consulta se a nota já existe.",
                                   codigo="COMUNICACAO", tecnico=str(e)[:300], nivel="aviso").como_dict()]
            evento(db, nota, "falha_comunicacao",
                   f"Falha de comunicação; nova tentativa às {regras.agora_local(nota.proxima_tentativa_em):%H:%M}.")
        db.commit()
        return nota
    except Exception as e:  # noqa: BLE001 - erro inesperado não pode deixar a nota presa em "processando"
        log.exception("Erro inesperado ao emitir a nota %s", nota.id)
        nota.status = StatusNota.rejeitada
        nota.erros = [ErroNota("Erro inesperado ao montar ou enviar a nota.",
                               "Tente de novo; se repetir, avise o suporte MayaCorp.", tecnico=str(e)[:300]).como_dict()]
        evento(db, nota, "erro", "Erro inesperado: " + str(e)[:200])
        db.commit()
        return nota
    _aplicar(db, nota, res, cfg)
    db.commit()
    if nota.status in (StatusNota.emitida, StatusNota.validada):
        _pos_emissao(db, nota, cfg, prov)
        db.commit()
    return nota


def processar_fila(db: Session, limite: int = 20, lote: str | None = None) -> int:
    """Processa as pendentes vencidas (worker) ou as de um lote (na hora, pela tela). Devolve quantas processou."""
    consulta = select(NotaFiscal).where(NotaFiscal.status == StatusNota.pendente)
    if lote:
        consulta = consulta.where(NotaFiscal.lote == lote)
    else:
        consulta = consulta.where(or_(NotaFiscal.proxima_tentativa_em.is_(None), NotaFiscal.proxima_tentativa_em <= agora()))
    feitas = 0
    for nota in db.scalars(consulta.order_by(NotaFiscal.id).limit(limite)).all():
        processar(db, nota)
        feitas += 1
    return feitas


def destravar_processando(db: Session, minutos: int = 15) -> int:
    """Nota em "processando" há muito tempo (worker caiu no meio): volta para a fila COM consulta antes."""
    limite = agora() - timedelta(minutes=minutos)
    presas = db.scalars(select(NotaFiscal).where(NotaFiscal.status == StatusNota.processando,
                                                 NotaFiscal.atualizado_em < limite)).all()
    for n in presas:
        n.status = StatusNota.pendente
        n.falha_comunicacao = True
        n.proxima_tentativa_em = agora()
        evento(db, n, "destravada", "Retomada pela fila (o envio anterior foi interrompido).")
    db.commit()
    return len(presas)


def emitir_automaticas(db: Session, limite: int = 50) -> int:
    """Recebimentos PAGOS desde que a emissão automática foi ligada e ainda sem nota viva entram na fila."""
    cfg = db.get(ConfigNfse, 1)
    if not cfg or not cfg.ativo or not cfg.emissao_automatica:
        return 0
    if pendencias_bloqueantes(cfg):
        return 0
    desde = cfg.automatica_desde or hoje()
    ja = select(NotaFiscal.conta_receber_id).where(NotaFiscal.conta_receber_id.is_not(None),
                                                   NotaFiscal.status.in_(VIVAS))
    contas = db.scalars(
        select(ContaReceber).where(ContaReceber.status == StatusReceber.PAGO, ContaReceber.pagamento >= desde,
                                   ContaReceber.id.not_in(ja)).order_by(ContaReceber.pagamento, ContaReceber.id).limit(limite)
    ).all()
    n = 0
    for conta in contas:
        r = rascunho_de_recebimento(db, cfg, conta, "automatica")
        if r.problemas or not regras.documento_valido(r.tomador_documento):
            continue  # aluno sem CPF válido: fica na lista de pendências do painel
        _, criada = enfileirar(db, r)
        n += int(criada)
    db.commit()
    return n


def pendencias_bloqueantes(cfg: ConfigNfse) -> list[dict[str, Any]]:
    return [p for p in pendencias_config(cfg) if p["nivel"] == "erro"]


# ================================================================================================ ações
def reprocessar(db: Session, nota: NotaFiscal, usuario_id: int | None) -> NotaFiscal:
    if nota.status not in (StatusNota.rejeitada, StatusNota.falha, StatusNota.pendente):
        raise erro(409, "Só notas rejeitadas, com falha ou na fila podem ser reenviadas.")
    cfg = obter_config(db)
    # DPS/RPS recusada não fica registrada no provedor: o reenvio usa o mesmo número (sem buraco na numeração)
    nota.status = StatusNota.pendente
    nota.proxima_tentativa_em = agora()
    nota.modo = cfg.modo
    if nota.tentativas >= regras.MAX_TENTATIVAS:
        nota.tentativas = 0
    evento(db, nota, "reenvio", "Reenvio pedido pela equipe.", usuario_id)
    db.commit()
    return processar(db, nota)


def corrigir(db: Session, nota: NotaFiscal, dados, usuario_id: int | None) -> NotaFiscal:
    if nota.status not in (StatusNota.rejeitada, StatusNota.falha):
        raise erro(409, "Só é possível corrigir notas rejeitadas.")
    mudou = []
    for campo in ("tomador_documento", "tomador_nome", "tomador_email", "discriminacao", "competencia"):
        v = getattr(dados, campo)
        if v is not None and v != getattr(nota, campo):
            setattr(nota, campo, v)
            mudou.append(campo)
    if mudou:
        evento(db, nota, "correcao", "Corrigido: " + ", ".join(mudou), usuario_id)
    return nota


def cancelar(db: Session, nota: NotaFiscal, codigo: str, motivo: str, usuario_id: int | None) -> NotaFiscal:
    if nota.status == StatusNota.cancelada:
        raise erro(409, "Esta nota já está cancelada.")
    if nota.status in (StatusNota.pendente, StatusNota.rejeitada, StatusNota.falha):
        # nunca saiu: só descarta e libera a chave
        nota.status = StatusNota.cancelada
        nota.cancelada_em = agora()
        nota.motivo_cancelamento = motivo
        nota.codigo_motivo_cancelamento = codigo
        nota.chave_emissao = regras.chave_liberada(nota.chave_emissao, nota.id)
        evento(db, nota, "descartada", f"Descartada antes de virar nota: {motivo}", usuario_id)
        db.commit()
        return nota
    if nota.status not in (StatusNota.emitida, StatusNota.validada):
        raise erro(409, "Aguarde o fim do envio para cancelar.")
    cfg = obter_config(db)
    if nota.status == StatusNota.emitida and nota.modo != Modo.simulado:
        try:
            prov = provedor_para(cfg, modo=str(nota.modo), provedor=str(nota.provedor))
            res = prov.cancelar(dados_da_nota(nota, cfg), codigo=codigo, motivo=motivo)
        except ErroConfiguracao as e:
            raise erro(409, str(e)) from None
        except FalhaComunicacao:
            raise erro(503, "O provedor não respondeu. Tente cancelar de novo em alguns minutos.") from None
        if not res.sucesso:
            nota.erros = [e.como_dict() for e in res.erros]
            evento(db, nota, "cancelamento_recusado",
                   "Cancelamento recusado: " + "; ".join(e.mensagem for e in res.erros[:2]), usuario_id)
            db.commit()
            raise HTTPException(409, {"mensagem": "O provedor recusou o cancelamento.", "erros": nota.erros})
    elif nota.status == StatusNota.emitida:  # simulado: exercita o simulador também
        prov = provedor_para(cfg, modo="simulado", provedor=str(nota.provedor))
        prov.cancelar(dados_da_nota(nota, cfg), codigo=codigo, motivo=motivo)
    nota.status = StatusNota.cancelada
    nota.cancelada_em = agora()
    nota.motivo_cancelamento = motivo
    nota.codigo_motivo_cancelamento = codigo
    nota.chave_emissao = regras.chave_liberada(nota.chave_emissao, nota.id)
    evento(db, nota, "cancelada", f"Cancelada: {motivo}", usuario_id)
    db.commit()
    return nota


def enviar_email(db: Session, nota: NotaFiscal, cfg: ConfigNfse | None = None) -> bool:
    cfg = cfg or obter_config(db)
    if not nota.tomador_email:
        raise erro(422, "O tomador não tem e-mail cadastrado.")
    estudio = _nome_estudio(db)
    anexos = []
    if nota.pdf_path:
        try:
            anexos.append((f"nfse-{nota.numero_nfse or nota.numero_dps}.pdf", storage.ler(nota.pdf_path), "application/pdf"))
        except (FileNotFoundError, storage.ArquivoInvalido):
            pass
    teste = "" if nota.modo == Modo.producao else "\n\n(Atenção: esta nota foi emitida em ambiente de TESTE e não tem valor fiscal.)"
    corpo = (
        f"Olá, {nota.tomador_nome.split()[0]}!\n\n"
        f"Segue a nota fiscal de serviço nº {nota.numero_nfse or '-'} referente a {regras.competencia_texto(nota.competencia)}, "
        f"no valor de {regras.brl(nota.valor_servico)}.\n"
        + (f"\nConsulte a nota oficial: {nota.link_oficial}\n" if nota.link_oficial else "")
        + f"{teste}\n\nObrigado,\n{estudio}"
    )
    ok = email_core.enviar([nota.tomador_email], f"Nota fiscal de serviço - {estudio}", corpo, db=db, anexos=anexos)
    if ok:
        nota.email_enviado_em = agora()
        evento(db, nota, "email", f"E-mail enviado para {nota.tomador_email}.")
    else:
        evento(db, nota, "email_falhou", "Não foi possível enviar o e-mail (confira Configurações › E-mail).")
    return ok


def pdf_da_nota(db: Session, nota: NotaFiscal) -> bytes:
    if nota.pdf_path:
        try:
            return storage.ler(nota.pdf_path)
        except (FileNotFoundError, storage.ArquivoInvalido):
            pass
    return pdf.espelho(nota, obter_config(db), _nome_estudio(db))


# ================================================================================================ consultas
def erro_principal(nota: NotaFiscal) -> str | None:
    if nota.erros:
        return nota.erros[0].get("mensagem")
    return None


def resumo(n: NotaFiscal) -> dict[str, Any]:
    return {
        "id": n.id, "status": str(n.status), "origem": str(n.origem), "provedor": str(n.provedor), "modo": str(n.modo),
        "serie": n.serie, "numero_dps": n.numero_dps, "numero_nfse": n.numero_nfse, "tomador_nome": n.tomador_nome,
        "tomador_documento": n.tomador_documento, "competencia": n.competencia, "valor_servico": n.valor_servico,
        "valor_iss": n.valor_iss, "emitida_em": n.emitida_em, "criado_em": n.criado_em,
        "conta_receber_id": n.conta_receber_id, "aluno_id": n.aluno_id, "tentativas": n.tentativas,
        "erro_principal": erro_principal(n), "tem_pdf": n.status in (StatusNota.emitida, StatusNota.validada),
        "link_oficial": n.link_oficial,
    }


def detalhe(db: Session, n: NotaFiscal) -> dict[str, Any]:
    eventos = db.scalars(select(NotaEvento).where(NotaEvento.nota_id == n.id).order_by(NotaEvento.id)).all()
    return {
        **resumo(n),
        **{c: getattr(n, c) for c in (
            "chave_emissao", "id_dps", "chave_acesso", "codigo_verificacao", "tomador_email", "tomador_tipo",
            "discriminacao", "item_lista_servico", "codigo_tributacao_nacional", "codigo_servico_municipal", "aliquota",
            "deducoes", "iss_retido", "regime", "cancelada_em", "motivo_cancelamento", "email_enviado_em",
            "proxima_tentativa_em")},
        "erros": n.erros or [], "alertas": n.alertas or [], "tem_xml_enviado": bool(n.xml_enviado),
        "tem_xml_retorno": bool(n.xml_retorno), "eventos": eventos,
        "pode_cancelar": n.status in (StatusNota.emitida, StatusNota.validada, StatusNota.pendente,
                                      StatusNota.rejeitada, StatusNota.falha),
        "pode_reprocessar": n.status in (StatusNota.rejeitada, StatusNota.falha, StatusNota.pendente),
    }


def listar(db: Session, *, status: str | None, q: str | None, de: date | None, ate: date | None, origem: str | None,
           pagina: int, por_pagina: int) -> dict[str, Any]:
    base = select(NotaFiscal)
    if q:
        termo = f"%{q.strip()}%"
        dig = so_digitos(q)
        conds = [NotaFiscal.tomador_nome.ilike(termo), NotaFiscal.numero_nfse.ilike(termo)]
        if dig:
            conds.append(NotaFiscal.tomador_documento.like(f"%{dig}%"))
        base = base.where(or_(*conds))
    if de:
        base = base.where(NotaFiscal.competencia >= de)
    if ate:
        base = base.where(NotaFiscal.competencia <= ate)
    if origem:
        base = base.where(NotaFiscal.origem == origem)
    contagens = _contagens(db, base)
    if status == "atencao":
        base = base.where(NotaFiscal.status.in_([StatusNota.rejeitada, StatusNota.falha]))
    elif status:
        base = base.where(NotaFiscal.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    itens = db.scalars(base.order_by(NotaFiscal.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    return {"itens": [resumo(n) for n in itens], "total": total or 0, "pagina": pagina, "por_pagina": por_pagina,
            "contagens": contagens}


def _contagens(db: Session, base) -> dict[str, int]:
    sub = base.subquery()
    linhas = db.execute(select(sub.c.status, func.count()).group_by(sub.c.status)).all()
    return {str(s.value if hasattr(s, "value") else s): c for s, c in linhas}


def recebimentos(db: Session, *, de: date | None, ate: date | None, situacao: str, q: str | None) -> list[dict[str, Any]]:
    """Recebimentos PAGOS no período, com a situação fiscal de cada um (sem nota / emitida / rejeitada...)."""
    de = de or hoje().replace(day=1)
    ate = ate or hoje()
    consulta = (select(ContaReceber, Aluno).join(Aluno, Aluno.id == ContaReceber.aluno_id)
                .where(ContaReceber.status == StatusReceber.PAGO, ContaReceber.pagamento >= de,
                       ContaReceber.pagamento <= ate))
    if q:
        consulta = consulta.where(Aluno.nome.ilike(f"%{q.strip()}%"))
    linhas = db.execute(consulta.order_by(ContaReceber.pagamento.desc(), ContaReceber.id.desc()).limit(500)).all()
    notas = {n.conta_receber_id: n for n in db.scalars(select(NotaFiscal).where(
        NotaFiscal.conta_receber_id.in_([c.id for c, _ in linhas]), NotaFiscal.status.in_(VIVAS)))}
    saida = []
    for conta, aluno in linhas:
        n = notas.get(conta.id)
        problema = None
        if not aluno.cpf:
            problema = "Aluno sem CPF: cadastre o CPF para emitir."
        elif not regras.documento_valido(aluno.cpf):
            problema = "CPF do aluno inválido."
        item = {
            "id": conta.id, "aluno_id": aluno.id, "aluno_nome": aluno.nome,
            "aluno_cpf": regras.formatar_documento(aluno.cpf) if aluno.cpf else None, "aluno_email": aluno.email,
            "descricao": conta.descricao, "valor": conta.valor, "vencimento": conta.vencimento,
            "pagamento": conta.pagamento, "competencia": conta.competencia, "nota_id": n.id if n else None,
            "nota_status": str(n.status) if n else None, "nota_numero": n.numero_nfse if n else None, "problema": problema,
        }
        if situacao == "sem_nota" and n:
            continue
        if situacao == "com_nota" and not n:
            continue
        saida.append(item)
    return saida


def emitir_lote(db: Session, ids: list[int], usuario_id: int | None, processar_agora: int = 10) -> dict[str, Any]:
    cfg = obter_config(db)
    bloqueios = pendencias_bloqueantes(cfg)
    if bloqueios:
        raise erro(409, f"Configuração incompleta: {bloqueios[0]['mensagem']} {bloqueios[0]['acao']}")
    lote = str(uuid.uuid4())
    criadas, existentes, ignoradas, notas = 0, 0, [], []
    for conta_id in dict.fromkeys(ids):
        conta = db.get(ContaReceber, conta_id)
        if conta is None:
            ignoradas.append({"id": conta_id, "motivo": "Recebimento não encontrado."})
            continue
        r = rascunho_de_recebimento(db, cfg, conta)
        if r.problemas:
            ignoradas.append({"id": conta_id, "motivo": r.problemas[0]["mensagem"]})
            continue
        if not regras.documento_valido(r.tomador_documento):
            ignoradas.append({"id": conta_id, "motivo": f"{r.tomador_nome}: CPF ausente ou inválido."})
            continue
        nota, criada = enfileirar(db, r, lote=lote, usuario_id=usuario_id)
        criadas += int(criada)
        existentes += int(not criada)
        notas.append(nota)
    db.commit()
    feitas = processar_fila(db, limite=processar_agora, lote=lote) if criadas <= processar_agora else 0
    for n in notas:
        db.refresh(n)
    return {"lote": lote, "criadas": criadas, "ja_existiam": existentes, "ignoradas": ignoradas,
            "processadas_agora": feitas, "notas": [resumo(n) for n in notas]}


def painel(db: Session) -> dict[str, Any]:
    cfg = obter_config(db)
    h = hoje()
    ini = h.replace(day=1)
    emitidas_mes = select(NotaFiscal).where(NotaFiscal.status == StatusNota.emitida, NotaFiscal.competencia >= ini,
                                            NotaFiscal.competencia <= h)
    sub = emitidas_mes.subquery()
    qtd, valor, iss = db.execute(select(func.count(), func.coalesce(func.sum(sub.c.valor_servico), 0),
                                        func.coalesce(func.sum(sub.c.valor_iss), 0))).one()
    por_status = _contagens(db, select(NotaFiscal))
    sem_nota = db.scalar(select(func.count()).select_from(ContaReceber).where(
        ContaReceber.status == StatusReceber.PAGO, ContaReceber.pagamento >= ini,
        ContaReceber.id.not_in(select(NotaFiscal.conta_receber_id).where(
            NotaFiscal.conta_receber_id.is_not(None), NotaFiscal.status.in_(VIVAS)))))
    valor_sem_nota = db.scalar(select(func.coalesce(func.sum(ContaReceber.valor), 0)).where(
        ContaReceber.status == StatusReceber.PAGO, ContaReceber.pagamento >= ini,
        ContaReceber.id.not_in(select(NotaFiscal.conta_receber_id).where(
            NotaFiscal.conta_receber_id.is_not(None), NotaFiscal.status.in_(VIVAS)))))
    # série dos últimos 6 meses (competência)
    serie = []
    m = ini
    meses = []
    for _ in range(6):
        meses.append(m)
        m = (m - timedelta(days=1)).replace(day=1)
    for mes in reversed(meses):
        fim = (mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        v, i, c = db.execute(select(func.coalesce(func.sum(NotaFiscal.valor_servico), 0),
                                    func.coalesce(func.sum(NotaFiscal.valor_iss), 0), func.count())
                             .where(NotaFiscal.status == StatusNota.emitida, NotaFiscal.competencia >= mes,
                                    NotaFiscal.competencia <= fim)).one()
        serie.append({"mes": f"{mes:%Y-%m}", "valor": Decimal(v), "iss": Decimal(i), "quantidade": c})
    pend = []
    rej = por_status.get("rejeitada", 0) + por_status.get("falha", 0)
    if rej:
        pend.append({"nivel": "erro", "mensagem": f"{rej} nota(s) precisam de atenção (rejeitadas ou com falha).",
                     "acao": "Abrir o raio-x de cada nota e corrigir.", "link": "/nfse?status=atencao"})
    if por_status.get("pendente", 0):
        pend.append({"nivel": "info", "mensagem": f"{por_status['pendente']} nota(s) na fila de envio.",
                     "acao": "Nenhuma ação: o envio é automático.", "link": "/nfse?status=pendente"})
    if sem_nota:
        pend.append({"nivel": "aviso", "mensagem": f"{sem_nota} recebimento(s) pago(s) no mês sem nota ({regras.brl(valor_sem_nota)}).",
                     "acao": "Emitir a partir dos recebimentos.", "link": "/nfse/recebimentos"})
    pend.extend(pendencias_config(cfg))
    regime_das = cfg.regime in ("mei", "simples")
    return {
        "mes": f"{ini:%Y-%m}", "notas_mes": qtd, "valor_mes": Decimal(valor), "iss_estimado_mes": Decimal(iss),
        "iss_no_das": regime_das, "ticket_medio": regras.centavos(Decimal(valor) / qtd) if qtd else Decimal("0"),
        "recebimentos_sem_nota": sem_nota or 0, "valor_sem_nota": Decimal(valor_sem_nota or 0), "por_status": por_status,
        "serie": serie, "pendencias": pend, "certificado": info_certificado(cfg), "modo": str(cfg.modo),
        "provedor": str(cfg.provedor), "ativo": cfg.ativo, "emissao_automatica": cfg.emissao_automatica,
        "configurado": not pendencias_bloqueantes(cfg),
    }
