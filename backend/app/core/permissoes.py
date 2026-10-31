"""Perfis de acesso: catálogo de permissões e o mapa rota -> permissão aplicado no servidor.

Cada permissão é "recurso.acao". O perfil administrador pode tudo.

NEGAR POR PADRÃO: toda rota protegida passa por `deps.get_contexto`, que consulta `permissao_da_rota`.
Rota que não casa com nenhuma regra recebe 403 (não existe mais fallback por perfil legado). Quem cria rotas
novas PRECISA acrescentar a regra aqui (`adicionar_regras`) ou declará-la em PUBLICAS. O teste
`tests/test_cobertura_rotas.py` enumera todas as rotas do app e falha se alguma ficar de fora.
"""

import re

ROTULO_ACAO = {
    "ver": "Ver",
    "editar": "Criar e editar",
    "excluir": "Excluir",
    "operar": "Operar a aula (chegou, faltou, remarcar, finalizar)",
    "evoluir": "Registrar evolução",
    "avaliar": "Registrar avaliação",
    "baixar": "Dar baixa (recebimento)",
    "pagar": "Pagar / reabrir",
    "gerar": "Gerar arquivo",
    "enviar": "Enviar mensagens",
    "configurar": "Configurar",
    "usar": "Usar",
}

# Ids de recurso sem ponto (o ponto separa recurso e ação). "financeiro_receber" = financeiro.receber do planejamento.
CATALOGO: list[dict] = [
    {"grupo": "Geral", "recursos": [
        {"id": "painel", "nome": "Painel (dashboard)", "acoes": ["ver"]},
        {"id": "ia", "nome": "Inteligência Artificial (melhorar textos, preencher cadastros)", "acoes": ["usar"]},
    ]},
    {"grupo": "Alunos e agenda", "recursos": [
        {"id": "alunos", "nome": "Alunos (cadastro, ficha, documentos)", "acoes": ["ver", "editar", "excluir"]},
        {"id": "agenda", "nome": "Agenda (grade semanal e horários das aulas)", "acoes": ["ver", "editar", "excluir"]},
        {"id": "aulas", "nome": "Aulas (painel operacional, evolução e avaliação)", "acoes": ["ver", "operar", "evoluir", "avaliar"]},
        {"id": "reposicoes", "nome": "Reposições (pedidos dos alunos: só a gerência aprova)", "acoes": ["ver", "editar"]},
    ]},
    {"grupo": "Contratos", "recursos": [
        {"id": "contratos", "nome": "Contratos (precificação, parcelas, assinatura)", "acoes": ["ver", "editar", "excluir", "enviar"]},
        {"id": "planos", "nome": "Planos", "acoes": ["ver", "editar", "excluir"]},
    ]},
    {"grupo": "Financeiro", "recursos": [
        {"id": "financeiro_receber", "nome": "Contas a receber", "acoes": ["ver", "editar", "baixar", "excluir"]},
        {"id": "financeiro_pagar", "nome": "Contas a pagar", "acoes": ["ver", "editar", "pagar", "excluir"]},
        {"id": "financeiro_caixa", "nome": "Fluxo de caixa", "acoes": ["ver"]},
        {"id": "financeiro_dre", "nome": "DRE", "acoes": ["ver"]},
        {"id": "financeiro_bancos", "nome": "Contas bancárias e movimentos", "acoes": ["ver", "editar", "excluir"]},
        {"id": "receita_saude", "nome": "Receita Saúde", "acoes": ["ver", "gerar"]},
        {"id": "comissoes", "nome": "Comissões dos profissionais", "acoes": ["ver", "editar"]},
    ]},
    {"grupo": "Cadastros", "recursos": [
        {"id": "cadastros_unidades", "nome": "Unidades", "acoes": ["ver", "editar", "excluir"]},
        {"id": "cadastros_servicos", "nome": "Tipos de serviço", "acoes": ["ver", "editar", "excluir"]},
        {"id": "cadastros_profissionais", "nome": "Profissionais", "acoes": ["ver", "editar", "excluir"]},
        {"id": "cadastros_fornecedores", "nome": "Fornecedores", "acoes": ["ver", "editar", "excluir"]},
        {"id": "cadastros_categorias", "nome": "Categorias e subcategorias", "acoes": ["ver", "editar", "excluir"]},
        {"id": "cadastros_horarios", "nome": "Horários de funcionamento", "acoes": ["ver", "editar", "excluir"]},
        {"id": "cadastros_bloqueios", "nome": "Bloqueios de agenda", "acoes": ["ver", "editar", "excluir"]},
        {"id": "cadastros_termos", "nome": "Termos de uso e de imagem", "acoes": ["ver", "editar", "excluir"]},
        {"id": "cadastros_modelos", "nome": "Modelos (contrato, evolução)", "acoes": ["ver", "editar", "excluir"]},
    ]},
    {"grupo": "Comunicação e integrações", "recursos": [
        {"id": "whatsapp", "nome": "WhatsApp (conexão e histórico)", "acoes": ["ver", "enviar", "configurar"]},
        {"id": "comunicacao", "nome": "Comunicados e avisos", "acoes": ["ver", "enviar"]},
        {"id": "integracoes", "nome": "Integrações (TotalPass, tokens de API)", "acoes": ["ver", "editar"]},
    ]},
    {"grupo": "Administração", "recursos": [
        {"id": "configuracoes", "nome": "Configurações (identidade, e-mail, IA)", "acoes": ["ver", "editar"]},
        {"id": "usuarios", "nome": "Usuários", "acoes": ["ver", "editar"]},
        {"id": "perfis", "nome": "Perfis de acesso", "acoes": ["ver", "editar"]},
        {"id": "auditoria", "nome": "Auditoria", "acoes": ["ver"]},
    ]},
]

