#!/usr/bin/env python3
"""Assert compliance rules against a rendered multi-document Kubernetes manifest.

Usage:
    python infra/scripts/validate-rendered-manifests.py <rendered.yaml>

Exits 0 when every rule passes, non-zero with a per-violation report otherwise.

This is the CI-side half of several controls that no runtime test reaches.
Backend unit tests run against SQLite and never open a Postgres connection,
docker-compose stays plaintext for local dev, and the k3d smoke-test job is
deferred — so nothing in CI performs a real TLS handshake (Phase 5, Decision 8).
What CI can prove is that the rendered YAML says the right thing. These
assertions are what stop a future template edit from silently reopening a path
that a human reviewer would have to catch by eye.

Rules enforced (Phase 5, Decision 7):
    1. Every Deployment/StatefulSet/CronJob sets securityContext.runAsNonRoot.
    2. Credential-shaped env vars use valueFrom.secretKeyRef, never a literal.
    3. Every Deployment configured with an https:// peer has a Certificate.
    4. Every namespaced resource resolves to the eaistack namespace.
    5. Every PersistentVolumeClaim names a StorageClass (Decision 6).
    6. The rendered database-url uses sslmode=verify-full + sslrootcert
       (Decision 10).
    7. Every workload whose probes claim scheme: HTTPS actually mounts a
       Secret-backed volume for TLS, and a container references that mount.

Known limits, stated rather than papered over — a static check on rendered YAML
proves configuration, not effect:
    - Rule 5 proves a StorageClass is *named*, not that the class is actually
      backed by an encrypted volume. Node-layer LUKS is verified against a live
      cluster by infra/scripts/verify-encryption-at-rest.sh.
    - Rule 6 proves the connection string *asks* for verify-full. That the
      server enforces it (and rejects sslmode=disable) is a live-cluster check.
    - Rule 3 pairs a Deployment with a same-named Certificate. It cannot prove
      the certificate's SANs match the DNS name the client actually dials,
      which is where first-deploy friction concentrates.
    - Rule 7 proves a Secret-backed volume is mounted somewhere a probe expects
      TLS. It cannot prove the mounted Secret's key pair is the one the
      container process actually passes to its TLS listener (that requires
      reading the entrypoint script, not the rendered YAML).
"""

import base64
import sys
from pathlib import Path
from typing import Any, NamedTuple

import yaml

WORKLOAD_KINDS = ("Deployment", "StatefulSet", "CronJob")

EXPECTED_NAMESPACE = "eaistack"

# Cluster-scoped kinds have no namespace by definition, so rule 4 skips them.
CLUSTER_SCOPED_KINDS = (
    "Namespace",
    "ClusterIssuer",
    "ClusterRole",
    "ClusterRoleBinding",
    "StorageClass",
    "CustomResourceDefinition",
    "PersistentVolume",
)

# Exact names and prefixes that identify an env var as carrying a credential.
# Prefix matching keeps new MINIO_*/POSTGRES_* credentials covered without an
# edit here — a rule that only fires on an enumerated list silently misses the
# next secret someone adds.
CREDENTIAL_ENV_NAMES = (
    "DATABASE_URL",
    "KEYCLOAK_CLIENT_SECRET",
    "LLM_API_KEY",
    "OPENAI_API_KEY",
)
CREDENTIAL_ENV_PREFIXES = (
    "MINIO_",
    "POSTGRES_",
    "KEYCLOAK_ADMIN_",
)
# Substrings that mark a name as credential-shaped regardless of its prefix.
CREDENTIAL_ENV_SUBSTRINGS = ("PASSWORD", "SECRET", "_API_KEY", "ACCESS_KEY", "TOKEN")

