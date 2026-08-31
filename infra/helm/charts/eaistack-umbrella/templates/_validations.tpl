{{/*
Cross-chart validations for the umbrella chart.

Helm has no built-in way to validate one subchart's values against
another's, since each subchart only sees its own values plus `global` (see
the fullname-override helpers' comments for the same constraint). These
checks live here, in the umbrella chart itself, and are invoked from a
template that always renders (namespace.yaml) so they run on every install/
upgrade regardless of which subcharts are enabled.
*/}}

{{/*
backend.tracingEnabled with phoenix.enabled: false has no destination for
its traces - the backend would instrument every chat run and then send
spans to an endpoint nothing is listening on. That's not a loud failure
(OTLP export failures are swallowed by the BatchSpanProcessor's background
thread, per app.core.tracing's own comments), so it's the kind of
misconfiguration a deployer could carry for a long time without noticing -
exactly what a fail-fast install-time guard is for, rather than relying on
someone to notice missing traces in Phoenix that isn't even installed.
*/}}
{{- define "eaistack-umbrella.validateTracingRequiresPhoenix" -}}
{{- if and .Values.backend.tracingEnabled (not .Values.phoenix.enabled) }}
{{- fail "backend.tracingEnabled requires phoenix.enabled=true (tracing has no destination otherwise). Set both or neither." }}
{{- end }}
{{- end }}