TODAS = {f"{r['id']}.{a}" for g in CATALOGO for r in g["recursos"] for a in r["acoes"]}


def _todas_de(*prefixos: str, acoes: tuple[str, ...] | None = None) -> set[str]:
    """Permissões dos recursos cujo id é um dos `prefixos` (ou começa por `prefixo_`)."""
    out = set()
    for p in TODAS:
        rec, acao = p.split(".")
        if any(rec == x or rec.startswith(x + "_") for x in prefixos) and (acoes is None or acao in acoes):
            out.add(p)
    return out


_SECRETARIA = (
    {"painel.ver", "ia.usar", "agenda.ver", "agenda.editar", "aulas.ver", "aulas.operar", "aulas.evoluir", "aulas.avaliar",
     "alunos.ver", "alunos.editar", "contratos.ver", "contratos.editar", "contratos.enviar", "planos.ver",
     "financeiro_receber.ver", "financeiro_receber.baixar", "whatsapp.ver", "whatsapp.enviar", "comunicacao.ver", "comunicacao.enviar"}
    | _todas_de("cadastros", acoes=("ver",))
    # decisão do Jefferson (25/10/2026): a Secretária também edita horários, bloqueios, termos e modelos
    | {"cadastros_horarios.editar", "cadastros_bloqueios.editar", "cadastros_termos.editar", "cadastros_modelos.editar"}
)

# Perfis criados de saída (decisão do Jefferson: só três; outros se criam pela matriz de permissões).
# "Full" é o administrador (não excluível). Escopo da Secretária = SUPOSIÇÃO a confirmar com o Jefferson.
PERFIS_PADRAO: list[dict] = [
    {"nome": "Full", "descricao": "Acesso total a tudo, inclusive configurações, usuários e perfis.", "cor": "#6B1F3A",
     "administrador": True, "sistema": True, "somente_proprias_aulas": False, "permissoes": []},
    {"nome": "Professor", "descricao": "Vê só as próprias aulas: agenda/painel, evolução e avaliação. Sem financeiro, contratos, cadastros ou configurações.",
     "cor": "#2F7D6D", "administrador": False, "sistema": False, "somente_proprias_aulas": True,
     "permissoes": sorted({"painel.ver", "agenda.ver", "aulas.ver", "aulas.evoluir", "aulas.avaliar"})},
    {"nome": "Secretária", "descricao": "Opera o estúdio: aulas de todos os professores, alunos, contratos, recebimentos, horários, bloqueios e modelos. Sem contas a pagar, caixa, DRE e administração.",
     "cor": "#B4536F", "administrador": False, "sistema": False, "somente_proprias_aulas": False,
     "permissoes": sorted(_SECRETARIA)},
]

