# Frontend — dashboard Streamlit do SaaS de faturas
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Instala dependências primeiro (melhor cache de camada)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copia o código do frontend (contexto = ./frontend)
COPY . .
RUN chmod +x /app/docker-entrypoint.sh

# Caminho default do módulo de mapas do Baltazar VENDORIZADO na imagem (ver
# vendor/). Em produção (nuvem) não há volume; o docker-compose local sobrescreve
# este valor e monta a cópia viva da biblioteca.
ENV BALTAZAR_MAPAS_PATH=/app/vendor/mapas_dinamicos.py

EXPOSE 8501

# O entrypoint gera o .streamlit/secrets.toml (auth OIDC) a partir de env vars e
# sobe o Streamlit. /app na raiz do sys.path → `from api.client import ...` resolve.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
