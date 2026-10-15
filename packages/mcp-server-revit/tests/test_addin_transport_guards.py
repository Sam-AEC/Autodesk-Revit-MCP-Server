"""Static guards on the add-in's durable-result transport, context command and image export.

Nothing here runs against a live Revit (the pure logic has C# tests in packages/revit-bridge-addin-tests).
These read the source and fail on the patterns that would bring back a lost result, a wrong image path or a mutating context command.
"""
import re
from pathlib import Path

ADDIN_SRC = Path(__file__).resolve().parents[3] / "packages" / "revit-bridge-addin" / "src"
BRIDGE = ADDIN_SRC / "Bridge"


def _read(name: str) -> str:
    return (BRIDGE / name).read_text(encoding="utf-8")


def _body(source: str, signature_re: str) -> str:
    match = re.search(signature_re, source)
    assert match, f"method not found: {signature_re}"
    start = source.index("{", match.end())
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError("unbalanced braces")


# --- 0.1 durable results ----------------------------------------------------------------------------

def test_waiting_never_drops_the_pending_entry():
    source = _read("CommandQueue.cs")
    wait = _body(source, r"public async Task<RequestSnapshot\?> WaitForResponse\(")
    assert "Remove" not in wait, "a timed-out wait must leave the request, and later its result, in place"
    assert "timed out after" not in source, "a timeout is a state now, not an error response"


def test_finished_results_are_kept_for_a_ttl_and_bounded():
    source = _read("CommandQueue.cs")
    assert "AEC_BRIDGE_RESULT_TTL_SECONDS" in source and "900" in source, "default TTL is 15 minutes"
    assert "MaxFinishedEntries" in source and "MaxFinishedBytes" in source, "memory must be bounded"
    sweep = _body(source, r"private void Sweep\(DateTime now\)")
    assert "ResultTtl" in sweep and "MaxFinishedEntries" in sweep and "MaxFinishedBytes" in sweep


def test_complete_stores_the_response_and_marks_done_or_failed():
    complete = _body(_read("CommandQueue.cs"), r"public void Complete\(string requestId, CommandResponse response\)")
    assert "JsonSerializer.Serialize(response)" in complete, "serialize once, while the result is still valid"
    assert '"done"' in complete and '"failed"' in complete
    assert "ResponseJson = json" in complete


def test_resubmitting_a_finished_request_id_does_not_run_it_again():
    enqueue = _body(_read("CommandQueue.cs"), r"public void Enqueue\(CommandRequest request\)")
    assert "IsFinished) return;" in enqueue
    assert enqueue.index("IsFinished) return;") < enqueue.index("_queue.Enqueue(request)")
    assert "_inflight.TryAdd" in enqueue


def test_executor_marks_a_request_running_before_it_starts():
    run_one = _body(_read("ExternalEventHandler.cs"), r"private void RunOne\(UIApplication app, CommandRequest request\)")
    assert run_one.index("MarkRunning(") < run_one.index("BridgeCommandFactory.Execute(")


def test_server_has_a_result_endpoint_and_a_soft_wait():
    source = _read("BridgeServer.cs")
    assert '"/result/"' in source and 'HttpMethod == "GET"' in source
    result = _body(source, r"private Task HandleResult\(")
    assert "404" in result and "GetSnapshot(" in result and '\\"state\\"' in result
    execute = _body(source, r"private async Task HandleExecute\(")
    assert "wait_ms" in execute and 'status = "running"' in execute and "request_id = requestId" in execute
    assert "SoftWaitMs" in source and "AEC_BRIDGE_SOFT_WAIT_MS" in source


def test_result_endpoint_is_behind_the_session_token():
    handle = _body(_read("BridgeServer.cs"), r"private async Task HandleRequest\(")
    assert handle.index("Unauthorized") < handle.index('"/result/"')


# --- 0.4 context ------------------------------------------------------------------------------------

def test_get_context_is_a_read_only_bridge_command_with_the_promised_fields():
    source = _read("ContextCommands.cs")
    assert re.search(r'\[BridgeCommand\("revit\.get_context", IsMutating = false\)\]', source)
    body = _body(source, r"private static object ExecuteGetContext\(UIApplication app\)")
    for field in ("ProductInfo.BuildInfo", "VersionNumber", "doc.Title", "doc.PathName", "CreationGUID",
                  "ActiveView", "IsWorkshared", "queue"):
        assert field in body, field
    assert "Transaction" not in body and "SubTransaction" not in body, "context must not touch the model"


def test_factory_is_partial_so_the_command_can_live_in_its_own_file():
    assert re.search(r"public static partial class BridgeCommandFactory", _read("BridgeCommandFactory.cs"))
    assert re.search(r"public static partial class BridgeCommandFactory", _read("ContextCommands.cs"))


def test_health_reports_queue_and_build_without_waiting_for_revit():
    health = _body(_read("BridgeServer.cs"), r"private Task HandleHealth\(")
    for field in ("queue_depth", "running", "build = ProductInfo.BuildInfo"):
        assert field in health, field


def test_build_info_identifies_the_loaded_assembly():
    source = (ADDIN_SRC / "ProductInfo.cs").read_text(encoding="utf-8")
    body = _body(source, r"public static object BuildInfo")
    assert "ModuleVersionId" in body and "AssemblyInformationalVersionAttribute" in body


# --- 0.5 image export -------------------------------------------------------------------------------

def test_export_image_reports_the_true_file_path_size_and_existence():
    source = _read("BridgeCommandFactory.cs")
    body = _body(source, r"private static object ExecuteExportImage\(")
    assert "SanitizeFileName(view.Name)" not in body, "the file name must come from what Revit wrote, not a guess"
    assert "EnumerateFiles(outputDirectory" in body, "look at the folder after the export"
    for key in ("file_path =", "file_size_bytes =", "file_exists ="):
        assert key in body, key
    assert "file.Length > 0" in body, "an empty file is not an export"
    assert re.search(r'status = exportSucceeded \? "success" : "error"', body)
    assert "FirstOrDefault()?.Length" in body, "file_size_bytes belongs to file_path, not the sum of several files"
