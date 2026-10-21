"""Persistent image → illustrated PDF → read/edit follow-up, with real local files."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader

import artifact_history
import auth
import harness
import server
from execution_context import conversation_prompt


class ArtifactHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        for patcher in [
            patch.object(auth, "LOCAL", self.path / "private"),
            patch.object(server, "DB", self.path / "fresh.db"),
        ]:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.events = []
        self.emit = lambda kind, data: self.events.append({"type": kind, "data": data})
        self.actor = {"id": "artist", "name": "Artist", "tools": ["pdf-generator"]}
        png = io.BytesIO()
        Image.new("RGB", (300, 200), "#4c84e7").save(png, format="PNG")
        self.image = harness.ArtifactStore("image-turn", self.actor, self.emit).write(
            "Original scene", "png", png.getvalue()
        )

    def test_reopen_then_embed_prior_image_and_read_new_pdf(self):
        store = server.conversations()
        chat = store.create({"agents": [self.actor]}, {"mode": "one", "agent": "artist"})
        store.begin(chat, "Create a blue scene", "image-turn")
        store.finish(
            {
                "id": "image-turn",
                "status": "completed",
                "events": self.events,
                "run": {"conversationId": chat["id"], "steps": [{"output": "Image generated"}]},
            }
        )
        chat = server.conversations().get(chat["id"])
        history = store.artifacts(chat)
        self.assertEqual(history, [self.events[0]["data"]])
        prompt = conversation_prompt({"conversationArtifacts": history})
        self.assertIn(self.image["url"], prompt)
        llm = SimpleNamespace(config={"provider": "api", "conversationArtifacts": history})
        tool = harness.integration_tools(self.actor, llm, self.emit, "pdf-turn")[0]
        self.events.clear()
        result = json.loads(
            tool._run(
                json.dumps(
                    {
                        "pages": [
                            {
                                "text": "Panel one: Our adventure begins.",
                                "image_url": self.image["url"],
                            },
                            {"text": "Panel two: A happy ending.", "image_url": self.image["url"]},
                        ]
                    }
                ),
                "Illustrated comic",
            )
        )
        pdf = result["artifacts"][0]
        path = artifact_history.artifact_path(pdf)
        reader = PdfReader(path)
        self.assertEqual(len(reader.pages), 2)
        self.assertTrue(all(len(page.images) == 1 for page in reader.pages))
        self.assertIn("adventure", reader.pages[0].extract_text())
        self.assertIn("artifact_reused", [e["type"] for e in self.events])
        chat = store.get(chat["id"])
        store.begin(chat, "Make an illustrated comic with that image", "pdf-turn")
        store.finish(
            {
                "id": "pdf-turn",
                "status": "completed",
                "events": self.events,
                "run": {"conversationId": chat["id"], "steps": [{"output": "PDF generated"}]},
            }
        )
        reopened = server.conversations().get(chat["id"])
        files = store.artifacts(reopened)
        self.assertEqual({a["extension"] for a in files}, {"png", "pdf"})
        file_reader = artifact_history.ArtifactReader(
            config={"conversationArtifacts": files}, actor=self.actor, event_sink=self.emit
        )
        text = json.loads(file_reader._run(pdf["url"]))["content"]
        self.assertIn("adventure", text)
        self.assertIn("happy ending", text)

    def test_cross_conversation_and_path_escape_rejected(self):
        for url in [
            self.image["url"],
            "/artifacts/../../auth.json",
            "https://example.com/image.png",
        ]:
            with self.assertRaises(ValueError):
                artifact_history.resolve_reference({"conversationArtifacts": []}, url)
        item = dict(self.image)
        source = artifact_history.artifact_path(item)
        source.unlink()
        source.symlink_to(Path(__file__).resolve())
        with self.assertRaises(ValueError):
            artifact_history.resolve_reference({"conversationArtifacts": [item]}, item["url"])

    def test_pdf_does_not_force_unnecessary_image_generation(self):
        from runtime import image_result_guardrail

        self.assertIsNone(
            image_result_guardrail(
                {"tools": ["image-generator"]},
                "Crie um PDF com a imagem anterior",
                SimpleNamespace(),
                self.emit,
            )
        )

    def test_chart_source_cannot_follow_symlinks(self):
        source = artifact_history.artifact_path(self.image).with_suffix(".source.json")
        source.symlink_to(Path(__file__).resolve())
        reader = artifact_history.ArtifactReader(
            config={"conversationArtifacts": [self.image]}, actor=self.actor, event_sink=self.emit
        )
        with self.assertRaises(ValueError):
            reader._run(self.image["url"])

    def test_five_illustrated_chapters_and_cover_are_embedded(self):
        from ebook_workflow import instructions, plan

        actor = {**self.actor, "tools": ["image-generator", "pdf-generator"]}
        llm = SimpleNamespace(
            config={"provider": "chatgpt", "run_id": "ebook", "conversationArtifacts": []}
        )
        tools = {
            tool.tool_id: tool for tool in harness.integration_tools(actor, llm, self.emit, "ebook")
        }
        references = []
        images = []
        with (
            patch.object(
                harness.ChatGPTImageRuntime, "settings", return_value={"configured": True}
            ),
            patch.object(harness.ChatGPTImageRuntime, "generate") as generate,
        ):
            for index in range(6):
                buffer = io.BytesIO()
                Image.new("RGB", (300, 180), (20 + index * 30, 60, 150)).save(buffer, format="PNG")
                generate.return_value = [buffer.getvalue()]
                result = json.loads(
                    tools["image-generator"]._run(
                        "Cover scene" if index == 0 else f"Chapter {index} scene",
                        title=f"Illustration {index}",
                        reference_urls=references,
                    )
                )
                images.append(result["artifacts"][0])
                references = [images[0]["url"]]
            self.assertEqual(generate.call_count, 6)
        spec = {
            "cover": {
                "image_url": images[0]["url"],
                "subtitle": "An illustrated five-chapter ebook",
            },
            "chapters": [
                {
                    "title": f"Chapter {index}",
                    "text": f"The complete adventure in chapter {index}.",
                    "image_url": images[index]["url"],
                }
                for index in range(1, 6)
            ],
        }
        result = json.loads(tools["pdf-generator"]._run(json.dumps(spec), title="Five adventures"))
        reader = PdfReader(artifact_history.artifact_path(result["artifacts"][0]))
        self.assertEqual(len(reader.pages), 6)
        self.assertTrue(all(len(page.images) == 1 for page in reader.pages))
        for index in range(1, 6):
            self.assertIn(f"Chapter {index}", reader.pages[index].extract_text())
        goal = "Construa uma história em 5 capítulos. Ilustre cada capítulo e monte um PDF com capa para um e-book."
        workflow = plan(goal)
        self.assertEqual(workflow["chapters"], 5)
        self.assertEqual(workflow["illustrations"], 6)
        self.assertGreaterEqual(workflow["maxIterations"], 8)
        self.assertGreater(workflow["maxExecutionSeconds"], 600)
        self.assertIn("5 complete chapters", instructions(goal))
        from runtime import pdf_result_guardrail

        llm.config["ebookWorkflow"] = workflow
        check = pdf_result_guardrail(goal, llm.config, self.emit)
        self.assertTrue(check("Created the ebook")[0])
        llm.config["conversationArtifacts"][-1]["document"]["illustratedChapters"] = 4
        self.assertFalse(check("Incomplete ebook")[0])

    def test_pdf_completion_requires_a_new_document(self):
        from runtime import pdf_result_guardrail

        config = {
            "run_id": "current",
            "conversationArtifacts": [{"runId": "old", "extension": "pdf"}],
        }
        check = pdf_result_guardrail("Create an ebook PDF", config, self.emit)
        self.assertFalse(check("A promise")[0])
        config["conversationArtifacts"].append({"runId": "current", "extension": "pdf"})
        self.assertTrue(check("Created")[0])
