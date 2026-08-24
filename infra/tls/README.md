# TLS & Encryption Setup

This directory bootstraps the **internal certificate authority** that issues TLS
certificates to every EAIStack service running in Kubernetes.

If you have never deployed to Kubernetes before, read this whole page once
before running anything. It assumes no prior knowledge of `kubectl`,
cert-manager, or custom resources.

---

## Why an internal CA?

TLS (the "S" in HTTPS) needs two things: a **certificate** proving a server is
who it claims to be, and a **certificate authority (CA)** that the client
already trusts, which vouches for that certificate.

On the public internet you get certificates from Let's Encrypt, which proves
your identity by reaching your server over the internet (the ACME protocol).
**EAIStack runs air-gapped — there is no internet at runtime**, so Let's Encrypt
is not reachable and never will be.

The answer is to run our own CA inside the cluster:

- EAIStack creates one **root CA certificate**, self-signed, valid for 10 years.
- Every EAIStack service (backend, doc-search, postgres, minio, keycloak, ...)
  gets its own certificate **signed by that root**.
- Every EAIStack pod that makes outbound calls mounts the root CA and is told to
  trust it, so it can verify the certificates its peers present.

No browser or public CA is involved. Trust is entirely internal, which is
exactly what an air-gapped deployment needs.

### What is cert-manager?

Doing the above by hand — running `openssl`, copying key files into pods,
remembering to renew before expiry — is tedious and error-prone. **cert-manager**
is a program that runs inside the cluster and automates it. You describe the
certificate you want as a YAML file; cert-manager creates the keypair, signs it,
stores it in Kubernetes, and renews it before it expires. You never touch a
private key.

cert-manager adds new object types to Kubernetes, called **custom resources**
(CRDs). The two used here:

| Resource | What it means |
|---|---|
| `ClusterIssuer` | *Who signs certificates.* A cluster-wide signing authority any namespace can request from. |
| `Certificate` | *A certificate you want.* cert-manager issues it and stores the result in a Kubernetes **Secret**. |

A **Secret** is just Kubernetes' storage slot for sensitive data — here, the
certificate and its private key. Pods mount Secrets as files.

---

## Prerequisite: cert-manager must already be installed

**These manifests do not install cert-manager.** They assume it is already
running cluster-wide. Applying them to a cluster without cert-manager fails
immediately, because the `ClusterIssuer` and `Certificate` types will not exist.

Check whether it is installed:

```bash
kubectl get pods -n cert-manager
```

Healthy output — three pods, all `Running`:

```
NAME                                       READY   STATUS    RESTARTS   AGE
cert-manager-5d7f97b46d-xxxxx              1/1     Running   0          5m
cert-manager-cainjector-69d6f4d488-xxxxx   1/1     Running   0          5m
cert-manager-webhook-8d7495f4-xxxxx        1/1     Running   0          5m
```

If you instead see `No resources found in cert-manager namespace.` or
`Error from server (NotFound): namespaces "cert-manager" not found`, it is not
installed — stop here and install it first.

Also confirm the custom resource types are registered:

```bash
kubectl get crd | grep cert-manager.io
```

You should see roughly six lines including `clusterissuers.cert-manager.io` and
`certificates.cert-manager.io`. If this returns nothing, cert-manager's CRDs did
not install correctly.

> Air-gap note: installing cert-manager requires its container images to be
> present in your local registry. Mirroring them is part of air-gap setup, not
> part of this directory — see `docs/AIRGAP_SETUP.md`.

---

## The two files, and why there are two

| File | Contains | Purpose |
|---|---|---|
| `ca-cert.yaml` | Stage 1 + Stage 2 | Bootstrap issuer, and the root CA certificate it signs |
| `issuer.yaml` | Stage 3 | The real issuer every service requests certificates from |

### The chicken-and-egg problem

The issuer we actually want is a **CA issuer**: it signs certificates using the
EAIStack root CA's private key. But that private key has to exist somewhere
first — and the sensible way to create it is to have cert-manager issue it as a
`Certificate`. Which requires an issuer. Which is the thing we are trying to
create.

cert-manager breaks the loop with a third issuer type, `selfSigned`, which
signs a certificate with that certificate's *own* private key and needs no CA at
all. So:

```
Stage 1   ClusterIssuer  eaistack-selfsigned-bootstrap   (kind: selfSigned)
             │  signs
             ▼
Stage 2   Certificate    eaistack-ca      (isCA: true, namespace: cert-manager)
             │  writes keypair into
             ▼
          Secret         eaistack-ca-key-pair
             │  read by
             ▼
Stage 3   ClusterIssuer  eaistack-ca-issuer              (kind: ca)
             │  signs
             ▼
          every per-service Certificate (backend, postgres, minio, ...)
```

