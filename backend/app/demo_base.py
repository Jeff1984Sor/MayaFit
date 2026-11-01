"""Dados de BASE da demonstração (só dados sintéticos): cadastros, alunos, contratos, agenda e financeiro de um estúdio.

    from app.demo_base import popular_base
    popular_base(db, perfil="pilates", alunos=90)      # Studio Alfa Pilates: 2 unidades, turmas de até 4
    popular_base(db, perfil="funcional", alunos=60)    # Beta Funcional: 1 unidade, turmas grandes

Tudo passa pelos SERVIÇOS dos módulos (cadastros, alunos, contratos, agenda, financeiro, reposições, comunicação), então
preço, parcelas, capacidade, status, assinatura e comissão saem pelas mesmas regras das telas. Período: aulas e
recebimentos dos últimos ~75 dias e das próximas 2 semanas (os gráficos e KPIs do painel ganham tendência).

- Determinístico: `random.Random` com semente (a mesma semente + o mesmo `hoje` geram os mesmos dados).
- Idempotente: cadastros são achados pelo nome; se já há alunos de demonstração (e-mail `@demo.exemplo.com`), o resto
  não é refeito.
- Só dado inventado: nomes brasileiros combinados ao acaso, CPFs gerados (dígitos válidos), telefones da faixa
  (11) 90xxx-xxxx e e-mails `@demo.exemplo.com`.
"""

from __future__ import annotations

import base64
import logging
import random
import struct
import unicodedata
import zlib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import perfis, storage
from app.core.db import agora as agora_utc
from app.core.deps import Contexto
from app.core.models import PerfilAcesso, Usuario
from app.domain import agenda as dom_agenda
from app.domain.financeiro import hoje_de_negocio
from app.domain.status_aula import FUSO_NEGOCIO, momento_da_sessao

log = logging.getLogger("demo.base")

MARCA_EMAIL = "@demo.exemplo.com"
DIAS_HISTORICO = 75
DIAS_FUTURO = 14
IP_DEMO = "127.0.0.1"

# ------------------------------------------------------------------------------------------------------------ perfis
# Horário: (dias da semana, início, fim, serviços pelo nome; vazio = todos). Profissionais: (nome, comissão %, crefito,
# unidades em que dá aula, ativo). Planos: (nome, serviço, valor mensal, aulas/semana, meses, peso na escolha dos alunos).
PERFIS: dict[str, dict] = {
    "pilates": {
        "unidades": [("Unidade Centro", 4, 50), ("Unidade Jardins", 3, 50)],
        "servicos": ["Pilates", "Pilates Solo"],
        "horarios": [
            ([0, 1, 2, 3, 4], time(7), time(12), ["Pilates"]),
            ([0, 1, 2, 3, 4], time(16), time(21), ["Pilates"]),
            ([5], time(8), time(12), ["Pilates"]),
            ([0, 1, 2, 3, 4], time(12), time(13), ["Pilates Solo"]),
        ],
        "solo_so_na_primeira_unidade": True,
        "profissionais": [
            ("Carlos Lima", Decimal("30"), "123456-F", [0], True),
            ("Juliana Paiva", Decimal("35"), "234567-F", [0], True),
            ("Renato Alves", Decimal("30"), "345678-F", [0], True),
            ("Patrícia Nogueira", Decimal("40"), "456789-F", [1], True),
            ("Bruna Siqueira", Decimal("30"), "567890-F", [1], True),
            ("Sílvia Moraes", Decimal("0"), "678901-F", [0], False),
        ],
        "planos": [
            ("Pilates 1x por semana (mensal)", "Pilates", "290.00", 1, 1, 2),
            ("Pilates 2x por semana (mensal)", "Pilates", "430.00", 2, 1, 4),
            ("Pilates 2x por semana (trimestral)", "Pilates", "395.00", 2, 3, 4),
            ("Pilates 3x por semana (semestral)", "Pilates", "520.00", 3, 6, 2),
            ("Pilates 2x por semana (anual)", "Pilates", "360.00", 2, 12, 2),
            ("Pilates Solo 2x por semana (mensal)", "Pilates Solo", "260.00", 2, 1, 1),
        ],
        "plano_avulso": ("Aula avulsa de Pilates", "Pilates", "95.00"),
        "pesos_hora": {7: 3, 8: 3, 9: 2, 10: 1, 11: 1, 12: 2, 16: 1, 17: 2, 18: 4, 19: 4, 20: 2},
        "receita": ("Mensalidades", ["Pilates", "Pilates Solo", "Aulas avulsas"]),
        "feminino": 0.75,
        "despesas": [("Imobiliária Horizonte (demo)", "Aluguel", "6800.00", 5), ("Energia Paulista (demo)", "Energia elétrica", "780.00", 12),
                     ("NetFibra Internet (demo)", "Internet e telefone", "189.90", 15), ("Limpa Bem Serviços (demo)", "Limpeza", "1150.00", 20)],
        "comunicado": "Olá, {primeiro_nome}! Lembrando que no feriado de Finados (02/11) o estúdio fica fechado. "
                      "As aulas desse dia já foram desmarcadas com direito a reposição. Bom descanso!",
    },
    "funcional": {
        "unidades": [("Unidade Principal", 14, 50)],
        "servicos": ["Funcional", "HIIT"],
        "horarios": [
            ([0, 1, 2, 3, 4], time(6), time(10), ["Funcional"]),
            ([0, 1, 2, 3, 4], time(17), time(21), ["Funcional"]),
            ([5], time(8), time(11), ["Funcional"]),
            ([0, 1, 2, 3, 4], time(12), time(13), ["HIIT"]),
        ],
        "solo_so_na_primeira_unidade": False,
        "profissionais": [
            ("Ana Prado", Decimal("25"), None, [0], True),
            ("Diego Ramos", Decimal("25"), None, [0], True),
            ("Fábio Teixeira", Decimal("20"), None, [0], True),
            ("Luana Castro", Decimal("25"), None, [0], True),
        ],
        "planos": [
            ("Funcional 2x por semana (mensal)", "Funcional", "220.00", 2, 1, 3),
            ("Funcional 3x por semana (mensal)", "Funcional", "280.00", 3, 1, 4),
            ("Funcional 3x por semana (semestral)", "Funcional", "245.00", 3, 6, 3),
            ("Funcional 5x por semana (trimestral)", "Funcional", "320.00", 5, 3, 2),
            ("HIIT 2x por semana (mensal)", "HIIT", "190.00", 2, 1, 1),
        ],
        "plano_avulso": ("Diária funcional", "Funcional", "45.00"),
        "pesos_hora": {6: 6, 7: 6, 8: 2, 9: 1, 10: 1, 12: 2, 17: 2, 18: 7, 19: 7, 20: 2},
        "receita": ("Mensalidades", ["Funcional", "HIIT", "Diárias"]),
        "feminino": 0.5,
        "despesas": [("Imobiliária Horizonte (demo)", "Aluguel", "5200.00", 5), ("Energia Paulista (demo)", "Energia elétrica", "640.00", 12),
                     ("NetFibra Internet (demo)", "Internet e telefone", "149.90", 15), ("Limpa Bem Serviços (demo)", "Limpeza", "900.00", 20)],
        "comunicado": "Bom dia, {primeiro_nome}! Novidade: a partir de novembro teremos turma extra de HIIT às 12h, "
                      "de segunda a sexta. Fale com a recepção para experimentar!",
    },
}

