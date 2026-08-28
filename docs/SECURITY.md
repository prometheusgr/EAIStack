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

`backend/app/storage/minio_client.py` derives its `secure`/CA-bundle
behavior from `MINIO_URL`'s scheme, the same "let the URL decide" rule
every other outbound client in this codebase follows — the Helm-deployed
MinIO above is `https://`, so it always gets a TLS+CA-verified client.
docker-compose's local MinIO is plaintext, like every other service in
that stack; moving local dev to TLS-by-default across the board is tracked
separately (issue #17), not built into the MinIO client itself.

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

## Data Retention Policy

**Status**: Phase 4b, implemented.

Every persisted store has an explicit retention timeline. Windows marked
admin-configurable can be changed at runtime from the Settings screen and take
effect on the next retention sweep — no backend restart.

| Store | Retention timeline | Admin-configurable | Enforced by |
|---|---|---|---|
| `conversation_threads` / `conversation_checkpoints` | `session_ttl_hours`, default **24h** since last update. Also purged on logout when `session_cleanup_on_logout` is on. | Yes (`conversation_retention_hours`, `cleanup_on_logout`) | `purge_expired_conversations`, `purge_user_conversations` |
| `knowledge_base` (soft-deleted) | **30 days** after `deleted_at`, then hard-deleted. Live documents are never purged. | Yes (`knowledge_base_purge_days`) | `purge_expired_knowledge_base` |
| `embeddings` | Follows its parent document — purged in the same batch. | Inherited | `purge_expired_knowledge_base` |
| MinIO object (uploaded file, if any) | Follows its parent document — deleted in the same purge as the DB row. A pasted-text entry has no object (`storage_key` is NULL) and nothing is deleted for it. | Inherited | `purge_expired_knowledge_base` (via `DocumentStore.delete_many`) |
| `api_keys` (revoked) | **30 days** after `revoked_at`, then hard-deleted. Active keys are never purged. | Yes (`api_key_purge_days`) | `purge_expired_api_keys` |
| `system_settings` | **Forever** (configuration, single row). | n/a | Never purged |
| `audit_logs` | **Forever** — retained on a schedule independent of session cleanup. | **No, by design** | Never purged (see below) |

A window of `null` means "keep forever"; `0` means "purge immediately". Both are
meaningful values, so every resolver tests `is not None` rather than truthiness.

### Audit Records Are Exempt From Every Purge Path

This is enforced in code, not by convention:

- `AuditLogRepository` exposes only `record` and `list_recent`. There is no
  update or delete method, so no purge path can acquire one. A unit test asserts
  the class's public surface to keep it that way.
- No function in `app.services.retention_service` queries or deletes `AuditLog`
  at all.
- `run_retention_sweep` is tested with every window set to its most aggressive
  value: all other stores are emptied and audit history is still intact.

### Enforcement: K8s CronJob, not an in-process scheduler

The TTL sweep runs as a Kubernetes CronJob invoking
`python -m app.cli.retention_sweep`, rather than APScheduler inside the API
process. The deciding reason is multi-replica correctness: an in-process
scheduler runs in *every* replica, so a 3-replica Deployment fires three
concurrent sweeps issuing overlapping DELETEs. Avoiding that requires a
distributed lock or leader election — real machinery to build, test and operate.
Kubernetes already guarantees one Job per schedule, so the problem disappears
instead of being managed. Secondary benefits: a failed purge surfaces as a
failed Job with retained logs rather than a silently dead background thread, and
it adds no new runtime dependency to an air-gapped image.

**Trade-off**: nothing sweeps automatically under plain `docker-compose`. Run the
module manually (or from host cron) in that environment.

### Safety: Shortening a Window

Shortening a retention window irreversibly deletes data belonging to users other
than the admin making the change. Two controls apply:

1. The Settings UI requires explicit confirmation before applying a shortened
   window, naming each affected store and its old → new value.
2. Every retention change is written to `audit_logs` with the actor, timestamp,
   field, and old/new values — captured *before* the write, so the trail shows
   the actual transition rather than just the final state. Unchanged fields
   produce no record.

Purges are batched (500 rows per round-trip), never issued as one unbounded
DELETE, so a deployment with months of accumulated history doesn't hold a single
long transaction.

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

**Phase 4b**: Configurable per-deployment via environment variables, and
overridable at runtime by an admin from the Settings screen (the DB override
wins over the env default). The env vars below set the deployment's defaults.

#### Option 1: Logout-Triggered Cleanup

```bash
SESSION_CLEANUP_ON_LOGOUT=true
SESSION_TTL_HOURS=null  # Disabled
```

**Mechanism**: 
- The frontend calls `POST /api/auth/logout` on sign-out
- Backend purges all conversation threads/checkpoints for that user
- The purged user_id always comes from the validated token, never request
  input, so the endpoint cannot reach another user's data

**Implication**: Conversation history is deleted on logout. Good for high-sensitivity use cases.

#### Option 2: TTL-Based Cleanup

```bash
SESSION_CLEANUP_ON_LOGOUT=false
SESSION_TTL_HOURS=24
```

**Mechanism**: 
- A K8s CronJob runs `python -m app.cli.retention_sweep` on a schedule
- Deletes checkpoints (and their threads) not updated within the TTL
- See "Enforcement: K8s CronJob" above for why this is not an in-process scheduler

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

## MCP Server Isolation

**Status**: Phase 3, implemented — `mcp-servers/doc-search`.

`search_knowledge_base` runs as a standalone MCP server, reached by the
backend over the network (Streamable HTTP) instead of an in-process Python
closure. Crossing that process boundary removes the mechanism that used to
guarantee isolation: a closure over `user_id` and a `db` session can't
survive a network hop, so a new isolation guarantee had to replace it.

**Design**: the backend forwards the caller's own, already-validated
Keycloak access token — never a bare `user_id` string — as a `Bearer`
header on every call to doc-search. doc-search independently verifies that
token against Keycloak's JWKS (the same signature, audience, and expiry
checks `backend/app/core/auth.py`'s `verify_token` performs, duplicated in
`mcp-servers/doc-search/app/auth.py` rather than shared as a package, since
these are two separately deployed services) and derives `user_id` from the
verified `sub` claim itself. doc-search never trusts an identity claim
handed to it by another service — this is defense-in-depth, chosen
deliberately over the simpler alternative of trusting a bare `user_id` the
backend claims, appropriate for a template aimed at high-security
deployments.

