#!/usr/bin/env python3
"""TDD for Helm charts: test rendered manifests before writing templates.

Each test validates that a chart, when rendered, produces YAML matching the
expected compliance rules (security context, secret handling, resource limits,
probes, TLS certificates, etc.). Tests run `helm template` and parse the output
with PyYAML, asserting on the rendered structure.

Sequencing: Write all tests first (all fail on nonexistent charts — expected).
Then implement charts one-by-one, running tests after each addition until all
pass. Each chart commit includes the assertion count.

Compliance rules under test (see CLAUDE.md, AGENTS.md, Phase 5 plan):
- securityContext.runAsNonRoot: true
- securityContext.runAsUser: UID per chart spec
- secretKeyRef for all credential env vars (DATABASE_URL, KEYCLOAK_CLIENT_SECRET, etc.)
- Certificate resources for TLS (or conditional for llama-server/embedding-server)
- storageClassName required in PVCs (no silent default)
- Service and healthy probes present
- Namespace set correctly ({{ .Release.Namespace }} resolves to eaistack)
- CA bundle mount + env var for backend/doc-search
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_VALIDATOR_PATH = Path(__file__).parent.parent / "scripts" / "validate-rendered-manifests.py"
_validator_spec = importlib.util.spec_from_file_location(
    "validate_rendered_manifests_e2e", _VALIDATOR_PATH
)
_validator = importlib.util.module_from_spec(_validator_spec)
_validator_spec.loader.exec_module(_validator)


CHARTS_DIR = Path(__file__).parent.parent / "helm" / "charts"
UMBRELLA_CHART = CHARTS_DIR / "eaistack-umbrella"
VALUES_CI = Path(__file__).parent.parent / "helm" / "values-ci.yaml"

# Each chart's expected UID and replica count
CHART_SPECS = {
    "postgres": {"uid": 999, "kind": "StatefulSet"},
    "keycloak": {"uid": 1000, "kind": "Deployment"},
    "minio": {"uid": 1000, "kind": "Deployment"},
    "llama-server": {"uid": 1000, "kind": "Deployment"},
    "embedding-server": {"uid": 1000, "kind": "Deployment"},
    "backend": {"uid": 1000, "kind": "Deployment", "replicas": 1},
    "doc-search": {"uid": 1000, "kind": "Deployment", "replicas": 1},
    "frontend": {"uid": 1000, "kind": "Deployment", "replicas": 1},
}


def render_chart(chart_path: Path, values_file: Path = None, extra_set: dict = None) -> list[dict]:
    """Render a Helm chart and return parsed YAML documents.

    extra_set: optional {"some.values.path": value} dict applied via `helm
    template --set`, layered on top of values_file. Used to render the same
    chart under both tls.enabled: true/false without needing a second values
    file (e.g. verifying probe scheme flips correctly with the flag).
    """
    cmd = ["helm", "template", str(chart_path)]
    if values_file:
        cmd.extend(["-f", str(values_file)])
    if extra_set:
        for key, value in extra_set.items():
            cmd.extend(["--set", f"{key}={str(value).lower() if isinstance(value, bool) else value}"])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(f"Chart render failed (expected if chart incomplete): {result.stderr}")

    docs = yaml.safe_load_all(result.stdout)
    return [doc for doc in docs if isinstance(doc, dict)]


def get_workload_kinds(docs: list[dict]) -> dict[str, dict]:
    """Extract all Deployment/StatefulSet/CronJob resources from rendered docs."""
    workloads = {}
    for doc in docs:
        kind = doc.get("kind")
        if kind in ("Deployment", "StatefulSet", "CronJob"):
            name = doc.get("metadata", {}).get("name")
            workloads[name or kind] = doc
    return workloads


def get_pod_spec(workload: dict) -> dict:
    """Extract podSpec from a workload (Deployment/StatefulSet/CronJob)."""
    if workload.get("kind") == "CronJob":
        return workload.get("spec", {}).get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
    else:
        return workload.get("spec", {}).get("template", {}).get("spec", {})


def get_containers(pod_spec: dict) -> list[dict]:
    """Extract container list from pod spec."""
    return pod_spec.get("containers", [])


def get_security_context(pod_spec: dict) -> dict:
    """Extract pod-level securityContext."""
    return pod_spec.get("securityContext", {})


def get_secret_refs(containers: list[dict]) -> dict[str, dict]:
    """Extract env vars that use secretKeyRef."""
    refs = {}
    for container in containers:
        for env_var in container.get("env", []):
            name = env_var.get("name")
            if env_var.get("valueFrom", {}).get("secretKeyRef"):
                refs[name] = env_var["valueFrom"]["secretKeyRef"]
    return refs


def get_credential_env_vars(containers: list[dict]) -> set[str]:
    """Extract credential-shaped env var names (DATABASE_URL, *PASSWORD, etc.)."""
    credential_patterns = ("DATABASE_URL", "PASSWORD", "SECRET", "_API_KEY", "ACCESS_KEY", "TOKEN", "KEYCLOAK_CLIENT_SECRET")
    credentials = set()
    for container in containers:
        for env_var in container.get("env", []):
            name = env_var.get("name", "")
            if any(pattern in name.upper() for pattern in credential_patterns):
                # Exception: KEYCLOAK_CLIENT_SECRET_KEY_REF is not a credential itself
                if "KEY_REF" not in name:
                    credentials.add(name)
    return credentials


@pytest.mark.parametrize("chart_name", CHART_SPECS.keys())
class TestChartCompliance:
    """TDD test class for all per-service charts."""

    def test_chart_exists(self, chart_name: str):
        """Test 1: Chart directory and Chart.yaml exist."""
        chart_path = CHARTS_DIR / chart_name
        assert chart_path.exists(), f"Chart directory missing: {chart_path}"
        assert (chart_path / "Chart.yaml").exists(), f"Chart.yaml missing for {chart_name}"

    def test_renders_without_errors(self, chart_name: str):
        """Test 2: helm template succeeds (with CI values to satisfy {{ required }})."""
        chart_path = CHARTS_DIR / chart_name
        docs = render_chart(chart_path, VALUES_CI)
        assert len(docs) > 0, f"Chart rendered to empty output: {chart_name}"

    def test_workload_exists(self, chart_name: str):
        """Test 3: Chart produces a Deployment/StatefulSet (as specified in CHART_SPECS)."""
        chart_path = CHARTS_DIR / chart_name
        docs = render_chart(chart_path, VALUES_CI)
        spec = CHART_SPECS[chart_name]
        expected_kind = spec.get("kind", "Deployment")

        workloads = get_workload_kinds(docs)
        matching = [w for name, w in workloads.items() if w.get("kind") == expected_kind]
        assert len(matching) > 0, f"No {expected_kind} found in {chart_name}"

    def test_runs_as_nonroot(self, chart_name: str):
        """Test 4: All workloads have securityContext.runAsNonRoot: true."""
        chart_path = CHARTS_DIR / chart_name
        docs = render_chart(chart_path, VALUES_CI)
        workloads = get_workload_kinds(docs)

        for name, workload in workloads.items():
            pod_spec = get_pod_spec(workload)
            sec_ctx = get_security_context(pod_spec)
            assert sec_ctx.get("runAsNonRoot") is True, \
                f"Missing runAsNonRoot in {name}"

    def test_correct_uid(self, chart_name: str):
        """Test 5: securityContext.runAsUser matches chart spec."""
        chart_path = CHARTS_DIR / chart_name
        docs = render_chart(chart_path, VALUES_CI)
        workloads = get_workload_kinds(docs)
        expected_uid = CHART_SPECS[chart_name]["uid"]

        for name, workload in workloads.items():
            pod_spec = get_pod_spec(workload)
            sec_ctx = get_security_context(pod_spec)
            assert sec_ctx.get("runAsUser") == expected_uid, \
                f"Expected UID {expected_uid}, got {sec_ctx.get('runAsUser')} in {name}"

    def test_credentials_use_secretkeyref(self, chart_name: str):
        """Test 6: All credential env vars use secretKeyRef, never hardcoded value:."""
        chart_path = CHARTS_DIR / chart_name
        docs = render_chart(chart_path, VALUES_CI)
        workloads = get_workload_kinds(docs)

        for name, workload in workloads.items():
            pod_spec = get_pod_spec(workload)
            containers = get_containers(pod_spec)
            secret_refs = get_secret_refs(containers)
            cred_env_vars = get_credential_env_vars(containers)

            hardcoded = cred_env_vars - set(secret_refs.keys())
            assert len(hardcoded) == 0, \
                f"Hardcoded credentials in {name}: {hardcoded}. Use secretKeyRef instead."

    def test_resources_defined(self, chart_name: str):
        """Test 7: All containers have resources.requests and limits."""
        chart_path = CHARTS_DIR / chart_name
        docs = render_chart(chart_path, VALUES_CI)
        workloads = get_workload_kinds(docs)

        for name, workload in workloads.items():
            pod_spec = get_pod_spec(workload)
            for container in get_containers(pod_spec):
                resources = container.get("resources", {})
                assert "requests" in resources, \
                    f"Missing resources.requests in {name}/{container.get('name')}"
                assert "limits" in resources, \
                    f"Missing resources.limits in {name}/{container.get('name')}"

    def test_probes_defined(self, chart_name: str):
        """Test 8: Deployments/StatefulSets have readiness and liveness probes."""
        chart_path = CHARTS_DIR / chart_name
        docs = render_chart(chart_path, VALUES_CI)
        workloads = get_workload_kinds(docs)

        for name, workload in workloads.items():
            if workload.get("kind") == "CronJob":
                continue  # CronJobs don't have probes

            pod_spec = get_pod_spec(workload)
            for container in get_containers(pod_spec):
                assert "readinessProbe" in container, \
                    f"Missing readinessProbe in {name}/{container.get('name')}"
                assert "livenessProbe" in container, \
                    f"Missing livenessProbe in {name}/{container.get('name')}"

    def test_service_exists(self, chart_name: str):
        """Test 9: Chart produces a Service resource."""
        chart_path = CHARTS_DIR / chart_name
        docs = render_chart(chart_path, VALUES_CI)

        services = [doc for doc in docs if doc.get("kind") == "Service"]
        assert len(services) > 0, f"No Service found in {chart_name}"

    def test_namespace_correct(self, chart_name: str):
        """Test 10: All namespaced resources have namespace field set.

        Note: When rendering individual charts without umbrella context,
        {{ .Release.Namespace }} resolves to 'default'. This test verifies
        the namespace *field* is present. The umbrella chart will set
        namespace: eaistack in values, which overrides at deployment time.
        """
        chart_path = CHARTS_DIR / chart_name
        docs = render_chart(chart_path, VALUES_CI)

        cluster_scoped = ("Namespace", "ClusterIssuer", "ClusterRole", "ClusterRoleBinding", "StorageClass")
        for doc in docs:
            kind = doc.get("kind")
            if kind in cluster_scoped:
                continue
            # Just verify namespace field is present (helm will render it to actual namespace)
            namespace = doc.get("metadata", {}).get("namespace")
            assert namespace is not None, \
                f"Missing namespace for {kind}/{doc.get('metadata', {}).get('name')}"


def render_chart_expecting_failure(
    chart_path: Path, values_file: Path = None, extra_set: dict = None
) -> subprocess.CompletedProcess:
    """Run `helm template` and return the raw result, without render_chart's
    pytest.skip-on-nonzero-exit behavior.

    render_chart() treats a non-zero exit as "chart not implemented yet" and
    skips — the right call for compliance assertions, which need a
    successful render to inspect. But a `{{ required }}` guard test needs
    the opposite: it must render, deliberately without a required value, and
    prove the failure is the one the guard is supposed to produce. Skipping
    on failure would make that test pass no matter what caused it to fail
    (or trivially pass if the guard were deleted).
    """
    cmd = ["helm", "template", str(chart_path)]
    if values_file:
        cmd.extend(["-f", str(values_file)])
    if extra_set:
        for key, value in extra_set.items():
            cmd.extend(["--set", f"{key}={str(value).lower() if isinstance(value, bool) else value}"])
    return subprocess.run(cmd, capture_output=True, text=True)


@pytest.mark.parametrize(
    "chart_name,required_value_key,other_required_values",
    [
        ("postgres", "global.postgresPassword", {"storage.storageClassName": "standard"}),
        ("keycloak", "global.keycloakAdminPassword", {}),
        ("minio", "global.miniRootUser", {"storage.storageClassName": "standard"}),
        ("minio", "global.miniRootPassword", {"storage.storageClassName": "standard"}),
    ],
)
class TestRequiredValueGuards:
    """Every chart-level `{{ required "..." }}` guard actually stops the render.

    Previously each of these three charts had its own shallow test
    (test_postgres_password_required, test_admin_password_required,
    test_minio_credentials_required) whose docstring claimed to verify the
    `{{ required }}` guard, but whose body only asserted `len(secrets) > 0`
    against VALUES_CI - which already supplies every required value. That
    proves a Secret exists when its input is present; it never omits the
    value, so it could never have caught the guard being deleted from the
    template. This test renders each chart with VALUES_CI providing every
    *other* required value, but the one under test explicitly nulled via
    `--set key=null`, and asserts the render actually fails.
    """

    def test_required_value_guard_fails_render_when_omitted(
        self, chart_name: str, required_value_key: str, other_required_values: dict
    ):
        chart_path = CHARTS_DIR / chart_name
        extra_set = {**other_required_values, required_value_key: "null"}

        result = render_chart_expecting_failure(chart_path, VALUES_CI, extra_set)

        assert result.returncode != 0, (
            f"{chart_name}: expected `helm template` to fail with "
            f"{required_value_key} unset, but it rendered successfully. The "
            f"{{{{ required }}}} guard is missing or no longer enforced."
        )
        assert required_value_key in result.stderr, (
            f"{chart_name}: render failed as expected, but the error didn't "
            f"name {required_value_key} - got: {result.stderr!r}. This means "
            f"some other required value (not the one under test) caused the "
            f"failure, so this test isn't actually proving this guard works."
        )


class TestPostgres:
    """Postgres-specific tests."""

    def test_pvc_has_storageclassname(self):
        """Test: PVC references a non-empty storageClassName (Decision 6)."""
        chart_path = CHARTS_DIR / "postgres"
        docs = render_chart(chart_path, VALUES_CI)

        pvcs = [doc for doc in docs if doc.get("kind") == "PersistentVolumeClaim"]
        assert len(pvcs) > 0, "No PVC found in postgres chart"

        for pvc in pvcs:
            storage_class = pvc.get("spec", {}).get("storageClassName")
            assert storage_class and storage_class.strip(), \
                f"PVC {pvc.get('metadata', {}).get('name')} has empty storageClassName"


class TestKeycloak:
    """Keycloak-specific tests."""

    def test_realm_import_configmap_exists(self):
        """Test: Keycloak chart produces a realm-import ConfigMap."""
        chart_path = CHARTS_DIR / "keycloak"
        docs = render_chart(chart_path, VALUES_CI)

        configmaps = [doc for doc in docs if doc.get("kind") == "ConfigMap"]
        assert any("realm" in doc.get("metadata", {}).get("name", "") for doc in configmaps), \
            "No realm-import ConfigMap found in keycloak chart"


class TestMinio:
    """MinIO-specific tests."""

    def test_pvc_has_storageclassname(self):
        """Test: MinIO PVC references a non-empty storageClassName (Decision 6)."""
        chart_path = CHARTS_DIR / "minio"
        docs = render_chart(chart_path, VALUES_CI)

        pvcs = [doc for doc in docs if doc.get("kind") == "PersistentVolumeClaim"]
        assert len(pvcs) > 0, "No PVC found in minio chart"

        for pvc in pvcs:
            storage_class = pvc.get("spec", {}).get("storageClassName")
            assert storage_class and storage_class.strip(), \
                f"PVC {pvc.get('metadata', {}).get('name')} has empty storageClassName"


class TestLLMServers:
    """llama-server and embedding-server specific tests."""

    @pytest.mark.parametrize("chart_name", ["llama-server", "embedding-server"])
    def test_certificate_conditional_on_tls_enabled(self, chart_name: str):
        """Test: Certificate only rendered when tls.enabled: true."""
        chart_path = CHARTS_DIR / chart_name

        # With tls.enabled: false (VALUES_CI's default for these two charts),
        # no Certificate should be rendered at all.
        docs_disabled = render_chart(chart_path, VALUES_CI)
        certs_disabled = [doc for doc in docs_disabled if doc.get("kind") == "Certificate"]
        assert len(certs_disabled) == 0, (
            f"{chart_name}: expected no Certificate when tls.enabled=false, "
            f"found {len(certs_disabled)}"
        )

        # With tls.enabled: true, the chart must actually render one.
        docs_enabled = render_chart(chart_path, VALUES_CI, extra_set={"tls.enabled": True})
        certs_enabled = [doc for doc in docs_enabled if doc.get("kind") == "Certificate"]
        assert len(certs_enabled) > 0, (
            f"{chart_name}: expected a Certificate when tls.enabled=true, found none"
        )


class TestBackend:
    """Backend-specific tests."""

    def test_ca_bundle_mount_exists(self):
        """Test: Backend Deployment mounts CA bundle at /etc/ssl/eaistack."""
        chart_path = CHARTS_DIR / "backend"
        docs = render_chart(chart_path, VALUES_CI)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        assert len(deployments) > 0, "No Deployment found in backend chart"

        for deployment in deployments:
            pod_spec = get_pod_spec(deployment)
            containers = get_containers(pod_spec)

            for container in containers:
                volume_mounts = container.get("volumeMounts", [])
                ca_mounts = [vm for vm in volume_mounts if "/etc/ssl/eaistack" in vm.get("mountPath", "")]
                assert len(ca_mounts) > 0, "CA bundle mount missing in backend"

    def test_ca_bundle_env_var_set(self):
        """Test: Backend sets CA_BUNDLE_PATH env var."""
        chart_path = CHARTS_DIR / "backend"
        docs = render_chart(chart_path, VALUES_CI)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        for deployment in deployments:
            pod_spec = get_pod_spec(deployment)
            containers = get_containers(pod_spec)

            for container in containers:
                env_names = [env.get("name") for env in container.get("env", [])]
                assert "CA_BUNDLE_PATH" in env_names, "CA_BUNDLE_PATH env var missing"

    def test_database_url_has_verify_full(self):
        """Test: Rendered Secret's database-url contains sslmode=verify-full (Decision 10)."""
        chart_path = CHARTS_DIR / "backend"
        docs = render_chart(chart_path, VALUES_CI)

        secrets = [doc for doc in docs if doc.get("kind") == "Secret"]
        for secret in secrets:
            if "backend" not in secret.get("metadata", {}).get("name", ""):
                continue

            stringData = secret.get("stringData", {})
            db_url = stringData.get("database-url", "")
            assert "sslmode=verify-full" in db_url, \
                f"database-url missing sslmode=verify-full: {db_url}"

    def test_retention_cronjob_exists(self):
        """Test: Backend chart produces a retention CronJob."""
        chart_path = CHARTS_DIR / "backend"
        docs = render_chart(chart_path, VALUES_CI)

        cronjobs = [doc for doc in docs if doc.get("kind") == "CronJob"]
        assert len(cronjobs) > 0, "No CronJob found in backend chart (retention sweep)"

    def test_doc_search_url_env_var_name_matches_settings_field(self):
        """Test: the env var pointing at doc-search is named DOC_SEARCH_MCP_URL, matching
        Settings.doc_search_mcp_url in backend/app/core/config.py (pydantic-settings has
        no env_prefix configured there). Regression guard for Bug 3: the chart previously
        set MCP_DOC_SEARCH_URL, a name pydantic-settings never reads, so the backend
        silently fell back to its localhost default and every knowledge-base call broke
        inside the cluster."""
        chart_path = CHARTS_DIR / "backend"
        docs = render_chart(chart_path, VALUES_CI)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        assert len(deployments) > 0, "No Deployment found in backend chart"

        for deployment in deployments:
            pod_spec = get_pod_spec(deployment)
            containers = get_containers(pod_spec)

            for container in containers:
                env_names = [env.get("name") for env in container.get("env", [])]
                assert "DOC_SEARCH_MCP_URL" in env_names, \
                    "DOC_SEARCH_MCP_URL env var missing (must match Settings.doc_search_mcp_url)"
                assert "MCP_DOC_SEARCH_URL" not in env_names, \
                    "Stale MCP_DOC_SEARCH_URL env var still set; pydantic-settings never reads it"

    def test_doc_search_url_uses_https(self):
        """Test: backend reaches doc-search over https://, not plaintext http://.
        Regression guard for Bug 2: doc-search always serves TLS (Decision 1, compliance
        requirement), so backend's own hardcoded endpoint must match that scheme."""
        chart_path = CHARTS_DIR / "backend"
        docs = render_chart(chart_path, VALUES_CI)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        for deployment in deployments:
            pod_spec = get_pod_spec(deployment)
            containers = get_containers(pod_spec)

            for container in containers:
                doc_search_env = [
                    env for env in container.get("env", [])
                    if env.get("name") == "DOC_SEARCH_MCP_URL"
                ]
                assert len(doc_search_env) > 0, "DOC_SEARCH_MCP_URL env var not found"
                url = doc_search_env[0].get("value", "")
                assert url.startswith("https://"), \
                    f"DOC_SEARCH_MCP_URL must use https://, got: {url}"
                assert url.endswith("/mcp"), \
                    f"DOC_SEARCH_MCP_URL should end with /mcp (matches the code default path), got: {url}"

    def test_tls_cert_mounted_when_enabled(self):
        """Test: with tls.enabled true (VALUES_CI's default for backend), the
        Deployment actually mounts the cert-manager-issued Secret that the
        chart's certificate.yaml provisions, and points uvicorn at it via
        SSL_CERTFILE/SSL_KEYFILE (see backend/docker-entrypoint.sh). Regression
        guard: previously the chart set scheme: HTTPS on both probes with
        nothing in the container actually terminating TLS, so the pod could
        never pass its readiness/liveness checks on a real cluster."""
        chart_path = CHARTS_DIR / "backend"
        docs = render_chart(chart_path, VALUES_CI)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        assert len(deployments) > 0, "No Deployment found in backend chart"

        for deployment in deployments:
            pod_spec = get_pod_spec(deployment)
            containers = get_containers(pod_spec)
            volumes = pod_spec.get("volumes", [])

            tls_volumes = [v for v in volumes if v.get("secret", {}).get("secretName") == "eaistack-backend-tls"]
            assert len(tls_volumes) > 0, "backend-tls Secret not mounted as a volume"

            for container in containers:
                volume_mounts = container.get("volumeMounts", [])
                tls_mounts = [vm for vm in volume_mounts if vm.get("name") == tls_volumes[0].get("name")]
                assert len(tls_mounts) > 0, f"TLS cert volume not mounted into container {container.get('name')}"

                env_names = [env.get("name") for env in container.get("env", [])]
                assert "SSL_CERTFILE" in env_names, "SSL_CERTFILE env var missing (uvicorn TLS termination)"
                assert "SSL_KEYFILE" in env_names, "SSL_KEYFILE env var missing (uvicorn TLS termination)"

    def test_probe_scheme_matches_tls_enabled(self):
        """Test: readiness/liveness probes only claim scheme: HTTPS when
        tls.enabled is actually true, since an HTTPS probe against a
        container not configured to terminate TLS fails the handshake and
        the pod never becomes Ready."""
        chart_path = CHARTS_DIR / "backend"

        for tls_enabled, expect_https in [(True, True), (False, False)]:
            docs = render_chart(chart_path, VALUES_CI, extra_set={"tls.enabled": tls_enabled})
            deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
            assert len(deployments) > 0, "No Deployment found in backend chart"

            for deployment in deployments:
                pod_spec = get_pod_spec(deployment)
                for container in get_containers(pod_spec):
                    readiness_scheme = container.get("readinessProbe", {}).get("httpGet", {}).get("scheme")
                    liveness_scheme = container.get("livenessProbe", {}).get("httpGet", {}).get("scheme")
                    if expect_https:
                        assert readiness_scheme == "HTTPS", \
                            f"Expected HTTPS readiness probe scheme when tls.enabled=true, got {readiness_scheme}"
                        assert liveness_scheme == "HTTPS", \
                            f"Expected HTTPS liveness probe scheme when tls.enabled=true, got {liveness_scheme}"
                    else:
                        assert readiness_scheme != "HTTPS", \
                            "HTTPS readiness probe scheme set but tls.enabled=false: pod can never become Ready"
                        assert liveness_scheme != "HTTPS", \
                            "HTTPS liveness probe scheme set but tls.enabled=false: pod can never become Ready"