# ------------------------------------------------------------------------------------------------- rota -> permissão
LIVRE = None  # basta estar logado (a própria conta, dados que todo usuário vê)
A = "/api"

# Rotas SEM login (cada uma é aceita de propósito). (método ou "*", regex do caminho completo).
PUBLICAS: list[tuple[str, str]] = [
    ("GET", r"/api/health$"),
    ("POST", r"/api/auth/(login|refresh|forgot|reset|forgot-codigo|reset-codigo)$"),
    ("GET", r"/api/public/(identidade|logo)$"),
    # admin MayaFit (app/modules/admin_mayacorp): planos e cadastro do site, aprovação pelo link assinado do e-mail,
    # webhook do Mercado Pago (assinatura secreta). Todas com limite por IP.
    ("GET", r"/api/public/(planos|solicitacao)$"),
    ("POST", r"/api/public/(cadastro|mercadopago|solicitacao/aprovar|solicitacao/recusar)$"),
    ("GET", r"/api/arquivos-publicos/[^/]+$"),  # link assinado com prazo
    ("*", r"/api/(docs|openapi\.json|redoc).*"),  # só existem com DEBUG (ver main.py)
]

# Rotas com autenticação PRÓPRIA (chave de API, token de webhook, sessão do aluno). Não usam o login dos usuários,
# mas cada rota declarada nestes prefixos precisa ter ao menos uma dependência de autenticação (verificado em teste).
PUBLICAS_AUTENTICACAO_PROPRIA: list[str] = [r"/api/integracao/", r"/api/aluno-app/", r"/api/webhooks/"]

# (métodos, regex do caminho, permissão). A primeira regra que casa vale.
#   "recurso.acao"  -> exata
#   "recurso.*"     -> pela ação do método: GET=ver, DELETE=excluir, demais=editar
#   "recurso.*e"    -> GET=ver, demais (inclusive DELETE)=editar
# Os prefixos dos módulos de negócio abaixo são o PADRÃO planejado; cada módulo refina com `adicionar_regras`.
_REGRAS: list[tuple[str, str, str | None]] = [
    ("POST", r"/auth/usuarios/\d+/foto$", "usuarios.editar"),
    ("DELETE", r"/auth/usuarios/\d+/foto$", "usuarios.editar"),
    ("*", r"/auth/", LIVRE),
    ("GET", r"/config/identidade$", LIVRE),
    ("*", r"/config/identidade", "configuracoes.*e"),
    ("*", r"/config/(email|ia)", "configuracoes.*e"),
    ("*", r"/config/perfis", "perfis.*e"),
    ("*", r"/config/usuarios", "usuarios.*e"),
    ("*", r"/auditoria", "auditoria.ver"),
    ("GET", r"/arquivos/", LIVRE),  # a categoria do arquivo é checada na própria rota (core/storage.py)
    # --- módulos de negócio (padrão planejado) ---
    ("GET", r"/painel(/|$)", "painel.ver"),
    ("*", r"/ia(/|$)", "ia.usar"),
    ("*", r"/alunos", "alunos.*"),
    ("GET", r"/agenda", "agenda.ver"),
    ("*", r"/agenda", "agenda.*e"),
    ("*", r"/aulas/\d+/evolucao", "aulas.evoluir"),
    ("*", r"/aulas/\d+/avaliacao", "aulas.avaliar"),
    ("GET", r"/aulas", "aulas.ver"),
    ("*", r"/aulas", "aulas.operar"),
    ("*", r"/contratos/\d+/enviar", "contratos.enviar"),
    ("*", r"/contratos", "contratos.*"),
    ("*", r"/planos", "planos.*"),
    ("*", r"/financeiro/receber/\d+/baixa", "financeiro_receber.baixar"),
    ("*", r"/financeiro/receber", "financeiro_receber.*"),
    ("*", r"/financeiro/pagar/\d+/(pagar|reabrir)", "financeiro_pagar.pagar"),
    ("*", r"/financeiro/pagar", "financeiro_pagar.*"),
    ("GET", r"/financeiro/caixa", "financeiro_caixa.ver"),
    ("GET", r"/financeiro/dre", "financeiro_dre.ver"),
    ("*", r"/financeiro/bancos", "financeiro_bancos.*"),
    ("GET", r"/receita-saude", "receita_saude.ver"),
    ("*", r"/receita-saude", "receita_saude.gerar"),
    ("*", r"/comissoes", "comissoes.*e"),
    ("*", r"/cadastros/unidades", "cadastros_unidades.*"),
    ("*", r"/cadastros/servicos", "cadastros_servicos.*"),
    ("*", r"/cadastros/profissionais", "cadastros_profissionais.*"),
    ("*", r"/cadastros/fornecedores", "cadastros_fornecedores.*"),
    ("*", r"/cadastros/categorias", "cadastros_categorias.*"),
    ("*", r"/cadastros/horarios", "cadastros_horarios.*"),
    ("*", r"/cadastros/bloqueios", "cadastros_bloqueios.*"),
    ("*", r"/cadastros/termos", "cadastros_termos.*"),
    ("*", r"/cadastros/modelos", "cadastros_modelos.*"),
    ("GET", r"/whatsapp", "whatsapp.ver"),
    ("*", r"/whatsapp/(sessao|configuracao)", "whatsapp.configurar"),
    ("*", r"/whatsapp", "whatsapp.enviar"),
    ("GET", r"/comunicacao", "comunicacao.ver"),
    ("*", r"/comunicacao", "comunicacao.enviar"),
    ("*", r"/integracoes", "integracoes.*e"),
]


