# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability in MCP Revit Bridge, please report it responsibly.

### How to Report

**Do not open a public issue.** Instead, email security details to the maintainers or use GitHub's private security advisory feature:

1. Navigate to the repository's Security tab
2. Click "Report a vulnerability"
3. Provide detailed information about the vulnerability

Include in your report:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### What to Expect

- Acknowledgment within 48 hours
- Assessment and triage within 7 days
- Regular updates on remediation progress
- Credit in release notes (unless you prefer to remain anonymous)

### Security Best Practices

When using MCP Revit Bridge:

1. **Workspace Isolation**: Always configure `WORKSPACE_DIR` and `MCP_REVIT_ALLOWED_DIRECTORIES` to restrict file access
2. **Network Boundaries**: The bridge runs on localhost only (127.0.0.1:3000) - do not expose to external networks
3. **Input Validation**: All tool inputs are validated against JSON schemas, but review custom configurations carefully
4. **Audit Logs**: Enable and monitor audit logs for unexpected tool usage
5. **Mock Mode Testing**: Use mock mode in CI/CD pipelines to avoid exposing production Revit environments
6. **Least Privilege**: Run the bridge with minimal Windows permissions required for Revit operations

### Known Limitations

- The bridge HTTP listener does not implement authentication (localhost-only by design)
- File operations are restricted to allowed directories but rely on OS permissions
- Revit API operations inherit Revit's security model and limitations
