# Integration harness and future extension guide

## Execution path

The browser saves agent profiles and individual tool grants through `server.Handler`. `server.CATALOG` imports the authoritative built-in definitions from `harness.CATALOG`; old saved catalogs migrate without changing permissions. `runtime.build_agent` creates an independent Responses adapter for each agent, then `runtime.builtin_tools` attaches only that agent's granted tools. Managed teams use `orchestration.ObservedAgent` and CrewAI hierarchical delegation. A tool is called automatically when the LLM requests it; the UI does not require Next clicks.

The built-in `harness.IntegrationTool` accepts a `request` plus an optional `title`. PDF receives report text, image generation receives a prompt, Web Research receives a query, and Chart Generator receives a JSON string containing a Plotly figure (`data` and optional `layout`). Requests are declarative; they are not executed as Python or JavaScript source.

| Integration | Execution implementation | Runs where | Result |
| --- | --- | --- | --- |
| Calculator | `runtime.calculate` | Local Python | Numeric result |
| Web Research | `harness.ProviderTools` | Agent's selected provider/model, Responses `web_search` | Answer and citation links; an actual web_search_call is required |
| PDF Generator | `harness.PDFGenerator` | Local ReportLab | Real PDF with title, paragraphs and page footer |
| Image Generator | `native_images.ChatGPTImageRuntime` (ChatGPT agents); `harness.ImageProvider` / `ProviderTools` (API setup) | Native ChatGPT/Codex image service with its own sign-in, or a deliberately configured image API | Actual generated PNG |
| Chart Generator | `harness.ChartGenerator` | Local Plotly + Kaleido + installed Chrome | Self-contained interactive HTML, PNG 3200x2000 and SVG |
| MCP | `runtime.HTTPMCPTool` → `external_mcp.exchange` | Remote Streamable HTTP or explicitly trusted local stdio plugin | Actual MCP tools/call output, subject to grants and schema/revision checks |

Web Research uses the existing account and selected agent model. ChatGPT image requests now use `native_images.ChatGPTImageRuntime`: the official installed Codex CLI's native image tool, authenticated once into AgentSim's own protected `.local/image-runtime` directory. No desktop/other-app auth cache is copied. Shell/unified-exec and web search are disabled for image jobs. The child uses workspace-write sandboxing and its own file-backed credentials/configuration. Prompt/image generation uses the ChatGPT/Codex plan; it does not require an API key. The direct subscription-sharing Responses route still rejects hosted image_generation, so ChatGPT agents do not call that rejected hosted tool. An optional dedicated image API model remains supported for deliberate API setups. Native image generation is verified below; unsupported accounts/limits/timeouts still fail explicitly without fabricated output.

Charts accept Plotly trace specifications, allowing line, bar, scatter, pie, area, heatmap, box/violin, treemap, sunburst, Sankey, 3D and other supported declarative traces. Maps or figures requiring remote assets are outside the offline renderer contract. URL/script resources are rejected. HTML includes Plotly locally; previews run in an opaque-origin sandbox with remote connections disabled. SVG may contain rasterized WebGL components, as documented by Plotly. Chrome/Chromium must exist for static export; installing Python dependencies alone does not install a browser.

## Results and event evidence

`harness.ArtifactStore` writes generated files to ignored `.local/artifacts/<run-id>/`. The artifact id is random and the filename extension is allowlisted. The browser receives metadata and an application URL, never an OS path or base64 image payload. `server.Handler` serves real PDF/PNG/SVG/HTML outputs with strict MIME types, nosniff and no-store. HTML has a sandbox CSP. Watch & run attaches images, PDF file cards and interactive/high-resolution charts to the assistant message, including while generation finishes. Artifacts are also visible in Execution history. Conversation messages retain artifact metadata; older conversations reconstruct it from their saved execution records. All links point to the same real stored output files.

Every public event receives a sequence number, timestamp, implementation class/function, execution location and a short explanatory sentence from `execution_log.enrich`. Specific integrations supply more precise provenance. Inputs/results, cited source URLs, selected skills and actual assignments provide evidence for understanding decisions. This is public action evidence, not raw ReAct protocol, private Thought blocks or hidden model reasoning. External MCP credentials and raw arguments/results remain excluded from timeline tool logs; their output is passed only to the authorized agent.

