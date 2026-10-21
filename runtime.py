"""Real CrewAI tasks with a Responses adapter and allowlisted tools."""

import ast
import asyncio
import operator
import os
import re
import sys

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_TELEMETRY_ENABLED"] = "false"
import hashlib
from pathlib import Path
from typing import Any

from crewai import Agent, BaseLLM, Crew, Process, Task
from crewai.tools import BaseTool, tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import BadRequestError, OpenAI
from pydantic import ConfigDict, Field, create_model

import auth
import external_mcp
import harness
import profiles
from skill_runtime import SkillSelector, available_skills

ROOT = Path(__file__).parent


def calculate(expression):
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }

    def visit(n):
        if isinstance(n, ast.Constant) and type(n.value) in (int, float) and abs(n.value) < 1e12:
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](visit(n.left), visit(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -visit(n.operand)
        raise ValueError("Use only numbers and + - * /.")

    if len(expression) > 100:
        raise ValueError("Expression is too long.")
    return str(visit(ast.parse(expression, mode="eval").body))


async def mcp_call(name, args=None):
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_documents.py")])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            if name == "list":
                return [x.model_dump() for x in (await session.list_tools()).tools]
            result = await session.call_tool(name, args or {})
            if result.isError:
                raise ValueError("MCP tool returned an error.")
            return "\n".join(getattr(c, "text", "") for c in result.content)


class HTTPMCPTool(BaseTool):
    connection_id: str = Field(exclude=True)
    remote_name: str = Field(exclude=True)
    grants: list[str] = Field(exclude=True)
    expected_tool: dict = Field(exclude=True)
    event_sink: Any = Field(exclude=True)
    step_index: Any = Field(exclude=True)

    def _run(self, **kwargs):
        label = self.connection_id + ":" + self.remote_name
        # Do not record arguments or remote output: external tools may return secrets.
        self.event_sink(
            "tool_started",
            {
                "step": self.step_index(),
                "name": label,
                "input": "External MCP arguments kept out of the timeline.",
                "implementation": "runtime.HTTPMCPTool",
                "where": "MCP connection: " + self.connection_id,
            },
        )
        try:
            result = asyncio.run(
                external_mcp.call(
                    self.connection_id, self.remote_name, kwargs, self.grants, self.expected_tool
                )
            )
        except ValueError as exc:
            self.event_sink(
                "tool_failed", {"step": self.step_index(), "name": label, "error": str(exc)}
            )
            raise
        self.event_sink(
            "tool_completed",
            {
                "step": self.step_index(),
                "name": label,
                "output": "External MCP call completed. Its result was passed to the helper.",
            },
        )
        return result


def http_tools(agent, catalog, emit, llm):
    result = []
    for connection in catalog:
        if connection["id"] == "documents":
            continue
        for definition in connection["tools"]:
            grant = connection["id"] + ":" + definition["id"]
            if grant not in agent["mcp"]:
                continue
            schema = definition["inputSchema"]
            args_model = create_model(
                "MCPArgs_" + hashlib.sha256(grant.encode()).hexdigest()[:12],
                __config__=ConfigDict(extra="allow"),
            )
            args_model.model_json_schema = classmethod(
                lambda cls, *args, _schema=schema, **kwargs: __import__("copy").deepcopy(_schema)
            )
            tool_name = "mcp_" + hashlib.sha256(grant.encode()).hexdigest()[:20]
            result.append(
                HTTPMCPTool(
                    name=tool_name,
                    description=f"{grant}: " + definition["description"],
                    args_schema=args_model,
                    connection_id=connection["id"],
                    remote_name=definition["id"],
                    grants=list(agent["mcp"]),
                    expected_tool=definition,
                    event_sink=lambda kind, data, actor=agent, target=connection["id"]: emit(
                        kind,
                        {
                            "agentId": actor.get("id"),
                            "agent": actor.get("name", "MCP agent"),
                            "implementation": "runtime.HTTPMCPTool",
                            "where": "MCP connection: " + target,
                            **data,
                        },
                    ),
                    step_index=lambda: llm.current,
                )
            )
    return result


class ResponsesLLM(BaseLLM):
    def __init__(self, config, emit):
        super().__init__(model=config["model"], temperature=0.2)
        self.config = config
        self.emit = emit
        self.usage = []
        self.generated_images = []
        self.current = 0

    def supports_function_calling(self):
        return self.config.get("nativeTools", False)

    def supports_stop_words(self):
        return False

    def get_context_window_size(self):
        return self.config.get("contextWindow", 32000)

    def call(self, messages, tools=None, callbacks=None, available_functions=None, **kwargs):
        key = auth.access() if self.config["provider"] == "chatgpt" else self.config.get("api_key")
        if not key:
            raise ValueError(
                "Save your own provider key in Connection setup, or sign in with ChatGPT."
            )
        base = (
            "https://api.openai.com/v1"
            if self.config["provider"] == "chatgpt"
            else self.config["base_url"]
        )
        client = OpenAI(api_key=key, base_url=base, max_retries=0, timeout=90)
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        inputs = []
        for message in messages:
            if message.get("role") == "tool":
                inputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": message["tool_call_id"],
                        "output": str(message.get("content", "")),
                    }
                )
                continue
            if message.get("content") is not None and message.get("role") in (
                "system",
                "developer",
                "user",
                "assistant",
            ):
                inputs.append({"role": message["role"], "content": message["content"]})
            for call in message.get("tool_calls", []):
                inputs.append(
                    {
                        "type": "function_call",
                        "call_id": call["id"],
                        "name": call["function"]["name"],
                        "arguments": call["function"]["arguments"],
                    }
                )
        if self.config.get("agentId"):
            self.emit(
                "model_started",
                {
                    "agentId": self.config["agentId"],
                    "agent": self.config.get("agentName"),
                    "model": self.model,
                    "where": "Provider: "
                    + __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(base).netloc,
                    "implementation": "runtime.ResponsesLLM",
                    "availableTools": [t.get("function", t)["name"] for t in (tools or [])],
                },
            )
        final = None
        completed_items = {}
        options = {}
        if self.config.get("temperature") is not None:
            options["temperature"] = self.config["temperature"]
        if self.config.get("maxOutputTokens") is not None:
            options["max_output_tokens"] = self.config["maxOutputTokens"]
        if tools and self.supports_function_calling():
            # Native image generation is serialized; do not request concurrent jobs.
            options["parallel_tool_calls"] = False
            options["tools"] = [
                {"type": "function", **t.get("function", t), "strict": False} for t in tools
            ]
            if self.config.get("requireImage") and not self.generated_images:
                options["tool_choice"] = {"type": "function", "name": "image_generator"}
        try:
            with client.responses.create(
                model=self.model, input=inputs, store=False, stream=True, **options
            ) as stream:
                for event in stream:
                    if event.type == "response.output_item.done":
                        completed_items[event.output_index] = event.item
                    elif event.type == "response.completed":
                        final = event.response
                    elif event.type in ("response.failed", "response.incomplete", "error"):
                        raise ValueError(
                            "The provider did not complete this request. Check connection and usage limits."
                        )
        except BadRequestError:
            raise ValueError(
                "The provider rejected this agent’s model or parameters. Check Profile: temperature and output limits are not supported by every model."
            ) from None
        if final is None:
            raise ValueError("The provider stream ended early. No complete result was received.")
        if not final.output and completed_items:
            final = final.model_copy(
                update={"output": [completed_items[i] for i in sorted(completed_items)]}
            )
        usage = final.usage
        record = {
            "step": self.current,
            "input": usage.input_tokens if usage else None,
            "output": usage.output_tokens if usage else None,
        }
        self.usage.append(record)
        self.emit("usage", record)
        calls = [o for o in final.output if o.type == "function_call"]
        if calls:
            return [
                {
                    "id": o.call_id,
                    "type": "function",
                    "function": {"name": o.name, "arguments": o.arguments},
                }
                for o in calls
            ]
        return final.output_text


