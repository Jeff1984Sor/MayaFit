"""Regras do banco de controle: achar o estúdio (por slug, domínio ou login), o catálogo de logins, a criação do banco
de um estúdio novo (com o usuário Suporte e o link de primeiro acesso) e a foto de uso. Portado do MayaJus
(app/controle/service.py). Usado pela API, pelo worker, pelo terminal (app.controle.cli) e pelo Admin MayaFit.

API estável (outros módulos chamam): por_slug, por_host, por_login, ativos, limpar_cache, normalizar_host, RegraControle,
SLUG, ATIVOS, registrar, adicionar_dominio, dominio_padrao, nome_do_banco, criar_banco, migrar, migrar_controle,
migrar_todos, provisionar, link_primeiro_acesso, estudio_mayacorp, endereco_do_painel, zerar_senha_suporte,
definir_status, coletar_uso, gravar_uso_todos, registrar_principal_se_faltar, sincronizar_usuario, sincronizar_todos,
recursos_do, info, host_conhecido.
"""

import logging
import re
import time
import unicodedata
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select, text

from app.controle.models import Cliente, Dominio, Login, PoliticaComercial, SessaoControle
from app.core import tenancy
from app.core.tenancy import Estudio

log = logging.getLogger(__name__)

SLUG = re.compile(r"^[a-z][a-z0-9-]{1,38}$")
ATIVOS = ("teste", "ativo", "suspenso")  # suspenso continua entrando (a cobrança só avisa); inativo não entra
STATUS = ("teste", "ativo", "suspenso", "inativo")
_LOGIN = re.compile(r"^[a-z0-9._-]{3,60}$")
_cache: dict[tuple[str, str], tuple[float, object]] = {}
_TTL = 60


class RegraControle(ValueError):
    """Regra do controle violada; a mensagem já está pronta para o usuário."""


def _esc(c: Cliente | None) -> Estudio | None:
    return Estudio(slug=c.slug, banco=c.banco, mayacorp=c.tipo == "mayacorp") if c and c.status in ATIVOS else None


def _memo(tipo: str, chave: str, buscar):
    agora = time.monotonic()
    hit = _cache.get((tipo, chave))
    if hit and agora - hit[0] < _TTL:
        return hit[1]
    valor = buscar()
    _cache[(tipo, chave)] = (agora, valor)
    return valor


def limpar_cache() -> None:
    _cache.clear()


def normalizar_host(host: str) -> str:
    return (host or "").split(":")[0].strip().lower().rstrip(".")


# ---------------------------------------------------------------- achar o estúdio
def por_slug(slug: str) -> Estudio | None:
    """Estúdio que pode entrar (teste/ativo/suspenso); None se não existe ou está inativo."""
    def buscar():
        with SessaoControle() as db:
            return _esc(db.scalar(select(Cliente).where(Cliente.slug == slug)))
    return _memo("slug", slug, buscar)


def por_host(host: str) -> Estudio | None:
    host = normalizar_host(host)

    def buscar():
        with SessaoControle() as db:
            d = db.scalar(select(Dominio).where(Dominio.host == host))
            return _esc(d.cliente) if d else None
    return _memo("host", host, buscar) if host else None


def host_conhecido(host: str) -> bool:
    """O domínio está cadastrado no controle (qualquer status)? Usado na conferência do Host."""
    host = normalizar_host(host)

    def buscar():
        with SessaoControle() as db:
            return db.scalar(select(Dominio.id).where(Dominio.host == host)) is not None
    return bool(_memo("host-conhecido", host, buscar)) if host else False


def por_login(login: str) -> Estudio | None:
    """Catálogo de logins (no endereço principal). Só resolve quando o login existe em UM estúdio que pode entrar;
    repetido em mais de um → None (a pessoa entra pelo endereço do estúdio). O Admin MayaFit nunca é achado por aqui
    (abre só no domínio dele). Sem cache: o login acabou de ser criado ou mudou."""
    chave = (login or "").strip().lower()
    if not chave:
        return None
    with SessaoControle() as db:
        clientes = db.scalars(select(Cliente).join(Login, Login.cliente_id == Cliente.id).where(
            Login.chave == chave, Cliente.status.in_(ATIVOS), Cliente.tipo != "mayacorp")).all()
        return _esc(clientes[0]) if len(clientes) == 1 else None


