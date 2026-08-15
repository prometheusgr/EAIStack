# K3s Air-Gap Installation

K3s is a minimal, production-grade Kubernetes distribution ideal for air-gapped enterprise deployments.

## Installation Steps (Phase 5)

1. **Download K3s release** (on a machine with internet)
   ```bash
   wget https://github.com/k3s-io/k3s/releases/download/v1.28.0/k3s
   chmod +x k3s
   ```

2. **Copy to air-gapped host** (via physical media or secure transfer)

3. **Install K3s in air-gap mode** (on target machine with no internet)
   ```bash
   INSTALL_K3S_SKIP_DOWNLOAD=true ./k3s server --secrets-encryption
   ```

4. **Import pre-pulled images**
   ```bash
   ./k3s ctr images import /path/to/images.tar.gz
   ```

5. **Deploy Helm charts**
   ```bash
   helm repo add --local <registry>
   helm install eaistack <chart> -f values.yaml
   ```

## Configuration

- `--secrets-encryption` — Enable etcd secrets encryption at rest
- `--disable=servicelb` — Use cert-manager-based ingress instead of K3s's built-in load balancer
- Custom volumes with encrypted StorageClass for Postgres/MinIO data

## References

- [K3s Air-Gap Install Docs](https://docs.k3s.io/installation/airgap)
- Validation scripts in `/infra/scripts/`