def _compilar(rx: str) -> re.Pattern:
    """Prefixo /api + regex; sem '$' nem '/' no fim, exige fronteira (/cadastros/unidades não casa /cadastros/unidades-x)."""
    fim = "" if rx.endswith(("$", "/", ")", "*")) else r"(?![A-Za-z0-9_-])"
    return re.compile(A + rx + fim)


_COMPILADAS: list[tuple[str, re.Pattern, str | None]] = [(m, _compilar(rx), p) for m, rx, p in _REGRAS]
_PUBLICAS_C = [(m, re.compile(rx)) for m, rx in PUBLICAS]
_PROPRIA_C = [re.compile(rx) for rx in PUBLICAS_AUTENTICACAO_PROPRIA]


def adicionar_regras(regras: list[tuple[str, str, str | None]], *, antes: bool = True) -> None:
    """Módulos novos registram suas rotas aqui (o regex NÃO leva o prefixo /api). Por padrão entram antes das demais."""
    novas = [(m, _compilar(rx), p) for m, rx, p in regras]
    if antes:
        _COMPILADAS[:0] = novas
    else:
        _COMPILADAS.extend(novas)


def _acao_por_metodo(metodo: str, so_editar: bool) -> str:
    if metodo in ("GET", "HEAD", "OPTIONS"):
        return "ver"
    if metodo == "DELETE" and not so_editar:
        return "excluir"
    return "editar"


def permissao_da_rota(metodo: str, caminho: str) -> tuple[bool, str | None]:
    """(mapeada?, permissão exigida). Permissão None = livre para quem está logado. Não mapeada = negar."""
    for m, rx, p in _COMPILADAS:
        if (m == "*" or m == metodo) and rx.match(caminho):
            if p is None:
                return True, None
            rec, acao = p.split(".")
            if acao in ("*", "*e"):
                acao = _acao_por_metodo(metodo, acao == "*e")
            return True, f"{rec}.{acao}"
    return False, None


def rota_publica(metodo: str, caminho: str) -> bool:
    return any((m == "*" or m == metodo) and rx.match(caminho) for m, rx in _PUBLICAS_C)


def rota_autenticacao_propria(caminho: str) -> bool:
    return any(rx.match(caminho) for rx in _PROPRIA_C)


def normalizar(permissoes: list[str]) -> list[str]:
    """Só permissões conhecidas; quem pode editar/excluir/etc. também pode ver (quando o recurso tem 'ver')."""
    ok = {p for p in permissoes if p in TODAS}
    ok |= {f"{p.split('.')[0]}.ver" for p in ok if f"{p.split('.')[0]}.ver" in TODAS}
    return sorted(ok)
