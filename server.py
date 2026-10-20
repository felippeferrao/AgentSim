"""WABIX AgentSim: real CrewAI execution, explicit connections and optional teaching samples."""

import json
import os
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import auth
import external_mcp
import harness
import plugin_import
import profiles
import skill_files
from conversation_store import ConversationStore
from execution_context import resolve_target
from execution_log import enrich

LOCK = threading.RLock()
JOBS = {}
ROOT = Path(__file__).parent
DB = Path(os.environ.get("AGENTSIM_DB", str(ROOT / "agentsim.db")))
CATALOG = {
    "tools": harness.CATALOG,
    "skills": [
        {
            "id": "clear-writing",
            "name": "Clear writing",
            "description": "Use short, friendly sentences.",
            "requires": [],
            "instructions": "Use short sentences and simple English. Give one concrete example.",
        }
    ],
    "mcp": [
        {
            "id": "documents",
            "name": "Teaching documents (MCP)",
            "tools": [
                {"id": "search", "name": "Search documents"},
                {"id": "read", "name": "Read a document"},
            ],
        }
    ],
}


def connect():
    db = sqlite3.connect(DB)
    db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, data TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, data TEXT)")
    return db


def conversations():
    return ConversationStore(connect)


def save_job(job):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO executions VALUES (?,?)", (job["id"], json.dumps(job)))


def saved_job(ident):
    with connect() as db:
        row = db.execute("SELECT data FROM executions WHERE id=?", (ident,)).fetchone()
    return json.loads(row[0]) if row else None


def execution_history():
    with connect() as db:
        jobs = [
            json.loads(row[0])
            for row in db.execute("SELECT data FROM executions ORDER BY rowid DESC")
        ]
    known = {j["id"] for j in jobs}
    jobs += [
        {"id": r["id"], "status": "completed", "run": r, "events": r.get("events", [])}
        for r in reversed(read()["runs"])
        if r["id"] not in known
    ]
    return [
        {
            "id": j["id"],
            "status": j["status"],
            "goal": j.get("run", {}).get("goal", ""),
            "team": j.get("run", {}).get("team", ""),
            "startedAt": j.get("startedAt"),
            "eventCount": len(j["events"]),
            "error": j.get("error", ""),
        }
        for j in jobs
    ]


def recover_jobs():
    with connect() as db:
        rows = db.execute("SELECT data FROM executions").fetchall()
    for row in rows:
        job = json.loads(row[0])
        if job["status"] == "running":
            job["status"] = "interrupted"
            job["error"] = (
                "Application restarted during this run. Earlier activity and outputs were preserved."
            )
            job["events"].append(
                {
                    "type": "run_interrupted",
                    "sequence": len(job["events"]) + 1,
                    "time": time.time(),
                    "data": enrich(
                        "run_interrupted",
                        {
                            "error": job["error"],
                            "implementation": "server.recover_jobs",
                            "where": "Local application startup",
                            "explanation": "An unfinished run was recovered as interrupted after restart; no automatic replay was performed.",
                        },
                    ),
                }
            )
            job["run"].update(
                failed=True, error=job["error"], completed=False, events=job["events"]
            )
            save_job(job)
        if job["status"] != "running":
            conversations().finish(job)


def initial():
    return {
        "agents": [
            {"id": r.lower(), "name": r, "job": j, "tools": [], "skills": [], "mcp": []}
            for r, j in [
                ("Researcher", "Find useful facts"),
                ("Writer", "Write a clear answer"),
                ("Reviewer", "Check the result"),
            ]
        ],
        "teams": [
            {
                "id": "research",
                "name": "Research helpers",
                "agents": ["researcher", "writer", "reviewer"],
            }
        ],
        "catalog": __import__("copy").deepcopy(CATALOG),
        "runs": [],
    }


def blank():
    state = initial()
    state["agents"] = []
    state["teams"] = []
    return state


