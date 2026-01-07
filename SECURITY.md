# Security Policy

## Supported Versions

We actively support and provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | ✅ Active support  |
| < 1.0   | ❌ Not supported   |

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

✅ **Keep localhost-only** - Never bind to `0.0.0.0` without enterprise hardening
✅ **Update regularly** - Apply security patches within 30 days
✅ **Enable audit logs** - Monitor `%APPDATA%\RevitMCP\Logs\bridge.jsonl`
✅ **Workspace sandboxing** - Only allow trusted project directories
✅ **Enterprise mode** - Follow [docs/security.md](docs/security.md) for HTTPS/OAuth

### For Developers

✅ **Input validation** - All inputs validated against schemas
✅ **No secrets in code** - Use environment variables
✅ **Least privilege** - No privilege elevation
✅ **Exception handling** - Sanitize before returning to client

## Security Hardening Checklist

Before production deployment:

- [ ] Bridge binds to `127.0.0.1` only
- [ ] Workspace directories limited
- [ ] Audit logging enabled
- [ ] HTTPS configured (if remote access)
- [ ] OAuth2 enabled (if external clients)
- [ ] Rate limiting configured
- [ ] Security reviews scheduled

Full guide: [docs/security.md](docs/security.md)

---

**Last Updated**: 2026-01-07
