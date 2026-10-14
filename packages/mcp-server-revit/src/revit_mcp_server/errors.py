class RevitMCPError(Exception):
    """Base exception for MCP helpers."""


class WorkspaceViolation(RevitMCPError):
    """Raised when a tool targets a path outside the sandbox."""


class SchemaValidationError(RevitMCPError):
    """Presented when inputs fail the declared JSON schema."""


class BridgeError(RevitMCPError):
    """Signals communication or response issues with the bridge."""


class CommandFailed(BridgeError):
    """Revit ran the command and it failed (as opposed to a lost connection or an expired id).

    Only this error settles an in-flight approved action as failed; the others leave the outcome unknown."""
