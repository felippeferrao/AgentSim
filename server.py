"""AgentSim: local teaching app. No external inference or code execution."""

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

LOCK = threading.RLock()
JOBS = {}
ROOT = Path(__file__).parent
DB = Path(os.environ.get("AGENTSIM_DB", str(ROOT / "agentsim.db")))
CATALOG = {
    "tools": [
        {
            "id": "calculator",
            "name": "Calculator",
            "description": "Calculate numbers with + - * /.",
        }
    ],
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
    return db


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
        "catalog": CATALOG,
        "runs": [],
    }


def read():
    with connect() as db:
        row = db.execute("SELECT data FROM state WHERE id=1").fetchone()
    return json.loads(row[0]) if row else initial()


def save(s):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO state VALUES (1,?)", (json.dumps(s),))


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
            ids.append(a["id"])
            if kind == "agents":
                if (
                    set(a) != {"id", "name", "job", "tools", "skills", "mcp"}
                    or not isinstance(a["job"], str)
                    or len(a["job"]) > 500
                ):
                    raise ValueError("Invalid agent fields.")
            elif set(a) != {"id", "name", "agents"}:
                raise ValueError("Invalid team fields.")
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate ids.")
    catalog = s["catalog"]
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"tools", "skills", "mcp"}
        or catalog["tools"] != CATALOG["tools"]
        or catalog["mcp"] != CATALOG["mcp"]
    ):
        raise ValueError("Only built-in tools and MCP connections are allowed in this version.")
    if not isinstance(catalog["skills"], list) or len(catalog["skills"]) > 30:
        raise ValueError("Use at most 30 skills.")
    skill_ids = []
    for skill in catalog["skills"]:
        if not isinstance(skill, dict) or set(skill) != {
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
            ("description", 500),
            ("instructions", 4000),
        ]:
            if not isinstance(skill[key], str) or not 0 < len(skill[key]) <= limit:
                raise ValueError("Invalid skill text.")
        if not __import__("re").fullmatch(r"[a-z0-9-]+", skill["id"]):
            raise ValueError("Skill id uses lowercase letters, numbers and hyphens.")
        if not isinstance(skill["requires"], list) or any(
            x not in ["calculator", "documents:search", "documents:read"] for x in skill["requires"]
        ):
            raise ValueError("Unknown skill dependency.")
        skill_ids.append(skill["id"])
    if len(set(skill_ids)) != len(skill_ids):
        raise ValueError("Duplicate skill ids.")
    for a in s["agents"]:
        for k, allowed in [
            ("tools", ["calculator"]),
            ("skills", skill_ids),
            ("mcp", ["documents:search", "documents:read"]),
        ]:
            if not isinstance(a[k], list) or any(v not in allowed for v in a[k]):
                raise ValueError("Unknown assignment.")
    for t in s["teams"]:
        if not isinstance(t["agents"], list) or any(
            x not in [a["id"] for a in s["agents"]] for x in t["agents"]
        ):
            raise ValueError("Unknown team member.")
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
        raise ValueError("Add a helper to this team first.")
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
                message = "Signed in. Return to AgentSim and choose your model in Connection setup."
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
        if url.path.startswith("/api/jobs/"):
            job = JOBS.get(url.path.rsplit("/", 1)[-1])
            return self.reply(job or {"error": "Run not found"}, 200 if job else 404)
        if self.path == "/api/settings":
            return self.reply(auth.public_settings())
        if self.path == "/api/state":
            return self.reply(read())
        if self.path == "/api/connection":
            return self.reply(auth.public_settings())
        path = ROOT / "static" / ("index.html" if self.path == "/" else self.path.lstrip("/"))
        if path.parent != ROOT / "static" or not path.is_file():
            return self.reply({"error": "Not found"}, 404)
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            {"html": "text/html", "css": "text/css", "js": "text/javascript"}.get(
                path.suffix[1:], "text/plain"
            ),
        )
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
            if size > 200000:
                raise ValueError("File is too large. Limit: 200 KB.")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object.")
            s = read()
            if self.path == "/api/oauth/start":
                return self.reply({"url": auth.start(self.server.server_port)})
            if self.path == "/api/oauth/logout":
                auth.store("oauth", {})
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
                        "model": model,
                        "base_url": base,
                        "api_key": body.get("api_key") or old.get("api_key", ""),
                    },
                )
                return self.reply(auth.public_settings())
            if self.path == "/api/models":
                import httpx

                conf = auth.settings()
                key = auth.access() if conf["provider"] == "chatgpt" else conf.get("api_key")
                if not key:
                    raise ValueError("Connect your own account first.")
                base = (
                    "https://api.openai.com/v1"
                    if conf["provider"] == "chatgpt"
                    else conf["base_url"]
                )
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
                    if conf["provider"] == "chatgpt"
                    else [{"id": m["id"], "name": m["id"]} for m in data.get("data", [])]
                )
                return self.reply({"models": models})
            if self.path == "/api/mcp/check":
                import asyncio

                from runtime import mcp_call

                return self.reply({"tools": asyncio.run(mcp_call("list")), "connected": True})
            if self.path == "/api/real-run":
                if any(j["status"] == "running" for j in JOBS.values()):
                    raise ValueError("Wait for the current run to finish.")
                # Validate goal and membership before starting a background worker.
                make_run(s, body)
                run_config = auth.settings()
                job_id = str(uuid.uuid4())
                JOBS[job_id] = {
                    "id": job_id,
                    "status": "running",
                    "events": [],
                    "run": None,
                }

                def work():
                    job = JOBS[job_id]

                    def emit(kind, data):
                        job["events"].append({"type": kind, "data": data, "time": time.time()})

                    try:
                        from runtime import execute

                        steps = execute(s, body, emit, config=run_config)
                        run = {
                            "id": job_id,
                            "goal": body["goal"],
                            "mode": body.get("mode", "team"),
                            "team": next(t["name"] for t in s["teams"] if t["id"] == body["team"]),
                            "provider": run_config["provider"],
                            "model": run_config["model"],
                            "steps": steps,
                            "completed": True,
                            "events": job["events"],
                        }
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
                run = make_run(s, body)
                s["runs"] = (s["runs"] + [run])[-200:]
                save(s)
                return self.reply(run)
            return self.reply({"error": "Not found"}, 404)
        except (ValueError, KeyError, TypeError, StopIteration) as e:
            self.reply({"error": str(e) or "Invalid data"}, 400)
        except Exception:
            self.reply(
                {"error": "The request failed. Check your connection settings and try again."},
                502,
            )


if __name__ == "__main__":
    print("AgentSim: http://127.0.0.1:8080 (Demo + real CrewAI)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
