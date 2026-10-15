"""
selection_tools module — P8.1 + P8.2 Selection & Model Group Workflows.

Commands:
  set_selection           — Stage element UIDs to be selected (signals Revit plugin).
  save_selection          — Persist a named selection to workspace.
  restore_selection       — Retrieve and stage a previously saved selection.
  select_by_query         — Run DSL filter to compute element UIDs, then stage selection.
  list_saved_selections   — Enumerate all named saved selections.

  group_rename            — Draft ActionPlan to rename a group type.
  group_ungroup           — Draft ActionPlan to ungroup with member count in preview.
  group_convert_to_detail — Draft ActionPlan to convert model group → detail group.

All group write commands produce ActionPlan dicts (not executed here) that must be
approved via the approval provider before forwarding to Revit.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

SELECTIONS_FILE = "saved_selections.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _workspace_dir(workspace: Any) -> Path:
    return workspace.allowed_directories[0]

def _selections_file(workspace: Any) -> Path:
    return _workspace_dir(workspace) / SELECTIONS_FILE

def _load_selections(workspace: Any) -> Dict[str, List[str]]:
    sf = _selections_file(workspace)
    if sf.exists():
        with open(sf, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_selections(selections: Dict[str, List[str]], workspace: Any) -> None:
    sf = _selections_file(workspace)
    with open(sf, "w", encoding="utf-8") as f:
        json.dump(selections, f, indent=2)

def _load_snapshot(snapshot_id: str, workspace: Any) -> Dict[str, Any]:
    path = _workspace_dir(workspace) / "snapshots" / f"{snapshot_id}.json"
    if not path.exists():
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _match_element(el: Dict[str, Any], filter_dsl: Dict[str, Any]) -> bool:
    for key, val in filter_dsl.items():
        if key == "category":
            cats = val if isinstance(val, list) else [val]
            if el.get("category") not in cats:
                return False
        elif key == "family" and el.get("family") != val:
            return False
        elif key == "type_name" and el.get("type_name") != val:
            return False
        elif key == "level_uid" and el.get("level_uid") != val:
            return False
        elif key == "workset" and el.get("workset") != val:
            return False
        elif key == "group_uid" and el.get("group_uid") != val:
            return False
        elif key == "placed":
            is_placed = el.get("level_uid") is not None or el.get("location") is not None
            if val and not is_placed:
                return False
            elif not val and is_placed:
                return False
        elif key == "parameter":
            pname = val.get("name")
            params = el.get("params", {})
            param = params.get(pname) if params else None
            if val.get("empty") is True:
                if param is not None and param.get("v") not in (None, ""):
                    return False
            elif "value" in val:
                if param is None or str(param.get("v")) != str(val["value"]):
                    return False
    return True

def _make_action_plan(tool_name: str, args: Dict[str, Any], preview: Dict[str, Any]) -> Dict[str, Any]:
    """Return a lightweight ActionPlan dict stub for gated writes."""
    return {
        "plan_type": "action_plan_draft",
        "tool": tool_name,
        "arguments": args,
        "preview": preview,
        "requires_approval": True,
    }


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

class SelectionToolsModule:

    def set_selection(self, element_uids: List[str], workspace: Any = None, **_) -> Dict[str, Any]:
        """Stage element UIDs to be selected. The dockable panel / bridge picks this up."""
        # Write pending selection to workspace for the plugin to pick up
        pending_path = _workspace_dir(workspace) / "pending_selection.json"
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump({"element_uids": element_uids}, f, indent=2)
        return {
            "status": "staged",
            "element_count": len(element_uids),
            "pending_file": str(pending_path),
        }

    def save_selection(self, selection_name: str, element_uids: List[str], workspace: Any = None, **_) -> Dict[str, Any]:
        selections = _load_selections(workspace)
        selections[selection_name] = element_uids
        _save_selections(selections, workspace)
        return {"status": "saved", "selection_name": selection_name, "count": len(element_uids)}

    def restore_selection(self, selection_name: str, workspace: Any = None, **_) -> Dict[str, Any]:
        selections = _load_selections(workspace)
        if selection_name not in selections:
            raise ValueError(f"No saved selection named '{selection_name}'.")
        element_uids = selections[selection_name]
        # Stage it as pending
        return self.set_selection(element_uids=element_uids, workspace=workspace)

    def select_by_query(self, filter: Dict[str, Any], snapshot_id: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        is_mock = False
        if not snapshot_id:
            from revit_mcp_server.semantic.engine import generate_mock_snapshot, require_snapshot_or_mock
            require_snapshot_or_mock(snapshot_id, "selection_tools")
            is_mock = True
            snap = generate_mock_snapshot()
            elements = [el.model_dump(by_alias=True) for el in snap.elements]
        else:
            data = _load_snapshot(snapshot_id, workspace)
            elements = data.get("elements", [])

        matched_uids = [el["uid"] for el in elements if _match_element(el, filter)]
        result = self.set_selection(element_uids=matched_uids, workspace=workspace)
        if is_mock:
            result["data_source"] = "mock"
        return result

    def list_saved_selections(self, workspace: Any = None, **_) -> Dict[str, Any]:
        selections = _load_selections(workspace)
        return {
            "count": len(selections),
            "selections": [{"name": k, "element_count": len(v)} for k, v in selections.items()],
        }

    def group_rename(self, group_uid: str, new_name: str, snapshot_id: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        # Look up group info from snapshot
        group_info = self._find_group(group_uid, snapshot_id, workspace)
        preview = {
            "group_uid": group_uid,
            "current_name": group_info.get("current_name", "<unknown>"),
            "new_name": new_name,
            "instance_count": group_info.get("instance_count", 0),
            "description": f"Rename group type to '{new_name}'. Affects {group_info.get('instance_count', 0)} instance(s).",
        }
        return _make_action_plan(
            "group_rename",
            {"group_uid": group_uid, "new_name": new_name},
            preview
        )

    def group_ungroup(self, group_uid: str, snapshot_id: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        group_info = self._find_group(group_uid, snapshot_id, workspace)
        member_count = group_info.get("member_count", 0)
        preview = {
            "group_uid": group_uid,
            "member_count": member_count,
            "description": (
                f"Ungroup will dissolve {member_count} member(s) into individual elements. "
                "This is destructive and requires a rollback plan."
            ),
            "unsupported_cases": ["nested groups", "mirrored instances", "view-specific groups"],
        }
        return _make_action_plan(
            "group_ungroup",
            {"group_uid": group_uid},
            preview
        )

    def group_convert_to_detail(self, group_uid: str, snapshot_id: str = "", workspace: Any = None, **_) -> Dict[str, Any]:
        group_info = self._find_group(group_uid, snapshot_id, workspace)
        preview = {
            "group_uid": group_uid,
            "current_name": group_info.get("current_name", "<unknown>"),
            "description": "Convert model group to detail group. Members become annotation/detail elements.",
        }
        return _make_action_plan(
            "group_convert_to_detail",
            {"group_uid": group_uid},
            preview
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _find_group(self, group_uid: str, snapshot_id: str, workspace: Any) -> Dict[str, Any]:
        is_mock = False
        if not snapshot_id:
            from revit_mcp_server.semantic.engine import generate_mock_snapshot, require_snapshot_or_mock
            require_snapshot_or_mock(snapshot_id, "selection_tools")
            is_mock = True
            snap = generate_mock_snapshot()
            elements = [el.model_dump(by_alias=True) for el in snap.elements]
        else:
            data = _load_snapshot(snapshot_id, workspace)
            elements = data.get("elements", [])

        # Count instances (elements that are groups OR members of this group)
        group_el = next((el for el in elements if el.get("uid") == group_uid), None)
        member_elements = [el for el in elements if el.get("group_uid") == group_uid]

        return {
            "current_name": group_el.get("type_name") if group_el else "<unknown>",
            "member_count": len(member_elements),
            "instance_count": 1,  # Without a real Revit connection, assume 1 visible instance
            **({"data_source": "mock"} if is_mock else {}),
        }
