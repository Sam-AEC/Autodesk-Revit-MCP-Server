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
        r"public static Transaction CreateTransaction\(Document doc, string name\)",
    )
    assert "BridgeCommandFactory.CreateTransaction(" not in body, "CreateTransaction calls itself"
    assert "CreateTransaction(" not in body, "CreateTransaction calls itself"
    assert "new Transaction(" in body, "CreateTransaction must construct the Revit Transaction"


def test_add_in_constructs_transactions_somewhere():
    hits = [p for p in ADDIN_SRC.rglob("*.cs") if "new Transaction(" in p.read_text(encoding="utf-8")]
    assert hits, "no 'new Transaction(' in the add-in: every model write would fail"