FEMININOS = ["Ana", "Beatriz", "Camila", "Daniela", "Eduarda", "Fernanda", "Gabriela", "Helena", "Isabela", "Juliana", "Larissa",
             "Mariana", "Natália", "Olívia", "Patrícia", "Raquel", "Sabrina", "Tatiana", "Vanessa", "Yasmin", "Luana", "Cecília",
             "Lívia", "Marina", "Priscila", "Renata", "Simone", "Teresa", "Viviane", "Bianca", "Carolina", "Débora", "Elaine",
             "Flávia", "Giovana", "Heloísa", "Ingrid", "Jéssica", "Kátia", "Letícia", "Alice", "Clara", "Lúcia", "Rosana"]
MASCULINOS = ["André", "Bruno", "Caio", "Diego", "Eduardo", "Felipe", "Gustavo", "Henrique", "Igor", "João", "Leonardo", "Marcelo",
              "Nicolas", "Otávio", "Paulo", "Rafael", "Samuel", "Thiago", "Vinícius", "Wagner", "Rodrigo", "Fábio", "Lucas",
              "Mateus", "Ricardo", "Sérgio", "Daniel", "Fernando", "Gabriel", "Márcio", "Roberto", "César"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Santos", "Pereira", "Lima", "Carvalho", "Ferreira", "Rodrigues", "Almeida", "Costa",
              "Gomes", "Martins", "Araújo", "Barbosa", "Ribeiro", "Rocha", "Dias", "Moreira", "Cardoso", "Teixeira", "Correia",
              "Mendes", "Nunes", "Moura", "Cavalcanti", "Freitas", "Pinto", "Batista", "Campos", "Monteiro", "Vieira", "Ramos",
              "Duarte", "Castro", "Azevedo", "Farias", "Machado", "Lopes", "Prado", "Fonseca", "Brito", "Sales", "Queiroz"]
# leads do CRM de demonstração que viraram alunos (nome, dias desde a matrícula): a conversão aparece nos dois lados
CONVERTIDOS_CRM = [("Fernanda Alves", 12), ("Eduardo Pires", 25), ("Sofia Martins", 41)]
PROFISSOES = ["Advogada", "Engenheiro", "Professora", "Médica", "Designer", "Aposentado(a)", "Estudante", "Contador", "Arquiteta",
              "Enfermeira", "Analista de sistemas", "Empresária", "Psicóloga", "Jornalista", "Farmacêutico", "Administradora"]
ENDERECOS = [("Rua das Acácias", "Jardim Primavera", "São Paulo", "04512"), ("Avenida dos Ipês", "Vila Mariana", "São Paulo", "04101"),
             ("Rua Bem-te-vi", "Moema", "São Paulo", "04522"), ("Rua do Sol Nascente", "Pinheiros", "São Paulo", "05422"),
             ("Alameda das Palmeiras", "Cambuí", "Campinas", "13024"), ("Rua Monte Azul", "Perdizes", "São Paulo", "05014"),
             ("Travessa da Alegria", "Tatuapé", "São Paulo", "03310"), ("Rua Vale Verde", "Santana", "São Paulo", "02012")]
ESTADOS_CIVIS = ["SOLTEIRO", "CASADO", "CASADO", "DIVORCIADO", "UNIAO_ESTAVEL", "VIUVO"]
FORMAS = [("PIX", 5), ("CREDITO", 3), ("DEBITO", 1), ("DINHEIRO", 1)]
EVOLUCOES = [
    ("Evolução padrão", "Aula realizada sem intercorrências. Boa execução dos exercícios propostos; seguir progressão na próxima aula."),
    ("Foco em coluna", "Trabalho de mobilidade de coluna e fortalecimento de core. Relatou melhora da dor lombar."),
    ("Alongamento e respiração", "Ênfase em alongamento de cadeia posterior e respiração. Aluno(a) mais solto(a) ao final."),
]
TEXTOS_EVOLUCAO = [
    "Boa evolução no controle do core; aumentar carga das molas na próxima aula.",
    "Relatou leve desconforto no ombro direito; exercícios adaptados, sem dor ao final.",
    "Excelente disposição. Progressão para exercícios de equilíbrio unipodal.",
    "Trabalhamos mobilidade de quadril e alongamento de posteriores. Melhora visível da amplitude.",
    "Aula focada em respiração e estabilização escapular. Seguir com o mesmo plano.",
    "Cansaço no início (noite mal dormida); intensidade reduzida e boa resposta.",
]
FERIADOS = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]
MODELO_CONTRATO_HTML = (
    "<h3>Contrato de prestação de serviços nº {CONTRATO_NUMERO}</h3>"
    "<p><strong>Contratante:</strong> {ALUNO_NOME}, CPF {ALUNO_CPF}, residente em {ALUNO_ENDERECO}.</p>"
    "<p><strong>Plano:</strong> {PLANO_NOME} ({PLANO_AULAS_SEMANA} aula(s) por semana), na {UNIDADE_NOME}, "
    "com acompanhamento de {PROFISSIONAL_NOME}.</p>"
    "<p><strong>Vigência:</strong> {CONTRATO_INICIO} a {CONTRATO_FIM}. <strong>Parcela:</strong> {CONTRATO_VALOR_PARCELA} "
    "({CONTRATO_MODO_PAGAMENTO}). <strong>Total:</strong> {CONTRATO_VALOR_TOTAL}.</p>"
    "<p>Desmarcações com pelo menos 6 horas de antecedência dão direito a pedir reposição em até 30 dias.</p>"
    "<p>São Paulo, {DATA_HOJE}.</p>"
)
TERMO_HTML = ("<h3>Termo de autorização de uso de imagem</h3><p>Eu, {ALUNO_NOME}, CPF {ALUNO_CPF}, autorizo o estúdio a usar "
              "fotos e vídeos das aulas em que eu apareça, nas redes sociais e no site, sem fins comerciais diretos.</p>"
              "<p>{DATA_HOJE}</p>")


# --------------------------------------------------------------------------------------------------------- utilitários
def _cpf(rnd: random.Random, usados: set[str]) -> str:
    while True:
        d = [rnd.randint(0, 9) for _ in range(9)]
        if len(set(d)) == 1:
            continue
        for _ in range(2):
            s = sum(v * w for v, w in zip(d, range(len(d) + 1, 1, -1), strict=False))
            d.append((s * 10 % 11) % 10)
        cpf = "".join(map(str, d))
        if cpf not in usados:
            usados.add(cpf)
            return cpf


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _png(largura: int, altura: int, pixel) -> bytes:
    """PNG RGB mínimo (sem dependência de imagem): `pixel(x, y) -> (r, g, b)`."""
    linhas = b"".join(b"\x00" + bytes(c for x in range(largura) for c in pixel(x, y)) for y in range(altura))

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cabecalho = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cabecalho) + bloco(b"IDAT", zlib.compress(linhas, 9)) + bloco(b"IEND", b"")


def _assinatura_png(rnd: random.Random) -> str:
    """Rabisco de assinatura (data URL), diferente para cada um."""
    import math

    fase, amp, freq = rnd.uniform(0, 6.28), rnd.uniform(6, 12), rnd.uniform(0.05, 0.12)
    ys = {x: int(30 + amp * math.sin(freq * x + fase) + 4 * math.sin(0.31 * x)) for x in range(160)}

    def pixel(x, y):
        return (20, 30, 90) if abs(y - ys[x]) <= 1 and 10 <= x <= 150 else (255, 255, 255)

    return "data:image/png;base64," + base64.b64encode(_png(160, 60, pixel)).decode()


