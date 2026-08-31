{{/*
Expand the name of the chart.
*/}}
{{- define "phoenix.name" -}}
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
{{- define "phoenix.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else if dig "fullnameOverrides" "phoenix" "" (.Values.global | default dict) }}
{{- dig "fullnameOverrides" "phoenix" "" (.Values.global | default dict) | trunc 63 | trimSuffix "-" }}
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
{{- define "phoenix.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "phoenix.labels" -}}
helm.sh/chart: {{ include "phoenix.chart" . }}
{{ include "phoenix.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "phoenix.selectorLabels" -}}
app.kubernetes.io/name: {{ include "phoenix.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the Secret containing the Phoenix TLS certificate (cert-manager-issued).
Unused while tls.enabled defaults to false (see values.yaml and issue #33),
defined now so enabling TLS later is a values.yaml flip, not a template change.
*/}}
{{- define "phoenix.certificateSecretName" -}}
eaistack-phoenix-tls
{{- end }}
