"""Bounded inspection composes only dedicated reads on the selected bridge."""
import asyncio

import pytest

from revit_mcp_server.config import BridgeMode
from revit_mcp_server.errors import BridgeError
from revit_mcp_server.providers.revit import RevitProvider
from revit_mcp_server.security.approval import ApprovalGate
from revit_mcp_server.security.dispatch import run_gated_tool
from revit_mcp_server.security.workspace import WorkspaceMonitor
from revit_mcp_server.tool_metadata import enrich_tool


class InspectionBridge:
    def __init__(self, failures=None, documents=None):
        self.calls = []
        self.failures = failures or {}
        self.documents = list(documents or [{"title": "Villa", "path": "C:/models/Villa.rvt"}])

    def send_tool(self, name, payload):
        self.calls.append((name, payload))
        key = (name, payload.get("element_id"), payload.get("parameter_name"))
        if key in self.failures:
            failure = self.failures[key]
            if isinstance(failure, Exception):
                raise failure
            return failure
        if name == "revit.get_document_info":
            return self.documents.pop(0) if len(self.documents) > 1 else self.documents[0]
        if name == "revit.get_element_geometry":
            return {"success": True, "element_id": payload["element_id"], "length": 10.0,
                    "point": {"x": 1.0, "y": 2.0, "z": 3.0}, "bounding_box": None,
                    "area": 50.0, "volume": 5.0}
        if name == "revit.get_parameter_value":
            return {**payload, "value": "3048 mm", "storage_type": "Double"}
        raise AssertionError(f"Unexpected command {name}")


def provider(tmp_path, bridge=None, factory=None):
    bridge = bridge or InspectionBridge()
    result = RevitProvider(
        workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.bridge,
        bridge_url="http://127.0.0.1:1", bridge_factory=factory or (lambda *args: bridge),
    )
    return result, bridge


def inspect(prov, **args):
    return asyncio.run(prov.execute_tool("revit_inspect_elements", args))


def test_success_preserves_geometry_units_host_values_and_order(tmp_path):
    prov, bridge = provider(tmp_path)
    result = inspect(prov, element_ids=[20, 10], parameter_names=["Length", "Mark"],
                     expected_document_title="Villa")
    assert result["success"] is True
    assert result["completeness"] == {
        "complete": True, "requested_elements": 2, "successful_elements": 2,
        "requested_sections": 6, "successful_sections": 6,
        "failed_sections": 0, "skipped_sections": 0, "document_verified_at_endpoints": True,
    }
    assert [entry["element_id"] for entry in result["elements"]] == [20, 10]
    assert result["elements"][0]["geometry"]["data"]["length"] == 10.0
    assert result["elements"][0]["geometry"]["data"]["bounding_box"] is None
    assert result["elements"][0]["parameters"][0]["data"]["value"] == "3048 mm"
    assert result["units"]["geometry_length"] == "ft"
    assert result["units"]["geometry_area"] == "ft^2"
    assert result["units"]["geometry_volume"] == "ft^3"
    assert bridge.calls == [
        ("revit.get_document_info", {}),
        ("revit.get_element_geometry", {"element_id": 20}),
        ("revit.get_parameter_value", {"element_id": 20, "parameter_name": "Length"}),
        ("revit.get_parameter_value", {"element_id": 20, "parameter_name": "Mark"}),
        ("revit.get_element_geometry", {"element_id": 10}),
        ("revit.get_parameter_value", {"element_id": 10, "parameter_name": "Length"}),
        ("revit.get_parameter_value", {"element_id": 10, "parameter_name": "Mark"}),
        ("revit.get_document_info", {}),
    ]
    assert "not an atomic snapshot" in result["limitations"][0]


def test_geometry_only_does_not_collect_all_parameters(tmp_path):
    prov, bridge = provider(tmp_path)
    result = inspect(prov, element_ids=[1])
    assert result["elements"][0]["parameters"] == []
    assert [name for name, _ in bridge.calls] == [
        "revit.get_document_info", "revit.get_element_geometry", "revit.get_document_info",
    ]


