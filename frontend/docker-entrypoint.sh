#!/bin/sh

# Generate .env.local from environment variables for Vite
# Vite reads .env.local with higher priority than .env
cat > /app/.env.local << EOF
VITE_KEYCLOAK_URL=${VITE_KEYCLOAK_URL:-http://localhost:8080/}
VITE_BACKEND_URL=${VITE_BACKEND_URL:-http://localhost:8001}
EOF

echo "[entrypoint] Generated .env.local with:"
cat /app/.env.local
echo ""

# TLS is opt-in via SSL_CERTFILE/SSL_KEYFILE (read directly by vite.config.ts's
# server.https option) so this same image serves plain HTTP for local dev /
# docker-compose and HTTPS when deployed via Helm (infra/helm/charts/frontend),
# which mounts a cert-manager-issued Secret and sets these vars.
if [ -n "${SSL_CERTFILE:-}" ] && [ -n "${SSL_KEYFILE:-}" ]; then
    echo "[entrypoint] SSL_CERTFILE/SSL_KEYFILE set: starting Vite dev server with TLS"
else
    echo "[entrypoint] SSL_CERTFILE/SSL_KEYFILE not set: starting Vite dev server without TLS"
fi

# Start Vite dev server with host binding
exec npx vite --host 0.0.0.0
