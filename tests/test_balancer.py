import io
from typing import Any
import yaml

import pytest
import infractl_helm.lib as lib
from infractl_helm.lib import Balancer


@pytest.fixture
def balancer_setup(tmp_path, monkeypatch):
    base_dir = tmp_path / 'infractl'
    (base_dir / 'lib').mkdir(parents=True)
    (base_dir / 'namespace').mkdir()

    config_data: dict[str, Any] = {
        'domains': {
            'alpha': {
                'target_fqdn': ['dst.one', 'dst.two'],
                'target_port': 8443,
            },
            'beta': {'target_fqdn': 'dst.one', 'target_port': 8443},
            'gamma': 'invalid',
        },
        'override_defaults': {'awacs_namespace_name': 'custom.name'},
        'environment': 'prod',
    }

    config_path = base_dir / 'namespace' / 'balancer.yaml'
    with config_path.open('w', encoding='utf-8') as fh:
        yaml.safe_dump(config_data, fh)

    fake_lib_path = base_dir / 'lib' / '__init__.py'
    fake_lib_path.write_text('# dummy module for tests\n', encoding='utf-8')
    monkeypatch.setattr(lib, '__file__', str(fake_lib_path))
    monkeypatch.chdir(base_dir)

    balancer = Balancer('namespace', 'balancer')
    return balancer, config_data


def test_load_config_iter_domains_and_network_macro(balancer_setup):
    balancer, config_data = balancer_setup

    loaded = Balancer._load_config('namespace', 'balancer')
    assert loaded == config_data

    assert list(balancer._iter_domains()) == [
        ('alpha', config_data['domains']['alpha']),
        ('beta', config_data['domains']['beta']),
        ('gamma', {}),
    ]

    assert balancer._get_network_macro() == '_AWS_RTC_TAXI_CUSTOM_NAME_BALANCER_PROD_NETS_'


def test_request_puncher_rules_aggregates_and_creates_requests(balancer_setup, monkeypatch):
    balancer, _ = balancer_setup
    output = io.StringIO()

    class DummyPuncher:
        def __init__(self, endpoint=None, token=None):
            self.endpoint = endpoint
            self.token = token
            self.iter_calls: list[dict[str, Any]] = []
            self.requests: list[dict[str, Any]] = []

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def iter_rules(self, **filters):
            self.iter_calls.append(filters)
            destination = filters.get('destination')
            if destination == 'dst.one':
                return [
                    {
                        'ports': [' 8080 ', '8443'],
                        'sources': [
                            {'machine_name': 'source.one'},
                            {'machine_name': ''},
                        ],
                        'tasks': ['TASK-1', ' task-2 '],
                        'locations': [' VLA ', 'sas'],
                    }
                ]
            if destination == 'dst.two':
                return [
                    {
                        'ports': [],
                        'sources': [{'machine_name': 'source.two'}],
                        'tasks': [],
                        'locations': [],
                    }
                ]
            return []

        def create_request(self, payload):
            self.requests.append(payload)
            return {'request': {'id': 101}}

    dummy = DummyPuncher()
    monkeypatch.setattr(lib, 'Puncher', lambda *a, **kw: dummy)

    balancer.request_puncher_rules(token='token-value', endpoint='https://api', stream=output)

    text = output.getvalue()
    assert 'Collecting Puncher rules for 2 target balancer(s).' in text
    assert '# Target balancer: dst.one:8443' in text
    assert 'Retrieved 1 rule(s).' in text
    assert '# Summary' in text
    assert '"source.one"' in text
    assert '_AWS_RTC_TAXI_CUSTOM_NAME_BALANCER_PROD_NETS_' in text
    assert dummy.iter_calls == [
        {
            'destination': 'dst.one',
            'ports': ['8443'],
            'protocol': 'tcp',
            'rules': 'exclude_inactive',
        },
        {
            'destination': 'dst.two',
            'ports': ['8443'],
            'protocol': 'tcp',
            'rules': 'exclude_inactive',
        },
        {'destination': '_AWS_RTC_TAXI_CUSTOM_NAME_BALANCER_PROD_NETS_', 'protocol': 'tcp'},
    ]

    assert dummy.requests == [
        {
            'sources': ['source.one'],
            'destinations': [
                '_AWS_RTC_TAXI_CUSTOM_NAME_BALANCER_PROD_NETS_',
                'balancer',
            ],
            'protocol': 'tcp',
            'ports': ['8080', '8443'],
            'comment': (
                'Проксирование dst.one через AWS-балансер Такси balancer. '
                'Исходное правило на балансер в России запрашивалось в '
                'https://st.yandex-team.ru/TASK-1, https://st.yandex-team.ru/task-2. '
                'Правило запрашивается на макрос из-за особенностей работы NLB в AWS, подробнее - https://st.yandex-team.ru/NOCREQUE'
                'STS-71466#682f1b5ceca3590f7125eb64'
            ),
            'locations': ['VLA', 'sas'],
        },
        {
            'sources': ['source.two'],
            'destinations': [
                '_AWS_RTC_TAXI_CUSTOM_NAME_BALANCER_PROD_NETS_',
                'balancer',
            ],
            'protocol': 'tcp',
            'ports': ['8443'],
            'comment': (
                'Проксирование dst.two через AWS-балансер Такси balancer. '
                'Правило запрашивается на макрос из-за особенностей работы NLB в AWS, подробнее - https://st.yandex-team.ru/NOCREQUE'
                'STS-71466#682f1b5ceca3590f7125eb64'
            ),
        },
    ]


