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
    # pacotes cujos modelos ficam em `models.py` e não são importados pelo `__init__` do pacote
    from app.modules.app_aluno import models as _app_aluno_models  # noqa: F401
    from app.modules.comunicacao import models as _comunicacao_models  # noqa: F401
