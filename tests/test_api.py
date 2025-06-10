import time
import pytest
import requests
from im_internals.api import (
    TimeoutException,
    timeout_decorator,
    ensure_token,
    Api,
    ApiClientCRUD,
)


# ----- Helpers -----
class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text if text is not None else ""

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.RequestException(f"HTTP {self.status_code}")


class DummySession:
    def __init__(self):
        self.next_get = DummyResponse()
        self.next_post = DummyResponse(json_data={"token": "INIT"})
        self.next_put = DummyResponse(json_data={"result": "OK"})
        self.next_delete = DummyResponse()

    def get(self, url, headers=None, timeout=None, params=None):
        return self.next_get

    def post(self, url, data=None, json=None, files=None, headers=None, timeout=None):
        return self.next_post

    def put(self, url, json=None, headers=None, timeout=None):
        return self.next_put

    def delete(self, url, headers=None, timeout=None):
        return self.next_delete


@pytest.fixture(autouse=True)
def patch_requests(monkeypatch):
    import requests as rq
    monkeypatch.setattr(rq, "Session", lambda: DummySession())


# ----- timeout_decorator tests -----
def test_timeout_decorator_allows_fast_function():
    @timeout_decorator(1)
    def fast(a, b=0):
        return a + b
    assert fast(2, b=3) == 5


def test_timeout_decorator_exception_slow_function():
    @timeout_decorator(1)
    def slow():
        time.sleep(3)
        return True

    with pytest.raises(TimeoutException) as exc:
        slow()
    assert "Timed out after 1" in str(exc.value)


# ----- ensure_token tests -----
def test_ensure_token_calls_get_api_token_when_no_token(monkeypatch):
    class C:
        def __init__(self):
            self.api_token = None
            self.called = False

        def get_api_token(self):
            self.called = True
            return "T"

        @ensure_token
        def foo(self):
            return self.api_token

    c = C()
    assert c.foo() == "T"
    assert c.called


def test_ensure_token_refreshes_when_token_present():
    class C:
        def __init__(self):
            self.api_token = "OLD"
            self.refreshed = False

        def verify_and_refresh_api_token(self):
            self.refreshed = True
            self.api_token = "NEW"
            return self.api_token

        @ensure_token
        def foo(self):
            return self.api_token

    c = C()
    # Calling foo() should trigger verify_and_refresh_api_token(),
    # set api_token to "NEW", and return the updated token:
    assert c.foo() == "NEW"
    assert c.refreshed is True


# ----- Api tests -----
def test_init_and_header_generation():
    client = Api("https://data", "https://login", token="X", username="u", pwd="p")
    assert client.username == "u"
    assert client.pwd == "p"
    assert client.api_token == "X"
    # header uses the token
    assert client._get_headers() == {"Authorization": f"Bearer X"}


def test_token_property_triggers_verify_and_refresh(monkeypatch):
    client = Api("https://data", "https://login", token="X")
    monkeypatch.setattr(client, "verify_and_refresh_api_token", lambda: "REF")
    assert client.token == "REF"


def test_user_is_logged_out_behavior():
    client = Api("https://data", "https://login", token="X")

    # 200 OK → not logged out
    client.session.next_get = DummyResponse(status_code=200)
    assert client.user_is_logged_out() is False

    # 403 → logged out
    client.session.next_get = DummyResponse(status_code=403)
    assert client.user_is_logged_out() is True

    # network error → treat as logged out
    def boom(*args, **kw): raise requests.RequestException()
    client.session.get = boom
    assert client.user_is_logged_out() is True


def test_get_api_token_success_and_failure(monkeypatch):
    client = Api("https://data", "https://login", token=None, username="u", pwd="p")

    # success
    client.session.next_post = DummyResponse(status_code=200, json_data={"token": "ABC"})
    tok = client.get_api_token()
    assert tok == "ABC"
    assert client.api_token == "ABC"

    # failure
    def bad(*args, **kw): raise requests.RequestException("nope")
    client.session.post = bad
    assert client.get_api_token() == ""


def test_verify_and_refresh_sets_new_token_when_expired(monkeypatch):
    client = Api("https://data", "https://login", token="OLD")

    # simulate expiry
    monkeypatch.setattr(client, "user_is_logged_out", lambda: True)
    monkeypatch.setattr(client, "get_api_token", lambda: "NEW")
    assert client.verify_and_refresh_api_token() == "NEW"
    assert client.api_token == "NEW"


def test_send_json_and_send_files_and_get_files():
    client = Api("https://data", "https://login", token="T")

    # send_json success
    client.session.next_post = DummyResponse(status_code=200, json_data={"ok": True}, text="OK")
    resp = client.send_json([{"x": 1}])
    assert resp.json() == {"ok": True}

    # send_json bad type
    with pytest.raises(AssertionError):
        client.send_json("not a list")

    # send_json http error
    client.session.next_post = DummyResponse(status_code=500)
    with pytest.raises(requests.RequestException):
        client.send_json([1])

    # send_files success
    client.session.next_post = DummyResponse(status_code=200, json_data={"f": 2})
    resp2 = client.send_files({"a": b"1"}, {"m": "v"})
    assert resp2.json() == {"f": 2}

    # send_files bad inputs
    with pytest.raises(AssertionError):
        client.send_files("nope", {})
    with pytest.raises(AssertionError):
        client.send_files({}, "nope")

    # get_files unimplemented
    with pytest.raises(NotImplementedError):
        client.get_files()


# ----- ApiClientCRUD tests -----
def test_crud_init_requires_valid_base_url():
    with pytest.raises(AssertionError):
        ApiClientCRUD("nope", "https://data", "https://login", token="t")


def test_crud_get_post_put_delete(monkeypatch):
    c = ApiClientCRUD("https://api", "https://data", "https://login", token="T")
    # skip token logic
    monkeypatch.setattr(c, "verify_and_refresh_api_token", lambda: "T")

    # GET
    c.session.next_get = DummyResponse(status_code=200, json_data={"v": 1})
    assert c.get("e", params={"a": 1}) == {"v": 1}
    with pytest.raises(AssertionError):
        c.get(123)
    c.session.next_get = DummyResponse(status_code=500)
    with pytest.raises(requests.RequestException):
        c.get("e")

    # POST
    c.session.next_post = DummyResponse(status_code=200, json_data={"c": True})
    assert c.post("e", body={"x": 1}) == {"c": True}
    with pytest.raises(AssertionError):
        c.post("e", body="nope")
    c.session.next_post = DummyResponse(status_code=500)
    with pytest.raises(requests.RequestException):
        c.post("e", body={})

    # PUT
    c.session.next_put = DummyResponse(status_code=200, json_data={"u": True})
    assert c.put("e", body={"y": 2}) == {"u": True}
    with pytest.raises(AssertionError):
        c.put("e", body="nope")
    c.session.next_put = DummyResponse(status_code=500)
    with pytest.raises(requests.RequestException):
        c.put("e", body={})

    # DELETE
    c.session.next_delete = DummyResponse(status_code=200)
    assert c.delete("e") is None
    with pytest.raises(AssertionError):
        c.delete(123)
    c.session.next_delete = DummyResponse(status_code=404)
    with pytest.raises(requests.RequestException):
        c.delete("e")
