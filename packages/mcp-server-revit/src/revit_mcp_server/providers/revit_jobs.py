"""Async Revit jobs: run a Revit tool or script as a job, then poll it by id.

A job wraps one call to an existing Revit tool (or a Python script) in the shared
JobManager, so a slow script no longer ties up the MCP call. The add-in itself is
strictly serial, so jobs are also run one at a time here: a job is `queued` until
the previous one has finished, and only a queued job can be cancelled.

Approval is not weakened. `revit_run_job` is a gated tool; the gate asks
`call_is_read_only` and only skips itself when the wrapped call is a read-only
tool or a read-mode script. Anything else needs the plan_id of an approved plan.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..jobs import JobManager, JobReference
from ..security.audit import redact_data
from ..security.read_mode import ReadModeViolation, normalize_mode
from .base import AECProvider, ProviderTool, enrich_mutation_metadata
from .revit import RevitProvider

PYTHON_TOOL = "revit_execute_python"
MAX_PROGRESS_LINES = 20
_TERMINAL = frozenset({"completed", "failed", "cancelled"})


def _is_running(result: Any) -> bool:
    return isinstance(result, dict) and result.get("status") == "running" and bool(result.get("request_id"))


def _elapsed_seconds(ref: JobReference) -> float:
    def parse(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None

    start = parse(ref.created_at)
    end = parse(ref.finished_at) or datetime.now(timezone.utc)
    return round((end - start).total_seconds(), 2) if start else 0.0


class RevitJobProvider(AECProvider):
    def __init__(
        self,
        revit: RevitProvider,
        manager: JobManager,
        *,
        default_wait_s: float = 20.0,
        max_wait_s: float = 120.0,
        max_job_s: float = 1800.0,
        poll_s: float = 5.0,
    ) -> None:
        self.revit = revit
        self.manager = manager
        self.default_wait_s = default_wait_s
        self.max_wait_s = max_wait_s
        self.max_job_s = max_job_s
        self.poll_s = poll_s
        self._request_ids: dict[str, str] = {}
        self._lock: asyncio.Lock | None = None
        self._running: dict[str, str] = {}
        self._capabilities = self._build_capabilities()

    def _build_capabilities(self) -> List[ProviderTool]:
        job_id = {"job_id": {"type": "string", "description": "Job id returned by revit_run_job."}}
        tools = [
            ProviderTool(
                name="revit_run_job",
                description=(
                    "Run a Revit tool or an IronPython script as a background job and get a job_id back. "
                    "Waits up to wait_s seconds for a result; if the work is still running, poll revit_job_status. "
                    "Jobs run one at a time in Revit. A read-only command or a script with mode='read' needs no "
                    "approval; anything that can change the model needs the plan_id of an approved plan."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "A Revit MCP tool name such as revit_list_levels, or its bridge name revit.list_levels. Use this or script.",
                        },
                        "script": {
                            "type": "string",
                            "description": "IronPython source to run in Revit, same as revit_execute_python. Use this or command.",
                        },
                        "args": {
                            "type": "object",
                            "description": "Arguments for the command, exactly as the tool takes them.",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["read", "write"],
                            "default": "write",
                            "description": "For scripts: 'read' cannot open transactions and needs no approval; 'write' (default) needs an approved plan_id.",
                        },
                        "wait_s": {
                            "type": "number",
                            "minimum": 0,
                            "description": "Seconds to wait for a result before returning the job_id (default 20, at most 120). 0 returns at once.",
                        },
                        "idempotency_key": {
                            "type": "string",
                            "description": "Optional key; a repeated call with the same key returns the existing job instead of starting another.",
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            ProviderTool(
                name="revit_job_status",
                description=(
                    "Get the state of a Revit job: queued, running, completed, failed or cancelled, "
                    "with elapsed seconds, the last progress lines and the output once it has finished. Read-only."
                ),
                inputSchema={"type": "object", "properties": job_id, "required": ["job_id"], "additionalProperties": False},
            ),
            ProviderTool(
                name="revit_job_cancel",
                description=(
                    "Cancel a Revit job that is still queued. A job that Revit has already started cannot be "
                    "stopped from here; the reply says so and the job keeps running."
                ),
                inputSchema={"type": "object", "properties": job_id, "required": ["job_id"], "additionalProperties": False},
            ),
        ]
        enrich_mutation_metadata(tools, mutating_names=frozenset({"revit_run_job"}), destructive=frozenset({"revit_run_job"}))
        return tools

    def get_identity(self) -> str:
        return "revit_jobs"

    def get_capabilities(self) -> List[ProviderTool]:
        return self._capabilities

    async def check_health(self) -> Dict[str, Any]:
        return {"status": "healthy", "provider": "revit_jobs"}

    async def shutdown(self) -> None:
        pass

    # -- approval hook ---------------------------------------------------

    def call_is_read_only(self, name: str, arguments: Dict[str, Any]) -> bool:
        if name != "revit_run_job":
            return False
        try:
            tool_name, tool_args = self._resolve(arguments)
        except ReadModeViolation:
            raise
        except ValueError:
            return False  # a malformed call stays gated; execute_tool reports the real problem
        tool = self._revit_tools()[tool_name]
        if not tool.is_mutating:
            return True
        return self.revit.call_is_read_only(tool_name, tool_args) is True

    # -- execution -------------------------------------------------------

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "revit_run_job":
            return await self._run_job(arguments)
        if name == "revit_job_status":
            return await self._status(arguments["job_id"])
        if name == "revit_job_cancel":
            return await self._cancel(arguments["job_id"])
        raise ValueError(f"Unknown Revit job tool: {name}")

    def _revit_tools(self) -> dict[str, ProviderTool]:
        return {tool.name: tool for tool in self.revit.get_capabilities()}

    def _resolve(self, arguments: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        command = arguments.get("command")
        script = arguments.get("script")
        if bool(command) == bool(script):
            raise ValueError("revit_run_job needs exactly one of command or script")
        if script:
            return PYTHON_TOOL, {"script": script, "mode": normalize_mode(arguments.get("mode"))}

        mapping = getattr(self.revit, "_tool_mapping", {})
        by_bridge_name = {bridge: tool for tool, (bridge, _builder) in mapping.items()}
        tool_name = command if command in mapping else by_bridge_name.get(command)
        if tool_name is None or tool_name not in self._revit_tools():
            raise ValueError(f"Unknown Revit command '{command}'. Use a Revit tool name such as revit_list_levels.")
        tool_args = dict(arguments.get("args") or {})
        if tool_name == PYTHON_TOOL and arguments.get("mode") is not None:
            tool_args.setdefault("mode", arguments["mode"])
        return tool_name, tool_args

    async def _run_job(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool_name, tool_args = self._resolve(arguments)
        raw_wait = arguments.get("wait_s")
        wait_s = self.default_wait_s if raw_wait is None else float(raw_wait)
        wait_s = max(0.0, min(wait_s, self.max_wait_s))

        async def job(context=None):
            return await self._execute(context.job_id, tool_name, tool_args)

        ref = await self.manager.submit(job, idempotency_key=arguments.get("idempotency_key"))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        while True:
            current = await self.manager.get(ref.job_id)
            if current is None:
                raise ValueError(f"Job not found: {ref.job_id}")
            if current.status in _TERMINAL or loop.time() >= deadline:
                return self._describe(current, tool_name)
            await asyncio.sleep(0.1)

    async def _execute(self, job_id: str, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if len(self._running) > 256:
                for stale in list(self._running)[:-128]:
                    self._running.pop(stale, None)
                    self._request_ids.pop(stale, None)
            self._running[job_id] = tool_name
            try:
                # execute_tool runs the blocking bridge call on a worker thread, so the event loop stays free.
                result = await self.revit.execute_tool(tool_name, tool_args)
                result = await self._collect(job_id, result)
                if _is_running(result):
                    return {
                        "ok": False,
                        "tool": tool_name,
                        "error": {
                            "kind": "StillRunning",
                            "message": (
                                f"Revit was still working after {self.max_job_s:.0f} s. The job stopped waiting; Revit "
                                "keeps running it. Collect the output with revit_get_result using request_id "
                                f"{result.get('request_id')}. Do not repeat a write until it has finished."
                            ),
                            "request_id": result.get("request_id"),
                        },
                    }
                return {"ok": True, "tool": tool_name, "result": result}
            except Exception as exc:  # noqa: BLE001 - the agent needs the reason, not a generic "Job failed"
                return {
                    "ok": False,
                    "tool": tool_name,
                    "error": {"kind": type(exc).__name__, "message": redact_data(str(exc))},
                }

    async def _collect(self, job_id: str, result: Any) -> Any:
        """Follow a {"status": "running", "request_id": ...} answer to the durable result in the add-in.

        The add-in keeps the outcome of a call that outlived the bridge's soft wait, so the job polls
        `get_result` (on a worker thread) until it is done, fails, or max_job_s has passed.
        """
        if not _is_running(result):
            return result
        fetch = getattr(self.revit._active_bridge(), "get_result", None)
        if fetch is None:
            return result
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.max_job_s
        while _is_running(result) and loop.time() < deadline:
            request_id = str(result["request_id"])
            self._request_ids[job_id] = request_id
            wait_s = max(0.0, min(self.poll_s, deadline - loop.time()))
            result = await asyncio.to_thread(fetch, request_id, wait_s=wait_s)
        return result

    async def _status(self, job_id: str) -> Dict[str, Any]:
        ref = await self.manager.get(job_id)
        if ref is None:
            raise ValueError(f"Job not found: {job_id}")
        return self._describe(ref)

    async def _cancel(self, job_id: str) -> Dict[str, Any]:
        ref = await self.manager.get(job_id)
        if ref is None:
            raise ValueError(f"Job not found: {job_id}")
        state = self._state(ref)
        if state == "queued":
            cancelled = await self.manager.cancel(job_id)
            return {"job_id": job_id, "state": self._state(cancelled), "cancelled": True}
        if state == "running":
            message = "The job is already running in Revit; only queued jobs can be cancelled."
        else:
            message = f"The job already finished ({state})."
        return {"job_id": job_id, "state": state, "cancelled": False, "message": message}

    # -- reporting -------------------------------------------------------

    def _state(self, ref: JobReference) -> str:
        if ref.status in ("queued", "running"):
            return "running" if ref.job_id in self._running else "queued"
        if ref.status == "completed":
            envelope = ref.result if isinstance(ref.result, dict) else {}
            result = envelope.get("result")
            script_failed = isinstance(result, dict) and result.get("success") is False
            return "failed" if envelope.get("ok") is False or script_failed else "completed"
        return ref.status

    def _describe(self, ref: JobReference, tool_name: str | None = None) -> Dict[str, Any]:
        state = self._state(ref)
        envelope = ref.result if isinstance(ref.result, dict) else {}
        report: Dict[str, Any] = {
            "job_id": ref.job_id,
            "state": state,
            "tool": tool_name or envelope.get("tool") or self._running.get(ref.job_id),
            "elapsed_s": _elapsed_seconds(ref),
            "progress": [],
        }
        request_id = self._request_ids.get(ref.job_id)
        if request_id and state in ("running", "queued"):
            report["request_id"] = request_id
        if state in ("completed", "failed"):
            if envelope.get("ok") is False:
                report["error"] = envelope.get("error")
            else:
                output = envelope.get("result")
                report["output"] = output
                lines = output.get("progress") if isinstance(output, dict) else None
                if isinstance(lines, list):
                    report["progress"] = [str(line) for line in lines[-MAX_PROGRESS_LINES:]]
        return report
