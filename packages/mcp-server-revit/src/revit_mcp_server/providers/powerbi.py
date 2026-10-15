import logging
from typing import Any, Dict, List

from ..config import config, BridgeMode
from ..bridge.client import BridgeClient
from ..security.workspace import WorkspaceMonitor
from .base import AECProvider, ProviderTool

logger = logging.getLogger(__name__)

class PowerBIProvider(AECProvider):
    def __init__(
        self,
        workspace: WorkspaceMonitor,
        mode: BridgeMode = config.mode,
        bridge_url: str | None = None,
        bridge_factory=None
    ) -> None:
        self.workspace = workspace
        self.mode = mode
        
        url = bridge_url or "http://127.0.0.1:3006"
        factory = bridge_factory or (lambda u, t=None: BridgeClient(u, token=t))
        self._bridge = factory(url, None)
        self._init_tool_mapping()

    def get_identity(self) -> str:
        return "powerbi"

    def get_capabilities(self) -> List[ProviderTool]:
        return [self._capabilities[0]]

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
        if name != "powerbi_health":
            raise ValueError(f"Tool '{name}' is disabled in health-only mode")
            
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
            "powerbi_health": ("health", lambda args: {}),
            "powerbi_execute_dax": ("execute_dax", lambda args: {
                "query": args.get("query")
            }),
            "powerbi_invoke_method": ("invoke_method", lambda args: {
                "class_name": args.get("class_name"),
                "method_name": args.get("method_name"),
                "arguments": args.get("arguments"),
                "target_id": args.get("target_id")
            }),
            "powerbi_reflect_get": ("reflect_get", lambda args: {
                "target_id": args.get("target_id"),
                "property_name": args.get("property_name")
            }),
            "powerbi_reflect_set": ("reflect_set", lambda args: {
                "target_id": args.get("target_id"),
                "property_name": args.get("property_name"),
                "value": args.get("value")
            }),
        }

    _capabilities = [
        ProviderTool(
            name="powerbi_health", 
            description="Check if Power BI External Tool Bridge is running", 
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        ProviderTool(
            name="powerbi_execute_dax", 
            description="Execute a DAX query against the active Power BI dataset", 
            inputSchema={"type": "object", "properties": {
                "query": {"type": "string", "description": "The DAX query to execute"}
            }, "required": ["query"]}
        ),
        ProviderTool(
            name="powerbi_invoke_method", 
            description="Invoke a C# method in Power BI bridge via reflection", 
            inputSchema={"type": "object", "properties": {
                "class_name": {"type": "string"},
                "method_name": {"type": "string"},
                "arguments": {"type": "array"},
                "target_id": {"type": "string"}
            }, "required": ["class_name", "method_name", "arguments"]}
        ),
        ProviderTool(
            name="powerbi_reflect_get", 
            description="Get a C# property value from a Power BI bridge object via reflection", 
            inputSchema={"type": "object", "properties": {
                "target_id": {"type": "string"},
                "property_name": {"type": "string"}
            }, "required": ["target_id", "property_name"]}
        ),
        ProviderTool(
            name="powerbi_reflect_set", 
            description="Set a C# property value on a Power BI bridge object via reflection", 
            inputSchema={"type": "object", "properties": {
                "target_id": {"type": "string"},
                "property_name": {"type": "string"},
                "value": {}
            }, "required": ["target_id", "property_name", "value"]}
        ),
    ]
