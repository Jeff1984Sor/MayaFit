"""Configuração central, lida de variáveis de ambiente (.env). Em hml/prod os segredos são obrigatórios."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores só de desenvolvimento: o validador recusa estes em hml/prod.
_JWT_DEV = "dev-inseguro-troque-em-producao-0000"
_MASTER_DEV = "q5w0m9cY3G1o4oE5d2u2x2gVQv0q6Q7k1tq9a0c3Zf8="

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MayaFit"
    ambiente: Literal["dev", "hml", "prod"] = "dev"
    debug: bool = False
    # Hosts aceitos no cabeçalho Host. Em hml/prod é obrigatório listar explicitamente (nada de "*").
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'dev.db').as_posix()}"
    storage_dir: Path = BASE_DIR / "storage"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Segurança
    jwt_secret: str = _JWT_DEV
    jwt_access_minutes: int = 30
    jwt_refresh_days: int = 14
    # Chave Fernet (base64 urlsafe de 32 bytes) que cifra segredos guardados no banco (SMTP, IA, integrações).
    master_key: str = _MASTER_DEV
    # Chave anterior, só durante uma rotação: ainda decifra, mas tudo novo é cifrado com a master_key.
    master_key_anterior: str | None = None
    # SECRET_KEY do Django antigo: só para aceitar links de assinatura já enviados (usada pelo módulo de contratos).
    legacy_django_secret_key: str | None = None

    login_max_tentativas: int = 5
    login_bloqueio_minutos: int = 15
    recuperacao_email_minutos: int = 120
    recuperacao_codigo_minutos: int = 10
    recuperacao_codigo_max_tentativas: int = 5

    # Rate limit dos endpoints públicos
    rate_limit_ativo: bool = True
    rate_limit_backend: Literal["memoria", "banco"] = "memoria"

    # Arquivos
    upload_max_mb: int = 10
    link_assinado_horas: int = 72

    # E-mail (a configuração da tela Configurações › E-mail tem prioridade sobre estas)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "MayaFit <nao-responda@localhost>"

    frontend_url: str = "http://localhost:3000"
    # Um banco por estúdio (liga sozinho quando o banco `mayafit_controle` existe; ver app/core/tenancy.py):
    # cada estúdio novo ganha o endereço <slug>.<dominio_base> (ex.: "mayafit.com.br"). Vazio = só domínios cadastrados.
    dominio_base: str | None = None

    # Dev: a API roda as tarefas periódicas em thread e aplica as migrations ao subir.
    # Produção: worker_embutido=false (o serviço app.worker faz) e migrations no deploy.
    worker_embutido: bool = True
    migrar_na_subida: bool = True

    @model_validator(mode="after")
    def _validar(self):
        try:
            Fernet(self.master_key.encode())
            if self.master_key_anterior:
                Fernet(self.master_key_anterior.encode())
        except Exception:
            raise ValueError("MASTER_KEY inválida: use uma chave Fernet (base64 urlsafe de 32 bytes).") from None
        if self.ambiente == "dev":
            return self
        erros = []
        if self.jwt_secret == _JWT_DEV or len(self.jwt_secret) < 32:
            erros.append("JWT_SECRET próprio com pelo menos 32 caracteres")
        if self.master_key == _MASTER_DEV:
            erros.append("MASTER_KEY própria (diferente da de desenvolvimento)")
        if self.jwt_secret == self.master_key:
            erros.append("JWT_SECRET diferente da MASTER_KEY")
        if self.debug:
            erros.append("DEBUG=false")
        if not self.allowed_hosts or "*" in self.allowed_hosts or any(h in ("localhost", "testserver") for h in self.allowed_hosts):
            erros.append("ALLOWED_HOSTS explícito (domínios reais, sem '*' nem localhost)")
        if not self.frontend_url.startswith("https://"):
            erros.append("FRONTEND_URL com https://")
        if any("localhost" in o or "127.0.0.1" in o for o in self.cors_origins):
            erros.append("CORS_ORIGINS sem localhost")
        if not self.rate_limit_ativo:
            erros.append("RATE_LIMIT_ATIVO=true")
        if erros:
            raise ValueError(f"Configuração insegura para {self.ambiente}. Defina no .env: " + "; ".join(erros) + ".")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
