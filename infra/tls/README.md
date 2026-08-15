# TLS & Encryption Setup

Air-gapped TLS infrastructure for K3s deployment.

## Components

- **cert-manager**: Issues and manages TLS certificates using an internal CA
- **Internal CA**: Self-signed certificate authority (no external ACME)
- **Service certificates**: Automatically issued for internal K8s services

## Configuration (Phase 5)

- `issuer.yaml` — ClusterIssuer for internal CA
- `ca-cert.yaml` — Internal CA certificate bootstrap
- Individual service values will reference the issuer for automatic certificate generation

## Key Points

- All certificates are self-signed (no Let's Encrypt in air-gap)
- K8s services communicate over TLS by default
- Applications trust the internal CA via mounted CA bundle
