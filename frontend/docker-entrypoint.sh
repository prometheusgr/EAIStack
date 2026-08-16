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
echo "[entrypoint] Starting Vite dev server..."

# Start Vite dev server with host binding
exec npx vite --host 0.0.0.0