# Env var names that contain a credential substring, or match a credential
# prefix, but are not themselves credentials — they name where a secret lives,
# a hostname, a resource name, or a config string, rather than carrying a
# secret value. Prefix matching (below) is deliberately broad so a *new*
# MINIO_*/POSTGRES_* credential is covered without an edit here; each name
# added to this tuple is a specific, reviewed case where that broad match is
# wrong, not a way to quietly narrow the rule back down.
CREDENTIAL_ENV_EXEMPTIONS = (
    "KEYCLOAK_CLIENT_SECRET_KEY_REF",
    "MINIO_URL",
    "MINIO_BUCKET",
    "POSTGRES_DB",
    "POSTGRES_INITDB_ARGS",
)

DATABASE_URL_SECRET_KEYS = ("database-url", "DATABASE_URL")


class Violation(NamedTuple):
    """A single compliance failure, reported with enough context to act on it."""

    rule: str
    message: str


def _load_documents(rendered_yaml: str) -> list[dict[str, Any]]:
    """Parse a multi-document render, dropping the empty docs Helm conditionals emit."""
    documents = yaml.safe_load_all(rendered_yaml)
    return [doc for doc in documents if isinstance(doc, dict)]


def _resource_label(document: dict[str, Any]) -> str:
    """Describe a resource the way a reader would look for it in the render."""
    kind = document.get("kind", "<unknown kind>")
    name = document.get("metadata", {}).get("name", "<unnamed>")
    return f"{kind}/{name}"


def _pod_spec(document: dict[str, Any]) -> dict[str, Any]:
    """Return the pod spec, which a CronJob nests one Job template deeper."""
    spec = document.get("spec", {})
    if document.get("kind") == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {})
    return spec.get("template", {}).get("spec", {})


def _containers(pod_spec: dict[str, Any]) -> list[dict[str, Any]]:
    return pod_spec.get("containers", []) + pod_spec.get("initContainers", [])


def _runs_as_non_root(pod_spec: dict[str, Any]) -> bool:
    """A pod is compliant via its own securityContext or via every container's."""
    if pod_spec.get("securityContext", {}).get("runAsNonRoot") is True:
        return True

    containers = _containers(pod_spec)
    if not containers:
        return False
    return all(
        container.get("securityContext", {}).get("runAsNonRoot") is True
        for container in containers
    )


def check_run_as_non_root(documents: list[dict[str, Any]]) -> list[Violation]:
    """Rule 1: workloads must not run as root."""
    violations = []
    for document in documents:
        if document.get("kind") not in WORKLOAD_KINDS:
            continue
        if _runs_as_non_root(_pod_spec(document)):
            continue
        violations.append(
            Violation(
                rule="runAsNonRoot",
                message=(
                    f"{_resource_label(document)}: expected "
                    f"securityContext.runAsNonRoot: true on the pod spec (or on every "
                    f"container), found neither. A workload without it may run as UID 0."
                ),
            )
        )
    return violations


def _is_credential_env(name: str) -> bool:
    if name in CREDENTIAL_ENV_EXEMPTIONS:
        return False
    if name in CREDENTIAL_ENV_NAMES:
        return True
    if name.startswith(CREDENTIAL_ENV_PREFIXES):
        return True
    return any(marker in name for marker in CREDENTIAL_ENV_SUBSTRINGS)


def check_credentials_use_secret_key_ref(
    documents: list[dict[str, Any]]
) -> list[Violation]:
    """Rule 2: credential env vars come from a Secret, never a rendered literal.

    A hardcoded value here is committed to git and visible in `kubectl get
    deployment -o yaml` to anyone with read access on the namespace.
    """
    violations = []
    for document in documents:
        if document.get("kind") not in WORKLOAD_KINDS:
            continue
        for container in _containers(_pod_spec(document)):
            for env_var in container.get("env", []):
                name = env_var.get("name", "")
                if not _is_credential_env(name) or "value" not in env_var:
                    continue
                violations.append(
                    Violation(
                        rule="secretKeyRef",
                        message=(
                            f"{_resource_label(document)}, container '{container.get('name')}': "
                            f"env var {name} is credential-shaped but uses a hardcoded "
                            f"'value:'. Expected valueFrom.secretKeyRef so the credential "
                            f"lives in a Secret, not in the rendered manifest."
                        ),
                    )
                )
    return violations