def load_examples(state):
    if any(a.get("example") for a in state["agents"]):
        return state
    mapping = {}
    for a in initial()["agents"]:
        a["id"] = "example-" + a["id"] + "-" + uuid.uuid4().hex[:6]
        a["example"] = True
        mapping[a["name"].lower()] = a["id"]
        state["agents"].append(a)
    state["teams"].append(
        {
            "id": "example-team-" + uuid.uuid4().hex[:6],
            "name": "Example research team",
            "agents": list(mapping.values()),
            "example": True,
        }
    )
    return state


def read():
    with connect() as db:
        row = db.execute("SELECT data FROM state WHERE id=1").fetchone()
    state = json.loads(row[0]) if row else blank()
    before_migration = __import__("copy").deepcopy(state)
    state["catalog"]["tools"] = __import__("copy").deepcopy(CATALOG["tools"])
    # Migration labels the original bundled configurations; never resets user data.
    defaults = {a["id"]: a for a in initial()["agents"]}
    for a in state["agents"]:
        original = defaults.get(a["id"])
        if (
            "example" not in a
            and original
            and a["name"] == original["name"]
            and a["job"] == original["job"]
        ):
            a["example"] = True
    for team in state["teams"]:
        if (
            "example" not in team
            and team["id"] == "research"
            and team["name"] == "Research helpers"
            and team["agents"]
            and all(
                next((a.get("example", False) for a in state["agents"] if a["id"] == ident), False)
                for ident in team["agents"]
            )
        ):
            team["example"] = True
    state["agents"] = [profiles.validate(a) for a in state["agents"]]
    for a in state["agents"]:
        if a["model"]["mode"] == "inherit":
            old = auth.settings()
            a["model"]["mode"] = "custom"
            a["model"]["name"] = old.get("model", "")
            a["model"]["connection"] = (
                old.get("provider") if old.get("provider") in ("chatgpt", "api") else "chatgpt"
            )
    if row and state != before_migration:
        save(state)
    state["catalog"]["mcp"] = CATALOG["mcp"] + external_mcp.connections()
    allowed = {m["id"] + ":" + t["id"] for m in state["catalog"]["mcp"] for t in m["tools"]}
    for agent in state["agents"]:
        agent["mcp"] = [g for g in agent["mcp"] if g in allowed]
    return state


def save(s):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO state VALUES (1,?)", (json.dumps(s),))


def mcp_identity(records):
    def clean(value):
        if isinstance(value, dict):
            return {
                k: clean(v)
                for k, v in value.items()
                if k not in {"status", "hasCredential", "revision", "connectionRevision"}
            }
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value

    return clean(records)


