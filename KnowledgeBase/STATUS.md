# Delivery status — 2026-10-20, continued implementation

## Latest: working native ChatGPT images and chat attachments

The prior claim that all image generation required an API key was too broad. The subscription-sharing Responses endpoint still rejects hosted image_generation, but the official native ChatGPT/Codex runtime supports image generation with ChatGPT plan usage. `native_images.ChatGPTImageRuntime` now powers image-enabled ChatGPT agents through an independently authenticated, private AgentSim image session. No other application's credential cache was copied. No image API key was supplied. The Tools image form now leads with native ChatGPT sign-in/status; an API provider is optional.

Live verification completed inside the actual application's Billy chat: execution `c87731eb-adc2-4b48-bcb2-b5f148667f10`, 17 public events from 21:54:10–21:54:57, successful native image tool invocation, actual validated PNG stored and served from the artifact route, final assistant reply with the image visible in chat. The browser decoded the image at 1145×1374. The right-hand inspect displays `native_images.ChatGPTImageRuntime` and `Local Codex CLI → ChatGPT native image service`. This is actual external inference with the owner's account, not a fixture. Proof: `design/native-chatgpt-image-chat.png`.

Image-enabled ChatGPT agents now use proper Responses function schemas/calls/results, executed by CrewAI. Explicit image creation requires the granted function to run before a final answer. A real artifact guardrail rejects text-only generation claims. This also corrects a separately observed Billy run that claimed an image existed without any tool invocation. Historical records were preserved; the new successful run contains the actual image.

Images, PDF document attachments and interactive/PNG/SVG chart outputs render within the assistant message, with open/download controls, as well as execution/history evidence. Files can appear while the turn finishes. Conversation messages persist their artifact metadata and older chats hydrate it from saved executions. PDF file cards open the actual PDF rather than displaying a blank embedded viewer in browsers lacking inline PDF support.

Verification: **46 tests passed in 20.975 seconds**, including native runtime routing/output validation, rejection of stale files, private event/credential environment isolation, strict actual-image checks, structured function-call round trip and a full PDF/Plotly application run persisting its four real artifacts into the assistant message. Ruff, JavaScript syntax and whitespace checks pass. A separate controlled-provider browser run also verified four actual in-chat attachments (PDF, interactive HTML chart, PNG, SVG) with open/download links; proof: `design/pdf-chart-chat-fixture.png`. The real local server and current user tab are updated. No public deployment.

The native runtime uses the installed official Codex CLI with shell/unified execution and web search disabled, workspace-write sandboxing, private file-backed auth/config and bounded generation time. Native image model ids are selected by the runtime and are not fabricated in public evidence. [Current harness behavior](HARNESS_INTEGRATIONS.md). Earlier sections are historical and their image API-key-only limitations are superseded by this section.

## Latest: explicit targets, conversational execution and side-by-side inspection

Watch & run now always uses connected AI models. Removed the Real AI / Educational samples selector, the Home educational entry point and the active sample-run API. Historic sample records remain identifiable. Choose Team or One agent first, then explicitly select the target. One-agent calls resolve any saved agent directly, including an agent outside every team, rather than the first team member.

A persistent chat opens on the left; each message starts an automatic execution on the right. The chat and evidence panels scroll independently. Every message can reopen its own trace; the execution selector can inspect earlier turns. Existing public class/location/explanation, skill choice/reason, tool outputs, generated files and activity pulses remain. Live updates preserve open step inspectors, manual evidence scrolling and composer focus rather than recreating the entire page.

SQLite conversations store user/assistant messages and their run ids. Follow-up tasks receive server-loaded public conversation context, for both single agents and team managers. Target/history overrides from clients are ignored. Saved chats and reload restore conversation/results; running jobs can reconnect to SSE. Failed, rejected and interrupted turns are persisted, with idempotent recovery. [API and context boundaries](CHAT_EXECUTION.md).

Verification: 41 tests pass (21.036 seconds), including explicit non-first agent with no teams, selection of a second team and its actual manager, multi-turn context reaching the actual Responses request, ignored client history/target injection, persisted chat/job reload, rejected turns and restart interruption without duplicate replies. Ruff, JavaScript syntax and whitespace checks pass. Controlled local-provider browser verification covered Team chat → skill selection/delegation → actual PDF/Plotly generation → reply, follow-up message, per-message execution selection, reload and a separate Writer chat with only Writer running. This is controlled inference evidence, not a new live external account run.

