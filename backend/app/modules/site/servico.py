"""Serviço do site: configuração, publicação, montagem da página pública e contatos.

Assinaturas estáveis (outros módulos podem chamar):
    obter_config(db) -> SiteConfig
    pagina_publica(db) -> PaginaPublica | None        (None = site não publicado)
    registrar_contato(db, dados: ContatoIn) -> SiteContato | None   (None = descartado como spam)

O site NUNCA expõe dados de alunos: só cadastros do estúdio (modalidades, planos, grade fixa e profissionais que o
estúdio marcou para aparecer, pelo primeiro nome na grade).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import storage
from app.core.db import agora
from app.core.models import Identidade, Usuario
from app.modules.cadastros.models import HorarioStudio, Plano, Profissional, TipoServico, Unidade
from app.modules.site import regras
from app.modules.site import schemas as sc
from app.modules.site.models import SiteConfig, SiteContato

log = logging.getLogger(__name__)

COR_PADRAO = "#7C8FFF"  # Indigo MayaCorp (estúdio sem cor própria)
NOME_PADRAO = "Estúdio"

storage.registrar_categoria("site", "site.ver", storage.IMAGENS, 5)


class ErroSite(Exception):
    def __init__(self, mensagem: str, status: int = 400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


# --------------------------------------------------------------------------------------------------- identidade
def identidade_site(db: Session) -> sc.IdentidadeSite:
    ident = db.scalar(select(Identidade).order_by(Identidade.id))
    if not ident:
        return sc.IdentidadeSite(nome=NOME_PADRAO, cor=COR_PADRAO)
    logo = f"/public/logo?v={storage.versao(ident.logo_path)}" if storage.existe(ident.logo_path) else None
    return sc.IdentidadeSite(nome=ident.nome_exibicao or NOME_PADRAO, cor=ident.cor_destaque or COR_PADRAO, logo_url=logo)


# ------------------------------------------------------------------------------------------------------- config
def _modalidades_ativas(db: Session) -> list[TipoServico]:
    return list(db.scalars(select(TipoServico).where(TipoServico.ativo.is_(True)).order_by(TipoServico.nome)))


def _profissionais_ativos(db: Session) -> list[Profissional]:
    return list(db.scalars(select(Profissional).where(Profissional.ativo.is_(True)).order_by(Profissional.nome)))


def obter_config(db: Session) -> SiteConfig:
    """Configuração do site; na primeira vez nasce com um rascunho pronto (textos de exemplo + dados do estúdio)."""
    cfg = db.get(SiteConfig, 1)
    if cfg:
        return cfg
    nome = identidade_site(db).nome
    conteudo = regras.conteudo_padrao(
        nome,
        [(m.id, m.nome) for m in _modalidades_ativas(db)],
        [p.id for p in _profissionais_ativos(db)],
    )
    cfg = SiteConfig(id=1, tema="aurora", conteudo=sc.ConteudoSite.model_validate(conteudo).model_dump(mode="json"))
    db.add(cfg)
    db.flush()
    return cfg


def conteudo_de(cfg: SiteConfig, publicado: bool = False) -> sc.ConteudoSite:
    bruto = cfg.conteudo_publicado if publicado else cfg.conteudo
    return sc.ConteudoSite.model_validate(bruto or {})


def alteracoes_pendentes(cfg: SiteConfig) -> bool:
    if not cfg.publicado:
        return False
    return cfg.conteudo != cfg.conteudo_publicado or cfg.tema != cfg.tema_publicado


def salvar(db: Session, dados: sc.SalvarIn) -> SiteConfig:
    cfg = obter_config(db)
    _conferir_referencias(db, dados.conteudo)
    cfg.tema = dados.tema
    cfg.conteudo = dados.conteudo.model_dump(mode="json")
    return cfg


def _conferir_referencias(db: Session, c: sc.ConteudoSite) -> None:
    """Fotos citadas no conteúdo precisam existir no storage (evita link quebrado e caminho inventado)."""
    fotos = [c.hero.foto, c.sobre.foto, *(i.foto for i in c.modalidades.itens), *(i.foto for i in c.equipe.itens),
             *(f.foto for f in c.galeria.fotos)]
    for f in fotos:
        if f and not storage.existe(f):
            raise ErroSite("Uma das fotos não foi encontrada. Envie a imagem de novo.", 422)


def publicar(db: Session, usuario: Usuario) -> SiteConfig:
    cfg = obter_config(db)
    c = conteudo_de(cfg)
    if not any(s.ativa for s in c.secoes):
        raise ErroSite("Ligue pelo menos uma seção antes de publicar.", 422)
    cfg.conteudo_publicado = cfg.conteudo
    cfg.tema_publicado = cfg.tema
    cfg.publicado = True
    cfg.publicado_em = agora()
    cfg.publicado_por_id = usuario.id
    return cfg


def despublicar(db: Session) -> SiteConfig:
    cfg = obter_config(db)
    cfg.publicado = False
    return cfg


def descartar_alteracoes(db: Session) -> SiteConfig:
    cfg = obter_config(db)
    if cfg.conteudo_publicado is None:
        raise ErroSite("O site ainda não foi publicado: não há versão para restaurar.", 409)
    cfg.conteudo = cfg.conteudo_publicado
    cfg.tema = cfg.tema_publicado or cfg.tema
    return cfg


# ---------------------------------------------------------------------------------------------- dados do estúdio
def _grade(db: Session, servicos_visiveis: dict[int, str], profs_visiveis: dict[int, str], mostrar_prof: bool
           ) -> list[sc.HorarioDado]:
    """Grade fixa da semana (só leitura). Sem grade fixa cadastrada, usa as aulas dos próximos 14 dias."""
    unidades = set(db.scalars(select(Unidade.id).where(Unidade.ativo.is_(True))))
    linhas: list[tuple[int, object, object, int, int | None]] = [
        (h.dia_semana, h.hora_inicio, h.hora_fim, h.tipo_servico_id, h.profissional_id)
        for h in db.scalars(select(HorarioStudio))
        if h.unidade_id in unidades
    ]
    if not linhas:
        from app.modules.agenda.models import AulaSessao  # import tardio: agenda é opcional para o site

        hoje = date.today()
        q = select(AulaSessao.data, AulaSessao.hora_inicio, AulaSessao.hora_fim, AulaSessao.tipo_servico_id,
                   AulaSessao.profissional_id).where(AulaSessao.data >= hoje, AulaSessao.data < hoje + timedelta(days=14))
        linhas = [(d.weekday(), ini, fim, ts, pr) for d, ini, fim, ts, pr in db.execute(q)]
    vistos: dict[tuple, sc.HorarioDado] = {}
    for dia, ini, fim, ts, pr in linhas:
        if ts not in servicos_visiveis:
            continue
        prof = regras.primeiro_nome(profs_visiveis.get(pr)) if (mostrar_prof and pr) else None
        k = regras.chave_horario(dia, ini, fim, servicos_visiveis[ts], prof)
        vistos.setdefault(k, sc.HorarioDado(dia_semana=dia, hora_inicio=ini, hora_fim=fim,
                                            modalidade=servicos_visiveis[ts], professor=prof))
    return sorted(vistos.values(), key=lambda h: (h.dia_semana, h.hora_inicio, h.modalidade))


def dados_do_estudio(db: Session, c: sc.ConteudoSite, *, publico: bool) -> sc.DadosEstudio:
    """Cadastros que alimentam o site. `publico=True` filtra o que o estúdio escondeu (o editor recebe tudo para
    poder ligar/desligar cada item)."""
    servicos = _modalidades_ativas(db)
    escondidas = {i.tipo_servico_id for i in c.modalidades.itens if not i.mostrar}
    nomes_serv = {s.id: s.nome for s in servicos}
    visiveis = {s.id: s.nome for s in servicos if not publico or s.id not in escondidas}

    planos_q = select(Plano).where(Plano.ativo.is_(True)).order_by(Plano.avulso, Plano.valor, Plano.nome)
    planos = []
    for p in db.scalars(planos_q):
        if publico and (p.id in c.planos.ocultos or p.tipo_servico_id not in visiveis):
            continue
        planos.append(sc.PlanoDado(
            id=p.id, nome=p.nome, modalidade=nomes_serv.get(p.tipo_servico_id),
            valor=p.valor if (c.planos.mostrar_precos or not publico) else None,
            aulas_por_semana=p.aulas_por_semana, duracao_meses=p.duracao_meses, avulso=p.avulso,
        ))

    marcados = {i.profissional_id for i in c.equipe.itens if i.mostrar}
    profs = [p for p in _profissionais_ativos(db) if not publico or p.id in marcados]
    profs_marcados = {p.id: p.nome for p in profs if p.id in marcados}

    return sc.DadosEstudio(
        modalidades=[sc.ModalidadeDado(id=i, nome=n) for i, n in visiveis.items()],
        planos=planos,
        profissionais=[sc.ProfissionalDado(id=p.id, nome=p.nome) for p in profs],
        # no editor a grade leva o primeiro nome de todos (a prévia filtra pelos marcados enquanto se edita)
        grade=_grade(db, visiveis, profs_marcados if publico else {p.id: p.nome for p in profs},
                     c.grade.mostrar_professor or not publico),
    )


def _filtrar_conteudo_publico(c: sc.ConteudoSite, dados: sc.DadosEstudio) -> sc.ConteudoSite:
    """Tira do conteúdo público o que não deve sair (bio/foto de quem não aparece, itens de serviços inativos)."""
    ids_prof = {p.id for p in dados.profissionais}
    ids_mod = {m.id for m in dados.modalidades}
    c = c.model_copy(deep=True)
    c.equipe.itens = [i for i in c.equipe.itens if i.mostrar and i.profissional_id in ids_prof]
    c.modalidades.itens = [i for i in c.modalidades.itens if i.tipo_servico_id in ids_mod]
    c.planos.ocultos = []
    return c


def pagina_publica(db: Session) -> sc.PaginaPublica | None:
    cfg = db.get(SiteConfig, 1)
    if not cfg or not cfg.publicado or cfg.conteudo_publicado is None:
        return None
    c = conteudo_de(cfg, publicado=True)
    dados = dados_do_estudio(db, c, publico=True)
    mapa = regras.mapa_da_pagina(c.localizacao.mapa, c.localizacao.endereco)
    return sc.PaginaPublica(
        tema=cfg.tema_publicado or cfg.tema, identidade=identidade_site(db), conteudo=_filtrar_conteudo_publico(c, dados),
        dados=dados, publicado_em=cfg.publicado_em, mapa_embed=mapa.embed, mapa_link=mapa.link,
    )


# ------------------------------------------------------------------------------------------------------ endereço
def endereco(request_host: str | None) -> sc.EnderecoSite:
    """Endereço do site. Com o multi-tenant ligado, `<slug>.<domínio base>` (+ domínios próprios); senão o host atual."""
    principal, dominios = None, []
    try:  # import tardio: o módulo de tenancy é de outro agente e pode não existir nesta versão
        from app.core import tenancy  # type: ignore[attr-defined]
        from app.core.config import settings

        atual = None
        for nome in ("estudio_atual", "atual", "obter_estudio"):
            fn = getattr(tenancy, nome, None)
            if callable(fn):
                atual = fn()
                break
        base = getattr(settings, "dominio_base", None)
        slug = getattr(atual, "slug", None)
        if slug and base:
            principal = f"{slug}.{base}"
        dominios = list(getattr(atual, "dominios", None) or [])
    except Exception:  # noqa: BLE001 - qualquer falha aqui só tira o endereço da tela
        pass
    if not principal and request_host:
        principal = request_host.split(",")[0].strip()
    return sc.EnderecoSite(principal=principal, dominios=[d for d in dominios if d != principal])


# ------------------------------------------------------------------------------------------------------ contatos
def _enviar_ao_crm(db: Session, contato: SiteContato) -> None:
    """Cria o lead no CRM (se o módulo existir). Falha do CRM não perde o contato: fica registrada no histórico."""
    try:
        from app.modules.crm import servico as crm  # type: ignore[import-not-found]
    except ImportError:
        return
    try:
        lead = crm.criar_lead(
            db, nome=contato.nome, telefone=contato.telefone, email=contato.email, origem="site",
            interesse=contato.interesse, mensagem=contato.mensagem, quer_aula_experimental=contato.quer_aula_experimental,
        )
        db.flush()
        lead_id = lead if isinstance(lead, int) else getattr(lead, "id", None)
        contato.enviado_crm = True
        contato.lead_id = lead_id
        db.commit()
    except Exception as e:  # noqa: BLE001
        log.exception("site: falha ao criar lead no CRM (contato %s)", contato.id)
        db.rollback()
        contato = db.get(SiteContato, contato.id)
        if contato:
            contato.erro_crm = str(e)[:300] or e.__class__.__name__
            db.commit()


def registrar_contato(db: Session, dados: sc.ContatoIn) -> SiteContato | None:
    if regras.avaliar_spam(dados.website, dados.tempo_ms):
        log.info("site: contato descartado como spam")
        return None
    if not dados.consentimento:
        raise ErroSite("Para enviarmos o contato, marque a autorização de uso dos dados (LGPD).", 422)
    cfg = db.get(SiteConfig, 1)
    if not cfg or not cfg.publicado:
        raise ErroSite("Site não encontrado.", 404)
    contato = SiteContato(
        nome=dados.nome, telefone=dados.telefone or None, email=dados.email, interesse=dados.interesse or None,
        mensagem=dados.mensagem or None, quer_aula_experimental=dados.quer_aula_experimental,
        consentimento_em=agora(), consentimento_texto=regras.TEXTO_CONSENTIMENTO,
    )
    db.add(contato)
    db.commit()  # o contato fica guardado antes de qualquer tentativa no CRM
    _enviar_ao_crm(db, contato)
    return contato


def listar_contatos(db: Session, pagina: int, por_pagina: int) -> sc.ListaContatos:
    total = db.scalar(select(func.count()).select_from(SiteContato)) or 0
    nao_lidos = db.scalar(select(func.count()).select_from(SiteContato).where(SiteContato.lido.is_(False))) or 0
    itens = db.scalars(select(SiteContato).order_by(SiteContato.id.desc()).offset((pagina - 1) * por_pagina)
                       .limit(por_pagina))
    return sc.ListaContatos(itens=[sc.ContatoOut.model_validate(i) for i in itens], total=total, nao_lidos=nao_lidos)


def contar_nao_lidos(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(SiteContato).where(SiteContato.lido.is_(False))) or 0