def test_host_failures_and_bridge_exceptions_do_not_hide_successful_sections(tmp_path):
    bridge = InspectionBridge(failures={
        ("revit.get_element_geometry", 1, None): {
            "success": False, "error": "Element 1 not found", "error_code": "ELEMENT_NOT_FOUND",
        },
        ("revit.get_parameter_value", 1, "Mark"): BridgeError("Parameter missing"),
        ("revit.get_parameter_value", 2, "Mark"): {"element_id": 999, "parameter_name": "Mark", "value": "wrong"},
    })
    prov, _ = provider(tmp_path, bridge)
    result = inspect(prov, element_ids=[1, 2, 3], parameter_names=["Mark"])
    assert result["success"] is False
    assert result["completeness"]["successful_sections"] == 3
    assert result["completeness"]["failed_sections"] == 3
    assert result["completeness"]["successful_elements"] == 1
    first = result["elements"][0]
    assert first["geometry"]["error"]["code"] == "ELEMENT_NOT_FOUND"
    assert first["geometry"]["data"]["success"] is False
    assert first["parameters"][0]["exception_type"] == "BridgeError"
    assert result["elements"][1]["parameters"][0]["error"]["code"] == "ELEMENT_ID_MISMATCH"
    assert result["elements"][2]["success"] is True


@pytest.mark.parametrize("arguments", [
    {}, {"element_ids": []}, {"element_ids": [1] * 51},
    {"element_ids": [0]}, {"element_ids": [-1]}, {"element_ids": [True]},
    {"element_ids": [1.0]}, {"element_ids": ["1"]}, {"element_ids": [None]},
    {"element_ids": [2**31]}, {"element_ids": [1, 1]}, {"element_ids": (1,)},
    {"element_ids": [1], "parameter_names": "Mark"},
    {"element_ids": [1], "parameter_names": None},
    {"element_ids": [1], "parameter_names": ["Mark", "Mark"]},
    {"element_ids": [1], "parameter_names": [""]},
    {"element_ids": [1], "parameter_names": ["  \t"]},
    {"element_ids": [1], "parameter_names": [1]},
    {"element_ids": [1], "parameter_names": ["a" * 261]},
    {"element_ids": [1], "parameter_names": [str(i) for i in range(21)]},
    {"element_ids": list(range(1, 51)), "parameter_names": ["a", "b", "c", "d"]},
    {"element_ids": [1], "expected_document_title": " "},
    {"element_ids": [1], "expected_document_title": None},
    {"element_ids": [1], "expected_document_title": "a" * 261},
    {"element_ids": [1], "script": "print(doc.Title)"},
    {"element_ids": [1], "payload": {}},
])
def test_invalid_inputs_never_reach_bridge(tmp_path, arguments):
    prov, bridge = provider(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(prov.execute_tool("revit_inspect_elements", arguments))
    assert bridge.calls == []


def test_largest_permitted_batch_remains_bounded(tmp_path):
    prov, bridge = provider(tmp_path)
    result = inspect(prov, element_ids=list(range(1, 51)), parameter_names=["a", "b", "c"])
    assert result["completeness"]["requested_sections"] == 200
    assert len(bridge.calls) == 202


@pytest.mark.parametrize("document,code", [
    ({"title": "Other", "path": "C:/models/Other.rvt"}, "DOCUMENT_TITLE_MISMATCH"),
    ({"path": "C:/models/Villa.rvt"}, "DOCUMENT_UNVERIFIED"),
    ({"title": "Villa"}, "DOCUMENT_UNVERIFIED"),
])
def test_initial_document_guard_skips_all_element_reads(tmp_path, document, code):
    prov, bridge = provider(tmp_path, InspectionBridge(documents=[document]))
    result = inspect(prov, element_ids=[1, 2], parameter_names=["Mark"], expected_document_title="Villa")
    assert bridge.calls == [("revit.get_document_info", {})]
    assert result["document"]["guard_error"] == code
    assert result["completeness"]["skipped_sections"] == 4
    assert result["completeness"]["complete"] is False
    assert all(entry["geometry"]["status"] == "skipped" for entry in result["elements"])


def test_document_switch_makes_batch_incomplete_even_when_all_sections_succeed(tmp_path):
    docs = [{"title": "Villa", "path": "C:/models/Villa.rvt"},
            {"title": "Villa", "path": "C:/other/Villa.rvt"}]
    prov, _ = provider(tmp_path, InspectionBridge(documents=docs))
    result = inspect(prov, element_ids=[1])
    assert result["elements"][0]["success"] is True
    assert result["completeness"]["successful_sections"] == 1
    assert result["document"]["unchanged_at_endpoints"] is False
    assert result["success"] is False


def test_failed_final_document_read_preserves_sections_but_fails_completeness(tmp_path):
    class FinalDocumentFailure(InspectionBridge):
        def send_tool(self, name, payload):
            if name == "revit.get_document_info" and self.calls:
                self.calls.append((name, payload))
                raise BridgeError("Document was closed")
            return super().send_tool(name, payload)

    prov, _ = provider(tmp_path, FinalDocumentFailure())
    result = inspect(prov, element_ids=[1])
    assert result["elements"][0]["success"] is True
    assert result["document"]["after"]["error"]["message"] == "Document was closed"
    assert result["completeness"]["document_verified_at_endpoints"] is False
    assert result["completeness"]["complete"] is False


@pytest.mark.parametrize("bad_result", [None, [], {}, {"ok": False, "message": "Unavailable"}])
def test_invalid_or_failed_dedicated_geometry_response_is_an_error(tmp_path, bad_result):
    prov, _ = provider(tmp_path, InspectionBridge(failures={
        ("revit.get_element_geometry", 1, None): bad_result,
    }))
    result = inspect(prov, element_ids=[1])
    assert result["elements"][0]["geometry"]["success"] is False
    assert result["completeness"]["failed_sections"] == 1
    assert result["completeness"]["complete"] is False


def test_parameter_response_without_value_is_not_a_success(tmp_path):
    prov, _ = provider(tmp_path, InspectionBridge(failures={
        ("revit.get_parameter_value", 1, "Mark"): {"element_id": 1, "parameter_name": "Mark"},
    }))
    result = inspect(prov, element_ids=[1], parameter_names=["Mark"])
    assert result["elements"][0]["geometry"]["success"] is True
    assert result["elements"][0]["parameters"][0]["error"]["code"] == "INVALID_PARAMETER_RESULT"


def test_routed_bridge_used_for_every_read_and_default_restored(tmp_path):
    default, routed = InspectionBridge(), InspectionBridge()
    created = []

    def factory(endpoint, token):
        created.append((endpoint, token))
        return routed if endpoint.endswith(":2") else default

    prov, _ = provider(tmp_path, factory=factory)
    with prov.routed_to("http://127.0.0.1:2", "routed-token"):
        result = inspect(prov, element_ids=[1], parameter_names=["Mark"])
    assert result["success"] is True
    assert default.calls == []
    assert len(routed.calls) == 4
    inspect(prov, element_ids=[2])
    assert len(default.calls) == 3
    assert len(routed.calls) == 4
    assert created[-1] == ("http://127.0.0.1:2", "routed-token")


def test_live_connection_required_instead_of_mock_audit_claims(tmp_path):
    prov = RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.mock)
    with pytest.raises(ValueError, match="live Revit"):
        inspect(prov, element_ids=[1])