def _collect_strings(node: Any) -> list[str]:
    """Flatten every string in a nested structure, for scanning URLs anywhere in a spec."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _collect_strings(value)]
    if isinstance(node, list):
        return [s for item in node for s in _collect_strings(item)]
    return []


def check_https_deployments_have_certificates(
    documents: list[dict[str, Any]],
) -> list[Violation]:
    """Rule 3: a Deployment that speaks https:// needs a Certificate to speak it with."""
    certificate_names = {
        doc.get("metadata", {}).get("name")
        for doc in documents
        if doc.get("kind") == "Certificate"
    }

    violations = []
    for document in documents:
        if document.get("kind") != "Deployment":
            continue
        pod_spec = _pod_spec(document)
        if not any("https://" in value for value in _collect_strings(pod_spec)):
            continue
        name = document.get("metadata", {}).get("name")
        if name in certificate_names:
            continue
        violations.append(
            Violation(
                rule="certificate",
                message=(
                    f"{_resource_label(document)}: configuration references an https:// URL "
                    f"but no Certificate named '{name}' was rendered. Expected a "
                    f"cert-manager Certificate so this service has a key pair to serve "
                    f"and a CA to verify against."
                ),
            )
        )
    return violations


def _probes_claim_https(pod_spec: dict[str, Any]) -> bool:
    """True if any container's readiness/liveness probe declares scheme: HTTPS.

    A pod cannot pass such a probe unless something inside it actually speaks
    TLS on that port - this is the tell that a workload claims to serve TLS.
    """
    for container in _containers(pod_spec):
        for probe_name in ("readinessProbe", "livenessProbe"):
            scheme = container.get(probe_name, {}).get("httpGet", {}).get("scheme")
            if scheme == "HTTPS":
                return True
    return False


def _volume_names_sourced_from_secret(pod_spec: dict[str, Any], secret_name: str) -> set[str]:
    """Names of volumes in this pod spec that mount the given Secret by name."""
    return {
        volume.get("name")
        for volume in pod_spec.get("volumes", [])
        if volume.get("secret", {}).get("secretName") == secret_name
    }


def _mounted_volume_names(pod_spec: dict[str, Any]) -> set[str]:
    """Names of volumes actually referenced by a volumeMounts entry in any container."""
    return {
        mount.get("name")
        for container in _containers(pod_spec)
        for mount in container.get("volumeMounts", [])
    }


