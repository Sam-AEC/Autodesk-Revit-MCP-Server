import contextlib
import getpass
import os
import re
import tempfile
import threading
import time
import uuid
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Iterator, List, Optional
from ..config import APPROVAL_MODES, config, normalize_approval_mode  # noqa: F401 (re-exported)
from ..errors import BridgeError
from . import proof as proof_mod
from .approval_override import active_override

logger = logging.getLogger(__name__)

# Tools that move a plan between approval states. They stay registered (the Revit
# panel and the command-line tool use them) but are never offered to a model: an
# agent that can approve its own plan has no human gate at all. Every internal
# dispatch path refuses them too (see security/dispatch.py); only
# ApprovalProvider.execute_human_tool, called by the panel route, runs them.
HUMAN_ONLY_TOOLS = frozenset({"approve_plan", "reject_plan", "rollback_plan"})

# Channels that may record an approval. Set by the code path, never by tool arguments.
APPROVAL_CHANNELS = frozenset({"panel", "cli"})

# Arguments that identify or schedule a call rather than describe the change, so
# they are ignored when matching a call to an approved action.
VOLATILE_ARGUMENT_KEYS = frozenset({"plan_id", "run_async", "idempotency_key"})

# Plan keys the caller of create_plan(extra=...) may not set: the hash fields and the
# hashed review block (which has its own validated parameter).
_RESERVED_EXTRA_KEYS = frozenset({
    "review", "hash_version", "plan_hash", "approved_hash", "plan_id", "created_at", "actions",
}) | proof_mod.STATE_PLAN_KEYS

PLAN_ID_RE = re.compile(r"plan_[0-9a-f]{12}")
ACTION_ID_RE = re.compile(r"act_[0-9a-f]{12}")

# Action states. Only "pending" is open; "running", "executed" and "failed" are consumed.
OPEN_ACTION_STATES = frozenset({"pending", None})
DONE_ACTION_STATES = frozenset({"executed", "failed", "abandoned"})
# A running action older than this is shown as STALE to the person; nothing is ever
# recovered automatically, only the human `recover` command changes it.
STALE_RUNNING_SECONDS = 15 * 60
# os.replace can raise PermissionError on Windows while a reader holds the target.
REPLACE_ATTEMPTS = 5
REPLACE_BACKOFF_SECONDS = 0.01

_PROCESS_LOCK = threading.RLock()


LOOK_ONLY_MESSAGE = (
    "Look only mode: this tool changes the model. Switch to Ask me first in the panel or settings."
)


def validate_plan_id(plan_id: Any) -> str:
    """Accept only ids of the shape create_plan makes; anything else is refused."""
    if not isinstance(plan_id, str) or not PLAN_ID_RE.fullmatch(plan_id):
        raise BridgeError(
            "Invalid plan_id: expected the id returned by plan_actions ('plan_' followed by 12 hex characters)."
        )
    return plan_id


def local_user() -> str:
    """The OS account running this process. Recorded, not authenticated."""
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def _canonical(value: Any) -> Any:
    """Normalise JSON-ish data so equal calls compare equal (key order, 5 vs 5.0)."""
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def canonical_arguments(arguments: Any) -> str:
    if not isinstance(arguments, dict):
        # Never let a malformed (non-object) argument list compare equal to {}.
        return json.dumps({"__not_an_object__": _canonical(arguments)}, sort_keys=True, default=str,
                          separators=(",", ":"))
    kept = {k: v for k, v in arguments.items() if k not in VOLATILE_ARGUMENT_KEYS}
    return json.dumps(_canonical(kept), sort_keys=True, default=str, separators=(",", ":"))


def plan_hash(plan: Dict[str, Any]) -> str:
    """Content hash of what a person reviews: ids, tools, arguments, before values."""
    return proof_mod.plan_content_hash(plan)


