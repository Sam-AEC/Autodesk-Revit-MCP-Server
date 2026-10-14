"""Builds one fully-wired ProviderRegistry with every provider registered.

Shared by mcp_server.py (the stdio MCP server) and panel_server.py (the
panel's local HTTP shim) so both entry points wire providers identically
without duplicating ~60 lines of construction, and so importing one entry
point's module never has the side effect of also constructing the other's
registry.
"""
from __future__ import annotations

import logging
import os

from .config import config
from .providers import (
    ProviderRegistry,
    RevitProvider,
    IfcProvider,
    AECMapperProvider,
    RhinoProvider,
    SemanticGraphProvider,
    SpeckleProvider,
    AutodeskDataProvider,
    JobProvider,
    RevitJobProvider,
    SQLiteExporterProvider,
    McpProxyProvider,
    NavisworksProvider,
    ApprovalProvider,
    ModuleProvider,
    SemanticProvider,
)
from .module_registry import ModuleRegistry
from .security.workspace import WorkspaceMonitor
from .jobs import JobManager

logger = logging.getLogger(__name__)


def build_registry(
    workspace: WorkspaceMonitor | None = None,
) -> tuple[ProviderRegistry, ApprovalProvider, JobManager, ModuleRegistry, WorkspaceMonitor]:
    """Construct one fully-wired ProviderRegistry with every provider registered.

    Each caller gets its own independent instance — that's fine, since
    ApprovalGate persists plans to disk under the shared workspace directory,
    so plans created via one process are still visible to the other.

    `workspace` defaults to the process-wide config's allowed directories;
    pass an explicit WorkspaceMonitor (e.g. over a pytest tmp_path) to keep a
    test's plans/snapshots from being written into a shared directory.
    """
    if workspace is None:
        config.ensure_workspace()  # creates the default workspace on first use only
        workspace = WorkspaceMonitor(config.allowed_directories)

    registry = ProviderRegistry()
    approval_provider = ApprovalProvider(workspace=workspace, registry=registry)
    registry.register(approval_provider)
    revit_provider = RevitProvider(workspace=workspace)
    registry.register(revit_provider)
    revit_provider.approval_state_source = approval_provider.gate.approval_state
    registry.register(IfcProvider(workspace=workspace))
    registry.register(AECMapperProvider(workspace=workspace))
    registry.register(SQLiteExporterProvider(workspace=workspace, registry=registry))
    registry.register(NavisworksProvider(workspace=workspace))
    registry.register(SemanticProvider(workspace=workspace, registry=registry))

    # Initialize and register Module registry and Module provider
    module_registry = ModuleRegistry(config_obj=config)
    module_registry.discover_and_load()
    registry.register(ModuleProvider(module_registry=module_registry, workspace=workspace, tool_registry=registry))

    # Initialize Job Manager and Job Provider
    job_manager = JobManager()
    registry.register(JobProvider(manager=job_manager))
    registry.register(RevitJobProvider(revit=revit_provider, manager=job_manager))

    # Rhino Provider
    try:
        registry.register(RhinoProvider(workspace=workspace))
    except Exception as e:
        logger.warning("Could not initialize RhinoProvider: %s", e)

    # Semantic Graph Provider
    try:
        registry.register(SemanticGraphProvider())
    except Exception as e:
        logger.warning("Could not initialize SemanticGraphProvider: %s", e)

    # Speckle Provider
    try:
        registry.register(SpeckleProvider())
    except Exception as e:
        logger.warning("Could not initialize SpeckleProvider: %s. Please set SPECKLE_CLIENT_ID.", e)

    # Autodesk Data Provider
    try:
        registry.register(AutodeskDataProvider())
    except Exception as e:
        logger.warning("Could not initialize AutodeskDataProvider: %s. Please set APS_CLIENT_ID.", e)

    # Mcp Proxy Providers
    proxy_targets = os.getenv("MCP_PROXY_TARGETS")
    if proxy_targets:
        for target in proxy_targets.split(","):
            target = target.strip()
            if not target:
                continue
            if "=" in target:
                name, url = target.split("=", 1)
                name = name.strip()
                url = url.strip()
                identity = f"proxy_{name}"
            else:
                url = target
                identity = "proxy"

            try:
                registry.register(McpProxyProvider(target_url=url, identity=identity))
            except Exception as e:
                logger.warning("Could not initialize McpProxyProvider for %s: %s", target, e)

    return registry, approval_provider, job_manager, module_registry, workspace