The actual port8080 server and user's in-app tab were updated. One agent lists all four currently saved agents, including Billy; Billy's empty chat was opened and is ready for the user's message. No user profile, team, grant or credential was edited and no message/inference was sent on the user's behalf. Proof: design/chat-billy.png (actual app) and design/chat-execution-fixture.png (controlled execution). Earlier sections describe prior revisions.

## Latest: integration harness, skills, plugins and execution history

Implemented the requested Web Research, PDF Generator, Image Generator adapter and Plotly Chart Generator alongside Calculator. Generated files appear in Watch & run and persistent Execution history, with preview/open/download links. Plotly creates self-contained interactive HTML, 3200x2000 PNG and SVG; PDF uses ReportLab. The image adapter has its own dynamically loaded image-model configuration and protected API key, preserving agents' existing ChatGPT account.

Skills accept Codex-style SKILL.md with YAML name/description and Markdown instructions. View and Remove are available. The manager sees registered skill descriptions and can choose a relevant skill for itself or a team member. Actual skill selection, public reason and application are separate visible events; skills never grant tool permissions.

MCP Connections accepts plugin ZIP and access key, inspects `.mcp.json`/`mcp.json`, shows destinations and packaged entry-point source, imports packaged skills and automatically discovers tools. Supported transports are Streamable HTTP and explicitly trusted packaged Python/Node stdio entry points. This is a documented manifest contract, not an arbitrary installer. ZIP traversal/symlinks/embedded manifest credentials are rejected; imported tools start ungranted. A working example ZIP is downloadable from the form.

Every public execution event is numbered and persisted with timestamp, actor, model where applicable, explanation, execution location and implementation class/function. History includes completed, failed, rejected and interrupted runs; restart preserves evidence and marks running jobs interrupted, without resuming. No hidden model thoughts or credentials are exposed. [Class mapping, extension contract and plugin/skill schemas](HARNESS_INTEGRATIONS.md).

Verification: **38 tests passed in 17.008 seconds**. The suite includes actual ReportLab/Plotly output, real authenticated stdio plugin discovery/call, actual CrewAI manager skill choice and worker instruction application, HTTP Responses → app SSE → persistent history/artifact retrieval, failure/interruption records and empty-terminal streaming regression. Ruff, JavaScript syntax and diff whitespace checks passed. PDF and chart exports were visually inspected. An isolated app on port 8081 verified automatic execution, 33 public events, skill choice, PDF/chart gallery, reload persistence, Markdown upload/view and ZIP import/discovery using disposable fixture credentials. These controlled LLM responses are test evidence, not external inference.

Live provider verification: AgentSim's own authorized ChatGPT account completed Web Research with an actual `web_search_call` and message. Hosted `image_generation` was explicitly rejected by the subscription-sharing service. **Image generation requires the owner to configure an image API key in Tools → Image Generator → Configure image model.** The separate adapter is implemented and tested; no live image API key was supplied. No credentials were borrowed from another application. Both Responses adapters now support completed output items emitted before an empty terminal output list while still requiring terminal completion.

The real server on port 8080 was restarted and the user's existing in-app tab reloaded. Tools shows all five entries; image setup, SKILL.md view/remove, plugin ZIP/key form and Execution history are visible. Existing agent/team configuration was preserved. Proof: `design/harness-tools.png`; controlled execution proof: `design/harness-history-fixture.png`. No public deployment. Earlier sections below are historical and their test counts/external-inference limitations are superseded by this section.

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

**30 automated tests passed** (latest run: 8.413 seconds). Tests distinguish three evidence categories:

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

## Account model selection simplification

Removed the per-agent ChatGPT/API selector. Step 3 resolves the account from Connection setup and automatically loads its catalog, preserving model selection per agent and saved connection metadata for execution. Browser verification found no connection selector, seven actual account models, and selection retained across step changes. Closed the editor without saving user data. JavaScript syntax check and all 27 backend tests passed (6.805 seconds). No external inference performed.

## Manager-led execution, live conversation and architecture

Team configuration now persists a selected manager, with validated membership and at least one worker. Actual CrewAI hierarchical execution lets that manager delegate, ask questions, revisit workers and skip unused agents. Models and tool/MCP grants remain per agent. Existing teams are preserved; the UI requires choosing their manager rather than guessing one. [Execution behavior](ORCHESTRATION.md).

