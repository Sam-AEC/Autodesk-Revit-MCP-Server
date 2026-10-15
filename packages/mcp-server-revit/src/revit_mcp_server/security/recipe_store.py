"""Files behind the recipe library (module ``revit_recipes``) and the human-set standing approvals.

A recipe is IronPython 2.7 code saved as ``<workspace>/recipes/<id>.py`` with a manifest ``<id>.json``
(id, version, title, description, params schema, mode, sha256 of the code). Saving only writes those two files.

The approval gate imports this module to honour a *standing* approval, so everything the decision rests on lives
here and nowhere a model can write:

  * the code hash is recomputed from the file every time a recipe is read; a manifest that disagrees with its code
    is refused, never repaired;
  * a standing approval is a record under ``<workspace>/plans/standing/`` (a folder tools may not write, see
    security/workspace.py). Only ``aec-model-bridge-approve recipe-standing`` creates it. It names a recipe id and
    the sha256 of its code, and counts only while the code on disk still has that hash. Saving, editing or deleting
    a recipe removes it.

The manifest's own ``approval`` field is informational (always ``per_run`` when saved); the effective value is
computed from the record, so editing a manifest file cannot grant anything.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

RECIPE_RUN_TOOL = "revit_recipe_run"
RECIPES_DIR = "recipes"
STANDING_DIR = "standing"  # under <workspace>/plans

ID_RE = re.compile(r"[a-z0-9_-]{1,64}")
RESERVED_IDS = frozenset({"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)})
SHA_RE = re.compile(r"[0-9a-f]{64}")

MAX_CODE_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_RECIPES = 200
MAX_PARAMS = 30
MAX_PARAMS_JSON_BYTES = 8 * 1024
MODES = ("read", "write")
APPROVALS = ("per_run", "standing")
PARAM_TYPES = ("integer", "number", "string", "boolean")

_PARAM_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,39}")
_UNIT = re.compile(r"[A-Za-z0-9_/%^. -]{1,16}")
_FUTURE_IMPORT = re.compile(r"^\s*from\s+__future__\s+import\b", re.MULTILINE)
_PARAM_KEYS = {"name", "type", "unit", "min", "max", "required", "default", "enum", "max_length", "description"}
_LOCK = threading.RLock()


class RecipeError(ValueError):
    """A recipe request that is refused. ``kind`` is the machine-readable reason."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


# --------------------------------------------------------------------------- #
# Ids, hashes
# --------------------------------------------------------------------------- #
def validate_recipe_id(value: Any) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value) or value in RESERVED_IDS:
        raise RecipeError("invalid_id", "id must be 1 to 64 characters from a-z, 0-9, '_' and '-' (not a reserved device name)")
    return value


def normalize_code(code: Any) -> str:
    """Line endings are normalised to LF so a checkout with CRLF has the same hash."""
    if not isinstance(code, str):
        raise RecipeError("invalid_input", "code must be a string")
    return code.replace("\r\n", "\n").replace("\r", "\n")


def code_sha256(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode("utf-8")).hexdigest()


def check_code(code: Any) -> str:
    """Return the normalised code or raise: non-empty, UTF-8 text, at most 64 KiB, no NUL, no ``__future__`` import."""
    text = normalize_code(code)
    if not text.strip():
        raise RecipeError("invalid_input", "code is empty")
    if "\x00" in text:
        raise RecipeError("invalid_input", "code must not contain NUL characters")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise RecipeError("invalid_input", "code must be valid text") from exc
    if size > MAX_CODE_BYTES:
        raise RecipeError("code_too_large", f"code is {size} bytes; the limit is {MAX_CODE_BYTES} (64 KiB)")
    if _FUTURE_IMPORT.search(text):
        raise RecipeError("invalid_input", "'from __future__ import' is not supported in recipes (the server adds a header line before the code)")
    return text