def _avatar_png(cor: tuple[int, int, int]) -> bytes:
    def pixel(x, y):
        dx, dy = x - 48, y - 40
        if dx * dx + dy * dy <= 18 * 18:
            return (250, 240, 230)
        if y > 64 and abs(dx) < 34 - (96 - y) // 3:
            return (250, 240, 230)
        return cor

    return _png(96, 96, pixel)


def _escolher(rnd: random.Random, pares: list[tuple]):
    return rnd.choices([p[0] for p in pares], [p[1] for p in pares])[0]


def _agora_ref(hoje: date | None) -> datetime:
    """`agora` da geração: o relógio real, ou meio-dia (Brasília) do `hoje` informado."""
    if hoje is None:
        return agora_utc()
    return datetime.combine(hoje, time(12)).replace(tzinfo=FUSO_NEGOCIO).astimezone(UTC)


def _operador(db: Session) -> Usuario:
    """Quem "opera" a demonstração (auditoria): o primeiro administrador que não é o Suporte; sem nenhum, um usuário
    sem acesso ao sistema só para assinar a auditoria."""
    adm = select(PerfilAcesso.id).where(PerfilAcesso.administrador.is_(True))
    u = db.scalar(select(Usuario).where(Usuario.perfil_acesso_id.in_(adm), Usuario.ativo.is_(True))
                  .order_by(Usuario.suporte, Usuario.id))
    if u is not None:
        return u
    full = perfis.garantir_padrao(db)["Full"]
    u = Usuario(nome="Demonstração", email=f"demonstracao{MARCA_EMAIL}", login="demonstracao", perfil_acesso_id=full.id,
                senha_hash=None, acesso_sistema=False)
    db.add(u)
    db.commit()
    return u


@dataclass
class _Base:
    """Cadastros de um estúdio já resolvidos (ids)."""

    unidades: list[int] = field(default_factory=list)
    capacidades: dict[int, int] = field(default_factory=dict)
    servicos: dict[str, int] = field(default_factory=dict)
    profs_por_unidade: dict[int, list[int]] = field(default_factory=dict)
    planos: list[tuple[int, str, int, int, int]] = field(default_factory=list)  # (id, serviço, aulas/semana, meses, peso)
    profissoes: list[int] = field(default_factory=list)
    termo_id: int | None = None
    modelos_evolucao: list[int] = field(default_factory=list)
    conta_banco: int | None = None
    conta_caixa: int | None = None
    categorias: dict[str, int] = field(default_factory=dict)
    subcategorias: dict[str, int] = field(default_factory=dict)
    fornecedores: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------------------- cadastros
def _cadastros(ctx: Contexto, cfg: dict, n_unidades: int) -> _Base:
    from app.modules.cadastros import (
        categorias,
        fornecedores,
        modelos_documentos,
        profissoes,
        servicos,
        termos,
        unidades,
    )
    from app.modules.cadastros import horarios as cad_horarios
    from app.modules.cadastros import planos as cad_planos
    from app.modules.cadastros import profissionais as cad_prof
    from app.modules.cadastros.models import (
        Categoria,
        Fornecedor,
        HorarioFuncionamento,
        HorarioStudio,
        ModeloContrato,
        ModeloEvolucao,
        Plano,
        Profissao,
        Profissional,
        Subcategoria,
        TermoUso,
        TipoCategoria,
        TipoServico,
        Unidade,
    )
    from app.modules.financeiro import rotas_bancos
    from app.modules.financeiro.models import ContaBancaria
    from app.modules.financeiro.schemas import ContaBancariaIn

    db = ctx.db
    b = _Base()

    def achar(modelo, coluna, valor):
        return db.scalar(select(modelo.id).where(coluna == valor).limit(1))

    for nome, cap, dur in cfg["unidades"][:n_unidades]:
        uid = achar(Unidade, Unidade.nome, nome) or unidades.criar(
            unidades.UnidadeIn(nome=nome, capacidade=cap, duracao_aula_minutos=dur), ctx).id
        b.unidades.append(uid)
        b.capacidades[uid] = db.get(Unidade, uid).capacidade
    for nome in cfg["servicos"]:
        b.servicos[nome] = achar(TipoServico, TipoServico.nome, nome) or servicos.criar(servicos.ServicoIn(nome=nome), ctx).id
    for nome in PROFISSOES:
        b.profissoes.append(achar(Profissao, Profissao.nome, nome) or profissoes.criar(profissoes.ProfissaoIn(nome=nome), ctx).id)

    # categorias financeiras, fornecedores e contas bancárias
    rec_nome, rec_subs = cfg["receita"]
    grupos = [(rec_nome, TipoCategoria.RECEITA, rec_subs + ["Taxas e produtos"]),
              ("Despesas fixas", TipoCategoria.DESPESA, ["Aluguel", "Energia elétrica", "Internet e telefone", "Limpeza"]),
              ("Pessoal", TipoCategoria.DESPESA, ["Salários", "Comissões"]),
              ("Manutenção", TipoCategoria.DESPESA, ["Equipamentos", "Reformas"]),
              ("Marketing", TipoCategoria.DESPESA, ["Anúncios", "Material gráfico"])]
    for nome, tipo, subs in grupos:
        cid = achar(Categoria, Categoria.nome, nome) or categorias.criar(categorias.CategoriaIn(nome=nome, tipo=tipo), ctx).id
        b.categorias[nome] = cid
        for s in subs:
            sid = db.scalar(select(Subcategoria.id).where(Subcategoria.categoria_id == cid, Subcategoria.nome == s))
            b.subcategorias[s] = sid or categorias.criar_subcategoria(categorias.SubcategoriaIn(categoria_id=cid, nome=s), ctx).id
    forn = [f for f, _, _, _ in cfg["despesas"]] + ["Equipa Fitness Manutenção (demo)", "Agência Movimento Digital (demo)"]
    for nome in forn:
        b.fornecedores[nome] = achar(Fornecedor, Fornecedor.nome, nome) or fornecedores.criar(fornecedores.FornecedorIn(nome=nome), ctx).id
    b.conta_banco = achar(ContaBancaria, ContaBancaria.banco, "Banco Exemplo S.A.") or rotas_bancos.criar_conta(
        ContaBancariaIn(banco="Banco Exemplo S.A.", agencia="0001", conta="12345-6", saldo_inicial=Decimal("15000.00")), ctx).id
    b.conta_caixa = achar(ContaBancaria, ContaBancaria.banco, "Caixa da recepção") or rotas_bancos.criar_conta(
        ContaBancariaIn(banco="Caixa da recepção", agencia="-", conta="caixa", saldo_inicial=Decimal("500.00")), ctx).id

    # modelos de texto
    mc = achar(ModeloContrato, ModeloContrato.nome, "Contrato padrão de prestação de serviços") or modelos_documentos.criar_contrato(
        modelos_documentos.ModeloContratoIn(nome="Contrato padrão de prestação de serviços", conteudo_html=MODELO_CONTRATO_HTML), ctx).id
    for titulo, texto in EVOLUCOES:
        b.modelos_evolucao.append(achar(ModeloEvolucao, ModeloEvolucao.titulo, titulo) or modelos_documentos.criar_evolucao(
            modelos_documentos.ModeloEvolucaoIn(titulo=titulo, texto=texto), ctx).id)
    b.termo_id = achar(TermoUso, TermoUso.nome, "Uso de imagem") or termos.criar(
        termos.TermoIn(nome="Uso de imagem", conteudo_html=TERMO_HTML), ctx).id

    # profissionais (com e sem vínculo de usuário; um inativo)
    prof_ids: dict[str, int] = {}
    for nome, comissao, crefito, unids, ativo in cfg["profissionais"]:
        pid = achar(Profissional, Profissional.nome, nome)
        if pid is None:
            email = f"{_sem_acento(nome).replace(' ', '.')}{MARCA_EMAIL}"
            pid = cad_prof.criar(cad_prof.ProfissionalIn(
                nome=nome, email=email, celular=f"(11) 9{8100 + len(prof_ids):04d}-{1000 + 37 * len(prof_ids):04d}", crefito=crefito,
                comissao_percentual=comissao, ativo=ativo), ctx).id
        prof_ids[nome] = pid
        if ativo:
            for i in unids:
                if i < len(b.unidades):
                    b.profs_por_unidade.setdefault(b.unidades[i], []).append(pid)
    for uid in b.unidades:  # unidade sem professor próprio (perfil reduzido): usa os da primeira
        b.profs_por_unidade.setdefault(uid, b.profs_por_unidade[b.unidades[0]])
    _vincular_professores(db, prof_ids)

    # planos
    cat_rec = b.categorias[rec_nome]
    for nome, serv, valor, aulas, meses, peso in cfg["planos"]:
        pid = achar(Plano, Plano.nome, nome) or cad_planos.criar(cad_planos.PlanoIn(
            nome=nome, tipo_servico_id=b.servicos[serv], valor=Decimal(valor), aulas_por_semana=aulas, duracao_meses=meses,
            categoria_receita_id=cat_rec, subcategoria_receita_id=b.subcategorias.get(serv), modelo_contrato_id=mc), ctx).id
        b.planos.append((pid, serv, aulas, meses, peso))
    nome, serv, valor = cfg["plano_avulso"]
    if not achar(Plano, Plano.nome, nome):
        cad_planos.criar(cad_planos.PlanoIn(nome=nome, tipo_servico_id=b.servicos[serv], valor=Decimal(valor), aulas_por_semana=1,
                                            is_avulso=True, categoria_receita_id=cat_rec,
                                            subcategoria_receita_id=b.subcategorias.get(rec_subs[-1])), ctx)

    # horários de funcionamento e grade fixa (um professor de referência por horário)
    if not db.scalar(select(func.count()).select_from(HorarioFuncionamento)):
        for k, uid in enumerate(b.unidades):
            for dias, ini, fim, servs in cfg["horarios"]:
                if k > 0 and cfg["solo_so_na_primeira_unidade"] and servs == [cfg["servicos"][1]]:
                    continue
                cad_horarios.gerar_funcionamento(cad_horarios.GerarFuncionamentoIn(
                    unidade_id=uid, dias_semana=dias, hora_inicio=ini, hora_fim=fim,
                    tipos_servico_ids=[b.servicos[s] for s in servs]), ctx)
    if not db.scalar(select(func.count()).select_from(HorarioStudio)):
        for k, uid in enumerate(b.unidades):
            profs = b.profs_por_unidade[uid]
            for dias, ini, fim, servs in cfg["horarios"]:
                if k > 0 and cfg["solo_so_na_primeira_unidade"] and servs == [cfg["servicos"][1]]:
                    continue
                for dia in dias:
                    prof = _designado(profs, dia, ini.hour)
                    cad_horarios.gerar_studio(cad_horarios.GerarStudioIn(
                        unidade_id=uid, tipo_servico_id=b.servicos[servs[0]], profissional_id=prof, dias_semana=[dia],
                        hora_inicio=ini, hora_fim=fim, intervalo_minutos=60, capacidade=b.capacidades[uid]), ctx)
    return b


