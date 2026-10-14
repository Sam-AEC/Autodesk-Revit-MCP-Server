# ADR 0016: Cerberus, a multi-head read-only model review

Status: on the dev branch, not yet released.

## Status
Proposed. Not accepted. Nothing in this record is built. Only throwaway spikes exist, using fake models and fixture data, outside this repository. One real Claude CLI head ran once on synthetic fixture data (about 14 s, about $0.03).

No part of this product has ever run in a live Revit session, so every claim about Revit behaviour here is UNVERIFIED. Claims about vendor terms, vendor CLIs and library facts carry a grade in "What was and was not verified". Anything marked UNVERIFIED needs a check before it is relied on.

## Context
A coordinator who asks for a full model review today gets one agent that sees about 200 tools. Most of the review checks (naming, sheets and views, model bloat, schedules, clashes, QA/QC rules) are already deterministic Python modules that read a snapshot. They need no model. What a model adds is triage, explanation, fuzzy matching and a second opinion.

The owner asked for a mode, named Cerberus, that combines several agents on one task so they cross-check each other. Different vendors have different strengths and different blind spots. The same model run three times shares one set of blind spots.

Facts from the code that shape the design:

- Every call to live Revit goes through one ExternalEvent queue. Parallel agents calling live Revit just queue and time each other out.
- Each CLI turn starts its own hub process. ADR 0014 problem 4 says such a child process picks "the newest Revit". Several CLI agents could each attach to the wrong Revit.
- The approval gate (ADR 0008) hashes the plan. But `proof.plan_content_hash` covers only `plan_id`, `created_at`, `snapshot_id`, `skipped`, and each action's `action_id`, `tool`, `arguments` and `before`. It does not cover `create_plan(extra=...)`. Reasoning and citations stored in `extra` would show on the approval card without being bound by the plan hash. This is a gap that must be closed before any review proposals ship.
- `revit.extract_snapshot` exists but collects only 9 element classes. It has no types, no warnings, no views except drafting views, no worksets and no CAD, and it has never run in live Revit.

## Decision
Build Cerberus as a review feature on top of our own small harness, not as a general agent framework. The parts below are the proposal.

### 1. What Cerberus is for, and what it is not for
- Cerberus is used only for the full read-only model review over a frozen, hashed snapshot.
- It is never used for writes and never for small questions ("which doors lack a fire rating?" is one tool call).
- **Default Cerberus run:** rules plus one cheap AI head.
- **Council:** 3 heads by default, started only on request. It is meant for high-stakes checks (fire, egress, accessibility, large change sets) or as a second opinion on low-confidence items. The head count is configurable up to a cap of about 5 or 6.
- A head is defined by a **role**, a **tool allowlist** and a **knowledge scope**. It is not defined only by vendor. Two heads may use the same vendor with different roles.
- The voting and citation thresholds in section 4 apply to Council only. A single-head run may not meet them, so it follows the separate limits in section 4.
- Before a run, the panel shows the estimated cost and time, and which vendors receive which data.

| Mode | How it works | Order |
|---|---|---|
| Council (3 heads or more) | All heads attempt the task independently. A deterministic judge (code, not a model) verifies, clusters and ranks | First. This is what the spike tests |
| Relay | Head A drafts, head B reviews A's structured findings, head C attacks them | Later, once Council data shows where errors are |
| Split | Partition the model across heads for speed | Last. It does not cross-check, and plain parallel code is already fast |

### 2. Rules first, AI second
- Existing audit modules produce most findings, exactly and for free. AI heads triage, explain, cross-check and draft fixes.
- Every finding is labelled **Rule** or **AI suggestion**.
- If AI heads add less than 10% accepted findings beyond rules alone, drop them and ship deterministic fan-out only.

