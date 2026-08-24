"""Tests for the rendered-manifest validator (infra/scripts/validate-rendered-manifests.py).

The validator is the CI-side guard for compliance controls that no Python
unit test can reach: unit tests run against SQLite and never open a Postgres
TLS connection, and no automated test in this phase performs a real TLS
handshake (see Phase 5 Decision 8's accepted risk). What CI *can* prove is
that the rendered YAML says the right thing — so these assertions are the
only thing standing between a template edit and a silent compliance
regression.

Each rule is tested with both a compliant fixture and a violating one. The
fixtures are small inline YAML strings, deliberately not real charts: no
charts exist yet, and `helm template` against a nonexistent chart errors out
rather than producing a manifest that fails an assertion. Red-because-broken
teaches nothing; red-because-unimplemented is TDD (Decision 7, item 3).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_VALIDATOR_PATH = Path(__file__).parent.parent / "scripts" / "validate-rendered-manifests.py"

# The script's filename contains hyphens, so it isn't importable by name.
# Load it by path instead of renaming the file, which the CI job invokes
# directly as `python infra/scripts/validate-rendered-manifests.py`.
_spec = importlib.util.spec_from_file_location("validate_rendered_manifests", _VALIDATOR_PATH)
validator = importlib.util.module_from_spec(_spec)
sys.modules["validate_rendered_manifests"] = validator
_spec.loader.exec_module(validator)


def violation_messages(rendered_yaml: str) -> str:
    """Join all violation messages so tests can assert on their content."""
    violations = validator.validate_manifests(rendered_yaml)
    return "\n".join(v.message for v in violations)


COMPLIANT_DEPLOYMENT = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
      containers:
        - name: backend
          image: eaistack/backend:latest
"""


@pytest.mark.unit
class TestRunAsNonRoot:
    """Rule 1: every Deployment/StatefulSet/CronJob runs as a non-root user."""

    def test_accepts_deployment_with_run_as_non_root(self):
        assert validator.validate_manifests(COMPLIANT_DEPLOYMENT) == []

    def test_flags_deployment_missing_run_as_non_root(self):
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      containers:
        - name: backend
          image: eaistack/backend:latest
"""
        message = violation_messages(rendered)
        assert "eaistack-backend" in message
        assert "securityContext.runAsNonRoot" in message

    def test_flags_deployment_with_run_as_non_root_false(self):
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-frontend
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: false
      containers:
        - name: frontend
          image: eaistack/frontend:latest
"""
        message = violation_messages(rendered)
        assert "eaistack-frontend" in message
        assert "runAsNonRoot" in message

    def test_accepts_statefulset_with_run_as_non_root(self):
        rendered = """
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: eaistack-postgres
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 999
      containers:
        - name: postgres
          image: pgvector/pgvector:pg16
"""
        assert validator.validate_manifests(rendered) == []

    def test_flags_statefulset_missing_run_as_non_root(self):
        rendered = """
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: eaistack-postgres
  namespace: eaistack
spec:
  template:
    spec:
      containers:
        - name: postgres
          image: pgvector/pgvector:pg16
"""
        assert "eaistack-postgres" in violation_messages(rendered)

    def test_accepts_cronjob_with_run_as_non_root_in_job_template(self):
        rendered = """
apiVersion: batch/v1
kind: CronJob
metadata:
  name: eaistack-retention-sweep
  namespace: eaistack
spec:
  schedule: "0 3 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
          containers:
            - name: retention-sweep
              image: eaistack/backend:latest
"""
        assert validator.validate_manifests(rendered) == []

    def test_flags_cronjob_missing_run_as_non_root_in_job_template(self):
        rendered = """
apiVersion: batch/v1
kind: CronJob
metadata:
  name: eaistack-retention-sweep
  namespace: eaistack
spec:
  schedule: "0 3 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: retention-sweep
              image: eaistack/backend:latest
"""
        assert "eaistack-retention-sweep" in violation_messages(rendered)

    def test_accepts_run_as_non_root_set_on_every_container(self):
        """A per-container securityContext satisfies the rule without a pod-level one."""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      containers:
        - name: backend
          image: eaistack/backend:latest
          securityContext:
            runAsNonRoot: true
"""
        assert validator.validate_manifests(rendered) == []

    def test_flags_deployment_where_only_one_container_runs_as_non_root(self):
        """A sidecar without the setting still runs as root, so the pod isn't compliant."""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      containers:
        - name: backend
          image: eaistack/backend:latest
          securityContext:
            runAsNonRoot: true
        - name: sidecar
          image: eaistack/sidecar:latest
