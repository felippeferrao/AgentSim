# Requirements

Display name: **WABIX AgentSim**. Repository name remains AgentSim.

Teach agent orchestration to a nontechnical manager and to the owner's daughter. Do not infer age or create a separate child interface. Use plain English, concrete examples and guided steps with professional polish.

Preserve the approved light background, navy text, teal/orange/purple accents, robot mascot, sidebar, three helper cards, arrows, timeline, usage bar and right inspector. Keep Home, Agents, Teams, Tools, Skills and MCP Connections; One agent/Team, Next step and Compare runs. The approved reference is stored in design/approved-reference.png. Responsive layouts can stack panels.

Provide agent/team CRUD, explicit permission assignment/removal, granular MCP tool selection, validated declarative imports, skill dependencies without silent grants, and visible essential/advanced settings. Show inputs, outputs and clearly labeled teaching explanations, never private internal thought traces.

The initial scope was expanded during implementation: Demo alone is insufficient. Implement real CrewAI execution, tools/MCP, applied skills, own ChatGPT OAuth and a consciously selected configurable API alternative. Be honest about what has actually run against an external provider.

Never reuse private Cortex code, Codex credentials or Cortex secrets. Only its public WABIX logo asset was authorized for reuse. Do not deploy publicly. Commit and push to the authorized repository.

## Accepted refinements during construction

Home must be the entry dashboard/report with counts and explanatory cards, not the execution canvas. Move the approved canvas to explicit Watch & run. Keep Import setup / Export setup. Clearly identify example configurations and persistent SQLite data; do not auto-seed or reset user data.

Agent editing requires separate profile, Tools, Skills and MCP sections; the latest refinement below splits profile into three smaller steps. Expand the profile to framework-backed role, goal, context, instructions, purpose, input/output examples, expected result and advanced model/behavior options. Persist/migrate it and show a configuration preview. Let the user choose among approved character portraits and render the saved choice consistently.

Real AI is the primary experience; disconnected Home must automatically open Connection setup. Account validity is checked by the backend. Real work advances through streamed events without Next clicks. Samples are a deliberate secondary educational option and never a fallback. Connection and model belong to each agent, supporting heterogeneous teams. Shared global settings are for credentials rather than model overrides.

External HTTP MCP configuration and use are in scope: registry management, authentication, discovery, granular grants, schema-validated calls, clear errors, local secrets and controlled-endpoint verification, independent of OAuth access limits. No Brain Mentoria AI credential is authorized for the controlled tests.

Latest profile navigation refinement: split the original step 1 into Identity (character, name and role), Job (remaining fields through Expected result), and Model & settings (available-model dropdown and remaining configuration). Keep Tools, Skills and MCPs as following separate steps. Populate the model dropdown from the selected connection automatically.

- Account connection is configured once. Remove the per-agent ChatGPT/API selector; automatically load the connected account catalog while keeping model choice per agent.

- Team configuration selects the team's manager. The manager chooses assignments and order dynamically rather than a fixed member pipeline.
- Watch & run must pulse the agent actually executing and show delegation, questions, context and replies live underneath. Unused agents must not appear completed.
- Add an Architecture navigation item with application/runtime and selected-team diagrams.
- Preserve the current visual identity and approved artwork. Remove only the small robot icon beside the WABIX logo in the header. Use agents, not helpers, in product labels.

- Home navigation cards must include visible illustrations, not only text/counts. Keep the approved characters for Agents/Teams/Watch and matching resource artwork for Tools/Skills/MCP. Verify the result in the user's actual in-app tab.

- The Welcome to AgentSim card belongs at the top of the desktop sidebar, with the complete navigation menu below it.
- Agents and Teams dashboard images must be distinct purpose-made illustrations, not reused execution portraits.

- Add real Web Research, PDF, LLM image-generation and high-quality Plotly chart integrations to Tools. Show generated outputs/previews/downloads during execution.
- Import/view/remove Codex-format Markdown skills. Managers choose relevant skills, explain the public choice and apply them to delegated work; record selection/application explicitly.
- Persist every run and public execution stage, including failed/interrupted runs, with explanatory evidence, execution location and responsible implementation class.
- Interpret MCP plugin ZIP uploads plus locally entered access keys. Preview the manifest and executable entry points; discover tools automatically but retain explicit tool grants.
- Document the harness contract, classes, future integration workflow, supported plugin formats and provider prerequisites in the project knowledge base.

## Conversational execution refinement

- Execution is always real AI; remove the educational/real selector.
- Choose Team or One agent, then explicitly choose the actual saved target. Individual agents work independently of team membership.
- Open a persistent interactive chat on the left. Every user message triggers execution whose steps/results appear on the right, with scrolling and per-step inspection of the previously required evidence.
