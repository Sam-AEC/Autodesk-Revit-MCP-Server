"""Decides whether one concrete tool call needs the approval gate.

`is_mutating` on a tool is a static, per-tool flag. A few tools can also be
called in a way that provably cannot change the model (`revit_execute_python`
with mode='read'). Those providers implement `call_is_read_only(name, arguments)`
and this helper asks them. The answer is only ever "skip the gate" when the
provider says so positively; a missing hook or an unexpected shape keeps the gate.
A provider may raise (for example ReadModeViolation) to refuse a call outright.
"""
from __future__ import annotations

from typing import Any


def requires_approval(registry: Any, name: str, tool_def: Any, arguments: Any) -> bool:
    if tool_def is None or not tool_def.is_mutating:
        return False
    if not isinstance(arguments, dict):
        return True
    provider = registry.lookup_tool_provider(name)
    hook = getattr(provider, "call_is_read_only", None)
    if hook is None:
        return True
    return hook(name, arguments) is not True
