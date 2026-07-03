import requests

import src.http_client as http_client_module
from src.http_client import get_session


def test_get_session_returns_shared_instance():
    first = get_session()
    second = get_session()

    assert isinstance(first, requests.Session)
    assert first is second
    assert first is http_client_module.get_session()


def test_get_session_mounts_retry_adapters_for_both_schemes():
    session = get_session()

    for scheme in ["http://", "https://"]:
        adapter = session.get_adapter(f"{scheme}example.com")
        retry = adapter.max_retries
        assert retry.total == 2
        assert retry.backoff_factor == 0.5
        assert set(retry.status_forcelist) == {502, 503, 504}
        assert set(retry.allowed_methods) == {"GET"}
