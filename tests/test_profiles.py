import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crewai import Agent, Task

import auth
import profiles
import server
from runtime import ResponsesLLM, execute


def configured(name="model-alpha", connection="api"):
    return {
        "mode": "custom",
        "name": name,
        "connection": connection,
        "temperature": None,
        "maxOutputTokens": None,
        "contextWindow": 32000,
    }


class ProfileTests(unittest.TestCase):
    def test_persistent_legacy_migration_preserves_data(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(server, "DB", Path(d) / "state.db"),
            patch.object(auth, "LOCAL", Path(d) / "private"),
        ):
            old = server.legacy_initial()
            old["agents"][0]["tools"] = ["calculator"]
            server.save(old)
            migrated = server.read()
            agent = migrated["agents"][0]
            self.assertEqual(agent["goal"], old["agents"][0]["job"])
            self.assertEqual(agent["tools"], ["calculator"])
            self.assertEqual(agent["avatar"], "researcher")
            self.assertTrue(agent["example"])
            self.assertEqual(migrated["teams"][0]["agents"], old["teams"][0]["agents"])
            self.assertEqual(migrated["teams"][0]["id"], old["teams"][0]["id"])
            self.assertTrue(migrated["teams"][0]["example"])
            with server.connect() as db:
                stored = db.execute("SELECT data FROM state").fetchone()[0]
            self.assertIn("profileVersion", stored)
            self.assertEqual(server.read(), migrated)

    def test_starter_first_start_and_examples_are_non_destructive(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(server, "DB", Path(d) / "new.db"),
            patch.object(auth, "LOCAL", Path(d) / "private"),
        ):
            self.assertEqual(len(server.read()["agents"]), 6)
            state = server.blank()
            mine = copy.deepcopy(server.legacy_initial()["agents"][0])
            mine.update(id="mine", name="My helper", job="My own goal")
            state["agents"] = [mine]
            result = server.load_examples(state)
            self.assertEqual(result["agents"][0], mine)
            self.assertEqual(len(result["agents"]), 7)
            self.assertEqual(len(server.load_examples(result)["agents"]), 7)

    def test_rich_profile_round_trip_and_validation(self):
        state = server.legacy_initial()
        a = profiles.normalize(state["agents"][0])
        a.update(
            role="Picnic researcher",
            goal="Find safe picnic ideas",
            backstory="You know outdoor planning.",
            instructions="Ask about allergies.",
            purpose="Help a family prepare.",
            exampleInput="Picnic for two?",
            exampleOutput="Bring water and fruit.",
            expectedOutput="Three steps and a packing list.",
            avatar="reviewer",
            model=configured(),
        )
        state["agents"][0] = a
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(server, "DB", Path(d) / "roundtrip.db"),
            patch.object(auth, "LOCAL", Path(d) / "private"),
        ):
            server.validate(state)
            server.save(state)
            loaded = server.read()["agents"][0]
            self.assertEqual(loaded, a)
        bad = copy.deepcopy(a)
        bad["behavior"]["maxIterations"] = 999
        with self.assertRaises(ValueError):
            profiles.validate(bad)
        bad = copy.deepcopy(a)
        bad["model"]["connection"] = "unknown"
        with self.assertRaises(ValueError):
            profiles.validate(bad)
        bad = copy.deepcopy(a)
        bad["avatar"] = "imaginary-new-asset"
        with self.assertRaises(ValueError):
            profiles.validate(bad)

    def test_crewai_profile_mapping_and_heterogeneous_agent_models(self):
        state = server.legacy_initial()
        state["teams"][0]["agents"] = state["teams"][0]["agents"][:2]
        first = profiles.normalize(state["agents"][0])
        first.update(
            role="Research specialist",
            goal="Find picnic ideas",
            backstory="Know outdoor planning.",
            instructions="Write clear steps.",
            purpose="Help families.",
            exampleInput="Picnic?",
            exampleOutput="Bring water.",
            expectedOutput="A packing list.",
            avatar="robot",
            model=configured("model-alpha", "chatgpt"),
        )
        first["behavior"].update(
            maxIterations=4,
            maxRetries=1,
            maxExecutionSeconds=1200,
            maxRequestsPerMinute=20,
            respectContextWindow=False,
        )
        second = profiles.normalize(state["agents"][1])
        second["model"] = configured("model-beta", "api")
        state["agents"][:2] = [first, second]
        configs = []

        def scripted(llm, messages, **kwargs):
            configs.append(llm.config)
            if llm.model == "model-alpha":
                for term in [
                    "Research specialist",
                    "outdoor planning",
                    "Write clear steps",
                    "teaching_examples",
                    "Bring water.",
                ]:
                    self.assertIn(term, str(messages))
            return "Final Answer: A useful packing list."

        with (
            patch("runtime.Agent", wraps=Agent) as agents,
            patch("runtime.Task", wraps=Task) as tasks,
            patch.object(ResponsesLLM, "call", scripted),
        ):
            steps = execute(
                state,
                {"goal": "Plan a picnic", "team": "research"},
                lambda *args: None,
                config={
                    "provider": "api",
                    "api_key": "fixture-only",
                    "base_url": "http://127.0.0.1:1/v1",
                    "model": "must-not-override",
                },
            )
        self.assertEqual(
            [(c["provider"], c["model"]) for c in configs],
            [("chatgpt", "model-alpha"), ("api", "model-beta")],
        )
        self.assertEqual(agents.call_args_list[0].kwargs["max_iter"], 4)
        self.assertEqual(agents.call_args_list[0].kwargs["max_retry_limit"], 1)
        self.assertEqual(agents.call_args_list[0].kwargs["max_execution_time"], 1200)
        self.assertEqual(agents.call_args_list[0].kwargs["max_rpm"], 20)
        self.assertFalse(agents.call_args_list[0].kwargs["respect_context_window"])
        self.assertEqual(tasks.call_args_list[0].kwargs["expected_output"], "A packing list.")
        self.assertEqual(steps[0]["avatar"], "robot")
        self.assertEqual([s["model"] for s in steps], ["model-alpha", "model-beta"])
