# EAIStack Helm Charts

Kubernetes Helm charts for deploying the EAIStack to K3s (fully air-gapped).

## Structure

- `eaistack-umbrella/` — Top-level umbrella chart that depends on service charts
- Individual service charts (postgres, keycloak, minio, llama-server, backend, frontend)

## Using Official Upstream Charts

Per the architecture decision (avoiding deprecated Bitnami charts):

- **PostgreSQL + pgvector**: Use the official `pgvector/pgvector` Docker image; create a simple custom values overlay if needed
- **Keycloak**: Use Keycloak's own official chart (or codecentric/Keycloak community chart)
- **MinIO**: Use MinIO's official chart

## Chart Development (Phase 5)

Actual chart files to be created in Phase 5 with validation assertions written first per TDD standards.