# --------------------------------------------------------------------------- #
# Parameter schema and values
# --------------------------------------------------------------------------- #
def _number(value: Any, what: str, integer: bool = False, kind: str = "invalid_input") -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecipeError(kind, f"{what} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise RecipeError(kind, f"{what} must be finite")
    if integer and (isinstance(value, float) or abs(value) > 2 ** 53):
        raise RecipeError(kind, f"{what} must be a whole number")
    return value


def _check_value(spec: Dict[str, Any], value: Any) -> Any:
    """Check one value against its schema entry. Messages name the parameter, never echo the value."""
    name, kind = spec["name"], spec["type"]
    what = f"params.{name}"
    if kind == "boolean":
        if not isinstance(value, bool):
            raise RecipeError("invalid_params", f"{what} must be true or false")
        return value
    if kind in ("integer", "number"):
        value = _number(value, what, integer=kind == "integer", kind="invalid_params")
        if "min" in spec and value < spec["min"]:
            raise RecipeError("invalid_params", f"{what} is below the minimum {spec['min']}")
        if "max" in spec and value > spec["max"]:
            raise RecipeError("invalid_params", f"{what} is above the maximum {spec['max']}")
        return value
    if not isinstance(value, str):
        raise RecipeError("invalid_params", f"{what} must be text")
    if len(value) > spec.get("max_length", 200):
        raise RecipeError("invalid_params", f"{what} is longer than {spec.get('max_length', 200)} characters")
    if "enum" in spec and value not in spec["enum"]:
        raise RecipeError("invalid_params", f"{what} must be one of: {', '.join(spec['enum'])}")
    return value


def validate_param_schema(schema: Any) -> List[Dict[str, Any]]:
    """Check the declared parameters of a recipe and return a clean copy."""
    if schema is None:
        return []
    if not isinstance(schema, list) or len(schema) > MAX_PARAMS:
        raise RecipeError("invalid_input", f"params must be a list of at most {MAX_PARAMS} parameter definitions")
    clean: List[Dict[str, Any]] = []
    seen: set = set()
    for i, item in enumerate(schema):
        what = f"params[{i}]"
        if not isinstance(item, dict):
            raise RecipeError("invalid_input", f"{what} must be an object")
        extra = set(item) - _PARAM_KEYS
        if extra:
            raise RecipeError("invalid_input", f"{what} has unknown keys: {', '.join(sorted(extra))}")
        name = item.get("name")
        if not isinstance(name, str) or not _PARAM_NAME.fullmatch(name):
            raise RecipeError("invalid_input", f"{what}.name must be a name of letters, digits and '_' (at most 40)")
        if name in seen:
            raise RecipeError("invalid_input", f"{what}.name '{name}' is declared twice")
        seen.add(name)
        kind = item.get("type")
        if kind not in PARAM_TYPES:
            raise RecipeError("invalid_input", f"{what}.type must be one of: {', '.join(PARAM_TYPES)}")
        spec: Dict[str, Any] = {"name": name, "type": kind, "required": bool(item.get("required", False))}
        if "required" in item and not isinstance(item["required"], bool):
            raise RecipeError("invalid_input", f"{what}.required must be true or false")
        numeric = kind in ("integer", "number")
        if "unit" in item:
            if not numeric or not isinstance(item["unit"], str) or not _UNIT.fullmatch(item["unit"]):
                raise RecipeError("invalid_input", f"{what}.unit is only for numbers and must be a short label such as mm, m or deg")
            spec["unit"] = item["unit"]
        for key in ("min", "max"):
            if key in item:
                if not numeric:
                    raise RecipeError("invalid_input", f"{what}.{key} is only for numbers")
                spec[key] = _number(item[key], f"{what}.{key}", integer=kind == "integer")
        if "min" in spec and "max" in spec and spec["min"] > spec["max"]:
            raise RecipeError("invalid_input", f"{what}: min is above max")
        if "enum" in item:
            values = item["enum"]
            if kind != "string" or not isinstance(values, list) or not 1 <= len(values) <= 50 or not all(isinstance(v, str) and 1 <= len(v) <= 100 for v in values):
                raise RecipeError("invalid_input", f"{what}.enum must be 1 to 50 short texts and only for string parameters")
            spec["enum"] = list(values)
        if "max_length" in item:
            ml = item["max_length"]
            if kind != "string" or isinstance(ml, bool) or not isinstance(ml, int) or not 1 <= ml <= 2000:
                raise RecipeError("invalid_input", f"{what}.max_length must be a whole number from 1 to 2000 and only for string parameters")
            spec["max_length"] = ml
        if "description" in item:
            if not isinstance(item["description"], str) or len(item["description"]) > 200:
                raise RecipeError("invalid_input", f"{what}.description must be text of at most 200 characters")
            spec["description"] = item["description"]
        if "default" in item:
            try:
                spec["default"] = _check_value(spec, item["default"])
            except RecipeError as exc:
                raise RecipeError("invalid_input", f"{what}.default does not fit its own definition ({exc})") from exc
        clean.append(spec)
    return clean


def validate_params(schema: List[Dict[str, Any]], supplied: Any) -> Dict[str, Any]:
    """Return the values a run passes to the script: supplied or default, typed and in range. Raises RecipeError."""
    if supplied is None:
        supplied = {}
    if not isinstance(supplied, dict):
        raise RecipeError("invalid_params", "params must be an object of parameter values")
    known = {spec["name"] for spec in schema}
    unknown = sorted(str(k) for k in supplied if k not in known)
    if unknown:
        raise RecipeError("invalid_params", f"unknown parameter(s): {', '.join(unknown)}. This recipe declares: {', '.join(sorted(known)) or 'none'}")
    values: Dict[str, Any] = {}
    for spec in schema:
        name = spec["name"]
        if name in supplied:
            values[name] = _check_value(spec, supplied[name])
        elif "default" in spec:
            values[name] = spec["default"]
        elif spec.get("required"):
            raise RecipeError("invalid_params", f"params.{name} is required")
    if len(params_json(values).encode("ascii")) > MAX_PARAMS_JSON_BYTES:
        raise RecipeError("invalid_params", f"the parameter values are larger than {MAX_PARAMS_JSON_BYTES} bytes")
    return values


def params_json(values: Dict[str, Any]) -> str:
    """Canonical JSON text of the values (ASCII only), the one string the script receives as PARAMS_JSON."""
    return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


# --------------------------------------------------------------------------- #
# The store
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Recipe:
    id: str
    manifest: Dict[str, Any]
    code: str
    sha256: str
    source: str  # "workspace" or "starter"

    @property
    def version(self) -> int:
        return int(self.manifest["version"])

    @property
    def mode(self) -> str:
        return str(self.manifest["mode"])

    @property
    def params(self) -> List[Dict[str, Any]]:
        return list(self.manifest.get("params") or [])


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_atomic(path: Path, data: bytes) -> None:
    from .approval import replace_with_retry

    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_bytes(data)
        replace_with_retry(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


class RecipeStore:
    def __init__(self, workspace_dir: Any, starter_dir: Optional[Path] = None) -> None:
        self.workspace_dir = Path(workspace_dir)
        self.dir = self.workspace_dir / RECIPES_DIR
        self.standing_dir = self.workspace_dir / "plans" / STANDING_DIR
        self.starter_dir = starter_dir

    # ---- paths -------------------------------------------------------------- #
    def _file(self, root: Path, recipe_id: str, suffix: str) -> Path:
        validate_recipe_id(recipe_id)
        base = root.resolve()
        path = (base / f"{recipe_id}{suffix}").resolve()
        if path.parent != base:
            raise RecipeError("invalid_id", "the recipe path is outside the recipes folder")
        return path

    # ---- reading ------------------------------------------------------------ #
    def _load_from(self, root: Path, recipe_id: str, code_suffix: str, source: str) -> Optional[Recipe]:
        manifest_path = self._file(root, recipe_id, ".json")
        code_path = self._file(root, recipe_id, code_suffix)
        if not manifest_path.is_file() and not code_path.is_file():
            return None
        if not manifest_path.is_file() or not code_path.is_file():
            raise RecipeError("recipe_incomplete", f"recipe '{recipe_id}' is missing its {'manifest' if code_path.is_file() else 'code'} file")
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES or code_path.stat().st_size > MAX_CODE_BYTES * 2:
            raise RecipeError("recipe_too_large", f"recipe '{recipe_id}' is larger than the size limits")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw = code_path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise RecipeError("recipe_unreadable", f"recipe '{recipe_id}' cannot be read: {type(exc).__name__}") from exc
        code = check_code(raw)
        sha = code_sha256(code)
        problems = self._manifest_problems(manifest, recipe_id)
        if problems:
            raise RecipeError("manifest_invalid", f"recipe '{recipe_id}' has an invalid manifest: {problems}")
        if manifest["sha256"] != sha:
            raise RecipeError(
                "hash_mismatch",
                f"recipe '{recipe_id}': the code on disk (sha256 {sha[:12]}...) does not match its manifest ({manifest['sha256'][:12]}...). "
                "It was edited outside revit_recipe_save. Nothing is run; save the recipe again to make the manifest current.",
            )
        return Recipe(recipe_id, manifest, code, sha, source)

    @staticmethod
    def _manifest_problems(manifest: Any, recipe_id: str) -> str:
        if not isinstance(manifest, dict):
            return "not an object"
        if manifest.get("id") != recipe_id:
            return "id does not match the file name"
        version = manifest.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            return "version must be a whole number from 1"
        if manifest.get("mode") not in MODES:
            return "mode must be read or write"
        if not isinstance(manifest.get("sha256"), str) or not SHA_RE.fullmatch(manifest["sha256"]):
            return "sha256 is missing or malformed"
        if not isinstance(manifest.get("title"), str):
            return "title is missing"
        try:
            validate_param_schema(manifest.get("params") or [])
        except RecipeError as exc:
            return f"params: {exc}"
        return ""

    def load(self, recipe_id: Any) -> Recipe:
        """The recipe as it is on disk right now, verified. Raises RecipeError (not_found, hash_mismatch, ...)."""
        validate_recipe_id(recipe_id)
        recipe = self._load_from(self.dir, recipe_id, ".py", "workspace")
        if recipe is None and self.starter_dir is not None:
            recipe = self._load_from(self.starter_dir, recipe_id, ".ipy", "starter")
        if recipe is None:
            raise RecipeError("not_found", f"no recipe '{recipe_id}' (revit_recipe_list shows what exists)")
        return recipe

    def ids(self) -> List[str]:
        found: set = set()
        for root, suffix in ((self.dir, ".py"), (self.starter_dir, ".ipy")):
            if root is not None and root.is_dir():
                for path in root.glob(f"*{suffix}"):
                    if ID_RE.fullmatch(path.stem) and path.stem not in RESERVED_IDS:
                        found.add(path.stem)
        return sorted(found)

    # ---- writing ------------------------------------------------------------ #
    def save(self, recipe_id: Any, *, code: Any, title: Any, description: Any, params: Any, mode: Any) -> Dict[str, Any]:
        """Write code + manifest. Always sets ``approval`` to per_run and removes any standing approval."""
        validate_recipe_id(recipe_id)
        text = check_code(code)
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
            raise RecipeError("invalid_input", "title must be 1 to 120 characters")
        if not isinstance(description, str) or len(description) > 1000:
            raise RecipeError("invalid_input", "description must be text of at most 1000 characters")
        if mode not in MODES:
            raise RecipeError("invalid_input", "mode must be 'read' or 'write'")
        schema = validate_param_schema(params)
        with _LOCK:
            self.dir.mkdir(parents=True, exist_ok=True)
            code_path = self._file(self.dir, recipe_id, ".py")
            manifest_path = self._file(self.dir, recipe_id, ".json")
            existing = code_path.exists() or manifest_path.exists()
            if not existing and len(list(self.dir.glob("*.json"))) >= MAX_RECIPES:
                raise RecipeError("too_many_recipes", f"the workspace already holds {MAX_RECIPES} recipes; delete some first")
            version = 1
            created = _now()
            if manifest_path.is_file():
                try:
                    old = json.loads(manifest_path.read_text(encoding="utf-8"))
                    version = int(old.get("version", 0)) + 1 if isinstance(old, dict) else 1
                    created = str(old.get("created_at") or created) if isinstance(old, dict) else created
                except (OSError, ValueError, TypeError):
                    version = 1
            manifest = {
                "id": recipe_id,
                "version": max(1, version),
                "title": title.strip(),
                "description": description,
                "params": schema,
                "mode": mode,
                "approval": "per_run",
                "sha256": code_sha256(text),
                "created_at": created,
                "updated_at": _now(),
            }
            had_standing = self.revoke_standing(recipe_id)
            # Code first, manifest second: a crash in between leaves a mismatch, which run refuses.
            _write_atomic(code_path, text.encode("utf-8"))
            _write_atomic(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        manifest["standing_reset"] = had_standing
        return manifest

    def delete(self, recipe_id: Any) -> bool:
        """Remove a workspace recipe and its standing approval. A starter recipe cannot be deleted."""
        validate_recipe_id(recipe_id)
        with _LOCK:
            code_path = self._file(self.dir, recipe_id, ".py")
            manifest_path = self._file(self.dir, recipe_id, ".json")
            present = code_path.exists() or manifest_path.exists()
            if not present:
                if self.starter_dir is not None and self._file(self.starter_dir, recipe_id, ".json").exists():
                    raise RecipeError("starter_recipe", f"'{recipe_id}' is a built-in starter recipe and cannot be deleted; save your own with the same id to replace it")
                raise RecipeError("not_found", f"no recipe '{recipe_id}'")
            self.revoke_standing(recipe_id)
            for path in (manifest_path, code_path):
                if path.exists():
                    path.unlink()
        return True

    # ---- standing approvals ------------------------------------------------- #
    def _standing_file(self, recipe_id: str) -> Path:
        return self._file(self.standing_dir, recipe_id, ".json")

    def standing_record(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        try:
            path = self._standing_file(recipe_id)
            if not path.is_file() or path.stat().st_size > 4096:
                return None
            record = json.loads(path.read_text(encoding="utf-8"))
        except (RecipeError, OSError, ValueError):
            return None
        if not isinstance(record, dict) or record.get("id") != recipe_id or not isinstance(record.get("sha256"), str):
            return None
        return record

    def standing_valid(self, recipe: Recipe) -> bool:
        """True while a human-set record names this recipe id and the hash of the code that is on disk now."""
        record = self.standing_record(recipe.id)
        return bool(record) and record["sha256"] == recipe.sha256

    def grant_standing(self, recipe_id: str, sha256: str, approved_by: str) -> Dict[str, Any]:
        """Human only (called by the command-line tool). Refuses unless ``sha256`` is the hash of the code on disk."""
        recipe = self.load(recipe_id)
        if recipe.source != "workspace":
            raise RecipeError("starter_recipe", "starter recipes are read-only and need no approval")
        if recipe.mode != "write":
            raise RecipeError("not_write", "this is a read recipe; it runs without approval when its code passes read mode")
        if sha256 != recipe.sha256:
            raise RecipeError("hash_mismatch", f"--sha256 does not match the code on disk (sha256 {recipe.sha256}). Review the current code and pass its hash.")
        record = {"id": recipe_id, "sha256": recipe.sha256, "version": recipe.version, "approved_by": approved_by, "approved_via": "cli", "approved_at": _now()}
        with _LOCK:
            self.standing_dir.mkdir(parents=True, exist_ok=True)
            _write_atomic(self._standing_file(recipe_id), (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        return record

    def revoke_standing(self, recipe_id: str) -> bool:
        try:
            path = self._standing_file(recipe_id)
        except RecipeError:
            return False
        if path.exists():
            path.unlink()
            return True
        return False

    def record_standing_use(self, recipe: Recipe) -> None:
        """Append who ran what, by hash. Holds no parameter values."""
        try:
            self.standing_dir.mkdir(parents=True, exist_ok=True)
            line = json.dumps({"at": _now(), "id": recipe.id, "version": recipe.version, "sha256": recipe.sha256, "tool": RECIPE_RUN_TOOL})
            with open(self.standing_dir / "uses.jsonl", "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def standing_authorizes(workspace_dir: Any, tool_name: str, arguments: Any) -> Optional[Recipe]:
    """The recipe a standing approval lets this call run, or None. Used by ApprovalGate.claim_action.

    Needs: the run tool, no plan_id (a call with a plan uses the plan), an ``id`` and a ``sha256`` argument equal
    to the hash of the code on disk now, and a human-set record for exactly that id and hash.
    """
    if tool_name != RECIPE_RUN_TOOL or not isinstance(arguments, dict) or arguments.get("plan_id"):
        return None
    sha = arguments.get("sha256")
    if not isinstance(sha, str):
        return None
    try:
        store = RecipeStore(workspace_dir, starter_dir=None)
        recipe = store.load(arguments.get("id"))
    except RecipeError:
        return None
    if recipe.source != "workspace" or recipe.sha256 != sha or not store.standing_valid(recipe):
        return None
    return recipe
