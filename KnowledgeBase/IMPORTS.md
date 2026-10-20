# Declarative import format

## Setup JSON

Export from Agents/Teams and use that structure as the template. Required top-level keys: `agents`, `teams`, `catalog`, `runs`. No extra top-level keys. Use `runs: []`; import always preserves server-owned saved runs.

Legacy agent record: `id`, `name`, `job`, `tools`, `skills`, `mcp`. Rich profile fields below are also accepted and validated.

```json
{"id":"writer","name":"Writer","job":"Write a clear answer","tools":["calculator"],"skills":["clear-writing"],"mcp":["documents:search"]}
```

Team record: exactly `id`, `name`, `agents`. `agents` is an ordered list of existing agent ids. Names are 1–80 characters, jobs at most 500, unique ids required. At most 100 agents and 100 teams. The tool catalog and registered MCP identities/definitions must match this workspace. Status and local revision fields remain server-owned. Built-in tool: calculator. Built-in MCP tool ids: documents:search, documents:read; registered external connections add their own ids. Each skill id must exist in catalog.skills. Unknown grants, broken team members and executable fields are rejected. Import max size: 200 KB.

## Skill JSON

Skills → Import a skill accepts exactly these fields:

```json
{
  "id": "short-plan",
  "name": "Short plan",
  "description": "Make a plan easy to follow.",
  "instructions": "Use three numbered steps. Give one concrete example.",
  "requires": []
}
```

Use lowercase letters, numbers and hyphens for ids (1–80 characters). Name: 1–80, description: 1–500, instructions: 1–4000 characters. At most 30 skills. Reimporting an id replaces that skill. `requires` can list calculator, documents:search or documents:read. Dependencies never grant permissions. Real execution fails if any assigned skill dependency is missing. Plain instructions can influence model output; only import instructions you trust. Imports never install packages, open archives, run shell commands or create arbitrary MCP servers.

## Expanded agent profiles (version 1)

Legacy records remain accepted and are migrated without resetting ids or grants. Expanded records also carry `profileVersion: 1`, `avatar` (researcher/writer/reviewer/robot), `role`, `goal`, `backstory`, `instructions`, `purpose`, `exampleInput`, `exampleOutput`, `expectedOutput`, `model` and `behavior`. `job` is a synchronized alias of goal. `example` is an optional boolean identifying example configuration provenance.

`model`: `mode: "custom"`, `connection: "chatgpt" | "api"`, `name`, optional-null `temperature`, optional-null `maxOutputTokens`, and `contextWindow` (default 32000). No global setting overrides this model. Draft name can be blank; real execution requires an explicit model.

`behavior`: maxIterations (1–20), maxRetries (0–2), maxExecutionSeconds (10–600), maxRequestsPerMinute (0–120; 0 means no extra limiter), respectContextWindow (boolean). Text and numeric limits are enforced by profiles.py. [Complete mapping](AGENT_PROFILES.md).

External MCP connections must already be registered locally. Imports cannot install a server or alter its endpoint/authentication/tool definitions. Status, local revision and saved-credential flags are server-owned metadata; credential values never appear in an export. Explicit imported grants must name tools that exist in the registered catalog. Register/discover the same server first when moving a setup between installations. Skill dependencies can reference external `connection:tool` ids but never grant them; missing permissions block execution.
