# Comic Story Studio starter

A clean, English-language crew for producing an illustrated comic from a theme and story description.

| Agent | Responsibility | Generation tools |
| --- | --- | --- |
| Orchestrator | Adaptive task planning and delegation to available members | Delegation and file inspection |
| Scriptwriter | Complete chapter/panel script, dialogue and visual bible | None |
| Illustrator | New cover and distinct illustrated chapter pages with consistent characters | Image Generator |
| Layout Designer | Full structured cover/chapter layout with real illustration URLs | None |
| Quality Validator | Narrative, continuity, layout and actual file/metadata quality checks | Read generated files |
| PDF Generator | Requested PDF generation and final page/image/text inspection | PDF Generator; read generated files |

Orchestrator breaks the request into small tasks and chooses which available agents to call, in what order, and when to revise or review work. No role list or sequence is mandatory. Removing a specialist does not block a run: the manager adapts using the remaining members and its own text capabilities. If a required generation tool is unavailable to every remaining member, it explains the concrete limitation rather than inventing a result. Quality review can be requested at any useful point; there is no named-stage approval gate. Requested PDF/image outputs must still be real files. The default permissions give Image Generator only to Illustrator and PDF Generator only to PDF Generator. These are editable grants, not hardcoded routing rules. Read-only generated-file inspection is available throughout the run. Every execution action displays the responsible agent’s name and avatar; new events preserve that identity in their saved metadata.

In **Watch & run**, select **Team → Comic Story Studio → Open chat** and send, for example:

> Theme: courage and friendship. Story: a young inventor and a lost robot explore a floating city and find a way home. Create a five-chapter illustrated comic with a cover.

Five chapters are the default unless the brief requests another count. Configuration, instructions and default output are English. Explicit user requests for another output language are respected. The configured `gpt-5.6-terra` model was present in the owner's connected account catalog; another installation must connect its own account and select an available model if necessary. ChatGPT native image generation also requires that installation's own image session. No credentials are included.

## Seed files

- `configuration.json`: canonical human-readable configuration.
- `starter.sqlite3`: sanitized SQLite example with one configuration row and empty `executions`/`conversations` tables. It contains no user history, generated files, personal endpoint configuration or credentials.
- A new installation creates its operational `agentsim.db` dynamically from the same configuration. Operational databases remain ignored; this named seed is the sole Git exception, explicitly requested by the owner.

To rebuild the example database after an intentional configuration edit:

```sh
PYTHONPATH=. .venv/bin/python starter_crew.py --build-seed
```

This command rebuilds only the versioned starter fixture. It does not reset the user's operational database or delete their history.