The `executions` SQLite table stores running, completed, failed and interrupted jobs and their events. Each event is persisted immediately. History also includes older completed runs. A restart marks unfinished jobs interrupted and preserves prior evidence/artifacts; it does not resume them. Completed-run comparison keeps the existing last-200 snapshot window, while the execution table is not restricted to that window. History automatically refreshes running jobs. Historical records reference the class implementation and model used at execution time, not the subsequently edited profile.

## Add a built-in integration

1. Add a unique definition to `harness.CATALOG` (id/name/description). This makes it visible in Tools and agent permissions after catalog migration.
2. Implement the operation as a small class/function. Use `harness.IntegrationTool` for the request/title interface, or a separate CrewAI `BaseTool` with a Pydantic argument schema for richer structured inputs.
3. Attach it only when its id is explicitly present in `agent['tools']`. The current dispatch hook is `harness.integration_tools`, called by `runtime.builtin_tools`. Never grant it because a skill asks for it.
4. Emit `tool_started`, `tool_completed` and `tool_failed` with agent identity, implementation, location and public explanation. Return actual results to the LLM. Record provider usage in the current adapter's usage list when an operation makes additional model calls.
5. For files, call `ArtifactStore.write(title, extension, bytes)`. Add a new allowlisted MIME type/preview only if necessary; never return arbitrary filesystem paths or executable HTML in the main origin.
6. Test denied grants, argument errors, successful real output, failure propagation, history persistence and UI preview. Separate controlled-provider evidence from actual external inference.
7. Document prerequisites, credentials, data sent outside the machine, location/class mapping and limitations here. Keep secrets in `auth.LOCAL` protected records, outside SQLite public state/exports/logs.

A future database, email, document, analytics or enterprise service adapter can follow this contract. Alternatively, expose it as an MCP server and import its manifest: existing discovery, granular permission checks, schema validation, revisions and public events apply without adding application-specific Python branches.

## Codex-compatible skills

Upload a UTF-8 Markdown file, normally `SKILL.md`, with YAML front matter:

```markdown
---
name: evidence-report
description: Use when preparing a report from supplied observations.
metadata:
  requires:
    - pdf-generator
---
# Evidence report
State where the observations came from. Generate a PDF and distinguish evidence from conclusions.
```

`skill_files.parse_markdown` validates the name/description/front matter and retains the original Markdown. The optional AgentSim extension `metadata.requires` declares tool ids; it never grants them. The original legacy declarative skill records continue working. View and Remove are available in Skills. Removal also clears future agent assignments; old run evidence remains.

`skill_runtime.SkillSelector` exposes `use_skill(skill_id, reason, agent_id)` to the manager. The manager sees all registered skill descriptions, chooses only when relevant, and can target itself or an actual member. It checks target tool prerequisites, emits `skill_selected`, and loads instructions. `ObservedAgent.execute_task` applies manager-selected worker instructions before execution and emits `skill_applied`. Ordinary agents can load their explicitly assigned skills. Their tool-returned instructions enter their actual context. Importing a file makes instructions available; it does not claim they were used. Selection and application are visible in the trace.

A lone SKILL.md cannot carry its referenced scripts/assets. Such text can still be viewed and used as instructions, but arbitrary embedded shell/Python commands are not automatically run as skill code. Package service integrations as an MCP plugin when executable functionality is required.

## MCP plugin ZIP

The import form accepts a ZIP, inspects its configuration, displays destinations/entry point/files, receives an optional access key, and then imports and automatically discovers tools. No tools are granted automatically. A downloadable example is served at `/example-mcp-plugin.zip`; its sources are in `examples/plugin`.

Recognized manifest: one `.mcp.json` or `mcp.json` at the root or a single enclosing directory, with an `mcpServers` mapping. A `.codex-plugin/plugin.json` may be included as conventional plugin metadata. SKILL.md files in the package are parsed and registered. Credentials must be placeholders rather than embedded secrets.

Remote example:

```json
{"mcpServers":{"my-service":{"url":"https://your-server.example/mcp","headers":{"Authorization":"Bearer ${API_KEY}"}}}}
```

Local example:

```json
{"mcpServers":{"local-review":{"command":"python3","args":["mcp/server.py"],"env":{"SERVICE_KEY":"${API_KEY}"}}}}
```

