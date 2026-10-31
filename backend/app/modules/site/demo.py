"""Dados de demonstração do site (sintéticos). Idempotente: chamar várias vezes não duplica nem sobrescreve um site
que o estúdio já editou e publicou.

    from app.modules.site.demo import popular_demo
    popular_demo(db)   # faz commit
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.db import agora
from app.modules.site import schemas as sc
from app.modules.site import servico
from app.modules.site.models import SiteConfig

_BIOS = [
    ("Fisioterapeuta e instrutora de Pilates", "Especialista em Pilates clínico e reabilitação de coluna. Acredita que todo corpo pode se mover melhor."),
    ("Educador físico", "Treino funcional e condicionamento. Aulas animadas, seguras e com foco em resultado."),
    ("Instrutora de Pilates", "Formação completa em Pilates solo e aparelhos. Atenção a cada detalhe do movimento."),
]

_DEPOIMENTOS = [
    {"nome": "Marina S.", "texto": "Em três meses minhas dores nas costas sumiram. O cuidado de cada professor faz toda a diferença.", "detalhe": "Aluna há 2 anos"},
    {"nome": "Ricardo P.", "texto": "Ambiente acolhedor, turmas pequenas e horários que cabem na minha rotina. Recomendo demais!", "detalhe": "Aluno há 8 meses"},
    {"nome": "Lúcia M.", "texto": "Comecei aos 62 anos e hoje tenho mais disposição do que aos 40. Virou meu momento favorito da semana.", "detalhe": "Aluna há 1 ano"},
]

_FAQ_EXTRA = [
    {"pergunta": "Vocês atendem quem tem lesão?",
     "resposta": "Sim. Fazemos uma avaliação antes de começar e adaptamos os exercícios ao seu caso, com acompanhamento de fisioterapeuta."},
    {"pergunta": "Posso remarcar uma aula?",
     "resposta": "Pode. Desmarcando com antecedência pelo app, você pede reposição e a equipe encaixa você em outro horário."},
]


def popular_demo(db: Session) -> SiteConfig:
    cfg = servico.obter_config(db)
    if cfg.publicado_em is not None:  # já publicado alguma vez (demo ou estúdio): não mexe
        db.commit()
        return cfg
    c = servico.conteudo_de(cfg)
    nome = servico.identidade_site(db).nome
    c.hero.titulo = "Seu corpo em equilíbrio, sua mente em movimento."
    c.hero.subtitulo = f"Pilates e funcional em turmas reduzidas, com professores que conhecem você pelo nome. Venha conhecer o {nome}."
    c.sobre.texto = (
        "Nascemos do desejo de criar um espaço onde cada aluno é visto de verdade. Nossas aulas combinam técnica, "
        "respeito aos limites de cada corpo e uma energia leve, que faz você querer voltar.\n\n"
        "Aqui você encontra acompanhamento individual, equipamentos completos e uma equipe apaixonada por movimento."
    )
    c.sobre.destaques = ["Até 4 alunos por turma", "Avaliação postural", "Aula experimental", "Estacionamento"]
    descricoes = ["Fortalecimento, postura e consciência corporal nos aparelhos.",
                  "Força, resistência e agilidade com exercícios do dia a dia.",
                  "Alongamento, respiração e relaxamento para equilibrar corpo e mente."]
    for i, item in enumerate(c.modalidades.itens):
        if not item.descricao:
            item.descricao = descricoes[i % len(descricoes)]
    for i, item in enumerate(c.equipe.itens[:3]):
        item.mostrar = True
        item.cargo, item.bio = _BIOS[i % len(_BIOS)]
    c.depoimentos.itens = [sc.Depoimento(**d) for d in _DEPOIMENTOS]
    c.faq.itens = c.faq.itens + [sc.Pergunta(**p) for p in _FAQ_EXTRA]
    c.localizacao.endereco = "Av. Paulista, 1000 - Bela Vista, São Paulo - SP"
    c.localizacao.horario_texto = "Segunda a sexta, 6h às 21h · Sábado, 8h às 12h"
    c.contato.whatsapp = "(11) 99999-0000"
    c.contato.email = "contato@exemplo.com"
    c.contato.instagram = "@estudio.exemplo"
    c.seo.cidade, c.seo.estado = "São Paulo", "SP"
    c.privacidade.responsavel = nome
    c.privacidade.email = "privacidade@exemplo.com"
    for s in c.secoes:
        if s.tipo in ("depoimentos",):
            s.ativa = True
    cfg.conteudo = c.model_dump(mode="json")
    cfg.conteudo_publicado = cfg.conteudo
    cfg.tema_publicado = cfg.tema
    cfg.publicado = True
    cfg.publicado_em = agora()
    db.commit()
    return cfg