"""
        assert "eaistack-backend" in violation_messages(rendered)


@pytest.mark.unit
class TestCredentialEnvVarsUseSecretKeyRef:
    """Rule 2: credential-shaped env vars come from Secrets, never a literal value."""

    def test_accepts_database_url_from_secret_key_ref(self):
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: backend
          image: eaistack/backend:latest
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: eaistack-backend
                  key: database-url
"""
        assert validator.validate_manifests(rendered) == []

    def test_flags_hardcoded_database_url(self):
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: backend
          image: eaistack/backend:latest
          env:
            - name: DATABASE_URL
              value: "postgresql://eaistack:hunter2@eaistack-postgres:5432/eaistack"
"""
        message = violation_messages(rendered)
        assert "eaistack-backend" in message
        assert "DATABASE_URL" in message
        assert "secretKeyRef" in message

    def test_flags_hardcoded_keycloak_client_secret(self):
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: backend
          image: eaistack/backend:latest
          env:
            - name: KEYCLOAK_CLIENT_SECRET
              value: "eaistack-api-secret"
"""
        message = violation_messages(rendered)
        assert "KEYCLOAK_CLIENT_SECRET" in message
        assert "secretKeyRef" in message

    def test_flags_hardcoded_minio_secret_key(self):
        """MINIO_* is matched by prefix so new MinIO credentials are covered automatically."""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-minio
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: minio
          image: minio/minio:latest
          env:
            - name: MINIO_SECRET_KEY
              value: "minioadmin"
"""
        assert "MINIO_SECRET_KEY" in violation_messages(rendered)

    def test_accepts_non_credential_env_var_with_literal_value(self):
        """Non-secret config is legitimately a literal; the rule must not fire on it."""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-doc-search
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: doc-search
          image: eaistack/doc-search:latest
          env:
            - name: KEYCLOAK_REALM
              value: "eaistack"
            - name: EMBEDDING_MODEL
              value: "nomic-embed-text-v1.5.Q4_K_M.gguf"
"""
        assert validator.validate_manifests(rendered) == []

    def test_flags_hardcoded_credential_in_cronjob(self):
        """The retention CronJob carries DATABASE_URL too, so it needs the same guard."""
        rendered = """
apiVersion: batch/v1
kind: CronJob
metadata:
  name: eaistack-retention-sweep
  namespace: eaistack
spec:
  schedule: "0 3 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          securityContext:
            runAsNonRoot: true
          containers:
            - name: retention-sweep
              image: eaistack/backend:latest
              env:
                - name: DATABASE_URL
                  value: "postgresql://eaistack:hunter2@eaistack-postgres:5432/eaistack"
"""
        message = violation_messages(rendered)
        assert "eaistack-retention-sweep" in message
        assert "DATABASE_URL" in message


@pytest.mark.unit
class TestHttpsUrlRequiresCertificate:
    """Rule 3: a Deployment configured with an https:// peer needs a Certificate."""

    def test_accepts_https_deployment_with_matching_certificate(self):
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: backend
          image: eaistack/backend:latest
          env:
            - name: DOC_SEARCH_URL
              value: "https://eaistack-doc-search:8100/mcp"
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  secretName: eaistack-backend-tls
  issuerRef:
    name: eaistack-ca-issuer
    kind: ClusterIssuer
"""
        assert validator.validate_manifests(rendered) == []

    def test_flags_https_deployment_without_certificate(self):
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: backend
          image: eaistack/backend:latest
          env:
            - name: DOC_SEARCH_URL
              value: "https://eaistack-doc-search:8100/mcp"
"""
        message = violation_messages(rendered)
        assert "eaistack-backend" in message
        assert "Certificate" in message

    def test_accepts_http_only_deployment_without_certificate(self):
        """llama-server may stay plaintext (Decision 5), so http:// must not require a cert."""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-llama-server
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: llama-server
          image: eaistack/llama-server:latest
          env:
            - name: LLM_URL
              value: "http://eaistack-llama-server:8080/v1"
"""
        assert validator.validate_manifests(rendered) == []

    def test_detects_https_url_in_container_args(self):
        """An https:// peer configured via args is the same exposure as one via env."""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: backend
          image: eaistack/backend:latest
          args:
            - "--doc-search-url=https://eaistack-doc-search:8100/mcp"
