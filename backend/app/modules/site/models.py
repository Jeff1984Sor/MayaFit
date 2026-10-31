"""Site grátis do estúdio: configuração (rascunho + versão publicada) e contatos recebidos pelo formulário.

O conteúdo do site é um JSON validado por `schemas.ConteudoSite` (textos, fotos, seções e ordem). Modalidades, planos,
grade e equipe NÃO são copiados: vêm dos cadastros na hora de montar a página (o site nunca fica desatualizado).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UtcDateTime


class SiteConfig(Base, Timestamped):
    """Linha única (id=1). `conteudo` é o rascunho do editor; `conteudo_publicado` é o que o público vê."""

    __tablename__ = "site_config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    tema: Mapped[str] = mapped_column(String(20), default="aurora")
    conteudo: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tema_publicado: Mapped[str | None] = mapped_column(String(20))
    conteudo_publicado: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    publicado: Mapped[bool] = mapped_column(Boolean, default=False)
    publicado_em: Mapped[datetime | None] = mapped_column(UtcDateTime())
    publicado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))


class SiteContato(Base, Timestamped):
    """Pedido de contato / aula experimental feito pelo site. Guardado SEMPRE (histórico do site), mesmo quando o CRM
    recebe o lead. `lead_id` aponta para o lead do CRM quando ele existir."""

    __tablename__ = "site_contato"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    telefone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(200))
    interesse: Mapped[str | None] = mapped_column(String(120))
    mensagem: Mapped[str | None] = mapped_column(Text)
    quer_aula_experimental: Mapped[bool] = mapped_column(Boolean, default=False)
    consentimento_em: Mapped[datetime] = mapped_column(UtcDateTime())
    consentimento_texto: Mapped[str] = mapped_column(String(300))
    enviado_crm: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_id: Mapped[int | None] = mapped_column(Integer)
    erro_crm: Mapped[str | None] = mapped_column(String(300))
    lido: Mapped[bool] = mapped_column(Boolean, default=False)