def _designado(profs: list[int], dia: int, hora: int) -> int:
    """Professor de referência de um horário (grade fixa): alterna por dia e por turno."""
    turno = 0 if hora < 12 else (1 if hora < 16 else 2)
    return profs[(dia + 2 * turno) % len(profs)]


def _vincular_professores(db: Session, prof_ids: dict[str, int]) -> None:
    """Usuário de perfil Professor com o mesmo nome de um profissional: liga os dois (escopo "só as próprias aulas") e
    dá uma foto ao primeiro (os outros ficam sem foto)."""
    from app.modules.cadastros.models import Profissional

    professor = db.scalar(select(PerfilAcesso.id).where(PerfilAcesso.nome == "Professor"))
    if professor is None:
        return
    com_foto = False
    for u in db.scalars(select(Usuario).where(Usuario.perfil_acesso_id == professor).order_by(Usuario.id)):
        pid = prof_ids.get(u.nome)
        p = db.get(Profissional, pid) if pid else None
        if p is None or p.usuario_id is not None:
            continue
        if db.scalar(select(Profissional.id).where(Profissional.usuario_id == u.id)):
            continue
        p.usuario_id = u.id
        p.email = u.email
        if not com_foto and not u.foto_path:
            u.foto_path = storage.salvar("usuarios", "foto.png", _avatar_png((124, 143, 255)), nome_base=f"usuario_{u.id}", substituir=True)
            com_foto = True
    db.commit()


# ------------------------------------------------------------------------------------------------------------- alunos
@dataclass
class _Plano:
    """Plano de vida de um aluno na demonstração."""

    tipo: str  # "ativo" | "inativo" | "novo" (sem contrato) | "convertido"
    unidade_id: int
    plano: tuple[int, str, int, int, int] | None = None
    inicio: date | None = None
    fim_inativo: date | None = None
    inadimplente: bool = False
    forma: str = "PIX"


