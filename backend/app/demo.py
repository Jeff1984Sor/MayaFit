"""Ambiente de DEMONSTRAÇÃO multi-tenant completo (só dev, só dados sintéticos): `uv run python -m app.demo`.

Monta, numa pasta própria (padrão `data/demo/`, não mexe no `data/dev.db`):
- o banco de controle (`mayafit_controle.db`) → o modo um banco por estúdio liga sozinho;
- o Admin MayaFit (cliente tipo "mayacorp", domínio `admin.localhost`);
- dois estúdios com banco próprio: "Studio Alfa Pilates" (`studio-alfa.localhost`) e "Beta Funcional"
  (`studio-beta.localhost`), cada um com administrador, professor, secretária e o usuário Suporte;
- os dados sintéticos de cada módulo: chama `popular_demo(db)` de `app/modules/<modulo>/demo.py` (se existir) dentro de
  cada estúdio, e `app.modules.admin_mayacorp.demo.popular_demo()` (se existir) para o controle.

Os endereços `*.localhost` resolvem para 127.0.0.1 nos navegadores. A senha de todos vem de DEMO_SENHA (ou é gerada e
mostrada no fim). Para usar: rode a API e o worker com as variáveis que o comando imprime.

    uv run python -m app.demo                 # cria em data/demo (recusa se já existir)
    uv run python -m app.demo --recriar       # apaga data/demo e cria de novo
    uv run python -m app.demo --pasta /tmp/x  # outra pasta
"""

import argparse
import importlib
import logging
import os
import pkgutil
import secrets
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
log = logging.getLogger("demo")

ESTUDIOS = [
    {"slug": "studio-alfa", "nome": "Studio Alfa Pilates", "admin": ("Ana Souza", "ana@alfa.demo", "ana"),
     "equipe": [("Carlos Lima", "carlos@alfa.demo", "carlos", "Professor"),
                ("Dora Reis", "dora@alfa.demo", "dora", "Secretária")]},
    {"slug": "studio-beta", "nome": "Beta Funcional", "admin": ("Bruno Melo", "bruno@beta.demo", "bruno"),
     "equipe": [("Ana Prado", "ana@beta.demo", "ana", "Professor"),  # "ana" repete: no endereço principal é ambíguo
                ("Eva Nunes", "eva@beta.demo", "eva", "Secretária")]},
]


def _args(argv):
    ap = argparse.ArgumentParser(prog="app.demo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pasta", default=str(BASE_DIR / "data" / "demo"))
    ap.add_argument("--recriar", action="store_true", help="apaga a pasta da demonstração antes")
    ap.add_argument("--dominio-base", default="localhost", help="subdomínio de cada estúdio (padrão: localhost)")
    return ap.parse_args(argv)


