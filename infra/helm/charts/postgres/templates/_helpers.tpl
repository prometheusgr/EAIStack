{{/*
Expand the name of the chart.
*/}}
{{- define "postgres.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{/*
Resolution order:
  1. .Values.fullnameOverride - set when this chart is installed directly
     (standalone), not through the umbrella.
  2. .Values.global.fullnameOverrides.postgres - set when this chart is
     installed as a subchart of eaistack-umbrella. Subcharts cannot see a
     sibling subchart's own .Values (Helm only shares `global`), so this is
     the one channel every peer chart's cross-chart reference to
     "postgres.fullname" (see backend/doc-search/keycloak's _helpers.tpl) can
     also read - keeping their computed hostname consistent with the one
     this chart actually gives its own Service/StatefulSet.
  3. release-name-collision default (unchanged from Helm's chart starter).
*/}}
{{- define "postgres.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else if dig "fullnameOverrides" "postgres" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "postgres" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
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
{{- define "postgres.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "postgres.labels" -}}
helm.sh/chart: {{ include "postgres.chart" . }}
{{ include "postgres.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "postgres.selectorLabels" -}}
app.kubernetes.io/name: {{ include "postgres.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the Secret containing postgres credentials
*/}}
{{- define "postgres.secretName" -}}
eaistack-postgres
{{- end }}

{{/*
Name of the Secret containing the postgres TLS certificate (cert-manager-issued)
*/}}
{{- define "postgres.certificateSecretName" -}}
eaistack-postgres-tls
{{- end }}