### 3. One funnel, heads never write
- Every head, whatever its vendor or surface, reaches model data only through our MCP hub, in a **read-only head profile enforced server-side**: tool allowlist, call budget, full logging. Vendor CLI flags are belt and braces, not the control.
- Heads read a frozen, hashed run bundle. Live Revit is touched only once, serially, to build the bundle. This avoids ExternalEvent contention and wrong-Revit routing for heads.
- Only the coordinator drafts **at most one plan**, through `ApprovalGate.create_plan`. Humans approve. The plan hash binding and the at-most-once (run once) claim rules from ADR 0008 are unchanged.
- **Review plans are refused in `auto` mode.** They are model-proposed.
- **Gap to close before shipping proposals:** add an optional hashed `review` block to the plan content, holding `{run_id, bundle_hash, per-action {finding_id, rule_id, citation}}`. Plans without it keep their current hash. This is a small gate change and needs its own test.
- **Replay and the plan hash.** `create_plan` generates a new `plan_id`, `created_at` and per-action `act_` ids on every call (`security/approval.py`), and `plan_content_hash` hashes all of them (`security/proof.py`). So a replayed run can never reproduce `plan_hash`. Instead, the run log records a separate deterministic **content hash**: the actions' tool and canonical arguments, their before-values, `skipped`, and the `review` block, with generated ids and timestamps excluded. Replay must reproduce that content hash. The real `plan_hash` is recorded for audit and is not compared. (Re-injecting the recorded ids was rejected: it would mean overriding gate-generated values.)

### 4. Verification: disagreement is the signal
Ids, parameters, before-values and evidence call ids must resolve against the bundle and the hub log. Failures go to a "rejected" list and never show as findings. These checks apply to every run.

The voting and citation rules in the table apply to **Council only**.

**What a single-head run may and may not do:**
- Its findings are labelled "AI suggestion, one head". Rule findings keep the "Rule" label.
- Its citations count at most as "needs human review", never as "sourced", because two heads cannot cite them.
- A single-head finding **never enters a plan on its own**. It can enter only if the human explicitly chooses to include it. A Rule finding with a fix template is not affected.
- It never drives a change on a safety-critical item (fire, egress, accessibility). Those need Council.

| Question | Rule |
|---|---|
| Is a clause "sourced"? | Only if it resolves in a local rule pack AND at least 2 heads cite it. One resolving head means "needs human review". No resolution means "no source found", and that finding cannot drive a change |
| When does a change enter the plan? | Only with at least 2 identical votes (same element, parameter, value) and no contrary vote. A majority does not overrule a dissent |
| How is agreement shown? | "Agreed 3/3", "2/3", "1/3". A head that did not answer is shown separately, because silence is not disagreement. Dissenting heads show their reason, escaped and capped at 200 characters |
| What is `rule_id`? | A closed vocabulary built from installed rule packs, plus `other:<text>`. In the real run, free-form names did not cluster across vendors |

Models share training data, so "3/3 agree" is not three independent opinions. Agreement raises confidence. It proves nothing. Only resolution against the snapshot and a rule pack counts as proof.

Heads never see each other's raw output. In Relay, a reviewer sees only structured, verified findings, with free text escaped and capped.

### 5. The arbiter role (optional)
A fast arbiter answers strict yes, no or unsure micro-decisions: are these two findings the same issue (dedupe), does the evidence support the finding, does the citation match the rule, which severity bucket, and is this worth sending to the strong heads (triage).

Candidate: **JEV** from TypeSafe AI, a typed-decision model called "System One". It is early access and cloud-hosted, and all its performance claims come from the vendor or press and are UNVERIFIED (the vendor site was not reachable from the sandbox). The fallback is a deterministic rule or a small local model, and that fallback is the default.

Rules for the arbiter:
- Temperature 0. Run each question twice. If the two runs disagree, the answer is "unsure" and goes to a human.
- Every question and answer is logged.
- **It never decides** approval, plan inclusion, writes, or splits on safety-critical items (fire, egress, accessibility).
- It is dropped from a job if its accuracy is below about 95% on labelled fixture questions.
- A cloud arbiter is off by default, sits behind the per-project vendor allowlist, receives pseudonyms, and needs a terms and data-handling check first.

### 6. Provider adapters and credentials
One `HeadAdapter` interface (build the launch, parse the output, classify errors as rate limit, auth, timeout or error). Four kinds:

| Adapter | Notes |
|---|---|
| Headless vendor CLIs (Claude CLI, Codex CLI, Gemini CLI) | Subprocess in an empty working directory, scrubbed environment, our hub as the only MCP server, built-in tools off, process-tree kill on cancel. Never `--dangerously-skip-permissions` or similar modes |
| Direct API with the user's key | We own the tool loop (extends `agent_native.py`). Usage from the response, price from the user's rate table, no hard-coded prices |
| Local OpenAI-compatible endpoints (Ollama, LM Studio, llama.cpp) | The "local only" head and the outage fallback. Tool calling depends on the model (UNVERIFIED per model) |
| Other MCP-capable apps | A Cerberus head only if the app has a documented headless mode with JSON output. Otherwise it is an interactive client of the hub |

Credential rules:
- **API keys are the shipped default.** Driving a user's own signed-in CLI is opt-in, labelled with that vendor's terms, and off until counsel has reviewed it.
- **We never collect, store or proxy vendor sign-ins.** Anthropic's published terms forbid collecting or intermediating subscription credentials. They say developers building products should use API keys.
- Keys are stored in Windows Credential Manager as a **user-scope secret. Other processes running as the same Windows user can read it.** Credential Manager protects at the Windows-user boundary, not per process. We do not claim the key is hidden from same-user software.
- What the panel hub token does: it stops unauthorised HTTP callers from asking the hub to use a key. That depends on the per-user token in PR #115, which is still open (not merged) at the time of writing. Today `/execute` on the panel hub is unauthenticated (docs/security.md). The token does not protect the stored key itself.
- Residual risk: malware or another tool running as the same user can read the key. Mitigation: separate OS users for sensitive projects, and per-project spend limits set at the vendor. Local-only projects need no key.
- Keys never go into plans, logs, bundles or head environments, except for the one adapter that needs its own.

### 7. Privacy per project
- A per-project vendor allowlist, editable only from the panel. An NDA project means `local` only.
- A **local-only profile**: 2 or 3 local model families plus rules, zero egress. Its quality must be measured, not assumed.
- Project identifiers (title, client and project parameters, person names) become stable pseudonyms before any cloud head sees data. Element UniqueIds are kept, because verification needs them. Mapping back happens locally.
- A "Rules only, no AI" switch gives the full review with no egress.
- Consumer tiers whose terms allow training on user data (for example Gemini personal login) are excluded from client projects by default.
- The pre-run card names every vendor that will receive data.

### 8. State: one SQLite file per project
- WAL mode and FTS5. It holds run logs with exact replay, findings with status history, memory, rule packs and the clause index.
- Vectors (sqlite-vec) only if text search measurably misses on the gold set. Rejected: LanceDB, Chroma, Qdrant local, pgvector.
- **Memory never approves.** It can annotate, demote, or pre-fill a value a current rule already requires. It is untrusted input.
- Replay feeds recorded head outputs to the judge and must reproduce the finding ids and the plan **content hash** (section 3). It does not compare the gate's `plan_hash`, which includes generated ids and timestamps. Replay is refused if the bundle hash differs.

### 9. Knowledge layer
Expert heads come from versioned rule packs with citations, plus retrieval over documents the user owns. Retrieval can explain and cite. It can never be the sole basis of a plan action.

- Every rule carries jurisdiction, edition, effective dates, clause, licence and pack hash.
- **Unknown jurisdiction or edition means fire and accessibility checks do not run.** The progress list says so. No head infers a jurisdiction from the model.
- **An unresolved citation is shown as "no source found" and cannot drive a change.**
- Extracted rules from a client BEP are drafts until a person accepts them.
- Packs are data. They never grant tools or permissions.
- We extend `qaqc_checker` and the rule-pack format instead of building a new engine.

Honesty wording, shown once per report and on code findings:
> "Checked against {pack} ({edition}). This is a model check, not a code compliance determination. Confirm with the authority having jurisdiction or a qualified professional."

### 10. Legal posture for sources
This is not legal advice. Counsel must review before anything is bundled or ingested.