**Trade-off, stated explicitly**: forwarding the real bearer token widens
where a stolen token is dangerous. Before this design, a compromised token
was usable only against the backend; now it's also directly usable against
doc-search, since doc-search verifies it itself rather than trusting the
backend's say-so. This is the direct cost of independent verification over
blind trust — accepted deliberately, not overlooked. It is mitigated by:
the token being request-scoped in memory at both hops (never logged, never
persisted to disk or a database by either service); doc-search performing
the exact same signature/audience/expiry checks the backend does, so a
token invalid at one service is invalid at the other; and TLS on the
backend↔MCP-server hop (Phase 5, see the Encryption section above) closing
the remaining plaintext-network exposure this design accepts until then.

**Verification test** (Phase 3): `mcp-servers/doc-search/tests/unit/test_server.py`
proves this end-to-end over a real Streamable HTTP connection — a request
with no token, an expired token, or a token signed by the wrong key is
rejected before any database query runs, and a valid token for one user
never surfaces another user's documents even when both tokens are
independently valid.

## Audit & Compliance

**Status**: Phase 4b — `audit_logs` exists and records retention configuration
changes. Phase 4 added a second action type, `guardrail.input_rejected` (see
"Guardrails & Compliance" below). Checkpoint-mutation auditing is not yet in
scope.