@contextlib.contextmanager
def _locked_file(path: Path) -> Iterator[None]:
    """Exclusive lock on ``path`` across processes (fcntl on POSIX, msvcrt on Windows)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as fh:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except ImportError:  # pragma: no cover - Windows
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def replace_with_retry(src: Any, dst: Any) -> None:
    """Atomic ``os.replace`` with a bounded retry for transient PermissionError (Windows
    readers such as antivirus or a polling panel). Atomicity is unchanged: the same single
    replace call is retried, never a delete-then-write. Fails with a clear BridgeError."""
    last: Optional[BaseException] = None
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError as e:
            last = e
            if attempt < REPLACE_ATTEMPTS - 1:
                time.sleep(min(0.05, REPLACE_BACKOFF_SECONDS * (attempt + 1)))
    raise BridgeError(
        f"Could not write '{Path(str(dst)).name}': the file stayed locked by another program after "
        f"{REPLACE_ATTEMPTS} attempts ({last}). Nothing was changed; close whatever is reading the "
        "plans folder and try again."
    )


def running_actions(plan: Dict[str, Any], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Actions stuck in 'running', each as {action_id, tool, claimed_at, age_seconds, stale}.
    Information only: nothing here changes a plan."""
    now = now or datetime.now(timezone.utc)
    out = []
    actions = plan.get("actions", [])
    for a in actions if isinstance(actions, list) else []:
        if not isinstance(a, dict) or a.get("state") != "running":
            continue
        age = None
        try:
            claimed = datetime.fromisoformat(str(a.get("claimed_at")))
            if claimed.tzinfo is None:
                claimed = claimed.replace(tzinfo=timezone.utc)
            age = max(0.0, (now - claimed).total_seconds())
        except (TypeError, ValueError):
            pass
        out.append({"action_id": a.get("action_id"), "tool": a.get("tool"), "claimed_at": a.get("claimed_at"),
                    "age_seconds": age, "stale": age is None or age >= STALE_RUNNING_SECONDS})
    return out


