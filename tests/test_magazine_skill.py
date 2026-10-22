"""The imported MIT skill, actual local PDF layout and explicit tool permissions."""

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

import server
from harness import PDFGenerator
from skill_runtime import SkillSelector


class MagazineSkillTests(unittest.TestCase):
    def test_bundled_skill_assigned_and_loaded_with_public_selection(self):
        state = server.initial()
        actor = next(a for a in state["agents"] if a["id"] == "pdf-generator")
        self.assertEqual(actor["skills"], ["magazine-layout"])
        actor["skills"].append("minimax-pdf")
        skill = next(s for s in state["catalog"]["skills"] if s["id"] == "minimax-pdf")
        self.assertEqual(skill["format"], "codex-skill")
        self.assertEqual(skill["requires"], ["pdf-generator"])
        self.assertIn("60aaae52bb2af8162732751a4332f62a5fef518b", skill["markdown"])
        events = []
        selector = SkillSelector(
            actor=actor,
            catalog=state["catalog"]["skills"],
            members=[actor],
            selections={},
            event_sink=lambda k, d: events.append((k, d)),
        )
        self.assertIn("magazine", selector._run("minimax-pdf", "Create an editorial magazine"))
        self.assertEqual(events[0][0], "skill_selected")
        actor["tools"] = []
        with self.assertRaisesRegex(ValueError, "explicit tool permissions"):
            selector._run("minimax-pdf", "Create an editorial magazine")

    def test_magazine_renderer_preserves_narrative_and_embeds_images(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "art.png"
            Image.new("RGB", (900, 600), "#315E56").save(path)
            paragraphs = [
                "Paragraph "
                + str(i)
                + ": "
                + ("Careful editorial composition helps readers understand a story. " * 12)
                for i in range(6)
            ]
            spec = {
                "layout": "magazine",
                "publication": "FIELD NOTES",
                "cover": {"image_url": "owned", "subtitle": "An editorial sample"},
                "chapters": [
                    {
                        "title": "The art of noticing",
                        "image_url": "owned",
                        "caption": "A real local image.",
                        "pull_quote": "Make room for discovery.",
                        "text": "\n\n".join(paragraphs),
                    }
                ],
            }
            pdf = PDFGenerator.render(
                "A world of small discoveries", json.dumps(spec), {"owned": path}
            )
            reader = PdfReader(io.BytesIO(pdf))
            text = " ".join(
                " ".join(
                    line
                    for line in (page.extract_text() or "").splitlines()
                    if line != "FIELD NOTES" and not (line.isdigit() and len(line) == 2)
                )
                for page in reader.pages
            )
            self.assertGreaterEqual(len(reader.pages), 2)
            for p in paragraphs:
                self.assertIn(" ".join(p.split()), " ".join(text.split()))
            self.assertEqual(sum(len(p.images) for p in reader.pages), 2)
            spec["chapters"][0]["image_url"] = "file:///etc/passwd"
            with self.assertRaisesRegex(ValueError, "conversation"):
                PDFGenerator.render("Invalid", json.dumps(spec), {"owned": path})
            spec["chapters"][0]["image_url"] = "owned"
            spec["design"] = {"accent": "url(https://invalid)"}
            with self.assertRaisesRegex(ValueError, "hexadecimal"):
                PDFGenerator.render("Invalid", json.dumps(spec), {"owned": path})
