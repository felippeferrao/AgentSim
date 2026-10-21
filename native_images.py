"""ChatGPT's native image tool through an independently authenticated Codex runtime."""

import io
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from urllib.parse import urlsplit

import auth

_GENERATION_LOCK = threading.Lock()
_LOGIN_LOCK = threading.Lock()
_LOGIN = {}


def runtime_home():
    folder = auth.LOCAL / "image-runtime"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder.resolve()


def child_environment():
    # A private child configuration, never the desktop/CLI user's credential cache.
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("OPENAI_", "CODEX_", "CHATGPT_"))
    }
    env.update(CODEX_HOME=str(runtime_home()), BROWSER="/usr/bin/true")
    return env


class ChatGPTImageRuntime:
    @staticmethod
    def settings():
        return {
            "available": bool(shutil.which("codex")),
            "configured": (runtime_home() / "auth.json").is_file(),
            "provider": "chatgpt-native",
        }

    @staticmethod
    def login():
        with _LOGIN_LOCK:
            if _LOGIN.get("process") and _LOGIN["process"].poll() is None:
                if _LOGIN.get("url"):
                    return {"url": _LOGIN["url"]}
                raise ValueError("Image sign-in is already starting. Try again shortly.")
            executable = shutil.which("codex")
            if not executable:
                raise ValueError("Install the official Codex CLI to use native ChatGPT images.")
            process = subprocess.Popen(
                [executable, "-c", 'cli_auth_credentials_store="file"', "login"],
                env=child_environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            _LOGIN.clear()
            _LOGIN["process"] = process
            messages = queue.Queue()

            def read_login():
                for line in process.stdout:
                    value = line.strip()
                    parsed = urlsplit(value)
                    if parsed.scheme == "https" and parsed.hostname == "auth.openai.com":
                        _LOGIN["url"] = value
                        messages.put(value)
                messages.put(None)

            threading.Thread(target=read_login, daemon=True).start()
            timer = threading.Timer(
                600, lambda: process.terminate() if process.poll() is None else None
            )
            timer.daemon = True
            timer.start()
            try:
                url = messages.get(timeout=12)
            except queue.Empty:
                url = None
            if not url:
                raise ValueError(
                    "Could not start image sign-in. Check the Codex CLI and port 1455."
                )
            return {"url": url}

    @staticmethod
    def generate(prompt, llm, emit, actor, reference_paths=None):
        if not ChatGPTImageRuntime.settings()["configured"]:
            raise ValueError(
                "Connect the native ChatGPT image session in Tools → Image Generator. No API key is required."
            )
        if not _GENERATION_LOCK.acquire(blocking=False):
            emit(
                "provider_tool_queued",
                {
                    "agentId": actor["id"],
                    "agent": actor["name"],
                    "implementation": "native_images.ChatGPTImageRuntime",
                    "where": "Local native image generation queue",
                    "explanation": "This scene is queued until the current illustration completes.",
                },
            )
            if not _GENERATION_LOCK.acquire(timeout=3600):
                raise ValueError("The image generation queue exceeded its time limit.")
        try:
            return ChatGPTImageRuntime._generate(prompt, llm, emit, actor, reference_paths)
        finally:
            _GENERATION_LOCK.release()

    @staticmethod
    def _generate(prompt, llm, emit, actor, reference_paths=None):
        from PIL import Image

        executable = shutil.which("codex")
        if not executable:
            raise ValueError("The official Codex CLI is unavailable.")
        home = runtime_home()
        pool = home / "generated_images"
        before = set(pool.rglob("*.png")) if pool.exists() else set()
        job = home / "jobs" / uuid.uuid4().hex
        job.mkdir(parents=True, mode=0o700)
        metadata = {
            "agentId": actor["id"],
            "agent": actor["name"],
            "name": "image_generation",
            "implementation": "native_images.ChatGPTImageRuntime",
            "where": "Local Codex CLI → ChatGPT native image service",
        }
        emit(
            "provider_tool_started",
            {
                **metadata,
                "explanation": "The agent's prompt was sent to ChatGPT's native image runtime using AgentSim's own image session, without an API key.",
            },
        )
        command = [
            executable,
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "-c",
            'cli_auth_credentials_store="file"',
            "--sandbox",
            "workspace-write",
            "--disable",
            "shell_tool",
            "--disable",
            "unified_exec",
            "-c",
            'web_search="disabled"',
            "-C",
            str(job),
            "-",
        ]
        for path in reference_paths or []:
            command[-1:-1] = ["--image", str(path)]
        process = subprocess.Popen(
            command,
            env=child_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        instruction = (
            "Use only the native image generation tool to create one actual PNG image from the user's visual request below. "
            "Do not use shell, web search, code, SVG or unrelated tools. Do not claim generation without a real image. "
            "Use attached reference images to preserve the requested characters, appearance and visual style. "
            "Your final reply must contain only the generated image's absolute file path.\n<visual_request>\n"
            + prompt
            + "\n</visual_request>"
        )
        try:
            process.stdin.write(instruction)
            process.stdin.close()
            messages = queue.Queue()

            def read_events():
                try:
                    for line in process.stdout:
                        messages.put(line)
                finally:
                    messages.put(None)

            threading.Thread(target=read_events, daemon=True).start()
            deadline = time.monotonic() + llm.config.get("imageTimeoutSeconds", 105)
            completed = False
            thread_id = None
            while True:
                if time.monotonic() > deadline:
                    raise ValueError(
                        "ChatGPT image generation exceeded this agent's execution time. Increase the agent's time limit and retry."
                    )
                try:
                    line = messages.get(timeout=0.5)
                except queue.Empty:
                    continue
                if line is None:
                    break
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                kind = event.get("type")
                if kind == "thread.started":
                    thread_id = event.get("thread_id")
                if kind in ("thread.started", "turn.started"):
                    emit(
                        "provider_activity",
                        {
                            **metadata,
                            "name": kind,
                            "explanation": "The native ChatGPT runtime reported this execution stage.",
                        },
                    )
                elif kind == "turn.completed":
                    completed = True
                    usage = event.get("usage", {})
                    record = {
                        "step": llm.current,
                        "input": usage.get("input_tokens"),
                        "output": usage.get("output_tokens"),
                    }
                    llm.usage.append(record)
                    emit(
                        "usage",
                        {
                            **record,
                            **metadata,
                            "explanation": "Actual native-runtime model token usage. Image-plan accounting is managed by ChatGPT.",
                        },
                    )
                elif kind in ("turn.failed", "error"):
                    raise ValueError(
                        "The native ChatGPT image session failed. Check sign-in, plan limits and the visual request."
                    )
            code = process.wait(timeout=3)
            if code or not completed or not thread_id:
                raise ValueError(
                    "ChatGPT did not complete native image generation. Check the image session and account limits."
                )
            images = []
            for path in sorted(pool.rglob("*.png")):
                if (
                    path in before
                    or path.is_symlink()
                    or not path.resolve().is_relative_to(pool.resolve())
                ):
                    continue
                if path.parent.name != thread_id or not path.name.startswith("exec-"):
                    continue
                if path.stat().st_size > 30_000_000:
                    raise ValueError("Generated image exceeds the 30 MB limit.")
                data = path.read_bytes()
                with Image.open(io.BytesIO(data)) as check:
                    if check.format != "PNG":
                        raise ValueError("ChatGPT returned an invalid image file.")
                    check.verify()
                images.append(data)
            if not images:
                raise ValueError(
                    "The native runtime returned no new generated PNG. No older image was substituted."
                )
            credential = home / "auth.json"
            if credential.exists():
                credential.chmod(0o600)
            return images
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdout.close()
            shutil.rmtree(job, ignore_errors=True)
