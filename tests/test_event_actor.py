"""Execution attribution retains the actual actor independently of route targets."""

import unittest

from execution_log import enrich


class EventActorTests(unittest.TestCase):
    def test_delegation_reply_and_skill_selection_identify_the_sender(self):
        agents = [
            dict(id="manager", name="Coordinator", avatar="robot"),
            dict(id="worker", name="Illustrator", avatar="researcher"),
        ]
        for kind, data, expected in [
            ("delegation", {"fromId": "manager", "toId": "worker"}, "manager"),
            ("reply", {"fromId": "worker", "toId": "manager"}, "worker"),
            ("skill_selected", {"agentId": "worker", "selectedById": "manager"}, "manager"),
            ("step_completed", {"result": {"agentId": "worker"}}, "worker"),
            ("usage", {"agentId": "worker"}, "worker"),
        ]:
            with self.subTest(kind=kind):
                self.assertEqual(enrich(kind, data, agents)["actor"]["agentId"], expected)
        self.assertNotIn("actor", enrich("conversation_context", {}, agents))
