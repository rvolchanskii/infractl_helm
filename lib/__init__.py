"""High level helpers used by :mod:`manage.py`."""

import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Iterator, Mapping, Optional, TextIO, Tuple

import yaml

from .puncher import DEFAULT_ENDPOINT, Puncher, PuncherError


class BalancerError(RuntimeError):
    """Base error raised by :class:`Balancer`."""


class Balancer:
    """Representation of a single balancer configuration."""

    def __init__(self, namespace: str, balancer: str) -> None:
        self.namespace = namespace
        self.balancer = balancer
        self._config = self._load_config(namespace, balancer)

    # ------------------------------------------------------------------
    # public helpers
    # ------------------------------------------------------------------
    @property
    def config(self) -> Mapping[str, object]:
        """Return raw YAML configuration."""

        return self._config

    def request_puncher_rules(
        self,
        *,
        token: Optional[str] = None,
        endpoint: Optional[str] = None,
        stream: Optional[TextIO] = None,
    ) -> None:
        """Fetch Puncher rules for all destinations that require them.

        The resulting JSON output aggregates rules from every page returned by
        Puncher so that multi-page responses are represented in full.

        Parameters
        ----------
        token:
            OAuth token used to authenticate requests. If omitted the value is
            read from the ``PUNCHER_TOKEN`` environment variable.
        endpoint:
            Optional custom Puncher endpoint. Defaults to the production API.
        stream:
            Optional ``write``-supporting object used for output. When omitted
            the data is printed to :data:`sys.stdout`.
        """

        output = stream or sys.stdout
        token = token or os.environ.get('PUNCHER_TOKEN')
        if not token:
            raise BalancerError(
                'Puncher token is required. Provide it via the token argument or '
                'set the PUNCHER_TOKEN environment variable.'
            )

        endpoint = endpoint or os.environ.get('PUNCHER_ENDPOINT') or DEFAULT_ENDPOINT

        targets = list(self.iter_puncher_rule_targets())
        if not targets:
            print('No puncher rules are required for the current configuration.', file=output)
            return

        network_macro = self._get_network_macro()
        print(
            'Collecting Puncher rules for '
            f'{len(targets)} target balancer(s). '
            f'Destination network macro: {network_macro}.',
            file=output,
        )

        aggregated_sources: dict[str, dict[str, object]] = {}

        with Puncher(endpoint=endpoint, token=token) as client:
            for destination, port in targets:
                print(f'\n# Target balancer: {destination}:{port}', file=output)
                request_params = {
                    'destination': destination,
                    'ports': [str(port)],
                    'protocol': 'tcp',
                    'rules': 'exclude_inactive',
                }
                try:
                    rules = list(client.iter_rules(**request_params))
                except PuncherError as exc:  # pragma: no cover - network error path
                    print(f'Failed to fetch rules: {exc}', file=output)
                    if exc.payload:
                        print(
                            json.dumps(exc.payload, indent=2, ensure_ascii=False),
                            file=output,
                        )
                        continue

                print(f'  Retrieved {len(rules)} rule(s).', file=output)
                for rule in rules:
                    if not isinstance(rule, Mapping):
                        continue
                    ports = self._normalize_rule_ports(rule.get('ports'), str(port))
                    tasks = self._extract_rule_tasks(rule)
                    locations = self._extract_rule_locations(rule)
                    for source in self._extract_rule_sources(rule):
                        info = aggregated_sources.setdefault(
                            source,
                            {
                                'ports': set(),
                                'references': set(),
                                'targets': set(),
                                'tasks': set(),
                                'locations': set(),
                            },
                        )
                        info['ports'].update(ports)
                        info['references'].add(f'{destination}:{port}')
                        info['targets'].add(destination)
                        info['tasks'].update(tasks)
                        info['locations'].update(locations)

            try:
                existing_rules = list(client.iter_rules(destination=network_macro, protocol='tcp'))
            except PuncherError as exc:  # pragma: no cover - network error path
                print(
                    f'\nUnable to retrieve existing rules for {network_macro}: {exc}',
                    file=output,
                )
                if exc.payload:
                    print(f'Invalid payload found: {json.dumps(exc.payload)}', file=output)
                existing_sources: dict[str, set[str]] = {}
            else:
                existing_sources = {}
                for rule in existing_rules:
                    if not isinstance(rule, Mapping):
                        print(f'Invalid rule found: {json.dumps(rule)}', file=output)
                        continue
                    ports = self._normalize_rule_ports(rule.get('ports'), '')
                    for source in self._extract_rule_sources(rule):
                        info = existing_sources.setdefault(source, set())
                        info.update(ports)
                print(
                    f'\nExisting rules for {network_macro}: {len(existing_sources)} source(s) found.',
                    file=output,
                )

        if not aggregated_sources:
            print(
                '\nNo puncher rules were discovered for the configured target balancers.',
                file=output,
            )
            return

        already_allowed = {
            source
            for source, info in aggregated_sources.items()
            if info['ports'].issubset(existing_sources.get(source, set()))
        }
        pending_sources: dict[str, dict[str, object]] = {}
        for source, info in aggregated_sources.items():
            missing_ports = info['ports'].difference(existing_sources.get(source, set()))
            if not missing_ports:
                continue
            pending_info = dict(info)
            pending_info['ports'] = set(missing_ports)
            pending_sources[source] = pending_info

        print('\n# Summary', file=output)
        print(
            f'Total unique sources discovered: {len(aggregated_sources)}',
            file=output,
        )
        print(
            f'Sources already allowed for {network_macro}: {len(already_allowed)}',
            file=output,
        )

        if not pending_sources:
            print('No additional rules are required.', file=output)
            return

        print(f'Rules to request ({len(pending_sources)}):', file=output)
        for source in sorted(pending_sources):
            info = pending_sources[source]
            ports = sorted(
                info['ports'],
                key=lambda value: (0, int(value)) if str(value).isdigit() else (1, str(value)),
            )
            locations = sorted(info['locations'])
            targets = sorted(info['targets'])
            tasks = sorted(info['tasks'])
            comment = self._build_request_comment(targets, tasks)
            destinations = [network_macro, self.balancer]
            request_payload = {
                'sources': [source],
                'destinations': destinations,
                'protocol': 'tcp',
                'ports': ports,
                'comment': comment,
            }
            if locations:
                request_payload['locations'] = locations

            display_payload = dict(request_payload)
            display_payload['references'] = sorted(info['references'])
            print(json.dumps(display_payload, indent=2, ensure_ascii=False, sort_keys=True), file=output)

            try:
                response = client.create_request(request_payload)
            except PuncherError as exc:  # pragma: no cover - network error path
                print(
                    f'Failed to create Puncher request for {source}: {exc}',
                    file=output,
                )
                if getattr(exc, 'payload', None):
                    print(
                        json.dumps(exc.payload, indent=2, ensure_ascii=False, sort_keys=True),
                        file=output,
                    )
                continue

            request_id = response.get('request', {}).get('id') if isinstance(response, Mapping) else None
            if request_id:
                print(
                    f'Puncher request created successfully (ID: {request_id}).',
                    file=output,
                )
            else:
                print('Puncher request created successfully.', file=output)

    def iter_puncher_rule_targets(self) -> Iterator[Tuple[str, str]]:
        """Yield unique ``(destination, port)`` tuples that require rules."""

        aggregated: dict[Tuple[str, str], None] = {}
        for _domain_name, domain in self._iter_domains():
            targets = domain.get('target_fqdn')
            if isinstance(targets, str):
                target_list = [targets]
            elif isinstance(targets, Iterable) and not isinstance(targets, (str, bytes, Mapping)):
                target_list = [t for t in targets if isinstance(t, str) and t]
            else:
                continue
            port_value = domain.get('target_port', 443)
            port = str(port_value)
            for target in target_list:
                aggregated.setdefault((target, port), None)

        for target, port in aggregated:
            yield target, port

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _load_config(namespace: str, balancer: str) -> Mapping[str, object]:
        config_path = Path(os.path.join(namespace, f'{balancer}.yaml'))
        if not config_path.is_file():
            raise BalancerError(f'Values file not found: {config_path}')

        with config_path.open('r', encoding='utf-8') as stream:
            try:
                data = yaml.safe_load(stream) or {}
            except yaml.YAMLError as exc:  # pragma: no cover - depends on input data
                raise BalancerError(str(exc)) from exc

        if not isinstance(data, Mapping):
            raise BalancerError('Unexpected balancer configuration structure')
        return data

    def _iter_domains(self) -> Iterator[Tuple[str, Mapping[str, object]]]:
        domains = self._config.get('domains', {})
        if isinstance(domains, Mapping):
            for name, raw_domain in domains.items():
                if isinstance(raw_domain, Mapping):
                    yield name, raw_domain
                else:
                    yield name, {}

    def _get_network_macro(self) -> str:
        overrides = self._config.get('override_defaults', {})
        if isinstance(overrides, Mapping):
            override_macro = overrides.get('network_macro')
            if isinstance(override_macro, str) and override_macro:
                return override_macro

        namespace_name = self._get_awacs_namespace_name()
        sanitized = namespace_name.replace('.', '-').replace('-', '_').upper()
        environment = str(self._config.get('environment', '')).upper() or 'UNKNOWN'
        return f'_AWS_RTC_TAXI_{sanitized}_BALANCER_{environment}_NETS_'

    def _get_awacs_namespace_name(self) -> str:
        overrides = self._config.get('override_defaults', {})
        if isinstance(overrides, Mapping):
            custom_name = overrides.get('awacs_namespace_name')
            if isinstance(custom_name, str) and custom_name:
                return custom_name
        return self.balancer

    @staticmethod
    def _normalize_rule_ports(raw_ports: object, default_port: str) -> set[str]:
        ports: set[str] = set()
        if isinstance(raw_ports, Iterable) and not isinstance(raw_ports, (str, bytes, Mapping)):
            for raw in raw_ports:
                text = str(raw).strip()
                if text:
                    ports.add(text)
        if not ports:
            ports.add(str(default_port))
        return ports

    @staticmethod
    def _extract_rule_sources(rule: Mapping[str, object]) -> set[str]:
        sources: set[str] = set()
        raw_sources = rule.get('sources')
        if isinstance(raw_sources, Iterable) and not isinstance(raw_sources, (str, bytes, Mapping)):
            for raw_source in raw_sources:
                if isinstance(raw_source, Mapping):
                    name = raw_source.get('machine_name')
                    if isinstance(name, str) and name:
                        sources.add(name)
        return sources

    @staticmethod
    def _extract_rule_tasks(rule: Mapping[str, object]) -> set[str]:
        tasks: set[str] = set()
        raw_tasks = rule.get('tasks')
        if isinstance(raw_tasks, Iterable) and not isinstance(raw_tasks, (str, bytes, Mapping)):
            for raw_task in raw_tasks:
                text = str(raw_task).strip()
                if text:
                    tasks.add(text)
        return tasks

    @staticmethod
    def _extract_rule_locations(rule: Mapping[str, object]) -> set[str]:
        locations: set[str] = set()
        raw_locations = rule.get('locations')
        if isinstance(raw_locations, Iterable) and not isinstance(raw_locations, (str, bytes, Mapping)):
            for raw_location in raw_locations:
                text = str(raw_location).strip()
                if text:
                    locations.add(text)
        return locations

    def _build_request_comment(self, targets: Iterable[str], tasks: Iterable[str]) -> str:
        targets_text = ', '.join(sorted(set(targets))) or ''
        unique_tasks = sorted(set(tasks))
        tasks_text = ', '.join(f'https://st.yandex-team.ru/{task}' for task in unique_tasks) if unique_tasks else ''
        comment = f'Проксирование {targets_text} через AWS-балансер Такси {self.balancer}. '
        if tasks_text:
            comment += f'Исходное правило на балансер в России запрашивалось в {tasks_text}. '
        comment += (
            'Правило запрашивается на макрос из-за особенностей работы NLB в AWS, подробнее - '
            'https://st.yandex-team.ru/NOCREQUESTS-71466#682f1b5ceca3590f7125eb64'
        )
        return comment