Access-key placeholders are `${API_KEY}`, `${ACCESS_KEY}` or `${PLUGIN_ACCESS_KEY}`. Remote servers support Bearer or one custom access-key header. Local plugins support an already available Python/Python3/Node interpreter and one packaged entry-point file; manifest environment variable names are bound to the locally entered key. `${PLUGIN_ROOT}`/`${CLAUDE_PLUGIN_ROOT}` prefixes are recognized for packaged script paths. Files are stored under ignored `.local/plugins/<digest>`; credentials are protected separate registry fields and excluded from public records.

Local plugin code runs with the local user's permissions and requires an explicit trust checkbox before import/discovery. The package is not an OS/container sandbox. Import does not run shell commands, npm/pip installers, npx downloads or arbitrary setup scripts. Dependencies must already exist; connection errors remain visible. Supporting additional package ecosystems requires a reviewed installer/sandbox design, not guessing commands from README prose.

Limits: 10 MB ZIP, 20 MB expanded, 500 files, 10 servers. Absolute/traversal paths, symlinks, encrypted archives, duplicate paths, unsupported launchers and embedded manifest credentials are rejected. Connection ids cannot replace existing registrations through import. New servers still require individual agent tool grants after discovery. Editing/removing a registered connection or changed tools continues to revoke stale grants.

## Primary references

