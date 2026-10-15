import logging
from typing import Any, Dict, List
from ..config import config, BridgeMode
from ..bridge.client import BridgeClient
from ..security.workspace import WorkspaceMonitor
from .base import AECProvider, ProviderTool, enrich_mutation_metadata

logger = logging.getLogger(__name__)

class NavisworksProvider(AECProvider):
    def __init__(
        self,
        workspace: WorkspaceMonitor,
        mode: BridgeMode = config.mode,
        bridge_url: str | None = None,
        bridge_factory=None
    ) -> None:
        self.workspace = workspace
        self.mode = mode
        
        url = bridge_url or "http://127.0.0.1:3002"
        factory = bridge_factory or (lambda u, t=None: BridgeClient(u, token=t))
        self._bridge = factory(url, None)
        self._init_tool_mapping()
        self._enrich_tool_metadata()

    def _enrich_tool_metadata(self) -> None:
        mutating_verbs = {"set", "invoke", "delete", "create", "move", "copy", "rotate", "mirror", "run"}
        enrich_mutation_metadata(self._capabilities, mutating_verbs=mutating_verbs)

    def get_identity(self) -> str:
        return "navisworks"

    def get_capabilities(self) -> List[ProviderTool]:
        return self._capabilities

    async def check_health(self) -> Dict[str, Any]:
        if self.mode == BridgeMode.bridge:
            try:
                if hasattr(self._bridge, '_get'):
                    return self._bridge._get("/health")
                return {"status": "healthy", "mode": "bridge"}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)}
        return {"status": "healthy", "mode": "mock"}

    async def shutdown(self) -> None:
        close = getattr(getattr(self, "_bridge", None), "close", None)
        if callable(close):
            close()

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tool_mapping:
            raise ValueError(f"Unknown Navisworks tool '{name}'")
            
        bridge_tool, payload_builder = self._tool_mapping[name]
        payload = payload_builder(arguments)
        
        if "request_id" in arguments and "request_id" not in payload:
            payload["request_id"] = arguments["request_id"]

        if self.mode == BridgeMode.bridge:
            return self._bridge.send_tool(bridge_tool, payload)
        else:
            return {"mock": True, "tool": bridge_tool, "payload": payload}

    def _init_tool_mapping(self):
        self._tool_mapping = {
            "navisworks_health": ("navisworks.health", lambda args: {}),
            "navisworks_get_document_info": ("navis.get_document_info", lambda args: {}),
            "navisworks_get_model_tree": ("navis.get_model_tree", lambda args: {
                "max_depth": args.get("max_depth", 2)
            }),
            "navisworks_get_selection": ("navis.get_selection", lambda args: {}),
            "navisworks_append_file": ("navis.append_file", lambda args: {
                "path": args.get("path")
            }),
            "navisworks_refresh": ("navis.refresh", lambda args: {}),
            "navisworks_list_viewpoints": ("navis.list_viewpoints", lambda args: {}),
            "navisworks_create_viewpoint": ("navis.create_viewpoint", lambda args: {
                "name": args.get("name", "New Viewpoint")
            }),
            "navisworks_activate_viewpoint": ("navis.activate_viewpoint", lambda args: {
                "guid": args.get("guid")
            }),
            "navisworks_list_clash_tests": ("navis.list_clash_tests", lambda args: {}),
            "navisworks_run_clash_test": ("navis.run_clash_test", lambda args: {
                "guid": args.get("guid")
            }),
            "navisworks_get_clash_results": ("navis.get_clash_results", lambda args: {
                "guid": args.get("guid"),
                "skip": args.get("skip", 0),
                "limit": args.get("limit", 50)
            }),
            "navisworks_invoke_method": ("navis.invoke_method", lambda args: {
                "class_name": args.get("class_name"),
                "method_name": args.get("method_name"),
                "arguments": args.get("arguments"),
                "target_id": args.get("target_id")
            }),
            "navisworks_reflect_get": ("navis.reflect_get", lambda args: {
                "target_id": args.get("target_id"),
                "property_name": args.get("property_name")
            }),
            "navisworks_reflect_set": ("navis.reflect_set", lambda args: {
                "target_id": args.get("target_id"),
                "property_name": args.get("property_name"),
                "value": args.get("value")
            }),
        }

    _capabilities = [
        ProviderTool(name="navisworks_health", description="Check if Navisworks is running and get status information", inputSchema={"type": "object", "properties": {}, "required": []}),
        ProviderTool(name="navisworks_get_document_info", description="Get info about the active Navisworks document", inputSchema={"type": "object", "properties": {}, "required": []}),
        ProviderTool(name="navisworks_get_model_tree", description="Get the model hierarchy tree in Navisworks", inputSchema={"type": "object", "properties": {"max_depth": {"type": "integer", "default": 2}}, "required": []}),
        ProviderTool(name="navisworks_get_selection", description="Get active selection items in Navisworks", inputSchema={"type": "object", "properties": {}, "required": []}),
        ProviderTool(name="navisworks_append_file", description="Append a file (e.g. NWD, NWG, IFC) to the active document", inputSchema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
        ProviderTool(name="navisworks_refresh", description="Refresh all updated files in the active document", inputSchema={"type": "object", "properties": {}, "required": []}),
        ProviderTool(name="navisworks_list_viewpoints", description="List saved viewpoints", inputSchema={"type": "object", "properties": {}, "required": []}),
        ProviderTool(name="navisworks_create_viewpoint", description="Create a new saved viewpoint from the current view", inputSchema={"type": "object", "properties": {"name": {"type": "string", "default": "New Viewpoint"}}, "required": []}),
        ProviderTool(name="navisworks_activate_viewpoint", description="Activate a saved viewpoint by Guid", inputSchema={"type": "object", "properties": {"guid": {"type": "string"}}, "required": ["guid"]}),
        ProviderTool(name="navisworks_list_clash_tests", description="List clash tests defined in Clash Detective", inputSchema={"type": "object", "properties": {}, "required": []}),
        ProviderTool(name="navisworks_run_clash_test", description="Run a clash test by Guid", inputSchema={"type": "object", "properties": {"guid": {"type": "string"}}, "required": ["guid"]}),
        ProviderTool(name="navisworks_get_clash_results", description="Get results for a clash test by Guid", inputSchema={"type": "object", "properties": {"guid": {"type": "string"}, "skip": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 50}}, "required": ["guid"]}),
        ProviderTool(name="navisworks_invoke_method", description="Invoke a C# method in Navisworks via reflection", inputSchema={"type": "object", "properties": {"class_name": {"type": "string"}, "method_name": {"type": "string"}, "arguments": {"type": "array"}, "target_id": {"type": "string"}}, "required": ["class_name", "method_name", "arguments"]}),
        ProviderTool(name="navisworks_reflect_get", description="Get a C# property value from a Navisworks object via reflection", inputSchema={"type": "object", "properties": {"target_id": {"type": "string"}, "property_name": {"type": "string"}}, "required": ["target_id", "property_name"]}),
        ProviderTool(name="navisworks_reflect_set", description="Set a C# property value on a Navisworks object via reflection", inputSchema={"type": "object", "properties": {"target_id": {"type": "string"}, "property_name": {"type": "string"}, "value": {}}, "required": ["target_id", "property_name", "value"]})
    ]