def check_tls_enabled_deployments_mount_their_certificate(
    documents: list[dict[str, Any]],
) -> list[Violation]:
    """Rule 7: a workload that claims to serve HTTPS must actually mount its Certificate.

    This is the inverse of Rule 3, and catches a different failure mode: a
    chart can render `scheme: HTTPS` on its probes (declaring "I serve TLS")
    while never mounting the cert-manager Secret that would let the container
    actually terminate TLS. A pod in that state can never pass its readiness
    check on a real cluster - exactly the bug that shipped for doc-search,
    backend, and frontend earlier on this branch, fixed by adding a
    Secret-backed volume and a matching volumeMount alongside the HTTPS
    scheme. This rule guards against that regressing silently.

    The check is scoped to the *specific* Secret that workload's own
    cert-manager Certificate provisions (matched by name, same convention
    Rule 3 uses to pair a Deployment with its Certificate) - not "any"
    Secret-backed volume. Most workloads here also mount an unrelated
    Secret-backed volume (the internal CA trust bundle, for verifying
    outbound connections), which is irrelevant to whether this pod can
    terminate inbound TLS; checking "any" would let an unmounted
    certificate hide behind that unrelated mount.
    """
    certificates_by_name = {
        doc.get("metadata", {}).get("name"): doc
        for doc in documents
        if doc.get("kind") == "Certificate"
    }

    violations = []
    for document in documents:
        if document.get("kind") not in WORKLOAD_KINDS:
            continue
        pod_spec = _pod_spec(document)
        if not _probes_claim_https(pod_spec):
            continue

        name = document.get("metadata", {}).get("name")
        certificate = certificates_by_name.get(name)
        if certificate is None:
            # No same-named Certificate at all is Rule 3's concern for a
            # client-side https:// reference; here it means this workload
            # cannot possibly have cert-manager material to mount.
            violations.append(
                Violation(
                    rule="tlsCertificateMounted",
                    message=(
                        f"{_resource_label(document)}: a probe declares "
                        f"scheme: HTTPS but no Certificate named '{name}' was "
                        f"rendered, so there is no cert-manager Secret this pod "
                        f"could mount to terminate TLS."
                    ),
                )
            )
            continue

        secret_name = certificate.get("spec", {}).get("secretName")
        secret_volume_names = _volume_names_sourced_from_secret(pod_spec, secret_name)
        mounted_volumes = _mounted_volume_names(pod_spec)

        if not secret_volume_names:
            violations.append(
                Violation(
                    rule="tlsCertificateMounted",
                    message=(
                        f"{_resource_label(document)}: a probe declares "
                        f"scheme: HTTPS and Certificate '{name}' provisions "
                        f"Secret '{secret_name}', but the pod spec has no volume "
                        f"sourced from that Secret. A container here can never "
                        f"terminate TLS, so the pod can never pass this probe on "
                        f"a real cluster."
                    ),
                )
            )
        elif not secret_volume_names & mounted_volumes:
            violations.append(
                Violation(
                    rule="tlsCertificateMounted",
                    message=(
                        f"{_resource_label(document)}: a probe declares "
                        f"scheme: HTTPS and the pod spec defines a volume "
                        f"sourced from Certificate '{name}''s Secret "
                        f"'{secret_name}', but no container's volumeMounts "
                        f"references it. An unmounted certificate secret is an "
                        f"orphaned Certificate: issued but unused."
                    ),
                )
            )
    return violations


def check_namespace(documents: list[dict[str, Any]]) -> list[Violation]:
    """Rule 4: everything lands in the eaistack namespace.

    An unset namespace is a violation, not a pass — it resolves to whatever the
    applying context points at, which is exactly how resources land in `default`.
    """
    violations = []
    for document in documents:
        kind = document.get("kind")
        metadata = document.get("metadata", {})

        if kind == "Namespace":
            name = metadata.get("name")
            if name != EXPECTED_NAMESPACE:
                violations.append(
                    Violation(
                        rule="namespace",
                        message=(
                            f"{_resource_label(document)}: expected the namespace to be "
                            f"'{EXPECTED_NAMESPACE}', found '{name}'."
                        ),
                    )
                )
            continue

        if kind in CLUSTER_SCOPED_KINDS:
            continue

        namespace = metadata.get("namespace")
        if namespace == EXPECTED_NAMESPACE:
            continue
        found = namespace if namespace else "<unset>"
        violations.append(
            Violation(
                rule="namespace",
                message=(
                    f"{_resource_label(document)}: expected metadata.namespace "
                    f"'{EXPECTED_NAMESPACE}', found '{found}'. An unset namespace resolves "
                    f"to the applying context's default, not to eaistack."
                ),
            )
        )
    return violations


def _storage_class_violation(claim_label: str) -> Violation:
    return Violation(
        rule="storageClassName",
        message=(
            f"{claim_label}: storageClassName is missing or empty. This is a HARD "
            f"COMPLIANCE REQUIREMENT, not a style preference: encryption at rest is "
            f"only guaranteed when the claim names a known-encrypted StorageClass. "
            f"Falling back to the cluster default is how an unencrypted deploy happens "
            f"by accident, and it succeeds silently. Set persistence.storageClassName "
            f"to an encrypted class - see docs/SECURITY.md."
        ),
    )