- [Codex-compatible SKILL.md guidance](https://learn.chatgpt.com/docs/build-skills)
- [OpenAI hosted web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [OpenAI hosted image generation](https://developers.openai.com/api/docs/guides/tools-image-generation)
- [Plotly static and interactive export](https://plotly.com/python/static-image-export/)
- [Plugin architecture](https://developers.openai.com/plugins/concepts/plugins)

## Streaming compatibility observed during live verification

The ChatGPT-plan path requires store=false and stream=true for inference and hosted web tools. It may send completed message/web-search items in response.output_item.done while response.completed has an empty output list. Both adapters now collect those completed items and reconstruct output only when the terminal response omits it; success still requires response.completed. Raw deltas/reasoning remain outside event history. A contract regression test covers this terminal-empty case.

A live Web Research capability call using AgentSim's independently authorized ChatGPT account completed with web_search_call and message output. Hosted image_generation returned HTTP 400 with the explicit subscription-sharing tool restriction. The separate API ImageProvider path remains optional. A later correction adds the independently authenticated native ChatGPT/Codex image runtime, which successfully generated a real PNG without an API key. No other application's credentials were copied.

## Native ChatGPT image runtime

`native_images.ChatGPTImageRuntime` launches `codex exec --json --ephemeral --ignore-user-config --sandbox workspace-write` with shell/unified execution disabled and web search disabled. Only the native image generator is requested. A private child `CODEX_HOME` points to AgentSim's own runtime directory; host OPENAI/CODEX/CHATGPT credential variables are removed, and file-backed auth storage is forced. This does not change the user's global CLI configuration or reuse its auth cache. Login uses the official CLI OAuth flow; the loopback callback is handled by that process. The Tools form provides sign-in and session status. An installed official CLI with native image generation support is required (verified here with 0.163.0-alpha.10.2).

Only new PNGs in that invocation's returned native thread directory are accepted, after terminal turn completion and a zero process exit. PNG contents are validated with Pillow. Previous images, arbitrary paths, symlinks and oversized files cannot substitute for a missing result. Child processes have a bounded deadline derived from the agent's configured execution time; temporary work directories are removed. The private authentication directory and generated-image pool stay outside Git and setup exports.

Public events identify the native runtime class/location and actual start/completion/usage stages. Raw native model messages, hidden reasoning, stderr and credential data are not persisted as execution evidence. Native image model selection belongs to the official runtime; its exact image model id is not exposed in the CLI JSON events and is not invented by AgentSim.

Image-enabled ChatGPT agents use structured developer-defined function calls in `runtime.ResponsesLLM`. The adapter maps CrewAI function schemas/results to Responses `function_call` / `function_call_output`; CrewAI executes the granted tool. Explicit image creation requests require the image function before a final answer, and `runtime.image_result_guardrail` rejects text-only claims without an actual image artifact.

Primary native-runtime references: [image generation](https://learn.chatgpt.com/docs/image-generation), [non-interactive runtime](https://learn.chatgpt.com/docs/non-interactive-mode), [independent sign-in](https://learn.chatgpt.com/docs/auth).


## Persistent files and illustrated ebooks

`conversation_store.ConversationStore.artifacts` restores generated file metadata from persisted chat messages, including older messages hydrated from execution events. The server supplies this trusted catalog on subsequent turns independently of the bounded text window; client-supplied artifact catalogs are discarded. Actual bytes stay in ignored `.local/artifacts/`. `artifact_history.resolve_reference` accepts only exact file URLs owned by this conversation, blocks traversal/symlinks and checks existence/size. New current-turn files join the same catalog, including across delegated agents.

`read_generated_file` extracts PDF text and reads original Plotly source saved alongside new charts. `image_generator` accepts `reference_urls` and attaches those actual PNGs using the native CLI's documented `--image` option. Reference images are not supported by the optional API image provider. `pdf_generator` embeds original PNG bytes, either after plain text or through a structured request:

```json
{"cover":{"image_url":"/artifacts/RUN/FILE.png","subtitle":"An illustrated adventure"},"chapters":[{"title":"Chapter 1","text":"Complete chapter text...","image_url":"/artifacts/RUN/SCENE.png"}]}
```

For comics use `pages` instead of `chapters`, with `text` and `image_url` for each page. Images must already exist in the current conversation or current execution. Paths in these examples are illustrative placeholders, not real files.

Example user request: “Construa uma história em 5 capítulos sobre um cachorro viajante. Ilustre cada capítulo e monte um PDF com capa para um e-book.” Grant the selected agent Image Generator and PDF Generator, or assign those integrations to the team's workers. `ebook_workflow.plan` recognizes a long illustrated book request, supplies an explicit chapter/cover plan and extends this request's execution/iteration budget (five chapters: six illustrations, 900 seconds, 20 iterations); saved profile defaults are unchanged. The model writes the story, generates actual scene/cover images, then assembles the PDF. Every actual tool call/result remains visible. `runtime.pdf_result_guardrail` requires a new PDF in the current run; ebook completion additionally requires a cover, cover image, the requested chapter count and an image for every chapter. Missing grants or failed image generation produce an incomplete/failed run, never a fake successful book.

The user may select “Use in next message” on a saved chat attachment, or refer to it naturally. `artifact_reused` events identify selected source files and their purpose in the execution inspector.


Illustrated ebook validation also counts distinct illustration file contents by SHA-256: changing filenames or reusing one image for all chapters is insufficient. A cover plus N chapters needs at least N+1 distinct illustration contents. Requests explicitly requiring new/different images additionally require the embedded illustrations to come from the current run. Native function calls disable parallel tool calls; concurrent native requests are queued instead of rejecting the remaining chapter scenes.


PDF-only revision uses original generator arguments exposed as `read_generated_file.source` when retained. Reusing `source.request` avoids losing or rewriting narrative content during extraction. Multi-image PDF requests must declare a `pages` or `cover`/`chapters` JSON layout; natural-language instructions cannot substitute for actual document content. Chapter illustration height adapts to narrative length to reduce nearly empty continuation pages.

## Agent-authored editorial composition

`harness.PDFGenerator.render` accepts `{ "layout": "editorial-html", "html": "complete HTML with inline CSS", "page_count": 2 }`. The agent chooses and writes the composition; this route does not inject a cover/article template. Supply every actual conversation-owned PNG URL in `reference_urls`, including CSS background images. `editorial_html.render` uses an isolated, time-bounded WeasyPrint process and embeds bundled OFL DM Serif Display/DM Sans fonts. Native Pango is required (see README). The standard ReportLab and older magazine routes remain supported.

The resource fetcher permits only artifact paths previously resolved by the harness and the two bundled fonts. External/local-file URLs, scripts, embeds, remote stylesheets and CSS imports are rejected. HTML is bounded to 100 KB; rendering has a 45-second timeout and 35-second CPU limit on POSIX, with a 40-page/120 MB output cap. This is an offline single-user renderer, not an OS security sandbox. An explicit `page_count` is checked against actual PDF pages and rejected if different, so the agent can repair its composition. Generated source is retained for revisions; readback provides text/image/page evidence, not a visual-review claim.

For skill/no-skill experiments, saved assignment alone is not isolation: an authorized manager can select any registered skill for a permitted team member before delegation. A true no-skill control needs an empty skill registry and empty member skill assignments for that test, followed by restoration. Classify observed runs from skill_selected/skill_applied events, not only the saved profile. Production manager selection remains autonomous.
