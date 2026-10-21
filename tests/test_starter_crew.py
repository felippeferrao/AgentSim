"""The portable crew seed and actual five-specialist delegation with local renderer fixtures."""

import io
import json
import sqlite3
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader

import auth
import harness
import server
import starter_crew
from artifact_history import artifact_path
from runtime import ResponsesLLM, execute


class StarterCrewTests(unittest.TestCase):
    def test_seed_has_only_configuration_and_matches_default(self):
        seed = starter_crew.DIRECTORY / "starter.sqlite3"
        with sqlite3.connect(f"file:{seed}?mode=ro", uri=True) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT count(*) FROM executions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM conversations").fetchone()[0], 0)
            state = json.loads(db.execute("SELECT data FROM state").fetchone()[0])
        self.assertEqual(state, server.initial())
        self.assertEqual(state["runs"], [])
        self.assertEqual(state["teams"][0]["manager"], "orchestrator")
        self.assertEqual([a["id"] for a in state["agents"]], ["orchestrator", *starter_crew.STAGES])
        self.assertEqual(
            {a["id"]: a["tools"] for a in state["agents"] if a["tools"]},
            {"illustrator": ["image-generator"], "pdf-generator": ["pdf-generator"]},
        )
        self.assertNotIn("api_key", json.dumps(state))
        self.assertNotIn("access_token", json.dumps(state))
        self.assertTrue(all(a["instructions"] and a["expectedOutput"] for a in state["agents"]))

    def test_publication_requires_current_order_and_approval(self):
        results = [
            {"agentId": ident, "output": "APPROVED" if ident == "quality-validator" else "Completed"}
            for ident in starter_crew.STAGES
        ]
        self.assertIsNone(starter_crew.stage_problem(results))
        results[3]["output"] = "CHANGES REQUIRED"
        self.assertIn("not approved", starter_crew.stage_problem(results))
        results[3]["output"] = "APPROVED"
        results.append({"agentId": "scriptwriter", "output": "Revised story"})
        self.assertIn("revised", starter_crew.stage_problem(results))
        events = []
        tool = harness.IntegrationTool(
            name="pdf_generator",
            description="Publish a validated comic PDF",
            tool_id="pdf-generator",
            actor={"id": "pdf-generator", "name": "PDF Generator"},
            llm_adapter=SimpleNamespace(config={"provider": "api", "comicStages": []}),
            event_sink=lambda k, d: events.append(k),
            run_id="blocked",
        )
        with self.assertRaisesRegex(ValueError, "publication blocked"):
            tool._run("Publish too early")
        self.assertNotIn("artifact_created", events)

    def test_manager_delegates_every_stage_before_real_pdf(self):
        state = server.initial()
        for actor in state["agents"]:
            actor["model"]["connection"] = "api"
        counters = defaultdict(int)
        image_count = 0
        events = []

        def action(name, args):
            return (
                "Thought: Controlled fixture\nAction: "
                + name
                + "\nAction Input: "
                + json.dumps(args)
            )

        def images(*args):
            nonlocal image_count
            image_count += 1
            data = io.BytesIO()
            Image.new("RGB", (300, 200), (image_count * 60, 80, 170)).save(data, format="PNG")
            return [data.getvalue()]

        def scripted(llm, messages, **kwargs):
            ident = llm.config["agentId"]
            counters[ident] += 1
            call = counters[ident]
            llm.usage.append({"step": llm.current, "input": 5, "output": 5})
            artifacts = llm.config["conversationArtifacts"]
            pngs = [a for a in artifacts if a["extension"] == "png"]

            def layout():
                return {
                    "cover": {
                        "image_url": pngs[0]["url"],
                        "subtitle": "A controlled production check",
                    },
                    "chapters": [
                        {
                            "title": "Chapter 1 — A new friend",
                            "text": "A young inventor helped a lost robot find its way home. They learned that courage grows through friendship.",
                            "image_url": pngs[1]["url"],
                        }
                    ],
                }

            if ident == "orchestrator":
                if call <= 5:
                    actor = state["agents"][call]
                    return action(
                        "Delegate work to coworker",
                        {
                            "coworker": f"{call + 1}. {actor['name']} — {actor['role']}",
                            "task": "Complete your production stage for the one-chapter comic.",
                            "context": json.dumps(
                                {
                                    "artifacts": artifacts,
                                    "previous_results": llm.config["comicStages"],
                                }
                            ),
                        },
                    )
                return "Final Answer: The approved comic PDF and illustrations are ready."
            if ident == "scriptwriter":
                return "Final Answer: Complete one-chapter script: a young inventor helps a robot find home. Distinct cover and chapter scene prompts supplied."
            if ident == "illustrator":
                if call <= 2:
                    return action(
                        "image_generator",
                        {
                            "request": "Cover: inventor and robot in the floating city"
                            if call == 1
                            else "Chapter: inventor helps the robot return home",
                            "title": "Cover" if call == 1 else "Chapter 1",
                        },
                    )
                return "Final Answer: " + json.dumps(pngs)
            if ident == "layout-designer":
                return "Final Answer: " + json.dumps(layout())
            if ident == "quality-validator":
                if call <= 2:
                    return action("read_generated_file", {"url": pngs[call - 1]["url"]})
                return "Final Answer: APPROVED\nChecked complete narrative, two distinct PNG fingerprints and the cover/chapter mapping. Metadata checks do not claim visual inspection."
            if ident == "pdf-generator":
                if call == 1:
                    return action(
                        "pdf_generator",
                        {"request": json.dumps(layout()), "title": "The Inventor and the Robot"},
                    )
                pdf = next(a for a in artifacts if a["extension"] == "pdf")
                if call == 2:
                    return action("read_generated_file", {"url": pdf["url"]})
                return (
                    "Final Answer: "
                    + pdf["url"]
                    + "; inspected actual pages and embedded illustrations."
                )
            raise AssertionError(ident)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(auth, "LOCAL", Path(directory)),
            patch.object(ResponsesLLM, "call", scripted),
            patch.object(
                harness.ImageProvider,
                "settings",
                return_value={"configured": True, "base_url": "https://images.example"},
            ),
            patch.object(harness.ImageProvider, "generate", side_effect=images),
        ):
            steps = execute(
                state,
                {
                    "mode": "team",
                    "team": starter_crew.TEAM_ID,
                    "goal": "Create an illustrated comic PDF with 1 chapter about courage and friendship.",
                },
                lambda k, d: events.append({"type": k, "data": d}),
                config={"provider": "api", "model": "fixture", "run_id": "studio-test"},
            )
            completed = [
                e["data"]["agentId"]
                for e in events
                if e["type"] == "agent_completed" and not e["data"].get("manager")
            ]
            self.assertEqual(completed, list(starter_crew.STAGES))
            pdf = next(
                e["data"]
                for e in events
                if e["type"] == "artifact_created" and e["data"]["extension"] == "pdf"
            )
            reader = PdfReader(artifact_path(pdf))
            self.assertEqual(len(reader.pages), 2)
            self.assertTrue(all(len(page.images) == 1 for page in reader.pages))
            self.assertEqual(pdf["document"]["uniqueIllustrations"], 2)
            self.assertEqual(steps[-1]["agentId"], "orchestrator")
            self.assertEqual(image_count, 2)
            self.assertFalse(any(e["type"] == "workflow_validation_failed" for e in events))