def builtin_tools(a, emit, llm, catalog):
    assigned = []

    def tracked(name, fn, llm=llm):
        def wrapper(**args):
            metadata = {
                "agentId": a["id"],
                "agent": a["name"],
                "implementation": "runtime.builtin_tools",
                "where": "Local Python"
                if name == "calculator"
                else "Local MCP stdio · teaching documents",
            }
            emit("tool_started", {**metadata, "step": llm.current, "name": name, "input": args})
            try:
                result = fn(**args)
            except Exception:
                emit(
                    "tool_failed",
                    {
                        **metadata,
                        "name": name,
                        "error": "Assigned tool could not complete this request.",
                    },
                )
                raise
            emit(
                "tool_completed",
                {**metadata, "step": llm.current, "name": name, "output": result},
            )
            return result

        return wrapper

    if "calculator" in a["tools"]:

        @tool("calculator")
        def calculator(expression: str) -> str:
            """Calculate numbers using + - * / and parentheses."""
            return tracked("calculator", calculate)(expression=expression)

        assigned.append(calculator)
    if "documents:search" in a["mcp"]:

        @tool("documents_search")
        def documents_search(query: str) -> str:
            """Search bundled teaching documents using actual MCP."""
            return tracked(
                "documents:search",
                lambda query: asyncio.run(mcp_call("search", {"query": query})),
            )(query=query)

        assigned.append(documents_search)
    if "documents:read" in a["mcp"]:

        @tool("documents_read")
        def documents_read(document_id: str) -> str:
            """Read a bundled teaching document: picnic or teamwork."""
            return tracked(
                "documents:read",
                lambda document_id: asyncio.run(mcp_call("read", {"document_id": document_id})),
            )(document_id=document_id)

        assigned.append(documents_read)
    from artifact_history import ArtifactReader

    assigned.append(ArtifactReader(config=llm.config, actor=a, event_sink=emit))
    assigned.extend(harness.integration_tools(a, llm, emit, llm.config.get("run_id", "standalone")))
    assigned.extend(http_tools(a, catalog, emit, llm))
    return assigned


