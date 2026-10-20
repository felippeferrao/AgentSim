# Agent profile schema and real framework mapping

Profiles have four actual editor tabs: **Profile**, **Tools**, **Skills**, **MCPs**. Only the selected panel is visible; switching tabs preserves unsaved inputs. Import setup and Export setup remain in Agents/Teams.

`profiles.py` validates and migrates every legacy agent in place. Old `job` becomes `goal`; `job` remains a synchronized compatibility alias. Existing ids, memberships, permissions, saved runs and user text are preserved. The expanded profile is stored in the existing SQLite database. New installations start empty; loading examples is an explicit merge, not a reset. Original bundled helper definitions are labeled Example configuration. That label describes the configuration source, not proof that an AI request has run.

| Profile setting | Actual effect |
| --- | --- |
| name | Display name, history and step labels |
| avatar | Persisted choice of approved Researcher, Writer, Reviewer or Robot artwork; shown in editor, agent cards and Watch & run |
| role | CrewAI `Agent.role` |
| goal | CrewAI `Agent.goal` and the assigned task description |
| backstory | Included in `Agent.backstory` |
| instructions | Included in backstory and task description |
| purpose | Included as labeled context in backstory |
| exampleInput / exampleOutput | Included inside explicitly delimited `teaching_examples`, identified as style examples rather than current goal or verified facts |
| expectedOutput | CrewAI `Task.expected_output` |
| model.connection | This agent's own ChatGPT or API connection; global credentials do not replace its model |
| model.name | This agent's Responses model; each team member has its own LLM adapter |
| model.temperature | Sent only when explicitly set; rejection is shown, no silent fallback |
| model.maxOutputTokens | Sent as `max_output_tokens` only when set |
| model.contextWindow | Context budget returned to CrewAI; this does not enlarge the real model's capability |
| behavior.maxIterations | CrewAI `max_iter` |
| behavior.maxRetries | CrewAI `max_retry_limit` |
| behavior.maxExecutionSeconds | CrewAI `max_execution_time` |
| behavior.maxRequestsPerMinute | CrewAI `max_rpm`; 0 means no additional CrewAI limiter |
| behavior.respectContextWindow | CrewAI `respect_context_window` |

Model selection is per agent. Draft profiles can be saved with an empty model name, but real execution is blocked until each selected helper has a model and its chosen connection passes a provider access check. A legacy shared model, when present, is copied into each legacy profile once during migration; later global changes cannot override agent models. Different agents can use different models and different ChatGPT/API connections in the same sequential crew.

Profile preview displays user-configured inputs, without credentials. CrewAI adds its own framework/task instructions; the preview does not claim to show hidden model reasoning or every framework-generated token. There are no new magician illustrations in this release: the selector uses only approved, existing artwork.