"""
        assert "eaistack-backend" in violation_messages(rendered)


@pytest.mark.unit
class TestNamespaceIsEaistack:
    """Rule 4: everything lands in the eaistack namespace."""

    def test_accepts_resources_in_eaistack_namespace(self):
        assert validator.validate_manifests(COMPLIANT_DEPLOYMENT) == []

    def test_flags_resource_in_wrong_namespace(self):
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: default
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: backend
          image: eaistack/backend:latest
"""
        message = violation_messages(rendered)
        assert "eaistack-backend" in message
        assert "default" in message
        assert "namespace" in message

    def test_flags_namespaced_resource_with_no_namespace_set(self):
        """An unset namespace lands wherever kubectl's context points — not a guarantee."""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: backend
          image: eaistack/backend:latest
"""
        message = violation_messages(rendered)
        assert "eaistack-backend" in message
        assert "namespace" in message

    def test_accepts_cluster_scoped_resource_without_namespace(self):
        """A ClusterIssuer has no namespace by definition; the rule must not fire on it."""
        rendered = """
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: eaistack-ca-issuer
spec:
  ca:
    secretName: eaistack-ca-key-pair
"""
        assert validator.validate_manifests(rendered) == []

    def test_accepts_the_eaistack_namespace_resource_itself(self):
        """The Namespace object names the namespace rather than living in one."""
        rendered = """
apiVersion: v1
kind: Namespace
metadata:
  name: eaistack
"""
        assert validator.validate_manifests(rendered) == []

    def test_flags_a_namespace_resource_with_the_wrong_name(self):
        rendered = """
apiVersion: v1
kind: Namespace
metadata:
  name: production