def ativos() -> list[Estudio]:
    with SessaoControle() as db:
        return [e for c in db.scalars(select(Cliente).order_by(Cliente.id)) if (e := _esc(c))]


def recursos_do(slug: str) -> list[str]:
    """Recursos do plano + extras liberados ao estúdio (cache curto)."""
    def buscar():
        with SessaoControle() as db:
            c = db.scalar(select(Cliente).where(Cliente.slug == slug))
            if c is None:
                return []
            itens = list((c.plano.recursos if c.plano else None) or []) + list(c.extras or [])
            return list(dict.fromkeys(itens))
    return list(_memo("recursos", slug, buscar))


def info(slug: str) -> dict | None:
    """Resumo do estúdio para o /api/auth/me: slug, nome, mayacorp, status, teste_ate, recursos."""
    def buscar():
        with SessaoControle() as db:
            c = db.scalar(select(Cliente).where(Cliente.slug == slug))
            if c is None:
                return None
            return {"slug": c.slug, "nome": c.nome, "mayacorp": c.tipo == "mayacorp", "status": c.status,
                    "teste_ate": c.teste_ate}
    dados = _memo("info", slug, buscar)
    return {**dados, "recursos": recursos_do(slug)} if dados else None


# ---------------------------------------------------------------- catálogo de logins
def _cliente_id(db, slug: str) -> int:
    cid = db.scalar(select(Cliente.id).where(Cliente.slug == slug))
    if cid is None:
        raise RegraControle(f"Estúdio {slug} não existe no controle.")
    return cid


def sincronizar_usuario(slug: str, usuario_id: int, login: str | None) -> None:
    """Deixa no catálogo exatamente o login deste usuário (None = tira: sem login, inativo ou sem acesso).
    Só o login entra: ninguém entra com e-mail."""
    chave = (login or "").strip().lower() or None
    with SessaoControle() as db:
        cid = _cliente_id(db, slug)
        for x in db.scalars(select(Login).where(Login.cliente_id == cid, Login.usuario_id == usuario_id)):
            if x.chave != chave:
                db.delete(x)
        if chave:
            x = db.get(Login, (chave, cid))
            if x is None:
                db.add(Login(chave=chave, cliente_id=cid, usuario_id=usuario_id))
            else:
                x.usuario_id = usuario_id
        db.commit()


def chave_do_usuario(u) -> str | None:
    """O que vai para o catálogo: o login de quem pode entrar."""
    return u.login if u.login and u.ativo and u.acesso_sistema else None


def sincronizar_todos(slug: str) -> int:
    """Reconstrói o catálogo do estúdio a partir dos usuários do banco dele."""
    from app.core.db import SessionLocal
    from app.core.models import Usuario

    with SessaoControle() as db:
        c = db.scalar(select(Cliente).where(Cliente.slug == slug))
        if c is None:
            raise RegraControle(f"Estúdio {slug} não existe no controle.")
        esc = Estudio(slug=c.slug, banco=c.banco, mayacorp=c.tipo == "mayacorp")
    with tenancy.usando(esc), SessionLocal() as s:
        usuarios = [(u.id, chave_do_usuario(u)) for u in s.scalars(select(Usuario))]
    with SessaoControle() as db:
        cid = _cliente_id(db, slug)
        db.execute(delete(Login).where(Login.cliente_id == cid))
        for uid, chave in usuarios:
            if chave and db.get(Login, (chave.lower(), cid)) is None:
                db.add(Login(chave=chave.lower(), cliente_id=cid, usuario_id=uid))
                db.flush()
        db.commit()
    return len(usuarios)


