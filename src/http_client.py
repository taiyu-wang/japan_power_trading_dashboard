from __future__ import annotations

import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


POOL_CONNECTIONS = 10
POOL_MAXSIZE = 10
RETRY_TOTAL = 2
RETRY_BACKOFF_FACTOR = 0.5
RETRY_STATUS_FORCELIST = [502, 503, 504]

_session: requests.Session | None = None
_session_lock = threading.Lock()


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS_FORCELIST,
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(pool_connections=POOL_CONNECTIONS, pool_maxsize=POOL_MAXSIZE, max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_session() -> requests.Session:
    """Return the shared, lazily-created HTTP session with pooling and GET retries.

    requests.Session is safe for the concurrent GET usage in this codebase
    (ThreadPoolExecutor fetchers); creation is guarded by a lock so all callers
    share one connection pool.
    """
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = _build_session()
    return _session
