# Air-Gapped K3s Deployment Guide

This guide assumes a K3s cluster on an air-gapped network with no internet access at runtime.

## Prerequisites

- K3s v1.28+ installed and running on a target machine
- Fully air-gapped network (no outbound internet)
- Docker or Podman on the prep machine (to pull images)
- ~100GB disk for pre-pulled images (depends on model size)

## Setup Overview

1. **Prepare images on internet-connected machine**
2. **Transfer to air-gapped network** (physical media, secure file transfer, etc.)
3. **Import into K3s**
4. **Deploy Helm charts**
5. **Verify cluster health**

## Step 1: Prepare Images (Internet-Connected Machine)

```bash
# Clone EAIStack repo
git clone https://github.com/your-org/eaistack.git
cd eaistack

# Build local images
docker build -t eaistack-backend:latest ./backend
docker build -t eaistack-frontend:latest ./frontend

# Run bootstrap script to pull and save all images
bash infra/scripts/bootstrap-airgap.sh
# Outputs to __air-gap-images/*.tar.gz
```

## Step 2: Transfer to Air-Gapped Network

Transfer the `__air-gap-images/` directory to the air-gapped machine using:
- Physical USB/external drive
- Secure file transfer (rsync, sftp over VPN)
- Any mechanism available in your network

## Step 3: Import Images into K3s

On the air-gapped machine:

```bash
cd /path/to/__air-gap-images

# Import all images
for image in *.tar.gz; do
  k3s ctr images import "$image"
done

# Verify images are present
k3s ctr images list
```

## Step 4: Deploy Helm Charts

```bash
# Add local Helm chart repository (if using OCI registry)
# OR point directly to vendored charts

helm install eaistack ./infra/helm/charts/eaistack-umbrella \
  --namespace eaistack \
  --create-namespace \
  -f infra/helm/values-airgap.yaml
```

## Step 5: Verify Cluster Health

```bash
# Check pod status
kubectl get pods -n eaistack
# Expected: All pods in Running state within ~2 minutes

# Check services
kubectl get svc -n eaistack

# Check logs
kubectl logs -n eaistack deployment/eaistack-backend

# Verify TLS is enabled (Phase 5)
kubectl get cert -n eaistack
```

## Troubleshooting

### Images not found

```bash
# Verify images were imported
k3s ctr images list | grep eaistack

# Re-import if needed
k3s ctr images import __air-gap-images/eaistack-backend*.tar.gz
```

### Pods stuck in Pending

```bash
# Check node resources
kubectl describe nodes

# Check pod events
kubectl describe pod <pod-name> -n eaistack
```

### Network issues between services

Check that K8s service DNS is working:
```bash
kubectl exec -it deployment/eaistack-backend -n eaistack -- nslookup postgres
```

## Next Steps

Once the cluster is running:

1. **Access the frontend**: Get the ingress IP and navigate to it (or port-forward if no ingress)
2. **Login via Keycloak**: Default realm is `eaistack` (pre-configured during deployment)
3. **Test the agent flow**: Upload a document, ask a question, verify the MCP tool is called

See [docs/SECURITY.md](SECURITY.md) for encryption verification and session lifecycle configuration.

## Configuration

Key environment variables (can be overridden in Helm values):

- `SESSION_CLEANUP_ON_LOGOUT=true` — Purge checkpoint on Keycloak logout
- `SESSION_TTL_HOURS=24` — TTL-based cleanup (set to 0 to disable)
- `LLM_URL=http://llama-server:8000` — Local LLM endpoint

See `infra/helm/charts/*/values.yaml` for full configuration options.