def _criar_alunos(ctx: Contexto, rnd: random.Random, cfg: dict, b: _Base, n: int, hoje: date) -> list[tuple[int, _Plano]]:
    from app.modules.alunos import schemas as asc
    from app.modules.alunos import servico as alunos_srv

    db = ctx.db
    usados_cpf: set[str] = set()
    usados_nome: set[str] = set()
    usados_tel: set[str] = set()
    # quem faz aniversário nesta semana (índices sorteados)
    aniversariantes = set(rnd.sample(range(n), k=min(5, n)))
    saida: list[tuple[int, _Plano]] = []
    convertidos = list(CONVERTIDOS_CRM) if n >= 20 else []
    for i in range(n):
        if convertidos and i >= n - len(convertidos):
            nome, dias = convertidos[n - 1 - i]
            feminino = nome.split()[0] in FEMININOS or nome.split()[0] in ("Sofia",)
        else:
            feminino = rnd.random() < cfg["feminino"]
            while True:
                nome = f"{rnd.choice(FEMININOS if feminino else MASCULINOS)} {rnd.choice(SOBRENOMES)} {rnd.choice(SOBRENOMES)}"
                if nome not in usados_nome and nome.split()[1] != nome.split()[2]:
                    break
            dias = None
        usados_nome.add(nome)
        idade = rnd.randint(19, 72)
        if i in aniversariantes:
            dia = hoje + timedelta(days=rnd.randint(0, 6))
            nasc = date(dia.year - idade, dia.month, 28 if (dia.month, dia.day) == (2, 29) else dia.day)
        else:
            nasc = date(hoje.year - idade, rnd.randint(1, 12), rnd.randint(1, 28))
            if hoje - timedelta(days=1) <= nasc.replace(year=hoje.year) <= hoje + timedelta(days=8):
                nasc = nasc.replace(month=(nasc.month % 12) + 1)  # fora da semana: só os sorteados fazem aniversário
        while True:
            tel = f"(11) 90{rnd.randint(0, 999):03d}-{rnd.randint(0, 9999):04d}"
            if tel not in usados_tel:
                usados_tel.add(tel)
                break
        rua, bairro, cidade, cep = rnd.choice(ENDERECOS)
        partes = _sem_acento(nome).split()
        dados = asc.AlunoIn(
            nome=nome, cpf=_cpf(rnd, usados_cpf), rg=f"{rnd.randint(10, 59)}.{rnd.randint(100, 999)}.{rnd.randint(100, 999)}-{rnd.randint(0, 9)}",
            email=f"{partes[0]}.{partes[-1]}{i}{MARCA_EMAIL}", data_nascimento=nasc, estado_civil=rnd.choice(ESTADOS_CIVIS),
            profissao_id=rnd.choice(b.profissoes), unidade_id=b.unidades[0] if len(b.unidades) == 1 or rnd.random() < 0.6 else b.unidades[1],
            termo_uso_id=b.termo_id, autoriza_imagem=False,
            telefones=[asc.TelefoneIn(numero=tel, principal=True)]
            + ([asc.TelefoneIn(numero=f"(11) 3{rnd.randint(100, 999)}-{rnd.randint(1000, 9999)}")] if rnd.random() < 0.2 else []),
            endereco=asc.EnderecoIn(cep=f"{cep}{rnd.randint(0, 999):03d}", logradouro=rua, numero=str(rnd.randint(10, 1999)),
                                    bairro=bairro, cidade=cidade),
        )
        a = alunos_srv.criar_aluno(ctx, dados)
        # destino do aluno
        r = rnd.random()
        plano_aluno = _Plano(tipo="ativo", unidade_id=a.unidade_id, forma=_escolher(rnd, FORMAS))
        planos_unid = [p for p in b.planos if not (cfg["solo_so_na_primeira_unidade"] and p[1] == cfg["servicos"][1]
                                                    and a.unidade_id != b.unidades[0])]
        plano_aluno.plano = rnd.choices(planos_unid, [p[4] for p in planos_unid])[0]
        if dias is not None:
            plano_aluno.tipo, plano_aluno.inicio = "convertido", hoje - timedelta(days=dias)
        elif r < 0.10:
            plano_aluno.tipo = "inativo"
            plano_aluno.fim_inativo = hoje - timedelta(days=rnd.randint(8, 55))
        elif r < 0.14:
            plano_aluno.tipo = "novo"
        else:
            plano_aluno.inadimplente = rnd.random() < 0.08
        saida.append((a.id, plano_aluno))
        # foto de alguns alunos, termo de imagem assinado de outros
        if rnd.random() < 0.15:
            cor = rnd.choice([(30, 45, 107), (26, 143, 94), (245, 166, 35), (124, 143, 255)])
            a.foto_path = storage.salvar(alunos_srv.CAT_ALUNOS, "foto.png", _avatar_png(cor), subpasta="foto", nome_base=f"aluno_{a.id}",
                                         substituir=True)
            db.commit()
        if rnd.random() < 0.45:
            alunos_srv.assinar_termo_local(ctx, a, asc.AssinaturaTermoIn(termo_id=b.termo_id, nome=a.nome, documento=a.cpf,
                                                                          assinatura=_assinatura_png(rnd)))
    return saida


# --------------------------------------------------------------------------------------------------------- contratos
def _contratos(ctx: Contexto, rnd: random.Random, b: _Base, alunos: list[tuple[int, _Plano]], hoje: date) -> list[tuple[int, int, _Plano]]:
    """Cria os contratos (com parcelas e PDF) pelas regras do módulo. Planos mensais viram uma cadeia de renovações até
    hoje. Devolve (contrato_id, aluno_id, plano do aluno) de todos os contratos criados."""
    from app.modules.contratos import schemas as csc
    from app.modules.contratos import servico as contratos

    criados: list[tuple[int, int, _Plano]] = []
    for aluno_id, pa in alunos:
        if pa.tipo == "novo":
            continue
        plano_id, _serv, _aulas, meses, _peso = pa.plano
        prof = rnd.choice(b.profs_por_unidade[pa.unidade_id])
        if pa.tipo == "inativo":
            dur = 30 * meses
            inicio = pa.fim_inativo - timedelta(days=dur - 1)
        elif pa.tipo == "convertido":
            inicio = pa.inicio
        elif meses == 1:
            inicio = hoje - timedelta(days=rnd.choice([rnd.randint(85, 140), rnd.randint(85, 140), rnd.randint(5, 80)]))
        else:
            inicio = hoje - timedelta(days=rnd.randint(5, max(6, 30 * meses - 3)))
        dados = csc.ContratoIn(aluno_id=aluno_id, plano_id=plano_id, unidade_id=pa.unidade_id, profissional_id=prof,
                               data_inicio=inicio, forma_pagamento=pa.forma)
        c = contratos.criar_contrato(ctx, dados, hoje=inicio).contrato
        criados.append((c.id, aluno_id, pa))
        fim = c.data_fim
        while pa.tipo != "inativo" and fim < hoje:  # mensal: renova até cobrir hoje
            c = contratos.renovar(ctx, c.id, csc.RenovarIn(), hoje=fim + timedelta(days=1)).contrato
            criados.append((c.id, aluno_id, pa))
            fim = c.data_fim
    return criados


def _assinar(ctx: Contexto, rnd: random.Random, contratos_ids: list[int], deixar_sem: set[int]) -> int:
    from app.modules.alunos.models import Aluno
    from app.modules.contratos import servico as contratos
    from app.modules.contratos.models import StatusAssinatura

    db = ctx.db
    n = 0
    for cid in contratos_ids:
        if cid in deixar_sem:
            continue
        c = contratos.obter(db, cid)
        if c.status_assinatura != StatusAssinatura.NAO_ASSINADO:
            continue
        a = db.get(Aluno, c.aluno_id)
        digital = rnd.random() < 0.4
        quando = datetime.combine(c.data_inicio, time(rnd.randint(9, 19), rnd.randint(0, 59))).replace(tzinfo=FUSO_NEGOCIO)
        contratos.aplicar_assinatura(db, c, nome=a.nome, documento=a.cpf, assinatura_png=_assinatura_png(rnd),
                                     ip=f"189.{rnd.randint(1, 254)}.{rnd.randint(1, 254)}.{rnd.randint(1, 254)}" if digital else IP_DEMO,
                                     status=StatusAssinatura.ASSINADO_DIGITALMENTE if digital else StatusAssinatura.ASSINADO,
                                     agora_=min(quando.astimezone(UTC), agora_utc()))
        db.commit()
        contratos.atualizar_pdf_guardado(db, c)
        db.commit()
        n += 1
    return n


