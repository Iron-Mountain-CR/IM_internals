"""
API client
==========
HTTP API client with token auth, per-call timeouts, and retry-on-timeout, built on `requests`.

Two classes:

- `Api` — token-lifecycle management (fetch/verify/refresh) plus `send_json`/`send_files` for the
  bespoke document-submission APIs used by several client pipelines in this repo (e.g. AXA's
  Mountaineer API). `get_files()` is an unimplemented placeholder (always raises
  `NotImplementedError`) — no client currently needs a download path.
- `ApiClientCRUD(Api)` — adds `get`/`post`/`put`/`delete` against a `base_url`-prefixed REST API.
  This is the closest existing analogue for a future replacement of the legacy
  `Frequently_used_Prod.send_files_prod.JSON` class (see this repo's root CLAUDE.md — deferred
  migration blocker for `McDonald_SFTP_prod.py`/`AXA_temp_manual_prod.py`), though nothing currently
  uses it for that purpose.

Usage::

    api = Api(web_url="https://example.com/api", login_web_url="https://example.com/login",
              username="user", pwd="pass")
    api.send_json([{"key": "value"}])

Every network-calling method is wrapped in `@retry_on_timeout` (retries `TimeoutException` up to 3
times with exponential backoff) and `@timeout_decorator(seconds)` (runs the call on a background
daemon thread and raises `TimeoutException` if it doesn't finish in time).

`timeout_decorator` used to run the call inside a `with ThreadPoolExecutor(max_workers=1) as exec:`
block (fixed 2026-09-23). That looked equivalent but wasn't: a Python thread can't be killed once
started, so a call that never actually returns left that worker thread running forever - and exiting
the `with` block calls `exec.shutdown(wait=True)`, which blocks until every submitted thread
finishes, timeout or not. `concurrent.futures.thread` also registers a process-wide `atexit` hook
that joins *every* worker thread any `ThreadPoolExecutor` in the process ever created, so this could
hang the whole interpreter at shutdown even for code that never touched this decorator's return
value. The replacement spawns a plain `daemon=True` thread instead: `Thread.join(timeout)` still
gives up after `timeout` seconds (execution stays just as sequential from the caller's side - the
call already ran on a background thread before, this doesn't add new concurrency), but a daemon
thread is never joined at interpreter exit, so an abandoned one can't block the process from exiting.
"""
import logging
import requests
import functools
import threading
from typing import List, Dict, Any
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential, before_sleep_log

from . import logging as pl


class TimeoutException(Exception):
    """
    Custom exception to indicate that a function has exceeded its time limit.
    """
    pass


# Standard logger kept solely for tenacity's before_sleep_log (requires stdlib Logger)
_tenacity_logger = logging.getLogger(__name__)

# -----------------------------
# Retry decorator for timeouts
# -----------------------------
retry_on_timeout = retry(
    retry=retry_if_exception_type(TimeoutException),
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=3, max=10),
    before_sleep=before_sleep_log(_tenacity_logger, logging.WARNING)
)


def timeout_decorator(timeout: int):
    """
    Decorator to enforce a maximum execution time on a function.

    :param timeout: Maximum seconds the function is allowed to run.
    :type timeout: int
    :return: Decorated function that raises TimeoutException if time limit exceeded.
    :rtype: Callable

    :raises TimeoutException: When function execution surpasses the timeout.
    """
    assert timeout > 0, "Timeout must be positive"

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result_box = {}

            def target():
                try:
                    result_box["value"] = func(*args, **kwargs)
                except BaseException as e:
                    result_box["error"] = e

            worker = threading.Thread(target=target, daemon=True)
            worker.start()
            worker.join(timeout)

            if worker.is_alive():
                # Call is still running (likely a stalled network call). We can't kill it, so we
                # abandon it as a daemon thread - it won't block interpreter shutdown - and give
                # up here instead of blocking the caller (and every caller of this decorator, and
                # potentially interpreter exit) forever.
                raise TimeoutException(f"Timed out after {timeout}s")
            if "error" in result_box:
                raise result_box["error"]
            return result_box.get("value")
        return wrapper

    return decorator


