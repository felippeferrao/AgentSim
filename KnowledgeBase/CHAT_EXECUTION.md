# Chat execution workspace

Watch & run always executes the connected AI models. There is no sample/real mode selector or educational execution entry point. Historic sample records remain identifiable in Execution history; the old `/api/run` sample endpoint returns HTTP 410.

## User flow

1. Choose **Team** or **One agent**.
2. Select a saved team or any saved agent. An individual agent does not need team membership. No implicit first-member selection is made.
3. Open the chat. Team chats require a configured manager; agent chats call the selected agent directly.
4. Send messages on the left. Each message creates one automatic execution, with public events, tools, skill selection and generated files on the right. Enter sends, Shift+Enter inserts a newline.
5. Inspect an execution from its assistant answer or select it in Message execution. Chat messages and execution evidence have independent scroll containers. Open inspectors and manual evidence scroll positions survive live updates; the message composer is not rebuilt by streamed events.
6. Saved chats reopens prior conversations and their execution evidence. Reload restores the last selected chat; an active job can reconnect to its event stream. A server restart marks unfinished work interrupted rather than replaying it.

The existing visual style, mascot and avatar assets remain. Activity cards pulse while their agents run. Tools, skill and MCP grants still come from each selected agent's current saved profile.

## Data and runtime contract

- `execution_context.resolve_target(state, body)` resolves an explicit agent id or team id. One-agent execution never silently takes the first team member. A chat's target is stored at creation and cannot be redirected by message request fields.
- `conversation_store.ConversationStore` stores conversations in the same local SQLite database, in a separate `conversations` table. Each public user/assistant message references its execution id. Completed, failed, rejected and interrupted turns remain visible. Completion reconciliation is idempotent during startup recovery.
- `POST /api/conversations` accepts `{ "mode": "one", "agent": "agent-id" }` or `{ "mode": "team", "team": "team-id" }`. GET lists saved conversations; GET `/api/conversations/<id>` returns messages and the active run id.
- `POST /api/real-run` accepts `{ "conversationId": "id", "goal": "current message" }`. The server loads the target and prior messages from SQLite, validates access/models and starts the existing background worker/SSE execution path. Client-supplied history or target overrides are ignored for chat turns.
- Messages accept 1–8000 characters. All messages stay stored. The next model task receives up to the last 40 completed public user/assistant messages and at most 60000 prior-message characters. Failed assistant errors are not supplied as successful answers. A `conversation_context` event reports the included count and whether context was truncated, plus the target, class and execution location.
- `execution_context.conversation_prompt` attaches prior messages to the actual single-agent task in `runtime.execute` or manager task in `orchestration.execute_managed`. A follow-up is a new CrewAI execution with public conversation context; hidden model state is not persisted or implied.
- Existing tool/MCP events, skill reasons, provider usage and artifacts flow through `execution_log.enrich` and durable execution records. The UI renders the same evidence used by Execution history; it does not create simulated execution steps.

No external inference is triggered by selecting a target or opening a chat. Inference begins only when the user sends a message. Own account credentials remain independent of conversation history and are not exported into prompts or logs by this flow.
