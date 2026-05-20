{{/* Ensure generated object names fit infractl(awacs?) 101 character limit */}}
{{- define "generic.require_k8s_name_len" -}}
{{- $name := . -}}
{{- if gt (len $name) 101 -}}
{{- fail (printf "generated name '%s' exceeds max length 101" $name) -}}
{{- end -}}
{{- $name -}}
{{- end -}}

{{/* Ensure all l7_upstream_templates reference existing parents */}}
{{- define "generic.require_valid_extends" -}}
{{- $templates := . -}}
{{- range $name, $tmpl := $templates }}
  {{- $base := get $tmpl "extends" | default "" -}}
  {{- if and $base (not (hasKey $templates $base)) -}}
    {{- fail (printf "template '%s' extends unknown template '%s'" $name $base) -}}
  {{- end -}}
{{- end -}}
{{- end -}}

{{/* Ensure no recursive template extension loops */}}
{{- define "generic.require_no_recursive_extends" -}}
{{- $templates := . -}}
{{- range $name, $tmpl := $templates }}
  {{- $visited := dict -}}
  {{- $current := $name -}}
  {{- range until 30 }}
    {{- if empty $current }}
      {{- break }}
    {{- end }}
    {{- if hasKey $visited $current }}
      {{- fail (printf "template '%s' has recursive extends via '%s'" $name $current) -}}
    {{- end }}
  {{- $_ := set $visited $current true }}
  {{- $next := get (get $templates $current) "extends" | default "" }}
    {{- $current = $next }}
  {{- end }}
{{- end -}}
{{- end -}}

{{/* Ensure shadow_fqdns sets do not overlap between domains */}}
{{- define "generic.require_no_shadow_fqdns_intersection" -}}
{{- $domains := . -}}
{{- $seen := dict -}}
{{- range $name, $domain := $domains }}
  {{- range (splitList "," (include "generic.domain_shadow_fqdns" (dict "name" $name "domain" $domain)) ) }}
    {{- if hasKey $seen . }}
      {{- fail (printf "shadow_fqdn '%s' intersects between domains" .) -}}
    {{- else }}
      {{- $_ := set $seen . true }}
    {{- end }}
  {{- end }}
{{- end }}
{{- end -}}

{{/* Ensure template extends chain does not exceed 10 levels */}}
{{- define "generic.require_extends_depth_limit" -}}
{{- $templates := . -}}
{{- range $name, $_ := $templates }}
  {{- $current := $name -}}
  {{- $depth := 0 -}}
  {{- range until 11 }}
    {{- if empty $current }}
      {{- break }}
    {{- end }}
    {{- if gt $depth 9 }}
      {{- fail (printf "template '%s' extends chain exceeds max depth 10" $name) -}}
    {{- end }}
    {{- $current = get (get $templates $current) "extends" | default "" }}
    {{- $depth = add $depth 1 }}
  {{- end }}
{{- end -}}
{{- end -}}


{{/* Ensure tvm_settings variables are present when enabled */}}
{{- define "generic.require_tvm_settings_vars" -}}
{{- $values := .Values.tvm_settings -}}
{{- if eq $values.enabled "ENABLED" -}}
  {{- if or (not $values.client_secret_key) (eq $values.client_secret_key "") -}}
    {{- fail "tvm_settings.client_secret_key is required when tvm_settings.enabled is ENABLED" -}}
  {{- end -}}
  {{- if or (not $values.delegation_token) (eq $values.delegation_token "") -}}
    {{- fail "tvm_settings.delegation_token is required when tvm_settings.enabled is ENABLED" -}}
  {{- end -}}
  {{- if or (not $values.secret_id) (eq $values.secret_id "") -}}
    {{- fail "tvm_settings.secret_id is required when tvm_settings.enabled is ENABLED" -}}
  {{- end -}}
  {{- if or (not $values.secret_name) (eq $values.secret_name "") -}}
    {{- fail "tvm_settings.secret_name is required when tvm_settings.enabled is ENABLED" -}}
  {{- end -}}
  {{- if or (not $values.secret_ver) (eq $values.secret_ver "") -}}
    {{- fail "tvm_settings.secret_ver is required when tvm_settings.enabled is ENABLED" -}}
  {{- end -}}
  {{- if or (not $values.tvm_client_id) (eq $values.tvm_client_id "") -}}
    {{- fail "tvm_settings.tvm_client_id is required when tvm_settings.enabled is ENABLED" -}}
  {{- end -}}
{{- end -}}
{{- end -}}

{{/* Validate NetworkMacro grants */}}
{{- define "generic.require_network_macro_grants" -}}
{{- $overrides := .Values.override_defaults | default dict }}
{{- $grants := get $overrides "network_macro_grants" | default (list
    (dict "role" "BILLING" "slug" "svc_quotastaxiinternational")
    (dict "role" "FW" "slug" "svc_vopstaxi_administration")
    (dict "role" "FW" "slug" "svc_experimental_projects_team_administration")
) }}
{{- $billing := 0 -}}
{{- $fw := 0 -}}
{{- range $g := $grants }}
  {{- $role := index $g "role" }}
  {{- if eq $role "BILLING" }}
    {{- $billing = add $billing 1 }}
  {{- else if eq $role "FW" }}
    {{- $fw = add $fw 1 }}
  {{- else }}
    {{- fail (printf "unsupported grant role '%s'" $role) -}}
  {{- end }}
{{- end }}
{{- if ne $billing 1 }}
  {{- fail (printf "expected exactly one BILLING grant, got %d" $billing) -}}
{{- end }}
{{- if lt $fw 1 }}
  {{- fail "expected at least one FW grant" -}}
{{- end }}
{{- end -}}