"""
        assert "production" in violation_messages(rendered)


@pytest.mark.unit
class TestPersistentVolumeClaimStorageClass:
    """Rule 5: every PVC names a StorageClass (Decision 6's at-rest compliance gate)."""

    def test_accepts_pvc_with_storage_class_name(self):
        rendered = """
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: eaistack-postgres-data
  namespace: eaistack
spec:
  storageClassName: encrypted-local-path
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
"""
        assert validator.validate_manifests(rendered) == []

    def test_flags_pvc_missing_storage_class_name(self):
        rendered = """
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: eaistack-postgres-data
  namespace: eaistack
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
"""
        message = violation_messages(rendered)
        assert "eaistack-postgres-data" in message
        assert "storageClassName" in message

    def test_flags_pvc_with_empty_storage_class_name(self):
        """An empty string is Kubernetes' explicit opt-out of dynamic provisioning."""
        rendered = """
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: eaistack-minio-data
  namespace: eaistack
spec:
  storageClassName: ""
  accessModes:
    - ReadWriteOnce
"""
        assert "eaistack-minio-data" in violation_messages(rendered)

    def test_storage_class_violation_names_the_compliance_requirement(self):
        """The message must say this is a hard compliance gate, not a style preference."""
        rendered = """
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: eaistack-postgres-data
  namespace: eaistack
spec:
  accessModes:
    - ReadWriteOnce
"""
        message = violation_messages(rendered).lower()
        assert "compliance" in message
        assert "encryption at rest" in message

    def test_flags_volume_claim_template_missing_storage_class_name(self):
        """A StatefulSet's volumeClaimTemplates create PVCs, so they need the same gate."""
        rendered = """
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: eaistack-postgres
  namespace: eaistack
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: postgres
          image: pgvector/pgvector:pg16
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes:
          - ReadWriteOnce
        resources:
          requests:
            storage: 10Gi
"""
        message = violation_messages(rendered)
        assert "storageClassName" in message
        assert "data" in message


@pytest.mark.unit
class TestDatabaseUrlSslMode:
    """Rule 6: the Postgres hop verifies the certificate and hostname (Decision 10)."""

    COMPLIANT_SECRET = """
apiVersion: v1
kind: Secret
metadata:
  name: eaistack-backend
  namespace: eaistack
stringData:
  database-url: "postgresql://eaistack:pw@eaistack-postgres:5432/eaistack?sslmode=verify-full&sslrootcert=/etc/ssl/eaistack/ca.crt"
"""

    def test_accepts_database_url_with_verify_full_and_sslrootcert(self):
        assert validator.validate_manifests(self.COMPLIANT_SECRET) == []

    def test_flags_database_url_with_sslmode_require(self):
        rendered = """
apiVersion: v1
kind: Secret
metadata:
  name: eaistack-backend
  namespace: eaistack
stringData:
  database-url: "postgresql://eaistack:pw@eaistack-postgres:5432/eaistack?sslmode=require&sslrootcert=/etc/ssl/eaistack/ca.crt"
"""
        message = violation_messages(rendered)
        assert "eaistack-backend" in message
        assert "verify-full" in message
        assert "require" in message

    def test_sslmode_require_violation_explains_the_mitm_exposure(self):
        """`require` looks identical to verify-full in a connection test, so say why it isn't."""
        rendered = """
apiVersion: v1
kind: Secret
metadata:
  name: eaistack-backend
  namespace: eaistack
stringData:
  database-url: "postgresql://eaistack:pw@eaistack-postgres:5432/eaistack?sslmode=require"
"""
        message = violation_messages(rendered).lower()
        assert "mitm" in message or "man-in-the-middle" in message

    def test_flags_database_url_with_no_sslmode(self):
        rendered = """
apiVersion: v1
kind: Secret
metadata:
  name: eaistack-backend
  namespace: eaistack
stringData:
  database-url: "postgresql://eaistack:pw@eaistack-postgres:5432/eaistack"
"""
        message = violation_messages(rendered)
        assert "sslmode" in message
        assert "eaistack-backend" in message

    def test_flags_database_url_with_verify_full_but_no_sslrootcert(self):
        """verify-full without a CA path can't validate anything against the internal CA."""
        rendered = """
apiVersion: v1
kind: Secret
metadata:
  name: eaistack-backend
  namespace: eaistack
stringData:
  database-url: "postgresql://eaistack:pw@eaistack-postgres:5432/eaistack?sslmode=verify-full"
"""
        assert "sslrootcert" in violation_messages(rendered)

    def test_reads_base64_encoded_database_url_from_secret_data(self):
        """Helm may render the Secret's `data` (base64) rather than `stringData`."""
        import base64

        url = "postgresql://eaistack:pw@eaistack-postgres:5432/eaistack?sslmode=require"
        encoded = base64.b64encode(url.encode()).decode()
        rendered = f"""
apiVersion: v1
kind: Secret
metadata:
  name: eaistack-backend
  namespace: eaistack
data:
  database-url: "{encoded}"
"""
        assert "verify-full" in violation_messages(rendered)

    def test_accepts_base64_encoded_compliant_database_url(self):
        import base64

        url = (
            "postgresql://eaistack:pw@eaistack-postgres:5432/eaistack"
            "?sslmode=verify-full&sslrootcert=/etc/ssl/eaistack/ca.crt"
        )
        encoded = base64.b64encode(url.encode()).decode()
        rendered = f"""
apiVersion: v1
kind: Secret
metadata:
  name: eaistack-backend
  namespace: eaistack
data:
  database-url: "{encoded}"
"""
        assert validator.validate_manifests(rendered) == []


@pytest.mark.unit
class TestMultiDocumentParsing:
    """The validator's input is always a multi-doc render, not a single manifest."""

    def test_reports_violations_from_every_document(self):
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      containers:
        - name: backend
          image: eaistack/backend:latest
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: eaistack-minio-data
  namespace: eaistack
spec:
  accessModes:
    - ReadWriteOnce
"""
        message = violation_messages(rendered)
        assert "eaistack-backend" in message
        assert "eaistack-minio-data" in message

    def test_ignores_empty_documents_from_helm_conditionals(self):
        """A false `{{ if }}` renders an empty doc; that's normal, not a parse failure."""
        rendered = f"---\n{COMPLIANT_DEPLOYMENT}\n---\n---\n# comment only\n"
        assert validator.validate_manifests(rendered) == []


@pytest.mark.unit
class TestExitCodes:
    """The CI job gates on the exit code, so it has to be right."""

    def test_exits_zero_when_all_rules_pass(self, tmp_path):
        manifest = tmp_path / "rendered.yaml"
        manifest.write_text(COMPLIANT_DEPLOYMENT, encoding="utf-8")
        assert validator.main([str(manifest)]) == 0

    def test_exits_non_zero_when_a_rule_is_violated(self, tmp_path):
        manifest = tmp_path / "rendered.yaml"
        manifest.write_text(
            """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eaistack-backend
  namespace: eaistack
spec:
  template:
    spec:
      containers:
        - name: backend
          image: eaistack/backend:latest
""",
            encoding="utf-8",
        )
        assert validator.main([str(manifest)]) != 0

    def test_exits_non_zero_when_the_manifest_file_is_missing(self, tmp_path):
        assert validator.main([str(tmp_path / "does-not-exist.yaml")]) != 0
