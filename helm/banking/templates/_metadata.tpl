{{- define "banking.labels" -}}
app.kubernetes.io/name: {{ .service | quote }}
app.kubernetes.io/instance: {{ .root.Release.Name | quote }}
app.kubernetes.io/part-of: banking
app.kubernetes.io/component: {{ .service | quote }}
app.kubernetes.io/managed-by: {{ .root.Release.Service | quote }}
app.kubernetes.io/version: {{ trimPrefix "sha256:" .digest | trunc 12 | quote }}
banking.example/environment: {{ trimPrefix "banking-" .root.Release.Namespace | quote }}
{{- end -}}
{{- define "banking.annotations" -}}
banking.example/owner: {{ .root.Values.ownership.owner | quote }}
banking.example/image-digest: {{ .digest | quote }}
{{- end -}}
