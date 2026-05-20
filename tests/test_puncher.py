import pytest

from infractl_helm.lib.puncher import Puncher, PuncherError, PuncherHTTPError


class DummyResponse:
    def __init__(self, *, status_code=200, json_data=None, text=''):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.json_calls = 0

    def json(self):
        self.json_calls += 1
        if isinstance(self._json_data, Exception):
            raise self._json_data
        if self._json_data is None:
            raise ValueError('No JSON available')
        return self._json_data


class DummySession:
    def __init__(self):
        self.requests = []
        self._responses = []
        self.closed = False
        self.headers = {}

    def queue_response(self, response):
        self._responses.append(response)

    def request(self, method, url, *, params=None, json=None, headers=None):
        if not self._responses:
            raise AssertionError('No queued responses left')
        combined_headers = dict(self.headers)
        if headers:
            combined_headers.update(headers)
        self.requests.append({
            'method': method,
            'url': url,
            'params': params,
            'json': json,
            'headers': combined_headers,
        })
        return self._responses.pop(0)

    def close(self):
        self.closed = True


@pytest.fixture
def session():
    return DummySession()


def test_list_requests_builds_expected_params(session):
    session.queue_response(DummyResponse(json_data={'requests': [], 'links': {}}))
    puncher = Puncher(endpoint='https://example.net/api', token='tok', session=session)

    response = puncher.list_requests(
        status=['open', 'closed'],
        source='source-service',
        responsible='user.login',
        author='author.login',
        page=3,
    )

    assert response == {'requests': [], 'links': {}}
    assert session.requests == [
        {
            'method': 'GET',
            'url': 'https://example.net/api/requests',
            'params': {
                'status': 'open,closed',
                'source': 'source-service',
                'responsible': 'user.login',
                'author': 'author.login',
                'page': 3,
            },
            'json': None,
            'headers': {'Authorization': 'OAuth tok'},
        }
    ]


def test_iter_requests_handles_pagination(session):
    session.queue_response(
        DummyResponse(
            json_data={
                'requests': [{'id': 1}],
                'links': {'next': 'https://api.example.net/requests?page=2'},
            }
        )
    )
    session.queue_response(DummyResponse(json_data={'requests': [{'id': 2}], 'links': {}}))
    puncher = Puncher(endpoint='https://api.example.net', session=session)

    requests = list(puncher.iter_requests(status=['approved']))

    assert requests == [{'id': 1}, {'id': 2}]
    assert session.requests == [
        {
            'method': 'GET',
            'url': 'https://api.example.net/requests',
            'params': {'status': 'approved'},
            'json': None,
            'headers': {},
        },
        {
            'method': 'GET',
            'url': 'https://api.example.net/requests?page=2',
            'params': None,
            'json': None,
            'headers': {},
        },
    ]


def test_create_request_wraps_payload_and_sets_oauth_header(session):
    session.queue_response(DummyResponse(json_data={'request': {'id': 123, 'status': 'pending'}}))
    puncher = Puncher(endpoint='https://example.net/api', token='secret-token', session=session)

    payload = {'title': 'Allow access', 'comment': 'Details'}
    response = puncher.create_request(payload)

    assert response == {'request': {'id': 123, 'status': 'pending'}}
    assert session.requests == [
        {
            'method': 'POST',
            'url': 'https://example.net/api/requests',
            'params': None,
            'json': {'request': payload},
            'headers': {'Authorization': 'OAuth secret-token'},
        }
    ]


def test_list_rules_builds_expected_params(session):
    session.queue_response(DummyResponse(json_data={'rules': [], 'links': {}}))
    puncher = Puncher(endpoint='https://puncher.test', token='tok', session=session)

    response = puncher.list_rules(
        page=2,
        source='src',
        destination='dst',
        protocol='tcp',
        locations=['sas', 'iva'],
        ports=['80', '443'],
        sort='-updated',
        systems=['system-a', 'system-b'],
        service_id='service-id',
        rules='exclude_inactive',
    )

    assert response == {'rules': [], 'links': {}}
    assert session.requests == [
        {
            'method': 'GET',
            'url': 'https://puncher.test/rules',
            'params': {
                'page': 2,
                'source': 'src',
                'destination': 'dst',
                'protocol': 'tcp',
                'locations': 'sas,iva',
                'ports': '80,443',
                'sort': '-updated',
                'systems': 'system-a,system-b',
                'service_id': 'service-id',
                'rules': 'exclude_inactive',
            },
            'json': None,
            'headers': {'Authorization': 'OAuth tok'},
        }
    ]


def test_request_requires_path_or_url(session):
    puncher = Puncher(endpoint='https://api.example', session=session)

    with pytest.raises(ValueError, match='Either path or url must be provided'):
        puncher._request('get', None)


def test_close_closes_underlying_session(session):
    puncher = Puncher(endpoint='https://api.example', session=session)

    puncher.close()

    assert session.closed is True


def test_iter_rules_handles_pagination(session):
    first_page = {
        'rules': [{'id': 1}],
        'links': {'next': 'https://puncher.test/rules?page=2'},
    }
    second_page = {'rules': [{'id': 2}], 'links': {}}
    session.queue_response(DummyResponse(json_data=first_page))
    session.queue_response(DummyResponse(json_data=second_page))
    puncher = Puncher(endpoint='https://puncher.test', session=session)

    rules = list(puncher.iter_rules(destination='dst', ports=['80'], protocol='tcp', systems=['sys']))

    assert rules == [{'id': 1}, {'id': 2}]
    assert session.requests == [
        {
            'method': 'GET',
            'url': 'https://puncher.test/rules',
            'params': {
                'destination': 'dst',
                'ports': '80',
                'protocol': 'tcp',
                'systems': 'sys',
            },
            'json': None,
            'headers': {},
        },
        {
            'method': 'GET',
            'url': 'https://puncher.test/rules?page=2',
            'params': None,
            'json': None,
            'headers': {},
        },
    ]


def test_request_raises_http_error_on_bad_status(session):
    session.queue_response(DummyResponse(status_code=500, text='Internal error'))
    puncher = Puncher(endpoint='https://example.net', session=session)

    with pytest.raises(PuncherHTTPError) as exc_info:
        puncher._request('get', '/rules')

    assert exc_info.value.status_code == 500
    assert str(exc_info.value) == 'Internal error'


def test_request_raises_puncher_error_on_error_payload(session):
    session.queue_response(DummyResponse(json_data={'status': 'error', 'message': 'boom', 'details': {'code': 42}}))
    puncher = Puncher(endpoint='https://example.net', session=session)

    with pytest.raises(PuncherError) as exc_info:
        puncher._request('get', '/rules')

    assert exc_info.value.payload == {'status': 'error', 'message': 'boom', 'details': {'code': 42}}


def test_request_raises_puncher_error_on_non_json_response(session):
    session.queue_response(DummyResponse(text='<!DOCTYPE html>', json_data=ValueError('bad')))
    puncher = Puncher(endpoint='https://example.net', session=session)

    with pytest.raises(PuncherError) as exc_info:
        puncher._request('get', '/rules')

    assert exc_info.value.payload == {'raw': '<!DOCTYPE html>'}
