"""Native image routing, output validation and public-event isolation."""

import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import auth
import harness
import native_images


class NativeImageTests(unittest.TestCase):
    def exercise(self, produce=True, failure=False, reference=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        private = Path(temporary.name)
        patcher = patch.object(auth, "LOCAL", private)
        patcher.start()
        self.addCleanup(patcher.stop)
        home = native_images.runtime_home()
        (home / "auth.json").write_text('{"fixture":true}')
        old = home / "generated_images" / "old-thread" / "exec-old.png"
        old.parent.mkdir(parents=True)
        Image.new("RGB", (3, 3), "red").save(old)
        image = io.BytesIO()
        Image.new("RGB", (4, 4), "blue").save(image, format="PNG")
        png = image.getvalue()
        commands = []

        class Process:
            stdin = io.StringIO()
            code = None

            def __init__(self, command, **kwargs):
                commands.append((command, kwargs))
                self.stdout = self.events()

            def events(self):
                yield json.dumps({"type": "thread.started", "thread_id": "current-thread"})
                yield json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "reasoning",
                            "text": "Private native reasoning and fixture-secret",
                        },
                    }
                )
                if failure:
                    yield json.dumps(
                        {"type": "turn.failed", "error": {"message": "fixture-secret"}}
                    )
                    return
                if produce:
                    output = home / "generated_images" / "current-thread" / "exec-actual.png"
                    output.parent.mkdir(parents=True)
                    output.write_bytes(png)
                yield json.dumps(
                    {"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 7}}
                )

            def poll(self):
                return self.code

            def wait(self, timeout=None):
                self.code = 0
                return 0

            def terminate(self):
                self.code = -15

            def kill(self):
                self.code = -9

        events = []
        llm = SimpleNamespace(config={"provider": "chatgpt"}, current=0, usage=[])
        references = []
        if reference:
            item = harness.ArtifactStore(
                "previous-turn", {"id": "billy", "name": "Billy"}, lambda *args: None
            ).write("Previous character", "png", png)
            llm.config["conversationArtifacts"] = [item]
            references = [item["url"]]
        actor = {"id": "billy", "name": "Billy", "tools": ["image-generator"]}
        tool = harness.integration_tools(
            actor, llm, lambda k, d: events.append((k, d)), "native-test"
        )[0]
        with (
            patch("native_images.subprocess.Popen", Process),
            patch("native_images.shutil.which", return_value="/official/codex"),
            patch("harness.ProviderTools.request") as hosted,
            patch.dict(
                "os.environ",
                {"OPENAI_API_KEY": "fixture-secret", "CODEX_ACCESS_TOKEN": "fixture-secret"},
            ),
        ):
            try:
                result = tool._run("A blue test illustration", reference_urls=references)
            except ValueError as exc:
                result = exc
            hosted.assert_not_called()
        return private, result, events, commands, llm

    def test_chatgpt_uses_native_runtime_and_returns_actual_artifact(self):
        private, result, events, commands, llm = self.exercise()
        result = json.loads(result)
        artifact = result["artifacts"][0]
        output = private / "artifacts" / "native-test" / (artifact["id"] + ".png")
        with Image.open(output) as image:
            self.assertEqual(image.size, (4, 4))
        self.assertTrue(
            any(d.get("implementation") == "native_images.ChatGPTImageRuntime" for _, d in events)
        )
        self.assertNotIn("Private native reasoning", str(events))
        self.assertNotIn("fixture-secret", str(events))
        command, kwargs = commands[0]
        self.assertIn("shell_tool", command)
        self.assertIn("workspace-write", command)
        self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
        self.assertNotIn("CODEX_ACCESS_TOKEN", kwargs["env"])
        self.assertEqual(kwargs["env"]["CODEX_HOME"], str((private / "image-runtime").resolve()))
        self.assertEqual(llm.usage[-1]["input"], 5)
        self.assertEqual((private / "image-runtime" / "auth.json").stat().st_mode & 0o777, 0o600)

    def test_no_new_image_never_reuses_an_older_png(self):
        _, result, events, _, _ = self.exercise(produce=False)
        self.assertIsInstance(result, ValueError)
        self.assertIn("No older image was substituted", str(result))
        self.assertNotIn("artifact_created", [kind for kind, _ in events])
        self.assertIn("tool_failed", [kind for kind, _ in events])

    def test_native_failure_does_not_expose_raw_error_or_fall_back(self):
        _, result, events, _, _ = self.exercise(failure=True)
        self.assertIsInstance(result, ValueError)
        self.assertNotIn("fixture-secret", str(result) + str(events))
        self.assertNotIn("artifact_created", [kind for kind, _ in events])

    def test_prior_image_is_attached_to_native_runtime(self):
        private, result, events, commands, llm = self.exercise(reference=True)
        self.assertNotIsInstance(result, ValueError)
        command = commands[0][0]
        self.assertIn("--image", command)
        attached = Path(command[command.index("--image") + 1])
        self.assertTrue(attached.is_file())
        self.assertIn("previous-turn", str(attached))
        self.assertIn("artifact_reused", [kind for kind, _ in events])

    def test_image_answer_requires_a_real_tool_artifact(self):
        from runtime import image_result_guardrail

        events = []
        actor = {"id": "billy", "name": "Billy", "tools": ["image-generator"]}
        llm = SimpleNamespace(generated_images=[])
        validate = image_result_guardrail(
            actor, "Create an image of a dog", llm, lambda k, d: events.append((k, d))
        )
        accepted, reason = validate("The image has been generated.")
        self.assertFalse(accepted)
        self.assertIn("Call image_generator", reason)
        self.assertEqual(events[-1][0], "output_validation_failed")
        llm.generated_images.append({"id": "actual-file", "url": "/artifacts/run/actual.png"})
        self.assertTrue(validate("Generated image attached.")[0])
        self.assertIsNone(
            image_result_guardrail(actor, "What can you do?", llm, lambda *args: None)
        )

    def test_simultaneous_scene_requests_are_queued_without_failure(self):
        entered, release, queued = threading.Event(), threading.Event(), threading.Event()
        results, failures = [], []
        actor = {"id": "artist", "name": "Artist"}

        def emit(kind, data):
            if kind == "provider_tool_queued":
                queued.set()

        def generate(*args):
            entered.set()
            if not release.wait(3):
                raise ValueError("Test release timed out")
            return [b"scene"]

        def request():
            try:
                results.append(
                    native_images.ChatGPTImageRuntime.generate(
                        "New scene", SimpleNamespace(), emit, actor
                    )
                )
            except Exception as exc:
                failures.append(exc)

        with (
            patch.object(
                native_images.ChatGPTImageRuntime, "settings", return_value={"configured": True}
            ),
            patch.object(native_images.ChatGPTImageRuntime, "_generate", side_effect=generate),
        ):
            first = threading.Thread(target=request)
            second = threading.Thread(target=request)
            first.start()
            self.assertTrue(entered.wait(2))
            second.start()
            try:
                self.assertTrue(queued.wait(2))
            finally:
                release.set()
                first.join(3)
                second.join(3)
        self.assertFalse(failures)
        self.assertEqual(results, [[b"scene"], [b"scene"]])
