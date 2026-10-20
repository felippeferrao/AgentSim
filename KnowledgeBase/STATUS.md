# Delivery status — 2026-10-20

## Implemented

- WABIX AgentSim UI with approved mascot/helper artwork, official WABIX logo, light/navy palette and teal/orange/purple accents. Desktop composition preserved; smaller screens stack panels/cards.
- Persistent agent/team create, read, update and delete; explicit tool/skill/MCP grants, individual MCP tool selection. SQLite stores configuration and completed run history.
- Declarative setup import/export and skill JSON import with server-side validation. Skill instructions applied to real agent/task prompts. Missing dependencies fail rather than granting tools.
- Deterministic guided Demo, step inspector, timeline, sample counts and saved-run comparison for one helper versus a team.
- Actual CrewAI 1.15.28 sequential Agent/Task/Crew implementation, automatic real execution, background step/tool/usage events and completed-output persistence. Responses streaming adapter with terminal-event checks and provider-only usage counts.
- Restricted real arithmetic tool and actual MCP stdio documents server with discovery/search/read. No arbitrary plugin execution.
- Own dynamic ChatGPT OAuth authorization, callback exchange, signed ID-token validation, scope checks, refresh and protected local persistence. Model listing and explicit alternative API provider configuration. No reuse of Cortex/Codex credentials.

## Verified evidence

- **10 automated tests pass** on Python 3.12.9, macOS Apple Silicon. [Test record](evidence/verification.txt).
- Real CrewAI is invoked in the tests, with a scripted provider. Three tasks pass outputs sequentially; calculator and documents-search are actually executed by CrewAI. Skill instructions are present. **The provider is scripted in this test; this is not external inference.**
- MCP initialize/list_tools/read/search tested through real subprocess pipes. The web endpoint also completed actual MCP discovery.
- Local HTTP/SSE fixture validates outgoing Responses store=false/stream=true, successful terminal-event handling and provider usage mapping. Fixture counts are not live provider counts.
- OAuth fixture signs an ID token using a freshly generated RSA key and verifies identity, audience/client binding and protected persistence. State, PKCE, stable independent host id, denial and one-time callback rejection are tested. This is a contract/security test, not a live OpenAI token exchange.
- Actual HTTP create/read/update/delete of agent/team setup, explicit granular assignments, invalid-import rejection and cross-origin write rejection passed.
- Browser: Home loads; agent tool/skill/MCP checkboxes save; Team Demo starts and Next step advances; One agent starts; Compare runs shows separate saved results. Desktop screenshot inspected. Mobile layout inspected and adjusted to stack cards and expose connection settings in the header.
- JavaScript syntax check, Ruff lint and Git whitespace checks pass.
- [Desktop screenshot](design/implemented-desktop.png), [mobile screenshot](design/implemented-mobile.png). These screenshots deliberately show **Demo/sample** mode.

## External access limit — do not overstate

The official OpenAI authorization URL was generated using AgentSim's own host identity and opened in the automated browser. `auth.openai.com/api/accounts/authorize` returned **HTTP 403**, page title “Um momento…”, before a sign-in or consent screen. The plain HTTP probe returned the same status. No challenge bypass was attempted.

No AgentSim OAuth token has been issued. No human consent, live token exchange, refresh, model list or **external AI inference** has been confirmed. No AgentSim API key was supplied. A local Ollama endpoint on 127.0.0.1:11434 was not running. The application never substituted Demo for a failed real request. An actual successful OAuth/API → Responses → CrewAI run is still required before calling the complete external integration verified.

## Remaining work

1. User opens Connection setup → Continue with ChatGPT in their regular browser, passes the provider challenge and grants plan use. Then select ChatGPT, load an eligible model and run a small goal. This is the immediate next verification; do not ask for secrets in chat.
2. If preferred, the user can explicitly choose API provider and enter their own compatible provider key locally. Verify one agent and a three-agent team with real provider outputs/usage and actual selected tools.
3. General external HTTP/SSE MCP connection CRUD, authentication/discovery and custom tool packages are not implemented; current MCP catalog is the real bundled documents server. Multiple ChatGPT accounts/workspaces, Chat Completions-only providers, encrypted credential vault, durable background jobs, cancellation, public multi-user hosting and reconnect/resume are future work.
4. The initial UI is a working browser implementation, not a pixel-by-pixel screenshot renderer. Preserve the approved composition in further refinements.

No public deployment was performed. Commit/push evidence is reported in the delivery message and Git history.
