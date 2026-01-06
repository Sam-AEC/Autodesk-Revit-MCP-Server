class RevitMCPError(Exception):
    """Base exception for MCP helpers."""


class WorkspaceViolation(RevitMCPError):
    """Raised when a tool targets a path outside the sandbox."""


class SchemaValidationError(RevitMCPError):
    """Presented when inputs fail the declared JSON schema."""


class BridgeError(RevitMCPError):
    """Signals communication or response issues with the bridge."""
