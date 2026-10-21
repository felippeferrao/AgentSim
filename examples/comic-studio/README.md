# Comic Story Studio starter

A clean, English-language crew for producing an illustrated comic from a theme and story description.

| Agent | Responsibility | Generation tools |
| --- | --- | --- |
| Clara Reed | Creative director and orchestrator; delegates every production stage | Delegation and quality gate |
| Oliver Bennett | Complete chapter/panel script, dialogue and visual bible | None |
| Maya Chen | New cover and distinct illustrated chapter pages with consistent characters | Image Generator |
| Ethan Brooks | Full structured cover/chapter layout with real illustration URLs | None |
| Sofia Martins | Narrative, continuity, layout and actual file/metadata quality checks | Read generated files |
| Noah Hayes | Approved PDF generation and final page/image/text inspection | PDF Generator; read generated files |

Clara coordinates the dependency order **Oliver → Maya → Ethan → Sofia → Noah**, revisiting earlier stages when corrections are needed. Sofia must return `APPROVED` for the current material before Noah can publish. Completion requires all five specialists in order and a real illustrated PDF. Only Maya can generate images; only Noah can generate PDFs. Read-only generated-file inspection is available during the run, including for files created by another specialist.

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
