"""Terminal do banco de controle (um banco por estúdio). Portado do MayaJus (app/controle/cli.py).

    python -m app.controle.cli ativar [--slug-principal mayris]   # cria o mayafit_controle, migra e registra o principal
    python -m app.controle.cli migrar                             # controle + banco de cada estúdio
    python -m app.controle.cli novo-estudio --slug studio-ana --nome "Studio Ana" --admin-email ana@x.com --primeiro-acesso
    python -m app.controle.cli novo-estudio --slug studio-ana --nome "Studio Ana" --admin-email ana@x.com --admin-login ana --teste 15
    python -m app.controle.cli novo-admin-mayacorp --admin-nome "Jefferson" --admin-email voce@mayacorp.com.br \\
        --login jeff --dominio admin.mayafit.com.br --senha-stdin
    python -m app.controle.cli dominio --slug studio-ana --host app.studioana.com.br
    python -m app.controle.cli sincronizar-logins [--slug studio-ana]
    python -m app.controle.cli listar

A senha nunca vai na linha de comando: `--senha-stdin` lê da entrada padrão; sem ela, vai convite por link.
"""

import argparse
import sys

from app.controle import service
from app.controle.models import Cliente, SessaoControle
from app.core import tenancy


def _ativar(slug_principal: str | None) -> None:
    """Cria o banco de controle (no SQLite, o arquivo) e migra. Daqui em diante o modo multi liga sozinho."""
    from pathlib import Path

    from sqlalchemy.engine import make_url

    url = make_url(tenancy.url_controle())
    if url.get_backend_name() == "sqlite":
        Path(url.database or "").parent.mkdir(parents=True, exist_ok=True)
    else:
        service.criar_banco(tenancy.BANCO_CONTROLE)
    service.migrar_controle()
    tenancy.forcar_controle(None)  # redetecta: agora o controle existe
    slug = service.registrar_principal_se_faltar(slug_principal)
    print(f"Banco {tenancy.BANCO_CONTROLE} pronto. Um banco por estúdio ATIVO (reinicie a API e o worker).")
    if slug:
        print(f"O estúdio do banco principal entrou no controle como '{slug}' (logins no catálogo).")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="app.controle.cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ativar", help="cria o banco de controle e migra (liga o modo um banco por estúdio)")
    p.add_argument("--slug-principal", help="slug do estúdio que já mora no banco principal (padrão: pelo nome)")
    sub.add_parser("migrar", help="controle + banco de cada estúdio ativo")
    sub.add_parser("listar")
    p = sub.add_parser("novo-estudio", help="estúdio novo, com banco próprio, usuário Suporte e administrador")
    p.add_argument("--slug", required=True)
    p.add_argument("--nome", required=True)
    p.add_argument("--admin-email", required=True)
    p.add_argument("--admin-nome", default="")
    p.add_argument("--admin-login", help="login do administrador (padrão: a parte do e-mail antes do @)")
    p.add_argument("--senha-stdin", action="store_true", help="lê a senha do administrador da entrada padrão")
    p.add_argument("--primeiro-acesso", action="store_true", help="o dono cria o usuário master pelo link")
    p.add_argument("--teste", type=int, help="dias de teste grátis")
    p.add_argument("--dominio", action="append", default=[])
    p = sub.add_parser("novo-admin-mayacorp", help="o Admin MayaFit (banco próprio, aberto só no domínio dele)")
    p.add_argument("--admin-nome", required=True)
    p.add_argument("--admin-email", required=True)
    p.add_argument("--login", help="login de quem administra (padrão: a parte do e-mail antes do @)")
    p.add_argument("--senha-stdin", action="store_true", help="lê a senha da entrada padrão (sem ela, vai convite)")
    p.add_argument("--dominio", action="append", required=True, help="domínio do admin (ex.: admin.mayafit.com.br)")
    p = sub.add_parser("dominio", help="acrescenta um domínio a um estúdio")
    p.add_argument("--slug", required=True)
    p.add_argument("--host", required=True)
    p = sub.add_parser("sincronizar-logins", help="reconstrói o catálogo de logins (todos os estúdios sem --slug)")
    p.add_argument("--slug")
    a = ap.parse_args(argv)

    try:
        if a.cmd == "ativar":
            _ativar(a.slug_principal)
            return
        if not tenancy.multi():
            if a.cmd == "migrar":  # o deploy sempre chama: sem banco de controle, nada a fazer
                print(f"Sem o banco {tenancy.BANCO_CONTROLE}: um banco só, nada a migrar no controle.")
                return
            sys.exit(f"Sem o banco {tenancy.BANCO_CONTROLE}. Rode antes: python -m app.controle.cli ativar")
        import app.controle.sincronia  # noqa: F401  (catálogo de logins)

        if a.cmd == "migrar":
            print("Migrados:", ", ".join(service.migrar_todos()) or "(só o controle)")
        elif a.cmd == "novo-estudio":
            senha = sys.stdin.readline().rstrip("\r\n") if a.senha_stdin else None
            _, link = service.provisionar(a.slug, a.nome, admin_email=a.admin_email, admin_nome=a.admin_nome,
                                          admin_login=a.admin_login, admin_senha=senha, dias_teste=a.teste,
                                          dominios=a.dominio, primeiro_acesso=a.primeiro_acesso)
            print(f"Estúdio {a.slug} criado no banco {service.nome_do_banco(a.slug)} (com o usuário suporte.{a.slug}).")
            if link:
                print(("Link de primeiro acesso: " if a.primeiro_acesso else "Convite do administrador: ") + link)
        elif a.cmd == "novo-admin-mayacorp":
            senha = sys.stdin.readline().rstrip("\r\n") if a.senha_stdin else None
            _, link = service.provisionar("mayacorp", "Admin MayaFit", admin_nome=a.admin_nome,
                                          admin_email=a.admin_email, admin_login=a.login, admin_senha=senha,
                                          dominios=a.dominio, tipo="mayacorp")
            print(f"Admin MayaFit criado no banco {service.nome_do_banco('mayacorp')} ({', '.join(a.dominio)})."
                  + (f"\nConvite: {link}" if link else " Entre com o login e a senha informados."))
        elif a.cmd == "dominio":
            with SessaoControle() as db:
                c = db.query(Cliente).filter_by(slug=a.slug).one_or_none()
                if not c:
                    sys.exit(f"Estúdio {a.slug} não existe.")
                service.adicionar_dominio(db, c, a.host)
                db.commit()
            print(f"{a.host} → {a.slug}")
        elif a.cmd == "sincronizar-logins":
            slugs = [a.slug] if a.slug else [e.slug for e in service.ativos()]
            for slug in slugs:
                print(f"{slug}: {service.sincronizar_todos(slug)} usuário(s) no catálogo.")
        elif a.cmd == "listar":
            with SessaoControle() as db:
                for c in db.query(Cliente).order_by(Cliente.id):
                    doms = ", ".join(d.host for d in c.dominios) or "-"
                    print(f"{c.slug:20} {c.tipo:9} {c.status:9} {c.banco or '(principal)':28} {doms}")
    except service.RegraControle as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
