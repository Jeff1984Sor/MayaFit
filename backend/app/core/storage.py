"""Armazenamento de arquivos em disco (STORAGE_DIR).

Regras:
- No banco só vai o caminho RELATIVO ao storage (ex.: "usuarios/usuario_3.jpg"), nunca o absoluto.
- Todo caminho é validado contra path traversal.
- Extensão e tamanho são validados por CATEGORIA (a primeira pasta do caminho); o conteúdo é conferido pela assinatura
  do arquivo (um .jpg que não é imagem é recusado). SVG/HTML não são aceitos.
- Nada é servido sem autenticação: a rota `/api/arquivos/{caminho}` exige login e a permissão da categoria;
  para PDFs públicos use `link_publico()` (link assinado com prazo).
"""

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core import links, tenancy
from app.core.config import settings


class ArquivoInvalido(ValueError):
    """Mensagem já pronta para o usuário."""


@dataclass(frozen=True)
class Categoria:
    nome: str
    permissao: str | None  # permissão exigida para LER pela rota autenticada; None = qualquer usuário logado
    extensoes: frozenset[str]
    max_mb: int


IMAGENS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
DOCUMENTOS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".xlsx"})

_CATEGORIAS: dict[str, Categoria] = {}

# assinaturas (magic bytes) conferidas por extensão
_ASSINATURAS: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
}


def registrar_categoria(nome: str, permissao: str | None, extensoes: frozenset[str] | set[str], max_mb: int | None = None) -> None:
    """Cada módulo registra suas categorias (ex.: nome "documentos_aluno", permissao "alunos.ver").
    `permissao=None` = basta estar logado."""
    _CATEGORIAS[nome] = Categoria(nome, permissao, frozenset(extensoes), max_mb or settings.upload_max_mb)


registrar_categoria("usuarios", None, IMAGENS, 4)
registrar_categoria("identidade", None, IMAGENS, 3)


def categoria(nome: str) -> Categoria:
    c = _CATEGORIAS.get(nome)
    if not c:
        raise ArquivoInvalido("Categoria de arquivo desconhecida.")
    return c


def categoria_do_caminho(rel: str) -> Categoria:
    return categoria(rel.replace("\\", "/").split("/", 1)[0])


def raiz() -> Path:
    """Pasta do estúdio atual: `storage/` com um banco só (ou no estúdio principal), `storage/estudios/<slug>` nos demais."""
    p = tenancy.pasta_base().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolver(rel: str) -> Path:
    """Caminho absoluto seguro de um caminho relativo do storage (recusa absoluto, '..', NUL e saídas da raiz)."""
    if not rel or "\x00" in rel or "\\" in rel or rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        raise ArquivoInvalido("Caminho de arquivo inválido.")
    partes = rel.split("/")
    if any(p in ("", ".", "..") for p in partes):
        raise ArquivoInvalido("Caminho de arquivo inválido.")
    base = raiz()
    destino = (base / rel).resolve()
    if base not in destino.parents:
        raise ArquivoInvalido("Caminho de arquivo inválido.")
    return destino


def _validar(cat: Categoria, nome_original: str, conteudo: bytes) -> str:
    ext = Path(nome_original or "").suffix.lower()
    if ext not in cat.extensoes:
        permitidas = ", ".join(sorted(e.lstrip(".").upper() for e in cat.extensoes))
        raise ArquivoInvalido(f"Tipo de arquivo não permitido. Envie: {permitidas}.")
    if not conteudo:
        raise ArquivoInvalido("O arquivo está vazio.")
    if len(conteudo) > cat.max_mb * 1024 * 1024:
        raise ArquivoInvalido(f"O arquivo deve ter no máximo {cat.max_mb} MB.")
    assinaturas = _ASSINATURAS.get(ext)
    if assinaturas and not any(conteudo.startswith(a) for a in assinaturas):
        raise ArquivoInvalido("O conteúdo do arquivo não corresponde ao tipo informado.")
    if ext == ".webp" and conteudo[8:12] != b"WEBP":
        raise ArquivoInvalido("O conteúdo do arquivo não corresponde ao tipo informado.")
    return ext


def salvar(cat_nome: str, nome_original: str, conteudo: bytes, *, subpasta: str = "", nome_base: str | None = None,
           substituir: bool = False) -> str:
    """Grava o arquivo e devolve o caminho relativo. Com `nome_base` fixo (ex.: "usuario_3") e `substituir`, troca o
    anterior (qualquer extensão); sem `nome_base` o nome é aleatório (não adivinhável)."""
    cat = categoria(cat_nome)
    ext = _validar(cat, nome_original, conteudo)
    nome = f"{nome_base or uuid.uuid4().hex}{ext}"
    rel = "/".join(p for p in (cat.nome, subpasta.strip("/"), nome) if p)
    destino = resolver(rel)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if substituir and nome_base:
        for velho in destino.parent.glob(f"{nome_base}.*"):
            velho.unlink()
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_bytes(conteudo)
    os.replace(tmp, destino)
    return rel


def ler(rel: str) -> bytes:
    p = resolver(rel)
    if not p.is_file():
        raise FileNotFoundError(rel)
    return p.read_bytes()


def existe(rel: str | None) -> bool:
    if not rel:
        return False
    try:
        return resolver(rel).is_file()
    except ArquivoInvalido:
        return False


def remover(rel: str | None) -> None:
    if rel and existe(rel):
        resolver(rel).unlink()


def versao(rel: str | None) -> int:
    """mtime inteiro, para invalidar cache de imagem quando o arquivo muda."""
    return int(resolver(rel).stat().st_mtime) if existe(rel) else 0


def link_publico(rel: str, *, validade_s: int | None = None, nome_download: str | None = None) -> str:
    """Caminho (sem host) de um link público assinado para `rel`; vale `LINK_ASSINADO_HORAS` por padrão."""
    resolver(rel)
    categoria_do_caminho(rel)
    token = links.assinar("arquivo", {"p": rel, "n": nome_download}, validade_s or settings.link_assinado_horas * 3600)
    return f"/api/arquivos-publicos/{token}"
