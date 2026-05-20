"""High level client for the Puncher dynamic firewall API."""

from __future__ import annotations

import contextlib
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional

import requests

DEFAULT_ENDPOINT = 'https://api.puncher.yandex-team.ru/api/dynfw'


class PuncherError(RuntimeError):
    """Base exception raised by :class:`Puncher`."""

    def __init__(self, message: str, *, payload: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(message)
        self.payload = payload


class PuncherHTTPError(PuncherError):
    """Exception for unexpected HTTP responses."""

    def __init__(self, status_code: int, message: str, *, payload: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(message, payload=payload)
        self.status_code = status_code


class Puncher:
    """Simple client for interacting with the Puncher dynamic firewall API.

    Parameters
    ----------
    endpoint:
        Base URL of the API. By default the production endpoint is used.
    token:
        OAuth token that will be sent in the ``Authorization`` header. If not
        provided the client will work only with publicly available endpoints
        (most endpoints require authentication).
    session:
        Optional :class:`requests.Session` instance. A new session is created if
        this argument is omitted.
    """

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        *,
        token: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.endpoint = endpoint.rstrip('/')
        self.session = session or requests.Session()
        if token:
            self.session.headers['Authorization'] = f'OAuth {token}'

    # ------------------------------------------------------------------
    # public helpers
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Close the underlying requests session."""

        self.session.close()

    def __enter__(self) -> 'Puncher':  # pragma: no cover - convenience method
        return self

    def __exit__(self, *exc_info: object) -> None:  # pragma: no cover
        self.close()

    # ------------------------------------------------------------------
    # requests
    # ------------------------------------------------------------------
    def list_requests(
        self,
        *,
        status: Optional[Iterable[str]] = None,
        source: Optional[str] = None,
        responsible: Optional[str] = None,
        author: Optional[str] = None,
        page: Optional[int] = None,
    ) -> Mapping[str, Any]:
        """Retrieve Puncher requests with optional filtering."""

        params: Dict[str, Any] = {}
        if status:
            params['status'] = ','.join(status)
        if source:
            params['source'] = source
        if responsible:
            params['responsible'] = responsible
        if author:
            params['author'] = author
        if page is not None:
            params['page'] = page
        return self._request('get', '/requests', params=params)

    def iter_requests(self, **filters: Any) -> Iterator[Mapping[str, Any]]:
        """Iterate over requests transparently handling pagination."""

        response = self.list_requests(**filters)
        while True:
            for request in response.get('requests', []):
                yield request
            next_link = response.get('links', {}).get('next')
            if not next_link:
                break
            response = self._request('get', None, url=next_link)

    def create_request(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Create a new Puncher request."""

        body = {'request': dict(payload)}
        return self._request('post', '/requests', json=body)

    # ------------------------------------------------------------------
    # rules
    # ------------------------------------------------------------------
    def list_rules(
        self,
        *,
        page: Optional[int] = None,
        source: Optional[str] = None,
        destination: Optional[str] = None,
        protocol: Optional[str] = None,
        locations: Optional[Iterable[str]] = None,
        ports: Optional[Iterable[str]] = None,
        sort: Optional[str] = None,
        systems: Optional[Iterable[str]] = None,
        service_id: Optional[str] = None,
        rules: Optional[str] = None,
    ) -> Mapping[str, Any]:
        """Retrieve firewall rules."""

        params: Dict[str, Any] = {}
        if page is not None:
            params['page'] = page
        if source:
            params['source'] = source
        if destination:
            params['destination'] = destination
        if protocol:
            params['protocol'] = protocol
        if locations:
            params['locations'] = ','.join(locations)
        if ports:
            params['ports'] = ','.join(ports)
        if sort:
            params['sort'] = sort
        if systems:
            params['systems'] = ','.join(systems)
        if service_id:
            params['service_id'] = service_id
        if rules:
            params['rules'] = rules
        return self._request('get', '/rules', params=params)

    def iter_rules(self, **filters: Any) -> Iterator[Mapping[str, Any]]:
        """Iterate over rules using automatic pagination."""

        response = self.list_rules(**filters)
        while True:
            for rule in response.get('rules', []):
                yield rule
            next_link = response.get('links', {}).get('next')
            if not next_link:
                break
            response = self._request('get', None, url=next_link)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: Optional[str],
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Optional[Mapping[str, Any]] = None,
        url: Optional[str] = None,
    ) -> Mapping[str, Any]:
        if url is None:
            if path is None:
                raise ValueError('Either path or url must be provided')
            url = f'{self.endpoint}{path}'

        response = self.session.request(
            method.upper(),
            url,
            params=params,
            json=json,
        )

        if response.status_code >= 400:
            raise PuncherHTTPError(response.status_code, response.text or 'HTTP error')

        with contextlib.suppress(ValueError):
            data = response.json()
            if isinstance(data, Mapping) and data.get('status') == 'error':
                raise PuncherError(data.get('message', 'Puncher API error'), payload=data)
            if isinstance(data, Mapping):
                return data

        raise PuncherError('Invalid response from Puncher API', payload={'raw': response.text})