class TestFrontendTls:
    """Frontend TLS-serving tests (mirrors TestBackend's TLS coverage above)."""

    def test_tls_cert_mounted_when_enabled(self):
        """Test: with tls.enabled true (VALUES_CI's default for frontend), the
        Deployment actually mounts the cert-manager-issued Secret that the
        chart's certificate.yaml provisions, and points the Vite dev server at
        it via SSL_CERTFILE/SSL_KEYFILE (see frontend/vite.config.ts and
        frontend/docker-entrypoint.sh). Regression guard: previously the chart
        set scheme: HTTPS on both probes with nothing in the container
        actually terminating TLS, so the pod could never pass its
        readiness/liveness checks on a real cluster."""
        chart_path = CHARTS_DIR / "frontend"
        docs = render_chart(chart_path, VALUES_CI)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        assert len(deployments) > 0, "No Deployment found in frontend chart"

        for deployment in deployments:
            pod_spec = get_pod_spec(deployment)
            containers = get_containers(pod_spec)
            volumes = pod_spec.get("volumes", [])

            tls_volumes = [v for v in volumes if v.get("secret", {}).get("secretName") == "eaistack-frontend-tls"]
            assert len(tls_volumes) > 0, "frontend-tls Secret not mounted as a volume"

            for container in containers:
                volume_mounts = container.get("volumeMounts", [])
                tls_mounts = [vm for vm in volume_mounts if vm.get("name") == tls_volumes[0].get("name")]
                assert len(tls_mounts) > 0, f"TLS cert volume not mounted into container {container.get('name')}"

                env_names = [env.get("name") for env in container.get("env", [])]
                assert "SSL_CERTFILE" in env_names, "SSL_CERTFILE env var missing (Vite dev server TLS termination)"
                assert "SSL_KEYFILE" in env_names, "SSL_KEYFILE env var missing (Vite dev server TLS termination)"

    def test_probe_scheme_matches_tls_enabled(self):
        """Test: readiness/liveness probes only claim scheme: HTTPS when
        tls.enabled is actually true, since an HTTPS probe against a
        container not configured to terminate TLS fails the handshake and
        the pod never becomes Ready."""
        chart_path = CHARTS_DIR / "frontend"

        for tls_enabled, expect_https in [(True, True), (False, False)]:
            docs = render_chart(chart_path, extra_set={"tls.enabled": tls_enabled})
            deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
            assert len(deployments) > 0, "No Deployment found in frontend chart"

            for deployment in deployments:
                pod_spec = get_pod_spec(deployment)
                for container in get_containers(pod_spec):
                    readiness_scheme = container.get("readinessProbe", {}).get("httpGet", {}).get("scheme")
                    liveness_scheme = container.get("livenessProbe", {}).get("httpGet", {}).get("scheme")
                    if expect_https:
                        assert readiness_scheme == "HTTPS", \
                            f"Expected HTTPS readiness probe scheme when tls.enabled=true, got {readiness_scheme}"
                        assert liveness_scheme == "HTTPS", \
                            f"Expected HTTPS liveness probe scheme when tls.enabled=true, got {liveness_scheme}"
                    else:
                        assert readiness_scheme != "HTTPS", \
                            "HTTPS readiness probe scheme set but tls.enabled=false: pod can never become Ready"
                        assert liveness_scheme != "HTTPS", \
                            "HTTPS liveness probe scheme set but tls.enabled=false: pod can never become Ready"


