import json
import sqlite3
import unittest

import brain


class BrainTests(unittest.TestCase):
    def test_markdown_revision_changes_amount_and_preserves_run_snapshot(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE brains (id TEXT PRIMARY KEY, data TEXT)")
            original = brain.save_brain(db, {"name": "Demo", "markdown": brain.EXAMPLE.read_text()})
            updated = brain.save_brain(db, {
                **original, "markdown": original["markdown"].replace("| ING | 10 |", "| ING | 12 |"),
            })
            self.assertEqual(brain.quote(original, "Audi A3 Sportback", "ING")["total"], "900.00")
            self.assertEqual(brain.quote(updated, "Audi A3 Sportback", "ING")["total"], "880.00")
            self.assertEqual(brain.quote(updated, "Audi A3 Sportback", "Yuzzu")["total"], "1000.00")
            self.assertEqual(brain.list_brains(db)[0]["revision"], 2)
            with self.assertRaisesRegex(ValueError, "changed"):
                brain.save_brain(db, original)

    def test_tools_respect_document_grants_and_calculator_permission(self):
        document = {"id": "motor", "name": "Pricing", "revision": 1, "markdown": brain.EXAMPLE.read_text()}
        other = {**document, "id": "private", "markdown": "Undisclosed"}
        config = {
            "brains": [document, other], "quoteProgress": {},
            "quoteRequest": {"brainId": "motor", "vehicle": "Audi A3 Sportback", "partner": "ING"},
        }
        events = []
        emit = lambda kind, data: events.append((kind, data))
        actor = {"id": "a", "name": "Analyst", "tools": ["calculator"]}
        self.assertEqual(brain.tools(actor, config, emit), [])
        actor["brains"] = ["motor"]
        read, calculate = brain.tools(actor, config, emit)
        self.assertNotIn("Undisclosed", read.run(brain_id="private"))
        self.assertFalse(events)
        self.assertEqual(json.loads(read.run(brain_id="motor"))["name"], "Pricing")
        self.assertEqual(json.loads(calculate.run())["total"], "900.00")
        self.assertEqual(events[-1][1]["output"]["revision"], 1)
        self.assertEqual(len(brain.tools({**actor, "tools": []}, config, emit)), 1)