def test_rule_helpers_and_comment(balancer_setup):
    balancer, _ = balancer_setup

    ports = Balancer._normalize_rule_ports(['8080', ' 8080 '], '8443')
    assert ports == {'8080'}

    default_ports = Balancer._normalize_rule_ports([], '8443')
    assert default_ports == {'8443'}

    rule = {
        'sources': [
            {'machine_name': 'SRC1'},
            {'machine_name': ''},
            'not-a-mapping',
        ],
        'tasks': ['TASK-1', '', '   '],
        'locations': [' vla ', ''],
    }

    assert Balancer._extract_rule_sources(rule) == {'SRC1'}
    assert Balancer._extract_rule_tasks(rule) == {'TASK-1'}
    assert Balancer._extract_rule_locations(rule) == {'vla'}

    comment = balancer._build_request_comment(['dst.two', 'dst.one'], ['TASK-2', 'TASK-1', 'TASK-1'])
    assert 'dst.one, dst.two' in comment
    assert 'https://st.yandex-team.ru/TASK-1' in comment
    assert 'https://st.yandex-team.ru/TASK-2' in comment

    no_task_comment = balancer._build_request_comment(['dst.one'], [])
    assert 'Исходное правило на балансер' not in no_task_comment


def test_request_puncher_rules_requires_token(balancer_setup, monkeypatch):
    balancer, _ = balancer_setup
    monkeypatch.delenv('PUNCHER_TOKEN', raising=False)
    output = io.StringIO()

    with pytest.raises(lib.BalancerError):
        balancer.request_puncher_rules(stream=output)


def test_request_puncher_rules_no_targets_exits_early(balancer_setup, monkeypatch):
    balancer, _ = balancer_setup
    output = io.StringIO()

    monkeypatch.setattr(balancer, 'iter_puncher_rule_targets', lambda: iter(()))

    def fail(*args, **kwargs):
        raise AssertionError('Puncher should not be instantiated')

    monkeypatch.setattr(lib, 'Puncher', fail)

    balancer.request_puncher_rules(token='tok', stream=output)

    assert 'No puncher rules are required for the current configuration.' in output.getvalue()


def test_request_puncher_rules_handles_empty_aggregation(balancer_setup, monkeypatch):
    balancer, _ = balancer_setup
    output = io.StringIO()

    monkeypatch.setattr(
        balancer,
        'iter_puncher_rule_targets',
        lambda: iter((('dst', '443'),)),
    )

    class DummyPuncher:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def iter_rules(self, **filters):
            return []

    monkeypatch.setattr(lib, 'Puncher', lambda *a, **kw: DummyPuncher())

    balancer.request_puncher_rules(token='tok', stream=output)

    assert 'No puncher rules were discovered for the configured target balancers.' in output.getvalue()


def test_request_puncher_rules_detects_existing_sources(balancer_setup, monkeypatch):
    balancer, _ = balancer_setup
    output = io.StringIO()

    monkeypatch.setattr(
        balancer,
        'iter_puncher_rule_targets',
        lambda: iter((('dst', '443'),)),
    )

    class DummyPuncher:
        def __init__(self):
            self.created = False

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def iter_rules(self, **filters):
            if filters.get('destination') == 'dst':
                return [
                    {
                        'sources': [{'machine_name': 'srv'}],
                        'ports': ['443'],
                        'tasks': [],
                        'locations': [],
                    }
                ]
            return [
                {
                    'sources': [{'machine_name': 'srv'}],
                    'ports': ['443'],
                }
            ]

        def create_request(self, payload):
            self.created = True
            raise AssertionError('create_request should not be called')

    dummy = DummyPuncher()
    monkeypatch.setattr(lib, 'Puncher', lambda *a, **kw: dummy)

    balancer.request_puncher_rules(token='tok', stream=output)

    assert 'No additional rules are required.' in output.getvalue()
    assert dummy.created is False