def build_agent(a, state, config, emit, agent_class=None, manager=False, **extra):
    agent_class = agent_class or Agent
    agent_config = dict(config)
    workflow = config.get("ebookWorkflow")
    execution_seconds = a["behavior"]["maxExecutionSeconds"]
    iterations = a["behavior"]["maxIterations"]
    if workflow:
        execution_seconds = max(execution_seconds, workflow["maxExecutionSeconds"])
        iterations = max(iterations, workflow["maxIterations"])
        emit(
            "workflow_budget",
            {
                "agentId": a["id"],
                "agent": a["name"],
                "implementation": "ebook_workflow.plan → runtime.build_agent",
                "where": "Local CrewAI request budget",
                "explanation": "This illustrated book request needs several image generations and PDF assembly. The effective limits apply to this request only.",
                **workflow,
            },
        )
    agent_config["provider"] = a["model"]["connection"]
    agent_config["model"] = a["model"]["name"]
    if not agent_config["model"]:
        raise ValueError(f"{a['name']}: choose a model in Profile before running AI.")
    agent_config.update(
        {k: a["model"][k] for k in ["temperature", "maxOutputTokens", "contextWindow"]}
    )
    agent_config.update(
        agentId=a["id"],
        agentName=a["name"],
        imageTimeoutSeconds=max(15, a["behavior"]["maxExecutionSeconds"] - 15),
    )
    # Delegation, skills and file inspection need native tools just as images do.
    # Tool-call support must not depend on the independent image runtime login.
    agent_config["nativeTools"] = a["model"]["connection"] == "chatgpt"
    llm = ResponsesLLM(agent_config, emit)
    assigned = [] if manager else builtin_tools(a, emit, llm, state["catalog"]["mcp"])
    skill = ""
    for skill_id in a["skills"]:
        definition = next(x for x in state["catalog"]["skills"] if x["id"] == skill_id)
        missing = set(definition["requires"]) - set(a["tools"] + a["mcp"])
        if missing:
            raise ValueError(
                f"{a['name']}: skill {definition['name']} needs explicit permission for "
                + ", ".join(sorted(missing))
            )
        skill += " " + definition["description"]
    skill_catalog = state["catalog"]["skills"]
    available = available_skills(skill_catalog, a, manager)
    if available:
        skill += (
            "\nAvailable skills (call use_skill to load instructions when relevant):\n" + available
        )
    if not manager and a["skills"]:
        assigned.append(
            SkillSelector(
                actor=a, catalog=skill_catalog, members=[a], selections={}, event_sink=emit
            )
        )
    if "image-generator" in a["tools"]:
        skill += "\nFor image creation requests, call image_generator. Only report an image as generated after the tool returns a real PNG artifact URL. A description or promise is not a generated image."
    agent = agent_class(
        role=a["role"],
        goal=a["goal"] + skill,
        backstory="You are a helpful teaching assistant. Do not reveal private reasoning.\n"
        + profiles.prompt_context(a),
        llm=llm,
        tools=assigned,
        allow_delegation=False,
        verbose=False,
        max_iter=iterations,
        max_retry_limit=a["behavior"]["maxRetries"],
        max_execution_time=execution_seconds,
        max_rpm=a["behavior"]["maxRequestsPerMinute"] or None,
        respect_context_window=a["behavior"]["respectContextWindow"],
        **extra,
    )
    return agent, llm, agent_config, skill