Watch & run displays the fixed roster with actual activity events, pulsing active cards, a waiting status for the delegating manager, a live conversation and a task/result inspector. Repeated worker calls appear as separate completed tasks. Unused agents stay idle. Provider usage sums actual model calls, including repeated manager requests, without double-counting worker usage. Completed conversation events and manager metadata persist with the run. The optional sample lesson remains explicitly separate.

Architecture is a new menu item with the actual browser/API/CrewAI/Responses/MCP/SQLite diagram and a selectable saved-team diagram. The approved artwork, logo, colors and overall visual style remain. Only the small header robot was removed. Product labels now use agents instead of helpers.

Verification: all 30 tests pass (8.413 seconds), including actual CrewAI scripted delegation with repeated workers/questions and skipped agents, plus the HTTP Responses/SSE path observing delegation while a job is running and persisting replies/final results. Ruff, JavaScript syntax and diff whitespace checks pass. A separate temporary app on port 8081 with a controlled local provider verified manager waiting, worker active, actual dialogue before completion, idle unused agents, completed replies and no lingering active highlight. Screenshots marked fixture are controlled verification, not live external inference. No external inference was performed with the user's account.

## Dashboard illustration correction

The Home navigation cards were still text-only after the earlier delivery; that visual requirement had been missed. All six now contain visible artwork. Agents and Teams reuse the exact approved character atlas; Watch & run reuses the approved mascot with a play badge. Tools, Skills and MCP Connections use project-local generated illustrations matching the existing palette. The layout, avatar selection, team configuration and current account data are preserved.

Verified in the user's existing in-app browser tab on port 8080, including a reload, screenshot inspection of all six cards, Teams card navigation, manager selector and Architecture diagram. Returned the user's tab to Home without saving any configuration edits. Proof: design/dashboard-illustrated-cards.png. Static PNG MIME type and cache revalidation were corrected so assets are served properly and frontend changes refresh reliably. All 30 tests pass (7.489 seconds), Ruff, JavaScript syntax and diff whitespace checks pass.

## Sidebar order and distinct category illustrations

Moved the existing Welcome to AgentSim card above the navigation menu, removed its old top gap, and made the desktop sidebar scrollable on shorter screens so every menu item remains reachable. The card and current visual style are preserved. Replaced the reused Agents/Teams portraits with two independent project-local illustrations: an AI chip/task composition for Agents and a group collaborating around a table for Teams. Removed the superseded dashboard portrait-composition CSS; execution/editor avatars remain unchanged.

Reloaded and visually verified the user's existing in-app tab: Welcome is first, the menu appears directly below, and both distinct card illustrations load. Screenshot: design/dashboard-sidebar-top.png. No agent/team/account data was changed. JavaScript syntax and diff whitespace checks pass.

Sidebar/card revision regression check: all 30 tests passed in 8.201 seconds.

## Welcome card copy cleanup

Removed the three onboarding steps, the sidebar Connection setup button and the local-data/AI-connection note exactly as requested. The sidebar welcome card retains its approved robot and title, with navigation underneath. Removed the deleted button's JavaScript binding to prevent initialization errors. Account settings remain available in the header.

Verified in the existing user tab after reload: removed copy/button absent, robot/title present, navigation and Architecture still render. JavaScript syntax and diff whitespace checks pass.


## GitHub publication and local-only state — 2026-10-20

Audited all 184 reachable historical Git blobs before this change for OpenAI key patterns and exact credential values from AgentSim's local credential JSON files: no matches. No credential files or SQLite databases are tracked. Existing personal credentials and database remain local so the running installation keeps working. Expanded Git exclusions cover environment variants, common credential JSON names, private key files and SQLite database/journal/WAL variants.

A fresh-install regression check starts with a nonexistent database, creates it through the normal application read path, verifies empty agents/teams/runs/history and verifies no credential directory is created. GitHub distributes source only; execution remains loopback-only and every clone must configure its own account locally.


## Resizable chat and compact execution images — 2026-10-21

Watch & run now starts with a 60/40 chat/execution split. A draggable, keyboard-accessible separator adjusts the chat share from 30% to 75%, persists the browser preference and resets to 60% on double-click. Mobile keeps stacked panels and hides the separator. Execution result images use 112 × 84 px contain-fit thumbnails; chat images retain their larger preview and original Open/Download links.

Verified in the local app using an existing saved conversation: real image loaded at 112 × 84, pointer drag changed the split, ArrowLeft adjusted it, double-click restored 60%, and navigation away/back retained the setting. JavaScript syntax and whitespace checks pass.
