"""Real local renderers/MCP transport plus controlled provider and agent tests."""

import asyncio
import base64
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfReader

import auth
import external_mcp
import harness
import plugin_import
import profiles
import server
import skill_files
from runtime import ResponsesLLM, execute


def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return base64.b64encode(buffer.getvalue()).decode()


class HarnessTests(unittest.TestCase):
    def test_codex_skill_parsing_and_missing_metadata(self):
        skill = skill_files.parse_markdown(
            "---\nname: report-review\ndescription: Review an evidence-based report.\nmetadata:\n  requires: [pdf-generator]\n---\n# Review\nCheck sources and conclusions."
        )
        self.assertEqual(skill["requires"], ["pdf-generator"])
        self.assertIn("# Review", skill["instructions"])
        for invalid in [
            "# Just a heading",
            "---\nname: bad name\ndescription: A test\n---\nBody",
            "---\nname: valid\n---\nBody",
        ]:
            with self.assertRaises(ValueError):
                skill_files.parse_markdown(invalid)

    def test_interrupted_execution_is_recovered_from_sqlite(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(server, "DB", Path(temp) / "state.db"),
        ):
            server.save_job(
                {
                    "id": "restart-test",
                    "status": "running",
                    "events": [{"type": "tool_started", "data": {"name": "pdf-generator"}}],
                    "run": {"goal": "Create a PDF", "steps": [], "completed": False},
                }
            )
            server.recover_jobs()
            recovered = server.saved_job("restart-test")
            self.assertEqual(recovered["status"], "interrupted")
            self.assertTrue(recovered["run"]["failed"])
            self.assertEqual(recovered["events"][0]["type"], "tool_started")

    def test_real_pdf_and_high_resolution_chart_outputs(self):
        pdf = harness.PDFGenerator.render(
            "A verified report", "Evidence: 12 observations.\n\nConclusion: the count is 12."
        )
        reader = PdfReader(io.BytesIO(pdf))
        self.assertIn("12 observations", reader.pages[0].extract_text())
        html, png, svg = harness.ChartGenerator.render(
            {
                "data": [{"type": "bar", "x": ["Alpha", "Beta"], "y": [4, 7]}],
                "layout": {"title": {"text": "Verified chart"}},
            }
        )
        self.assertIn("Plotly.newPlot", html)
        self.assertTrue(png.startswith(b"\x89PNG"))
        from PIL import Image

        self.assertEqual(Image.open(io.BytesIO(png)).size, (3200, 2000))
        self.assertIn(b"<svg", svg)
        with self.assertRaises(ValueError):
            harness.ChartGenerator.render(
                {"data": [], "layout": {"images": [{"source": "https://remote.example/image.png"}]}}
            )

    def test_provider_tools_return_real_hosted_results_and_artifacts(self):
        events = []
        actor = {"id": "writer", "name": "Writer", "tools": ["web-research", "image-generator"]}
        llm = SimpleNamespace(
            config={
                "provider": "api",
                "api_key": "fixture-only",
                "base_url": "http://127.0.0.1:1/v1",
            },
            model="fixture",
            current=0,
            usage=[],
        )

        class Response:
            status = "completed"
            usage = SimpleNamespace(input_tokens=11, output_tokens=7)
            output_text = "A cited answer."

            def model_dump(self):
                return {
                    "output": [
                        {"type": "web_search_call"},
                        {
                            "type": "message",
                            "content": [
                                {
                                    "annotations": [
                                        {
                                            "type": "url_citation",
                                            "title": "Primary source",
                                            "url": "https://example.com/source",
                                        }
                                    ]
                                }
                            ],
                        },
                    ]
                }

        image = SimpleNamespace(
            status="completed",
            usage=SimpleNamespace(input_tokens=3, output_tokens=5),
            model_dump=lambda: {
                "output": [
                    {
                        "type": "image_generation_call",
                        "result": base64.b64encode(b"fixture-image-content").decode(),
                    }
                ]
            },
        )
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(auth, "LOCAL", Path(temp)),
            patch("harness.OpenAI") as client,
        ):
            from unittest.mock import MagicMock

            streams = []
            for response in (Response(), image):
                stream = MagicMock()
                stream.__enter__.return_value = iter(
                    [SimpleNamespace(type="response.completed", response=response)]
                )
                streams.append(stream)
            client.return_value.responses.create.side_effect = streams
            tools = harness.integration_tools(
                actor, llm, lambda k, d: events.append((k, d)), "run-fixture"
            )
            answer = json.loads(tools[0]._run("Find the source"))
            self.assertEqual(answer["sources"][0]["url"], "https://example.com/source")
            art = json.loads(tools[1]._run("Generate a visual"))["artifacts"][0]
            self.assertTrue(
                (harness.artifact_root() / "run-fixture" / (art["id"] + ".png")).exists()
            )
            self.assertEqual(
                client.return_value.responses.create.call_args_list[0].kwargs["tools"],
                [{"type": "web_search"}],
            )
            self.assertEqual(
                client.return_value.responses.create.call_args_list[1].kwargs["tools"],
                [{"type": "image_generation"}],
            )
            self.assertTrue(
                all(
                    c.kwargs["stream"] and c.kwargs["store"] is False
                    for c in client.return_value.responses.create.call_args_list
                )
            )
            self.assertEqual(sum(u["input"] for u in llm.usage), 14)
            self.assertNotIn("fixture-only", str(events))

    def test_dedicated_image_provider_keeps_the_agent_connection(self):
        actor = {"id": "writer", "name": "Writer", "tools": ["image-generator"]}
        llm = SimpleNamespace(
            config={"provider": "chatgpt"}, model="chatgpt-agent-model", current=0, usage=[]
        )
        events = []
        image = io.BytesIO()
        from PIL import Image

        Image.new("RGB", (2, 2), "blue").save(image, format="PNG")
        response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(image.getvalue()).decode())],
            usage=SimpleNamespace(input_tokens=4, output_tokens=8),
        )
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(auth, "LOCAL", Path(temp)),
            patch("harness.OpenAI") as client,
        ):
            auth.store(
                "image-provider",
                {
                    "api_key": "fixture-image-key",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-image-fixture",
                },
            )
            client.return_value.images.generate.return_value = response
            result = json.loads(
                harness.integration_tools(
                    actor, llm, lambda k, d: events.append((k, d)), "image-test"
                )[0]._run("A blue test image")
            )
            self.assertEqual(result["artifacts"][0]["extension"], "png")
            self.assertEqual(
                client.return_value.images.generate.call_args.kwargs["model"], "gpt-image-fixture"
            )
            self.assertEqual(llm.config["provider"], "chatgpt")
            self.assertNotIn(
                "fixture-image-key", str(events) + str(harness.ImageProvider.settings())
            )

    def test_plugin_zip_traversal_trust_and_actual_stdio_mcp(self):
        script = """from mcp.server.fastmcp import FastMCP
import os
server=FastMCP("fixture-plugin")
@server.tool()
def hello(name: str) -> str:
    return "Hello " + name + "; key present=" + str(bool(os.environ.get("MY_KEY")))
server.run(transport="stdio")
"""
        encoded = archive(
            {
                ".codex-plugin/plugin.json": '{"name":"fixture"}',
                ".mcp.json": json.dumps(
                    {
                        "mcpServers": {
                            "fixture-plugin": {
                                "command": "python3",
                                "args": ["server.py"],
                                "env": {"MY_KEY": "${API_KEY}"},
                            }
                        }
                    }
                ),
                "server.py": script,
            }
        )
        with tempfile.TemporaryDirectory() as temp, patch.object(auth, "LOCAL", Path(temp)):
            self.assertTrue(plugin_import.inspect(encoded)["runsLocalCode"])
            with self.assertRaises(ValueError):
                plugin_import.install(encoded, "fixture-plugin-key")
            _, connections = plugin_import.install(encoded, "fixture-plugin-key", True)
            self.assertNotIn("fixture-plugin-key", json.dumps(connections))
            discovered = asyncio.run(external_mcp.discover("fixture-plugin"))
            self.assertEqual(discovered["tools"][0]["id"], "hello")
            result = asyncio.run(
                external_mcp.call(
                    "fixture-plugin",
                    "hello",
                    {"name": "Agent"},
                    ["fixture-plugin:hello"],
                    discovered["tools"][0],
                )
            )
            self.assertIn("Hello Agent; key present=True", result)
            self.assertNotIn("fixture-plugin-key", result)
        with self.assertRaises(ValueError):
            plugin_import.inspect(archive({"../server.py": "bad", ".mcp.json": "{}"}))
        with self.assertRaises(ValueError):
            plugin_import.inspect(
                archive(
                    {
                        ".mcp.json": json.dumps(
                            {"mcpServers": {"bad": {"command": "sh", "args": ["setup.sh"]}}}
                        )
                    }
                )
            )

    def test_manager_chooses_skill_and_worker_receives_it_before_execution(self):
        state = server.initial()
        state["teams"][0]["manager"] = "reviewer"
        state["catalog"]["skills"].append(
            skill_files.parse_markdown(
                "---\nname: verify-report\ndescription: Verify a report before answering.\n---\nUse the phrase EVIDENCE VERIFIED in the final report."
            )
        )
        for a in state["agents"]:
            a.update(profiles.normalize(a))
            a["tools"] = []
            a["skills"] = []
            a["mcp"] = []
            a["model"].update(mode="custom", name=a["id"], connection="api")
        count = 0
        events = []

        def scripted(llm, messages, **kwargs):
            nonlocal count
            if llm.model == "reviewer":
                count += 1
                if count == 1:
                    return 'Thought: Pick the report skill.\nAction: use_skill\nAction Input: {"skill_id":"verify-report","reason":"The report needs an evidence check.","agent_id":"writer"}'
                if count == 2:
                    return 'Thought: Delegate the report.\nAction: Delegate work to coworker\nAction Input: {"coworker":"2. Writer — Writer","task":"Write the checked report","context":"Local fixture"}'
                return "Final Answer: The report is verified."
            self.assertIn("EVIDENCE VERIFIED", str(messages))
            return "Final Answer: EVIDENCE VERIFIED."

        with patch.object(ResponsesLLM, "call", scripted):
            results = execute(
                state,
                {"team": "research", "goal": "Verify the report"},
                lambda k, d: events.append((k, d)),
                config={
                    "provider": "api",
                    "api_key": "fixture-only",
                    "base_url": "http://127.0.0.1:1/v1",
                },
            )
        self.assertEqual(results[0]["output"], "EVIDENCE VERIFIED.")
        self.assertIn("skill_selected", [k for k, d in events])
        self.assertIn("skill_applied", [k for k, d in events])
        self.assertNotIn("Thought:", json.dumps(events))
