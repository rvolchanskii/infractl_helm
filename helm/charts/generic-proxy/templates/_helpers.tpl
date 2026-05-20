{{/*
Get awacs namespace name, should be same with helm release name
*/}}
{{- define "generic.awacs_namespace_name" -}}
{{- default .Release.Name .Values.override_defaults.awacs_namespace_name }}
{{- end }}

{{/*
Set default awacs namespace category
*/}}
{{- define "generic.category" -}}
{{- default  "quotastaxiinternational" .Values.override_defaults.category }}
{{- end }}

{{/*
Set default awacs namespace abc slug(will be quota ABC as well)
*/}}
{{- define "generic.abc_service_slug" -}}
{{- default  "quotastaxiinternational" .Values.override_defaults.abc_service_slug }}
{{- end }}

{{/*
Get L7-balancers data center, default - EXT
*/}}
{{- define "generic.l7_balancer_dc" -}}
{{- default "EXT" .Values.override_defaults.l7_balancer_dc }}
{{- end }}

{{/*
Get L7-balancers data center location, default - 448e71_test_ext=EXT
*/}}
{{- define "generic.l7_balancer_location" -}}
{{- if and (eq (include "generic.l7_balancer_dc" .) "EXT") (eq .Values.environment "testing") }}
{{- default  "448e71_test_ext" .Values.override_defaults.l7_balancer_location }}
{{- end }}
{{- if and (eq (include "generic.l7_balancer_dc" .) "EXT") (eq .Values.environment "production") }}
{{- default "448e71_ext" .Values.override_defaults.l7_balancer_location }}
{{- end }}
{{- end }}

{{/*
Get L7-balancers spec.balancer_spec.config_transport.nanny_static_file.instance_tags.ctype
*/}}
{{- define "generic.instance_tags_ctype" -}}
{{- if eq .Values.environment "testing" }}
{{- "testing" }}
{{- else }}
{{- "prod" }}
{{- end }}
{{- end }}

{{/*
Generate L7-balancer id
*/}}
{{- define "generic.l7_balancer_id" -}}
{{- default (printf "%s_%s" (include "generic.awacs_namespace_name" .) (include "generic.l7_balancer_location" .)) .Values.override_defaults.l7_balancer_id }}
{{- end }}

{{/*
Generate L7-balancer service id
*/}}
{{- define "generic.l7_balancer_service_id" -}}
{{- default (printf "rtc_balancer_%s_%s" (regexReplaceAll "\\." (include "generic.awacs_namespace_name" .) "_") (include "generic.l7_balancer_location" .)) .Values.override_defaults.l7_balancer_service_id }}
{{- end }}

{{/*
Get deploy_project, by default deploy_project=category
*/}}
{{- define "generic.deploy_project" -}}
{{- default  (include "generic.category" .) .Values.override_defaults.deploy_project}}
{{- end }}

{{/*
Get monitoring_project, by default monitoring_project=category
*/}}
{{- define "generic.monitoring_project" -}}
{{- default  (include "generic.category" .) .Values.override_defaults.monitoring_project}}
{{- end }}

{{/*
Get traffic source, by default TS_DIRECT
*/}}
{{- define "generic.traffic_source" -}}
{{- default  "TS_DIRECT" .Values.override_defaults.traffic_source}}
{{- end }}

{{/*
Generate L7-balancer name
*/}}
{{- define "generic.l7_balancer_name" -}}
{{- regexReplaceAll "_" (default (include "generic.l7_balancer_id" .) .Values.override_defaults.l7_balancer_name) "-" }}
{{- end }}

{{/*
Default awacs limits, can be changed only by awacs team admins
*/}}
{{- define "generic.object_upper_limits_certificate" -}}
{{- default  "47" .Values.override_defaults.object_upper_limits_certificate}}
{{- end }}
{{- define "generic.object_upper_limits_l3_balancer" -}}
{{- default  "1" .Values.override_defaults.object_upper_limits_l3_balancer}}
{{- end }}

{{/*
Generate NetworkMacro name
*/}}
{{- define "generic.network_macro" -}}
{{/*
Return network macro in `_AWS_RTC_TAXI_<ns>_BALANCER_<env>_NETS_` format.
It can be overridden via `override_defaults.network_macro`.
*/}}
{{- $default := printf "_AWS_RTC_TAXI_%s_BALANCER_%s_NETS_" (include "generic.awacs_namespace_name" . | replace "." "-" | replace "-" "_" | upper) (upper .Values.environment) }}
{{- default $default .Values.override_defaults.network_macro }}
{{- end }}