def ensure_token(func):
    """
    Decorator to ensure a valid API token exists before method execution.

    If no token is set, it calls get_api_token(). If verification fails, it refreshes the token.

    :param func: Method requiring a valid token.
    :type func: Callable
    :return: Wrapped method with token validation.
    :rtype: Callable
    """
    def wrapper(self, *args, **kwargs):
        if not getattr(self, 'api_token', None):
            pl.progress('No token found, fetching new token.')
            self.api_token = self.get_api_token()
        else:
            self.verify_and_refresh_api_token()
        return func(self, *args, **kwargs)
    return wrapper


class Api:
    """
    Core API client handling authentication, timeouts, and retries.
    """

    def __init__(self, web_url: str, login_web_url: str, token: str = None, username: str = "", pwd: str = ""):
        """
        Initializes the API class with the necessary URLs and login credentials.

        :param web_url: The base URL for data-related API operations.
        :type web_url: str
        :param login_web_url: The URL for obtaining a new API token.
        :type login_web_url: str
        :param token: Optional, an existing API token for immediate use.
        :type token: str, optional
        :param username: The username for the API login.
        :type username: str
        :param pwd: The password for the API login.
        :type pwd: str
        """
        assert isinstance(web_url, str) and ("http://" in web_url or "https://" in web_url), \
            "Web URL should be a string with the structure of URL like https://www.example.com"
        assert isinstance(login_web_url, str) and ("http://" in login_web_url or "https://" in login_web_url), \
            "Login URL should be a string with the structure of URL like https://www.login-page.com"
        assert isinstance(username, str), "Username must always be only string!"
        assert isinstance(pwd, str), "As we now do not support crypted password, we need a string!"

        self.username = username
        self.pwd = pwd
        self.api_token = token
        self.data_url = web_url
        self.login_url = login_web_url
        self.session = requests.Session()
        self.api_token = token if token else self.get_api_token()

    @property
    def token(self) -> str:
        """
        Return a fresh API token, refreshing if expired.

        :return: Valid API token string.
        :rtype: str
        """
        return self.verify_and_refresh_api_token()

    @retry_on_timeout
    @timeout_decorator(5 * 60)
    def verify_and_refresh_api_token(self) -> str:
        """
        Verify current token validity and refresh if expired.

        :return: Current or newly fetched API token.
        :rtype: str
        :raises TimeoutException: When checking token exceeds time limit.
        :raises requests.RequestException: On HTTP errors during verification.
        """
        pl.progress('Verifying token validity.')
        try:
            if self.user_is_logged_out():
                pl.progress('Token expired, fetching new one.')
                self.api_token = self.get_api_token()
        except TimeoutException:
            pl.error('Token verification timed out, will retry fetch.')
            self.api_token = self.get_api_token()
        except requests.RequestException as e:
            pl.error(f'Failed to verify token: {e}, fetching new one.')
            self.api_token = self.get_api_token()
        return self.api_token

    @retry_on_timeout
    @timeout_decorator(5 * 60)
    def user_is_logged_out(self) -> bool:
        """
        Determine if the current API token is expired based on a test request.

        :return: True if expired (status 403), False otherwise.
        :rtype: bool
        """
        try:
            resp = self.session.get(self.data_url, headers=self._get_headers(), timeout=30)
            return resp.status_code == 403
        except requests.RequestException:
            return True

    @retry_on_timeout
    @timeout_decorator(5 * 60)
    def get_api_token(self) -> str:
        """
        Obtain a new API token using stored credentials.

        :return: New API token string.
        :rtype: str
        :raises TimeoutException: When token request exceeds time limit.
        :raises requests.RequestException: On HTTP errors during token fetch.
        """
        pl.progress('Requesting new API token.')
        try:
            resp = self.session.post(self.login_url, data={'login': self.username, 'pwd': self.pwd}, timeout=30)
            resp.raise_for_status()
            token = resp.json().get('token', '')
            self.api_token = token
            return token
        except TimeoutException:
            pl.error('get_api_token function exceeded the time limit of 5 minutes.')
            raise
        except requests.RequestException as e:
            pl.error(f'Failed to retrieve new API token. Error: {e}')
            return ''

    def _get_headers(self) -> dict:
        """
        Construct authorization headers for API requests.

        :return: Headers containing the Bearer token.
        :rtype: dict
        """
        return {'Authorization': f'Bearer {self.api_token}'}

    @ensure_token
    @retry_on_timeout
    @timeout_decorator(20 * 60)
    def send_json(self, files_list: List[str | Dict[str, Any]] | Dict[str, Any]) -> requests.Response:
        """
        Send a list of items as JSON payload to the API endpoint.

        :param files_list: List of items to serialize and send.
        :type files_list: list
        :return: Response from the API.
        :rtype: requests.Response
        :raises TimeoutException: If request exceeds allowed time.
        :raises requests.RequestException: On HTTP errors during send.
        """
        assert isinstance(files_list, list), "List of files must contain a JSON list-like structure!!"

        pl.progress('Sending JSON payload.')
        try:
            resp = self.session.post(self.data_url, json=files_list, headers=self._get_headers(), timeout=60)
            resp.raise_for_status()
            pl.log_kv("Response", text=resp.text)
            return resp
        except TimeoutException:
            pl.error('send_json function exceeded the time limit of 20 minutes.')
            raise
        except requests.RequestException as e:
            pl.error(f'Failed to send JSON data to API. Error: {e}')
            raise

    @ensure_token
    @retry_on_timeout
    @timeout_decorator(20 * 60)
    def send_files(self, files_dict: Dict[str, str | bytes], form_data: Dict[str, Any]):
        """
        Send files via multipart/form-data to the API endpoint.

        :param files_dict: Mapping of filename to file-like object or bytes.
        :type files_dict: dict
        :param form_data: Additional form fields.
        :type form_data: dict
        :return: Response from the API.
        :rtype: requests.Response
        :raises TimeoutException: If upload exceeds allowed time.
        :raises requests.RequestException: On HTTP errors during upload.
        """
        assert isinstance(files_dict, dict), ("Files_dict must contain a dictionary in structure: "
                                              "{'filename': b'file_bytes', ...}")
        assert isinstance(form_data, dict), "Metadata must be in a dictionary strcture: {'metadata1': value, ...}"

        pl.progress('Sending multipart files.')
        try:
            resp = self.session.post(self.data_url, files=files_dict, data=form_data, headers=self._get_headers(),
                                     timeout=60)
            resp.raise_for_status()
            return resp
        except TimeoutException:
            pl.error('send_files function exceeded the time limit of 20 minutes.')
            raise
        except requests.RequestException as e:
            pl.error(f'Failed to send files to the API. Error: {e}')
            raise

    @ensure_token
    @retry_on_timeout
    @timeout_decorator(20 * 60)
    def get_files(self):
        """
        Placeholder for downloading files from the API.

        :raises NotImplementedError: Always, until implemented.
        """
        pl.progress("get_files is not implemented yet.")
        raise NotImplementedError