def validate(s):
    if not isinstance(s, dict) or set(s) != {"agents", "teams", "catalog", "runs"}:
        raise ValueError("Expected agents, teams, catalog and runs.")
    for kind in ["agents", "teams"]:
        items = s[kind]
        if not isinstance(items, list) or len(items) > 100:
            raise ValueError("Use at most 100 items.")
        ids = []
        for a in items:
            if (
                not isinstance(a, dict)
                or not isinstance(a.get("id"), str)
                or not a["id"]
                or not isinstance(a.get("name"), str)
                or not 0 < len(a["name"]) <= 80
            ):
                raise ValueError("Each item needs an id and a name (1–80 letters).")
            if "example" in a and not isinstance(a["example"], bool):
                raise ValueError("Example marker must be true or false.")
            ids.append(a["id"])
            if kind == "agents":
                if not {"id", "name", "job", "tools", "skills", "mcp"} <= set(a):
                    raise ValueError("Missing agent fields.")
                a.update(profiles.validate(a))
            elif set(a) - {"example", "manager"} != {"id", "name", "agents"}:
                raise ValueError("Invalid team fields.")
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate ids.")
    catalog = s["catalog"]
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"tools", "skills", "mcp"}
        or catalog["tools"] != CATALOG["tools"]
        or mcp_identity(catalog["mcp"]) != mcp_identity(CATALOG["mcp"] + external_mcp.connections())
    ):
        raise ValueError(
            "Imports cannot add or change MCP connections. Register them in MCP Connections first."
        )
    catalog["mcp"] = CATALOG["mcp"] + external_mcp.connections()
    if not isinstance(catalog["skills"], list) or len(catalog["skills"]) > 30:
        raise ValueError("Use at most 30 skills.")
    skill_ids = []
    for skill in catalog["skills"]:
        if not isinstance(skill, dict) or set(skill) - {"markdown", "format"} != {
            "id",
            "name",
            "description",
            "instructions",
            "requires",
        }:
            raise ValueError("Skill needs id, name, description, instructions and requires.")
        for key, limit in [
            ("id", 80),
            ("name", 80),
            ("description", 1024),
            ("instructions", 100000),
        ]:
            if not isinstance(skill[key], str) or not 0 < len(skill[key]) <= limit:
                raise ValueError("Invalid skill text.")
        if not __import__("re").fullmatch(r"[a-z0-9-]+", skill["id"]):
            raise ValueError("Skill id uses lowercase letters, numbers and hyphens.")
        if not isinstance(skill["requires"], list) or any(
            not isinstance(x, str)
            or (
                x not in [t["id"] for t in CATALOG["tools"]]
                and not __import__("re").fullmatch(r"[a-z0-9-]+:[A-Za-z0-9_.-]{1,128}", x)
            )
            for x in skill["requires"]
        ):
            raise ValueError("Unknown skill dependency.")
        skill_ids.append(skill["id"])
    if len(set(skill_ids)) != len(skill_ids):
        raise ValueError("Duplicate skill ids.")
    for a in s["agents"]:
        for k, allowed in [
            ("tools", [t["id"] for t in CATALOG["tools"]]),
            ("skills", skill_ids),
            ("mcp", [m["id"] + ":" + t["id"] for m in catalog["mcp"] for t in m["tools"]]),
        ]:
            if not isinstance(a[k], list) or any(v not in allowed for v in a[k]):
                raise ValueError("Unknown assignment.")
    for t in s["teams"]:
        if not isinstance(t["agents"], list) or any(
            x not in [a["id"] for a in s["agents"]] for x in t["agents"]
        ):
            raise ValueError("Unknown team member.")
        if len(set(t["agents"])) != len(t["agents"]):
            raise ValueError("Choose each team member only once.")
        if t.get("manager") is not None:
            if not isinstance(t["manager"], str) or t["manager"] not in t["agents"]:
                raise ValueError("Choose a manager from this team's members.")
            if len(t["agents"]) < 2:
                raise ValueError("A managed team needs a manager and at least one other agent.")
    if not isinstance(s["runs"], list) or len(s["runs"]) > 200:
        raise ValueError("Invalid run history.")
    return s


def make_run(s, body):
    goal = body.get("goal", "").strip()
    if not goal or len(goal) > 500:
        raise ValueError("Write a goal (1–500 letters).")
    team = next((t for t in s["teams"] if t["id"] == body.get("team")), None)
    if not team:
        raise ValueError("Choose a team first.")
    members = [next(a for a in s["agents"] if a["id"] == i) for i in team["agents"]]
    if body.get("mode") == "one":
        members = members[:1]
    if not members:
        raise ValueError("Add an agent to this team first.")
    previous = goal
    steps = []
    for i, a in enumerate(members):
        output = f"Sample {i + 1}: {a['name']} works on ‘{goal}’. Job: {a['job']}. " + (
            "Sample facts: define the audience, choose three key points, give an example."
            if i == 0
            else "Uses the previous sample to make the answer clearer."
        )
        steps.append(
            {
                "agent": a["name"],
                "agentId": a["id"],
                "avatar": profiles.normalize(a)["avatar"],
                "input": previous,
                "output": output,
                "why": f"Teaching explanation: this helper has the job “{a['job']}”. Passing its result to the next helper shows teamwork.",
                "assignments": {k: a[k] for k in ["tools", "skills", "mcp"]},
                "inputTokens": None,
                "outputTokens": None,
                "sampleInput": 80 + i * 30,
                "sampleOutput": 45 + i * 15,
            }
        )
        previous = output
    return {
        "id": str(uuid.uuid4()),
        "goal": goal,
        "mode": body.get("mode", "team"),
        "team": team["name"],
        "provider": "demo",
        "steps": steps,
        "completed": False,
    }