class ApprovalGate:
    def __init__(self, workspace_dir: Path, approval_mode: str = config.approval_mode) -> None:
        self.workspace_dir = workspace_dir
        self.override_token: Optional[str] = None  # tests; normally read from the panel token file
        self.approval_mode = approval_mode
        self.plans_dir = workspace_dir / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    @property
    def approval_mode(self) -> str:
        """The mode in force right now: the mode this process started with, unless the panel has
        switched approvals to 'auto' for a limited time (see approval_override.py). The window
        never relaxes look_only and ends by itself."""
        if self._approval_mode == "ask_first" and active_override(self.workspace_dir, token=self.override_token):
            return "auto"
        return self._approval_mode

    @approval_mode.setter
    def approval_mode(self, value: Any) -> None:
        self._approval_mode = normalize_approval_mode(value)

    @property
    def baseline_approval_mode(self) -> str:
        """The mode this process started with, ignoring any temporary 'auto' window."""
        return self._approval_mode

    def auto_window(self) -> Optional[Dict[str, int]]:
        """{"set_at", "expires_at"} while a temporary 'auto' window is in force, else None."""
        if self._approval_mode == "ask_first":
            return active_override(self.workspace_dir, token=self.override_token)
        return None

    def refuse_if_look_only(self) -> None:
        """Raise when the mode is look_only. Called for every mutating tool, on every path."""
        if self.approval_mode == "look_only":
            raise BridgeError(LOOK_ONLY_MESSAGE)

    def _get_plan_path(self, plan_id: str) -> Path:
        validate_plan_id(plan_id)
        root = self.plans_dir.resolve()
        path = (root / f"{plan_id}.json").resolve()
        if path.parent != root:
            raise BridgeError("Invalid plan_id: the plan file is outside the plans folder.")
        return path

    @contextlib.contextmanager
    def _plan_lock(self, plan_id: str) -> Iterator[None]:
        """Serialise read-modify-write of one plan across threads and processes."""
        validate_plan_id(plan_id)
        with _PROCESS_LOCK, _locked_file(self.plans_dir / ".locks" / f"{plan_id}.lock"):
            yield

    def load_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        path = self._get_plan_path(plan_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                plan = json.load(f)
        except Exception as e:
            logger.error("Failed to load plan %s: %s", plan_id, e)
            return None
        if not isinstance(plan, dict) or plan.get("plan_id") != plan_id:
            raise BridgeError(f"Plan file for '{plan_id}' does not hold that plan; refusing to use it.")
        return plan

    def save_plan(self, plan: Dict[str, Any]) -> None:
        plan_id = plan["plan_id"]
        path = self._get_plan_path(plan_id)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{plan_id}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=2)
            replace_with_retry(tmp, path)
        except Exception as e:
            logger.error("Failed to save plan %s: %s", plan_id, e)
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    @staticmethod
    def validate_actions(actions: Any) -> None:
        """Refuse action lists a person could not review faithfully or that name human-only tools."""
        if not isinstance(actions, list):
            raise BridgeError("'actions' must be a list.")
        for i, action in enumerate(actions):
            if not isinstance(action, dict) or not isinstance(action.get("tool"), str) or not action.get("tool"):
                raise BridgeError(f"Action {i + 1} must be an object with a 'tool' name.")
            if action["tool"] in HUMAN_ONLY_TOOLS:
                raise BridgeError(f"Action {i + 1}: '{action['tool']}' cannot be part of a plan; a person runs it.")
            if not isinstance(action.get("arguments", {}), dict):
                raise BridgeError(f"Action {i + 1} ('{action['tool']}'): 'arguments' must be an object.")

    def create_plan(
        self,
        actions: List[Dict[str, Any]],
        before_states: List[Dict[str, Any]],
        snapshot_id: Optional[str] = None,
        skipped: Optional[List[Dict[str, Any]]] = None,
        extra: Optional[Dict[str, Any]] = None,
        before_storage_types: Optional[List[Optional[str]]] = None,
        review: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Draft a plan. ``review`` (summary, reasoning, citations, ...) is validated,
        canonicalised and covered by the plan hash. ``extra`` is metadata only: it is NOT
        hashed and must not be presented as approved content (see proof.unhashed_metadata_keys)."""
        self.validate_actions(actions)
        if proof_mod.has_nonfinite_float(actions) or proof_mod.has_nonfinite_float(review):
            raise BridgeError("A plan cannot hold NaN or Infinity.")
        reserved = sorted(k for k in (extra or {}) if k in _RESERVED_EXTRA_KEYS)
        if reserved:
            raise BridgeError("'extra' cannot set: " + ", ".join(reserved)
                              + ". Use the review block for reviewable content.")
        if review is not None:
            try:
                review = proof_mod.normalize_review(review)
            except ValueError as e:
                raise BridgeError(f"Invalid review block: {e}")
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        plan_actions = []
        for i, action in enumerate(actions):
            act_id = f"act_{uuid.uuid4().hex[:12]}"
            before = before_states[i] if i < len(before_states) else {}

            arguments = action.get("arguments", {})
            diff = {
                "type": "parameter_change" if "parameter_name" in arguments else "model_modification",
                "before": before,
                "after": arguments,
                "element_count": 1
            }
            if before_storage_types and i < len(before_storage_types) and before_storage_types[i]:
                # Revit StorageType of the parameter when the before value was captured, so a
                # revert can rebuild a correctly typed value (the live read returns strings).
                diff["before_storage_type"] = before_storage_types[i]
            plan_actions.append({
                "action_id": act_id,
                "tool": action.get("tool"),
                "arguments": arguments,
                "diff": diff,
                "state": "pending"
            })

        plan = {
            "plan_id": plan_id,
            "state": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "actions": plan_actions,
            "is_reversible": True,
            "reversible_strategy": "inverse"
        }
        if snapshot_id:
            plan["snapshot_id"] = snapshot_id
        if skipped:
            plan["skipped"] = skipped
        if extra:
            plan.update({k: v for k, v in extra.items() if k not in ("plan_id", "state", "actions")})
        if review is not None:
            plan["review"] = review
            plan["hash_version"] = proof_mod.HASH_VERSION_REVIEW
        plan["plan_hash"] = plan_hash(plan)
        self.save_plan(plan)
        return plan

    def list_pending_plans(self) -> List[Dict[str, Any]]:
        plans = []
        for path in self.plans_dir.glob("*.json"):
            if not PLAN_ID_RE.fullmatch(path.stem):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    plan = json.load(f)
            except Exception:
                continue
            if isinstance(plan, dict) and plan.get("plan_id") == path.stem and plan.get("state") == "pending":
                plans.append(plan)
        return plans

    def update_plan_state(self, plan_id: str, state: str, approver: Optional[str] = None,
                          via: Optional[str] = None, expected_hash: Optional[str] = None) -> Dict[str, Any]:
        """Move a plan to ``state``.

        Approving needs ``expected_hash``: the hash of the plan the person was shown. The
        approval is refused if the plan on disk no longer has that content, so a person
        approves exactly what they reviewed. ``via`` is the channel ('panel' or 'cli')
        and is set by the calling code path, never taken from tool arguments.
        """
        with self._plan_lock(plan_id):
            plan = self.load_plan(plan_id)
            if not plan:
                raise ValueError(f"Plan {plan_id} not found")
            current = plan.get("state")
            if state == "approved":
                if current != "pending":
                    raise ValueError(f"Plan {plan_id} is in state '{current}'; only a pending plan can be approved.")
                if via not in APPROVAL_CHANNELS:
                    raise ValueError("An approval must come from the panel or the command-line tool.")
                now_hash = plan_hash(plan)
                if not expected_hash or expected_hash != now_hash:
                    raise ValueError(
                        f"Plan {plan_id} is not the plan that was shown for approval (its content changed). "
                        "Review it again before approving."
                    )
                if proof_mod.plan_hash_version(plan) == proof_mod.HASH_VERSION_REVIEW:
                    # Same strict schema the command-line tool applies, on every approval channel.
                    if proof_mod.normalize_review(plan["review"]) != plan["review"]:
                        raise ValueError(
                            f"Plan {plan_id} has a review block that is not in canonical form; it cannot be approved."
                        )
                if plan.get("plan_hash") != now_hash:
                    raise ValueError(
                        f"Plan {plan_id} was changed after it was drafted. Ask for a new plan instead of approving it."
                    )
            elif state == "rejected":
                if current not in ("pending", "approved"):
                    raise ValueError(
                        f"Plan {plan_id} is in state '{current}'; only a pending or approved plan can be rejected."
                    )
                if via is not None and via not in APPROVAL_CHANNELS:
                    raise ValueError("A rejection must come from the panel or the command-line tool.")
            plan["state"] = state
            now = datetime.now(timezone.utc).isoformat()
            if state == "approved":
                plan["approved_at"] = now
                plan["approved_hash"] = now_hash
                plan["approved_via"] = via
                plan["approved_by"] = str(approver) if approver else local_user()
            elif state == "rejected":
                plan["rejected_at"] = now
                if current == "approved":
                    plan["rejected_after_approval"] = True
                if via:
                    plan["rejected_via"] = via
            fill_proof = False
            if state == "executed":
                plan["executed_at"] = now
                # execute_plan writes a richer proof itself; only fill in for direct tool calls.
                try:
                    fill_proof = proof_mod.read_proof(self.workspace_dir, plan_id) is None
                except ValueError:
                    fill_proof = False
            self.save_plan(plan)
        if fill_proof:
            try:
                self.record_proof(plan)
            except Exception:
                logger.exception("Failed to write proof bundle for plan %s", plan_id)
        return plan

    def record_proof(self, plan: Dict[str, Any], results: Optional[List[Dict[str, Any]]] = None,
                     outcome: Optional[str] = None) -> Dict[str, Any]:
        """Write proofs/<plan_id>.json for a finished (success / partial / failed) plan."""
        bundle = proof_mod.build_proof(plan, self.workspace_dir, results=results, outcome=outcome)
        proof_mod.write_proof(self.workspace_dir, bundle)
        return bundle

    def load_proof(self, plan_id: str) -> Optional[Dict[str, Any]]:
        return proof_mod.read_proof(self.workspace_dir, plan_id)

    def verify_approved(self, plan: Dict[str, Any]) -> None:
        """Refuse unless the plan is approved and still holds exactly what was approved."""
        plan_id = plan.get("plan_id")
        if plan.get("state") != "approved":
            raise BridgeError(f"Plan '{plan_id}' is in state '{plan.get('state')}', not 'approved'. Execution blocked.")
        approved = plan.get("approved_hash")
        try:
            current_hash = plan_hash(plan)
        except ValueError:
            current_hash = None
        if not approved or current_hash != approved:
            raise BridgeError(
                f"Plan '{plan_id}' changed after it was approved (or has no approval record). Execution blocked; "
                "draft a new plan and ask the person to approve it."
            )

    def check_tool_execution(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        """Read-only check that a call is covered by an approved, unchanged plan.

        Execution paths use claim_action, which makes the same checks and consumes the
        action atomically before the tool runs.
        """
        self.refuse_if_look_only()
        if self.approval_mode == "auto":
            return
        if tool_name in HUMAN_ONLY_TOOLS:
            raise BridgeError(f"'{tool_name}' is run by a person, not through a tool call.")

        plan_id = arguments.get("plan_id") if isinstance(arguments, dict) else None
        if not plan_id:
            raise BridgeError(f"Approval mode is enabled. Mutating tool '{tool_name}' requires a valid 'plan_id' parameter.")

        plan = self.load_plan(plan_id)
        if not plan:
            raise BridgeError(f"Plan '{plan_id}' does not exist.")
        self.verify_approved(plan)

        if self._find_open_action(plan, tool_name, arguments) is None:
            raise self._no_action_error(plan_id, tool_name)

    @staticmethod
    def _no_action_error(plan_id: str, tool_name: str) -> BridgeError:
        return BridgeError(
            f"Plan '{plan_id}' does not approve this call: it has no remaining approved action for "
            f"'{tool_name}' with these arguments (an action can only run once, exactly as approved). "
            "Draft a new plan for this change and ask the person to approve it."
        )

    @staticmethod
    def _find_open_action(plan: Dict[str, Any], tool_name: str, arguments: Any,
                          skip: Optional[set] = None) -> Optional[Dict[str, Any]]:
        wanted = canonical_arguments(arguments)
        for action in plan.get("actions", []):
            if action.get("state") not in OPEN_ACTION_STATES or action.get("tool") != tool_name:
                continue
            if skip and action.get("action_id") in skip:
                continue
            if canonical_arguments(action.get("arguments", {})) == wanted:
                return action
        return None

    def _claim_marker(self, plan_id: str, action_id: Any) -> Path:
        if not isinstance(action_id, str) or not ACTION_ID_RE.fullmatch(action_id):
            raise BridgeError(f"Plan '{plan_id}' has a malformed action id; refusing to run it.")
        return self.plans_dir / ".claims" / f"{plan_id}.{action_id}"

    def claim_action(self, tool_name: str, arguments: Any) -> Optional[Dict[str, str]]:
        """Consume the matching approved action BEFORE the tool runs (at most once).

        Under a per-plan lock, checks the plan (approved, unchanged since approval),
        finds an open action with the same tool and arguments, creates a claim marker
        with O_EXCL (so exactly one caller wins even across processes, and an edited
        action state cannot reopen it) and marks the action 'running'. The action stays
        consumed whatever the tool does next: a failed or interrupted call needs a new plan.

        Returns {"plan_id", "action_id"} or None when the gate is off and the call
        carries no plan. Raises BridgeError when the call is not allowed.
        """
        if tool_name in HUMAN_ONLY_TOOLS:
            raise BridgeError(f"'{tool_name}' is run by a person, not through a tool call.")
        self.refuse_if_look_only()
        plan_id = arguments.get("plan_id") if isinstance(arguments, dict) else None
        if self.approval_mode == "auto":
            if not plan_id:
                return None
            try:  # gate off: keep the plan bookkeeping when we can, never block
                return self._claim(plan_id, tool_name, arguments)
            except BridgeError:
                return None
        if not plan_id:
            raise BridgeError(f"Approval mode is enabled. Mutating tool '{tool_name}' requires a valid 'plan_id' parameter.")
        return self._claim(plan_id, tool_name, arguments)

    def _claim(self, plan_id: Any, tool_name: str, arguments: Any) -> Dict[str, str]:
        validate_plan_id(plan_id)
        with self._plan_lock(plan_id):
            plan = self.load_plan(plan_id)
            if not plan:
                raise BridgeError(f"Plan '{plan_id}' does not exist.")
            self.verify_approved(plan)
            tried: set = set()
            while True:
                action = self._find_open_action(plan, tool_name, arguments, skip=tried)
                if action is None:
                    raise self._no_action_error(plan_id, tool_name)
                action_id = action.get("action_id")
                tried.add(action_id)
                marker = self._claim_marker(plan_id, action_id)
                marker.parent.mkdir(parents=True, exist_ok=True)
                try:
                    fd = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError:
                    continue  # consumed earlier; its recorded state is not trusted
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(datetime.now(timezone.utc).isoformat())
                break
            action["state"] = "running"
            action["claimed_at"] = datetime.now(timezone.utc).isoformat()
            self.save_plan(plan)
        return {"plan_id": plan_id, "action_id": action_id}

    def finish_action(self, claim: Optional[Dict[str, str]], ok: bool, error: Optional[str] = None
                      ) -> Optional[Dict[str, Any]]:
        """Record how a claimed action ended. Never reopens it.

        When no action is left open or running, the plan moves to 'executed' (every
        action succeeded) or 'partial' (some failed), unless a person rejected it.
        """
        if not claim:
            return None
        plan_id = claim["plan_id"]
        finished_all = False
        with self._plan_lock(plan_id):
            plan = self.load_plan(plan_id)
            if not plan:
                return None
            for action in plan.get("actions", []):
                if action.get("action_id") == claim["action_id"]:
                    if action.get("state") == "abandoned":
                        continue  # a person gave this action up; a late finish never revives it
                    action["state"] = "executed" if ok else "failed"
                    if not ok and error:
                        action["error"] = str(error)[:500]
            states = [a.get("state") for a in plan.get("actions", [])]
            all_done = all(s in DONE_ACTION_STATES for s in states)
            if all_done and plan.get("state") == "approved":
                if all(s == "executed" for s in states):
                    finished_all = True
                else:
                    plan["state"] = "partial"
                    plan["executed_at"] = datetime.now(timezone.utc).isoformat()
            self.save_plan(plan)
        if finished_all:
            return self.update_plan_state(plan_id, "executed")
        if plan.get("state") == "partial" and all_done:
            try:
                self.record_proof(plan)
            except Exception:
                logger.exception("Failed to write proof bundle for plan %s", plan_id)
        return plan

    def recover_running_actions(self, plan_id: str, reason: str, by: Optional[str] = None,
                                force: bool = False) -> Dict[str, Any]:
        """Human-only: give up every action stuck in 'running' (its process died mid-call).

        The actions become 'abandoned' with a reason and time. They are NEVER run again (the
        claim marker stays, and 'abandoned' is not an open state), so at-most-once holds. An
        approved plan becomes 'partial': its remaining open actions cannot run either, and
        need a new plan that a person approves. Not reachable through any tool call: only
        the command-line tool calls this. Fresh actions (younger than the stale threshold)
        are refused unless ``force``.
        """
        reason = str(reason or "").strip()
        if not reason:
            raise BridgeError("A reason is required to abandon a running action.")
        now = datetime.now(timezone.utc)
        with self._plan_lock(plan_id):
            plan = self.load_plan(plan_id)
            if not plan:
                raise BridgeError(f"Plan '{plan_id}' does not exist.")
            stuck = running_actions(plan, now)
            if not stuck:
                raise BridgeError(f"Plan '{plan_id}' has no action in state 'running'; nothing to recover.")
            if not force and any(not r["stale"] for r in stuck):
                raise BridgeError(
                    f"An action in plan '{plan_id}' started less than {STALE_RUNNING_SECONDS // 60} minutes ago "
                    "and may still be running. Wait, or pass --force if you are sure it is dead."
                )
            ids = {r["action_id"] for r in stuck}
            for action in plan["actions"]:
                if isinstance(action, dict) and action.get("action_id") in ids and action.get("state") == "running":
                    action["state"] = "abandoned"
                    action["abandoned_at"] = now.isoformat()
                    action["abandoned_reason"] = reason[:500]
                    action["abandoned_by"] = str(by) if by else local_user()
                    action["abandoned_via"] = "cli"
            closed = plan.get("state") == "approved"
            if closed:
                plan["state"] = "partial"
                plan["executed_at"] = now.isoformat()
            self.save_plan(plan)
        if closed:
            try:
                self.record_proof(plan)
            except Exception:
                logger.exception("Failed to write proof bundle for plan %s", plan_id)
        return plan

    def mark_action_executed(self, tool_name: str, arguments: Any) -> Optional[Dict[str, Any]]:
        """Claim and complete the matching action in one step (bookkeeping helper).

        Returns the plan, or None when the call carries no plan_id. A call that matches
        no open action leaves the plan unchanged.
        """
        plan_id = arguments.get("plan_id") if isinstance(arguments, dict) else None
        if not plan_id:
            return None
        try:
            claim = self._claim(plan_id, tool_name, arguments)
        except BridgeError:
            try:
                return self.load_plan(plan_id)
            except BridgeError:
                return None
        return self.finish_action(claim, ok=True)

    async def rollback_plan(self, plan_id: str, execute_fn) -> Dict[str, Any]:
        """Roll back an executed plan.

        `execute_fn` is an async callable `(tool_name, arguments) -> dict`; it MUST be
        awaited here rather than merely invoked, otherwise the inverse tool call never
        actually runs (a bare call just constructs and discards a coroutine object).

        Tools without a registered rollback handler are recorded as warnings (not
        errors) so that a mixed plan (some rollback-able, some not) still rolls back
        what it can and reports clearly what was skipped.
        """
        self.refuse_if_look_only()  # rollback writes to the model directly, outside claim_action
        plan = self.load_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        if plan.get("state") != "executed":
            raise ValueError(f"Plan {plan_id} is in state '{plan.get('state')}', cannot rollback. Only executed plans can be rolled back.")

        errors = []
        warnings = []
        for action in reversed(plan["actions"]):
            tool = action["tool"]
            before = action["diff"]["before"]
            if tool == "revit_set_parameter_value":
                elem_id = action["arguments"].get("element_id")
                param_name = action["arguments"].get("parameter_name")
                old_val = before.get(str(elem_id), {}).get(param_name)
                if old_val is not None:
                    try:
                        # Make sure to bypass or satisfy the approved state check
                        # We temporarily set the plan state to 'approved' for the rollback calls
                        plan["state"] = "approved"
                        self.save_plan(plan)
                        await execute_fn("revit_set_parameter_value", {
                            "element_id": elem_id,
                            "parameter_name": param_name,
                            "value": old_val,
                            "plan_id": plan_id
                        })
                    except Exception as e:
                        errors.append(f"Failed to rollback action {action.get('action_id')}: {e}")
                    finally:
                        plan["state"] = "executed"
                        self.save_plan(plan)
                else:
                    warnings.append(f"Skipped rollback for action {action.get('action_id')}: no before-value recorded")
            else:
                warnings.append(f"No rollback handler for tool '{tool}' (action {action.get('action_id')}) — skipped")

        if errors:
            plan["state"] = "partial_rollback"
            plan["rollback_warnings"] = warnings
            self.save_plan(plan)
            raise BridgeError(f"Rollback encountered errors: {'; '.join(errors)}")

        plan["state"] = "rolled_back"
        plan["rollback_warnings"] = warnings
        self.save_plan(plan)
        return plan