The bootstrap issuer from Stage 1 is used exactly once, for Stage 2, and never
again. Nothing else in EAIStack ever references it.

**The single wire that matters:** `spec.secretName: eaistack-ca-key-pair` in
`ca-cert.yaml` must match `spec.ca.secretName: eaistack-ca-key-pair` in
`issuer.yaml`. That Secret is the whole handoff between the two stages. If those
names drift apart, nothing errors loudly — the issuer just stays unready and
every service certificate hangs forever.

**Why `namespace: cert-manager` on the root CA Certificate:** a `ClusterIssuer`
of kind `ca` always looks for its keypair Secret in the namespace cert-manager
itself runs in, regardless of where the certificates it issues live. Putting the
root CA Certificate in `eaistack` instead produces a Secret in the wrong place
and Stage 3 never finds it. This is the most common way this setup fails.

---

## Applying

Apply both files together. `kubectl apply` is declarative — running it twice
changes nothing the second time, so it is safe to re-run.

```bash
kubectl apply -f infra/tls/
```

You do not need to apply them in a particular order. Kubernetes accepts
resources in any order and cert-manager reconciles continuously: if `issuer.yaml`
lands before the Secret from `ca-cert.yaml` exists, the issuer reports NotReady
for a few seconds and then goes Ready on its own once the Secret appears.

Expected output:

```
clusterissuer.cert-manager.io/eaistack-selfsigned-bootstrap created
certificate.cert-manager.io/eaistack-ca created
clusterissuer.cert-manager.io/eaistack-ca-issuer created
```

---

## Verification

Issuance takes a few seconds. Wait, then run both checks.

### 1. Both issuers are Ready

```bash
kubectl get clusterissuer
```

Healthy:

```
NAME                            READY   AGE
eaistack-ca-issuer              True    30s
eaistack-selfsigned-bootstrap   True    30s
```

`READY  True` on **both** lines is what you want. Anything else — `False`, or a
blank column — means the chain is broken; see Troubleshooting.

### 2. The root CA certificate was issued

```bash
kubectl get certificate -n cert-manager
```

Healthy:

```
NAME          READY   SECRET                 AGE
eaistack-ca   True    eaistack-ca-key-pair   30s
```

Failure looks like `READY  False` with the SECRET column still listed — the
Secret name is what you *asked for*, not proof it exists.

### 3. The keypair Secret actually exists and is populated

This is the real proof, since Stage 3 depends on it:

```bash
kubectl get secret eaistack-ca-key-pair -n cert-manager
```

Healthy — note `DATA  3` (`tls.crt`, `tls.key`, `ca.crt`):

```
NAME                   TYPE                DATA   AGE
eaistack-ca-key-pair   kubernetes.io/tls   3      30s
```

`Error from server (NotFound)` means Stage 2 has not completed.

### 4. (Optional) Inspect the certificate itself

To see the actual X.509 contents — useful for confirming the CA flag is set:

```bash
kubectl get secret eaistack-ca-key-pair -n cert-manager \
  -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -text
```

Look for `CA:TRUE` under `X509v3 Basic Constraints` and
`Subject: CN = eaistack-internal-ca`.

### Later: per-service certificates

Once the Helm charts are deployed, the same check against the app namespace
shows one row per service:

```bash
kubectl get certificate -n eaistack
```

This returns `No resources found in eaistack namespace.` at this stage — that is
correct and expected. Nothing in this directory creates per-service
certificates.

---

## Troubleshooting

Diagnose in this order; each failure mode has a distinct signature.

### cert-manager is not installed

**Symptom** — `kubectl apply` fails immediately:

```
error: unable to recognize "infra/tls/ca-cert.yaml": no matches for kind
"ClusterIssuer" in version "cert-manager.io/v1"
```

Kubernetes does not know what a `ClusterIssuer` is, because the CRDs that define
it were never installed. **Nothing was created** — this is a total failure, not a
partial one.

**Fix:** install cert-manager (see the Prerequisite section), then re-apply.

### CRDs are registered but cert-manager's pods are not ready

**Symptom** — `kubectl apply` fails with a webhook error:

```
Error from server (InternalError): error when creating "infra/tls/ca-cert.yaml":
Internal error occurred: failed calling webhook "webhook.cert-manager.io":
dial tcp ...: connect: connection refused
```

cert-manager validates every resource through an admission webhook served by its
own pods. If those pods are still starting, the webhook is unreachable. This is
common in the first 30–60 seconds after installing cert-manager.

**Fix:** wait for the pods, then re-apply:

```bash
kubectl wait --for=condition=Available --timeout=120s \
  deployment -n cert-manager --all
kubectl apply -f infra/tls/
```

