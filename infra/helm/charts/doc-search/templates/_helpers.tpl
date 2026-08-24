{{/*
Expand the name of the chart.
*/}}
{{- define "doc-search.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{/*
Resolution order: see the matching comment on postgres.fullname in
postgres/templates/_helpers.tpl for why the global.fullnameOverrides branch
exists (subcharts can't see a sibling's own .Values, only `global`).
*/}}
{{- define "doc-search.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else if dig "fullnameOverrides" "doc-search" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "doc-search" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
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
{{- define "doc-search.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "doc-search.labels" -}}
helm.sh/chart: {{ include "doc-search.chart" . }}
{{ include "doc-search.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "doc-search.selectorLabels" -}}
app.kubernetes.io/name: {{ include "doc-search.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the Secret containing the doc-search TLS certificate (cert-manager-issued)
*/}}
{{- define "doc-search.certificateSecretName" -}}
eaistack-doc-search-tls
{{- end }}

{{/*
Keycloak fullname helper (for cross-chart reference).

This chart (doc-search) cannot see keycloak's own .Values - Helm only
shares `global` across sibling subcharts - so it can't directly call
keycloak's "fullname" logic against keycloak's own values. This duplicate
MUST stay in lock-step with keycloak/templates/_helpers.tpl's own
keycloak.fullname (same resolution order, same
global.fullnameOverrides.keycloak key) or the two computed names silently
diverge. It intentionally does NOT check
.Values.fullnameOverride/.Values.nameOverride here - those belong to
whoever installs the keycloak chart directly, and doc-search has no way to
read them; the global.fullnameOverrides.keycloak branch is the one channel
both charts can agree on.
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
embedding-server fullname helper (for cross-chart reference). See the
keycloak.fullname comment above for why this must stay in lock-step with
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
Backend secret name helper (for cross-chart reference)
*/}}
{{- define "backend.secretName" -}}
eaistack-backend
{{- end }}
