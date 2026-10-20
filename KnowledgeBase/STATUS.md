# Delivery status — 2026-10-20, continued implementation

## Implemented and verified

- **Home is a dashboard**, with Agents, Teams, Tools, Skills, MCP Connections and Watch & run cards, counts, a short explanation and next steps. The approved team visualization now lives in Watch & run. Existing layout, art, mascot, WABIX logo and palette are preserved.
- **Real AI is the primary flow.** Disconnected Home automatically opens Connection setup. Backend provider access checks are required; stored keys/tokens do not imply a successful connection. A failed real run cannot fall back to samples.
- **Automatic execution via server-sent events.** No Next clicks are required for real AI. The explicit educational sample option retains its separate deterministic lesson and clearly labeled sample counts.
- **Six separate agent-editor steps:** Identity (character/name/role), Job (goal through expected result), Model & settings (provider model dropdown and remaining settings), Tools, Skills, MCPs. [Runtime mapping](AGENT_PROFILES.md).
- **Per-agent model selection** with a separate LLM adapter per helper. Heterogeneous ChatGPT/API connections and different model names are respected; global connection settings do not override agent models. Optional unsupported model parameters produce errors, never silent substitution.
- **Selectable approved avatars** (Researcher, Writer, Reviewer, Robot) persist and render in editor, catalog and execution cards. No new unseen character asset is claimed.
- **Persistent migration**, preserving ids, jobs→goals, team membership, existing permissions and saved runs. SQLite remains the data store. New installations are empty; examples load only after an explicit action and merge without overwriting own helpers. Original bundled configs are labeled examples.
- **External HTTP MCP management:** create/edit/remove connection, Bearer or custom-header credential, initialize and paginated tools/list, individual tool grants per agent, real schema-validated tools/call through CrewAI. Edits, changed tool definitions and removals revoke affected permissions. [Behavior and security boundaries](EXTERNAL_MCP.md).
- Import setup / Export setup retained; declarative skill import retained. Imported MCP metadata cannot register new servers or override registered endpoints. Credentials remain local and outside logs/Git/exports.

## Verification evidence

**27 automated tests passed** (final run: 7.030 seconds). Tests distinguish three evidence categories:

1. **Real MCP transport:** separate authenticated Streamable HTTP server process with a generated fixture credential; Bearer and custom-header discovery, actual tool calls, optional/nested schema handling, denied grants, changed revisions, edit/remove revocation and HTTP API management round-trip. Actual CrewAI calls an external fixture MCP tool using a scripted LLM. No Brain Mentoria AI credential was used.
2. **Real application and framework path with a controlled provider:** HTTP configuration → backend access check → actual CrewAI tasks → local Responses SSE endpoint → application SSE events → persisted results. Two agents select model-alpha and model-beta; requests preserve those model choices. Completion occurs without Next actions. Fixture usage values remain test data, not live external usage.
3. **Contract/data/UI checks:** signed OAuth identity validation, PKCE/state isolation, incomplete registration retention, profile migration/round-trip, framework field mapping, per-agent ChatGPT/API selection, declarative import/permission restrictions, arithmetic restrictions and builtin MCP stdio. Browser checks confirm disconnected setup modal, dashboard navigation, separate editor panels and unsaved selections surviving step changes. Screenshots are under design/.

Python 3.12.9, macOS Apple Silicon. Ruff and JavaScript syntax checks pass. [Evidence record](evidence/verification.txt).

## OAuth and external inference boundary

Reviewed the official request contract again. Fixed the invalid_grant retry edge case so an issued client id is retained as an **incomplete registration**, without claiming connection. No configuration error was found that establishes the cause of the previously observed HTTP 403 browser challenge. [Review and human verification steps](OAUTH_REVIEW.md).

The automated browser received HTTP 403 before consent. At the earlier delivery, OpenAI consent, token exchange, refresh, account model listing and external AI inference had not been confirmed. The later catalog check is recorded below. No own API credential was supplied. Controlled/scripted tests do not change that status. The application requires provider-verified access for real execution; the connection state observed in the latest UI check is recorded below.

## Remaining work

- Human sign-in in a regular browser and a live one-helper/team run with the actual authorized account; verify provider usage and selected real tools. Alternatively, deliberately configure a compatible API provider locally and choose each agent's model.
- Legacy HTTP+SSE MCP transport and remote MCP OAuth, multiple ChatGPT registrations / multiple API credential profiles, arbitrary executable plugins, an encrypted vault, cancellation, durable in-flight recovery and public multi-user hosting are not implemented.
- Completed runs persist. A server restart interrupts in-flight work. Local credential protection uses OS permissions, not encryption.

No public deployment. Commits and push are reported in the delivery message and repository history.

## Profile step refinement

The original Profile step is now split into three visible panels, followed by Tools, Skills and MCPs. Back/Next and direct step navigation retain unsaved name, avatar, job and model values. Model discovery runs automatically in step 3 and on connection changes; it populates a real select control. JavaScript syntax and browser checks passed. Existing backend/runtime mappings were unchanged by this UI revision.

During this verification, the existing ChatGPT connection reported provider-verified access and its model catalog returned **7 available models**. This supersedes the earlier delivery's unverified model-list status. This UI task did not perform a new sign-in, inspect credential contents, or execute external inference. No user agent data was changed by the browser checks (the editor was closed without saving).
