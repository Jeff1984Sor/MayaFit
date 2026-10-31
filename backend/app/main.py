import importlib
import logging
import pkgutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.controle.sincronia  # noqa: F401  (catálogo de logins do controle, um banco por estúdio)
import app.modules as modulos_pkg
from app.core import tenancy
from app.core.config import BASE_DIR, settings
from app.core.deps import get_contexto
from app.core.estudio_http import EstudioMiddleware
from app.core.routes import arquivos, auditoria, auth, config, public
from app.core.tenancy import EstudioNaoIdentificado

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # o httpx loga a URL completa de cada chamada

VERSAO = (BASE_DIR / "VERSION").read_text().strip() if (BASE_DIR / "VERSION").exists() else "dev"


def migrar() -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite"):
        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    if settings.migrar_na_subida:
        migrar()
        if tenancy.multi():  # um banco por estúdio: o controle e o banco de cada estúdio ativo
            from app.controle import service as controle

            controle.migrar_todos()
    yield


app = FastAPI(
    title=f"{settings.app_name} - API",
    version=VERSAO,
    lifespan=lifespan,
    # documentação interativa só com DEBUG (nunca em hml/prod)
    docs_url="/api/docs" if settings.debug else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.debug else None,
)
# Confere o Host (ALLOWED_HOSTS, aceita "*.dominio"; no modo multi também os domínios do controle) e define o estúdio
# do pedido (token `est` ou endereço). Com um banco só, é só a conferência do Host (como o TrustedHostMiddleware).
app.add_middleware(EstudioMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def _cabecalhos_de_seguranca(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


def _traduzir(e: dict) -> str:
    ctx = e.get("ctx") or {}
    tipo = e.get("type", "")
    if tipo == "missing":
        return "campo obrigatório"
    if tipo == "string_too_short":
        return f"precisa ter pelo menos {ctx.get('min_length')} caracteres"
    if tipo == "string_too_long":
        return f"pode ter no máximo {ctx.get('max_length')} caracteres"
    if tipo == "string_pattern_mismatch":
        return "formato inválido"
    if tipo == "value_error" and "email" in e.get("msg", "").lower():
        return "e-mail inválido"
    if tipo.startswith(("int_", "decimal_", "float_")):
        return "número inválido"
    if tipo.startswith("date"):
        return "data inválida"
    return e.get("msg", "valor inválido")


@app.exception_handler(EstudioNaoIdentificado)
async def _sem_estudio(_: Request, exc: EstudioNaoIdentificado):
    """Um banco por estúdio: pedido sem estúdio identificado não abre banco nenhum; pede login de novo."""
    return JSONResponse(status_code=401, content={"detail": "Sessão expirada. Entre novamente."})


@app.exception_handler(RequestValidationError)
async def _validacao(_: Request, exc: RequestValidationError):
    """422 em português claro: primeiro problema no `detail`, lista completa em `erros`."""
    erros = []
    for e in exc.errors():
        campo = ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path"))
        erros.append({"campo": campo, "mensagem": _traduzir(e)})
    primeiro = erros[0] if erros else {"campo": "", "mensagem": "Dados inválidos."}
    return JSONResponse(status_code=422, content={"detail": f"{primeiro['campo']}: {primeiro['mensagem']}".strip(": "), "erros": erros})


# --- Rotas SEM login (cada uma precisa estar em permissoes.PUBLICAS) ---
for r in (auth.publico, public.router):
    app.include_router(r, prefix="/api")

# --- Rotas PROTEGIDAS: o login é exigido no nível do router (negar por padrão), além do mapa de permissões ---
_protegidas = [auth.router, config.router, auditoria.router, arquivos.router]


def _descobrir_modulos() -> None:
    """Cada módulo de negócio expõe `app/modules/<nome>/routes.py` com `router` (protegido) e, se precisar,
    `router_publico` (autenticação própria: webhook, chave de API, app do aluno; ver permissoes.PUBLICAS_AUTENTICACAO_PROPRIA)."""
    for info in pkgutil.iter_modules(modulos_pkg.__path__):
        try:
            mod = importlib.import_module(f"app.modules.{info.name}.routes")
        except ModuleNotFoundError as e:
            if e.name == f"app.modules.{info.name}.routes":
                continue
            raise
        if hasattr(mod, "router"):
            _protegidas.append(mod.router)
        if hasattr(mod, "router_publico"):
            app.include_router(mod.router_publico, prefix="/api")


_descobrir_modulos()
for r in _protegidas:
    app.include_router(r, prefix="/api", dependencies=[Depends(get_contexto)])


@app.get("/api/health", tags=["infra"])
def health():
    return {"ok": True, "versao": VERSAO, "ambiente": settings.ambiente}