{{/*
Generate NetworkMacro in full-macro-name format
*/}}
{{- define "generic.network_macro_name" -}}
{{/*{{- trimAll "_" include "generic.network_macro" | lower | replace "_" "-" }}*/}}
{{- include "generic.network_macro" . | trimAll "_" | lower | replace "_" "-" }}
{{- end }}

{{/*
Get parent network macro name
*/}}
{{- define "generic.parent_network_macro_name" -}}
{{- default "_AWS_RTC_TAXI_NETS_" .Values.override_defaults.parent_network_macro_name }}
{{- end }}

{{/*
Define NetworkMacro grants
*/}}
{{- define "generic.network_macro_grants" -}}
{{- $default := list
    (dict "role" "BILLING" "slug" "svc_quotastaxiinternational")
    (dict "role" "FW" "slug" "role_svc_quotastaxiinternational_administration")
}}
{{- $overrides := .Values.override_defaults | default dict }}
{{- $grants := default $default (get $overrides "network_macro_grants") }}
{{- toYaml $grants }}
{{- end }}

{{/*
Define DC location
*/}}
{{- define "generic.location" -}}
{{- $loc := default dict .Values.override_defaults.location }}
node_segment: {{ default "rtc-aws-eu-central-1-taxi" $loc.node_segment }}
city:         {{ default "Frankfurt" $loc.city }}
country:      {{ default "Germany" $loc.country }}
country_code: {{ default "DE" $loc.country_code }}
provider:     {{ default "AWS" $loc.provider }}
yp_cluster:   {{ default "EXT" $loc.yp_cluster }}
{{- end }}

{{/* Define RTC over AWS allocation, used in pods per zone and pods per rack calculations */}}
{{- define "generic.rtc_setup" -}}
availability_zones_count: {{ default 3 .Values.override_defaults.availability_zones_count }}
nodes_count: {{ default 21 .Values.override_defaults.nodes_count }}
{{- end }}

{{/* Define pod allocation */}}
{{- define "generic.antiaffinity_constraints" -}}
{{- $rtc_setup := include "generic.rtc_setup" . | fromYaml }}
node_max_pods: {{ default (div (add .Values.number_of_pods (sub $rtc_setup.nodes_count 1)) $rtc_setup.nodes_count) .Values.override_defaults.node_max_pods }}
rack_max_pods: {{ default (div (add .Values.number_of_pods (sub $rtc_setup.availability_zones_count 1)) $rtc_setup.availability_zones_count) .Values.override_defaults.rack_max_pods }}
{{- end }}

{{/* Define degrade parameters */}}
{{- define "generic.degrade_params" -}}
{{- $antiaffinity_constraints := include "generic.antiaffinity_constraints" . | fromYaml }}
max_unavailable_pods: {{ default $antiaffinity_constraints.node_max_pods .Values.override_defaults.max_unavailable_pods }}
min_update_delay_seconds: {{ default 300 .Values.override_defaults.min_update_delay_seconds }}
{{- end }}

{{/* Define antirobot parameters */}}
{{- define "generic.antirobot_params" -}}
service: {{ default "taxi" .Values.override_defaults.antirobot_service }}
req_group: {{ default (include "generic.awacs_namespace_name" . | replace "." "_" ) .Values.override_defaults.antirobot_req_group }}
{{- end }}


{{- define "getUpstreamKey" -}}
{{- $domain := . -}}
{{- if and $domain.l7_upstream_template $domain.target_fqdn -}}
{{- printf "%s-%s-%s" ($domain.target_fqdn | replace "." "-") (toString (default 443 $domain.target_port)) $domain.l7_upstream_template -}}
{{- else -}}
{{- if $domain.l7_upstream_template -}}
{{- $domain.l7_upstream_template -}}
{{- else -}}
{{- $configHash := (toYaml $domain.l7_upstream_config | sha256sum | trunc 8) -}}
{{- printf "%s-%s-custom-%s" ($domain.target_fqdn | replace "." "-") (toString (default 443 $domain.target_port)) $configHash -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Generate AwacsUpstream name based on domain information
*/}}
{{- define "generic.awacs_upstream_name" -}}
{{- $domain := .domain -}}
{{- $root := .root -}}
{{- $seed := include "generic.awacs_namespace_name" $root -}}
{{- if $domain.host_header }}{{- $seed = printf "%s-%s" $seed $domain.host_header }}{{- end -}}
{{- printf "%s-%s" (include "getUpstreamKey" $domain) ($seed | sha256sum | trunc 8) }}
{{- end -}}

