FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY . .
RUN pip install --no-cache-dir -e .

EXPOSE 8000

# TLS is optional and controlled entirely by environment variables so that
# docker-compose / local dev (no SSL_CERTFILE/SSL_KEYFILE set) keeps serving
# plain HTTP, while the Helm-deployed container (which mounts a cert-manager
# Secret and sets these vars, see infra/helm/charts/backend/templates/deployment.yaml)
# serves HTTPS on the same port 8000 that the readiness/liveness probes and
# Service expect. docker-entrypoint.sh builds the uvicorn command line from
# these vars at container start.
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
