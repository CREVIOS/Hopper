{{/*
Common labels stamped on every chart-managed object.
*/}}
{{- define "hopper.labels" -}}
app.kubernetes.io/part-of: hopper
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/*
Full image reference for one of the three service images.
Usage: {{ include "hopper.image" (dict "root" . "component" .Values.apiGateway) }}
*/}}
{{- define "hopper.image" -}}
{{- $tag := .component.image.tag | default .root.Values.global.imageTag -}}
{{- printf "%s:%s" .component.image.repository $tag -}}
{{- end -}}