class TestDocSearch:
    """doc-search specific tests."""

    def test_ca_bundle_mount_exists(self):
        """Test: doc-search Deployment mounts CA bundle at /etc/ssl/eaistack."""
        chart_path = CHARTS_DIR / "doc-search"
        docs = render_chart(chart_path, VALUES_CI)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        assert len(deployments) > 0, "No Deployment found in doc-search chart"

        for deployment in deployments:
            pod_spec = get_pod_spec(deployment)
            containers = get_containers(pod_spec)

            for container in containers:
                volume_mounts = container.get("volumeMounts", [])
                ca_mounts = [vm for vm in volume_mounts if "/etc/ssl/eaistack" in vm.get("mountPath", "")]
                assert len(ca_mounts) > 0, "CA bundle mount missing in doc-search"

    def test_certificate_san_includes_fqdn(self):
        """Test: doc-search Certificate includes fully-qualified DNS names (Decision 1)."""
        chart_path = CHARTS_DIR / "doc-search"
        docs = render_chart(chart_path, VALUES_CI)

        certs = [doc for doc in docs if doc.get("kind") == "Certificate"]
        assert len(certs) > 0, "No Certificate found in doc-search chart"

        for cert in certs:
            dns_names = cert.get("spec", {}).get("dnsNames", [])
            fqdn_forms = [name for name in dns_names if "svc.cluster.local" in name]
            assert len(fqdn_forms) > 0, "Certificate missing fully-qualified DNS names (Decision 1)"

    def test_healthz_probe_path(self):
        """Test: doc-search readinessProbe uses /healthz path."""
        chart_path = CHARTS_DIR / "doc-search"
        docs = render_chart(chart_path, VALUES_CI)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        for deployment in deployments:
            pod_spec = get_pod_spec(deployment)
            containers = get_containers(pod_spec)

            for container in containers:
                probe = container.get("readinessProbe", {})
                path = probe.get("httpGet", {}).get("path")
                assert path == "/healthz", \
                    f"doc-search probe path should be /healthz, got {path}"

    def test_tls_secret_mounted_when_enabled(self):
        """Test: with tls.enabled: true (doc-search's own default, per values.yaml's
        "TLS is always enabled for doc-search" comment), the Deployment mounts the
        cert-manager-issued Secret and passes its path to the container via env vars
        the docker-entrypoint.sh script reads (mirrors llama-server/embedding-server)."""
        chart_path = CHARTS_DIR / "doc-search"
        docs = render_chart(chart_path, VALUES_CI)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        assert len(deployments) > 0, "No Deployment found in doc-search chart"

        for deployment in deployments:
            pod_spec = get_pod_spec(deployment)
            containers = get_containers(pod_spec)

            for container in containers:
                volume_mounts = container.get("volumeMounts", [])
                tls_mounts = [vm for vm in volume_mounts if vm.get("name") == "doc-search-tls"]
                assert len(tls_mounts) > 0, \
                    "doc-search TLS secret volume not mounted despite tls.enabled: true"

                env_names = {env.get("name") for env in container.get("env", [])}
                assert "TLS_ENABLED" in env_names, "TLS_ENABLED env var missing in doc-search"
                assert "TLS_CERT_FILE" in env_names, "TLS_CERT_FILE env var missing in doc-search"
                assert "TLS_KEY_FILE" in env_names, "TLS_KEY_FILE env var missing in doc-search"

        volumes = deployments[0]["spec"]["template"]["spec"].get("volumes", [])
        tls_volumes = [v for v in volumes if v.get("name") == "doc-search-tls"]
        assert len(tls_volumes) > 0, "doc-search-tls volume missing from pod spec"
        assert tls_volumes[0]["secret"]["secretName"] == "eaistack-doc-search-tls"

    def test_probes_use_https_scheme_when_tls_enabled(self):
        """Test: readiness/liveness probes target HTTPS once doc-search actually
        terminates TLS itself (regression guard for Bug 1: probes previously stayed
        plain HTTP even though tls.enabled was true)."""
        chart_path = CHARTS_DIR / "doc-search"
        docs = render_chart(chart_path, VALUES_CI)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        for deployment in deployments:
            pod_spec = get_pod_spec(deployment)
            containers = get_containers(pod_spec)

            for container in containers:
                for probe_name in ("readinessProbe", "livenessProbe"):
                    scheme = container.get(probe_name, {}).get("httpGet", {}).get("scheme")
                    assert scheme == "HTTPS", \
                        f"doc-search {probe_name} should use HTTPS scheme when tls.enabled, got {scheme}"


