#!/bin/sh
# Starts uvicorn, adding TLS args only when TLS_ENABLED=true.
#
# Local dev and docker-compose don't set TLS_ENABLED, so they get the same
# plain-HTTP startup as before (Phase 5, Decision 1 only requires TLS inside
# the K8s deployment, where the Helm chart sets TLS_ENABLED/TLS_CERT_FILE/
# TLS_KEY_FILE to point at the cert-manager-issued Secret mounted into the
# pod — see infra/helm/charts/doc-search/templates/deployment.yaml).
set -e

if [ "$TLS_ENABLED" = "true" ]; then
    exec uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8100 \
        --ssl-certfile "$TLS_CERT_FILE" \
        --ssl-keyfile "$TLS_KEY_FILE"
else
    exec uvicorn app.main:app --host 0.0.0.0 --port 8100
fi
