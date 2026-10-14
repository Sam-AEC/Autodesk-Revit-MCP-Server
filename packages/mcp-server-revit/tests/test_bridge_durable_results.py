"""A request that outlives the soft wait must not lose its result (upgrade plan item 0.1).

The HTTP bridge is mocked with a small fake add-in that mirrors the C# queue: it keeps every request by
id, answers /execute within wait_ms, and serves /result/{id}. Time is simulated, so a 90 s script runs
in milliseconds.
"""
from __future__ import annotations

import json

import httpx
import pytest

from revit_mcp_server.bridge.client import BridgeClient
from revit_mcp_server.errors import BridgeError


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeAddin:
    """Serves the add-in's /execute and /result/{id} for commands that take run_seconds."""

    def __init__(self, time: FakeTime, run_seconds: float, outcome: str = "ok") -> None:
        self.time = time
        self.run_seconds = run_seconds
        self.outcome = outcome
        self.runs = 0
        self.execute_bodies: list[dict] = []
        self.jobs: dict[str, float] = {}  # request id -> finish time
        self.auth: set[str | None] = set()

    def _response(self) -> dict:
        if self.outcome == "ok":
            return {"Status": "ok", "Tool": "revit.execute_python", "Result": {"output": "done after the wait", "wall_id": 7}}
        return {"Status": "error", "Tool": "revit.execute_python", "Message": "Boom", "StackTrace": "at X"}

    def _snapshot(self, request_id: str) -> dict:
        if self.time.now >= self.jobs[request_id]:
            state = "done" if self.outcome == "ok" else "failed"
            return {"request_id": request_id, "state": state, "elapsed_ms": 1, "response": self._response()}
        return {"request_id": request_id, "state": "running", "tool": "revit.execute_python", "elapsed_ms": 5, "response": None}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.auth.add(request.headers.get("authorization"))
        path = request.url.path
        if request.method == "POST" and path == "/execute":
            body = json.loads(request.content)
            self.execute_bodies.append(body)
            request_id = body["request_id"]
            if request_id not in self.jobs:  # the same id again is a retry: never run it twice
                self.runs += 1
                self.jobs[request_id] = self.time.now + self.run_seconds
            wait = body["wait_ms"] / 1000
            finish = self.jobs[request_id]
            if finish - self.time.now <= wait:
                self.time.now = max(self.time.now, finish)
                return httpx.Response(200, json=self._response())
            self.time.now += wait
            return httpx.Response(200, json={
                "status": "running", "state": "running", "request_id": request_id,
                "tool": body["tool"], "elapsed_ms": int(wait * 1000),
            })
        if request.method == "GET" and path.startswith("/result/"):
            request_id = path.removeprefix("/result/")
            if request_id not in self.jobs:
                return httpx.Response(404, json={"error": "unknown_or_expired", "request_id": request_id})
            return httpx.Response(200, json=self._snapshot(request_id))
        return httpx.Response(404, json={"error": "Not found"})


def attach(client: BridgeClient, handler, time: FakeTime) -> BridgeClient:
    client._http = httpx.Client(transport=httpx.MockTransport(handler), headers={"Authorization": f"Bearer {client.token}"})
    client._http_key = (client.token, client.timeout)
    client._clock = time.clock
    client._sleep = time.sleep
    return client


def make_client(run_seconds: float, outcome: str = "ok", soft_wait: float = 25.0):
    time = FakeTime()
    addin = FakeAddin(time, run_seconds, outcome)
    client = attach(BridgeClient("http://bridge.test", timeout=30, token="tok", soft_wait=soft_wait), addin.handler, time)
    return client, addin, time


def collect(client: BridgeClient, result: dict, attempts: int = 6) -> dict:
    for _ in range(attempts):
        if result.get("status") != "running":
            return result
        result = client.get_result(result["request_id"])
    return result


def test_fast_command_returns_its_result_in_one_post():
    client, addin, time = make_client(run_seconds=2)
    result = client.call_tool("revit.execute_python", {"code": "x"})
    assert result["output"] == "done after the wait"
    assert result["element_id"] == 7, "element id normalisation still applies"
    assert addin.runs == 1 and time.sleeps == []
    assert addin.execute_bodies[0]["wait_ms"] == 25000
    assert addin.auth == {"Bearer tok"}


