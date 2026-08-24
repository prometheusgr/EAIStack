{{/*
Expand the name of the chart.
*/}}
{{- define "embedding-server.name" -}}
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
{{- define "embedding-server.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else if dig "fullnameOverrides" "embedding-server" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "embedding-server" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
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
{{- define "embedding-server.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "embedding-server.labels" -}}
helm.sh/chart: {{ include "embedding-server.chart" . }}
{{ include "embedding-server.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "embedding-server.selectorLabels" -}}
app.kubernetes.io/name: {{ include "embedding-server.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the Secret containing the embedding-server TLS certificate (cert-manager-issued)
*/}}
{{- define "embedding-server.certificateSecretName" -}}
eaistack-embedding-server-tls
{{- end }}