### The CA issuer stays NotReady — Secret not found

**Symptom** — `kubectl get clusterissuer` shows the bootstrap issuer `True` but
`eaistack-ca-issuer` `False`. Get the reason:

```bash
kubectl describe clusterissuer eaistack-ca-issuer
```

```
Status:
  Conditions:
    Message:  Failed to get certificate: secret "eaistack-ca-key-pair" not found
    Reason:   ErrGetKeyPair
    Status:   False
```

The Stage 2 → Stage 3 handoff broke. Three possible causes, in order of
likelihood:

1. **Stage 2 has not finished yet.** Wait 10–20 seconds and re-check — if this
   was it, the issuer flips to `True` on its own with no action from you.
2. **The root CA Certificate is in the wrong namespace.** Confirm with
   `kubectl get certificate -A | grep eaistack-ca` — it must show
   `cert-manager`, not `eaistack` or `default`.
3. **The Secret names do not match.** Compare `spec.secretName` in
   `ca-cert.yaml` against `spec.ca.secretName` in `issuer.yaml`; they must be
   byte-identical.

### The root CA Certificate itself is stuck

**Symptom** — `kubectl get certificate -n cert-manager` shows `READY  False` for
`eaistack-ca`. Look at its events:

```bash
kubectl describe certificate eaistack-ca -n cert-manager
```

The `Events:` section at the bottom names the actual problem. Common cases:
the bootstrap issuer name is misspelled in `issuerRef` (`Issuer ... not found`),
or `issuerRef.kind` says `Issuer` instead of `ClusterIssuer` — cert-manager then
looks for a namespaced issuer that does not exist.

For deeper detail, cert-manager's own logs explain what it attempted:

```bash
kubectl logs -n cert-manager deployment/cert-manager --tail=50
```

---

## Per-service certificates (a later step)

Nothing in this directory issues certificates to EAIStack services. Each service
gets its own `Certificate` from its Helm chart, all referencing the issuer
created here:

```yaml
issuerRef:
  name: eaistack-ca-issuer
  kind: ClusterIssuer
  group: cert-manager.io
```

One certificate per service (backend, frontend, doc-search, postgres, minio,
keycloak, ...) rather than one shared wildcard, so a compromise of any single
pod's key does not expose every other service's identity.

### Every certificate must list all its DNS names (SANs)

**This is the single most common cert-manager mistake, so it is worth
understanding before you write your first chart.**

A certificate lists the hostnames it is valid for, in a field called
**Subject Alternative Names** (SANs) — `dnsNames` in cert-manager YAML. When a
client connects, it checks that the hostname it dialed appears in that list. If
it does not, the connection is **rejected**, even though the certificate is
otherwise perfectly valid and signed by a trusted CA.

Inside Kubernetes the *same service* is reachable under several names. A pod in
the `eaistack` namespace can reach the backend as any of:

```
eaistack-backend                              (short — same namespace only)
eaistack-backend.eaistack                     (with namespace)
eaistack-backend.eaistack.svc                 (with service qualifier)
eaistack-backend.eaistack.svc.cluster.local   (fully qualified)
```

All four are the same service. But a certificate issued only for
`eaistack-backend` fails the moment some client dials the fully-qualified form —
and different clients pick different forms, so this typically surfaces as "it
works from one pod but not another."

**Rule: every `Certificate` lists the short name, the `.svc` form, and the
fully-qualified form.** For example:

```yaml
dnsNames:
  - eaistack-backend
  - eaistack-backend.eaistack.svc
  - eaistack-backend.eaistack.svc.cluster.local
```

Services reached from outside the cluster (frontend, keycloak) additionally list
their external hostname.

This matters most for Postgres. EAIStack connects with
`sslmode=verify-full`, which validates both the certificate chain **and** the
hostname. A SAN mismatch there is a hard connection failure at startup, not a
warning — the backend simply will not connect. (`sslmode=require` would encrypt
without checking the hostname, which stops passive eavesdropping but not an
active impostor, so EAIStack does not use it.)

To check what a live certificate actually covers:

```bash
kubectl get secret eaistack-backend-tls -n eaistack \
  -o jsonpath='{.data.tls\.crt}' | base64 -d \
  | openssl x509 -noout -text | grep -A1 "Subject Alternative Name"
```

---

## Key points

- All certificates chain to a self-signed internal root — no Let's Encrypt, no
  internet, by design.
- cert-manager renews per-service certificates automatically; the 10-year root
  is the only one with a long manual horizon.
- Applications trust the internal CA by mounting `ca.crt` from the CA Secret and
  pointing their HTTP/database clients at that file explicitly.
- See `docs/SECURITY.md` for the full encryption-in-transit posture, including
  which hops are TLS-protected and which are deliberately not.
