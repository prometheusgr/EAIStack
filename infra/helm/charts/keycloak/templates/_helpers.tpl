{{/*
Expand the name of the chart.
*/}}
{{- define "keycloak.name" -}}
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
{{- define "keycloak.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else if dig "fullnameOverrides" "keycloak" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "keycloak" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
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
{{- define "keycloak.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "keycloak.labels" -}}
helm.sh/chart: {{ include "keycloak.chart" . }}
{{ include "keycloak.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "keycloak.selectorLabels" -}}
app.kubernetes.io/name: {{ include "keycloak.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the Secret containing keycloak credentials
*/}}
{{- define "keycloak.secretName" -}}
eaistack-keycloak
{{- end }}

{{/*
Name of the Secret containing the keycloak TLS certificate (cert-manager-issued)
*/}}
{{- define "keycloak.certificateSecretName" -}}
eaistack-keycloak-tls
{{- end }}

{{/*
Postgres fullname helper (for cross-chart reference).

This chart (keycloak) cannot see postgres's own .Values - Helm only shares
`global` across sibling subcharts - so it can't directly call postgres's
"fullname" logic against postgres's own values. This duplicate MUST stay
in lock-step with postgres/templates/_helpers.tpl's own postgres.fullname
(same resolution order, same global.fullnameOverrides.postgres key) or the
two computed names silently diverge and KC_DB_URL points at a hostname
that doesn't exist. It intentionally does NOT check
.Values.fullnameOverride/.Values.nameOverride here - those belong to
whoever installs the postgres chart directly, and keycloak has no way to
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
