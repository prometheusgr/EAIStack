#!/bin/bash
# bootstrap-airgap.sh — Prepare all container images for air-gapped deployment

set -e

IMAGES_DIR="${IMAGES_DIR:-./__air-gap-images}"
REGISTRY="${REGISTRY:=localhost:5000}"

# Create output directory
mkdir -p "$IMAGES_DIR"

echo "=== EAIStack Air-Gap Bootstrap ==="
echo "Pulling images for air-gapped K3s deployment..."
echo "Output directory: $IMAGES_DIR"
echo ""

# TODO: Add all required images once they're finalized
# For now, stub the script structure

IMAGES=(
  # Infrastructure
  "pgvector/pgvector:0.5.1"
  "quay.io/keycloak/keycloak:22.0.0"
  "minio/minio:latest"
  "ghcr.io/ggml-org/llama.cpp:server-latest"
  "jetstack/cert-manager-controller:v1.13.0"
  "jetstack/cert-manager-webhook:v1.13.0"
  "jetstack/cert-manager-cainjector:v1.13.0"

  # Application (built from local Dockerfiles)
  "eaistack-backend:latest"
  "eaistack-frontend:latest"
)

echo "This script would:"
echo "1. Build local Docker images (backend, frontend)"
echo "2. Pull all external images"
echo "3. Save images to .tar.gz files"
echo "4. Create import script for k3s ctr images import"
echo ""
echo "Full implementation in Phase 5 with validation assertions."