def _preparar_ambiente(a) -> Path:
    """O app lê o .env na importação: as variáveis da demonstração precisam vir ANTES de importar qualquer coisa."""
    pasta = Path(a.pasta).resolve()
    if pasta.exists() and any(pasta.iterdir()):
        if not a.recriar:
            sys.exit(f"{pasta} já existe. Use --recriar para apagar e montar de novo.")
        shutil.rmtree(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{(pasta / 'principal.db').as_posix()}"
    os.environ["STORAGE_DIR"] = str(pasta / "storage")
    os.environ["DOMINIO_BASE"] = a.dominio_base
    return pasta


def _modulos_com_demo() -> list:
    import app.modules as modulos_pkg

    achados = []
    for info in pkgutil.iter_modules(modulos_pkg.__path__):
        nome = f"app.modules.{info.name}.demo"
        try:
            mod = importlib.import_module(nome)
        except ModuleNotFoundError as e:
            if e.name == nome:
                continue
            raise
        if hasattr(mod, "popular_demo") and info.name != "admin_mayacorp":
            achados.append(mod)
    return achados


def _equipe(esc, equipe, senha: str) -> None:
    from app.core import perfis, tenancy
    from app.core.db import SessionLocal
    from app.core.models import Usuario
    from app.core.security import hash_senha

    with tenancy.usando(esc), SessionLocal() as db:
        padrao = perfis.garantir_padrao(db)
        for nome, email, login, perfil in equipe:
            db.add(Usuario(nome=nome, email=email, login=login, perfil_acesso_id=padrao[perfil].id,
                           senha_hash=hash_senha(senha)))
        db.commit()


def main(argv: list[str] | None = None) -> None:
    a = _args(argv)
    pasta = _preparar_ambiente(a)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from app.core.config import settings

    if settings.ambiente != "dev":
        sys.exit("A demonstração só roda com AMBIENTE=dev.")
    import app.controle.sincronia  # noqa: F401  (catálogo de logins)
    from app.controle import service
    from app.controle.models import PoliticaComercial, SessaoControle
    from app.core import tenancy
    from app.core.db import SessionLocal
    from app.core.security import hash_senha, validar_politica_senha
    from app.main import migrar

    senha = os.environ.get("DEMO_SENHA") or f"Demo-{secrets.token_urlsafe(6)}1"
    if erro := validar_politica_senha(senha):
        sys.exit(f"DEMO_SENHA: {erro}")

    migrar()  # o banco principal fica vazio (sem estúdio): todos os estúdios têm banco próprio
    service.migrar_controle()
    tenancy.forcar_controle(None)  # redetecta: agora o controle existe → modo multi
    assert tenancy.multi(), "o banco de controle deveria existir"
    with SessaoControle() as db:
        db.add(PoliticaComercial(id=1, senha_suporte_hash=hash_senha(senha)))
        db.commit()

    service.provisionar("mayacorp", "Admin MayaFit", admin_nome="Administração MayaFit", admin_email="admin@mayafit.demo",
                        admin_login="admin", admin_senha=senha, dominios=[f"admin.{a.dominio_base}"], tipo="mayacorp")
    modulos = _modulos_com_demo()
    for e in ESTUDIOS:
        nome, email, login = e["admin"]
        service.provisionar(e["slug"], e["nome"], admin_nome=nome, admin_email=email, admin_login=login,
                            admin_senha=senha, dias_teste=30 if e["slug"] == "studio-beta" else None)
        esc = service.por_slug(e["slug"])
        _equipe(esc, e["equipe"], senha)
        for mod in modulos:
            with tenancy.usando(esc), SessionLocal() as db:
                mod.popular_demo(db)
                db.commit()
            log.info("%s: dados de %s", e["slug"], mod.__name__)
    try:
        from app.modules.admin_mayacorp import demo as demo_admin
    except ModuleNotFoundError as e:
        if e.name not in ("app.modules.admin_mayacorp", "app.modules.admin_mayacorp.demo"):
            raise
        demo_admin = None
    if demo_admin is not None and hasattr(demo_admin, "popular_demo"):
        demo_admin.popular_demo()
        log.info("controle: dados de app.modules.admin_mayacorp.demo")
    service.gravar_uso_todos()

    print(f"\nDemonstração pronta em {pasta}\nSenha de todos os usuários: {senha}\n")
    print("Endereços (rode a API na porta 8000 e o Next na 3000):")
    print(f"  Admin MayaFit   http://admin.{a.dominio_base}:3000   login admin")
    for e in ESTUDIOS:
        logins = ", ".join([e["admin"][2]] + [x[2] for x in e["equipe"]] + [f"suporte.{e['slug']}"])
        print(f"  {e['nome']:16} http://{e['slug']}.{a.dominio_base}:3000   logins {logins}")
    print("\nNo endereço principal (localhost) o login curto acha o estúdio pelo catálogo; 'ana' é ambíguo.")
    print("\nVariáveis para a API e o worker usarem a demonstração:")
    print(f"  DATABASE_URL={os.environ['DATABASE_URL']}")
    print(f"  STORAGE_DIR={os.environ['STORAGE_DIR']}")
    print(f"  DOMINIO_BASE={a.dominio_base}")
    print('  ALLOWED_HOSTS=["localhost","127.0.0.1"]   (os domínios dos estúdios são aceitos pelo controle)')


if __name__ == "__main__":
    main()