def test_command_that_finishes_during_polling_returns_the_real_output():
    client, addin, time = make_client(run_seconds=40)
    result = client.call_tool("revit.execute_python", {"code": "x"}, wait_s=60)
    # The add-in holds the call for 25 s (the HTTP timeout minus a margin), then the client polls.
    assert result["output"] == "done after the wait"
    assert addin.runs == 1
    assert time.sleeps[:4] == [0.5, 1.0, 2.0, 3.0], "polls back off instead of failing"


def test_command_that_outlives_the_soft_wait_returns_running_and_can_be_resumed():
    client, addin, time = make_client(run_seconds=90)
    first = client.call_tool("revit.execute_python", {"code": "slow"})
    assert first["status"] == "running"
    request_id = first["request_id"]
    assert request_id == addin.execute_bodies[0]["request_id"]
    assert "revit_get_result" in first["message"]
    assert addin.runs == 1
    assert time.now <= 25.5, "the soft wait is a bound, not a floor"

    still = client.get_result(request_id, wait_s=5)
    assert still["status"] == "running" and still["request_id"] == request_id

    final = collect(client, still)
    assert final["output"] == "done after the wait"
    assert addin.runs == 1, "collecting the result never re-runs the command"
    assert client.get_result(request_id, wait_s=0)["output"] == "done after the wait", "kept for later calls"


def test_get_result_with_zero_wait_does_not_sleep():
    client, _addin, time = make_client(run_seconds=90)
    first = client.call_tool("revit.execute_python", {"code": "slow"})
    slept = len(time.sleeps)
    assert client.get_result(first["request_id"], wait_s=0)["status"] == "running"
    assert len(time.sleeps) == slept


def test_failed_command_raises_bridge_error_with_the_add_in_message():
    client, _addin, _time = make_client(run_seconds=40, outcome="error")
    first = client.call_tool("revit.execute_python", {"code": "x"})
    assert first["status"] == "running"
    with pytest.raises(BridgeError, match="Boom"):
        client.get_result(first["request_id"], wait_s=60)


def test_unknown_or_expired_id_is_a_clear_error():
    client, _addin, _time = make_client(run_seconds=1)
    with pytest.raises(BridgeError, match="unknown to the add-in"):
        client.get_result("does-not-exist")


def test_timeout_style_error_from_an_older_add_in_is_still_an_error():
    time = FakeTime()
    handler = lambda request: httpx.Response(200, json={  # noqa: E731
        "Status": "error", "Tool": "x", "Message": "Request r timed out after 30000ms"})
    client = attach(BridgeClient("http://bridge.test", soft_wait=25), handler, time)
    with pytest.raises(BridgeError, match="timed out"):
        client.call_tool("x", {})


def test_transport_retry_reuses_the_request_id_and_keeps_the_running_path():
    time = FakeTime()
    addin = FakeAddin(time, run_seconds=90)
    posts = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts["n"] += 1
            if posts["n"] == 1:
                raise httpx.ConnectError("connection reset", request=request)
        return addin.handler(request)

    client = attach(BridgeClient("http://bridge.test", soft_wait=25), flaky, time)
    result = client.call_tool("revit.execute_python", {"code": "x"})
    assert result["status"] == "running"
    assert addin.runs == 1, "the retry carried the same request id, so the add-in did not run it twice"
    assert len({b["request_id"] for b in addin.execute_bodies}) == 1


def test_lost_connection_while_polling_names_the_request_id():
    time = FakeTime()
    addin = FakeAddin(time, run_seconds=90)

    def dropping(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            raise httpx.ConnectError("refused", request=request)
        return addin.handler(request)

    client = attach(BridgeClient("http://bridge.test", soft_wait=25), dropping, time)
    with pytest.raises(BridgeError, match="may still be running"):
        client.call_tool("revit.execute_python", {"code": "x"}, wait_s=60)


def test_soft_wait_is_configurable_from_the_environment(monkeypatch):
    monkeypatch.setenv("AEC_BRIDGE_SOFT_WAIT_SECONDS", "7")
    assert BridgeClient("http://bridge.test").soft_wait == 7
    monkeypatch.setenv("AEC_BRIDGE_SOFT_WAIT_SECONDS", "nonsense")
    assert BridgeClient("http://bridge.test").soft_wait == 25
