"""Actual CrewAI delegation with a scripted LLM, not external inference."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import auth
import profiles
import server
from runtime import ResponsesLLM, execute


class OrchestrationTests(unittest.TestCase):
    def state(self):
        state = server.initial()
        state["teams"][0]["manager"] = "reviewer"
        for a in state["agents"]:
            a.update(profiles.normalize(a))
            a["tools"], a["skills"], a["mcp"] = [], [], []
            a["model"].update(name=a["id"], connection="api", mode="custom")
        return state

    def test_team_manager_persistence_and_validation(self):
        state = self.state()
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(auth, "LOCAL", Path(temp) / "private"),
            patch.object(server, "DB", Path(temp) / "state.db"),
        ):
            server.validate(state)
            server.save(state)
            self.assertEqual(server.read()["teams"][0]["manager"], "reviewer")
            for manager, members in [
                ("missing", ["researcher", "writer"]),
                ("writer", ["writer"]),
                ("writer", ["writer", "writer"]),
            ]:
                invalid = copy.deepcopy(state)
                invalid["teams"][0].update(manager=manager, agents=members)
                with self.assertRaises(ValueError):
                    server.validate(invalid)

    def test_manager_selects_revisits_and_skips_agents_with_actual_delegation(self):
        state = self.state()
        events, calls = [], []
        manager_calls = 0
        worker_calls = 0
        role = "2. Writer — Writer"

        def scripted(llm, messages, **kwargs):
            nonlocal manager_calls, worker_calls
            calls.append(llm.model)
            llm.usage.append({"step": llm.current, "input": 10, "output": 3})
            if llm.model == "reviewer":
                manager_calls += 1
                if manager_calls < 4:
                    import json

                    args = {"coworker": role, "context": f"Revision {manager_calls}"}
                    if manager_calls == 2:
                        tool = "Ask question to coworker"
                        args["question"] = "Is this plan accessible?"
                    else:
                        tool = "Delegate work to coworker"
                        args["task"] = "Draft the plan" if manager_calls == 1 else "Revise the plan"
                    return (
                        "Thought: PRIVATE TEST REASONING\nAction: "
                        + tool
                        + "\nAction Input: "
                        + json.dumps(args)
                    )
                return "Final Answer: Manager's combined plan."
            worker_calls += 1
            return f"Final Answer: Writer reply {worker_calls}."

        with patch.object(ResponsesLLM, "call", scripted):
            result = execute(
                state,
                {"team": "research", "goal": "Plan a picnic"},
                lambda kind, data: events.append({"type": kind, "data": data}),
                config={
                    "provider": "api",
                    "base_url": "http://127.0.0.1:1/v1",
                    "api_key": "fixture-only",
                },
            )
        self.assertNotIn("researcher", calls)
        self.assertEqual([s["agentId"] for s in result], ["writer", "writer", "writer", "reviewer"])
        self.assertEqual([s["inputTokens"] for s in result], [10, 10, 10, 40])
        self.assertEqual(
            [e["data"]["kind"] for e in events if e["type"] == "delegation"],
            ["task", "question", "task"],
        )
        self.assertEqual(len([e for e in events if e["type"] == "reply"]), 3)
        first_delegation = next(i for i, e in enumerate(events) if e["type"] == "delegation")
        first_reply = next(i for i, e in enumerate(events) if e["type"] == "reply")
        self.assertTrue(
            any(
                e["type"] == "agent_started" and e["data"]["agentId"] == "writer"
                for e in events[first_delegation:first_reply]
            )
        )
        self.assertEqual(events[-1]["data"]["result"]["output"], "Manager's combined plan.")
        self.assertNotIn("PRIVATE TEST REASONING", str(events))