class Handler(BaseHTTPRequestHandler):
    def reply(self, data, status=200):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get("Host", "").split(":")[0] not in ["127.0.0.1", "localhost"]:
            return self.reply({"error": "Use the loopback address"}, 403)
        url = urlparse(self.path)
        if url.path == "/auth/callback":
            try:
                auth.callback({k: v[0] for k, v in parse_qs(url.query).items()})
                message = "Signed in. Return to AgentSim and choose each helper’s model in Agents → Profile."
            except Exception as e:
                message = (
                    str(e)
                    if isinstance(e, ValueError)
                    else "Sign-in validation failed. Start again."
                )
            raw = (
                "<!doctype html><title>WABIX AgentSim</title><p>"
                + __import__("html").escape(message)
                + '</p><a href="/">Return to AgentSim</a>'
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(raw)
            return
        if url.path == "/api/image-runtime":
            return self.reply(harness.ChatGPTImageRuntime.settings())
        if url.path == "/api/image-provider":
            return self.reply(harness.ImageProvider.settings())
        if url.path == "/api/conversations":
            return self.reply(conversations().list())
        if url.path.startswith("/api/conversations/"):
            try:
                return self.reply(conversations().get(url.path.rsplit("/", 1)[-1]))
            except ValueError as exc:
                return self.reply({"error": str(exc)}, 404)
        if url.path == "/api/executions":
            return self.reply(execution_history())
        if url.path.startswith("/artifacts/"):
            import re

            match = re.fullmatch(
                r"/artifacts/([A-Za-z0-9-]+)/([a-f0-9]{32}\.(pdf|png|svg|html))", url.path
            )
            if not match:
                return self.reply({"error": "Artifact not found"}, 404)
            path = harness.artifact_root() / match[1] / match[2]
            if not path.is_file():
                return self.reply({"error": "Artifact not found"}, 404)
            raw = path.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                {
                    "pdf": "application/pdf",
                    "png": "image/png",
                    "svg": "image/svg+xml",
                    "html": "text/html; charset=utf-8",
                }[match[3]],
            )
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("Content-Disposition", 'inline; filename="' + match[2] + '"')
            if match[3] == "html":
                self.send_header(
                    "Content-Security-Policy",
                    "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'",
                )
            self.end_headers()
            self.wfile.write(raw)
            return
        if url.path.startswith("/api/jobs/") and url.path.endswith("/events"):
            ident = url.path.split("/")[-2]
            if ident not in JOBS:
                stored = saved_job(ident)
                if stored:
                    JOBS[ident] = stored
            if ident not in JOBS:
                return self.reply({"error": "Run not found"}, 404)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            last = None
            try:
                while True:
                    job = JOBS[ident]
                    signature = (job["status"], len(job["events"]))
                    if signature != last:
                        self.wfile.write(("data: " + json.dumps(job) + "\n\n").encode())
                        self.wfile.flush()
                        last = signature
                    if job["status"] != "running":
                        return
                    time.sleep(0.25)
            except (BrokenPipeError, ConnectionResetError):
                return
        if url.path.startswith("/api/jobs/"):
            ident = url.path.rsplit("/", 1)[-1]
            job = JOBS.get(ident) or saved_job(ident)
            if not job:
                legacy = next((r for r in read()["runs"] if r["id"] == ident), None)
                if legacy:
                    job = {
                        "id": ident,
                        "status": "sample"
                        if legacy.get("provider") == "demo"
                        else "failed"
                        if legacy.get("failed")
                        else "completed"
                        if legacy.get("completed")
                        else "saved",
                        "run": legacy,
                        "events": legacy.get("events", []),
                    }
            return self.reply(job or {"error": "Run not found"}, 200 if job else 404)
        if self.path == "/api/connection/status":
            return self.reply(auth.connection_status())
        if self.path == "/api/settings":
            return self.reply(auth.public_settings())
        if self.path == "/api/state":
            return self.reply(read())
        if self.path == "/api/connection":
            return self.reply(auth.connection_status())
        path = ROOT / "static" / ("index.html" if url.path == "/" else url.path.lstrip("/"))
        if path.parent != ROOT / "static" or not path.is_file():
            return self.reply({"error": "Not found"}, 404)
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            {
                "html": "text/html",
                "css": "text/css",
                "js": "text/javascript",
                "png": "image/png",
                "zip": "application/zip",
            }.get(path.suffix[1:], "text/plain"),
        )
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):
        pass  # Callback query strings contain authorization codes. Never log them.

    def do_POST(self):
        if self.headers.get("Host", "").split(":")[0] not in ["127.0.0.1", "localhost"]:
            return self.reply({"error": "Use the loopback address"}, 403)
        try:
            if self.headers.get("Origin") and self.headers[
                "Origin"
            ] != "http://" + self.headers.get("Host", ""):
                return self.reply({"error": "Cross-origin writes blocked"}, 403)
            size = int(self.headers.get("Content-Length", "0"))
            if size > (15_000_000 if self.path.startswith("/api/plugins/") else 8_000_000):
                raise ValueError("Upload exceeds the permitted request size.")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object.")
            s = read()
            if self.path == "/api/conversations":
                return self.reply(conversations().create(s, body), 201)
            if self.path == "/api/image-runtime/login":
                return self.reply(harness.ChatGPTImageRuntime.login())
            if self.path == "/api/image-provider/clear":
                auth.store("image-provider", {})
                return self.reply(harness.ImageProvider.settings())
            if self.path in ("/api/image-provider/models", "/api/image-provider/save"):
                old = auth.load("image-provider")
                key = body.get("api_key") or old.get("api_key", "")
                base = body.get("base_url", "https://api.openai.com/v1").rstrip("/")
                if (
                    not isinstance(key, str)
                    or not key
                    or len(key) > 8192
                    or "\n" in key
                    or "\r" in key
                ):
                    raise ValueError("Enter a valid image-provider API key locally.")
                models = harness.ImageProvider.models(base, key)
                if self.path.endswith("/models"):
                    return self.reply({"models": models})
                if body.get("model") not in [m["id"] for m in models]:
                    raise ValueError("Choose an available GPT Image model.")
                auth.store(
                    "image-provider", {"api_key": key, "base_url": base, "model": body["model"]}
                )
                return self.reply(harness.ImageProvider.settings())
            if self.path == "/api/plugins/inspect":
                return self.reply(plugin_import.inspect(body.get("zip", "")))
            if self.path == "/api/plugins/import":
                preview = plugin_import.inspect(body.get("zip", ""))
                candidate = __import__("copy").deepcopy(s)
                for skill in preview["skills"]:
                    if any(x["id"] == skill["id"] for x in candidate["catalog"]["skills"]):
                        raise ValueError("A plugin skill id already exists: " + skill["id"])
                    candidate["catalog"]["skills"].append(skill)
                validate(candidate)
                description, imported = plugin_import.install(
                    body["zip"], body.get("accessKey", ""), body.get("trustLocal", False)
                )
                import asyncio

                discovery = []
                for connection in imported:
                    try:
                        asyncio.run(external_mcp.discover(connection["id"]))
                        discovery.append({"id": connection["id"], "status": "Connected"})
                    except ValueError as exc:
                        discovery.append({"id": connection["id"], "status": str(exc)})
                candidate["catalog"]["mcp"] = CATALOG["mcp"] + external_mcp.connections()
                validate(candidate)
                save(candidate)
                return self.reply({"state": candidate, "discovery": discovery})
            if self.path == "/api/skills/import":
                skill = skill_files.parse_markdown(body.get("markdown", ""))
                if any(x["id"] == skill["id"] for x in s["catalog"]["skills"]):
                    raise ValueError(
                        "A skill with this name already exists. Remove it before importing a replacement."
                    )
                s["catalog"]["skills"].append(skill)
                validate(s)
                save(s)
                return self.reply(s)
            if self.path == "/api/skills/remove":
                ident = body.get("id")
                if not any(x["id"] == ident for x in s["catalog"]["skills"]):
                    raise ValueError("Skill not found.")
                s["catalog"]["skills"] = [x for x in s["catalog"]["skills"] if x["id"] != ident]
                for agent in s["agents"]:
                    agent["skills"] = [x for x in agent["skills"] if x != ident]
                validate(s)
                save(s)
                return self.reply(s)
            if self.path == "/api/examples":
                with LOCK:
                    s = load_examples(read())
                    save(s)
                return self.reply(read())
            if self.path == "/api/oauth/start":
                return self.reply({"url": auth.start(self.server.server_port)})
            if self.path == "/api/oauth/logout":
                auth.store("oauth", {})
                auth.store("registration", {})
                return self.reply({"ok": True})
            if self.path == "/api/settings":
                if body.get("provider") not in ["demo", "chatgpt", "api"]:
                    raise ValueError("Unknown provider.")
                from urllib.parse import urlsplit

                base = body.get("base_url", "https://api.openai.com/v1").rstrip("/")
                u = urlsplit(base)
                if u.scheme != "https" and not (
                    u.scheme == "http" and u.hostname in ["127.0.0.1", "localhost"]
                ):
                    raise ValueError("Use HTTPS, or HTTP on this computer only.")
                if u.username or u.password or u.query or u.fragment:
                    raise ValueError(
                        "Use a clean API base URL without credentials or query parameters."
                    )
                model = body.get("model", "")
                if not isinstance(model, str) or len(model) > 150:
                    raise ValueError("Invalid model.")
                old = auth.settings()
                auth.store(
                    "provider",
                    {
                        "provider": body["provider"],
                        "model": "",
                        "base_url": base,
                        "api_key": body.get("api_key") or old.get("api_key", ""),
                    },
                )
                return self.reply(auth.public_settings())
            if self.path == "/api/models":
                import httpx

                conf = auth.settings()
                connection = body.get("connection", conf["provider"])
                key = auth.access() if connection == "chatgpt" else conf.get("api_key")
                if not key:
                    raise ValueError("Connect your own account first.")
                base = "https://api.openai.com/v1" if connection == "chatgpt" else conf["base_url"]
                response = httpx.get(
                    base + "/models",
                    headers={"Authorization": "Bearer " + key},
                    timeout=30,
                )
                if response.status_code != 200:
                    raise ValueError("The provider could not list models. Check your connection.")
                data = response.json()
                models = (
                    [
                        {"id": m["slug"], "name": m.get("display_name", m["slug"])}
                        for m in data.get("models", [])
                        if m.get("visibility") == "list"
                    ]
                    if connection == "chatgpt"
                    else [{"id": m["id"], "name": m["id"]} for m in data.get("data", [])]
                )
                return self.reply({"models": models})
            if self.path in ("/api/mcp/save", "/api/mcp/remove", "/api/mcp/discover"):
                import asyncio

                ident = body.get("id")
                before = next((c for c in external_mcp.connections() if c["id"] == ident), None)
                if self.path.endswith("/save"):
                    external_mcp.save_connection(body)
                elif self.path.endswith("/remove"):
                    external_mcp.remove(ident)
                else:
                    external_mcp_result = asyncio.run(external_mcp.discover(ident))
                    # Any changed schema/description revokes that grant on all agents.
                    old_tools = {t["id"]: t for t in (before or {}).get("tools", [])}
                    changed = {
                        t["id"] for t in external_mcp_result["tools"] if t != old_tools.get(t["id"])
                    }
                    for agent in s["agents"]:
                        agent["mcp"] = [
                            g
                            for g in agent["mcp"]
                            if g not in {ident + ":" + name for name in changed}
                        ]
                with LOCK:
                    s["catalog"]["mcp"] = CATALOG["mcp"] + external_mcp.connections()
                    allowed = {
                        c["id"] + ":" + t["id"] for c in s["catalog"]["mcp"] for t in c["tools"]
                    }
                    for agent in s["agents"]:
                        agent["mcp"] = [g for g in agent["mcp"] if g in allowed]
                    s["runs"] = read()["runs"]
                    save(s)
                return self.reply(s)
            if self.path == "/api/mcp/check":
                import asyncio

                from runtime import mcp_call

                return self.reply({"tools": asyncio.run(mcp_call("list")), "connected": True})
            if self.path == "/api/real-run":
                if any(j["status"] == "running" for j in JOBS.values()):
                    raise ValueError("Wait for the current run to finish.")
                conversation = None
                context_truncated = False
                if body.get("conversationId"):
                    conversation = conversations().get(body["conversationId"])
                    # Only the persisted target/history can define a conversation turn.
                    context, context_truncated = conversations().context(conversation)
                    body = {
                        "conversationId": conversation["id"],
                        "mode": conversation["mode"],
                        "agent": conversation["targetId"]
                        if conversation["mode"] == "one"
                        else None,
                        "team": conversation["targetId"]
                        if conversation["mode"] == "team"
                        else None,
                        "goal": body.get("goal", ""),
                        "conversationContext": context,
                    }
                else:
                    body.pop("conversationContext", None)
                goal = body.get("goal", "")
                if not isinstance(goal, str) or not goal.strip() or len(goal) > 8000:
                    raise ValueError("Write a message (1–8000 characters).")
                selected_team, selected_agents = resolve_target(s, body)
                if (
                    body.get("mode", "team") == "team"
                    and conversation
                    and not selected_team.get("manager")
                ):
                    raise ValueError("Choose this team's manager in Teams first.")
                for agent in selected_agents:
                    if not agent["model"]["name"]:
                        raise ValueError(agent["name"] + ": select a model in Profile first.")
                status = auth.connection_status()
                for agent in selected_agents:
                    if not status[agent["model"]["connection"]]["valid"]:
                        raise ValueError(
                            agent["name"]
                            + ": account access is not verified. Open Connection setup."
                        )
                run_config = dict(auth.settings())
                job_id = str(uuid.uuid4())
                run_config["run_id"] = job_id
                seed = {
                    "id": job_id,
                    "goal": body["goal"],
                    "mode": body.get("mode", "team"),
                    "conversationId": body.get("conversationId"),
                    "team": selected_team["name"],
                    "provider": "real",
                    "steps": [],
                    "events": [],
                    "managerId": selected_team.get("manager")
                    if body.get("mode") != "one"
                    else None,
                    "orchestration": "managed"
                    if selected_team.get("manager") and body.get("mode") != "one"
                    else "sequential",
                    "roster": [
                        {"agentId": a["id"], "agent": a["name"], "avatar": a["avatar"]}
                        for a in selected_agents
                    ],
                    "completed": False,
                }
                JOBS[job_id] = {
                    "id": job_id,
                    "status": "running",
                    "events": [],
                    "run": seed,
                    "startedAt": time.time(),
                }

                if conversation:
                    conversations().begin(conversation, body["goal"], job_id)
                save_job(JOBS[job_id])

                def work():
                    job = JOBS[job_id]

                    def emit(kind, data):
                        job["events"].append(
                            {
                                "type": kind,
                                "data": enrich(kind, data),
                                "time": time.time(),
                                "sequence": len(job["events"]) + 1,
                            }
                        )
                        job["run"]["events"] = job["events"]
                        job["run"]["steps"] = [
                            e["data"]["result"]
                            for e in job["events"]
                            if e["type"] == "step_completed"
                        ]
                        save_job(job)

                    try:
                        from runtime import execute

                        if conversation:
                            emit(
                                "conversation_context",
                                {
                                    "implementation": "conversation_store.ConversationStore",
                                    "where": "Local SQLite conversation → agent task context",
                                    "explanation": "The current message and prior completed conversation messages were supplied to the selected target.",
                                    "conversationId": conversation["id"],
                                    "priorMessages": len(body["conversationContext"]),
                                    "contextTruncated": context_truncated,
                                    "mode": body["mode"],
                                    "targetId": conversation["targetId"],
                                    "target": selected_team["name"],
                                },
                            )
                        steps = execute(s, body, emit, config=run_config)
                        run = {
                            "id": job_id,
                            "goal": body["goal"],
                            "mode": body.get("mode", "team"),
                            "team": selected_team["name"],
                            "conversationId": body.get("conversationId"),
                            "provider": "real",
                            "managerId": selected_team.get("manager")
                            if body.get("mode") != "one"
                            else None,
                            "orchestration": "managed"
                            if selected_team.get("manager") and body.get("mode") != "one"
                            else "sequential",
                            "roster": [
                                {"agentId": a["id"], "agent": a["name"], "avatar": a["avatar"]}
                                for a in selected_agents
                            ],
                            "models": [a["model"] for a in selected_agents],
                            "steps": steps,
                            "completed": True,
                            "events": job["events"],
                        }
                        emit(
                            "run_completed",
                            {
                                "implementation": "server.Handler.work",
                                "where": "Local execution worker",
                                "explanation": "The agent work completed; its results and event history are being saved.",
                            },
                        )
                        with LOCK:
                            latest = read()
                            latest["runs"] = (latest["runs"] + [run])[-200:]
                            save(latest)
                        job["run"] = run
                        job["status"] = "completed"
                    except Exception as exc:
                        job["status"] = "failed"
                        job["error"] = (
                            str(exc)
                            if isinstance(exc, ValueError)
                            else "Real run failed. Check provider access, model support and your settings. No demo result was substituted."
                        )
                        emit("run_failed", {"error": job["error"]})
                        job["run"].update(failed=True, error=job["error"], completed=False)
                        with LOCK:
                            latest = read()
                            latest["runs"] = (latest["runs"] + [job["run"]])[-200:]
                            save(latest)
                    finally:
                        if conversation:
                            conversations().finish(job)
                        save_job(job)

                threading.Thread(target=work, daemon=True).start()
                return self.reply({"id": job_id}, 202)
            if self.path == "/api/skills":
                candidate = __import__("copy").deepcopy(s)
                candidate["catalog"]["skills"] = [
                    x for x in candidate["catalog"]["skills"] if x["id"] != body.get("id")
                ] + [body]
                validate(candidate)
                save(candidate)
                return self.reply(candidate)
            if self.path == "/api/state":
                validate(body)
                with LOCK:
                    body["runs"] = read()["runs"]
                    save(body)
                return self.reply(body)
            if self.path == "/api/run":
                return self.reply(
                    {
                        "error": "Sample execution is no longer available. Open a chat with an agent or team."
                    },
                    410,
                )
            return self.reply({"error": "Not found"}, 404)
        except (ValueError, KeyError, TypeError, StopIteration) as e:
            message = str(e) or "Invalid data"
            if self.path == "/api/real-run" and not locals().get("job_id"):
                request_body = locals().get("body", {})
                request_body = request_body if isinstance(request_body, dict) else {}
                ident = str(uuid.uuid4())
                event = {
                    "type": "validation_failed",
                    "data": enrich(
                        "validation_failed",
                        {
                            "error": message,
                            "implementation": "server.Handler.do_POST",
                            "where": "Local API validation",
                            "explanation": "Execution was rejected before any agent/model ran.",
                        },
                    ),
                    "time": time.time(),
                    "sequence": 1,
                }
                rejected = {
                    "id": ident,
                    "status": "rejected",
                    "startedAt": time.time(),
                    "events": [event],
                    "error": message,
                    "run": {
                        "id": ident,
                        "goal": str(request_body.get("goal", ""))[:8000],
                        "conversationId": (locals().get("conversation") or {}).get("id"),
                        "team": str(request_body.get("team", ""))[:80],
                        "provider": "real",
                        "steps": [],
                        "events": [event],
                        "failed": True,
                        "completed": False,
                    },
                }
                current_conversation = locals().get("conversation")
                if (
                    current_conversation
                    and isinstance(request_body.get("goal"), str)
                    and request_body["goal"].strip()
                    and len(request_body["goal"]) <= 8000
                ):
                    conversations().begin(current_conversation, request_body["goal"], ident)
                    conversations().finish(rejected)
                save_job(rejected)
                return self.reply({"error": message, "id": ident}, 400)
            self.reply({"error": message}, 400)
        except Exception:
            self.reply(
                {"error": "The request failed. Check your connection settings and try again."},
                502,
            )


if __name__ == "__main__":
    recover_jobs()
    port = int(os.environ.get("PORT", "8080"))
    print(f"WABIX AgentSim: http://127.0.0.1:{port} (real AI workspace)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
