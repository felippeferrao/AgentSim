# Declarative import format

## Setup JSON

Export from Agents/Teams and use that structure as the template. Required top-level keys: `agents`, `teams`, `catalog`, `runs`. No extra top-level keys. Use `runs: []`; import always preserves server-owned saved runs.

Agent record: exactly `id`, `name`, `job`, `tools`, `skills`, `mcp`.

```json
{"id":"writer","name":"Writer","job":"Write a clear answer","tools":["calculator"],"skills":["clear-writing"],"mcp":["documents:search"]}
```

Team record: exactly `id`, `name`, `agents`. `agents` is an ordered list of existing agent ids. Names are 1–80 characters, jobs at most 500, unique ids required. At most 100 agents and 100 teams. The built-in tools and MCP catalogs must match the exported values. Tools allowed: calculator. MCP tool ids: documents:search, documents:read. Each skill id must exist in catalog.skills. Unknown grants, broken team members and executable fields are rejected. Import max size: 200 KB.

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
