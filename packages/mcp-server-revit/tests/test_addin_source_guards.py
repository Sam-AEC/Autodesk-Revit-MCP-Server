"""Static guards on the C# add-in source.

There is no C# test project yet and CI only compiles the add-in, so a method that calls
itself still builds. These checks read the source text and fail on known-fatal patterns.
"""
import re
from pathlib import Path

ADDIN_SRC = Path(__file__).resolve().parents[3] / "packages" / "revit-bridge-addin" / "src"
FACTORY = ADDIN_SRC / "Bridge" / "BridgeCommandFactory.cs"


def _method_body(source: str, signature_re: str) -> str:
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


def test_create_transaction_builds_a_real_transaction_and_does_not_call_itself():
    body = _method_body(
        FACTORY.read_text(encoding="utf-8"),
        r"public static BridgeTransaction CreateTransaction\(Document doc, string name\)",
    )
    assert "BridgeCommandFactory.CreateTransaction(" not in body, "CreateTransaction calls itself"
    assert "CreateTransaction(" not in body, "CreateTransaction calls itself"
    assert "new BridgeTransaction(" in body, "CreateTransaction must construct the checked BridgeTransaction"
    wrapper = (ADDIN_SRC / "Bridge" / "BridgeTransaction.cs").read_text(encoding="utf-8")
    assert "new Transaction(" in wrapper, "BridgeTransaction must construct the Revit Transaction"


def test_add_in_constructs_transactions_somewhere():
    hits = [p for p in ADDIN_SRC.rglob("*.cs") if "new Transaction(" in p.read_text(encoding="utf-8")]
    assert hits, "no 'new Transaction(' in the add-in: every model write would fail"


# --- Revit must never be held by one long request (the 2026-10-13 freeze) -------------------------

def test_executor_runs_one_request_per_revit_turn_and_skips_abandoned_ones():
    source = (ADDIN_SRC / "Bridge" / "ExternalEventHandler.cs").read_text(encoding="utf-8")
    execute = _method_body(source, r"public void Execute\(UIApplication app\)")
    assert "IsWanted(" in execute, "abandoned requests must be dropped before they start"
    assert re.search(r"RunOne\(app, request\);\s*break;", execute), "only one request may run per Execute"
    assert "Event?.Raise()" in execute, "remaining requests need another Revit turn, not the same one"


def test_queue_does_not_enqueue_a_retried_request_id_twice():
    source = (ADDIN_SRC / "Bridge" / "CommandQueue.cs").read_text(encoding="utf-8")
    enqueue = _method_body(source, r"public void Enqueue\(CommandRequest request\)")
    assert "_inflight.TryAdd" in enqueue and "return;" in enqueue


def test_snapshot_is_bounded_by_count_and_time_and_skips_geometry_computed_values():
    body = _method_body(FACTORY.read_text(encoding="utf-8"), r"private static object ExecuteExtractSnapshot\(")
    assert "ElapsedMilliseconds > budgetMs" in body and "maxElements" in body
    assert "truncated" in body
    assert "IsHeavySnapshotParameter" in body
    assert "ToElementIds()" in body, "collect ids first; do not materialise every element up front"


def test_snapshot_records_carry_host_uid_for_the_hosting_rules():
    """door_no_host / window_no_host test host_uid; leaving it out flagged every hosted door."""
    body = _method_body(FACTORY.read_text(encoding="utf-8"), r"private static object ExecuteExtractSnapshot\(")
    assert re.search(r"host_uid\s*=\s*\(elem as FamilyInstance\)\?\.Host\?\.UniqueId", body)


def test_hub_is_never_launched_from_the_bundled_python_folder():
    """From that folder the panel chat's MCP server failed to start (python311.dll conflict) and the chat had no tools."""
    source = (ADDIN_SRC / "Bridge" / "PanelHubLauncher.cs").read_text(encoding="utf-8")
    assert "GetDirectoryName(interpreter)" not in source
    assert "startInfo.WorkingDirectory = workspace" in source


# --- door/window fit checks and the clash budget (B-13, B-04) ------------------------------------

def _factory_text() -> str:
    return FACTORY.read_text(encoding="utf-8")


def test_place_door_and_window_share_the_checked_opening_helper():
    source = _factory_text()
    for command, category in (("revit.place_door", "OST_Doors"), ("revit.place_window", "OST_Windows")):
        match = re.search(r'\[BridgeCommand\("' + re.escape(command) + r'"[^\]]*\]\s*private static object \w+\([^)]*\)\s*=>([^;]*);', source)
        assert match, f"{command} must delegate to the shared helper"
        assert "PlaceHostedOpening(" in match.group(1) and category in match.group(1)


def test_opening_placement_refuses_before_the_transaction_and_verifies_the_host():
    source = _factory_text()
    body = _method_body(source, r"private static object PlaceHostedOpening\(")
    assert body.index("CheckOpeningFit(") < body.index("CreateTransaction("), "fit check must run before any transaction"
    assert body.index("ResolveOpeningSymbol(") < body.index("CreateTransaction(")
    assert body.count("CreateTransaction(") == 1, "one transaction per call"
    assert "CommitChecked()" in body
    assert body.count("VerifyOpeningHost(") == 2, "host verified before and after commit"
    assert "host_wall_id" in body and "volume_delta_m3" in body
    assert "hand_flipped" in body and "facing_flipped" in body
    assert "flipHand()" in body and "flipFacing()" in body


def test_opening_fit_check_names_the_wall_and_reads_width_height_parameters():
    source = _factory_text()
    body = _method_body(source, r"private static object CheckOpeningFit\(")
    assert "wallId" in body and "does not fit" in body
    for builtin in ("DOOR_WIDTH", "DOOR_HEIGHT", "WINDOW_WIDTH", "WINDOW_HEIGHT"):
        assert builtin in body
    assert "throw new ArgumentException" in body


def test_opening_symbol_defaults_are_not_hard_coded_names():
    source = _factory_text()
    for stale in ('"Single-Flush"', '"0915 x 2134mm"', '"1200 x 1500mm"'):
        assert stale not in source, f"{stale} does not exist in most projects; pick the first loaded symbol"
    body = _method_body(source, r"private static FamilySymbol ResolveOpeningSymbol\(")
    assert "first_available" in body
    assert "throw new InvalidOperationException" in body, "must fail loudly when no symbol is loaded"


def test_check_clashes_has_a_budget_and_does_not_look_names_up_in_the_pair_loop():
    source = _factory_text()
    body = _method_body(source, r"private static object ExecuteCheckClashes\(")
    for token in ("max_pairs", "time_budget_s", "truncated", "pairs_examined", "Stopwatch"):
        assert token in body, token
    loop_start = body.index("foreach (var a in list1)")
    loop = body[loop_start:]
    assert "get_BoundingBox" not in loop, "bounding boxes must be cached outside the pair loop"
    assert ".Name" not in loop.replace("d1.Name", "").replace("d2.Name", ""), "Name lookups must go through the cache"
    assert "WhereElementIsNotElementType" in source[source.index("CollectClashCandidates(Document"):]
