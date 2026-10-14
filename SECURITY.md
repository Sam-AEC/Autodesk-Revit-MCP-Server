# Security Policy

## Supported Versions

We actively support and provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | Supported          |
| < 1.0   | Not supported      |

Security fixes go into the latest 1.x release. For the Revit and Python versions that are built and tested, see the table below and the [deprecation policy](docs/deprecation-policy.md).

| Component | Supported | Notes |
| --------- | --------- | ----- |
| Revit | 2024, 2025, 2026, 2027 | Built in CI for every year |
| Python | 3.11, 3.12, 3.13 | Tested on Windows in CI. Linux (3.12) is experimental. |

## Reporting a Vulnerability

**DO NOT** open public GitHub issues for security vulnerabilities.

### Where to Report

Use GitHub's private security advisory feature:

1. Navigate to the repository's **Security** tab
2. Click **"Report a vulnerability"**
3. Provide detailed information

### What to Include

- **Description**: Clear description of the vulnerability
- **Steps to Reproduce**: Detailed steps to demonstrate the issue
- **Impact Assessment**: What an attacker could achieve
- **Affected Versions**: Which versions are vulnerable
- **Suggested Fix** (optional): Your recommendations

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Triage**: Within 7 days
- **Fix Development**:
  - **Critical**: Within 7 days
  - **High**: Within 30 days
  - **Medium**: Within 90 days

### Disclosure Policy

We follow **coordinated disclosure**:
1. Private report received
2. Fix developed and tested
3. Patched version released
4. Public disclosure after 30 days

## Security Best Practices

### For Users

- **Keep the bridges on localhost.** They bind to `127.0.0.1` only. Do not expose them through a reverse proxy or port forward. There is no HTTPS, OAuth or rate limiting on the local bridges; they rely on the localhost boundary and, in the default Revit mode, a session token (see [docs/security.md](docs/security.md)).
- **Keep approval on.** Leave `MCP_REVIT_APPROVAL_MODE` at its default (`required`). Setting `auto` turns the approval check off.
- **Limit the workspace.** Set `MCP_REVIT_WORKSPACE_DIR` and `MCP_REVIT_ALLOWED_DIRECTORIES` to the folders you need.
- **Check the logs.** The server writes `audit.log` (see [docs/logging-and-audit.md](docs/logging-and-audit.md)) and the Revit add-in writes `%APPDATA%\AECModelBridge\Logs\bridge.jsonl`. Restrict access to both.
- **Update regularly.** Apply security releases within 30 days.
- **Do not give an AI client a shell on the account you approve plans with.** The panel authenticates a local process, not a person.

### For Developers

- Tool arguments are validated against schemas before they reach a provider.
- Keep secrets out of code; use environment variables or a keyring.
- Audit entries and tool responses are redacted for secrets and local paths.

## Hardening Checklist

Before relying on a deployment:

- [ ] Bridges bind to `127.0.0.1` only and are not behind a port forward
- [ ] Workspace directories are limited to the folders you need
- [ ] `MCP_REVIT_APPROVAL_MODE` is not `auto`
- [ ] Access to `audit.log` and `bridge.jsonl` is restricted
- [ ] No AI client has a shell on the account used to approve plans

The dev build passed scoped read-only smoke checks in Revit 2024; model writes, rollback and export acceptance remain pending. See the [live-validation report](docs/revit-addin-live-validation-2026-10-14.md) and [release checklist](docs/release-checklist.md).

Full guide: [docs/security.md](docs/security.md)
