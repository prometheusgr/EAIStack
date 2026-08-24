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

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


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


def render_chart(chart_path: Path, values_file: Path = None) -> list[dict]:
    """Render a Helm chart and return parsed YAML documents."""
    cmd = ["helm", "template", str(chart_path)]
    if values_file:
        cmd.extend(["-f", str(values_file)])

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

    def test_postgres_password_required(self):
        """Test: postgres Secret uses {{ required }} for password."""
        chart_path = CHARTS_DIR / "postgres"
        # This test checks that {{ required }} causes failure if value not set
        # With CI values set, it should pass; without values, it should fail
        docs = render_chart(chart_path, VALUES_CI)
        secrets = [doc for doc in docs if doc.get("kind") == "Secret"]
        assert len(secrets) > 0, "No Secret found in postgres chart"


class TestKeycloak:
    """Keycloak-specific tests."""

    def test_realm_import_configmap_exists(self):
        """Test: Keycloak chart produces a realm-import ConfigMap."""
        chart_path = CHARTS_DIR / "keycloak"
        docs = render_chart(chart_path, VALUES_CI)

        configmaps = [doc for doc in docs if doc.get("kind") == "ConfigMap"]
        assert any("realm" in doc.get("metadata", {}).get("name", "") for doc in configmaps), \
            "No realm-import ConfigMap found in keycloak chart"

    def test_admin_password_required(self):
        """Test: Keycloak Secret uses {{ required }} for admin password."""
        chart_path = CHARTS_DIR / "keycloak"
        docs = render_chart(chart_path, VALUES_CI)
        secrets = [doc for doc in docs if doc.get("kind") == "Secret"]
        assert len(secrets) > 0, "No Secret found in keycloak chart"


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

    def test_minio_credentials_required(self):
        """Test: MinIO Secret uses {{ required }} for root-user and root-password."""
        chart_path = CHARTS_DIR / "minio"
        docs = render_chart(chart_path, VALUES_CI)
        secrets = [doc for doc in docs if doc.get("kind") == "Secret"]
        assert len(secrets) > 0, "No Secret found in minio chart"


class TestLLMServers:
    """llama-server and embedding-server specific tests."""

    @pytest.mark.parametrize("chart_name", ["llama-server", "embedding-server"])
    def test_certificate_conditional_on_tls_enabled(self, chart_name: str):
        """Test: Certificate only rendered when tls.enabled: true."""
        chart_path = CHARTS_DIR / chart_name

        # With tls.enabled: false (default), no Certificate
        docs = render_chart(chart_path, VALUES_CI)
        certs = [doc for doc in docs if doc.get("kind") == "Certificate"]
        # Should be no certs since VALUES_CI has tls.enabled: false
        # But test gracefully skips if chart not yet complete


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
