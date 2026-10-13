"""Bounded orchestration of existing dedicated Revit reads, never executable code."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

MAX_ELEMENTS = 50
MAX_PARAMETERS = 20
MAX_SECTIONS = 200
MAX_ELEMENT_ID = 2**31 - 1  # get_parameter_value currently uses GetInt32.
MAX_NAME_LENGTH = 260

INSPECTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "element_ids": {
            "type": "array", "minItems": 1, "maxItems": MAX_ELEMENTS, "uniqueItems": True,
            "items": {"type": "integer", "minimum": 1, "maximum": MAX_ELEMENT_ID},
            "description": "Explicit positive element IDs in the active document, up to 50 unique IDs.",
        },
        "parameter_names": {
            "type": "array", "maxItems": MAX_PARAMETERS, "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": MAX_NAME_LENGTH, "pattern": r"\S"},
            "description": "Up to 20 exact parameter names; omitted or empty means geometry only. IDs times (1 + names) must be at most 200.",
        },
        "expected_document_title": {
            "type": "string", "minLength": 1, "maxLength": MAX_NAME_LENGTH, "pattern": r"\S",
            "description": "Optional exact active-document title guard; a mismatch skips all element reads.",
        },
    },
    "required": ["element_ids"],
}


def validate_inspection(arguments: dict[str, Any]) -> tuple[list[int], list[str], str | None]:
    """Validate independently of the MCP schema: panel and internal callers use this too."""
    if not isinstance(arguments, dict) or set(arguments) - set(INSPECTION_SCHEMA["properties"]):
        raise ValueError("revit_inspect_elements accepts only element_ids, parameter_names and expected_document_title")
    ids = arguments.get("element_ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_ELEMENTS:
        raise ValueError("element_ids must be a list of 1 to 50 unique positive integers")
    if any(type(value) is not int or not 1 <= value <= MAX_ELEMENT_ID for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("element_ids must be unique positive integers no greater than 2147483647")
    names = arguments.get("parameter_names", [])
    if not isinstance(names, list) or len(names) > MAX_PARAMETERS:
        raise ValueError("parameter_names must be a list of at most 20 unique names")
    if any(not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME_LENGTH for name in names):
        raise ValueError("parameter_names must contain nonblank strings of at most 260 characters")
    if len(set(names)) != len(names):
        raise ValueError("parameter_names must be unique")
    expected = arguments.get("expected_document_title")
    if "expected_document_title" in arguments and (
        not isinstance(expected, str) or not expected.strip() or len(expected) > MAX_NAME_LENGTH
    ):
        raise ValueError("expected_document_title must be a nonblank string of at most 260 characters")
    if len(ids) * (1 + len(names)) > MAX_SECTIONS:
        raise ValueError("At most 200 geometry/parameter sections may be requested; split this inspection into smaller batches")
    return list(ids), list(names), expected


def _error(message: str, code: str, **details: Any) -> dict[str, Any]:
    return {"success": False, "status": "error", "error": {"code": code, "message": message}, **details}


async def _read(
    execute: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
    tool: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = await execute(tool, arguments)
    except Exception as exc:
        return _error(str(exc), "READ_FAILED", exception_type=type(exc).__name__)
    if not isinstance(result, dict) or not result:
        return _error("Dedicated read returned no structured result", "INVALID_READ_RESULT")
    if result.get("success") is False or result.get("ok") is False or result.get("error") or result.get("status") == "error":
        return _error(str(result.get("error") or result.get("message") or "Dedicated read failed"),
                      str(result.get("error_code") or "READ_FAILED"), data=result)
    if "element_id" in arguments and result.get("element_id") != arguments["element_id"]:
        return _error("Dedicated read did not return the requested element ID", "ELEMENT_ID_MISMATCH", data=result)
    if "parameter_name" in arguments and (
        result.get("parameter_name") != arguments["parameter_name"] or "value" not in result
    ):
        return _error("Dedicated read did not return the requested parameter value", "INVALID_PARAMETER_RESULT", data=result)
    return {"success": True, "status": "success", "data": result}


async def _document(execute: Callable[..., Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    result = await _read(execute, "revit_get_document_info", {})
    if result["success"]:
        data = result["data"]
        if not isinstance(data.get("title"), str) or not data["title"].strip() or not isinstance(data.get("path"), str):
            return _error("Document read did not return a title and path", "DOCUMENT_UNVERIFIED")
        # Return only the identity needed for this inspection, rather than all project metadata.
        result["data"] = {key: data[key] for key in ("title", "path", "is_family", "is_workshared") if key in data}
    return result


async def inspect_elements(
    execute: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    ids, names, expected = validate_inspection(arguments)
    before = await _document(execute)
    guard_error = None
    if not before["success"]:
        guard_error = "DOCUMENT_UNVERIFIED"
    elif expected is not None and before["data"]["title"] != expected:
        guard_error = "DOCUMENT_TITLE_MISMATCH"

    elements = []
    for element_id in ids:
        if guard_error:
            skipped = {"success": False, "status": "skipped", "error": {
                "code": guard_error, "message": "Element read skipped because the initial document guard failed",
            }}
            geometry = dict(skipped)
            parameters = [{"parameter_name": name, **skipped} for name in names]
        else:
            # Await every read in order. No concurrent Revit user-interface requests.
            geometry = await _read(execute, "revit_get_element_geometry", {"element_id": element_id})
            parameters = []
            for name in names:
                value = await _read(execute, "revit_get_parameter_value", {
                    "element_id": element_id, "parameter_name": name,
                })
                parameters.append({"parameter_name": name, **value})
        sections = [geometry, *parameters]
        elements.append({
            "element_id": element_id,
            "success": all(section["success"] for section in sections),
            "geometry": geometry,
            "parameters": parameters,
        })

    after = await _document(execute) if not guard_error else {
        "success": False, "status": "skipped", "reason": "Initial document guard failed",
    }
    unchanged = bool(before["success"] and after["success"] and before["data"] == after["data"])
    sections = [section for element in elements for section in [element["geometry"], *element["parameters"]]]
    succeeded = sum(section["success"] for section in sections)
    failed = sum(section["status"] == "error" for section in sections)
    skipped_count = sum(section["status"] == "skipped" for section in sections)
    complete = unchanged and succeeded == len(sections)
    return {
        "success": complete,
        "document": {"before": before, "after": after, "unchanged_at_endpoints": unchanged,
                     "expected_title": expected, "guard_error": guard_error},
        "elements": elements,
        "completeness": {
            "complete": complete, "requested_elements": len(ids),
            "successful_elements": sum(element["success"] for element in elements),
            "requested_sections": len(sections), "successful_sections": succeeded,
            "failed_sections": failed, "skipped_sections": skipped_count,
            "document_verified_at_endpoints": unchanged,
        },
        "units": {"geometry_length": "ft", "geometry_area": "ft^2", "geometry_volume": "ft^3",
                  "parameters": "Values are returned unchanged by get_parameter_value; formatted strings may use document display units."},
        "limitations": [
            "Sequential dedicated reads are not an atomic snapshot; endpoint document checks cannot detect a switch away and back or edits between reads.",
            "Completeness covers requested reads only. Null geometry fields remain null; omitted parameters are not inspected.",
        ],
    }
