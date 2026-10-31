"""Carga inicial idempotente: `python -m app.seed`.

Cria (só o que faltar): identidade "Estúdio Demonstração", configuração de e-mail, perfis de acesso padrão e, em dev,
1 administrador de demonstração. A senha NUNCA fica no código: vem de SEED_ADMIN_SENHA ou é pedida no terminal.

    uv run python -m app.seed                  # dev: base + admin de demonstração
    uv run python -m app.seed --somente-base   # hml/prod: sem usuário (crie com app.criar_usuario)
    uv run python -m app.seed --com-admin      # força o admin também fora do dev

Variáveis: SEED_ADMIN_EMAIL (padrão admin@mayafit.local), SEED_ADMIN_LOGIN (padrão admin), SEED_ADMIN_SENHA.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit, perfis
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import ConfigEmail, ConfigIA, Identidade, Usuario
from app.core.security import hash_senha, validar_politica_senha

NOME_ESTUDIO = "Estúdio Demonstração"


def base(db: Session, nome: str = NOME_ESTUDIO) -> None:
    """Identidade, configs e perfis padrão. Idempotente: não sobrescreve o que o administrador já editou.
    `nome` = nome do estúdio (o provisionamento de um estúdio novo passa o nome dele)."""
    if not db.scalar(select(Identidade.id)):
        db.add(Identidade(id=1, nome_exibicao=nome, assinatura_email=nome))
    if not db.get(ConfigEmail, 1):
        db.add(ConfigEmail(id=1, remetente_nome=nome, copia_padrao=[]))
    if not db.get(ConfigIA, 1):
        db.add(ConfigIA(id=1, ativo=False, provedor="openai"))
    perfis.garantir_padrao(db)
    db.commit()


def admin_demonstracao(db: Session, *, email: str, login: str, senha: str) -> Usuario | None:
    """Cria o administrador se ainda não existir nenhum usuário com este e-mail/login. Devolve o criado (ou None)."""
    if erro := validar_politica_senha(senha):
        raise ValueError(erro)
    email, login = email.strip().lower(), login.strip().lower()
    if db.scalar(select(Usuario.id).where((Usuario.email == email) | (Usuario.login == login))):
        return None
    admin = perfis.garantir_padrao(db)["Full"]
    u = Usuario(nome="Administrador", email=email, login=login, senha_hash=hash_senha(senha), perfil_acesso_id=admin.id)
    db.add(u)
    db.flush()
    audit.registrar(db, usuario=None, acao="usuario.criar_seed", entidade="usuario", entidade_id=u.id,
                    descricao="Administrador de demonstração criado pelo seed")
    db.commit()
    return u


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--somente-base", action="store_true", help="não cria usuário")
    ap.add_argument("--com-admin", action="store_true", help="cria o admin mesmo fora do dev")
    ap.add_argument("--sem-migrar", action="store_true", help="não roda as migrations antes")
    ap.add_argument("--estudio", help="um banco por estúdio: slug do estúdio (obrigatório nesse modo)")
    a = ap.parse_args()

    from app.core import tenancy

    esc = None
    if tenancy.multi():
        from app.controle import service

        if not a.estudio or (esc := service.por_slug(a.estudio)) is None:
            sys.exit("Um banco por estúdio: informe --estudio <slug> de um estúdio ativo (python -m app.controle.cli listar).")
        import app.controle.sincronia  # noqa: F401  (catálogo de logins)
    if not a.sem_migrar:
        if esc is not None and esc.banco is not None:
            from app.controle import service

            service.migrar(esc)
        else:
            from app.main import migrar

            migrar()
    with tenancy.usando(esc), SessionLocal() as db:
        base(db)
        print(f"Base pronta: identidade '{NOME_ESTUDIO}', e-mail, IA e perfis de acesso padrão.")
        if a.somente_base or (settings.ambiente != "dev" and not a.com_admin):
            print("Crie o primeiro acesso: python -m app.criar_usuario --email ... --nome ... --perfil Full")
            return
        senha = os.environ.get("SEED_ADMIN_SENHA") or (getpass.getpass("Senha do admin de demonstração: ") if sys.stdin.isatty() else "")
        if not senha:
            sys.exit("Informe a senha do admin em SEED_ADMIN_SENHA (ou rode em um terminal interativo).")
        u = admin_demonstracao(db, email=os.environ.get("SEED_ADMIN_EMAIL", "admin@mayafit.local"),
                               login=os.environ.get("SEED_ADMIN_LOGIN", "admin"), senha=senha)
        print(f"Administrador criado: {u.email}" if u else "Administrador já existia (nada alterado).")


if __name__ == "__main__":
    main()