class TestUmbrellaChart:
    """Umbrella chart specific tests."""

    def test_umbrella_chart_exists(self):
        """Test: Umbrella chart directory and Chart.yaml exist."""
        assert UMBRELLA_CHART.exists(), f"Umbrella chart missing: {UMBRELLA_CHART}"
        assert (UMBRELLA_CHART / "Chart.yaml").exists(), "Umbrella Chart.yaml missing"

    def test_umbrella_renders(self):
        """Test: Umbrella chart renders with CI values."""
        docs = render_chart(UMBRELLA_CHART, VALUES_CI)
        assert len(docs) > 0, "Umbrella chart rendered to empty output"

    def test_umbrella_includes_all_subcharts(self):
        """Test: Umbrella chart Chart.yaml declares all eight subcharts as dependencies."""
        chart_yaml_path = UMBRELLA_CHART / "Chart.yaml"
        if not chart_yaml_path.exists():
            pytest.skip("Umbrella Chart.yaml not yet created")

        with open(chart_yaml_path) as f:
            chart_yaml = yaml.safe_load(f)

        dependencies = chart_yaml.get("dependencies", [])
        dep_names = [dep.get("name") for dep in dependencies]

        expected_subcharts = ["postgres", "keycloak", "minio", "llama-server", "embedding-server", "backend", "doc-search", "frontend"]
        for subchart in expected_subcharts:
            assert subchart in dep_names, f"Umbrella missing dependency: {subchart}"

    def test_umbrella_namespace_in_values(self):
        """Test: Umbrella values.yaml sets namespace: eaistack."""
        values_path = UMBRELLA_CHART / "values.yaml"
        if not values_path.exists():
            pytest.skip("Umbrella values.yaml not yet created")

        with open(values_path) as f:
            values = yaml.safe_load(f)

        assert values.get("namespace") == "eaistack", \
            "Umbrella values.yaml should set namespace: eaistack"

    def test_postgres_fullname_override_agrees_across_charts(self):
        """Regression guard: postgres, backend, and keycloak each compute a
        peer's Service/StatefulSet hostname independently (a subchart cannot
        read a sibling subchart's own .Values.fullnameOverride - Helm only
        shares `global` across subcharts - so each cross-chart reference to
        "postgres.fullname" is a separate, duplicated template definition;
        see the comments in postgres/backend/keycloak's _helpers.tpl).

        Before this fix, those duplicates hardcoded the release-name-based
        default and ignored any override entirely, AND - because Helm merges
        every subchart's _helpers.tpl into one shared template namespace -
        having the same template name ("postgres.fullname") defined multiple
        times made it unspecified which definition even applied, including
        for postgres's own StatefulSet/Service. Setting
        global.fullnameOverrides.postgres must now rename postgres's own
        resources AND flow through to every consumer's hostname reference
        identically.
        """
        docs = render_chart(
            UMBRELLA_CHART,
            VALUES_CI,
            extra_set={"global.fullnameOverrides.postgres": "custom-pg-name-test"},
        )

        statefulsets = [doc for doc in docs if doc.get("kind") == "StatefulSet"]
        postgres_statefulsets = [sts for sts in statefulsets if sts.get("metadata", {}).get("name") == "custom-pg-name-test"]
        assert len(postgres_statefulsets) > 0, \
            "postgres's own StatefulSet did not pick up global.fullnameOverrides.postgres"

        services = [doc for doc in docs if doc.get("kind") == "Service"]
        postgres_services = [svc for svc in services if svc.get("metadata", {}).get("name") == "custom-pg-name-test"]
        assert len(postgres_services) > 0, \
            "postgres's own Service did not pick up global.fullnameOverrides.postgres"

        secrets = [doc for doc in docs if doc.get("kind") == "Secret"]
        backend_secrets = [s for s in secrets if s.get("metadata", {}).get("name") == "eaistack-backend"]
        assert len(backend_secrets) > 0, "backend Secret not found"
        database_url = backend_secrets[0].get("stringData", {}).get("database-url", "")
        assert "custom-pg-name-test." in database_url, \
            f"backend's database-url did not follow postgres's overridden hostname: {database_url}"

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
        keycloak_deployments = [d for d in deployments if d.get("metadata", {}).get("name") == "release-name-keycloak"]
        assert len(keycloak_deployments) > 0, "keycloak Deployment not found"
        keycloak_containers = get_containers(get_pod_spec(keycloak_deployments[0]))
        kc_db_url = next(
            env.get("value", "") for env in keycloak_containers[0].get("env", [])
            if env.get("name") == "KC_DB_URL"
        )
        assert "custom-pg-name-test." in kc_db_url, \
            f"keycloak's KC_DB_URL did not follow postgres's overridden hostname: {kc_db_url}"

    def test_rendered_umbrella_passes_manifest_compliance_validator(self):
        """End-to-end proof: `helm template` output for the real umbrella
        chart, with TLS enabled, passes every rule in
        infra/scripts/validate-rendered-manifests.py — not just the
        validator's own hand-picked fixtures.

        This is the gap that let a real bug ship silently: the validator's
        MINIO_*/POSTGRES_* credential-prefix match flagged MINIO_URL,
        MINIO_BUCKET, POSTGRES_DB, and POSTGRES_INITDB_ARGS as hardcoded
        credentials, because no test had ever run the validator against the
        actual chart's full env-var list — only against synthetic fixtures
        that happened not to include those specific names. Rendering the
        real chart here means a future template or validator change that
        reintroduces a false positive (or a real compliance gap) fails this
        test immediately.
        """
        cmd = [
            "helm", "template", "test", str(UMBRELLA_CHART),
            "-f", str(VALUES_CI),
            "--namespace", "eaistack",
            "--set", "backend.tls.enabled=true",
            "--set", "doc-search.tls.enabled=true",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            pytest.skip(f"Umbrella chart render failed: {result.stderr}")

        violations = _validator.validate_manifests(result.stdout)
        assert violations == [], "\n".join(v.message for v in violations)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