# ------------------------------------------------------------------------------------------------------------ agenda
def _escolher_horarios(db: Session, rnd: random.Random, cfg: dict, b: _Base, *, unidade_id: int, servico_id: int, inicio: date,
                       fim: date, quantos: int, preferidos: list | None) -> list:
    """Escolhe `quantos` horários (dias diferentes) entre os oferecidos pela agenda (funcionamento - bloqueios - lotação),
    sempre com o professor de referência do horário. Prefere os horários de antes (renovação mantém a turma)."""
    from app.modules.agenda import servico as agenda

    slots = agenda.calcular_slots(db, unidade_id=unidade_id, tipo_servico_id=servico_id, inicio=inicio, fim=fim)
    profs = b.profs_por_unidade[unidade_id]
    opcoes = []
    for (dia, ini, fi), permitidos in slots.items():
        prof = _designado(profs, dia, ini.hour)
        if prof in permitidos:
            opcoes.append(dom_agenda.SelecaoHorario(dia_semana=dia, inicio=ini, fim=fi, profissional_id=prof))
    escolhidos = []
    if preferidos:
        validos = {(o.dia_semana, o.inicio) for o in opcoes}
        escolhidos = [p for p in preferidos if (p.dia_semana, p.inicio) in validos]
    dias_usados = {e.dia_semana for e in escolhidos}
    while len(escolhidos) < quantos:
        livres = [o for o in opcoes if o.dia_semana not in dias_usados]
        if not livres:
            break
        pesos = [cfg["pesos_hora"].get(o.inicio.hour, 1) ** 2 * (0.5 if o.dia_semana == 5 else 1) for o in livres]  # turmas cheias nos picos
        o = rnd.choices(livres, pesos)[0]
        escolhidos.append(o)
        dias_usados.add(o.dia_semana)
    return escolhidos[:quantos]


def _agenda(ctx: Contexto, rnd: random.Random, cfg: dict, b: _Base, contratos: list[tuple[int, int, _Plano]], hoje: date) -> int:
    """Reservas de cada contrato na janela [hoje-75, hoje+14] pelo serviço da agenda (capacidade atômica, bloqueios)."""
    from app.modules.agenda import servico as agenda
    from app.modules.cadastros.models import Plano
    from app.modules.contratos.models import Contrato

    db = ctx.db
    ini_janela, fim_janela = hoje - timedelta(days=DIAS_HISTORICO), hoje + timedelta(days=DIAS_FUTURO)
    preferidos: dict[int, list] = {}
    total = 0
    for cid, aluno_id, _pa in sorted(contratos, key=lambda x: x[0]):
        c = db.get(Contrato, cid)
        plano = db.get(Plano, c.plano_id)
        inicio, fim = max(c.data_inicio, ini_janela), min(c.data_fim, fim_janela)
        if inicio > fim or plano.avulso:
            continue
        rec = getattr(c.recorrencia, "value", c.recorrencia)
        por_semana = dom_agenda.aulas_por_semana_do_contrato(rec, plano.aulas_por_semana)
        escolha = _escolher_horarios(db, rnd, cfg, b, unidade_id=c.unidade_id, servico_id=plano.tipo_servico_id, inicio=inicio, fim=fim,
                                     quantos=por_semana, preferidos=preferidos.get(aluno_id))
        if len(escolha) < por_semana:
            # janela curta (renovação no fim do período) ou turma lotada: agenda o que couber
            log.info("contrato %s: %s de %s horários com vaga", cid, len(escolha), por_semana)
            if not escolha:
                continue
            por_semana = len(escolha)
        preferidos[aluno_id] = escolha
        res = agenda.gerar_agenda_do_contrato(
            db, aluno_id=aluno_id, contrato_id=cid, unidade_id=c.unidade_id, tipo_servico_id=plano.tipo_servico_id,
            data_inicio=inicio, data_fim=fim, selecoes=escolha, aulas_por_semana=por_semana, recorrencia_contrato=rec)
        db.commit()
        total += len(res.reservas_criadas)
    return total


def _feriados(ini: date, fim: date) -> list[date]:
    out = []
    for ano in {ini.year, fim.year}:
        for m, d in FERIADOS:
            dia = date(ano, m, d)
            if ini <= dia <= fim and dia.weekday() != 6:
                out.append(dia)
    return sorted(out)


def _presencas(ctx: Contexto, rnd: random.Random, b: _Base, hoje: date, agora: datetime) -> dict:
    """Aulas passadas: presença (com ou sem evolução), falta, falta avisada e desmarcação com reposição. Feriados da
    janela: aulas desmarcadas (com reposição) e bloqueio cadastrado. Próximas aulas: algumas confirmadas e duas
    desmarcadas. Reposições: pedidos pendentes, um aprovado e um recusado."""
    from app.modules.agenda import evolucao
    from app.modules.agenda import servico as agenda
    from app.modules.agenda.models import AulaSessao, Reserva, StatusReserva
    from app.modules.alunos.models import Aluno
    from app.modules.app_aluno import reposicoes
    from app.modules.app_aluno.models import ReposicaoPedido
    from app.modules.cadastros import bloqueios

    db = ctx.db
    cont = {"concluidas": 0, "faltas": 0, "desmarcadas": 0, "evolucoes": 0, "confirmadas": 0, "reposicoes_pendentes": 0}
    feriados = set(_feriados(hoje - timedelta(days=DIAS_HISTORICO), hoje + timedelta(days=DIAS_FUTURO)))
    linhas = db.execute(
        select(Reserva.id, AulaSessao.data, AulaSessao.hora_inicio, AulaSessao.hora_fim)
        .join(AulaSessao, AulaSessao.id == Reserva.aula_sessao_id)
        .where(Reserva.status == StatusReserva.RESERVADA).order_by(AulaSessao.data, AulaSessao.hora_inicio, Reserva.id)
    ).all()
    candidatas_reposicao: list[int] = []
    futuras: list[tuple[int, date]] = []
    for rid, dia, ini, fim in linhas:
        inicio_aula = momento_da_sessao(dia, ini)
        if dia in feriados:
            agenda.desmarcar_reserva(db, rid, agora=min(inicio_aula - timedelta(days=2), agora), excecao_prazo=True,
                                     motivo="Feriado: estúdio fechado")
            cont["desmarcadas"] += 1
            continue
        if momento_da_sessao(dia, fim) > agora:
            futuras.append((rid, dia))
            continue
        r = rnd.random()
        if r < 0.05:
            agenda.desmarcar_reserva(db, rid, agora=inicio_aula - timedelta(hours=rnd.randint(8, 48)))
            cont["desmarcadas"] += 1
            if dia >= hoje - timedelta(days=25):
                candidatas_reposicao.append(rid)
        elif r < 0.11:
            agenda.aplicar_acao_presenca(db, rid, "faltou")
            cont["faltas"] += 1
        elif r < 0.15:
            agenda.aplicar_acao_presenca(db, rid, "faltou_avisou")
            cont["faltas"] += 1
        elif r < 0.60 and dia >= hoje - timedelta(days=40):
            texto = rnd.choice(TEXTOS_EVOLUCAO) if rnd.random() < 0.7 else None
            evolucao.criar_registro(db, "evolucoes", rid, texto=texto, modelo_evolucao_id=rnd.choice(b.modelos_evolucao), finalizar=True)
            cont["evolucoes"] += 1
            cont["concluidas"] += 1
        elif r < 0.80:
            agenda.aplicar_acao_presenca(db, rid, "finalizar")
            cont["concluidas"] += 1
        # o resto fica RESERVADA e o job de fim de aula conclui (como no dia a dia)
    db.commit()
    cont["concluidas"] += agenda.concluir_aulas_passadas(db, agora=agora)
    db.commit()

    # próximas aulas: confirmações dos próximos 2 dias e duas desmarcações com pedido de reposição
    for rid, dia in futuras:
        if dia <= hoje + timedelta(days=4) and rnd.random() < 0.45:
            agenda.confirmar_reserva(db, rid, agora=agora)
            cont["confirmadas"] += 1
    desmarcar_futuras = [rid for rid, dia in futuras if hoje + timedelta(days=2) <= dia <= hoje + timedelta(days=9)]
    for rid in rnd.sample(desmarcar_futuras, k=min(2, len(desmarcar_futuras))):
        agenda.desmarcar_reserva(db, rid, agora=agora)
        cont["desmarcadas"] += 1
        candidatas_reposicao.append(rid)
    db.commit()

    # pedidos de reposição (o aluno pede; a gerência decide)
    prefs = ["Prefiro de manhã, se possível.", "Qualquer horário depois das 18h.", None, "Pode ser no sábado?", "Mesmo horário, outro dia."]
    pedidos: list[tuple[int, int]] = []
    for rid in rnd.sample(candidatas_reposicao, k=min(7, len(candidatas_reposicao))):
        r = db.get(Reserva, rid)
        if any(aid == r.aluno_id for aid, _ in pedidos):
            continue
        reposicoes.pedir_reposicao(db, db.get(Aluno, r.aluno_id), rid, rnd.choice(prefs), agora=agora)
        pid = db.scalar(select(ReposicaoPedido.id).where(ReposicaoPedido.reserva_origem_id == rid).order_by(ReposicaoPedido.id.desc()))
        pedidos.append((r.aluno_id, pid))
    db.commit()
    ids = [pid for _, pid in pedidos if pid]
    if ids:
        aprovado = ids[0]
        opcoes = reposicoes.opcoes_do_pedido(db, aprovado, agora=agora)
        if opcoes:
            reposicoes.aprovar(db, aprovado, opcoes[min(2, len(opcoes) - 1)]["aula_id"], ctx.usuario, agora=agora)
    if len(ids) > 1:
        reposicoes.recusar(db, ids[1], ctx.usuario, "Sem horário compatível dentro do prazo da reposição.", agora=agora)
    db.commit()
    cont["reposicoes_pendentes"] = max(len(ids) - 2, 0)

    # bloqueios: feriados (as aulas já foram desmarcadas acima) e a reunião semanal da equipe
    from app.modules.cadastros.models import BloqueioAgenda

    if not db.scalar(select(func.count()).select_from(BloqueioAgenda)):
        for uid in b.unidades:
            for dia in sorted(feriados):
                bloqueios.criar(bloqueios.BloqueioIn(unidade_id=uid, data_inicio=dia, data_fim=dia, hora_inicio=time(0), hora_fim=time(23, 59),
                                                     motivo="Feriado"), ctx)
            bloqueios.criar(bloqueios.BloqueioIn(unidade_id=uid, recorrente=True, dias_semana=[2], data_inicio=hoje - timedelta(days=90),
                                                 hora_inicio=time(14), hora_fim=time(15, 30), motivo="Reunião pedagógica da equipe"), ctx)
    return cont