def check_persistent_volume_claims_have_storage_class(
    documents: list[dict[str, Any]],
) -> list[Violation]:
    """Rule 5: every PVC names a StorageClass (Decision 6's at-rest gate).

    Covers volumeClaimTemplates too — a StatefulSet's templates create real PVCs
    and would otherwise slip past a check that only looked at PVC documents.
    """
    violations = []
    for document in documents:
        kind = document.get("kind")

        if kind == "PersistentVolumeClaim":
            if not document.get("spec", {}).get("storageClassName"):
                violations.append(_storage_class_violation(_resource_label(document)))
            continue

        for claim in document.get("spec", {}).get("volumeClaimTemplates", []):
            if claim.get("spec", {}).get("storageClassName"):
                continue
            claim_name = claim.get("metadata", {}).get("name", "<unnamed>")
            violations.append(
                _storage_class_violation(
                    f"{_resource_label(document)} volumeClaimTemplate '{claim_name}'"
                )
            )
    return violations


def _decoded_secret_values(
    document: dict[str, Any], keys: tuple[str, ...]
) -> list[str]:
    """Read a Secret key from stringData or base64 `data`, whichever Helm rendered."""
    values = []
    string_data = document.get("stringData", {})
    data = document.get("data", {})

    for key in keys:
        if key in string_data:
            values.append(str(string_data[key]))
        elif key in data:
            values.append(base64.b64decode(str(data[key])).decode("utf-8"))
    return values


def check_database_url_verifies_tls(documents: list[dict[str, Any]]) -> list[Violation]:
    """Rule 6: the Postgres connection string validates the certificate and hostname.

    sslmode=require encrypts but validates neither the certificate nor the
    hostname, so it stops passive sniffing and not an active MITM. Both look
    identical in a connection test, which is exactly why this needs a static check.
    """
    violations = []
    for document in documents:
        if document.get("kind") != "Secret":
            continue
        label = _resource_label(document)

        for url in _decoded_secret_values(document, DATABASE_URL_SECRET_KEYS):
            if "sslmode=verify-full" not in url:
                found = (
                    "sslmode=require"
                    if "sslmode=require" in url
                    else "no sslmode parameter"
                )
                violations.append(
                    Violation(
                        rule="sslmode",
                        message=(
                            f"{label}: database-url must use sslmode=verify-full, found "
                            f"{found}. 'require' encrypts the connection but validates "
                            f"neither the server certificate nor the hostname, so it does "
                            f"not stop an active MITM - and it is indistinguishable from "
                            f"verify-full in a connection test. Absent sslmode may "
                            f"negotiate plaintext entirely."
                        ),
                    )
                )
            if "sslrootcert=" not in url:
                violations.append(
                    Violation(
                        rule="sslrootcert",
                        message=(
                            f"{label}: database-url must reference an sslrootcert path so "
                            f"verify-full has the internal CA to validate the server "
                            f"certificate against. Without it, verification has no trust "
                            f"anchor and the connection fails or falls back."
                        ),
                    )
                )
    return violations


def validate_manifests(rendered_yaml: str) -> list[Violation]:
    """Run every compliance rule against a rendered multi-document manifest."""
    documents = _load_documents(rendered_yaml)

    return (
        check_run_as_non_root(documents)
        + check_credentials_use_secret_key_ref(documents)
        + check_https_deployments_have_certificates(documents)
        + check_tls_enabled_deployments_mount_their_certificate(documents)
        + check_namespace(documents)
        + check_persistent_volume_claims_have_storage_class(documents)
        + check_database_url_verifies_tls(documents)
    )


def main(argv: list[str] | None = None) -> int:
    """Validate the manifest named on the command line. Returns a process exit code."""
    args = sys.argv[1:] if argv is None else argv

    if len(args) != 1:
        print("Usage: validate-rendered-manifests.py <rendered.yaml>")
        return 2

    manifest_path = Path(args[0])
    if not manifest_path.is_file():
        print(f"Rendered manifest not found: {manifest_path}")
        return 2

    try:
        violations = validate_manifests(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        print(f"Could not parse {manifest_path} as YAML: {error}")
        return 2

    if not violations:
        print(f"OK: {manifest_path} passes all rendered-manifest compliance rules.")
        return 0

    print(f"FAILED: {len(violations)} compliance violation(s) in {manifest_path}\n")
    for violation in violations:
        print(f"  [{violation.rule}] {violation.message}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
