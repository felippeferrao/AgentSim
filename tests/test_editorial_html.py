"""Actual offline HTML/CSS rendering with explicit resource boundaries and page checks."""

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

import server
from harness import PDFGenerator


class EditorialHTMLTests(unittest.TestCase):
    def test_malformed_design_request_never_becomes_a_plain_pdf(self):
        with self.assertRaisesRegex(ValueError, "Invalid PDF request JSON"):
            PDFGenerator.render(
                "Incomplete", '{"layout":"editorial-html","html":"<p>Story</p>"', {}
            )

    def test_agent_authored_pages_embed_fonts_and_owned_images(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "test.png"
            Image.new("RGB", (300, 200), "#aacc99").save(image)
            html = """<html><head><style>@page{size:A4;margin:0}body{margin:0}.page{width:210mm;height:297mm;box-sizing:border-box;padding:15mm;break-after:page}.page:last-child{break-after:auto}h1{font-family:EditorialDisplay;font-size:40pt}p{font-family:EditorialText;font-size:12pt}</style></head><body><section class="page"><h1>Across the garden</h1><img src="/artifacts/test/scene.png"><p>A little story begins.</p></section><section class="page"><h1>A new world</h1><p>The complete ending remains intact.</p></section></body></html>"""
            spec = {"layout": "editorial-html", "page_count": 2, "html": html}
            data = PDFGenerator.render(
                "A new story", json.dumps(spec), {"/artifacts/test/scene.png": image}
            )
            reader = PdfReader(io.BytesIO(data))
            self.assertEqual(len(reader.pages), 2)
            self.assertIn("Across the garden", reader.pages[0].extract_text())
            self.assertIn("complete ending remains intact", reader.pages[1].extract_text())
            self.assertEqual(len(reader.pages[0].images), 1)
            fonts = reader.pages[0]["/Resources"]["/Font"]
            self.assertTrue(any(f.get_object().get("/Subtype") == "/Type0" for f in fonts.values()))
            spec["page_count"] = 1
            with self.assertRaisesRegex(ValueError, "page count"):
                PDFGenerator.render(
                    "A new story", json.dumps(spec), {"/artifacts/test/scene.png": image}
                )

    def test_external_files_network_scripts_and_imports_are_rejected(self):
        for html in [
            '<img src="file:///etc/passwd">',
            '<img src="http://127.0.0.1:8080/api/state">',
            "<script>alert(1)</script>",
            '<p onclick="run()">Text</p>',
            '<style>@import "https://example.com/style.css";</style><p>Text</p>',
        ]:
            with self.subTest(html=html), self.assertRaises(ValueError):
                PDFGenerator.render(
                    "Blocked", json.dumps({"layout": "editorial-html", "html": html}), {}
                )

    def test_new_skill_keeps_old_skill_available_without_new_permissions(self):
        state = server.initial()
        actor = next(a for a in state["agents"] if a["id"] == "pdf-generator")
        self.assertEqual(actor["skills"], ["magazine-layout"])
        self.assertEqual(actor["tools"], ["pdf-generator"])
        self.assertEqual(
            {s["id"] for s in state["catalog"]["skills"]}, {"magazine-layout", "minimax-pdf"}
        )