# -----------------------------
# CRUD extension
# -----------------------------
class ApiClientCRUD(Api):
    """
    Extension of Api providing standard CRUD HTTP methods.
    """

    def __init__(self, base_url: str, *args, api_key: str = None, **kwargs):
        """
        Initialize CRUD client with base URL and credentials.

        :param base_url: Root URL for CRUD endpoints.
        :param web_url: Base URL for data operations (inherited).
        :param login_web_url: URL for authentication requests (inherited).
        :param token: Optional initial API token.
        :param username: Username for login.
        :param pwd: Password for login.
        """
        assert isinstance(base_url, str) and ("http://" in base_url or "https://" in base_url), \
            "Base URL that is used as a prefix for all endpoints must be a string and contain 'http://' or 'https://'"

        super().__init__(*args, **kwargs)
        self.base_url = base_url
        if api_key:
            self.api_token = api_key

    @ensure_token
    @retry_on_timeout
    @timeout_decorator(10)
    def get(self, endpoint: str, params: dict = None) -> dict:
        """
        Perform an HTTP GET request.

        :param endpoint: API endpoint path to append to base_url.
        :type endpoint: str
        :param params: Query parameters for the request.
        :type params: dict
        :return: JSON-decoded response body.
        :rtype: dict
        :raises TimeoutException: If request exceeds time limit.
        :raises requests.RequestException: On HTTP errors.
        """
        assert isinstance(endpoint, str), "Endpoint must be an existing web-path"

        pl.progress(f'GET {endpoint}')
        try:
            resp = self.session.get(f"{self.base_url}/{endpoint}", headers=self._get_headers(), params=params,
                                    timeout=10)
            resp.raise_for_status()
            return resp.json()
        except TimeoutException:
            pl.error(f'GET {endpoint} timed out.')
            raise
        except requests.RequestException as e:
            pl.error(f'Failed GET {endpoint}: {e}')
            raise

    @ensure_token
    @retry_on_timeout
    @timeout_decorator(10)
    def post(self, endpoint: str, body: Dict[str, Any]) -> dict:
        """
        Perform an HTTP POST request with a JSON body.

        :param endpoint: API endpoint path to append to base_url.
        :type endpoint: str
        :param body: JSON-serializable dictionary to send.
        :type body: dict
        :return: JSON-decoded response body.
        :rtype: dict
        :raises TimeoutException: If request exceeds time limit.
        :raises requests.RequestException: On HTTP errors.
        """
        assert isinstance(endpoint, str), "Endpoint must be an existing web-path"
        assert isinstance(body, dict), "Body must a dictionary/JSON like structure. Example: {'metadata': value, ...}"

        pl.progress(f'POST {endpoint}')
        try:
            resp = self.session.post(f"{self.base_url}/{endpoint}", headers=self._get_headers(), json=body, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except TimeoutException:
            pl.error(f'POST {endpoint} timed out.')
            raise
        except requests.RequestException as e:
            pl.error(f'Failed POST {endpoint}: {e}')
            raise

    @ensure_token
    @retry_on_timeout
    @timeout_decorator(10)
    def put(self, endpoint: str, body: dict) -> dict:
        """
         Perform an HTTP PUT request with a JSON body.

        :param endpoint: API endpoint path to append to base_url.
        :type endpoint: str
        :param body: JSON-serializable dictionary to send.
        :type body: dict
        :return: JSON-decoded response body.
        :rtype: dict
        :raises TimeoutException: If request exceeds time limit.
        :raises requests.RequestException: On HTTP errors.
        """
        assert isinstance(endpoint, str), "Endpoint must be an existing web-path"
        assert isinstance(body, dict), "Body must a dictionary/JSON like structure. Example: {'metadata': value, ...}"

        pl.progress(f'PUT {endpoint}')
        try:
            resp = self.session.put(f"{self.base_url}/{endpoint}", headers=self._get_headers(), json=body, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except TimeoutException:
            pl.error(f'PUT {endpoint} timed out.')
            raise
        except requests.RequestException as e:
            pl.error(f'Failed PUT {endpoint}: {e}')
            raise

    @ensure_token
    @retry_on_timeout
    @timeout_decorator(10)
    def delete(self, endpoint: str) -> None:
        """
        Perform an HTTP DELETE request.

        :param endpoint: API endpoint path to append to base_url.
        :type endpoint: str
        :raises TimeoutException: If request exceeds time limit.
        :raises requests.RequestException: On HTTP errors.
        """
        assert isinstance(endpoint, str), "Endpoint must be an existing web-path"

        pl.progress(f'DELETE {endpoint}')
        try:
            resp = self.session.delete(f"{self.base_url}/{endpoint}", headers=self._get_headers(), timeout=10)
            resp.raise_for_status()
        except TimeoutException:
            pl.error(f'DELETE {endpoint} timed out.')
            raise
        except requests.RequestException as e:
            pl.error(f'Failed DELETE {endpoint}: {e}')
            raise
