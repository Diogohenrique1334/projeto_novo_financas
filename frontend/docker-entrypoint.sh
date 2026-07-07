#!/bin/sh
# Sobe o Streamlit garantindo o .streamlit/secrets.toml (config do OIDC nativo).
#   - Se um secrets.toml já estiver presente (ex.: montado como volume no teste
#     local com docker-compose), usa-o.
#   - Senão (deploy no Render), GERA a partir de env vars — secrets.toml nunca vai
#     no git nem na imagem. Falha cedo se faltar credencial.
set -e

mkdir -p /app/.streamlit
if [ -f /app/.streamlit/secrets.toml ] && grep -q '\[auth\]' /app/.streamlit/secrets.toml; then
  echo "secrets.toml já presente — usando o arquivo montado."
else
  : "${GOOGLE_CLIENT_ID:?defina GOOGLE_CLIENT_ID}"
  : "${GOOGLE_CLIENT_SECRET:?defina GOOGLE_CLIENT_SECRET}"
  : "${AUTH_COOKIE_SECRET:?defina AUTH_COOKIE_SECRET}"
  : "${AUTH_REDIRECT_URI:?defina AUTH_REDIRECT_URI (URL pública + /oauth2callback)}"
  cat > /app/.streamlit/secrets.toml <<EOF
[auth]
redirect_uri = "${AUTH_REDIRECT_URI}"
cookie_secret = "${AUTH_COOKIE_SECRET}"

[auth.google]
client_id = "${GOOGLE_CLIENT_ID}"
client_secret = "${GOOGLE_CLIENT_SECRET}"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
EOF
fi

exec streamlit run app.py \
  --server.port="${PORT:-8501}" \
  --server.address=0.0.0.0 \
  --server.headless=true
