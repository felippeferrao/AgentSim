# Manager-led teams and live activity

Teams persist an optional `manager` agent id alongside `agents`. The manager must be a member, membership cannot contain duplicates, and a managed team needs at least one other agent. Existing records without a manager are preserved and the UI prompts for one before a team run. New/edited teams require a manager. Import/export round-trips preserve it. Removing a manager or leaving fewer than two members clears the reference. No existing user's manager is guessed.

Managed execution uses the installed CrewAI 1.15.28 `Process.hierarchical`, a custom manager agent and one goal task. The manager's own model, profile, behavior limits and instructions are respected. It can delegate work, ask questions, revisit agents, skip agents or answer directly. Worker routing names include an ordinal, name and role, allowing identical specialties without ambiguous delegation. Membership order is not an execution order. Each worker retains its own model and explicitly granted tools/MCP capabilities.

CrewAI requires the custom manager's initial tools to be empty: the manager coordinates via delegation/question tools, while workers execute ordinary tools and MCPs. The team form explains this. No permissions are auto-granted. Delegated calls execute synchronously in this framework path; the live display does not imply parallel worker execution. Single-agent mode bypasses team management. The backend keeps a legacy sequential path for old integrations; the current team UI requires a manager.

`orchestration.py` subclasses public Agent execution/delegation methods with per-run callbacks, avoiding a global event listener. Activity events include agent start, waiting, resume, failure, completion and model request start. Interaction events contain actual delegation/question payloads, shared context and returned replies. No raw ReAct protocol, Thought fields, hidden reasoning or raw provider delta stream is shown. External MCP arguments/raw results remain excluded from tool telemetry as before.

Public events flow through the existing background-job SSE endpoint. Watch & run renders a fixed roster with actual per-agent activity, an independently scrollable live conversation, and the latest task/result inspector. The active card pulses; reduced-motion preference disables animation and retains a visible highlight. A manager waiting for a delegated response has a separate status; unused agents stay idle even when the goal finishes. Responses appear on actual completion, with activity visible during inference.

Completed task results may include the same worker multiple times. Provider usage is summed across each agent's actual model calls and is not double-counted through the manager's result. Completion includes roster, manager id, orchestration mode and the interaction events in saved runs. Failed work cannot fall back to samples. Educational samples retain their explicitly labeled fixed teaching sequence.

Architecture shows the browser, Python API/background jobs, CrewAI, Responses API, authorized tools/MCPs and SQLite, plus the selected team's saved configuration. That configuration diagram does not claim every agent was used in a run. Live activity is shown in Watch & run.

## Evidence

- Actual CrewAI with a scripted LLM: manager delegates to Writer, asks it a question, delegates a revision, skips Researcher, and combines the responses. Tests verify actual worker execution, ordering, per-agent model usage, manager/worker token aggregation and exclusion of raw private reasoning.
- Actual local HTTP Responses/SSE path: a manager's delegation is observed while the job is still running, then a worker reply and final manager answer complete automatically and persist. Controlled provider counts are not external AI usage.
- A separate temporary application on port 8081, with fixture credentials and a controlled local provider, is used for browser activity checks. It does not use the user's database or account. Screenshots containing fixture text are named watch-managed-fixture-*.png.


## Comic Story Studio preset

The named production crew is specified in `examples/comic-studio/configuration.json`. Its manager coordinates Oliver → Maya → Ethan → Sofia → Noah and may revisit earlier stages for corrections. The runtime verifies actual specialist completions and their latest dependency order; an APPROVED review of superseded material is insufficient. `harness.IntegrationTool` blocks the PDF publisher until approval. Generic user-created teams retain their existing manager-led behavior. See the starter README for responsibilities, tool permissions and reset/seed boundaries.