{{- define "generic.modules_whitelist" -}}
{{- if .Values.override_defaults.modules_whitelist -}}
{{- .Values.override_defaults.modules_whitelist | toYaml | nindent 6 -}}
{{- else -}}
{{- dict | toYaml -}}
{{- end -}}
{{- end -}}

{{/*
Recursive merge of templates with extends support
*/}}
{{/*
Resolve upstream template with extends support and merged headers
*/}}
{{- define "resolveUpstreamTemplate" -}}
{{- $templates := .templates -}}
{{- $name := .name -}}
{{- $chain := list -}}
{{- $visited := dict -}}
{{- $current := $name -}}
{{- range until 10 }}
  {{- if or (empty $current) (hasKey $visited $current) }}
    {{- break }}
  {{- end }}
  {{- $_ := set $visited $current true }}
  {{- $tmpl := get $templates $current | toYaml | fromYaml }}
  {{- $chain = append $chain $tmpl }}
  {{- $current = $tmpl.extends }}
{{- end }}
{{- $chain = reverse $chain }}
{{- $result := dict -}}
{{- $headers := list -}}
{{- range $chain }}
  {{- $result = mergeOverwrite $result . }}
  {{- $headers = concat $headers (dig "config" "l7_upstream_macro" "headers" (list) .) }}
{{- end }}
{{- $seen := dict -}}
{{- $uniqueRev := list -}}
{{- range (reverse $headers) }}
  {{- $actions := keys . }}
  {{- if not (empty $actions) }}
    {{- $action := index $actions 0 }}
    {{- $target := dig $action "target" nil . }}
    {{- $key := printf "%s" $action }}
    {{- if $target }}
      {{- $key = printf "%s:%v" $action $target }}
    {{- else }}
      {{- $key = printf "%s:%s" $action (toJson (get . $action)) }}
    {{- end }}
    {{- if not (hasKey $seen $key) }}
      {{- $_ := set $seen $key true }}
      {{- $uniqueRev = append $uniqueRev . }}
    {{- end }}
  {{- end }}
{{- end }}
{{- $unique := reverse $uniqueRev }}
{{- if not (hasKey $result.config "l7_upstream_macro") }}
  {{- $_ := set $result.config "l7_upstream_macro" dict }}
{{- end }}
{{- $_ := set $result.config.l7_upstream_macro "headers" $unique }}
{{- toYaml $result }}
{{- end }}

{{/*
Generate key for unique target fqdn and port combinations
*/}}
{{- define "getTargetKey" -}}
{{- printf "%s-%s" (.target_fqdn | replace "." "-") (toString (default 443 .target_port)) -}}
{{- end -}}

{{/*
Return shadow_fqdns for a domain with fallback to the domain name
*/}}
{{- define "generic.domain_shadow_fqdns" -}}
{{- $name := .name -}}
{{- $domain := .domain -}}
{{- $result := default (list $name) $domain.shadow_fqdns -}}
{{- join "," $result -}}
{{- end -}}

{{/*
Return whether PuncherRuleSet should be created for the given domain.
Default is true but can be overridden globally via
`override_defaults.request_puncher_rules` or per-domain via
`request_puncher_rules`.
*/}}
{{- define "generic.request_puncher_rules" -}}
{{- $domain := .domain -}}
{{- $root := .root -}}
{{- $request := true -}}
{{- if hasKey $root.Values.override_defaults "request_puncher_rules" }}
  {{- $request = $root.Values.override_defaults.request_puncher_rules }}
{{- end }}
{{- if hasKey $domain "request_puncher_rules" }}
  {{- $request = $domain.request_puncher_rules }}
{{- end }}
{{- if $request }}true{{ else }}false{{ end -}}
{{- end -}}

{{/*
Resolve balancer config template with extends support
*/}}
{{- define "resolveBalancerConfigTemplate" -}}
{{- $templates := .templates -}}
{{- $name := .name -}}
{{- $chain := list -}}
{{- $visited := dict -}}
{{- $current := $name -}}
{{- range until 10 }}
  {{- if or (empty $current) (hasKey $visited $current) }}
    {{- break }}
  {{- end }}
  {{- $_ := set $visited $current true }}
  {{- $tmpl := get $templates $current | toYaml | fromYaml }}
  {{- $chain = append $chain $tmpl }}
  {{- $current = $tmpl.extends }}
{{- end }}
{{- $chain = reverse $chain }}
{{- $result := dict -}}
{{- range $chain }}
  {{- $result = mergeOverwrite $result . }}
{{- end }}
{{- toYaml $result }}
{{- end }}