| Source | Position |
|---|---|
| UK Approved Documents | Open Government Licence v3. Bundle text and derived packs with attribution, excluding third-party material. Check each edition's notice |
| Other open sources (for example US ADA Standards, Uniclass, IFC) | Likely allowed, but unconfirmed or with conditions (IFC docs are CC BY-ND, so no modified copies). Legal review first |
| ICC, NFPA, ISO, BSI, CEN | Do not bundle. **Cite by clause number and edition only** |
| ISO | ISO terms forbid AI and machine-learning use without a separate licence. **A user's ISO copy is not indexed by default** |
| Client and firm documents | Local only |

Each document collection gets a policy: `cite_only` (clause number and title, no text sent), `local_model_only` (text may go only to a model on this PC), or `cloud_ok` (the user attests their licence allows it). Default is `cite_only` for standards and `local_model_only` for client documents.

### 11. Panel experience
One "Run full model review" button. A pre-run card, a per-check progress list where partial results stream in and Cancel keeps what finished, one ranked list with agreement badges, and one proposed-changes card. "Cerberus" is the feature name. The UI never says agent, head or token.

## Consequences
Good:
- The part users will value most (many checks, one ranked list, cross-checked) comes mostly from deterministic code, which is cheap and exact.
- Heads get no write tools from the hub, and a CLI head's built-in tools are switched off. That is the design and is enforced server-side for the hub. Whether each vendor CLI honours the switch-off is UNVERIFIED until phase 0. The approval gate stays the only way a change reaches Revit.
- Disagreement becomes visible work for the human instead of a hidden error.
- Per-project vendor control and a local-only profile make the feature usable on NDA projects.

Costs and risks:
- About three times the cost and the slowest head's latency when three heads run. The 3x figure is an estimate, UNVERIFIED until measured with real models.
- Three times the prompt-injection surface, because every head reads untrusted model text and sends it to a different company. Mitigated by no write tools, server-side allowlists, escaped envelopes, schema validation, the verifier, and human approval.
- Three CLIs mean three sets of sign-ins and breaking changes to support.
- A gate change (the hashed `review` block) is needed first, with its own test.
- The knowledge layer needs outside experts and counsel. We cannot ship code-domain checks without them.
- Nothing here is real until the snapshot extractor exists.

## Alternatives considered
| Alternative | Why not |
|---|---|
| One agent with all 200 tools | Pays for the schema every turn, no cross-check. Stays the default for small questions |
| One agent with a curated tool subset | May match Cerberus at lower cost. This is a kill criterion and the spike must test it |
| Adopt an agent framework (LangGraph, OpenAI Agents SDK, Claude Agent SDK, CrewAI, AutoGen, smolagents, Temporal) | Churn, vendor lock-in, a 110 MB bundle, default-on telemetry (CrewAI), model-written code (smolagents, against ADR 0013 rule 6), or a server dependency (Temporal). We borrow patterns instead: checkpoints, event history and replay, guardrails |
| Free-form group chat between heads | Spreads prompt injection from head to head |
| Parallel heads calling live Revit | ExternalEvent serialises them, and the wrong-Revit risk multiplies |
| Vector database first | Not shown to be needed. FTS5 first |
| Ship consumer-CLI scripting as the default | Vendor terms are unclear or restrictive (Anthropic, OpenAI) and counsel has not reviewed it |
| Bundle code and standards text | Copyright, and ISO and NEN explicitly forbid AI use |

## Phases
Effort is in focused days for one engineer. These are estimates.

| Phase | Work | Days |
|---|---|---|
| 0 | Spike. Real Claude CLI, Codex and Gemini or Ollama heads through the real hub in mock mode, on a seeded fixture of about 30 known defects (plus traps). Compare three heads against the best single head. Measure the precision gain against about 3x cost | 5 |
| 1 | Read-only fan-out over snapshots: head manifests, broker, bundle builder, head profile in the hub, progress list, findings store | 12 to 15 |
| 2 | Reconcile and draft one plan: merge, conflicts, ranking, hashed `review` block, proposed-changes card, auto-mode refusal | 10 to 12 |
| C | Adapters (CLI, HTTP, local), hub head profiles, judge UI, per-project allowlist, pseudonyms, Credential Manager keys. Relay mode after that | about 27 to 33 on top of the base harness |
| 3 | Memory and DB consolidation: one project SQLite, status history, rejected-suggestion memory, FTS5 | 8 to 10 |
| K | Knowledge layer: rule pack schema v2, jurisdiction refusal, citation verifier, corpus ingestion, gold sets. Includes an **external domain expert and legal review** phase | about 30 of our days, plus about 15 to 28 expert days and counsel |
| 4 | Optional vectors, only if measured | 5 to 8 |

