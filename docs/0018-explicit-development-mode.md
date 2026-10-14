# ADR 0018: Explicit development mode in the Revit panel

## Status

Implemented in source; deployment and live Revit acceptance are pending.

## Context

The owner decisions in [the upgrade plan, section 13](upgrade-plan-hands-and-eyes.md#13-owner-decisions-2026-10-14-and-resulting-priorities) request a development mode that remains on until the person switches it off. Timed Auto already supports temporary unplanned writes, but its expiry is unsuitable for a sustained development session.

The default remains Ask first. [ADR 0008](0008-approval-gate-lifecycle.md) describes plan approval; [ADR 0017](0017-approval-document-binding-and-expiry.md) remains a separate proposal. Development mode does not implement document binding or approval expiry.

## Decision

- A person selects Dev in the panel Settings and confirms it. The existing authenticated `POST /approval-mode` accepts `{"mode":"dev","confirm":true}`. No MCP tool enables it.
- The hub stores a separate HMAC-signed `.dev-mode.json` in the workspace, using the panel token outside that workspace. It must match an owner-only nonce authority beside the token. Off revokes that authority before clearing the workspace record; restoring an old signed record cannot re-enable Dev. Processes sharing the workspace observe the same switch. There is no timer or document binding; a restart does not switch Dev off. Invalid, unsigned, revoked or unreadable records are ignored.
- Dev permits unplanned writes. A supplied plan id still passes hash and single-use checks. Baseline Look only always takes precedence.
- Diagnostics and `revit_get_context` expose `dev_mode: true`, effective `approval_mode: "auto"` and no Auto expiry. The panel labels this state Dev and displays that it remains on until switched off.
- Selecting Ask first clears both overrides. Selecting timed Auto clears Dev and creates the existing expiring Auto window. Clearing an override restores the process's configured baseline; it cannot override an environment configured as Auto or Look only.
- Mode changes and calls made in Dev are audited with existing secret and path redaction. Failure to write a Dev audit record refuses the call. Loopback, Host/Origin checks, panel tokens, plan hashes and Python read-mode safeguards remain enforced.
- This implementation does not relax the workspace sandbox or path masking. Optional extra-folder access and exposing paths require a separate explicit control and tests; selecting Dev alone does not grant them.

## Consequences

Dev persists across process restarts and applies to all clients sharing the workspace. The panel must make that state visible, and its off control must remain available. The token establishes a local-user boundary, not proof of a person's presence; see [security](security.md).

Source tests and a Revit 2024 build verify the implementation before delivery. The installed add-in must be updated with the complete output folder, then checked using `revit_get_context`. Any mutating acceptance test runs only on an owner-opened scratch model, as specified in the upgrade plan.