def pdf_result_guardrail(goal, config, emit):
    if not re.search(r"\b(pdf|e-?book)\b", goal, re.I):
        return None

    def check(output):
        documents = [
            a
            for a in config.get("conversationArtifacts", [])
            if a.get("extension") == "pdf" and a.get("runId") == config.get("run_id", "standalone")
        ]
        workflow = config.get("ebookWorkflow")
        if workflow:
            documents = [
                a
                for a in documents
                if a.get("document", {}).get("hasCover")
                and a["document"].get("coverIllustrated")
                and a["document"].get("chapterCount") == workflow["chapters"]
                and a["document"].get("illustratedChapters") == workflow["chapters"]
                and a["document"].get("uniqueIllustrations", 0) >= workflow["illustrations"]
                and (
                    not workflow.get("requireNewIllustrations")
                    or all(
                        r == config.get("run_id", "standalone")
                        for r in a["document"].get("illustrationRunIds", [])
                    )
                )
            ]
        if documents:
            return True, output
        emit(
            "output_validation_failed",
            {
                "implementation": "runtime.pdf_result_guardrail",
                "where": "Local generated-file verification",
                "explanation": "The requested PDF, or its required cover/illustrated chapters, has not been completed during this execution.",
            },
        )
        return (
            False,
            "Create the requested real PDF with pdf_generator after its illustrations are ready. For an ebook, include an illustrated cover and every requested chapter with a DISTINCT illustration. Do not reuse the same image for multiple chapters. Generate missing scenes with image_generator before assembling the PDF. Do not claim completion without a new PDF artifact. If tools/permissions are missing or a provider failed, explain the concrete failure.",
        )

    return check


def image_result_guardrail(actor, goal, llm, emit):
    # A PDF reusing an existing illustration must not force a new image generation.
    if re.search(r"\bpdf\b", goal, re.I):
        return None
    if "image-generator" not in actor["tools"] or not (
        re.search(
            r"\b(image|picture|photo|illustration|imagem|foto|ilustra[çc][aã]o)\b", goal, re.I
        )
        and re.search(
            r"\b(create|generate|draw|make|paint|crie|criar|gere|gerar|desenhe|fa[çc]a)\b",
            goal,
            re.I,
        )
    ):
        return None

    def check(output):
        if llm.generated_images:
            return True, output
        emit(
            "output_validation_failed",
            {
                "agentId": actor["id"],
                "agent": actor["name"],
                "implementation": "runtime.image_result_guardrail",
                "where": "Local artifact verification",
                "explanation": "The answer was rejected because the requested image has no real generated artifact.",
            },
        )
        return (
            False,
            "No actual image artifact exists. Call image_generator now and return its PNG URL. Do not claim image generation from text alone.",
        )

    return check


