"""Ephemeral capability granted only by dispatch after the outer approval check.

Metadata and stored plan claims do not authorize nested execution. A copied thread
context shares this revocable scope, so an executor cannot outlive its outer call.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass
class _Execution:
    name: str
    active: bool = True


_execution: ContextVar[_Execution | None] = ContextVar("authorized_module_execution", default=None)


@contextmanager
def authorized_module_execution(name: str) -> Iterator[None]:
    """Wrap a provider call only AFTER the shared gate has authorized that call."""
    scope = _Execution(name)
    token = _execution.set(scope)
    try:
        yield
    finally:
        scope.active = False
        _execution.reset(token)


def capture_module_execution(name: str) -> _Execution | None:
    """Return the exact active scope; callers retain its identity, not just its name."""
    scope = _execution.get()
    return scope if scope is not None and scope.active and scope.name == name else None


def module_execution_authorized(name: str, expected_scope: _Execution | None = None) -> bool:
    scope = capture_module_execution(name)
    return scope is not None and (expected_scope is None or scope is expected_scope)
