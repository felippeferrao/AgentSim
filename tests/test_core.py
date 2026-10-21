import asyncio
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import auth
import server
from runtime import ResponsesLLM, calculate, execute, mcp_call


class CoreTests(unittest.TestCase):
    def test_new_installation_creates_starter_database_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fresh.sqlite3"
            credentials = Path(directory) / "credentials"
            with patch.object(server, "DB", database), patch.object(auth, "LOCAL", credentials):
                self.assertFalse(database.exists())
                state = server.read()
                self.assertTrue(database.is_file())
                self.assertEqual(len(state["agents"]), 6)
                self.assertEqual(state["teams"][0]["manager"], "orchestrator")
                self.assertEqual(state["runs"], [])
                self.assertEqual(server.execution_history(), [])
                self.assertFalse(credentials.exists())

    def test_import_rejects_unknown_permissions_and_code(self):
        s = server.legacy_initial()
        s["agents"][0]["mcp"] = ["documents:delete"]
        with self.assertRaises(ValueError):
            server.validate(s)
        s = server.legacy_initial()
        s["agents"][0]["command"] = "rm anything"
        with self.assertRaises(ValueError):
            server.validate(s)

    def test_import_rejects_broken_membership(self):
        s = server.legacy_initial()
        s["teams"][0]["agents"] = ["missing"]
        with self.assertRaises(ValueError):
            server.validate(s)

    def test_demo_is_deterministic_and_never_real_usage(self):
        s = server.legacy_initial()
        b = {"goal": "Plan a picnic", "team": "research"}
        a = server.make_run(s, b)
        c = server.make_run(s, b)
        self.assertEqual(a["steps"], c["steps"])
        self.assertIsNone(a["steps"][0]["inputTokens"])
        self.assertEqual(server.make_run(s, {**b, "mode": "one"})["steps"].__len__(), 1)

    def test_calculator_cannot_execute_code(self):
        self.assertEqual(calculate("(12+3)*2"), "30")
        for bad in ['__import__("os")', "2**100000", "a.b", "[1]*20"]:
            with self.assertRaises(ValueError):
                calculate(bad)

    def test_mcp_real_transport_discovery_and_call(self):
        tools = asyncio.run(mcp_call("list"))
        self.assertEqual({t["name"] for t in tools}, {"search", "read"})
        self.assertIn("blanket", asyncio.run(mcp_call("read", {"document_id": "picnic"})))

    def test_oauth_has_independent_host_pkce_and_one_time_state(self):
        from urllib.parse import parse_qs, urlparse

        with tempfile.TemporaryDirectory() as d, patch.object(auth, "LOCAL", Path(d)):
            q = parse_qs(urlparse(auth.start(8080)).query)
            self.assertEqual(q["client_id"], ["dynamic_agent_client"])
            self.assertEqual(q["redirect_uri"], ["http://127.0.0.1:8080/auth/callback"])
            self.assertIn("chatgpt.tokens.use.direct", q["scope"][0])
            host = q["ext_agent_host_id"]
            q2 = parse_qs(urlparse(auth.start(8080)).query)
            self.assertEqual(host, q2["ext_agent_host_id"])
            with self.assertRaises(ValueError):
                auth.callback({"state": "wrong"})
            with self.assertRaises(ValueError):
                auth.callback({"state": q2["state"][0], "error": "access_denied"})
            with self.assertRaises(ValueError):
                auth.callback({"state": q2["state"][0]})
            self.assertEqual((Path(d) / "host.json").stat().st_mode & 0o777, 0o600)

    def test_oauth_callback_validates_signed_identity_before_saving(self):
        import time
        from types import SimpleNamespace
        from urllib.parse import parse_qs, urlparse

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        with tempfile.TemporaryDirectory() as d, patch.object(auth, "LOCAL", Path(d)):
            query = parse_qs(urlparse(auth.start(8080)).query)
            state = query["state"][0]
            nonce = query["nonce"][0]
            private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            claims = {
                "iss": auth.AUTH,
                "aud": "oaiapp_fixture",
                "sub": "fixture-user",
                "nonce": nonce,
                "exp": time.time() + 300,
            }
            token = jwt.encode(claims, private, algorithm="RS256")
            payload = {
                "id_token": token,
                "access_token": "fixture-access",
                "refresh_token": "fixture-refresh",
                "scope": "openid chatgpt.tokens.use.direct",
                "expires_in": 3600,
            }
            response = SimpleNamespace(status_code=200, json=lambda: payload)
            client = SimpleNamespace(
                get_signing_key_from_jwt=lambda value: SimpleNamespace(key=private.public_key())
            )
            with (
                patch("auth.httpx.post", return_value=response),
                patch("auth.jwt.PyJWKClient", return_value=client),
            ):
                auth.callback(
                    {
                        "state": state,
                        "code": "fixture-code",
                        "client_id": "oaiapp_fixture",
                    }
                )
            self.assertEqual(auth.load("oauth")["subject"], "fixture-user")
            self.assertEqual(auth.access(), "fixture-access")
            self.assertFalse("access_token" in auth.public_settings())
            # A returned client id cannot replace a registration on reauthorization.
            query = parse_qs(urlparse(auth.start(8080)).query)
            with self.assertRaisesRegex(ValueError, "expected client"):
                auth.callback(
                    {
                        "state": query["state"][0],
                        "code": "fixture-code",
                        "client_id": "wrong-client",
                    }
                )

    def test_incomplete_oauth_registration_retry_is_not_a_connection(self):
        from types import SimpleNamespace
        from urllib.parse import parse_qs, urlparse

        with tempfile.TemporaryDirectory() as d, patch.object(auth, "LOCAL", Path(d)):
            q = parse_qs(urlparse(auth.start(8080)).query)
            failure = SimpleNamespace(status_code=400, json=lambda: {"error": "invalid_grant"})
            with patch("auth.httpx.post", return_value=failure):
                with self.assertRaisesRegex(ValueError, "retained"):
                    auth.callback(
                        {
                            "state": q["state"][0],
                            "code": "fixture",
                            "client_id": "oaiapp_incomplete_fixture",
                        }
                    )
            retry = parse_qs(urlparse(auth.start(8080)).query)
            self.assertEqual(retry["client_id"], ["oaiapp_incomplete_fixture"])
            self.assertNotIn("agent_name_hint", retry)
            self.assertFalse(auth.public_settings()["oauth_connected"])
            self.assertFalse(auth.connection_status()["ready"])

    def test_skill_import_is_declarative_and_never_grants_tools(self):
        s = copy.deepcopy(server.legacy_initial())
        skill = {
            "id": "budget",
            "name": "Budget",
            "description": "Check picnic cost",
            "instructions": "Use calculator for the total.",
            "requires": ["calculator"],
        }
        s["catalog"]["skills"].append(skill)
        s["agents"][0]["skills"] = ["budget"]
        for helper in s["agents"]:
            helper["model"] = {
                "mode": "custom",
                "name": "fixture",
                "connection": "api",
                "temperature": None,
                "maxOutputTokens": None,
                "contextWindow": 32000,
            }
        server.validate(s)
        self.assertEqual(s["agents"][0]["tools"], [])
        with patch(
            "runtime.auth.settings",
            return_value={"provider": "api", "model": "fixture"},
        ):
            with self.assertRaisesRegex(ValueError, "explicit permission"):
                execute(s, {"goal": "Picnic budget", "team": "research"}, lambda *args: None)
        s["catalog"]["skills"][-1]["command"] = "execute me"
        with self.assertRaises(ValueError):
            server.validate(s)

    def test_actual_crewai_tasks_with_scripted_provider(self):
        # Integration test of real CrewAI; scripted LLM is NOT external inference.
        state = server.legacy_initial()
        for helper in state["agents"]:
            helper["model"] = {
                "mode": "custom",
                "name": "fixture",
                "connection": "api",
                "temperature": None,
                "maxOutputTokens": None,
                "contextWindow": 32000,
            }
        state["agents"][0]["tools"] = ["calculator"]
        state["agents"][0]["mcp"] = ["documents:search"]
        state["agents"][0]["skills"] = ["clear-writing"]
        events = []
        calls = []

        def scripted(llm, messages, **kwargs):
            calls.append(llm.current)
            if len(calls) == 1:
                return 'Thought: I should use the assigned calculator.\nAction: calculator\nAction Input: {"expression":"2+3"}'
            if len(calls) == 2:
                return 'Thought: Find picnic facts.\nAction: documents_search\nAction Input: {"query":"picnic"}'
            if len(calls) == 3:
                return 'Thought: Use the writing skill.\nAction: use_skill\nAction Input: {"skill_id":"clear-writing","reason":"Keep the picnic instructions easy to follow.","agent_id":""}'
            if llm.current == 0:
                self.assertIn("short sentences", str(messages))
            return "Final Answer: Bring five sandwiches and water."

        with (
            patch(
                "runtime.auth.settings",
                return_value={"provider": "api", "model": "contract-fixture"},
            ),
            patch.object(ResponsesLLM, "call", scripted),
        ):
            steps = execute(
                state,
                {"goal": "Plan a picnic for five", "team": "research"},
                lambda k, d: events.append((k, d)),
            )
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[1]["input"], steps[0]["output"])
        self.assertTrue(any(k == "tool_completed" and d["output"] == "5" for k, d in events))
        self.assertTrue(
            any(
                k == "tool_completed"
                and d["name"] == "documents:search"
                and "blanket" in d["output"]
                for k, d in events
            )
        )
        self.assertNotIn("Thought:", steps[0]["output"])
        self.assertIsNone(steps[0]["inputTokens"])


if __name__ == "__main__":
    unittest.main()
