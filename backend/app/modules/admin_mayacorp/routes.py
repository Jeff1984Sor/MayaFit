"""Rotas do admin MayaFit (cliente `tipo="mayacorp"` do controle) e do "Meu plano" dos estúdios.

- `router` (protegido, login exigido pelo main.py):
    `/api/admin/*`  → guarda `servico.Painel`: só no estúdio MayaCorp e só para administradores (403 nos demais).
    `/api/meu-plano` → só administradores de um estúdio cliente.
- `router_publico` (sem login, cada rota na lista PUBLICAS de app/core/permissoes.py, com limite por IP):
    `/api/public/planos`, `/api/public/cadastro`, `/api/public/solicitacao[/aprovar|/recusar]` (link assinado do
    e-mail) e `/api/public/mercadopago` (webhook com a assinatura secreta).

Permissão: as rotas são LIVRES no mapa (basta estar logado) porque a guarda de cada uma é mais estrita que o
catálogo de permissões do estúdio (exige o estúdio MayaCorp + administrador, ou administrador no "Meu plano").
"""

from fastapi import APIRouter

from app.core.permissoes import LIVRE, adicionar_regras
from app.modules.admin_mayacorp import rotas_cadastro, rotas_cobranca, rotas_estudios, rotas_painel

adicionar_regras([
    ("*", r"/admin/", LIVRE),  # guarda: servico._painel (MayaCorp + administrador)
    ("*", r"/meu-plano", LIVRE),  # guarda: rotas_cobranca._meu_cliente (administrador do estúdio)
])

router = APIRouter()
for _r in (rotas_painel.router, rotas_estudios.router, rotas_cobranca.admin, rotas_cadastro.admin, rotas_cobranca.meu):
    router.include_router(_r)

router_publico = APIRouter()
for _r in (rotas_cadastro.publico, rotas_cobranca.publico):
    router_publico.include_router(_r)
