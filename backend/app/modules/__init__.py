"""Módulos de negócio do MayaFit."""


def registrar_modelos() -> None:
    """Importa todos os modelos para registrá-los no `Base.metadata` (create_all, Alembic, ETL)."""
    import app.core.models  # noqa: F401
    from app.modules import (  # noqa: F401
        agenda,
        alunos,
        cadastros,
        contratos,
        financeiro,
        integracoes,
    )
    # todo módulo com `models.py` entra sozinho (crm, site, acesso, wellhub, nfse... sem editar esta lista)
    import importlib
    import pkgutil

    import app.modules as pacote

    for info in pkgutil.iter_modules(pacote.__path__):
        try:
            importlib.import_module(f"app.modules.{info.name}.models")
        except ModuleNotFoundError as e:
            if e.name != f"app.modules.{info.name}.models":
                raise
