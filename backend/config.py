"""Configurações da aplicação via Pydantic BaseSettings."""

from pathlib import Path

from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Configurações da API carregadas de variáveis de ambiente."""

    APP_NAME: str = "SaaS Análise de Faturas"
    DEBUG: bool = False
    DATABASE_URL: str
    BACKEND_URL: str = "http://backend:8001"
    ALLOWED_ORIGINS: str = "http://localhost:8501"
    # Bootstrap de admin: e-mails (separados por vírgula) que nascem role=admin,
    # status=approved. É assim que o Diogo vira admin no dia 1 (spec §3).
    ADMIN_EMAILS: str = ""
    # Segredo HMAC compartilhado entre frontend e backend para a asserção interna
    # (padrão BFF): o frontend, após o login OIDC do Google, cunha um JWT curto que
    # o backend verifica. NUNCA hardcoded — só via env. Sem ele, a auth não sobe.
    INTERNAL_AUTH_SECRET: str = ""
    # Janela de validade (segundos) da asserção interna. Curta de propósito.
    AUTH_ASSERTION_TTL: int = 300
    # Teto diário de extrações de fatura (cada upload dispara uma chamada de LLM).
    # Na Fase 6 vira teto POR usuário; hoje é global por processo.
    LIMITE_DIARIO_UPLOAD: int = 50
    # Tamanho máximo (MB) de um PDF de fatura aceito no upload.
    UPLOAD_MAX_MB: int = 10
    # --- Extração por visão (Fase 5) ---
    OPENAI_API_KEY: str = ""
    # Modelo com visão + structured output usado na extração de faturas.
    EXTRACT_MODEL: str = "gpt-5-mini"
    # Resolução (DPI) do render de cada página do PDF em imagem.
    EXTRACT_DPI: int = 150
    # Teto de páginas enviadas ao modelo (proteção de custo/token).
    EXTRACT_MAX_PAGINAS: int = 12

    @property
    def admin_emails(self) -> set[str]:
        """E-mails de admin normalizados (minúsculos, sem espaços, sem vazios)."""
        return {e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()}

    class Config:
        env_file = str(_ENV_FILE)
        extra = "allow"


settings = Settings()