def test_request_puncher_rules_requests_missing_ports(balancer_setup, monkeypatch):
    balancer, _ = balancer_setup
    output = io.StringIO()

    monkeypatch.setattr(
        balancer,
        'iter_puncher_rule_targets',
        lambda: iter((('dst', '443'),)),
    )

    class DummyPuncher:
        def __init__(self):
            self.requests = []

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def iter_rules(self, **filters):
            if filters.get('destination') == 'dst':
                return [
                    {
                        'sources': [{'machine_name': 'srv'}],
                        'ports': ['443', ' 8443 '],
                        'tasks': [],
                        'locations': [],
                    }
                ]
            return [
                {
                    'sources': [{'machine_name': 'srv'}],
                    'ports': ['443'],
                }
            ]

        def create_request(self, payload):
            self.requests.append(payload)
            return {'request': {'id': 202}}

    dummy = DummyPuncher()
    monkeypatch.setattr(lib, 'Puncher', lambda *a, **kw: dummy)

    balancer.request_puncher_rules(token='tok', stream=output)

    assert len(dummy.requests) == 1
    request = dummy.requests[0]
    assert request['sources'] == ['srv']
    assert request['ports'] == ['8443']


def test_request_puncher_rules_success_without_id(balancer_setup, monkeypatch):
    balancer, _ = balancer_setup
    output = io.StringIO()

    monkeypatch.setattr(
        balancer,
        'iter_puncher_rule_targets',
        lambda: iter((('dst', '443'),)),
    )

    class DummyPuncher:
        def __init__(self):
            self.requests = []

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def iter_rules(self, **filters):
            if filters.get('destination') == 'dst':
                return [
                    {
                        'sources': [{'machine_name': 'srv'}],
                        'ports': ['80'],
                        'tasks': [],
                        'locations': [],
                    }
                ]
            return []

        def create_request(self, payload):
            self.requests.append(payload)
            return {}

    dummy = DummyPuncher()
    monkeypatch.setattr(lib, 'Puncher', lambda *a, **kw: dummy)

    balancer.request_puncher_rules(token='tok', stream=output)

    text = output.getvalue()
    assert 'Puncher request created successfully.' in text
    assert any(request['sources'] == ['srv'] for request in dummy.requests)


def test_load_config_missing_file(tmp_path, monkeypatch):
    base_dir = tmp_path / 'infractl'
    lib_dir = base_dir / 'lib'
    lib_dir.mkdir(parents=True)
    init_path = lib_dir / '__init__.py'
    init_path.write_text('# lib placeholder\n', encoding='utf-8')
    monkeypatch.setattr(lib, '__file__', str(init_path))
    monkeypatch.chdir(base_dir)

    with pytest.raises(lib.BalancerError) as exc:
        Balancer._load_config('namespace', 'balancer')

    assert 'Values file not found' in str(exc.value)


def test_load_config_invalid_structure(tmp_path, monkeypatch):
    base_dir = tmp_path / 'infractl'
    lib_dir = base_dir / 'lib'
    config_dir = base_dir / 'namespace'
    config_dir.mkdir(parents=True)
    init_path = lib_dir / '__init__.py'
    lib_dir.mkdir(parents=True, exist_ok=True)
    init_path.write_text('# lib placeholder\n', encoding='utf-8')
    monkeypatch.setattr(lib, '__file__', str(init_path))
    monkeypatch.chdir(base_dir)

    config_path = config_dir / 'balancer.yaml'
    with config_path.open('w', encoding='utf-8') as fh:
        yaml.safe_dump(['not', 'a', 'mapping'], fh)

    with pytest.raises(lib.BalancerError) as exc:
        Balancer._load_config('namespace', 'balancer')

    assert 'Unexpected balancer configuration structure' in str(exc.value)


def test_network_macro_and_awacs_defaults(tmp_path, monkeypatch):
    base_dir = tmp_path / 'infractl'
    lib_dir = base_dir / 'lib'
    config_dir = base_dir / 'namespace'
    config_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True, exist_ok=True)
    init_path = lib_dir / '__init__.py'
    init_path.write_text('# lib placeholder\n', encoding='utf-8')
    monkeypatch.setattr(lib, '__file__', str(init_path))
    monkeypatch.chdir(base_dir)

    config_path = config_dir / 'balancer.name-with.dots.yaml'
    with config_path.open('w', encoding='utf-8') as fh:
        yaml.safe_dump({'domains': {}}, fh)

    balancer = Balancer('namespace', 'balancer.name-with.dots')

    assert balancer._get_awacs_namespace_name() == 'balancer.name-with.dots'
    assert balancer._get_network_macro() == '_AWS_RTC_TAXI_BALANCER_NAME_WITH_DOTS_BALANCER_UNKNOWN_NETS_'