The base harness is about 1,500 to 2,500 lines of Python (stdlib plus SQLite).

## Kill criteria
Stop or reshape if any of these happen:
- Three heads raise the precision of shown findings by less than 10 points over the best single head, or agreement does not track correctness.
- Counsel rules out scripting consumer CLIs and users refuse to use API keys.
- A single head with a tuned tool subset matches the results.
- No BIM manager or code consultant is available to review the rule packs and gold sets. Then ship without code-domain heads.
- The snapshot extractor slips past a quarter. Then stop, because there is nothing real to review.
- A head keeps a parse failure rate above 10%, or a verifier reject rate above 20%, after prompt and schema work. Drop that head.

## Blockers
- **The add-in snapshot extractor.** It collects only 9 element classes and the repo's own estimate is about 46.6 days to extend it. It has never run in live Revit.
- One live Revit run (snapshot plus an approved write, in Revit 2024 and 2026). **Everything involving live Revit is UNVERIFIED.**
- The hashed `review` block (gate change).
- The panel hub token (PR #115, open) for key storage.
- Counsel review of bring-your-own-CLI.
- Stale-model detection at execute time.

Phase 0 and phase 1 can start on fixtures before the extractor exists. Nothing should be called supported before the live run.

## What was and was not verified
| Item | Status |
|---|---|
| Repo facts (agent bridge, native agent, gate, proof hash, audit modules, snapshot extractor) | Read from `origin/dev` on 2026-10-10. Not run in Revit |
| Anthropic terms on signing in to the unmodified CLI | Read from the official legal page on 2026-10-10 |
| Claude CLI headless flags and JSON output | Official docs plus one real run (version 2.1.296) |
| Codex CLI and Gemini CLI headless behaviour, event names, rate limits | **Not verified.** Their documentation pages were unreachable from the sandbox. Facts come from search snippets and secondary sources. Per-run tool filtering and structured-output flags are UNVERIFIED |
| OpenAI and Google consumer-terms positions | Secondary sources. Grey, UNVERIFIED |
| JEV / System One (launch, price, speed claims) | Press only, UNVERIFIED firsthand |
| Library versions, licences and wheel sizes | PyPI API, 2026-10-10 |
| Local embedding model sizes | **From memory, UNVERIFIED** (model hosting site blocked) |
| FTS5 in every Windows Python build | Probe at runtime. Passed in the sandbox only |
| Legal statements about ICC, NFPA, ISO, BSI, CEN, ADA, OmniClass, COBie, BCF licences | Mixed grades, several UNVERIFIED. All need counsel |
| Cross-vendor precision gain, 3x cost, arbiter accuracy | **Not measured.** That is the point of phase 0 |

## Open questions
1. Does the phase 0 measurement show a precision gain worth about 3x cost?
2. Which vendors and surfaces must the first release support, and will users supply API keys?
3. Will counsel accept scripting a user's signed-in CLI, per vendor?
4. Does `codex exec` support per-run tool filtering, or must each head profile be a separately registered server?
5. Can the arbiter beat a deterministic rule on dedupe and citation matching, and what are its terms and data handling?
6. Which jurisdiction is first (GB-ENG is the only one with an open source we can bundle), and who is the code consultant?
7. Does the existing QA/QC issue store become the findings store, or is it replaced?
8. Should the hashed `review` block go in as its own small change before this record is accepted?
9. What cap on heads is right in practice (5 or 6)?
10. Who owns the extractor batch, and when?
