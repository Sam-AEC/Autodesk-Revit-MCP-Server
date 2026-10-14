# Bounded live acceptance harness

This runner implements context/build identity, Python standard-library runtime
checks, T11 read-mode refusal, and the retained-result part of T1. It never edits
model content, saves a document, toggles approval settings, approves a plan or
cleans up existing elements. T2–T10, T12 and T13 remain `UNSUPPORTED`.

Use the project virtual environment with the editable server installed. Pin the
actual Revit process ID, exact document title and its `CreationGUID` from a
trusted `revit_get_context` response. The default is an offline plan:

```powershell
.\.venv\Scripts\python.exe scripts/revit/acceptance/run.py --pid 12345 --expected-document "Acceptance scratch" --expected-guid "00000000-0000-0000-0000-000000000001"
```

Add `--run` to perform live calls. The authenticated panel must be running. The
runner reads the existing per-user panel token using the server's safe reader;
do not pass or print a token. `--hub` accepts only `http://127.0.0.1:<port>`.
Every request carries the explicit PID through the real panel `instance` schema.
Each read script checks the actual executing PID, title and GUID. Context must
be live, idle, supported by the loaded add-in and carry a module/file-time stamp.

Default scope requires a scratch/disposable/test title and rejects Heijmans,
production and workshared documents. When the owner has explicitly designated
the exact existing document for tests, add `--allow-existing-test-document`.
That flag still requires the exact title/GUID/PID and permits no model writes.
Future mutating cases must create uniquely phase-tagged fixtures, record their
new IDs and verify foreign dependencies before deleting only those fixtures.
They are not implemented here.

For T11's no-approval exemption, switch Dev/Auto off yourself and use Ask me
first. No plan is supplied. T11 requires the specific transaction refusal and
unchanged element/warning counts. Under Dev/Auto or Look only it reports
`PARTIAL`, because those modes cannot establish the Ask me first exemption.
Counts and the read runner's zero-change report do not replace a full model diff.

To request T1's 90-second retained-result probe, add `--t1-seconds` (default 90),
or `--t1-seconds 2` for a short smoke probe. This deliberately blocks Revit's UI
thread while sleeping; it cannot be cancelled from the harness. The submit call
uses `revit_execute_python(mode="read")`. Pending output is collected with the
actual `revit_get_result(request_id, wait_s)` interface; the current server has
no `revit_job_status` tool. `--poll-wait` is 0–25 seconds and `--max-wait` caps
the follow-up polling budget (default 120 seconds). A pending receipt is saved
before polling. Never resubmit a timed-out script.

To recover after closing the runner, use the same identity arguments and:

```powershell
--run --resume-request-id "REQUEST_ID_FROM_PENDING_EVIDENCE" --expected-marker "MARKER_FROM_PENDING_EVIDENCE"
```

Resume only collects the earlier result and verifies its identity and marker;
it does not submit a script. Results expire after the loaded add-in's TTL
(normally 15 minutes), and a Revit restart can lose them. Full T1 stays
`PARTIAL`: retrieving and replaying a retained 90-second output does not prove
the separate MCP-client-kill requirement. That subcase is explicitly `NOT_RUN`.

Evidence is bounded, redacted and written exclusively below the ignored
`artifacts/revit-acceptance/` directory. CLI output contains paths and statuses,
never credentials. A zero exit code means this narrow run observed no failure;
it does not mean the full acceptance suite passed. Unit tests use fake
transports, no live calls and no real sleeps:

```powershell
.\.venv\Scripts\python.exe -m pytest -c packages/mcp-server-revit/pyproject.toml packages/mcp-server-revit/tests/test_live_acceptance_harness.py -q
```
