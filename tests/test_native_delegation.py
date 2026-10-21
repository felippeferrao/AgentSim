"""Real CrewAI and Responses transport against a local SSE fixture, not live AI."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from openai import OpenAI

import profiles
import server
from runtime import execute


class NativeDelegationTests(unittest.TestCase):
    def test_chatgpt_manager_transmits_and_executes_native_delegation(self):
        captured, events = [], []
        state = server.legacy_initial()
        state["teams"][0]["manager"] = "reviewer"
        for actor in state["agents"]:
            actor.update(profiles.normalize(actor))
            actor["tools"], actor["skills"], actor["mcp"] = [], [], []
            actor["model"].update(name=actor["id"], connection="chatgpt", mode="custom")

        class Fixture(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                captured.append(request)
                if len(captured) == 1:
                    item = {
                        "id": "fc_delegate",
                        "type": "function_call",
                        "call_id": "call_delegate",
                        "name": "delegate_work_to_coworker",
                        "status": "completed",
                        "arguments": json.dumps(
                            {
                                "coworker": "2. Writer — Writer",
                                "task": "Write a picnic plan",
                                "context": "Accessible park",
                            }
                        ),
                    }
                else:
                    item = {
                        "id": "msg_answer",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "annotations": [],
                                "text": "Writer completed the plan."
                                if request["model"] == "writer"
                                else "Manager checked the writer result.",
                            }
                        ],
                    }
                payload = {
                    "type": "response.completed",
                    "response": {
                        "id": "fixture",
                        "object": "response",
                        "created_at": 1,
                        "status": "completed",
                        "model": request["model"],
                        "output": [item],
                        "usage": {"input_tokens": 5, "output_tokens": 6, "total_tokens": 11},
                    },
                }
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(("data: " + json.dumps(payload) + "\n\n").encode())

            def log_message(self, *args):
                pass

        service = HTTPServer(("127.0.0.1", 0), Fixture)
        threading.Thread(target=service.serve_forever, daemon=True).start()

        def client(**kwargs):
            kwargs["base_url"] = f"http://127.0.0.1:{service.server_port}/v1"
            return OpenAI(**kwargs)

        try:
            with (
                patch("runtime.auth.access", return_value="fixture-only"),
                patch("runtime.OpenAI", client),
            ):
                result = execute(
                    state,
                    {"team": "research", "goal": "Plan a picnic"},
                    lambda kind, data: events.append((kind, data)),
                    config={},
                )
            self.assertEqual([r["agentId"] for r in result], ["writer", "reviewer"])
            self.assertEqual([r["model"] for r in captured], ["reviewer", "writer", "reviewer"])
            self.assertIn("delegate_work_to_coworker", [t["name"] for t in captured[0]["tools"]])
            self.assertEqual([t["name"] for t in captured[1]["tools"]], ["read_generated_file"])
            returned = [m for m in captured[2]["input"] if m.get("type") == "function_call_output"]
            self.assertEqual(returned[0]["call_id"], "call_delegate")
            self.assertIn("Writer completed", returned[0]["output"])
            self.assertEqual([d["toId"] for k, d in events if k == "delegation"], ["writer"])
            self.assertIn(
                "delegate_work_to_coworker",
                next(d["availableTools"] for k, d in events if k == "model_started"),
            )
        finally:
            service.shutdown()
            service.server_close()
