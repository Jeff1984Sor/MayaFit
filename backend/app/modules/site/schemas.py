"""Esquemas do site: conteúdo editável (validado), página montada (pública/prévia) e contato."""

from __future__ import annotations

import re
from datetime import datetime, time
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.modules.site import regras

TEMAS = ("aurora", "zen", "energia")
Tema = Literal["aurora", "zen", "energia"]
TipoSecao = Literal[
    "hero", "sobre", "modalidades", "planos", "grade", "equipe", "depoimentos", "galeria", "faq", "localizacao", "contato"
]
TIPOS_SECAO: tuple[str, ...] = TipoSecao.__args__  # type: ignore[attr-defined]

Txt = lambda n: Annotated[str, Field(max_length=n)]  # noqa: E731
Foto = Annotated[str | None, Field(default=None, max_length=80)]


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _foto_ok(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    if not regras.foto_valida(v):
        raise ValueError("foto inválida (envie a imagem pelo editor)")
    return v


class _ComFoto(_Base):
    foto: Foto = None

    @field_validator("foto")
    @classmethod
    def validar_foto(cls, v: str | None) -> str | None:
        return _foto_ok(v)


class Secao(_Base):
    tipo: TipoSecao
    ativa: bool = True


class Hero(_ComFoto):
    titulo: Txt(120) = ""
    subtitulo: Txt(300) = ""
    botao_texto: Txt(40) = "Agende sua aula experimental"


class Sobre(_ComFoto):
    titulo: Txt(120) = "Sobre nós"
    texto: Txt(3000) = ""
    destaques: list[Txt(60)] = Field(default_factory=list, max_length=6)


class ItemModalidade(_ComFoto):
    tipo_servico_id: int
    mostrar: bool = True
    descricao: Txt(400) = ""


class Modalidades(_Base):
    titulo: Txt(120) = "Modalidades"
    subtitulo: Txt(300) = ""
    itens: list[ItemModalidade] = Field(default_factory=list, max_length=100)


class Planos(_Base):
    titulo: Txt(120) = "Planos"
    subtitulo: Txt(300) = ""
    mostrar_precos: bool = True
    ocultos: list[int] = Field(default_factory=list, max_length=500)
    destaque_id: int | None = None
    observacao: Txt(300) = ""


class Grade(_Base):
    titulo: Txt(120) = "Horários"
    subtitulo: Txt(300) = ""
    mostrar_professor: bool = True


class ItemEquipe(_ComFoto):
    profissional_id: int
    mostrar: bool = False  # só aparece quem o estúdio marcar
    cargo: Txt(80) = ""
    bio: Txt(600) = ""


class Equipe(_Base):
    titulo: Txt(120) = "Nossa equipe"
    subtitulo: Txt(300) = ""
    itens: list[ItemEquipe] = Field(default_factory=list, max_length=100)


class Depoimento(_Base):
    nome: Txt(80)
    texto: Txt(600)
    detalhe: Txt(80) = ""


class Depoimentos(_Base):
    titulo: Txt(120) = "O que dizem sobre nós"
    itens: list[Depoimento] = Field(default_factory=list, max_length=12)


class FotoGaleria(_ComFoto):
    legenda: Txt(120) = ""


class Galeria(_Base):
    titulo: Txt(120) = "Nosso espaço"
    fotos: list[FotoGaleria] = Field(default_factory=list, max_length=24)


class Pergunta(_Base):
    pergunta: Txt(200)
    resposta: Txt(1200)


class Faq(_Base):
    titulo: Txt(120) = "Perguntas frequentes"
    itens: list[Pergunta] = Field(default_factory=list, max_length=20)


class Localizacao(_Base):
    titulo: Txt(120) = "Onde estamos"
    endereco: Txt(300) = ""
    mapa: Txt(2000) = ""  # link do Google Maps ou código <iframe> de "incorporar mapa"
    horario_texto: Txt(300) = ""

    @field_validator("mapa")
    @classmethod
    def _mapa(cls, v: str) -> str:
        if v and regras.extrair_mapa(v) is None:
            raise ValueError("cole um link do Google Maps (ou o código de incorporar mapa)")
        return v


class Contato(_Base):
    titulo: Txt(120) = "Fale com a gente"
    subtitulo: Txt(300) = ""
    whatsapp: Txt(30) = ""
    telefone: Txt(30) = ""
    email: Txt(200) = ""
    instagram: Txt(200) = ""
    facebook: Txt(200) = ""
    tiktok: Txt(200) = ""
    youtube: Txt(200) = ""
    mensagem_whatsapp: Txt(200) = "Olá! Vim pelo site e quero saber mais sobre as aulas."

    @field_validator("whatsapp", "telefone")
    @classmethod
    def _fone(cls, v: str) -> str:
        if v and not (10 <= len(re.sub(r"\D", "", v)) <= 13):
            raise ValueError("telefone inválido (use DDD + número)")
        return v

    @field_validator("instagram", "facebook", "tiktok", "youtube")
    @classmethod
    def _rede(cls, v: str) -> str:
        if v and regras.url_rede(v) is None:
            raise ValueError("informe o @usuário ou o link completo (https://...)")
        return v


class Seo(_Base):
    titulo: Txt(70) = ""
    descricao: Txt(170) = ""
    cidade: Txt(80) = ""
    estado: Txt(2) = ""
    categoria: Literal["pilates", "academia", "funcional", "estudio"] = "pilates"


class Privacidade(_Base):
    responsavel: Txt(150) = ""  # razão social / nome do controlador
    documento: Txt(20) = ""  # CNPJ ou CPF (opcional)
    email: Txt(200) = ""


class ConteudoSite(_Base):
    secoes: list[Secao] = Field(default_factory=list)
    hero: Hero = Field(default_factory=Hero)
    sobre: Sobre = Field(default_factory=Sobre)
    modalidades: Modalidades = Field(default_factory=Modalidades)
    planos: Planos = Field(default_factory=Planos)
    grade: Grade = Field(default_factory=Grade)
    equipe: Equipe = Field(default_factory=Equipe)
    depoimentos: Depoimentos = Field(default_factory=Depoimentos)
    galeria: Galeria = Field(default_factory=Galeria)
    faq: Faq = Field(default_factory=Faq)
    localizacao: Localizacao = Field(default_factory=Localizacao)
    contato: Contato = Field(default_factory=Contato)
    seo: Seo = Field(default_factory=Seo)
    privacidade: Privacidade = Field(default_factory=Privacidade)

    @model_validator(mode="after")
    def _secoes_completas(self) -> ConteudoSite:
        """Toda seção aparece uma vez na lista (as que faltam entram no fim, desligadas)."""
        vistos: list[Secao] = []
        tipos: set[str] = set()
        for s in self.secoes:
            if s.tipo not in tipos:
                tipos.add(s.tipo)
                vistos.append(s)
        for t in TIPOS_SECAO:
            if t not in tipos:
                vistos.append(Secao(tipo=t, ativa=False))
        self.secoes = vistos
        return self


# ------------------------------------------------------------------------------------- dados vindos dos cadastros
class ModalidadeDado(BaseModel):
    id: int
    nome: str


class PlanoDado(BaseModel):
    id: int
    nome: str
    modalidade: str | None = None
    valor: Decimal | None = None  # None quando o estúdio escolheu esconder preços
    aulas_por_semana: int
    duracao_meses: int
    avulso: bool


class ProfissionalDado(BaseModel):
    id: int
    nome: str


class HorarioDado(BaseModel):
    dia_semana: int
    hora_inicio: time
    hora_fim: time
    modalidade: str
    professor: str | None = None


class DadosEstudio(BaseModel):
    modalidades: list[ModalidadeDado]
    planos: list[PlanoDado]
    profissionais: list[ProfissionalDado]
    grade: list[HorarioDado]


class IdentidadeSite(BaseModel):
    nome: str
    cor: str
    logo_url: str | None = None


class PaginaPublica(BaseModel):
    tema: Tema
    identidade: IdentidadeSite
    conteudo: ConteudoSite
    dados: DadosEstudio
    publicado_em: datetime | None = None
    mapa_embed: str | None = None
    mapa_link: str | None = None


# ------------------------------------------------------------------------------------------------- editor
class EnderecoSite(BaseModel):
    principal: str | None = None
    dominios: list[str] = []


class EditorOut(BaseModel):
    tema: Tema
    conteudo: ConteudoSite
    publicado: bool
    publicado_em: datetime | None
    alteracoes_pendentes: bool
    identidade: IdentidadeSite
    dados: DadosEstudio
    endereco: EnderecoSite
    contatos_nao_lidos: int


class SalvarIn(_Base):
    tema: Tema
    conteudo: ConteudoSite


class ImagemOut(BaseModel):
    foto: str
    url: str


class ContatoIn(_Base):
    nome: Annotated[str, Field(min_length=2, max_length=150)]
    telefone: Annotated[str, Field(max_length=30)] = ""
    email: EmailStr | None = None
    interesse: Annotated[str, Field(max_length=120)] = ""
    mensagem: Annotated[str, Field(max_length=2000)] = ""
    quer_aula_experimental: bool = True
    consentimento: bool = False
    # anti-spam: campo invisível (robôs preenchem) e tempo de preenchimento informado pelo formulário
    website: Annotated[str, Field(max_length=300)] = ""
    tempo_ms: int | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _vazio(cls, v):
        return v or None

    @model_validator(mode="after")
    def _contato_minimo(self) -> ContatoIn:
        if not self.telefone and not self.email:
            raise ValueError("informe um telefone ou um e-mail para retornarmos")
        if self.telefone and not (10 <= len(re.sub(r"\D", "", self.telefone)) <= 13):
            raise ValueError("telefone inválido (use DDD + número)")
        return self


class ContatoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    telefone: str | None
    email: str | None
    interesse: str | None
    mensagem: str | None
    quer_aula_experimental: bool
    enviado_crm: bool
    lead_id: int | None
    lido: bool
    criado_em: datetime


class ListaContatos(BaseModel):
    itens: list[ContatoOut]
    total: int
    nao_lidos: int