{{/* Ensure TVM is set up for logging */}}
{{- define "generic.require_tvm_for_logging" -}}
{{- if and .Values.logbroker_topic (ne .Values.tvm_settings.enabled "ENABLED") }}
{{- fail "Logging requires TVM to be enabled" -}}
{{- end }}
{{- end -}}

{{/* Ensure domains define required variables used by their l7_upstream_template */}}
{{- define "generic.require_domain_template_placeholders" -}}
{{- $root := . -}}
{{- range $name, $domain := $root.Values.domains }}
  {{- if $domain.l7_upstream_template }}
    {{- $resolved := include "resolveUpstreamTemplate" (dict "name" $domain.l7_upstream_template "templates" $root.Values.l7_upstream_templates) | fromYaml }}
    {{- $configYaml := toYaml $resolved.config }}
    {{- $needsTvm := contains ".tvm_service_ticket" $configYaml }}
    {{- $needsHostHeader := contains ".host_header" $configYaml }}
    {{- if $needsTvm }}
      {{- $_ := required (printf "domain '%s' uses l7_upstream_template '%s' requiring tvm_service_ticket but domain.tvm_service_ticket is not set" $name $domain.l7_upstream_template) $domain.tvm_service_ticket -}}
    {{- end }}
    {{- if $needsHostHeader }}
      {{- $_ := required (printf "domain '%s' uses l7_upstream_template '%s' requiring host_header but domain.host_header is not set" $name $domain.l7_upstream_template) $domain.host_header -}}
    {{- end }}
  {{- else if $domain.upstreams }}
    {{- range $idx, $upstream := $domain.upstreams }}
      {{- $resolved := include "resolveUpstreamTemplate" (dict "name" $upstream.l7_upstream_template "templates" $root.Values.l7_upstream_templates) | fromYaml }}
      {{- $configYaml := toYaml $resolved.config }}
      {{- $needsTvm := contains ".tvm_service_ticket" $configYaml }}
      {{- $needsHostHeader := contains ".host_header" $configYaml }}
      {{- if $needsTvm }}
        {{- $_ := required (printf "domain '%s' upstream #%d uses l7_upstream_template '%s' requiring tvm_service_ticket but upstream.tvm_service_ticket is not set" $name $idx $upstream.l7_upstream_template) $upstream.tvm_service_ticket -}}
      {{- end }}
      {{- if $needsHostHeader }}
        {{- $_ := required (printf "domain '%s' upstream #%d uses l7_upstream_template '%s' requiring host_header but upstream.host_header is not set" $name $idx $upstream.l7_upstream_template) $upstream.host_header -}}
      {{- end }}
    {{- end }}
  {{- end }}
{{- end -}}
{{- end -}}

{{/* Ensure domains only define placeholders used by their l7_upstream_template */}}
{{- define "generic.require_domain_template_placeholder_usage" -}}
{{- $root := . -}}
{{- range $name, $domain := $root.Values.domains }}
  {{- if $domain.l7_upstream_template }}
    {{- $resolved := include "resolveUpstreamTemplate" (dict "name" $domain.l7_upstream_template "templates" $root.Values.l7_upstream_templates) | fromYaml }}
    {{- $configYaml := toYaml $resolved.config }}
    {{- $usesTvm := contains ".tvm_service_ticket" $configYaml }}
    {{- $usesHostHeader := contains ".host_header" $configYaml }}
    {{- if and $domain.tvm_service_ticket (not $usesTvm) }}
      {{- fail (printf "domain '%s' sets tvm_service_ticket but l7_upstream_template '%s' does not use it" $name $domain.l7_upstream_template) -}}
    {{- end }}
    {{- if and $domain.host_header (not $usesHostHeader) }}
      {{- fail (printf "domain '%s' sets host_header but l7_upstream_template '%s' does not use it" $name $domain.l7_upstream_template) -}}
    {{- end }}
  {{- else if $domain.upstreams }}
    {{- range $idx, $upstream := $domain.upstreams }}
      {{- $resolved := include "resolveUpstreamTemplate" (dict "name" $upstream.l7_upstream_template "templates" $root.Values.l7_upstream_templates) | fromYaml }}
      {{- $configYaml := toYaml $resolved.config }}
      {{- $usesTvm := contains ".tvm_service_ticket" $configYaml }}
      {{- $usesHostHeader := contains ".host_header" $configYaml }}
      {{- if and $upstream.tvm_service_ticket (not $usesTvm) }}
        {{- fail (printf "domain '%s' upstream #%d sets tvm_service_ticket but l7_upstream_template '%s' does not use it" $name $idx $upstream.l7_upstream_template) -}}
      {{- end }}
      {{- if and $upstream.host_header (not $usesHostHeader) }}
        {{- fail (printf "domain '%s' upstream #%d sets host_header but l7_upstream_template '%s' does not use it" $name $idx $upstream.l7_upstream_template) -}}
      {{- end }}
    {{- end }}
  {{- end }}
{{- end -}}
{{- end -}}
