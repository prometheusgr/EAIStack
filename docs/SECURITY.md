# Security & Data Lifecycle

## Encryption

### In Transit (TLS)

**Status**: Phase 5, enabled by default via cert-manager.

All service-to-service communication is encrypted:
- Frontend ↔ Backend: TLS
- Backend ↔ Database: TLS
- Backend ↔ MinIO: TLS
- Backend ↔ llama-server: TLS (optional, can be unencrypted on private network)
- Backend ↔ MCP servers: TLS

**Implementation**: 
- cert-manager with self-signed internal CA (no external ACME)
- Helm charts auto-generate certificates via ClusterIssuer

**Verification**:
```bash
# Check TLS is enabled on a service
openssl s_client -connect backend.eaistack:443 < /dev/null

# Check certificate validity
kubectl get cert -n eaistack
```

### At Rest

**Secrets (Kubernetes)**:
- Enabled via K3s `--secrets-encryption` flag
- etcd encryption with AES-GCM (automatic)

**Verification**:
```bash
# Secrets should not be readable in plaintext
kubectl get secret session-jwt -n eaistack -o yaml
# Should show encrypted values, not plaintext
```

**Volumes (Postgres, MinIO)**:
- Backed by encrypted StorageClass (LUKS or host-provided)
- Configuration is environment/deployment-dependent
- Document your storage backend's encryption mechanism

**Example** (LUKS-backed local storage):
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: encrypted-local
provisioner: kubernetes.io/local
parameters:
  encryption: luks
```

### No KMS in v1

This template does **not** include a dedicated Key Management Service (Vault, AWS KMS, etc.).

**For deployments requiring stricter key separation**:
1. Add HashiCorp Vault as a separate Helm deployment
2. Configure Postgres and MinIO to fetch encryption keys from Vault
3. Document the Vault init/unseal process for air-gapped networks

This is a documented upgrade path, not built in to keep the template's complexity down.

## Session & Context Lifecycle

Every conversation exists as a LangGraph "checkpoint" in Postgres, tied to a specific user session.

**Checkpoint structure**:
```sql
-- app/db/models.py (Phase 4a)
class Checkpoint(Base):
    __tablename__ = "checkpoints"
    user_id: str     -- Keycloak subject
    thread_id: str   -- Conversation thread ID
    state: dict      -- LangGraph state (serialized)
    created_at: datetime
    updated_at: datetime
```

### Cleanup Policy

**Phase 4a**: Configurable per-deployment via environment variables.

#### Option 1: Logout-Triggered Cleanup

```bash
SESSION_CLEANUP_ON_LOGOUT=true
SESSION_TTL_HOURS=null  # Disabled
```

**Mechanism**: 
- Keycloak backchannel logout webhook calls `/api/logout`
- Backend purges all checkpoints for that user

**Implication**: Conversation history is deleted on logout. Good for high-sensitivity use cases.

#### Option 2: TTL-Based Cleanup

```bash
SESSION_CLEANUP_ON_LOGOUT=false
SESSION_TTL_HOURS=24
```

**Mechanism**: 
- Background job (APScheduler or K8s CronJob) runs hourly
- Deletes checkpoints older than the TTL

**Implication**: Sessions live for N hours; users can re-login and see old conversations until TTL expires.

#### Option 3: Both (Recommended for Defense-in-Depth)

```bash
SESSION_CLEANUP_ON_LOGOUT=true
SESSION_TTL_HOURS=72
```

**Implication**: Cleanup on logout AND hard TTL prevents long-lived leaked sessions.

### What Gets Deleted

**Deleted**:
- LangGraph checkpoint state (conversation thread, model state, context)
- Temporary conversation-scoped data (e.g., uploaded document references for that session)

**NOT deleted** (important for compliance):
- Audit logs (who accessed what, when)
- Guardrail violation records
- Inference request/response logs (if enabled)

These retention policies are separate; configure them independently in your compliance/audit framework.

### Preventing Context Bleeding

**By design**, each checkpoint is keyed to a single user's session. Two concurrent sessions **never share state**.

**Verification test** (Phase 4a):
```python
def test_session_isolation():
    # Create two concurrent sessions
    session1 = get_session(user_id="user1", thread_id="thread1")
    session2 = get_session(user_id="user2", thread_id="thread1")
    
    # Set state in session 1
    set_checkpoint_state(session1, {"key": "value_from_user1"})
    
    # Read from session 2 — should NOT see user1's state
    assert get_checkpoint_state(session2) is None
```

## Audit & Compliance

**Not included in v1**, but ready for Phase 4a expansion:
1. Log all checkpoint mutations (CREATE, UPDATE, DELETE)
2. Capture audit metadata (user, timestamp, action)
3. Store in an immutable audit log table
4. Configure retention policy independent of session cleanup

Example:
```python
# app/db/models.py
class AuditLog(Base):
    __tablename__ = "audit_logs"
    user_id: str
    action: str  # "create_checkpoint", "update_checkpoint", "delete_checkpoint"
    checkpoint_id: str
    timestamp: datetime
    # ... metadata
```

## Compliance Considerations

### GDPR/Data Deletion

The session cleanup mechanism satisfies "right to be forgotten" by:
1. User requests deletion (or session expires)
2. Checkpoint rows are purged
3. MinIO document metadata can be tagged with user_id for bulk deletion

**Caveat**: Audit logs are retained separately; configure audit log retention per your compliance requirements.

### Data Residency

All data stays on-premise (fully air-gapped). No external logging, no cloud storage, no third-party model APIs.

### Guardrails & Compliance

Guardrail violations are logged to a separate table for compliance review:
```python
class GuardrailViolation(Base):
    __tablename__ = "guardrail_violations"
    user_id: str
    violation_type: str  # "pii_detected", "topic_blocked", etc.
    input_text: str
    timestamp: datetime
```

## Secrets Management (K3s Native)

K3s secrets are encrypted at rest in etcd. To manually create a secret:

```bash
kubectl create secret generic my-secret --from-literal=key=value -n eaistack
# Secret is encrypted in etcd automatically
```

For more complex secrets (API keys, certificates):
```bash
kubectl create secret tls my-cert --cert=path/to/cert.crt --key=path/to/key.key -n eaistack
```

## Monitoring & Verification

Checklist for Phase 5 deployment:

- [ ] TLS is enabled on all service-to-service communication
- [ ] etcd encryption is enabled (`kubectl get cm kube-apiserver-config -n kube-system`)
- [ ] StorageClass volumes are encrypted (ask your infrastructure team)
- [ ] Session cleanup is configured and working
- [ ] Audit logs are being captured
- [ ] Secrets are not readable in plaintext (`kubectl get secret --show-sensitive`)

## Questions?

Refer to [docs/ARCHITECTURE.md](ARCHITECTURE.md) for architectural context, or [CLAUDE.md](../CLAUDE.md) for development standards.