def execute(state, body, emit, config=None):
    from execution_context import conversation_prompt, resolve_target

    config = dict(config or auth.settings())
    config.setdefault("conversationArtifacts", list(body.get("conversationArtifacts", [])))
    from ebook_workflow import plan

    config["ebookWorkflow"] = plan(body.get("goal", ""))
    team, members = resolve_target(state, body)
    if team.get("manager") and body.get("mode") != "one":
        from orchestration import execute_managed

        return execute_managed(state, body, emit, config)
    goal = body.get("goal", "").strip()
    if not goal or len(goal) > 8000:
        raise ValueError("Write a message (1–8000 characters).")
    agents = []
    tasks = []
    steps = []
    for i, original in enumerate(members):
        a = profiles.validate(original)
        agent, llm, agent_config, skill = build_agent(a, state, config, emit)
        llm.current = i
        llm.config["requireImage"] = image_result_guardrail(a, goal, llm, emit) is not None

        def callback(output, i=i, a=a, llm=llm, agent_config=agent_config):
            result = {
                "agent": a["name"],
                "agentId": a["id"],
                "avatar": a["avatar"],
                "input": goal if i == 0 else steps[-1]["output"],
                "output": output.raw,
                "why": f"Teaching explanation: {a['name']} was assigned this job: {a['job']}. This describes the setup, not private reasoning.",
                "assignments": {k: a[k] for k in ["tools", "skills", "mcp"]},
                "model": agent_config["model"],
                "profile": {
                    "role": a["role"],
                    "goal": a["goal"],
                    "behavior": a["behavior"],
                    "connection": a["model"]["connection"],
                },
                "inputTokens": None,
                "outputTokens": None,
            }
            usage = [u for u in llm.usage if u["step"] == i]
            if usage and all(u["input"] is not None for u in usage):
                result["inputTokens"] = sum(u["input"] for u in usage)
                result["outputTokens"] = sum(u["output"] for u in usage)
            steps.append(result)
            emit(
                "agent_completed",
                {"agentId": a["id"], "agent": a["name"], "manager": False, "output": output.raw},
            )
            emit("step_completed", {"index": i, "result": result})
            if i + 1 < len(members):
                emit("step_started", {"index": i + 1, "agent": members[i + 1]["name"]})
                emit(
                    "agent_started",
                    {
                        "agentId": members[i + 1]["id"],
                        "agent": members[i + 1]["name"],
                        "task": tasks[i + 1].description,
                        "implementation": "runtime.execute",
                        "where": "Local CrewAI sequential task",
                    },
                )

        task = Task(
            description=f"Current user message: {goal}{conversation_prompt(body)}\nYour job: {a['goal']}.{skill}\nAgent instructions: {a['instructions']}\nUse previous task results when provided.",
            expected_output=a["expectedOutput"],
            agent=agent,
            context=list(tasks),
            callback=callback,
            guardrail=(
                pdf_result_guardrail(goal, llm.config, emit)
                if "pdf-generator" in a["tools"]
                else None
            )
            or image_result_guardrail(a, goal, llm, emit),
            guardrail_max_retries=1,
        )
        agents.append(agent)
        tasks.append(task)
    emit("step_started", {"index": 0, "agent": members[0]["name"]})
    emit(
        "agent_started",
        {"agentId": members[0]["id"], "agent": members[0]["name"], "task": tasks[0].description},
    )
    Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=False,
        memory=False,
        cache=False,
        share_crew=False,
    ).kickoff()
    return steps
