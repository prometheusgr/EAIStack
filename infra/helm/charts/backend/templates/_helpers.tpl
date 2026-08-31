{{/*
Expand the name of the chart.
*/}}
{{- define "backend.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "backend.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "backend.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "backend.labels" -}}
helm.sh/chart: {{ include "backend.chart" . }}
{{ include "backend.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "backend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the Secret containing backend credentials
*/}}
{{- define "backend.secretName" -}}
eaistack-backend
{{- end }}

{{/*
Name of the Secret containing the backend TLS certificate (cert-manager-issued)
*/}}
{{- define "backend.certificateSecretName" -}}
eaistack-backend-tls
{{- end }}

{{/*
Postgres fullname helper (for cross-chart reference).

This chart (backend) cannot see postgres's own .Values - Helm only shares
`global` across sibling subcharts - so it can't directly call postgres's
"fullname" logic against postgres's own values. This duplicate MUST stay
in lock-step with postgres/templates/_helpers.tpl's postgres.fullname
(same resolution order, same global.fullnameOverrides.postgres key) or the
two computed names silently diverge and DATABASE_URL points at a hostname
that doesn't exist. It intentionally does NOT check
.Values.fullnameOverride/.Values.nameOverride here - those belong to
whoever installs the postgres chart directly, and backend has no way to
read them; the global.fullnameOverrides.postgres branch is the one channel
both charts can agree on.
*/}}
{{- define "postgres.fullname" -}}
{{- if dig "fullnameOverrides" "postgres" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "postgres" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := "postgres" }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Postgres secret name helper (for cross-chart reference)
*/}}
{{- define "postgres.secretName" -}}
eaistack-postgres
{{- end }}

{{/*
Keycloak fullname helper (for cross-chart reference). See the
postgres.fullname comment above for why this must stay in lock-step with
keycloak/templates/_helpers.tpl's own keycloak.fullname.
*/}}
{{- define "keycloak.fullname" -}}
{{- if dig "fullnameOverrides" "keycloak" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "keycloak" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := "keycloak" }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
llama-server fullname helper (for cross-chart reference). See the
postgres.fullname comment above for why this must stay in lock-step with
llama-server/templates/_helpers.tpl's own llama-server.fullname.
*/}}
{{- define "llama-server.fullname" -}}
{{- if dig "fullnameOverrides" "llama-server" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "llama-server" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := "llama-server" }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
embedding-server fullname helper (for cross-chart reference). See the
postgres.fullname comment above for why this must stay in lock-step with
embedding-server/templates/_helpers.tpl's own embedding-server.fullname.
*/}}
{{- define "embedding-server.fullname" -}}
{{- if dig "fullnameOverrides" "embedding-server" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "embedding-server" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := "embedding-server" }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
minio fullname helper (for cross-chart reference). See the
postgres.fullname comment above for why this must stay in lock-step with
minio/templates/_helpers.tpl's own minio.fullname.
*/}}
{{- define "minio.fullname" -}}
{{- if dig "fullnameOverrides" "minio" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "minio" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := "minio" }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
doc-search fullname helper (for cross-chart reference). See the
postgres.fullname comment above for why this must stay in lock-step with
doc-search/templates/_helpers.tpl's own doc-search.fullname.
*/}}
{{- define "doc-search.fullname" -}}
{{- if dig "fullnameOverrides" "doc-search" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "doc-search" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := "doc-search" }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
phoenix fullname helper (for cross-chart reference). See the
postgres.fullname comment above for why this must stay in lock-step with
phoenix/templates/_helpers.tpl's own phoenix.fullname. Only referenced when
.Values.tracingEnabled is true - see deployment.yaml's TRACING_OTLP_ENDPOINT.
*/}}
{{- define "phoenix.fullname" -}}
{{- if dig "fullnameOverrides" "phoenix" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "phoenix" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := "phoenix" }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
OIDC client ID: defaults to "eaistack-backend" but stays overridable via
values.yaml's oidcClient.clientId, since keycloak's realm-import ConfigMap
(keycloak/templates/realm-import-configmap.yaml) reads
.Values.oidcClient.clientId directly and must register the same client ID
backend authenticates as.
*/}}
{{- define "backend.oidcClient.clientId" -}}
{{- .Values.oidcClient.clientId | default "eaistack-backend" }}
{{- end }}