# ---------------------------------------------------------------------------------------------------------- financeiro
def _financeiro(ctx: Contexto, rnd: random.Random, cfg: dict, b: _Base, contratos: list[tuple[int, int, _Plano]], hoje: date,
                agora: datetime) -> dict:
    from app.modules.financeiro import bancos, comissoes, pagar
    from app.modules.financeiro import servico as fin
    from app.modules.financeiro.models import Comissao, ContaPagar, ContaReceber, StatusPagar, TipoMovimento
    from app.modules.financeiro.schemas import ContaPagarIn

    db = ctx.db
    hoje_real = min(hoje, hoje_de_negocio(agora_utc()))
    cont = {"pagos": 0, "abertos": 0, "atrasados": 0, "contas_pagar": 0, "comissoes": 0}
    por_contrato = {cid: pa for cid, _aid, pa in contratos}
    contas = db.scalars(select(ContaReceber).where(ContaReceber.contrato_id.in_(list(por_contrato))).order_by(ContaReceber.vencimento,
                                                                                                                  ContaReceber.id)).all()
    for conta in contas:
        pa = por_contrato[conta.contrato_id]
        forma = pa.forma
        banco = b.conta_caixa if forma == "DINHEIRO" else b.conta_banco
        atraso = (conta.vencimento - hoje).days
        if conta.vencimento <= hoje:
            devendo = (pa.inadimplente and atraso >= -45) or (atraso >= -6 and rnd.random() < 0.25) or rnd.random() < 0.02
            if devendo:
                if conta.vencimento < hoje:
                    cont["atrasados"] += 1
                else:
                    cont["abertos"] += 1
                continue
            pago = conta.vencimento + timedelta(days=rnd.choice([-3, -2, -1, 0, 0, 0, 1, 2, 3, 5]))
            fin.baixar_conta_receber(db, conta, data_pagamento=min(pago, hoje_real), forma_pagamento=forma, conta_bancaria_id=banco)
            cont["pagos"] += 1
        elif atraso <= 5 and rnd.random() < 0.3:  # adiantados
            fin.baixar_conta_receber(db, conta, data_pagamento=hoje_real - timedelta(days=rnd.randint(0, 3)), forma_pagamento=forma,
                                     conta_bancaria_id=banco)
            cont["pagos"] += 1
        else:
            cont["abertos"] += 1
    db.commit()

    # lançamentos avulsos (produtos e taxas)
    aluno_ids = [aid for _cid, aid, pa in contratos if pa.tipo != "inativo"]
    for k in range(min(6, len(aluno_ids))):
        venc = hoje - timedelta(days=rnd.randint(-5, 50))
        desc, valor = rnd.choice([("Meia antiderrapante", "39.90"), ("Taxa de matrícula", "80.00"), ("Garrafa térmica", "59.90"),
                                  ("Avaliação postural", "120.00")])
        conta = fin.lancar_avulso(db, aluno_id=rnd.choice(aluno_ids), descricao=desc, valor=Decimal(valor), vencimento=venc)
        if venc <= hoje_real and k % 3 != 0:
            fin.baixar_conta_receber(db, conta, data_pagamento=venc, forma_pagamento="PIX", conta_bancaria_id=b.conta_banco)
            cont["pagos"] += 1
        elif venc < hoje:
            cont["atrasados"] += 1
        else:
            cont["abertos"] += 1
    db.commit()

    # contas a pagar: despesas fixas recorrentes (4 meses), manutenção e marketing
    if not db.scalar(select(func.count()).select_from(ContaPagar)):
        inicio_mes = (hoje.replace(day=1) - timedelta(days=75)).replace(day=1)
        for fornecedor, sub, valor, dia in cfg["despesas"]:
            pagar.criar(db, ContaPagarIn(fornecedor_id=b.fornecedores[fornecedor], categoria_id=b.categorias["Despesas fixas"],
                                         subcategoria_id=b.subcategorias[sub], descricao=sub, vencimento=inicio_mes.replace(day=dia),
                                         valor=Decimal(valor), recorrencia="MENSAL", recorrencia_quantidade=4))
        pagar.criar(db, ContaPagarIn(fornecedor_id=b.fornecedores["Equipa Fitness Manutenção (demo)"], categoria_id=b.categorias["Manutenção"],
                                     subcategoria_id=b.subcategorias["Equipamentos"], descricao="Revisão dos aparelhos e troca de molas",
                                     vencimento=hoje - timedelta(days=18), valor=Decimal("1480.00")))
        pagar.criar(db, ContaPagarIn(fornecedor_id=b.fornecedores["Agência Movimento Digital (demo)"], categoria_id=b.categorias["Marketing"],
                                     subcategoria_id=b.subcategorias["Anúncios"], descricao="Campanha de anúncios no Instagram",
                                     vencimento=hoje + timedelta(days=6), valor=Decimal("600.00"), recorrencia="MENSAL", recorrencia_quantidade=2))
        db.commit()
        energia = b.subcategorias["Energia elétrica"]
        for cp in db.scalars(select(ContaPagar).where(ContaPagar.status == StatusPagar.AGENDADO).order_by(ContaPagar.vencimento)):
            cont["contas_pagar"] += 1
            if cp.vencimento >= hoje:
                continue
            if cp.subcategoria_id == energia and cp.vencimento >= hoje - timedelta(days=25):
                continue  # a conta de luz do mês ficou atrasada
            pagar.pagar(db, cp, data_pagamento=min(cp.vencimento, hoje_real), conta_bancaria_id=b.conta_banco)
        db.commit()
        # movimentos manuais: depósito do caixa no banco e uma venda de balcão
        bancos.criar_movimento(db, conta_id=b.conta_banco, tipo=TipoMovimento.ENTRADA, valor=Decimal("350.00"),
                               data=hoje - timedelta(days=9), descricao="Venda de acessórios no balcão")
        grupo = fin.novo_grupo()
        quando = hoje - timedelta(days=4)
        bancos.criar_movimento(db, conta_id=b.conta_caixa, tipo=TipoMovimento.SAIDA, valor=Decimal("400.00"), data=quando,
                               descricao="Depósito do caixa no banco", transferencia_id=grupo)
        bancos.criar_movimento(db, conta_id=b.conta_banco, tipo=TipoMovimento.ENTRADA, valor=Decimal("400.00"), data=quando,
                               descricao="Depósito do caixa no banco", transferencia_id=grupo)
        db.commit()

    # comissões dos meses da janela (as dos meses fechados já repassadas)
    mes = (hoje - timedelta(days=DIAS_HISTORICO)).replace(day=1)
    while mes <= hoje:
        comp = f"{mes:%Y-%m}"
        res = comissoes.gerar(db, comp)
        cont["comissoes"] += len(res.comissoes)
        proximo = (mes + timedelta(days=32)).replace(day=1)
        if proximo <= hoje:
            ids = list(db.scalars(select(Comissao.id).where(Comissao.competencia == comp, Comissao.paga_em.is_(None))))
            if ids:
                comissoes.marcar_pagas(db, ids, min(proximo + timedelta(days=4), hoje_real))
        db.commit()
        mes = proximo
    return cont