def test_schema_annotations_and_look_only_gate(tmp_path):
    prov, bridge = provider(tmp_path)
    tool = next(t for t in prov.get_capabilities() if t.name == "revit_inspect_elements")
    offered = enrich_tool("revit", tool)
    assert not tool.is_mutating and not tool.destructive
    assert offered.annotations.readOnlyHint is True
    assert offered.annotations.destructiveHint is False
    assert offered.annotations.openWorldHint is False
    assert "plan_id" not in offered.inputSchema["properties"]
    assert offered.inputSchema["additionalProperties"] is False
    assert offered.inputSchema["properties"]["element_ids"]["maxItems"] == 50
    assert offered.inputSchema["properties"]["parameter_names"]["maxItems"] == 20
    assert offered.inputSchema["properties"]["element_ids"]["items"]["minimum"] == 1

    class Registry:
        def lookup_tool_provider(self, name):
            return prov if name == tool.name else None

        def lookup_tool(self, name):
            return tool if name == tool.name else None

    gate = ApprovalGate(tmp_path / "ws", "look_only")
    result = asyncio.run(run_gated_tool(Registry(), gate, tool.name, {"element_ids": [1]}))
    assert result["success"] is True
    assert {name for name, _ in bridge.calls} == {"revit.get_document_info", "revit.get_element_geometry"}


def test_python_description_does_not_imply_reads_bypass_approval(tmp_path):
    prov, _ = provider(tmp_path)
    tool = next(t for t in prov.get_capabilities() if t.name == "revit_execute_python")
    assert "including read-only scripts" in tool.description
    assert "requires an approved plan" in tool.description
    assert "Reading the model needs no setup" not in tool.description
