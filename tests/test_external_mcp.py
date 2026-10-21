import asyncio
import copy
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

import auth
import external_mcp
import server
from runtime import ResponsesLLM, execute, http_tools

ROOT = Path(__file__).resolve().parents[1]


class ExternalMCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.key = secrets.token_urlsafe(24)
        cls.process = subprocess.Popen(
            [sys.executable, str(ROOT / "tests/fixture_mcp_http.py")],
            env=os.environ | {"MCP_FIXTURE_PORT": str(cls.port), "MCP_FIXTURE_KEY": cls.key},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls.url = f"http://127.0.0.1:{cls.port}/mcp"
        for _ in range(100):
            try:
                if httpx.get(cls.url, timeout=0.2).status_code == 401:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        cls.process.terminate()
        raise RuntimeError("Controlled MCP server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(auth, "LOCAL", Path(self.temp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def connection(self, kind="bearer"):
        return external_mcp.save_connection(
            {
                "id": "controlled",
                "name": "Controlled HTTP server",
                "url": self.url,
                "authType": kind,
                "headerName": "X-API-Key",
                "credential": self.key,
            }
        )

    def discover(self):
        return asyncio.run(external_mcp.discover("controlled"))

    def test_authenticated_discovery_call_and_secret_isolation(self):
        public = self.connection()
        self.assertNotIn(self.key, json.dumps(public))
        record = self.discover()
        self.assertEqual({t["id"] for t in record["tools"]}, {"count_items", "server_note"})
        tool = next(t for t in record["tools"] if t["id"] == "count_items")
        result = asyncio.run(
            external_mcp.call(
                "controlled",
                "count_items",
                {"items": ["a", "b"], "label": "apples"},
                ["controlled:count_items"],
                tool,
            )
        )
        self.assertEqual(result, "2 apples")
        self.assertEqual((Path(self.temp.name) / "mcp.json").stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.key, json.dumps(external_mcp.connections()))

    def test_custom_header_and_unauthorized_error(self):
        self.connection("header")
        self.assertEqual(self.discover()["status"], "Connected")
        external_mcp.save_connection(
            {
                "id": "controlled",
                "name": "Controlled HTTP server",
                "url": self.url,
                "authType": "bearer",
                "credential": "wrong-fixture-token",
            }
        )
        with self.assertRaisesRegex(ValueError, "access denied"):
            self.discover()

    def test_permissions_schema_changed_tool_and_removal(self):
        self.connection()
        record = self.discover()
        tool = next(t for t in record["tools"] if t["id"] == "count_items")
        with self.assertRaisesRegex(ValueError, "not allowed"):
            asyncio.run(external_mcp.call("controlled", "count_items", {"items": []}, [], tool))
        with self.assertRaisesRegex(ValueError, "input schema"):
            asyncio.run(
                external_mcp.call(
                    "controlled",
                    "count_items",
                    {"items": "not an array"},
                    ["controlled:count_items"],
                    tool,
                )
            )
        changed = copy.deepcopy(tool)
        changed["description"] = "Changed"
        with self.assertRaisesRegex(ValueError, "changed"):
            asyncio.run(
                external_mcp.call(
                    "controlled", "count_items", {"items": []}, ["controlled:count_items"], changed
                )
            )
        external_mcp.remove("controlled")
        with self.assertRaisesRegex(ValueError, "removed"):
            asyncio.run(
                external_mcp.call(
                    "controlled", "count_items", {"items": []}, ["controlled:count_items"], tool
                )
            )

    def test_actual_crewai_calls_external_tool_with_scripted_llm(self):
        self.connection()
        record = self.discover()
        state = server.legacy_initial()
        state["catalog"]["mcp"] = state["catalog"]["mcp"] + [record]
        state["agents"][0]["mcp"] = ["controlled:count_items"]
        state["agents"][0]["model"] = {
            "mode": "custom",
            "name": "fixture",
            "connection": "api",
            "temperature": None,
            "maxOutputTokens": None,
            "contextWindow": 32000,
        }
        events = []
        calls = []
        llm = ResponsesLLM({"provider": "api", "model": "fixture"}, lambda *args: None)
        name = http_tools(state["agents"][0], [record], lambda *args: None, llm)[0].name

        def scripted(llm, messages, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                return (
                    "Thought: Count the list.\nAction: "
                    + name
                    + '\nAction Input: {"items":["apple","pear"],"label":"fruit"}'
                )
            return "Final Answer: We have 2 fruit."

        with patch.object(ResponsesLLM, "call", scripted):
            steps = execute(
                state,
                {
                    "goal": "Count two fruit",
                    "team": "research",
                    "mode": "one",
                    "agent": "researcher",
                },
                lambda k, d: events.append((k, d)),
                config={"provider": "api", "model": "fixture"},
            )
        self.assertIn("2 fruit", steps[0]["output"])
        self.assertTrue(
            any(k == "tool_completed" and d["name"] == "controlled:count_items" for k, d in events)
        )
        self.assertIn("2 fruit", str(calls[1]))
        self.assertNotIn(self.key, json.dumps(events))

    def test_http_management_roundtrip_and_permission_revocation(self):
        import threading
        from http.server import ThreadingHTTPServer

        with patch.object(server, "DB", Path(self.temp.name) / "app.db"):
            web = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            threading.Thread(target=web.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{web.server_port}/api/"

            def post(path, data):
                response = httpx.post(base + path, json=data, timeout=20)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn(self.key, response.text)
                return response.json()

            try:
                body = {
                    "id": "controlled",
                    "name": "Controlled HTTP server",
                    "url": self.url,
                    "authType": "bearer",
                    "credential": self.key,
                }
                state = post("mcp/save", body)
                self.assertEqual(state["catalog"]["mcp"][-1]["tools"], [])
                state = post("mcp/discover", {"id": "controlled"})
                self.assertEqual(len(state["catalog"]["mcp"][-1]["tools"]), 2)
                state = post("examples", {})
                state["agents"][0]["mcp"] = ["controlled:count_items"]
                post("state", state)
                state = post("mcp/discover", {"id": "controlled"})
                self.assertEqual(state["agents"][0]["mcp"], ["controlled:count_items"])
                state = post("mcp/save", body | {"name": "Edited connection", "credential": ""})
                self.assertEqual(state["agents"][0]["mcp"], [])
                self.assertTrue(state["catalog"]["mcp"][-1]["hasCredential"])
                state = post("mcp/discover", {"id": "controlled"})
                self.assertEqual(state["agents"][0]["mcp"], [])
                state = post("mcp/remove", {"id": "controlled"})
                self.assertEqual(len(state["catalog"]["mcp"]), 1)
                self.assertNotIn("controlled", external_mcp.registry())
            finally:
                web.shutdown()
                web.server_close()

    def test_optional_arguments_and_changed_endpoint_revision(self):
        self.connection()
        record = self.discover()
        helper = {"mcp": ["controlled:count_items"]}
        llm = ResponsesLLM({"provider": "api", "model": "fixture"}, lambda *args: None)
        wrapper = http_tools(helper, [record], lambda *args: None, llm)[0]
        structured = wrapper.to_structured_tool()
        self.assertEqual(structured.invoke({"items": ["apple"]}), "1 items")
        self.connection()
        self.discover()
        with self.assertRaisesRegex(ValueError, "changed"):
            wrapper._run(items=["apple"])

    def test_saved_api_credential_is_not_assumed_valid(self):
        auth.store(
            "provider",
            {"provider": "api", "api_key": "wrong-fixture-key", "base_url": self.url, "model": ""},
        )
        self.assertTrue(auth.public_settings()["has_key"])
        status = auth.connection_status()
        self.assertTrue(status["api"]["configured"])
        self.assertFalse(status["api"]["valid"])
        self.assertFalse(status["ready"])

    def test_plain_import_cannot_install_connection(self):
        state = server.legacy_initial()
        state["catalog"]["mcp"].append({"id": "unregistered", "name": "No", "tools": []})
        with self.assertRaisesRegex(ValueError, "Imports cannot"):
            server.validate(state)

    def test_url_credentials_and_protocol_headers_rejected(self):
        for url in [
            "https://x.example/mcp?token=secret",
            "https://secret@x.example/mcp",
            "http://external.example/mcp",
        ]:
            with self.assertRaises(ValueError):
                external_mcp.save_connection({"id": "bad", "name": "Bad", "url": url})
        with self.assertRaisesRegex(ValueError, "reserved"):
            external_mcp.save_connection(
                {
                    "id": "bad",
                    "name": "Bad",
                    "url": self.url,
                    "authType": "header",
                    "headerName": "Host",
                    "credential": self.key,
                }
            )
