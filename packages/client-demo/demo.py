"""Simple MCP client that exercises the Revit bridge HTTP endpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import httpx

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "examples" / "revit-mcp-config.json"


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def send_tool(base_url: str, tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    with httpx.Client(base_url=base_url.rstrip("/")) as client:
        response = client.post("/", json={"tool": tool, "payload": payload}, timeout=10.0)
        response.raise_for_status()
        return response.json()


def run_demo(config_path: Path, tools: List[str]) -> None:
    cfg = load_config(config_path)
    bridge_url = cfg.get("bridge_url") or "http://localhost:3000"
    workspace_dir = Path(cfg.get("workspace_dir", "."))
    workspace_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running demo against {bridge_url}, workspace {workspace_dir}")
    for tool in tools:
        payload = {"request_id": tool, "workspace_dir": str(workspace_dir)}
        if tool == "revit.open_document":
            payload["file_path"] = str(workspace_dir / "demo.rvt")
        if tool.endswith("export_quantities"):
            payload["output_path"] = str(workspace_dir / "quantities.json")
        print(f"-> calling {tool}")
        result = send_tool(bridge_url, tool, payload)
        print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo MCP client for Revit bridge")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to the example MCP configuration file",
    )
    parser.add_argument(
        "--tools",
        nargs="+",
        default=["revit.health", "revit.open_document", "revit.export_quantities"],
        help="List of tools to invoke",
    )
    args = parser.parse_args()
    run_demo(args.config, args.tools)


if __name__ == "__main__":
    main()