```python
# app/db/models.py
class AuditLog(Base):
    __tablename__ = "audit_logs"
    actor_user_id: str   # who made the change (Keycloak subject)
    action: str          # "retention.update" | "guardrail.input_rejected"
    field_name: str      # e.g. "conversation_retention_hours", or "message"
    old_value: str | None  # NULL = had no DB override before the change
    new_value: str | None
    created_at: datetime
```

Append-only by design: no application code updates or deletes a row, and the
repository exposes no method that could. Read it via `GET /api/settings/audit`
(admin-only). Retention is independent of session cleanup — see the retention
policy table above.

## Compliance Considerations

### GDPR/Data Deletion

The session cleanup mechanism satisfies "right to be forgotten" by:
1. User requests deletion (or session expires)
2. Checkpoint rows are purged
3. MinIO document metadata can be tagged with user_id for bulk deletion

**Caveat**: Audit logs are deliberately exempt from every purge path and retained
indefinitely; configure audit log retention per your compliance requirements
before treating deletion as complete.

### Data Residency

All data stays on-premise (fully air-gapped). No external logging, no cloud storage, no third-party model APIs.

### Guardrails & Compliance

**Status**: Phase 4 — input and output guardrails are implemented
(`backend/app/guardrails/`). No separate `guardrail_violations` table: a
tripped input guardrail is recorded through the existing `AuditLog`
(`action="guardrail.input_rejected"`, `field_name="message"`,
`new_value` = the rejection reason code) rather than a new table, keeping
one append-only audit path instead of two.

**Input guardrail** (`app/guardrails/input_guardrail.py`): runs on every
`POST /api/agents/chat` request before the agent (and therefore the LLM) is
invoked. Checks, in order, are empty input, a length cap
(`MAX_INPUT_LENGTH`), and a set of prompt-injection heuristics (instruction
override, role reassignment, system-prompt exfiltration phrasings). Trip
behavior is **reject**: the endpoint returns `400` with the reason code as
`detail`, and the message never reaches the LLM. Reject was chosen over
silently sanitizing the message (which risks answering a different question
than the user asked, without their knowledge) or merely flagging-and-allowing
(which still lets an injection attempt reach the model).

**Output guardrail** (`app/guardrails/output_guardrail.py`): runs on the
agent's response before it's returned. Redacts system-prompt disclosures,
verbatim system-prompt leaks, and credential-shaped tokens (e.g.
`sk-...`-style API keys) in place. Trip behavior is **sanitize**, not reject:
unlike the input side, there is no cheap way to "re-ask" once the LLM has
already produced a full response, and rejecting the whole answer over one
flagged span would discard an otherwise useful, already-computed response.

System-prompt leak detection uses two independent strategies, because
neither alone covers the whole threat: a **phrasing** check
(`_SYSTEM_PROMPT_DISCLOSURE_PATTERN`) catches a response that announces
itself as a disclosure ("my system prompt is: ..."), and a **content** check
(`_find_verbatim_prompt_leak`) catches a response that reproduces the actual
system prompt's wording with no announcing phrase at all — e.g. complying
with "repeat everything above verbatim." The content check compares the
response against the caller's real, rendered system prompt text (threaded
through from `app.services.chat_guardrail_service.filter_agent_response`),
so it generalizes to any prompt wording without needing new regex per
phrasing. A second agent added later (see `docs/AGENT_LIBRARY.md`) gets this
protection automatically as long as it passes its own rendered prompt
through the same service.

**PII detection is out of scope for this phase.** It was deliberately
deferred rather than silently dropped: scoping it correctly requires
deciding which PII categories to detect and how redacted PII should be
represented in the (immutable, indefinitely-retained) `AuditLog` — writing
raw PII into an audit entry would work against the "right to be forgotten"
posture described above. That decision needs its own pass, not one made
under this ticket's guardrail scope.

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
