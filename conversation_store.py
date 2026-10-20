"""Durable user/assistant conversations and links to public execution evidence."""

import json
import time
import uuid

from execution_context import resolve_target


class ConversationStore:
    def __init__(self, connect):
        self.connect = connect

    def save(self, record):
        record["updatedAt"] = time.time()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, data TEXT)")
            db.execute(
                "INSERT OR REPLACE INTO conversations VALUES (?,?)",
                (record["id"], json.dumps(record)),
            )
        return record

    def get(self, ident):
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, data TEXT)")
            row = db.execute("SELECT data FROM conversations WHERE id=?", (ident,)).fetchone()
        if not row:
            raise ValueError("Conversation not found.")
        record = json.loads(row[0])
        for message in record["messages"]:
            if message["role"] == "assistant" and "artifacts" not in message:
                with self.connect() as db:
                    execution = db.execute(
                        "SELECT data FROM executions WHERE id=?", (message.get("runId"),)
                    ).fetchone()
                events = json.loads(execution[0]).get("events", []) if execution else []
                message["artifacts"] = [
                    e["data"] for e in events if e["type"] == "artifact_created"
                ]
        return record

    def list(self):
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, data TEXT)")
            records = [json.loads(r[0]) for r in db.execute("SELECT data FROM conversations")]
        return sorted(
            [{k: c[k] for k in ("id", "mode", "targetId", "name", "updatedAt")} for c in records],
            key=lambda c: c["updatedAt"],
            reverse=True,
        )

    def create(self, state, body):
        target, _ = resolve_target(state, body)
        if body.get("mode", "team") == "team" and not target.get("manager"):
            raise ValueError("Choose this team's manager in Teams first.")
        return self.save(
            {
                "id": str(uuid.uuid4()),
                "mode": body.get("mode", "team"),
                "targetId": body.get("agent") if body.get("mode") == "one" else body.get("team"),
                "name": target["name"],
                "messages": [],
                "createdAt": time.time(),
            }
        )

    def context(self, record):
        # Keep all messages stored; bound only the context sent on the next turn.
        messages = [m for m in record["messages"] if m.get("status") == "completed"]
        selected, size = [], 0
        for m in reversed(messages[-40:]):
            if size + len(m["content"]) > 60000:
                break
            selected.insert(0, {"role": m["role"], "content": m["content"]})
            size += len(m["content"])
        return selected, len(selected) < len(messages)

    def begin(self, record, text, run_id):
        record["messages"].append(
            {
                "role": "user",
                "content": text,
                "runId": run_id,
                "status": "completed",
                "time": time.time(),
            }
        )
        record["activeRunId"] = run_id
        return self.save(record)

    def finish(self, job):
        ident = job.get("run", {}).get("conversationId")
        if not ident:
            return
        try:
            record = self.get(ident)
        except ValueError:
            return  # A rejected/legacy record may not reference an existing chat.
        if any(
            m["role"] == "assistant" and m.get("runId") == job["id"] for m in record["messages"]
        ):
            return
        completed = job["status"] == "completed"
        steps = job["run"].get("steps", [])
        content = (
            steps[-1]["output"]
            if completed and steps
            else job.get("error", "No answer was returned.")
        )
        record["messages"].append(
            {
                "role": "assistant",
                "content": content,
                "name": record["name"],
                "runId": job["id"],
                "status": job["status"],
                "artifacts": [
                    e["data"] for e in job.get("events", []) if e["type"] == "artifact_created"
                ],
                "time": time.time(),
            }
        )
        record["activeRunId"] = None
        self.save(record)
