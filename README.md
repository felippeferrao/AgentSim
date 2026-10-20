# WABIX AgentSim

Build a team of AI helpers and watch real work happen automatically. Plain English, professional design, and concrete explanations for beginners.

![Home dashboard](KnowledgeBase/design/implemented-home.png)

## Start

Use Python **3.12**. No frontend build is needed.

```sh
git clone https://github.com/felippeferrao/AgentSim.git
cd AgentSim
./start.sh
```

The script creates an isolated environment and installs pinned dependencies. With `uv` it can obtain Python 3.12. Without `uv`, install Python 3.12 first. For manual setup:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python server.py
```

Open **http://127.0.0.1:8080**. Use `PORT=8081 ./start.sh` to change ports. The app is single-user and binds only to loopback. On a simple remote server, use an SSH tunnel (`ssh -L 8080:127.0.0.1:8080 your-server`), then open that exact loopback address locally so the OAuth callback can follow the tunnel. No public multi-user deployment is included.

## Your workspace

**Home** is a short dashboard with Agents, Teams, Tools, Skills, MCP Connections and Watch & run cards. It explains counts and next steps. It does not start a run. Data is persistent SQLite in `agentsim.db`, not temporary in-memory state. A new installation starts empty. You can explicitly load examples without overwriting your own helpers. Existing original samples are labeled Example configuration; saved setup is not proof of an AI request.

When Home opens with no provider-verified connection, Connection setup opens automatically. A saved token/key is not presented as successful access: the backend checks the provider's models endpoint. Dismissing the dialog still allows configuration; real execution remains blocked until access is verified.

**Agents** has Import setup / Export setup and six separate editor steps:

1. **Identity** — choose a character, name and role.
2. **Job** — goal, purpose, context, instructions and expected result.
3. **Model & settings** — this agent's connection, automatically loaded model dropdown, teaching examples and advanced behavior/model settings.
4. **Tools** — explicit tool permissions.
5. **Skills** — instruction packages; dependencies never grant tools silently.
6. **MCPs** — each connection's individual discovered tools.

Back/Next preserve unsaved entries. Models reload when the selected connection changes; a failed lookup never invents available models.

The approved Researcher, Writer, Reviewer and Robot characters are selectable and persisted. Profile fields and behavior settings map to actual CrewAI configuration, not decorative metadata. [Mapping and schema](KnowledgeBase/AGENT_PROFILES.md).

**Watch & run** preserves the approved team visualization. Choose a team, enter a goal and press Run with AI. Execution advances automatically through server-sent events; no Next clicks are required. Every helper uses its own connection/model, including heterogeneous teams. Inputs, outputs, tool events and provider-reported tokens are inspectable. Only configuration-based teaching explanations are shown, never raw private reasoning traces. Failed runs show errors and never switch to samples.

**Educational samples** are secondary and explicitly chosen. Only that optional mode uses deterministic samples and a Next step lesson. Sample token counts are labeled; they are never real provider usage. Compare runs lets you inspect saved results.

## Connect ChatGPT

In Connection setup press **Continue with ChatGPT**, complete the official browser flow, then Check connection again. Keep AgentSim running for the loopback callback. In each agent's Profile, select ChatGPT, load your account's available models and choose a model for that helper.

AgentSim uses its own dynamic open-source client registration, host identity, PKCE, nonce, issued client id, JWT validation and protected credential files. It never reads Codex/Cortex credential stores. ChatGPT plan permission is separate from identity. [Official sign-in guide](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [inference contract](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference).

**Live verification remains pending:** OpenAI returned a 403 browser challenge before consent in the automated environment. No actual OAuth token exchange or external AI inference was completed. The app explains that boundary and retains a reviewable sign-in link. [OAuth review and human test steps](KnowledgeBase/OAUTH_REVIEW.md).

### Explicit API alternative

Open Alternative: your API connection and enter your own key locally, never in chat. Use an HTTPS base URL supporting streaming Responses, or HTTP loopback for a local service. Save and check, then select API and a model separately for each agent. Global settings hold connection credentials; they do not override agent models. Chat Completions-only providers are not supported. Optional temperature/output settings are sent only when set, and unsupported settings produce an error without silent fallback.

Credentials stay in ignored `.local/` files, written atomically with `0600` permissions. They are excluded from exports and public settings responses. This is OS file protection, not encryption at rest. Sign out clears local OAuth credentials; revoke remote access in ChatGPT settings if required.

## Connect external MCP servers

MCP Connections → Add HTTP connection → enter the **Streamable HTTP** endpoint and optional Bearer/custom-header credential → Save → Discover tools → assign specific tools in each agent's MCPs tab.

Discovery and calls use the real MCP SDK. Editing/removing connections or changing tool definitions revokes affected permissions. Credentials never enter Git, SQLite public catalogs, exports or timeline logs. Runtime validates permissions, connection revision and complete JSON input schema before tools/call. HTTP redirects and remote schema references are blocked. The built-in teaching documents also use real MCP stdio. [External MCP behavior and verification](KnowledgeBase/EXTERNAL_MCP.md).

## Verification and limits

```sh
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
```

Tests include actual CrewAI execution with a scripted LLM, authenticated HTTP MCP server processes, complete app HTTP/SSE runs against a controlled Responses fixture, per-agent heterogeneous models, migration, profile mapping, permissions and OAuth contracts. Fixture responses/counts are **not live external AI**.

The current app supports one ChatGPT registration and one API credential connection, chosen independently by each agent. Legacy HTTP+SSE MCP, remote MCP OAuth, arbitrary tool plugins, encrypted credential vault, durable background-job recovery, cancellation and public multi-user hosting remain future work. Completed runs persist; a server restart interrupts in-flight jobs.

See [KnowledgeBase](KnowledgeBase/README.md) for requirements, architecture, evidence and exact delivery status.
