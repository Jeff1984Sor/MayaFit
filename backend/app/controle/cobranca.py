"""Cobrança dos estúdios do MayaFit pelo Mercado Pago (porte de app/controle/cobranca.py do MayaJus).

- Mensalidade: todo mês sai uma cobrança por estúdio ativo/suspenso com plano: o plano (com o desconto por
  indicação) + alunos ativos acima do limite × preço do aluno excedente + usuários acima do limite × preço do usuário
  adicional. No ciclo anual, o plano entra só no mês de aniversário do contrato; nos outros meses vão só os
  excedentes, se houver. O uso vem da foto `Cliente.uso` (gravada pelo worker); sem foto, é coletado na hora.
- Teste grátis: nada é cobrado durante o teste. Quando ele acaba, o estúdio passa a "ativo" e a 1ª mensalidade nasce
  (vence em 3 dias). Estúdio criado sem teste já nasce com a 1ª mensalidade.
- Quem paga no cartão (assinatura recorrente) já tem o plano debitado pelo Mercado Pago: a mensalidade dele leva só
  os excedentes. Cada débito da assinatura vira uma cobrança "cartao" paga.
- Avulsa: valor e descrição livres.
- Régua: e-mails nos dias da régua (ex.: 3 dias antes, no dia, 3 e 10 dias depois), um passo de cada vez.
- Atraso: com cobrança vencida há SUSPENDER_APOS_DIAS dias, o estúdio fica "suspenso" (continua entrando, mas é
  avisado). Pagou tudo o que estava vencido → volta a "ativo".
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.controle import eventos, indicacao, ponte
from app.controle.mercadopago import FORMAS, ErroMercadoPago, MercadoPago
from app.controle.models import Cliente, Cobranca, ConfigCobranca, SessaoControle
from app.core.db import agora

log = logging.getLogger(__name__)

COBRAVEIS = ("ativo", "suspenso")  # em teste não paga; inativo não tem acesso
SUSPENDER_APOS_DIAS = 15
DIAS_PARA_PAGAR = 3  # 1ª mensalidade (fim do teste / estúdio sem teste) vence em 3 dias
MARCA = "MayaFit"


class RegraCobranca(Exception):
    pass


# ---------------------------------------------------------------- configuração
def config(db) -> ConfigCobranca:
    cfg = db.scalar(select(ConfigCobranca).limit(1))
    if cfg is None:
        cfg = ConfigCobranca(dia_vencimento=10, gerar_automatico=True, regua=[-3, 0, 3, 10])
        db.add(cfg)
        db.flush()
    return cfg


def token(cfg: ConfigCobranca) -> str | None:
    from app.core.segredos import decifrar_texto

    return decifrar_texto(cfg.mp_token_cifrado) if cfg.mp_token_cifrado else None


def segredo(cfg: ConfigCobranca) -> str | None:
    from app.core.segredos import decifrar_texto

    return decifrar_texto(cfg.mp_segredo_cifrado) if cfg.mp_segredo_cifrado else None


def mp(cfg: ConfigCobranca) -> MercadoPago:
    t = token(cfg)
    if not t:
        raise RegraCobranca("Conecte a conta do Mercado Pago em Cobranças › Mercado Pago antes de gerar links.")
    return MercadoPago(t)


def _publico() -> str | None:
    """Endereço público do admin (onde o Mercado Pago avisa e para onde se volta). Só https serve ao MP."""
    host = ponte.endereco_do_painel()
    return f"https://{host}" if host else None


def url_notificacao() -> str | None:
    base = _publico()
    return f"{base}/api/public/mercadopago" if base else None


def _url_cliente(c: Cliente) -> str | None:
    """Para onde o estúdio volta depois de pagar: o "Meu plano" no próprio endereço dele."""
    dom = c.dominios[0].host if c.dominios else ponte.dominio_padrao(c.slug)
    if dom:
        return f"https://{dom}/minha-conta/plano"
    from app.core.config import settings

    base = settings.frontend_url.rstrip("/")
    return f"{base}/minha-conta/plano" if base.startswith("https://") else None


# ---------------------------------------------------------------- uso e valores (regras puras + leitura da foto)
def calcular_uso(plano, foto: dict | None) -> dict:
    """Regra pura: uso (alunos ativos e usuários com acesso) contra os limites do plano. Limite vazio = ilimitado."""
    foto = foto or {}
    usuarios = int(foto.get("usuarios") or 0)
    alunos = int(foto.get("alunos_ativos") or 0)
    p = plano
    exc_u = max(0, usuarios - p.usuarios) if p and p.usuarios else 0
    exc_a = max(0, alunos - p.alunos_ativos) if p and p.alunos_ativos else 0
    valor = (exc_u * Decimal(p.preco_usuario_adicional) + exc_a * Decimal(p.preco_aluno_excedente)) if p else Decimal(0)
    return {"usuarios": usuarios, "limite_usuarios": p.usuarios if p else None,
            "alunos_ativos": alunos, "limite_alunos": p.alunos_ativos if p else None,
            "aulas_mes": foto.get("aulas_mes"), "em": foto.get("em"),
            "usuarios_excedentes": exc_u, "alunos_excedentes": exc_a,
            "valor_excedente": Decimal(valor).quantize(Decimal("0.01"))}


def foto_de_uso(c: Cliente, *, coletar: bool = True) -> dict:
    """A foto gravada pelo worker; sem foto, coleta agora no banco do estúdio (service.coletar_uso)."""
    if c.uso:
        return dict(c.uso)
    if not coletar:
        return {}
    try:
        return dict(ponte.service().coletar_uso(ponte.estudio_de(c)) or {})
    except Exception:  # banco do estúdio fora do ar não derruba o admin
        log.exception("Não deu para coletar o uso de %s", c.slug)
        return {}


def uso(c: Cliente) -> dict:
    return calcular_uso(c.plano, foto_de_uso(c))


def valor_ciclo(c: Cliente) -> Decimal | None:
    if not c.plano:
        return None
    return c.plano.preco_anual if c.ciclo == "anual" else c.plano.preco_mensal


def valor_do_plano(db, c: Cliente) -> Decimal | None:
    """Mensalidade (ou anuidade) já com o desconto por indicação."""
    _, pct = indicacao.desconto(db, c)
    return indicacao.aplicar(valor_ciclo(c), pct)


def montar_itens(*, plano, ciclo: str, mes_ano: str, incluir_plano: bool, indicados: int, pct: Decimal,
                 uso_calc: dict | None) -> list[dict]:
    """Regra pura da mensalidade: plano − desconto por indicação + alunos excedentes + usuários adicionais."""
    itens: list[dict] = []
    if plano is None:
        return itens
    if incluir_plano:
        bruto = Decimal(plano.preco_anual if ciclo == "anual" else plano.preco_mensal)
        rotulo = "anuidade" if ciclo == "anual" else "mensalidade"
        itens.append({"descricao": f"Plano {plano.nome} ({rotulo} {mes_ano})", "valor": f"{bruto:.2f}"})
        if pct:
            desc = bruto - indicacao.aplicar(bruto, pct)
            itens.append({"descricao": f"Desconto por indicação ({indicados} indicado(s), {pct:g}%)",
                          "valor": f"{-desc:.2f}"})
    if uso_calc:
        if uso_calc["alunos_excedentes"]:
            n = uso_calc["alunos_excedentes"]
            v = n * Decimal(plano.preco_aluno_excedente)
            itens.append({"descricao": f"{n} aluno(s) ativo(s) além do plano ({uso_calc['alunos_ativos']} de "
                                       f"{uso_calc['limite_alunos']})", "valor": f"{v:.2f}"})
        if uso_calc["usuarios_excedentes"]:
            n = uso_calc["usuarios_excedentes"]
            v = n * Decimal(plano.preco_usuario_adicional)
            itens.append({"descricao": f"{n} usuário(s) adicional(is)", "valor": f"{v:.2f}"})
    return itens


def total(itens: list[dict]) -> Decimal:
    return sum((Decimal(i["valor"]) for i in itens), Decimal(0))


def itens_da_mensalidade(db, c: Cliente, ano: int, mes: int, *, primeira: bool = False) -> list[dict]:
    aniversario = (c.inicio_contrato or c.criado_em.date()).month == mes
    incluir = c.forma_pagamento != "cartao" and (c.ciclo == "mensal" or aniversario or primeira)
    n, pct = indicacao.desconto(db, c)
    return montar_itens(plano=c.plano, ciclo=c.ciclo, mes_ano=f"{mes:02d}/{ano}", incluir_plano=incluir,
                        indicados=n, pct=pct, uso_calc=None if primeira else uso(c))


def _vencimento(cfg: ConfigCobranca, ano: int, mes: int, hoje: date | None = None) -> date:
    dia = min(max(cfg.dia_vencimento, 1), 28)
    venc = date(ano, mes, dia)
    hoje = hoje or date.today()
    # gerada depois do dia de vencimento (estúdio ativado no meio do mês): ganha prazo para pagar
    if venc < hoje and (ano, mes) == (hoje.year, hoje.month):
        venc = hoje + timedelta(days=DIAS_PARA_PAGAR)
    return venc


def _ja_tem(db, c: Cliente, comp: str) -> bool:
    return bool(db.scalar(select(Cobranca.id).where(Cobranca.cliente_id == c.id, Cobranca.tipo == "mensalidade",
                                                    Cobranca.competencia == comp)))


# ---------------------------------------------------------------- criar cobranças
def gerar_mensalidade(db, c: Cliente, ano: int, mes: int, hoje: date | None = None) -> Cobranca | None:
    """Idempotente: uma mensalidade por estúdio e mês. None quando não há nada a cobrar (ou ainda em teste)."""
    comp = f"{ano:04d}-{mes:02d}"
    if c.status not in COBRAVEIS or _ja_tem(db, c, comp):
        return None
    itens = itens_da_mensalidade(db, c, ano, mes)
    valor = total(itens)
    if valor <= 0:
        return None
    cob = Cobranca(cliente_id=c.id, tipo="mensalidade", competencia=comp, descricao=f"{MARCA} {mes:02d}/{ano}",
                   itens=itens, valor=valor, vencimento=_vencimento(config(db), ano, mes, hoje), status="pendente",
                   avisos=[])
    db.add(cob)
    db.flush()
    eventos.registrar(db, c.id, "cobranca", f"Mensalidade {mes:02d}/{ano} gerada: {moeda(valor)}")
    return cob


def primeira_cobranca(db, c: Cliente, hoje: date | None = None) -> Cobranca | None:
    """1ª mensalidade (ou anuidade), só fora do teste: vence em 3 dias. As seguintes saem pela rotina do mês."""
    if not c.plano or c.status == "teste":
        return None
    hoje = hoje or date.today()
    venc = hoje + timedelta(days=DIAS_PARA_PAGAR)
    comp = f"{hoje:%Y-%m}"
    if _ja_tem(db, c, comp):
        return None
    itens = itens_da_mensalidade(db, c, hoje.year, hoje.month, primeira=True)
    valor = total(itens)
    if valor <= 0:
        return None
    cob = Cobranca(cliente_id=c.id, tipo="mensalidade", competencia=comp, descricao=f"{MARCA} {hoje:%m/%Y}",
                   itens=itens, valor=valor, vencimento=venc, status="pendente", avisos=[])
    db.add(cob)
    db.flush()
    eventos.registrar(db, c.id, "cobranca", f"1ª mensalidade gerada: {moeda(valor)}, vence em {venc:%d/%m/%Y}")
    return cob


def avulsa(db, c: Cliente, descricao: str, valor: Decimal, vencimento: date) -> Cobranca:
    if valor <= 0:
        raise RegraCobranca("O valor precisa ser maior que zero.")
    cob = Cobranca(cliente_id=c.id, tipo="avulsa", descricao=descricao, valor=valor, vencimento=vencimento,
                   itens=[{"descricao": descricao, "valor": f"{valor:.2f}"}], status="pendente", avisos=[])
    db.add(cob)
    db.flush()
    return cob


def criar_link(db, cob: Cobranca) -> str:
    """Link do Mercado Pago (Pix, cartão ou boleto). Reaproveita o que já existe."""
    if cob.link:
        return cob.link
    c = cob.cliente
    r = mp(config(db)).preferencia(ref=f"cob:{cob.id}", titulo=f"{cob.descricao} — {c.nome}", valor=cob.valor,
                                   email=c.email_financeiro, notificacao=url_notificacao(), voltar=_url_cliente(c))
    cob.mp_preferencia_id = r.get("id")
    cob.link = r.get("init_point")
    return cob.link


def assinar_cartao(db, c: Cliente) -> str:
    """Link para o estúdio cadastrar o cartão: o Mercado Pago passa a debitar a mensalidade todo mês."""
    if not c.plano:
        raise RegraCobranca("Defina o plano do estúdio antes de criar a assinatura.")
    if c.ciclo == "anual":
        raise RegraCobranca("A assinatura no cartão é mensal. No plano anual, use o link de pagamento.")
    if not c.email_financeiro:
        raise RegraCobranca("Informe o e-mail do financeiro na ficha: o Mercado Pago exige o e-mail de quem paga.")
    voltar = _url_cliente(c) or _publico()
    if not voltar:
        raise RegraCobranca("Cadastre o domínio do admin para o Mercado Pago saber para onde voltar.")
    cliente_mp = mp(config(db))
    if c.mp_assinatura_id and c.mp_assinatura_status != "cancelled":
        try:
            cliente_mp.alterar_assinatura(c.mp_assinatura_id, status="cancelled")
        except ErroMercadoPago:
            log.warning("Não deu para cancelar a assinatura antiga %s", c.mp_assinatura_id)
    r = cliente_mp.assinatura(ref=f"cli:{c.id}", titulo=f"{MARCA} — plano {c.plano.nome}", valor=valor_do_plano(db, c),
                              email=c.email_financeiro, voltar=voltar, notificacao=url_notificacao())
    c.mp_assinatura_id = r.get("id")
    c.mp_assinatura_status = r.get("status") or "pending"
    c.forma_pagamento = "cartao"
    return r.get("init_point")


def plano_mudou(db, c: Cliente) -> None:
    """Upgrade/downgrade: a assinatura no cartão passa a debitar o valor novo a partir do próximo mês."""
    if c.forma_pagamento == "cartao" and c.mp_assinatura_id and c.mp_assinatura_status == "authorized":
        mp(config(db)).alterar_assinatura(c.mp_assinatura_id, valor=valor_do_plano(db, c))


def _reativar_se_quitou(db, c: Cliente, hoje: date | None = None) -> None:
    hoje = hoje or date.today()
    if c.status != "suspenso":
        return
    db.flush()
    vencidas = db.scalar(select(Cobranca.id).where(Cobranca.cliente_id == c.id, Cobranca.status == "pendente",
                                                   Cobranca.vencimento < hoje))
    if not vencidas:
        c.status = "ativo"
        eventos.mudou_status(db, c.id, "suspenso", "ativo", motivo="pagamento em dia")
        ponte.limpar_cache()


def dar_baixa(cob: Cobranca, forma: str, pagamento_id: str | None = None, quando: datetime | None = None,
              usuario: str | None = None) -> bool:
    if cob.status == "paga":
        return False
    cob.status = "paga"
    cob.forma_paga = forma
    cob.mp_pagamento_id = pagamento_id or cob.mp_pagamento_id
    cob.pago_em = quando or agora()
    from sqlalchemy.orm import object_session

    db = object_session(cob)
    if db is not None and cob.cliente is not None:
        eventos.registrar(db, cob.cliente_id, "pagamento", f"{cob.descricao} paga ({forma}): {moeda(cob.valor)}",
                          usuario=usuario)
        _reativar_se_quitou(db, cob.cliente)
    return True


# ---------------------------------------------------------------- notificações do Mercado Pago
def processar_notificacao(db, tipo: str, recurso_id: str) -> str:
    cliente_mp = mp(config(db))
    if tipo == "payment":
        p = cliente_mp.pagamento(recurso_id)
        ref = p.get("external_reference") or ""
        if not ref.startswith("cob:") or p.get("status") != "approved":
            return f"pagamento {recurso_id}: {p.get('status')} ({ref or 'sem referência'})"
        cob = db.get(Cobranca, int(ref[4:]))
        if cob is None:
            return f"cobrança {ref} não existe"
        if dar_baixa(cob, FORMAS.get(p.get("payment_type_id"), p.get("payment_type_id") or "Mercado Pago"),
                     str(p.get("id")), _data_mp(p.get("date_approved"))):
            _avisar_pagamento(cob)
        return f"{ref} paga"
    if tipo in ("subscription_preapproval", "preapproval"):
        a = cliente_mp.ler_assinatura(recurso_id)
        c = db.scalar(select(Cliente).where(Cliente.mp_assinatura_id == recurso_id))
        if c:
            c.mp_assinatura_status = a.get("status")
        return f"assinatura {recurso_id}: {a.get('status')}"
    if tipo == "subscription_authorized_payment":
        a = cliente_mp.pagamento_da_assinatura(recurso_id)
        c = db.scalar(select(Cliente).where(Cliente.mp_assinatura_id == a.get("preapproval_id")))
        pag = a.get("payment") or {}
        if not c or pag.get("status") != "approved":
            return f"débito {recurso_id}: {pag.get('status')}"
        quando = _data_mp(a.get("debit_date") or a.get("date_created")) or agora()
        comp = f"{quando:%Y-%m}"
        cob = db.scalar(select(Cobranca).where(Cobranca.cliente_id == c.id, Cobranca.tipo == "cartao",
                                               Cobranca.competencia == comp))
        if cob is None:
            valor = Decimal(str(a.get("transaction_amount") or 0))
            cob = Cobranca(cliente_id=c.id, tipo="cartao", competencia=comp,
                           descricao=f"{MARCA} {quando:%m/%Y} (cartão)",
                           itens=[{"descricao": f"Plano {c.plano.nome if c.plano else ''} — assinatura",
                                   "valor": f"{valor:.2f}"}],
                           valor=valor, vencimento=quando.date(), status="pendente", avisos=[])
            db.add(cob)
            db.flush()
        if dar_baixa(cob, "cartão (assinatura)", str(pag.get("id") or recurso_id), quando):
            _avisar_pagamento(cob)
        return f"débito da assinatura de {c.slug} em {comp}"
    return f"tipo {tipo} ignorado"


def _data_mp(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------- e-mails (pelo SMTP do admin MayaCorp)
def enviar_email(para: list[str], assunto: str, corpo: str) -> None:
    from app.controle import emails

    emails.enviar_email(para, assunto, corpo)


def moeda(v: Decimal) -> str:
    return f"R$ {Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _texto_itens(cob: Cobranca) -> str:
    return "\n".join(f"  • {i['descricao']}: {moeda(Decimal(i['valor']))}" for i in cob.itens or [])


def enviar_cobranca(db, cob: Cobranca, passo: int | None = None) -> list[str]:
    c = cob.cliente
    para = [e for e in [c.email_financeiro] if e]
    if not para:
        raise RegraCobranca(f"{c.nome} não tem e-mail do financeiro na ficha.")
    link = criar_link(db, cob)
    venc = f"{cob.vencimento:%d/%m/%Y}"
    if passo is None or passo < 0:
        assunto = f"{MARCA} — {cob.descricao}: vence em {venc}"
        abertura = f"Segue a cobrança do {MARCA}, com vencimento em {venc}."
    elif passo == 0:
        assunto = f"{MARCA} — {cob.descricao} vence hoje"
        abertura = f"Lembrete: a cobrança do {MARCA} vence hoje."
    else:
        assunto = f"{MARCA} — {cob.descricao} em aberto"
        abertura = (f"Ainda não identificamos o pagamento da cobrança que venceu em {venc}. Se já pagou, "
                    "desconsidere este aviso.")
    corpo = (f"Olá, {c.responsavel or c.nome}.\n\n{abertura}\n\n{_texto_itens(cob)}\n\nTotal: {moeda(cob.valor)}\n\n"
             f"Pague por Pix, cartão ou boleto neste link:\n{link}\n\nQualquer dúvida, é só responder este e-mail.\n\n"
             "Equipe MayaFit")
    enviar_email(para, assunto, corpo)
    return para


def _avisar_pagamento(cob: Cobranca) -> None:
    c = cob.cliente
    if not c.email_financeiro:
        return
    try:
        enviar_email([c.email_financeiro], f"{MARCA} — pagamento recebido ({cob.descricao})",
                     f"Olá, {c.responsavel or c.nome}.\n\nRecebemos o pagamento de {moeda(cob.valor)} "
                     f"({cob.descricao}). Obrigado!\n\nEquipe MayaFit")
    except Exception:
        log.exception("Aviso de pagamento da cobrança %s falhou", cob.id)


# ---------------------------------------------------------------- rotinas diárias (worker, só no modo multi)
def _estudios(db, *status: str):
    return db.scalars(select(Cliente).where(Cliente.tipo == "estudio", Cliente.status.in_(status)))


def encerrar_testes(hoje: date | None = None) -> dict:
    """Teste que acabou: o estúdio passa a "ativo" e a 1ª mensalidade nasce (vence em 3 dias)."""
    hoje = hoje or date.today()
    feitos = {"encerrados": 0, "cobrancas": 0}
    with SessaoControle() as db:
        tem_mp = bool(config(db).mp_token_cifrado)
        db.commit()
        for c in list(_estudios(db, "teste")):
            if not c.teste_ate or c.teste_ate >= hoje:
                continue
            try:
                c.status = "ativo"
                eventos.mudou_status(db, c.id, "teste", "ativo", motivo=f"teste acabou em {c.teste_ate:%d/%m/%Y}")
                cob = primeira_cobranca(db, c, hoje)
                db.commit()
                feitos["encerrados"] += 1
                if cob and tem_mp and c.email_financeiro:
                    enviar_cobranca(db, cob)
                    db.commit()
                    feitos["cobrancas"] += 1
            except Exception:
                db.rollback()
                log.exception("Fim do teste de %s falhou", c.slug)
    if feitos["encerrados"]:
        ponte.limpar_cache()
    return feitos


def suspender_atrasados(hoje: date | None = None) -> list[str]:
    """Cobrança vencida há SUSPENDER_APOS_DIAS dias: estúdio "suspenso" (entra, mas é avisado) + e-mail."""
    hoje = hoje or date.today()
    limite = hoje - timedelta(days=SUSPENDER_APOS_DIAS)
    suspensos: list[str] = []
    with SessaoControle() as db:
        for c in list(_estudios(db, "ativo")):
            atrasada = db.scalar(select(Cobranca).where(Cobranca.cliente_id == c.id, Cobranca.status == "pendente",
                                                        Cobranca.vencimento <= limite)
                                 .order_by(Cobranca.vencimento).limit(1))
            if not atrasada:
                continue
            c.status = "suspenso"
            eventos.mudou_status(db, c.id, "ativo", "suspenso",
                                 motivo=f"{atrasada.descricao} vencida em {atrasada.vencimento:%d/%m/%Y}")
            db.commit()
            suspensos.append(c.slug)
            if c.email_financeiro:
                try:
                    enviar_email([c.email_financeiro], f"{MARCA} — acesso suspenso por falta de pagamento",
                                 f"Olá, {c.responsavel or c.nome}.\n\nA cobrança {atrasada.descricao} "
                                 f"({moeda(atrasada.valor)}) venceu em {atrasada.vencimento:%d/%m/%Y} e ainda está em "
                                 "aberto. O sistema continua funcionando, mas a equipe passa a ver um aviso. Assim que "
                                 "o pagamento for identificado, o aviso some sozinho."
                                 + (f"\n\nPague por Pix, cartão ou boleto neste link:\n{atrasada.link}" if atrasada.link
                                    else "") + "\n\nEquipe MayaFit")
                except Exception:
                    log.exception("Aviso de suspensão de %s falhou", c.slug)
    if suspensos:
        ponte.limpar_cache()
    return suspensos


def rotina_diaria(hoje: date | None = None) -> dict:
    """Gera as mensalidades do mês (se automático) e manda os e-mails da régua."""
    hoje = hoje or date.today()
    feitos = {"geradas": 0, "avisos": 0}
    with SessaoControle() as db:
        cfg = config(db)
        db.commit()
        if not cfg.mp_token_cifrado:
            return feitos
        if cfg.gerar_automatico and hoje.day >= 1:
            for c in list(_estudios(db, *COBRAVEIS)):
                try:
                    cob = gerar_mensalidade(db, c, hoje.year, hoje.month, hoje)
                    db.commit()
                    feitos["geradas"] += bool(cob)
                except Exception:
                    db.rollback()
                    log.exception("Mensalidade de %s falhou", c.slug)
        regua = sorted(set(cfg.regua or []))
        pendentes = list(db.scalars(select(Cobranca).where(Cobranca.status == "pendente", Cobranca.tipo != "cartao")))
        for cob in pendentes:
            devidos = [p for p in regua if hoje >= cob.vencimento + timedelta(days=p) and p not in (cob.avisos or [])]
            if not devidos:
                continue
            try:
                enviar_cobranca(db, cob, max(devidos))  # só o passo mais recente: nunca vários e-mails de uma vez
                cob.avisos = sorted({*(cob.avisos or []), *devidos})
                db.commit()
                feitos["avisos"] += 1
            except Exception:
                db.rollback()
                log.exception("Aviso da cobrança %s falhou", cob.id)
    return feitos


def atualizar_fotos_de_uso() -> int:
    """Grava em `Cliente.uso` a foto de uso de cada estúdio (o admin lista sem abrir o banco de cada um)."""
    n = 0
    with SessaoControle() as db:
        for c in list(_estudios(db, "teste", "ativo", "suspenso")):
            try:
                foto = dict(ponte.service().coletar_uso(ponte.estudio_de(c)) or {})
            except Exception:
                log.exception("Uso de %s não foi coletado", c.slug)
                continue
            foto.setdefault("em", agora().isoformat())
            c.uso = foto
            db.commit()
            n += 1
    return n
