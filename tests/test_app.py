"""Live local HTTP/SSE integration, with a controlled Responses fixture only."""

import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import httpx

import auth
import profiles
import server


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.patches = [
            patch.object(auth, "LOCAL", self.path / "private"),
            patch.object(server, "DB", self.path / "state.db"),
            patch.object(server, "JOBS", {}),
        ]
        for p in self.patches:
            p.start()
        captured = []
        scripts = {}

        class Fixture(BaseHTTPRequestHandler):
            def do_GET(self):
                raw = json.dumps({"data": [{"id": "model-alpha"}, {"id": "model-beta"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                captured.append(body)
                time.sleep(0.15)
                script = scripts.get(body["model"])
                answer = (
                    script.pop(0)
                    if script
                    else "Final Answer: Controlled answer from " + body["model"]
                )
                data = {
                    "type": "response.completed",
                    "response": {
                        "id": "fixture",
                        "object": "response",
                        "created_at": 1,
                        "status": "completed",
                        "model": body["model"],
                        "output": [
                            {
                                "id": "message",
                                "type": "message",
                                "role": "assistant",
                                "status": "completed",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": answer,
                                        "annotations": [],
                                    }
                                ],
                            }
                        ],
                        "usage": {"input_tokens": 17, "output_tokens": 6, "total_tokens": 23},
                    },
                }
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(("data: " + json.dumps(data) + "\n\n").encode())

            def log_message(self, *args):
                pass

        self.provider = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        self.app = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        for service in [self.provider, self.app]:
            threading.Thread(target=service.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.app.server_port}/api/"
        self.captured = captured
        self.scripts = scripts

    def tearDown(self):
        for service in [self.app, self.provider]:
            service.shutdown()
            service.server_close()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def post(self, path, body):
        return httpx.post(self.base + path, json=body, timeout=20)

    def configured_state(self):
        state = server.legacy_initial()
        state["teams"][0]["agents"] = state["teams"][0]["agents"][:2]
        for i, a in enumerate(state["agents"]):
            a.update(profiles.normalize(a))
            a["model"].update(
                mode="custom",
                connection="api",
                name=["model-alpha", "model-beta", "model-alpha"][i],
            )
        return state

    def test_disconnected_backend_blocks_real_run_without_creating_sample(self):
        state = self.configured_state()
        server.save(state)
        self.assertFalse(httpx.get(self.base + "connection/status").json()["ready"])
        response = self.post("real-run", {"goal": "Test", "team": "research"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("not verified", response.json()["error"])
        self.assertEqual(server.read()["runs"], [])

    def test_automatic_sse_two_models_and_round_trip(self):
        state = self.configured_state()
        state["agents"][0]["model"].update(temperature=0.3, maxOutputTokens=120)
        self.assertEqual(self.post("state", state).status_code, 200)
        persisted = httpx.get(self.base + "state").json()
        self.assertEqual(persisted["agents"][0]["model"]["name"], "model-alpha")
        self.post(
            "settings",
            {
                "provider": "api",
                "api_key": "fixture-only-key",
                "base_url": f"http://127.0.0.1:{self.provider.server_port}/v1",
            },
        )
        self.assertTrue(httpx.get(self.base + "connection/status").json()["api"]["valid"])
        ident = self.post(
            "real-run", {"goal": "Plan a picnic", "team": "research", "mode": "team"}
        ).json()["id"]
        snapshots = []
        with httpx.stream("GET", self.base + "jobs/" + ident + "/events", timeout=30) as stream:
            self.assertEqual(stream.headers["Content-Type"], "text/event-stream")
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    snapshots.append(json.loads(line[6:]))
        self.assertEqual(snapshots[-1]["status"], "completed")
        run = snapshots[-1]["run"]
        self.assertEqual([s["model"] for s in run["steps"]], ["model-alpha", "model-beta"])
        self.assertEqual([c["model"] for c in self.captured], ["model-alpha", "model-beta"])
        self.assertEqual(self.captured[0]["temperature"], 0.3)
        self.assertEqual(self.captured[0]["max_output_tokens"], 120)
        self.assertNotIn("temperature", self.captured[1])
        self.assertFalse(self.captured[0]["store"])
        self.assertTrue(self.captured[0]["stream"])
        self.assertEqual(run["steps"][0]["inputTokens"], 17)
        self.assertEqual(len([e for e in run["events"] if e["type"] == "step_completed"]), 2)
        self.assertEqual(server.read()["runs"][-1]["id"], ident)
        self.assertNotIn("fixture-only-key", json.dumps(snapshots))
        self.assertNotIn("sample", run["steps"][0]["output"].lower())

    def test_managed_run_streams_delegation_before_completion(self):
        state = self.configured_state()
        state["teams"][0]["manager"] = "researcher"
        for a in state["agents"]:
            a["tools"], a["skills"], a["mcp"] = [], [], []
        self.assertEqual(self.post("state", state).status_code, 200)
        self.post(
            "settings",
            {
                "provider": "api",
                "api_key": "fixture-only-key",
                "base_url": f"http://127.0.0.1:{self.provider.server_port}/v1",
            },
        )
        self.scripts["model-alpha"] = [
            'Thought: Private fixture reasoning\nAction: Delegate work to coworker\nAction Input: {"coworker":"2. Writer — Writer", "task":"Write the picnic plan", "context":"Two people"}',
            "Final Answer: The manager accepted the plan.",
        ]
        ident = self.post(
            "real-run", {"goal": "Plan a picnic", "team": "research", "mode": "team"}
        ).json()["id"]
        snapshots = []
        with httpx.stream("GET", self.base + "jobs/" + ident + "/events", timeout=30) as stream:
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    snapshots.append(json.loads(line[6:]))
        self.assertEqual(snapshots[-1]["status"], "completed")
        self.assertTrue(
            any(
                s["status"] == "running" and any(e["type"] == "delegation" for e in s["events"])
                for s in snapshots
            )
        )
        run = snapshots[-1]["run"]
        self.assertEqual(run["orchestration"], "managed")
        self.assertEqual(run["managerId"], "researcher")
        self.assertEqual([s["agentId"] for s in run["steps"]], ["writer", "researcher"])
        self.assertEqual(
            [c["model"] for c in self.captured], ["model-alpha", "model-beta", "model-alpha"]
        )
        self.assertEqual(sum(s["inputTokens"] for s in run["steps"]), 51)
        self.assertEqual(sum(s["outputTokens"] for s in run["steps"]), 18)
        self.assertIn("reply", [e["type"] for e in run["events"]])
        self.assertNotIn("Private fixture reasoning", json.dumps(run))
        self.assertEqual(server.read()["runs"][-1]["managerId"], "researcher")

    def test_skill_to_artifacts_and_persisted_failed_history(self):
        import io

        from pypdf import PdfReader

        markdown = "---\nname: checked-report\ndescription: Use for reports with checked numbers.\n---\nState that inputs are provided values, not independently verified data."
        imported = self.post("skills/import", {"markdown": markdown})
        self.assertEqual(imported.status_code, 200)
        state = self.configured_state()
        state["catalog"]["skills"] = imported.json()["catalog"]["skills"]
        state["teams"][0]["manager"] = "researcher"
        for agent in state["agents"]:
            agent["tools"] = []
            agent["skills"] = []
            agent["mcp"] = []
        state["agents"][1]["tools"] = ["pdf-generator", "chart-generator"]
        state["agents"][1]["skills"] = ["checked-report"]
        self.assertEqual(self.post("state", state).status_code, 200)
        self.post(
            "settings",
            {
                "provider": "api",
                "api_key": "fixture-only-key",
                "base_url": f"http://127.0.0.1:{self.provider.server_port}/v1",
            },
        )

        def action(name, args):
            return (
                "Thought: Private fixture reasoning\nAction: "
                + name
                + "\nAction Input: "
                + json.dumps(args)
            )

        self.scripts["model-alpha"] = [
            action(
                "use_skill",
                {
                    "skill_id": "checked-report",
                    "reason": "The report needs a clear data caveat.",
                    "agent_id": "writer",
                },
            ),
            action(
                "Delegate work to coworker",
                {
                    "coworker": "2. Writer — Writer",
                    "task": "Create a report and chart from provided counts 4 and 7.",
                    "context": "Controlled fixture",
                },
            ),
            "Final Answer: The PDF and chart are attached.",
        ]
        self.scripts["model-beta"] = [
            action(
                "pdf_generator",
                {
                    "request": "Provided values: Alpha 4; Beta 7. These are supplied inputs.",
                    "title": "Checked report",
                },
            ),
            action(
                "chart_generator",
                {
                    "request": json.dumps(
                        {"data": [{"type": "bar", "x": ["Alpha", "Beta"], "y": [4, 7]}]}
                    ),
                    "title": "Provided counts",
                },
            ),
            "Final Answer: Created the report and chart.",
        ]
        conversation = self.post("conversations", {"team": "research", "mode": "team"}).json()
        ident = self.post(
            "real-run",
            {
                "goal": "Create a checked PDF report and a chart.",
                "conversationId": conversation["id"],
            },
        ).json()["id"]
        snapshots = []
        with httpx.stream("GET", self.base + "jobs/" + ident + "/events", timeout=40) as stream:
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    snapshots.append(json.loads(line[6:]))
        job = snapshots[-1]
        self.assertEqual(job["status"], "completed", job.get("error"))
        self.assertIn("skill_selected", [e["type"] for e in job["events"]])
        artifacts = [e["data"] for e in job["events"] if e["type"] == "artifact_created"]
        self.assertEqual({a["extension"] for a in artifacts}, {"pdf", "png", "svg", "html"})
        saved_chat = httpx.get(self.base + "conversations/" + conversation["id"]).json()
        self.assertEqual(saved_chat["messages"][-1]["artifacts"], artifacts)
        self.assertTrue(
            all(e["data"].get("implementation") and e["data"].get("where") for e in job["events"])
        )
        pdf = next(a for a in artifacts if a["extension"] == "pdf")
        raw = httpx.get(self.base.removesuffix("api/") + pdf["url"].lstrip("/"))
        self.assertEqual(raw.headers["content-type"], "application/pdf")
        self.assertIn("Provided values", PdfReader(io.BytesIO(raw.content)).pages[0].extract_text())
        server.JOBS.clear()
        self.assertEqual(httpx.get(self.base + "jobs/" + ident).json()["status"], "completed")
        self.assertIn(ident, [j["id"] for j in httpx.get(self.base + "executions").json()])
        self.assertNotIn("Private fixture reasoning", json.dumps(job))
        removed = self.post("skills/remove", {"id": "checked-report"}).json()
        self.assertNotIn("checked-report", removed["agents"][1]["skills"])
        with patch("runtime.execute", side_effect=ValueError("Controlled provider failure")):
            failed_id = self.post(
                "real-run", {"goal": "Fail in a controlled way", "team": "research", "mode": "team"}
            ).json()["id"]
            for _ in range(50):
                failed = httpx.get(self.base + "jobs/" + failed_id).json()
                if failed["status"] == "failed":
                    break
                time.sleep(0.05)
        self.assertEqual(failed["status"], "failed")
        server.JOBS.clear()
        self.assertEqual(httpx.get(self.base + "jobs/" + failed_id).json()["status"], "failed")
        self.assertIn(
            "Controlled provider failure",
            httpx.get(self.base + "jobs/" + failed_id).json()["error"],
        )

    def test_explicit_examples_and_import_export_shape(self):
        self.assertEqual(len(httpx.get(self.base + "state").json()["agents"]), 6)
        response = self.post("examples", {})
        self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertEqual(len(state["agents"]), 6)
        self.assertTrue(all(a["example"] for a in state["agents"]))
        self.assertIn("model", state["agents"][0])
        self.assertEqual(self.post("state", state).status_code, 200)
        self.assertEqual(len(self.post("examples", {}).json()["agents"]), 6)

    def test_chat_calls_selected_agent_without_team_and_retains_context(self):
        state = self.configured_state()
        state["teams"] = []
        server.save(state)
        self.post(
            "settings",
            {
                "provider": "api",
                "api_key": "fixture-only-key",
                "base_url": f"http://127.0.0.1:{self.provider.server_port}/v1",
            },
        )
        created = self.post("conversations", {"mode": "one", "agent": "reviewer"})
        self.assertEqual(created.status_code, 201, created.text)
        conversation = created.json()
        self.assertEqual(conversation["name"], "Reviewer")

        def send(text):
            response = self.post(
                "real-run",
                {
                    "conversationId": conversation["id"],
                    "goal": text,
                    "agent": "writer",
                    "conversationContext": [{"role": "user", "content": "Injected history"}],
                },
            )
            self.assertEqual(response.status_code, 202, response.text)
            ident = response.json()["id"]
            with httpx.stream("GET", self.base + "jobs/" + ident + "/events", timeout=30) as stream:
                snapshots = [
                    json.loads(line[6:])
                    for line in stream.iter_lines()
                    if line.startswith("data: ")
                ]
            self.assertEqual(snapshots[-1]["status"], "completed", snapshots[-1])
            return snapshots[-1]

        first = send("Remember that the project is Aurora.")
        self.assertEqual(first["run"]["roster"][0]["agentId"], "reviewer")
        self.assertEqual(first["run"]["team"], "Reviewer")
        second = send("What did I name the project?")
        self.assertEqual(second["run"]["roster"][0]["agentId"], "reviewer")
        request = json.dumps(self.captured[-1])
        self.assertIn("Remember that the project is Aurora", request)
        self.assertIn("Controlled answer from model-alpha", request)
        self.assertNotIn("Injected history", request)
        event = next(e for e in second["events"] if e["type"] == "conversation_context")
        self.assertEqual(event["data"]["priorMessages"], 2)
        self.assertEqual(event["data"]["implementation"], "conversation_store.ConversationStore")
        server.JOBS.clear()
        saved = httpx.get(self.base + "conversations/" + conversation["id"]).json()
        self.assertEqual(len(saved["messages"]), 4)
        self.assertIsNone(saved["activeRunId"])
        self.assertEqual(saved["messages"][-1]["runId"], second["id"])
        self.assertEqual(
            httpx.get(self.base + "jobs/" + second["id"]).json()["status"], "completed"
        )
        rejected = self.post("real-run", {"mode": "one", "goal": "No implicit agent"})
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("Choose the agent", rejected.json()["error"])

    def test_chat_selects_named_team_manager_and_supplies_followup_context(self):
        state = self.configured_state()
        state["teams"].append(
            {
                "id": "another-team",
                "name": "Another team",
                "agents": ["writer", "reviewer"],
                "manager": "writer",
            }
        )
        server.save(state)
        self.post(
            "settings",
            {
                "provider": "api",
                "api_key": "fixture-only-key",
                "base_url": f"http://127.0.0.1:{self.provider.server_port}/v1",
            },
        )
        conversation = self.post("conversations", {"mode": "team", "team": "another-team"}).json()
        for text in ("Plan project Polaris.", "Continue with the plan we discussed."):
            started = self.post("real-run", {"conversationId": conversation["id"], "goal": text})
            self.assertEqual(started.status_code, 202, started.text)
            ident = started.json()["id"]
            with httpx.stream("GET", self.base + "jobs/" + ident + "/events", timeout=30) as stream:
                jobs = [
                    json.loads(line[6:])
                    for line in stream.iter_lines()
                    if line.startswith("data: ")
                ]
            self.assertEqual(jobs[-1]["status"], "completed")
            self.assertEqual(jobs[-1]["run"]["managerId"], "writer")
            self.assertEqual(
                [a["agentId"] for a in jobs[-1]["run"]["roster"]], ["writer", "reviewer"]
            )
            self.assertEqual(jobs[-1]["run"]["team"], "Another team")
        self.assertEqual(self.captured[-1]["model"], "model-beta")
        self.assertIn("Plan project Polaris", json.dumps(self.captured[-1]))
        self.assertIn("Controlled answer from model-beta", json.dumps(self.captured[-1]))

    def test_chat_preserves_rejected_and_interrupted_turns(self):
        server.save(self.configured_state())
        invalid = self.post("real-run", {"conversationId": "missing-chat", "goal": "No such chat"})
        self.assertEqual(invalid.status_code, 400)
        server.recover_jobs()  # An invalid chat reference must not break startup.
        self.assertEqual(self.post("run", {"goal": "Sample", "team": "research"}).status_code, 410)
        conversation = self.post("conversations", {"mode": "one", "agent": "writer"}).json()
        response = self.post(
            "real-run", {"conversationId": conversation["id"], "goal": "Try a disconnected turn"}
        )
        self.assertEqual(response.status_code, 400)
        rejected = response.json()["id"]
        record = server.conversations().get(conversation["id"])
        self.assertEqual(len(record["messages"]), 2)
        self.assertEqual(record["messages"][-1]["status"], "rejected")
        self.assertEqual(record["messages"][-1]["runId"], rejected)
        server.conversations().begin(
            record, "A second message interrupted by restart", "interrupted-chat-job"
        )
        job = {
            "id": "interrupted-chat-job",
            "status": "running",
            "events": [],
            "run": {
                "id": "interrupted-chat-job",
                "conversationId": conversation["id"],
                "steps": [],
                "events": [],
            },
        }
        server.save_job(job)
        server.recover_jobs()
        server.recover_jobs()
        record = server.conversations().get(conversation["id"])
        self.assertEqual(len(record["messages"]), 4)
        self.assertEqual(record["messages"][-1]["status"], "interrupted")
        self.assertIsNone(record["activeRunId"])
        context, _ = server.conversations().context(record)
        self.assertTrue(all(m["role"] == "user" for m in context))

    def test_prior_image_is_available_after_reopen_for_illustrated_pdf(self):
        self._exercise_prior_image_pdf("one")

    def test_manager_can_reuse_prior_image_and_delegate_pdf(self):
        self._exercise_prior_image_pdf("team")

    def _exercise_prior_image_pdf(self, mode):
        import io

        from PIL import Image
        from pypdf import PdfReader

        import harness

        state = self.configured_state()
        writer = next(a for a in state["agents"] if a["id"] == "writer")
        writer["tools"] = ["pdf-generator"]
        if mode == "team":
            state["teams"][0]["manager"] = "researcher"
        self.post("state", state)
        self.post(
            "settings",
            {
                "provider": "api",
                "api_key": "fixture-only-key",
                "base_url": f"http://127.0.0.1:{self.provider.server_port}/v1",
            },
        )
        chat = self.post(
            "conversations", {"mode": mode, "agent": "writer", "team": "research"}
        ).json()
        events = []
        png = io.BytesIO()
        Image.new("RGB", (240, 160), "#3a7ccc").save(png, format="PNG")
        image = harness.ArtifactStore(
            "previous-image", writer, lambda kind, data: events.append({"type": kind, "data": data})
        ).write("Saved character", "png", png.getvalue())
        store = server.conversations()
        store.begin(chat, "Create a character", "previous-image")
        store.finish(
            {
                "id": "previous-image",
                "status": "completed",
                "events": events,
                "run": {"conversationId": chat["id"], "steps": [{"output": "Character ready"}]},
            }
        )
        server.JOBS.clear()
        self.scripts[writer["model"]["name"]] = [
            "Thought: Use the saved illustration\nAction: pdf_generator\nAction Input: "
            + json.dumps(
                {
                    "request": json.dumps(
                        {
                            "pages": [
                                {"text": "A new illustrated adventure.", "image_url": image["url"]}
                            ]
                        }
                    ),
                    "title": "Follow-up comic",
                }
            ),
            "Final Answer: The illustrated PDF is ready.",
        ]
        if mode == "team":
            self.scripts["model-alpha"] = [
                "Thought: Inspect the saved file\nAction: read_generated_file\nAction Input: "
                + json.dumps({"url": image["url"]}),
                "Thought: Delegate the document\nAction: Delegate work to coworker\nAction Input: "
                + json.dumps(
                    {
                        "coworker": "2. Writer — Writer",
                        "task": "Make the illustrated PDF with the saved image",
                        "context": image["url"],
                    }
                ),
                "Final Answer: The illustrated PDF is ready.",
            ]
        started = self.post(
            "real-run",
            {
                "conversationId": chat["id"],
                "goal": "Make a PDF comic using the previous image",
                "conversationArtifacts": [{"url": "/artifacts/foreign/fake.png"}],
            },
        )
        self.assertEqual(started.status_code, 202, started.text)
        ident = started.json()["id"]
        with httpx.stream("GET", self.base + "jobs/" + ident + "/events", timeout=30) as stream:
            snapshots = [
                json.loads(line[6:]) for line in stream.iter_lines() if line.startswith("data: ")
            ]
        job = snapshots[-1]
        self.assertEqual(job["status"], "completed", job.get("error"))
        public = next(e["data"] for e in job["events"] if e["type"] == "conversation_context")
        self.assertEqual(public["availableArtifacts"][0]["url"], image["url"])
        self.assertNotIn("foreign/fake", json.dumps(self.captured))
        self.assertIn("artifact_reused", [e["type"] for e in job["events"]])
        pdf = next(e["data"] for e in job["events"] if e["type"] == "artifact_created")
        raw = httpx.get(self.base.removesuffix("api/") + pdf["url"].lstrip("/"))
        page = PdfReader(io.BytesIO(raw.content)).pages[0]
        self.assertEqual(len(page.images), 1)
        self.assertIn("illustrated adventure", page.extract_text())
        reopened = server.conversations().get(chat["id"])
        self.assertEqual({a["extension"] for a in store.artifacts(reopened)}, {"pdf", "png"})