# ---------------------------------------------------------------- estúdios
def registrar(slug: str, nome: str, *, banco: str | None, status: str = "ativo", dias_teste: int | None = None,
              dominios: list[str] | None = None, tipo: str = "estudio", **ficha) -> Cliente:
    if not SLUG.match(slug or ""):
        raise RegraControle("Identificador: letras minúsculas, números e hífen (2 a 39), começando com letra.")
    if status not in STATUS:
        raise RegraControle(f"Status inválido: {status}.")
    with SessaoControle() as db:
        if db.scalar(select(Cliente).where(Cliente.slug == slug)):
            raise RegraControle(f"Já existe o estúdio {slug}.")
        if banco is None and db.scalar(select(Cliente).where(Cliente.banco.is_(None))):
            raise RegraControle("Já existe um estúdio no banco principal.")
        if tipo == "mayacorp" and db.scalar(select(Cliente).where(Cliente.tipo == "mayacorp")):
            raise RegraControle("O Admin MayaFit já existe.")
        c = Cliente(slug=slug, nome=nome, banco=banco, status="teste" if dias_teste else status, tipo=tipo,
                    teste_ate=date.today() + timedelta(days=dias_teste) if dias_teste else None, **ficha)
        db.add(c)
        db.flush()
        for host in dict.fromkeys(normalizar_host(h) for h in (dominios or []) if h):
            adicionar_dominio(db, c, host)
        db.commit()
        limpar_cache()
        return c


def adicionar_dominio(db, cliente: Cliente, host: str) -> Dominio:
    host = normalizar_host(host)
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", host):
        raise RegraControle(f"Domínio inválido: {host}")
    if db.scalar(select(Dominio).where(Dominio.host == host)):
        raise RegraControle(f"O domínio {host} já está em uso.")
    d = Dominio(cliente_id=cliente.id, host=host)
    db.add(d)
    db.flush()
    limpar_cache()
    return d


def dominio_padrao(slug: str) -> str | None:
    """`<slug>.<DOMINIO_BASE>` (None sem DOMINIO_BASE no .env do servidor)."""
    from app.core.config import settings

    base = normalizar_host(settings.dominio_base or "")
    return f"{slug}.{base}" if base else None


def nome_do_banco(slug: str) -> str:
    return "mayafit_" + slug.replace("-", "_")


def criar_banco(banco: str) -> None:
    """CREATE DATABASE no mesmo servidor do principal (no SQLite o arquivo nasce na primeira conexão)."""
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ProgrammingError

    from app.core.config import settings

    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite":
        return
    if not re.match(r"^[a-z][a-z0-9_]{1,62}$", banco):
        raise RegraControle("Nome de banco inválido.")
    adm = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with adm.connect() as conn:
            if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": banco}):
                conn.execute(text(f'CREATE DATABASE "{banco}"'))
    except ProgrammingError as e:
        if "permission denied" in str(e).lower():
            raise RegraControle(f"O servidor do banco não deixa o MayaFit criar bancos. Peça ao suporte para rodar: "
                                f"ALTER ROLE {url.username} CREATEDB;") from e
        raise
    finally:
        adm.dispose()


def migrar(estudio: Estudio) -> None:
    """Aplica as migrations do sistema (alembic/) no banco do estúdio."""
    from alembic.config import Config

    from alembic import command
    from app.core.config import BASE_DIR

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    with tenancy.engine_do(estudio.banco).connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()


