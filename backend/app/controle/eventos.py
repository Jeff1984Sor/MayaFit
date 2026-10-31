"""Linha do tempo dos estúdios (tabela `evento_cliente` do controle). Quem muda algo de um estúdio registra aqui."""

from app.controle.models import EventoCliente

STATUS = {"teste": "Em teste", "ativo": "Ativo", "suspenso": "Suspenso (avisado)", "inativo": "Inativo (sem acesso)"}

TIPOS = {
    "criado": "Estúdio criado",
    "status": "Status",
    "plano": "Plano",
    "teste": "Teste grátis",
    "cobranca": "Cobrança",
    "pagamento": "Pagamento",
    "contrato": "Contrato",
    "dominio": "Endereço",
    "acesso": "Acesso",
    "ficha": "Ficha",
}


def registrar(db, cliente_id: int, tipo: str, descricao: str, *, usuario: str | None = None,
              dados: dict | None = None) -> EventoCliente:
    """Acrescenta o evento na sessão do controle (quem chama faz o commit)."""
    ev = EventoCliente(cliente_id=cliente_id, tipo=tipo, descricao=descricao[:500], usuario=usuario,
                       dados=dados or {})
    db.add(ev)
    return ev


def mudou_status(db, cliente_id: int, de: str, para: str, *, usuario: str | None = None, motivo: str = "") -> None:
    texto = f"Status: {STATUS.get(de, de)} → {STATUS.get(para, para)}" + (f" ({motivo})" if motivo else "")
    registrar(db, cliente_id, "status", texto, usuario=usuario, dados={"de": de, "para": para})


def out(ev: EventoCliente) -> dict:
    return {"id": ev.id, "tipo": ev.tipo, "tipo_rotulo": TIPOS.get(ev.tipo, ev.tipo), "descricao": ev.descricao,
            "dados": ev.dados or {}, "usuario": ev.usuario or "Sistema", "criado_em": ev.criado_em}