# -------------------------------------------------------------------------------------------------------- comunicação
def _comunicados(ctx: Contexto, cfg: dict, hoje: date) -> int:
    """Um comunicado já enviado (histórico) e um pausado. Nada sai de verdade: o envio do histórico é simulado."""
    from app.modules.comunicacao import comunicados
    from app.modules.comunicacao.models import Comunicado, ComunicadoDestinatario

    db = ctx.db
    if db.scalar(select(func.count()).select_from(Comunicado)):
        return 0
    enviado = comunicados.criar(db, ctx.usuario.id, cfg["comunicado"], "ativos", None, pausa_segundos=5)
    quando = datetime.combine(hoje - timedelta(days=3), time(10)).replace(tzinfo=FUSO_NEGOCIO).astimezone(UTC)
    for k, d in enumerate(db.scalars(select(ComunicadoDestinatario).where(ComunicadoDestinatario.comunicado_id == enviado.id,
                                                                          ComunicadoDestinatario.status == "pendente"))):
        d.status, d.enviado_em = "enviado", quando + timedelta(seconds=6 * k)
    enviado.criado_em = quando
    enviado.ultimo_envio_em = quando
    comunicados._concluir_se_acabou(db, enviado, quando + timedelta(minutes=10))
    pausado = comunicados.criar(db, ctx.usuario.id, "Oi, {primeiro_nome}! Pesquisa rápida: o que você está achando das aulas? "
                                                    "Responda com uma nota de 0 a 10.", "ativos", None, pausa_segundos=8)
    comunicados.pausar(db, pausado)
    db.commit()
    return 2


# --------------------------------------------------------------------------------------------------------------- tudo
def popular_base(db: Session, *, perfil: str, alunos: int, hoje: date | None = None, semente: int | None = None,
                 unidades: int | None = None) -> dict:
    """Popula o estúdio da sessão `db` (um banco só ou o estúdio corrente do multi-tenant). Faz commit.

    `perfil`: "pilates" ou "funcional". `alunos`: quantos alunos criar. `semente`: muda os nomes/sorteios (padrão: a do
    perfil). `unidades`: limita as unidades do perfil. Devolve as contagens do que existe no banco ao final.
    """
    if perfil not in PERFIS:
        raise ValueError(f"perfil desconhecido: {perfil!r} (use {', '.join(PERFIS)})")
    cfg = PERFIS[perfil]
    agora = _agora_ref(hoje)
    hoje = hoje or hoje_de_negocio(agora)
    rnd = random.Random(semente if semente is not None else zlib.crc32(perfil.encode()))
    ctx = Contexto(db=db, usuario=_operador(db), ip=IP_DEMO)
    n_unid = max(1, min(unidades or len(cfg["unidades"]), len(cfg["unidades"])))
    b = _cadastros(ctx, cfg, n_unid)

    from app.modules.alunos.models import Aluno

    ja = db.scalar(select(func.count()).select_from(Aluno).where(Aluno.email.like(f"%{MARCA_EMAIL}")))
    detalhes: dict = {}
    if not ja:
        lista = _criar_alunos(ctx, rnd, cfg, b, alunos, hoje)
        contratos = _contratos(ctx, rnd, b, lista, hoje)
        # os dois contratos vigentes mais recentes ficam aguardando assinatura
        vigentes = sorted((cid for cid, _aid, pa in contratos if pa.tipo != "inativo"), reverse=True)
        _assinar(ctx, rnd, [cid for cid, _, _ in contratos], set(vigentes[:2]))
        detalhes["reservas"] = _agenda(ctx, rnd, cfg, b, contratos, hoje)
        detalhes.update(_presencas(ctx, rnd, b, hoje, agora))
        detalhes.update(_financeiro(ctx, rnd, cfg, b, contratos, hoje, agora))
        from app.modules.alunos import servico as alunos_srv
        from app.modules.alunos.models import StatusAluno

        for aid, pa in lista:
            if pa.tipo == "inativo":
                alunos_srv.mudar_status(ctx, db.get(Aluno, aid), StatusAluno.INATIVO)
        _comunicados(ctx, cfg, hoje)
    return {**contagens(db), **({"geracao": detalhes} if detalhes else {})}


def contagens(db: Session) -> dict:
    from app.modules.agenda.models import AulaSessao, Reserva
    from app.modules.alunos.models import Aluno, StatusAluno
    from app.modules.app_aluno.models import ReposicaoPedido
    from app.modules.contratos.models import Contrato
    from app.modules.financeiro.models import Comissao, ContaPagar, ContaReceber, MovimentoConta

    def n(modelo, *cond):
        return int(db.scalar(select(func.count()).select_from(modelo).where(*cond)) or 0)

    return {"alunos": n(Aluno), "alunos_ativos": n(Aluno, Aluno.status == StatusAluno.ATIVO), "contratos": n(Contrato),
            "aulas": n(AulaSessao), "reservas": n(Reserva), "contas_receber": n(ContaReceber), "contas_pagar": n(ContaPagar),
            "movimentos": n(MovimentoConta), "comissoes": n(Comissao), "reposicoes": n(ReposicaoPedido)}
