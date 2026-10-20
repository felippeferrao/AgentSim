# Architecture and decisions

## Runtime

Browser HTML/CSS/JavaScript → loopback Python HTTP server → SQLite configuration/history. Real runs use a background thread with JSON event polling; a CrewAI sequential Crew owns tasks and passes prior task outputs as context. The UI exposes completed task output and explicit tool/usage events only, not raw model traces. Demo is a separate deterministic path.

`runtime.py` implements the CrewAI BaseLLM interface. Both ChatGPT OAuth and a compatible API provider use streaming Responses. OAuth tokens are passed only to the public OpenAI API, with store=false and stream=true. Incomplete/failed/interrupted streams are failures. Usage is retained per call and aggregated per task only when reported. Tool execution is the CrewAI text tool protocol, bounded to six iterations; no code execution or agent delegation is enabled.

`mcp_documents.py` is a real FastMCP stdio server with two allowlisted read-only tools. Its documents are bundled teaching content, not private local files. Each session discovers/calls tools through the MCP SDK. Custom external MCP connections and arbitrary tool plugins remain future work; do not describe the built-in catalog as a universal MCP manager.

## Own OAuth

`auth.py` implements dynamic_agent_client registration, a persistent AgentSim host UUID, random state/nonce, S256 PKCE, exact loopback redirect URI, issued-client-id checks, code exchange, JWKS signature/issuer/audience/expiration/nonce validation and same-subject checks on reauthorization. Granted plan scopes are checked separately from identity. Refresh replaces token data atomically. Files are private to this app under .local/ and never committed or exported. One ChatGPT registration is supported at a time; a multi-account switcher is not yet implemented.

Official sources checked 2026-10-20:
- https://developers.openai.com/siwc/quickstart
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://auth.openai.com/.well-known/openid-configuration

No claim that a ChatGPT subscription is a general API key. No reuse of Codex auth files or backend-api endpoints. External provider consent and inference remain unverified because the automated browser encountered an HTTP 403 challenge.

## Visual and brand

User explicitly prioritized the approved image over generic brand color overrides. Retain its palette and composition. The `wabix-brand-identity` skill informed asset handling, spacing and clarity; user direction controls the palette. The unmodified approved image is also used as a CSS image atlas for the mascot and helper illustrations, preserving those exact illustrations without regenerating them.

Official logo provenance: copied only `/Users/felippeferrao/Documents/antigravity/hopeful-lavoisier/wabix-cortex/frontend/public/wabix-logo.png` to static/wabix-logo.png. No Cortex source was imported. The logo asset includes substantial transparent clear space; CSS preserves it and scales its display.

## Limits

Single-user loopback app; no internet-facing authentication, tenant isolation or deployment. Credential files use OS permissions rather than encryption. Runs are not durable jobs: restart interrupts in-flight work, completed runs persist. A single real run is accepted at a time; configuration edits during a run apply to later runs. Future production service needs a durable queue, stronger concurrency/storage model, access control and credential vault.
