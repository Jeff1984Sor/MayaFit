"""Admin MayaCorp (/api/admin): início, estúdios (ficha, domínios, status, extras, uso, usuários), planos,
política de indicação, usuário Suporte, modelos de contrato, contratos e IA.

Porte de app/controle/routes_admin.py do MayaJus. Os caminhos ficam os mesmos (`/admin/clientes/...`): o
"cliente" do controle é o estúdio.
"""

import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, or_, select

from app.controle import cobranca, contratos, emails, eventos, indicacao, planos, ponte
from app.controle.models import Cliente, ContratoCliente, Dominio, ModeloContrato, Plano, SessaoControle
from app.core.db import SessionLocal, agora
from app.modules.admin_mayacorp import schemas as sc
from app.modules.admin_mayacorp.servico import (
    STATUS,
    Painel,
    cliente,
    cliente_out,
    d,
    erro,
    plano_out,
    regra_controle,
    slug_de,
    uso_out,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin MayaFit"])


def _validar_indicacao(db, indicado_por_id: int | None, proprio_id: int | None = None) -> None:
    if indicado_por_id is None:
        return
    quem = db.get(Cliente, indicado_por_id)
    if not quem or quem.tipo != "estudio" or indicado_por_id == proprio_id:
        raise HTTPException(400, "Indicação inválida: escolha outro estúdio do MayaFit.")


def _ficha(dados: sc.FichaIn) -> dict:
    campos = dados.model_dump(include=set(sc.FichaIn.model_fields))
    campos["documento"] = re.sub(r"\D", "", campos["documento"] or "") or None
    if campos["documento"] and len(campos["documento"]) not in (11, 14):
        raise HTTPException(400, "CNPJ ou CPF inválido.")
    campos["email_financeiro"] = str(campos["email_financeiro"]).lower() if campos["email_financeiro"] else None
    if campos.get("extras") is None:
        campos.pop("extras", None)
    else:
        campos["extras"] = [x for x in dict.fromkeys(campos["extras"]) if x in planos.EXTRAS]
    return campos



@router.get("/meta", response_model=None)
def meta(ctx: Painel) -> dict:
    return {"status": [{"chave": k, "rotulo": v} for k, v in STATUS.items()],
            "dias_teste_padrao": planos.DIAS_TESTE_PADRAO}


# ================================================================ estúdios
@router.get("/clientes")
def listar_clientes(ctx: Painel, q: str | None = None, status: str | None = None):
    with SessaoControle() as db:
        sel = select(Cliente).where(Cliente.tipo == "estudio")
        if status:
            sel = sel.where(Cliente.status == status)
        if q:
            dig = re.sub(r"\D", "", q)
            conds = [Cliente.nome.ilike(f"%{q}%"), Cliente.slug.ilike(f"%{q}%")]
            if dig:
                conds.append(Cliente.documento.like(f"%{dig}%"))
            sel = sel.where(or_(*conds))
        return [cliente_out(c) for c in db.scalars(sel.order_by(Cliente.nome))]


def criar_estudio(dados: sc.ClienteNovoIn, ctx) -> dict:
    """Estúdio novo: banco próprio, usuário Suporte e o link de primeiro acesso (o dono cria o usuário master)."""
    with SessaoControle() as db:
        _validar_indicacao(db, dados.indicado_por_id)
        if dados.plano_id and not db.get(Plano, dados.plano_id):
            raise HTTPException(400, "Plano não encontrado.")
    ficha = _ficha(dados)
    nome = ficha.pop("nome")
    teste_ate = ficha.pop("teste_ate")
    slug = (dados.slug or slug_de(nome)).strip().lower()
    admin_email = str(dados.admin_email).lower()
    ficha["email_financeiro"] = ficha.get("email_financeiro") or admin_email  # o "1º acesso" usa este e-mail
    dias = dados.dias_teste or None
    try:
        novo, link = ponte.service().provisionar(slug, nome, admin_email=admin_email, admin_nome=dados.admin_nome,
                                                 dias_teste=dias, dominios=dados.dominios, primeiro_acesso=True,
                                                 **ficha)
    except regra_controle() as e:
        erro(e)
    with SessaoControle() as db:
        c = db.get(Cliente, novo.id)
        if teste_ate and not dias:
            c.teste_ate, c.status = teste_ate, "teste"
        plano = c.plano.nome if c.plano else "sem plano"
        teste = f", teste grátis até {c.teste_ate:%d/%m/%Y}" if c.status == "teste" and c.teste_ate else ", sem teste"
        eventos.registrar(db, c.id, "criado", f"Estúdio criado ({plano}, {c.ciclo}{teste})", usuario=ctx.usuario.nome)
        db.commit()
    boas_vindas(admin_email, dados.admin_nome, nome, link, dias)
    _primeira_cobranca(novo.id)
    ctx.auditar("admin.estudio.criar", "controle_cliente", novo.id, descricao=f"{slug}: {nome}")
    ctx.db.commit()
    with SessaoControle() as db:
        return {**cliente_out(db.get(Cliente, novo.id)), "convite": link}


@router.post("/clientes", status_code=201)
def criar_cliente(dados: sc.ClienteNovoIn, ctx: Painel):
    return criar_estudio(dados, ctx)


def _primeira_cobranca(cid: int) -> None:
    """Sem teste grátis, a 1ª mensalidade nasce com o estúdio (com teste, nasce quando o teste acaba)."""
    with SessaoControle() as db:
        try:
            cob = cobranca.primeira_cobranca(db, db.get(Cliente, cid))
            db.commit()
            if cob and cobranca.config(db).mp_token_cifrado and cob.cliente.email_financeiro:
                cobranca.enviar_cobranca(db, cob)
                db.commit()
        except Exception:  # cobrança nunca impede o estúdio de nascer (dá para gerar depois em Cobranças)
            db.rollback()
            log.exception("1ª cobrança do estúdio %s falhou", cid)


def boas_vindas(email: str, pessoa: str, estudio: str, link: str, dias_teste: int | None = None) -> None:
    ola = f"Olá, {pessoa.split()[0]}!" if pessoa.strip() else "Olá!"
    teste = (f"\n\nVocê tem {dias_teste} dias de teste grátis, com todos os recursos do plano. Nada é cobrado "
             "durante o teste.") if dias_teste else ""
    emails.enviar_email(
        [email], f"Bem-vindo ao MayaFit — {estudio}",
        f"{ola}\n\nO {estudio} já tem o seu MayaFit pronto.{teste}\n\nPara começar, crie o seu usuário master (o "
        f"administrador do estúdio) neste link:\n{link}\n\nCom ele você cadastra a equipe, as unidades, os planos e "
        "os alunos. O link vale por 7 dias.\n\nQualquer dúvida, é só responder este e-mail.\n\nEquipe MayaFit")


def _e_suporte(u, slug: str) -> bool:
    # a fundação marca o Suporte na coluna `usuario.suporte`; sem ela, pelo login `suporte.<slug>`
    return bool(getattr(u, "suporte", False)) or (u.login or "").lower() == f"suporte.{slug}"


@router.post("/clientes/{cid}/boas-vindas")
def reenviar_boas_vindas(cid: int, ctx: Painel):
    """Link novo de primeiro acesso (enquanto o dono não criou o usuário master)."""
    from app.core.models import Usuario

    with SessaoControle() as db:
        c = cliente(db, cid)
        est, slug, nome, para, pessoa = ponte.estudio_de(c), c.slug, c.nome, c.email_financeiro, c.responsavel or ""
    with ponte.usando(est), SessionLocal() as s:
        if any(not _e_suporte(u, slug) for u in s.scalars(select(Usuario).where(Usuario.senha_hash.is_not(None)))):
            raise HTTPException(400, "O estúdio já criou o usuário master. Use \"Zerar senha\" na aba Usuários.")
    if not para:
        raise HTTPException(400, "Informe o e-mail do financeiro na ficha para reenviar as boas-vindas.")
    link = ponte.service().link_primeiro_acesso(slug, para)
    boas_vindas(para, pessoa, nome, link)
    with SessaoControle() as db:
        eventos.registrar(db, cid, "acesso", f"Link de primeiro acesso reenviado para {para}", usuario=ctx.usuario.nome)
        db.commit()
    ctx.auditar("admin.estudio.boas_vindas", "controle_cliente", cid, descricao=para)
    ctx.db.commit()
    return {"link": link, "enviado_para": para}


@router.get("/clientes/{cid}")
def ler_cliente(cid: int, ctx: Painel):
    with SessaoControle() as db:
        return cliente_out(cliente(db, cid))


@router.put("/clientes/{cid}")
def alterar_cliente(cid: int, dados: sc.FichaIn, ctx: Painel):
    with SessaoControle() as db:
        c = cliente(db, cid)
        if dados.plano_id and not db.get(Plano, dados.plano_id):
            raise HTTPException(400, "Plano não encontrado.")
        _validar_indicacao(db, dados.indicado_por_id, c.id)
        plano_antes, ciclo_antes = c.plano_id, c.ciclo
        nome_antes = c.plano.nome if c.plano else "sem plano"
        extras_antes = list(c.extras or [])
        for k, v in _ficha(dados).items():
            setattr(c, k, v)
        db.flush()
        db.refresh(c)
        if (c.plano_id, c.ciclo) != (plano_antes, ciclo_antes):
            novo = c.plano.nome if c.plano else "sem plano"
            eventos.registrar(db, c.id, "plano", f"Plano: {nome_antes} ({ciclo_antes}) → {novo} ({c.ciclo})",
                              usuario=ctx.usuario.nome, dados={"de": plano_antes, "para": c.plano_id})
            try:
                cobranca.plano_mudou(db, c)
            except Exception as e:  # noqa: BLE001 — a ficha salva; o débito no cartão é ajustado depois
                log.warning("Assinatura de %s não foi ajustada: %s", c.slug, e)
        if list(c.extras or []) != extras_antes:
            rotulos = ", ".join(planos.EXTRAS.get(x, x) for x in c.extras or []) or "nenhum"
            eventos.registrar(db, c.id, "plano", f"Extras liberados: {rotulos}", usuario=ctx.usuario.nome)
        db.commit()
        ponte.limpar_cache()  # extras liberados valem no próximo clique do estúdio
        ctx.auditar("admin.estudio.alterar", "controle_cliente", c.id, descricao=c.nome)
        ctx.db.commit()
        return cliente_out(c)


def aplicar_status(cid: int, novo: str, ctx, *, teste_ate=None, motivo: str = "") -> dict:
    """Troca o status (com evento na linha do tempo, auditoria e cache limpo)."""
    with SessaoControle() as db:
        c = cliente(db, cid)
        antes = c.status
        if novo == "teste":
            if not (teste_ate or c.teste_ate):
                raise HTTPException(400, "Informe até quando vai o teste.")
            c.teste_ate = teste_ate or c.teste_ate
        c.status = novo
        if antes != novo:
            eventos.mudou_status(db, c.id, antes, novo, usuario=ctx.usuario.nome, motivo=motivo)
        db.commit()
        ponte.limpar_cache()
        ctx.auditar("admin.estudio.status", "controle_cliente", c.id,
                    descricao=f"{c.nome}: {antes} → {novo}" + (f" ({motivo})" if motivo else ""))
        ctx.db.commit()
        return cliente_out(c)


@router.post("/clientes/{cid}/status")
def mudar_status(cid: int, dados: sc.StatusIn, ctx: Painel):
    return aplicar_status(cid, dados.status, ctx, teste_ate=dados.teste_ate)


@router.post("/clientes/{cid}/dominios", status_code=201)
def adicionar_dominio(cid: int, dados: sc.DominioIn, ctx: Painel):
    with SessaoControle() as db:
        c = cliente(db, cid)
        try:
            ponte.service().adicionar_dominio(db, c, dados.host)
        except regra_controle() as e:
            erro(e)
        eventos.registrar(db, c.id, "dominio", f"Endereço adicionado: {dados.host}", usuario=ctx.usuario.nome)
        db.commit()
        db.refresh(c)
        ponte.limpar_cache()
        ctx.auditar("admin.estudio.dominio", "controle_cliente", c.id, descricao=f"+ {dados.host}")
        ctx.db.commit()
        return cliente_out(c)


@router.delete("/clientes/{cid}/dominios/{did}")
def remover_dominio(cid: int, did: int, ctx: Painel):
    with SessaoControle() as db:
        c = cliente(db, cid)
        dom = db.get(Dominio, did)
        if not dom or dom.cliente_id != c.id:
            raise HTTPException(404, "Domínio não encontrado.")
        if dom.host == ponte.dominio_padrao(c.slug):
            raise HTTPException(400, "O endereço padrão do estúdio não pode ser removido.")
        host = dom.host
        db.delete(dom)
        eventos.registrar(db, c.id, "dominio", f"Endereço removido: {host}", usuario=ctx.usuario.nome)
        db.commit()
        db.refresh(c)
        ponte.limpar_cache()
        ctx.auditar("admin.estudio.dominio", "controle_cliente", c.id, descricao=f"- {host}")
        ctx.db.commit()
        return cliente_out(c)


@router.get("/clientes/{cid}/uso")
def uso(cid: int, ctx: Painel):
    """Alunos ativos e usuários com acesso, contra os limites do plano (foto do worker; sem foto, coleta agora)."""
    with SessaoControle() as db:
        return uso_out(cobranca.uso(cliente(db, cid)))


# ================================================================ usuários do estúdio
def _usuario_out(u, slug: str) -> dict:
    return {"id": u.id, "nome": u.nome, "email": u.email, "login": u.login, "ativo": u.ativo,
            "acesso_sistema": u.acesso_sistema, "convite_pendente": u.convite_pendente,
            "perfil": u.perfil_acesso.nome if u.perfil_acesso else None, "administrador": u.administrador,
            "ultimo_acesso": u.ultimo_acesso, "suporte": _e_suporte(u, slug),
            "equipe_mayacorp": _e_suporte(u, slug)}  # nome do MayaJus, usado pelo frontend


def _do_estudio(cid: int):
    with SessaoControle() as db:
        c = cliente(db, cid)
        return ponte.estudio_de(c), c.slug, c.nome


@router.get("/clientes/{cid}/usuarios")
def usuarios_do_cliente(cid: int, ctx: Painel):
    from app.core.models import Usuario

    est, slug, _ = _do_estudio(cid)
    with ponte.usando(est), SessionLocal() as s:
        return [_usuario_out(u, slug) for u in s.scalars(select(Usuario).order_by(Usuario.nome))]


def _login_livre(s, base: str) -> str:
    from app.core.models import Usuario

    base = re.sub(r"[^a-z0-9._-]", "", base.lower())[:50] or "usuario"
    login, n = base, 1
    while s.scalar(select(Usuario.id).where(func.lower(Usuario.login) == login)):
        n += 1
        login = f"{base}{n}"
    return login


def _convidar(nome_estudio: str, nome: str, email: str, link: str, *, zerada: bool = False) -> None:
    if zerada:
        emails.enviar_email([email], "Sua senha do MayaFit foi zerada",
                            f"Olá, {nome}.\n\nA equipe MayaFit zerou a sua senha do MayaFit ({nome_estudio}). Para criar "
                            f"uma nova, acesse:\n{link}\n\nO link só pode ser usado uma vez.")
    else:
        emails.enviar_email([email], f"Convite para o MayaFit — {nome_estudio}",
                            f"Olá, {nome}.\n\nVocê foi convidado(a) para o MayaFit do {nome_estudio}. Para criar sua "
                            f"senha, acesse:\n{link}\n\nO link só pode ser usado uma vez.")


@router.post("/clientes/{cid}/usuarios", status_code=201)
def criar_usuario_do_cliente(cid: int, dados: sc.UsuarioEstudioIn, ctx: Painel):
    from app.core import auth_service, perfis
    from app.core.models import Usuario

    email = str(dados.email).lower()
    est, slug, nome_estudio = _do_estudio(cid)
    with ponte.usando(est), SessionLocal() as s:
        if s.scalar(select(Usuario.id).where(func.lower(Usuario.email) == email)):
            raise HTTPException(409, "Já existe um usuário com este e-mail neste estúdio.")
        if dados.login and s.scalar(select(Usuario.id).where(func.lower(Usuario.login) == dados.login.lower())):
            raise HTTPException(409, "Já existe um usuário com este login neste estúdio.")
        login = dados.login.lower() if dados.login else _login_livre(s, email.split("@")[0])
        perfil = perfis.garantir_padrao(s)[dados.perfil]
        u = Usuario(nome=dados.nome, email=email, login=login, perfil_acesso_id=perfil.id, convite_pendente=True)
        s.add(u)
        s.flush()
        link = auth_service.criar_link_email(s, u, minutos=48 * 60)
        s.commit()
        s.refresh(u)
        out = _usuario_out(u, slug)
    _convidar(nome_estudio, dados.nome, email, link)
    ctx.auditar("admin.usuario.criar", "controle_cliente", cid, descricao=f"{nome_estudio}: {email}")
    ctx.db.commit()
    return {**out, "convite": link}


def _usuario(s, uid: int):
    from app.core.models import Usuario

    u = s.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuário não encontrado.")
    return u


@router.post("/clientes/{cid}/usuarios/{uid}/convite")
def reenviar_convite(cid: int, uid: int, ctx: Painel):
    """Convite novo para quem ainda não criou a senha."""
    from app.core import auth_service

    est, _, nome_estudio = _do_estudio(cid)
    with ponte.usando(est), SessionLocal() as s:
        u = _usuario(s, uid)
        if u.senha_hash and not u.convite_pendente:
            raise HTTPException(400, "Este usuário já criou a senha. Use \"Zerar senha\".")
        link = auth_service.criar_link_email(s, u, minutos=48 * 60)
        s.commit()
        email, nome = u.email, u.nome
    _convidar(nome_estudio, nome, email, link)
    ctx.auditar("admin.usuario.convite", "controle_cliente", cid, descricao=f"{nome_estudio}: {email}")
    ctx.db.commit()
    return {"mensagem": f"Convite reenviado para {email}.", "link": link}


@router.post("/clientes/{cid}/usuarios/{uid}/zerar-senha")
def zerar_senha(cid: int, uid: int, ctx: Painel):
    """Apaga a senha atual (ninguém entra com ela) e envia o link para a pessoa criar uma nova."""
    from app.core import auth_service

    est, _, nome_estudio = _do_estudio(cid)
    with ponte.usando(est), SessionLocal() as s:
        u = _usuario(s, uid)
        u.senha_hash, u.tentativas_falhas, u.bloqueado_ate, u.convite_pendente = None, 0, None, True
        u.token_version = (u.token_version or 0) + 1  # derruba as sessões abertas
        link = auth_service.criar_link_email(s, u)
        s.commit()
        email, nome = u.email, u.nome
    _convidar(nome_estudio, nome, email, link, zerada=True)
    ctx.auditar("admin.usuario.zerar_senha", "controle_cliente", cid, descricao=f"{nome_estudio}: {email}")
    ctx.db.commit()
    return {"mensagem": f"Senha de {nome} zerada. Enviamos o link para {email}.", "link": link}


@router.post("/clientes/{cid}/usuarios/{uid}/ativo")
def ativar_usuario(cid: int, uid: int, dados: sc.AtivoIn, ctx: Painel):
    est, slug, nome_estudio = _do_estudio(cid)
    with ponte.usando(est), SessionLocal() as s:
        u = _usuario(s, uid)
        u.ativo = dados.ativo
        if not dados.ativo:
            u.token_version = (u.token_version or 0) + 1
        s.commit()
        s.refresh(u)
        out = _usuario_out(u, slug)
    ctx.auditar("admin.usuario.ativo", "controle_cliente", cid,
                descricao=f"{nome_estudio}: {out['email']} {'ativado' if dados.ativo else 'desativado'}")
    ctx.db.commit()
    return out


@router.post("/clientes/{cid}/suporte/zerar-senha")
def zerar_senha_suporte(cid: int, ctx: Painel):
    """Volta a senha do usuário Suporte deste estúdio para a senha do Suporte definida no admin (e o desbloqueia)."""
    from app.core.models import Usuario

    with SessaoControle() as db:
        hash_suporte = indicacao.politica(db).senha_suporte_hash
        db.commit()
    if not hash_suporte:
        raise HTTPException(400, "Defina antes a senha do usuário Suporte em Planos e indicação › Usuário Suporte.")
    est, slug, nome_estudio = _do_estudio(cid)
    with ponte.usando(est), SessionLocal() as s:
        u = s.scalar(select(Usuario).where(func.lower(Usuario.login) == f"suporte.{slug}"))
        if not u:
            raise HTTPException(404, "Este estúdio não tem o usuário Suporte.")
        u.senha_hash, u.tentativas_falhas, u.bloqueado_ate = hash_suporte, 0, None
        u.ativo, u.convite_pendente = True, False
        u.token_version = (u.token_version or 0) + 1
        s.commit()
        login = u.login
    ctx.auditar("admin.suporte.zerar_senha", "controle_cliente", cid, descricao=f"{nome_estudio}: {login}")
    ctx.db.commit()
    return {"mensagem": f"A senha do {login} voltou a ser a senha do Suporte definida no admin.", "login": login}


# ================================================================ política de indicação e usuário Suporte
@router.get("/politica-indicacao")
def ler_politica(ctx: Painel):
    with SessaoControle() as db:
        p = indicacao.politica(db)
        db.commit()
        return {"desconto_por_indicacao": d(p.desconto_por_indicacao), "desconto_maximo": d(p.desconto_maximo),
                "teto": d(indicacao.TETO)}


@router.put("/politica-indicacao")
def salvar_politica(dados: sc.PoliticaIn, ctx: Painel):
    with SessaoControle() as db:
        p = indicacao.politica(db)
        p.desconto_por_indicacao, p.desconto_maximo = dados.desconto_por_indicacao, dados.desconto_maximo
        db.commit()
    ctx.auditar("admin.politica_indicacao", "controle_politica", 1,
                descricao=f"{dados.desconto_por_indicacao}% por indicação, máximo {dados.desconto_maximo}%")
    ctx.db.commit()
    return ler_politica(ctx)


@router.get("/suporte")
def ler_suporte(ctx: Painel):
    with SessaoControle() as db:
        p = indicacao.politica(db)
        db.commit()
        return {"senha_definida": bool(p.senha_suporte_hash)}


@router.put("/suporte")
def salvar_suporte(dados: sc.SenhaSuporteIn, ctx: Painel):
    """Senha do usuário Suporte dos estúdios NOVOS (os existentes mudam pelo "Zerar senha do Suporte" na ficha)."""
    from app.core.security import hash_senha, validar_politica_senha

    if problema := validar_politica_senha(dados.senha):
        raise HTTPException(400, problema)
    with SessaoControle() as db:
        indicacao.politica(db).senha_suporte_hash = hash_senha(dados.senha)
        db.commit()
    ctx.auditar("admin.suporte.senha", "controle_politica", 1, descricao="senha do usuário Suporte alterada")
    ctx.db.commit()
    return {"senha_definida": True}


# ================================================================ planos, recursos e extras
@router.get("/extras")
def extras(ctx: Painel):
    return [{"chave": k, "rotulo": v} for k, v in planos.EXTRAS.items()]


@router.get("/recursos")
def recursos(ctx: Painel):
    return [{"chave": k, "rotulo": v} for k, v in planos.RECURSOS.items()]


@router.get("/planos")
def listar_planos(ctx: Painel):
    with SessaoControle() as db:
        planos.garantir_padrao(db)
        return [plano_out(p) for p in db.scalars(select(Plano).order_by(Plano.ordem, Plano.id))]


def _salvar_plano(db, p: Plano, dados: sc.PlanoIn) -> None:
    invalidos = set(dados.recursos) - set(planos.RECURSOS)
    if invalidos:
        raise HTTPException(400, f"Recurso desconhecido: {', '.join(sorted(invalidos))}")
    dup = db.scalar(select(Plano.id).where(func.lower(Plano.nome) == dados.nome.lower(), Plano.id != (p.id or 0)))
    if dup:
        raise HTTPException(409, "Já existe um plano com este nome.")
    for k, v in dados.model_dump().items():
        setattr(p, k, v)
    p.recursos = [r for r in dict.fromkeys(dados.recursos)]


@router.post("/planos", status_code=201)
def criar_plano(dados: sc.PlanoIn, ctx: Painel):
    with SessaoControle() as db:
        p = Plano()
        _salvar_plano(db, p, dados)
        db.add(p)
        db.commit()
        ctx.auditar("admin.plano.criar", "controle_plano", p.id, descricao=p.nome)
        ctx.db.commit()
        return plano_out(p)


@router.put("/planos/{pid}")
def alterar_plano(pid: int, dados: sc.PlanoIn, ctx: Painel):
    with SessaoControle() as db:
        p = db.get(Plano, pid)
        if not p:
            raise HTTPException(404, "Plano não encontrado.")
        _salvar_plano(db, p, dados)
        db.commit()
        ponte.limpar_cache()  # recursos do plano valem no próximo clique dos estúdios
        ctx.auditar("admin.plano.alterar", "controle_plano", p.id, descricao=p.nome)
        ctx.db.commit()
        return plano_out(p)


# ================================================================ modelos de contrato
def _modelo_out(m: ModeloContrato) -> dict:
    return {"id": m.id, "nome": m.nome, "corpo": m.corpo, "ativo": m.ativo, "atualizado_em": m.atualizado_em,
            "variaveis_desconhecidas": contratos.desconhecidas(m.corpo)}


@router.get("/contratos/variaveis")
def variaveis(ctx: Painel):
    return [{"chave": k, "rotulo": v} for k, v in contratos.VARIAVEIS.items()]


@router.get("/modelos-contrato")
def listar_modelos(ctx: Painel):
    with SessaoControle() as db:
        return [_modelo_out(m) for m in db.scalars(select(ModeloContrato).order_by(ModeloContrato.nome))]


@router.post("/modelos-contrato", status_code=201)
def criar_modelo(dados: sc.ModeloIn, ctx: Painel):
    with SessaoControle() as db:
        m = ModeloContrato(**dados.model_dump())
        db.add(m)
        db.commit()
        ctx.auditar("admin.modelo_contrato.criar", "controle_modelo", m.id, descricao=m.nome)
        ctx.db.commit()
        return _modelo_out(m)


@router.put("/modelos-contrato/{mid}")
def alterar_modelo(mid: int, dados: sc.ModeloIn, ctx: Painel):
    with SessaoControle() as db:
        m = db.get(ModeloContrato, mid)
        if not m:
            raise HTTPException(404, "Modelo não encontrado.")
        for k, v in dados.model_dump().items():
            setattr(m, k, v)
        db.commit()
        ctx.auditar("admin.modelo_contrato.alterar", "controle_modelo", m.id, descricao=m.nome)
        ctx.db.commit()
        return _modelo_out(m)


# ================================================================ contratos dos estúdios
def _contrato_out(k: ContratoCliente) -> dict:
    return {"id": k.id, "cliente_id": k.cliente_id, "modelo_id": k.modelo_id, "titulo": k.titulo, "corpo": k.corpo,
            "status": k.status, "enviado_para": k.enviado_para or [], "enviado_em": k.enviado_em,
            "criado_em": k.criado_em}


def _contrato(db, kid: int) -> ContratoCliente:
    k = db.get(ContratoCliente, kid)
    if not k:
        raise HTTPException(404, "Contrato não encontrado.")
    return k


@router.get("/contratos")
def todos_os_contratos(ctx: Painel):
    with SessaoControle() as db:
        q = select(ContratoCliente).order_by(ContratoCliente.id.desc())
        return [{**_contrato_out(k), "cliente_nome": k.cliente.nome} for k in db.scalars(q)]


@router.get("/clientes/{cid}/contratos")
def contratos_do_cliente(cid: int, ctx: Painel):
    with SessaoControle() as db:
        cliente(db, cid)
        q = select(ContratoCliente).where(ContratoCliente.cliente_id == cid).order_by(ContratoCliente.id.desc())
        return [_contrato_out(k) for k in db.scalars(q)]


@router.post("/clientes/{cid}/contratos", status_code=201)
def gerar_contrato(cid: int, dados: sc.GerarContratoIn, ctx: Painel):
    with SessaoControle() as db:
        c = cliente(db, cid)
        m = db.get(ModeloContrato, dados.modelo_id)
        if not m or not m.ativo:
            raise HTTPException(400, "Modelo não encontrado ou inativo.")
        corpo, vazias = contratos.preencher(m.corpo, c)
        k = ContratoCliente(cliente_id=c.id, modelo_id=m.id, titulo=f"{m.nome} — {c.nome}", corpo=corpo)
        db.add(k)
        eventos.registrar(db, c.id, "contrato", f"Contrato gerado: {k.titulo}", usuario=ctx.usuario.nome)
        db.commit()
        ctx.auditar("admin.contrato.gerar", "controle_contrato", k.id, descricao=k.titulo)
        ctx.db.commit()
        return {**_contrato_out(k), "variaveis_vazias": [contratos.VARIAVEIS[v] for v in vazias]}


@router.put("/contratos/{kid}")
def editar_contrato(kid: int, dados: sc.ContratoEdicaoIn, ctx: Painel):
    with SessaoControle() as db:
        k = _contrato(db, kid)
        if k.status != "rascunho":
            raise HTTPException(400, "Contrato já enviado: gere um novo para alterar o texto.")
        k.titulo, k.corpo = dados.titulo, dados.corpo
        db.commit()
        ctx.auditar("admin.contrato.editar", "controle_contrato", k.id, descricao=k.titulo)
        ctx.db.commit()
        return _contrato_out(k)


def _emitente(ctx) -> str:
    from app.core.models import Identidade

    ident = ctx.db.scalar(select(Identidade).limit(1))
    return ident.nome_exibicao if ident else "MayaFit"


@router.get("/contratos/{kid}/pdf")
def contrato_pdf(kid: int, ctx: Painel):
    with SessaoControle() as db:
        k = _contrato(db, kid)
        conteudo = contratos.pdf(k.titulo, k.corpo, _emitente(ctx))
    return Response(conteudo, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="contrato-{kid}.pdf"'})


@router.post("/contratos/{kid}/enviar")
def enviar_contrato(kid: int, dados: sc.EnviarContratoIn, ctx: Painel):
    with SessaoControle() as db:
        k = _contrato(db, kid)
        if k.status == "cancelado":
            raise HTTPException(400, "Contrato cancelado.")
        emitente = _emitente(ctx)
        arquivo = contratos.pdf(k.titulo, k.corpo, emitente)
        para = [str(e).lower() for e in dados.para]
        texto = (dados.mensagem or f"Olá,\n\nSegue em anexo o contrato \"{k.titulo}\" para leitura e assinatura.\n\n"
                 "Qualquer dúvida, é só responder este e-mail.").strip()
        emails.enviar_email(para, k.titulo, f"{texto}\n\n{emitente}",
                            anexos=[(f"contrato-{k.id}.pdf", arquivo, "application/pdf")])
        k.status, k.enviado_para, k.enviado_em = "enviado", para, agora()
        eventos.registrar(db, k.cliente_id, "contrato", f"Contrato enviado para {', '.join(para)}: {k.titulo}",
                          usuario=ctx.usuario.nome)
        db.commit()
        ctx.auditar("admin.contrato.enviar", "controle_contrato", k.id, descricao=f"{k.titulo} → {', '.join(para)}")
        ctx.db.commit()
        return _contrato_out(k)


@router.post("/contratos/{kid}/status")
def status_contrato(kid: int, dados: sc.ContratoStatusIn, ctx: Painel):
    with SessaoControle() as db:
        k = _contrato(db, kid)
        k.status = dados.status
        eventos.registrar(db, k.cliente_id, "contrato", f"Contrato {dados.status}: {k.titulo}",
                          usuario=ctx.usuario.nome)
        db.commit()
        ctx.auditar("admin.contrato.status", "controle_contrato", k.id, descricao=f"{k.titulo}: {dados.status}")
        ctx.db.commit()
        return _contrato_out(k)


# ================================================================ IA (provedor configurado no próprio admin)
SISTEMA_ADMIN = ("Você é o assistente comercial do admin MayaFit, que vende o MayaFit (sistema de gestão para "
                 "estúdios de Pilates, funcional e academias) por assinatura. Escreva em português do Brasil, claro, "
                 "profissional e sem inventar dados. Responda SOMENTE com um objeto JSON válido no formato pedido.")


def _ia(ctx, pedido: str) -> dict:
    from app.core import ia

    try:
        return ia.gerar_json(ia.provedor_ativo(ctx.db), SISTEMA_ADMIN, pedido)
    except ia.IAIndisponivel as e:
        erro(e)


@router.post("/ia/ficha")
def ia_ficha(dados: sc.TextoIAIn, ctx: Painel):
    """Preenche a ficha do estúdio a partir de um texto colado (cartão CNPJ, e-mail, assinatura)."""
    r = _ia(ctx, "Extraia do texto os dados do estúdio cliente. Use null para o que não estiver no texto; nunca "
                 "invente.\nFormato: {\"nome\", \"documento\" (CNPJ ou CPF), \"responsavel\" (pessoa que assina), "
                 "\"email_financeiro\", \"telefone\"}\nTexto:\n" + dados.texto)
    campos = {k: str(v).strip() for k, v in r.items()
              if k in ("nome", "documento", "responsavel", "email_financeiro", "telefone")
              and v not in (None, "", "null")}
    if "documento" in campos:
        dig = re.sub(r"\D", "", campos["documento"])
        if len(dig) in (11, 14):
            campos["documento"] = dig
        else:
            campos.pop("documento")
    if "email_financeiro" in campos and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", campos["email_financeiro"]):
        campos.pop("email_financeiro")
    return {"campos": campos}


@router.post("/ia/contrato")
def ia_contrato(dados: sc.ContratoIAIn, ctx: Painel):
    """Escreve ou melhora o texto do contrato usando só as variáveis que o sistema sabe preencher."""
    if not (dados.instrucao or dados.corpo):
        raise HTTPException(400, "Diga o que a IA deve fazer ou cole o texto atual.")
    lista = "\n".join(f"{{{{{k}}}}} = {v}" for k, v in contratos.VARIAVEIS.items())
    r = _ia(ctx,
            "Escreva (ou melhore, se houver texto atual) um contrato de licença de uso de software por assinatura entre "
            "o MayaFit (contratada) e o estúdio (contratante). Use os dados do estúdio SOMENTE por estas variáveis, "
            f"exatamente como escritas:\n{lista}\nNão crie outras variáveis nem invente valores. Parágrafos separados "
            "por uma linha em branco; cláusulas numeradas; sem markdown.\n"
            f"Pedido: {dados.instrucao or 'revise e deixe mais claro, completo e profissional'}\n"
            f"Texto atual:\n{dados.corpo or '(nenhum)'}\n"
            'Formato: {"corpo": str, "resumo": str (o que mudou, 1-2 frases)}')
    corpo = str(r.get("corpo") or "").strip()
    if len(corpo) < 50:
        raise HTTPException(400, "A IA não devolveu um texto utilizável. Tente de novo com outro pedido.")
    return {"corpo": corpo, "resumo": str(r.get("resumo") or ""),
            "variaveis_desconhecidas": contratos.desconhecidas(corpo)}


@router.post("/ia/mensagem")
def ia_mensagem(dados: sc.MensagemIAIn, ctx: Painel):
    """Texto do e-mail que leva o contrato."""
    with SessaoControle() as db:
        c = cliente(db, dados.cliente_id)
        quem, nome = c.responsavel or "", c.nome
    r = _ia(ctx, f"Escreva um e-mail curto e cordial enviando o contrato \"{dados.titulo}\" para {nome}"
                 f"{f', aos cuidados de {quem}' if quem else ''}, pedindo leitura e assinatura. Sem assinatura no "
                 f"final (ela é adicionada depois). {dados.instrucao or ''}\n"
                 'Formato: {"mensagem": str}')
    mensagem = str(r.get("mensagem") or "").strip()
    if not mensagem:
        raise HTTPException(400, "A IA não devolveu um texto. Tente de novo.")
    return {"mensagem": mensagem}
