"""Harness safety and honest evidence, using fake transports; no Revit or sleeps."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("live_acceptance_harness", ROOT / "scripts/revit/acceptance/run.py")
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)
GUID = "b3e63473-1641-4c71-9425-510915cddc65"


def options(*extra):
    return harness.parser().parse_args(["--pid", "123", "--expected-document", "Acceptance scratch",
                                       "--expected-guid", GUID, *extra])


def context(title="Acceptance scratch", guid=GUID, mode="ask_first"):
    return {"ok": True, "addin_supports_context": True, "busy": False,
            "document": {"title": title, "guid": guid, "path": "unsaved", "is_family": False},
            "addin": {"module_id": "module-1", "assembly_file_time_utc": "2026-10-14T08:00:00Z"},
            "queue": {"depth": 0, "running": None}, "server": {"approval_mode": mode}}


def read_result(opts=None, marker="", elements=4):
    opts = opts or options()
    return {"success": True, "mode": "read", "model_changes_in_read_mode": 0,
            "output": json.dumps({"identity": [opts.pid, opts.expected_document, opts.expected_guid],
                                  "elements": elements, "warnings": 0, "modifiable": False,
                                  "stdlib": [1, 2], "marker": marker})}


class FakeClient:
    def __init__(self, ctx=None, refusal=None, changed=False, duration=False):
        self.context = ctx or context()
        self.refusal = refusal or harness.REFUSAL + " (found: Transaction)"
        self.changed, self.duration = changed, duration
        self.calls, self.reads, self.marker, self.polls = [], 0, "", 0

    def call(self, tool, args):
        self.calls.append((tool, args))
        if tool == "revit_get_context":
            return self.context
        if tool == "revit_get_result":
            self.polls += 1
            return read_result(marker=self.marker)
        assert tool == "revit_execute_python" and args["mode"] == "read"
        assert "plan_id" not in args
        if "Transaction" in args["script"]:
            raise harness.AcceptanceError(self.refusal)
        self.reads += 1
        if "time.sleep(" in args["script"]:
            # Execute the fixed read script in a synthetic scope is not needed: the marker
            # supplied to the fake output is independent of its receipt/replay assertions.
            import re
            self.marker = re.search(r"'marker': (\"[^\"]+\")", args["script"])[1].strip('"')
            return {"status": "running", "request_id": "durable-r1"}
        return read_result(elements=5 if self.changed and self.reads > 1 else 4)


def test_default_cli_is_offline_and_does_not_read_token(monkeypatch, capsys):
    monkeypatch.setattr(harness, "read_token", lambda: pytest.fail("Plan read a secret"))
    assert harness.main(["--pid", "123", "--expected-document", "Acceptance scratch", "--expected-guid", GUID]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_RUN"


@pytest.mark.parametrize("ctx", [context(guid="another-guid"), context(title="Another document"),
                                {**context(), "mock": True}, {**context(), "busy": True},
                                {**context(), "addin_supports_context": False},
                                {**context(), "queue": {"depth": 1}}])
def test_bad_preflight_never_submits_script(ctx):
    client = FakeClient(ctx=ctx)
    report = harness.run_checks(client, options())
    assert report["checks"]["preflight_or_transport"]["status"] == "FAIL"
    assert [name for name, _ in client.calls] == ["revit_get_context"]


def test_existing_document_requires_explicit_exact_owner_scope():
    opts = options()
    opts.expected_document = "Heijmans project"
    ctx = context(title=opts.expected_document)
    with pytest.raises(harness.AcceptanceError, match="Default scope"):
        harness.identity(ctx, opts)
    opts.allow_existing_test_document = True
    assert harness.identity(ctx, opts)["title"] == opts.expected_document
    ctx["document"]["guid"] = "different"
    with pytest.raises(harness.AcceptanceError, match="exact expected"):
        harness.identity(ctx, opts)


@pytest.mark.parametrize(("mode", "expected"), [("ask_first", "PASS"), ("auto", "PARTIAL"), ("look_only", "PARTIAL")])
def test_t11_only_proves_no_plan_exemption_in_ask_first(mode, expected):
    report = harness.run_checks(FakeClient(ctx=context(mode=mode)), options())
    assert report["checks"]["runtime"]["status"] == "PASS"
    assert report["checks"]["T11"]["status"] == expected
    assert report["checks"]["T2"]["status"] == "UNSUPPORTED"


@pytest.mark.parametrize("client", [FakeClient(refusal="unrelated network error"), FakeClient(changed=True)])
def test_arbitrary_error_or_changed_counts_cannot_pass_t11(client):
    report = harness.run_checks(client, options())
    assert report["checks"]["T11"]["status"] == "FAIL"


@pytest.mark.parametrize("alter", [{"model_changes_in_read_mode": 1}, {"mode": "write"},
                                 {"success": False}, {"output": "[]"}])
def test_read_runner_requires_real_zero_change_metadata(alter):
    with pytest.raises(harness.AcceptanceError):
        harness.decode_read({**read_result(), **alter}, options())


def test_t1_uses_result_interface_and_does_not_claim_full_acceptance():
    client = FakeClient(duration=True)
    checkpoints = []
    report = harness.run_checks(client, options("--t1-seconds"), checkpoint=checkpoints.append,
                                sleep=lambda _: pytest.fail("Unexpected test sleep"))
    detail = report["checks"]["T1"]["detail"]
    assert detail["ninety_second_result_subcase"] == "PASS"
    assert detail["retained_replay_matches"] is True
    assert report["checks"]["T1"]["status"] == "PARTIAL"
    assert detail["mcp_client_kill"].startswith("NOT_RUN")
    assert checkpoints[0]["run_id"].endswith("-pending")
    fetches = [args for name, args in client.calls if name == "revit_get_result"]
    assert fetches == [{"request_id": "durable-r1", "wait_s": 5}, {"request_id": "durable-r1", "wait_s": 0}]


def test_resume_collects_without_resubmitting_or_queueing_preflight():
    client = FakeClient()
    client.marker = "earlier-marker"
    report = harness.run_checks(client, options("--resume-request-id", "durable-r1", "--expected-marker", client.marker))
    assert [name for name, _ in client.calls] == ["revit_get_result", "revit_get_context", "revit_get_result"]
    assert report["checks"]["T1"]["status"] == "PARTIAL"
    assert report["checks"]["T11"]["status"] == "NOT_RUN"


def test_read_script_pins_pid_and_document_before_and_after_delay():
    script = harness.read_script(options(), seconds=90, marker="receipt-marker")
    assert script.count("assert session_identity() == expected") == 2
    assert "time.sleep(90)" in script and GUID in script
    from revit_mcp_server.security.read_mode import validate_read_script
    validate_read_script(script)
    compile(script, "acceptance-read-script", "exec")


@pytest.mark.parametrize("url", ["https://127.0.0.1:8787", "http://evil.example:8787", "http://127.0.0.1:8787/path",
                               "http://token@127.0.0.1:8787", "http://127.0.0.1:8787?token=x"])
def test_transport_refuses_secret_exfiltration_targets(url):
    with pytest.raises(harness.AcceptanceError):
        harness.PanelClient(url, 123, "s" * 43)


def test_transport_uses_authenticated_panel_instance_schema(monkeypatch):
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        assert request.headers["X-AMB-Token"] == "s" * 43
        return httpx.Response(200, json={"ok": True, "result": {"answer": 1}})

    factory = httpx.Client
    monkeypatch.setattr(harness.httpx, "Client", lambda **kw: factory(transport=httpx.MockTransport(handler), **kw))
    assert harness.PanelClient("http://127.0.0.1:8787", 123, "s" * 43).call("revit_get_context", {}) == {"answer": 1}
    assert captured == [{"tool": "revit_get_context", "arguments": {}, "instance": {"pid": 123}}]


def test_evidence_is_bounded_redacted_exclusive_and_inside_ignored_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    harness.PanelClient("http://127.0.0.1:8787", 123, "s" * 43)
    report = {"run_id": "case-1", "token": "s" * 43, "message": "secret echo " + "s" * 43,
              "path": "C:/secret/project.rvt", "large": "x" * 10000}
    evidence = harness.write_evidence(report, tmp_path / "artifacts" / "acceptance")
    content = evidence.read_text()
    assert "s" * 43 not in content and "C:/secret" not in content and len(content) < 3000
    with pytest.raises(FileExistsError):
        harness.write_evidence(report, evidence.parent)
    with pytest.raises(harness.AcceptanceError):
        harness.write_evidence(report, tmp_path / "tracked")
