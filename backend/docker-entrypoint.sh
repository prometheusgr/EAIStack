#!/bin/sh
# Entrypoint for the backend image. Two responsibilities:
#
# 1. Pass through any explicit command (docker-compose's `migrate` service
#    runs `alembic upgrade head` through this same image/entrypoint, and
#    `backend`'s own docker-compose command overrides with `--reload`).
# 2. When no command is given (the Helm-deployed container has none), start
#    uvicorn, adding TLS args only when a certificate is actually mounted.
#
# TLS is opt-in via SSL_CERTFILE/SSL_KEYFILE so this image behaves correctly
# in two different deployments without any code branching:
#   - docker-compose / local dev: neither var is set -> plain HTTP on :8000.
#   - Helm (infra/helm/charts/backend): tls.enabled gates a volumeMount of the
#     cert-manager-issued Secret plus these two env vars pointing at the
#     mounted tls.crt/tls.key, so the container serves HTTPS on the same
#     port 8000 that the chart's readiness/liveness probes (scheme: HTTPS)
#     and Service already expect.
set -e

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

UVICORN_ARGS="app.main:app --host 0.0.0.0 --port 8000"

if [ -n "${SSL_CERTFILE:-}" ] && [ -n "${SSL_KEYFILE:-}" ]; then
    echo "[entrypoint] SSL_CERTFILE/SSL_KEYFILE set: starting uvicorn with TLS"
    UVICORN_ARGS="${UVICORN_ARGS} --ssl-certfile ${SSL_CERTFILE} --ssl-keyfile ${SSL_KEYFILE}"
else
    echo "[entrypoint] SSL_CERTFILE/SSL_KEYFILE not set: starting uvicorn without TLS"
fi

exec uvicorn ${UVICORN_ARGS}