def migrar_controle() -> None:
    """Cria/atualiza as tabelas do banco de controle (alembic_controle/) e os planos padrão, se existirem."""
    from alembic.config import Config

    from alembic import command
    from app.core.config import BASE_DIR

    cfg = Config(str(BASE_DIR / "alembic_controle.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic_controle"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    try:  # os planos padrão são do Admin MayaFit (app/controle/planos.py), quando existir
        from app.controle import planos
    except ImportError:
        return
    if hasattr(planos, "garantir_padrao"):
        with SessaoControle() as db:
            planos.garantir_padrao(db)
            db.commit()


def migrar_todos() -> list[str]:
    """Controle + o banco de cada estúdio (o principal é migrado pelo deploy de sempre). Devolve os migrados."""
    migrar_controle()
    try:
        registrar_principal_se_faltar()
    except RegraControle:
        log.exception("Não foi possível registrar o estúdio do banco principal no controle")
    feitos = []
    for esc in ativos():
        if esc.banco is not None:
            migrar(esc)
            feitos.append(esc.slug)
    return feitos


def _slugificar(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:39].strip("-")
    return s if SLUG.match(s) else f"estudio-{s}"[:39].strip("-") if s else "estudio"


def _login_de(email: str) -> str:
    base = re.sub(r"[^a-z0-9._-]", "", unicodedata.normalize("NFKD", email.split("@")[0]).encode("ascii", "ignore")
                  .decode().lower())
    return (base + "adm")[:60] if len(base) < 3 else base[:60]


def provisionar(slug: str, nome: str, *, admin_email: str, admin_nome: str = "", dias_teste: int | None = None,
                dominios: list[str] | None = None, tipo: str = "estudio", admin_login: str | None = None,
                admin_senha: str | None = None, primeiro_acesso: bool = False, **ficha) -> tuple[Cliente, str]:
    """Estúdio novo: banco próprio, tabelas, identidade (nome), perfis padrão, o usuário Suporte e:
    - com `primeiro_acesso`: devolve o link de boas-vindas (o dono cria o usuário master; admin_email só recebe o link);
    - senão: cria o administrador (com `admin_senha` → devolve ""; sem senha → devolve o link do convite).
    Com DOMINIO_BASE, o subdomínio `<slug>.<DOMINIO_BASE>` entra sozinho. Sem estúdio pela metade em caso de erro."""
    from app.core.db import SessionLocal
    from app.core.security import validar_politica_senha
    from app.seed import base as base_do_estudio

    email = (admin_email or "").strip().lower()
    login = (admin_login or "").strip().lower() or (None if primeiro_acesso else _login_de(email))
    if not email or "@" not in email:
        raise RegraControle("Informe o e-mail do administrador.")
    if login and not _LOGIN.match(login):
        raise RegraControle("Login: letras minúsculas, números, ponto, hífen ou sublinhado (3 a 60).")
    if admin_senha and (erro := validar_politica_senha(admin_senha)):
        raise RegraControle(erro)
    if not SLUG.match(slug or ""):
        raise RegraControle("Identificador: letras minúsculas, números e hífen (2 a 39), começando com letra.")
    with SessaoControle() as db:
        if db.scalar(select(Cliente.id).where(Cliente.slug == slug)):
            raise RegraControle(f"Já existe o estúdio {slug}.")
    hosts = list(dominios or [])
    if (padrao := dominio_padrao(slug)) and padrao not in [normalizar_host(h) for h in hosts]:
        hosts.insert(0, padrao)
    banco = nome_do_banco(slug)
    criar_banco(banco)  # antes de registrar: sem banco, o estúdio não pode existir no controle
    cliente = registrar(slug, nome, banco=banco, dias_teste=dias_teste, dominios=hosts, tipo=tipo, **ficha)
    esc = Estudio(slug=slug, banco=banco, mayacorp=tipo == "mayacorp")
    try:
        migrar(esc)
        with tenancy.usando(esc), SessionLocal() as db:
            base_do_estudio(db, nome="MayaFit" if tipo == "mayacorp" else nome)  # o admin se apresenta como MayaFit
            if tipo != "mayacorp":
                _usuario_suporte(db, slug)
            if primeiro_acesso:
                db.commit()
                link = link_primeiro_acesso(slug, email)
            else:
                admin = _primeiro_admin(db, admin_nome or nome, email, login, admin_senha)
                link = "" if admin_senha else _convite(db, admin)
                db.commit()
    except Exception:
        with SessaoControle() as db:  # não deixa estúdio pela metade no controle (o banco vazio pode ser reaproveitado)
            db.execute(delete(Login).where(Login.cliente_id == cliente.id))
            db.execute(delete(Dominio).where(Dominio.cliente_id == cliente.id))
            db.execute(delete(Cliente).where(Cliente.id == cliente.id))
            db.commit()
        limpar_cache()
        raise
    sincronizar_todos(slug)
    return cliente, link


def _senha_suporte_hash() -> str | None:
    with SessaoControle() as ctl:
        return ctl.scalar(select(PoliticaComercial.senha_suporte_hash).order_by(PoliticaComercial.id).limit(1))


def _usuario_suporte(db, slug: str):
    """Usuário "Suporte" da MayaCorp em todo estúdio novo (perfil administrador; não conta no limite de usuários do
    plano). A senha é a definida no admin (PoliticaComercial.senha_suporte_hash); sem ela, nasce sem senha."""
    from app.core import perfis
    from app.core.models import Usuario

    senha_hash = _senha_suporte_hash()
    adm = next(p for p in perfis.garantir_padrao(db).values() if p.administrador)
    u = Usuario(nome="Suporte", email=f"suporte+{slug}@mayacorp.com.br", login=f"suporte.{slug}",
                perfil_acesso_id=adm.id, senha_hash=senha_hash, convite_pendente=senha_hash is None, suporte=True)
    db.add(u)
    db.flush()
    return u


def _primeiro_admin(db, nome: str, email: str, login: str, senha: str | None):
    from app.core import audit, perfis
    from app.core.models import Usuario
    from app.core.security import hash_senha

    adm = next(p for p in perfis.garantir_padrao(db).values() if p.administrador)
    u = Usuario(nome=nome, email=email, login=login, perfil_acesso_id=adm.id,
                senha_hash=hash_senha(senha) if senha else None, convite_pendente=not senha)
    db.add(u)
    db.flush()
    audit.registrar(db, usuario=None, acao="usuario.criar_provisionamento", entidade="usuario", entidade_id=u.id,
                    descricao="Administrador criado junto com o estúdio")
    return u


def _convite(db, u) -> str:
    from app.core import auth_service

    return auth_service.criar_link_email(db, u)


def _estudio_do_cliente(slug: str) -> Estudio:
    with SessaoControle() as db:
        c = db.scalar(select(Cliente).where(Cliente.slug == slug))
        if c is None:
            raise RegraControle(f"Estúdio {slug} não existe.")
        return Estudio(slug=c.slug, banco=c.banco, mayacorp=c.tipo == "mayacorp")


def link_primeiro_acesso(slug: str, email: str) -> str:
    """Link de boas-vindas (vale 7 dias): o dono cria o usuário master. O token assinado carrega o estúdio (`est`)."""
    from app.core.config import settings
    from app.core.security import criar_token

    with tenancy.usando(_estudio_do_cliente(slug)):
        token = criar_token(slug, "primeiro", {"email": (email or "").strip().lower()})
    return f"{settings.frontend_url.rstrip('/')}/primeiro-acesso?token={token}"


def estudio_mayacorp() -> Estudio | None:
    with SessaoControle() as db:
        c = db.scalar(select(Cliente).where(Cliente.tipo == "mayacorp"))
        return Estudio(slug=c.slug, banco=c.banco, mayacorp=True) if c else None


def endereco_do_painel() -> str | None:
    """Domínio do Admin MayaFit (o 1º cadastrado): o admin só abre nele."""
    with SessaoControle() as db:
        return db.scalar(select(Dominio.host).join(Cliente).where(Cliente.tipo == "mayacorp").order_by(Dominio.id))


def zerar_senha_suporte(slug: str, senha_hash: str | None) -> bool:
    """Grava a senha (hash) do usuário Suporte do estúdio e derruba as sessões dele. False se o estúdio não tem Suporte."""
    from app.core import auth_service
    from app.core.db import SessionLocal
    from app.core.models import Usuario

    with tenancy.usando(_estudio_do_cliente(slug)), SessionLocal() as db:
        u = db.scalar(select(Usuario).where(Usuario.suporte.is_(True)).order_by(Usuario.id))
        if u is None:
            return False
        u.senha_hash = senha_hash
        u.convite_pendente = senha_hash is None
        u.tentativas_falhas, u.bloqueado_ate = 0, None
        auth_service.invalidar_sessoes(db, u)
        db.commit()
        return True


def definir_status(slug: str, status: str) -> Cliente:
    """teste | ativo | suspenso | inativo (inativo não entra; o cache curto é limpo na hora)."""
    if status not in STATUS:
        raise RegraControle(f"Status inválido: {status}.")
    with SessaoControle() as db:
        c = db.scalar(select(Cliente).where(Cliente.slug == slug))
        if c is None:
            raise RegraControle(f"Estúdio {slug} não existe.")
        c.status = status
        db.commit()
    limpar_cache()
    return c


# ---------------------------------------------------------------- uso (para o admin e a cobrança)
def coletar_uso(estudio: Estudio) -> dict:
    """Foto do uso do estúdio: alunos ativos, usuários (sem o Suporte, só quem tem acesso) e aulas do mês."""
    from app.core.db import SessionLocal
    from app.core.models import Usuario
    from app.modules.agenda.models import AulaSessao
    from app.modules.alunos.models import Aluno, StatusAluno

    hoje = date.today()
    inicio = hoje.replace(day=1)
    fim = (inicio + timedelta(days=32)).replace(day=1)
    with tenancy.usando(estudio), SessionLocal() as db:
        alunos = db.scalar(select(func.count()).select_from(Aluno).where(Aluno.status == StatusAluno.ATIVO))
        usuarios = db.scalar(select(func.count()).select_from(Usuario).where(
            Usuario.suporte.is_(False), Usuario.ativo.is_(True), Usuario.acesso_sistema.is_(True)))
        aulas = db.scalar(select(func.count()).select_from(AulaSessao).where(
            AulaSessao.data >= inicio, AulaSessao.data < fim))
    return {"alunos_ativos": int(alunos or 0), "usuarios": int(usuarios or 0), "aulas_mes": int(aulas or 0)}


def gravar_uso_todos() -> int:
    """Tarefa do worker (1x por hora): grava `Cliente.uso` de cada estúdio ativo. Um estúdio com erro não para os outros."""
    n = 0
    for esc in ativos():
        if esc.mayacorp:
            continue
        try:
            uso = {**coletar_uso(esc), "em": datetime.now(UTC).isoformat(timespec="seconds")}
        except Exception:
            log.exception("Uso do estúdio %s não coletado", esc.slug)
            continue
        with SessaoControle() as db:
            c = db.scalar(select(Cliente).where(Cliente.slug == esc.slug))
            if c is not None:
                c.uso = uso
                db.commit()
                n += 1
    return n


# ---------------------------------------------------------------- primeira ativação
def registrar_principal_se_faltar(slug: str | None = None) -> str | None:
    """Primeira ativação: o estúdio que já mora no banco principal (há Identidade lá) entra no controle com banco=None
    e com os logins, antes de a API reiniciar no modo novo — ninguém fica sem acesso. Slug: o informado ou o nome."""
    from sqlalchemy import inspect
    from sqlalchemy.orm import Session

    from app.core.models import Identidade

    with SessaoControle() as db:
        if db.scalar(select(Cliente.id).where(Cliente.banco.is_(None))):
            return None
    eng = tenancy.engine_do(None)
    if not inspect(eng).has_table("identidade"):
        return None
    with Session(eng) as db:
        ident = db.scalar(select(Identidade).order_by(Identidade.id))
        if ident is None:
            return None
        nome = ident.nome_exibicao
    slug = slug or _slugificar(nome)
    registrar(slug, nome, banco=None)
    sincronizar_todos(slug)
    return slug
