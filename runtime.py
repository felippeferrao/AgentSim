"""Real CrewAI sequential tasks with a Responses adapter and allowlisted tools."""

import ast
import asyncio
import operator
import os
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
import profiles

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
                    event_sink=emit,
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
        self.current = 0

    def supports_function_calling(self):
        return False

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
        # CrewAI uses a text tool protocol. Only final task output reaches the UI.
        inputs = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("system", "user", "assistant")
        ]
        final = None
        options = {}
        if self.config.get("temperature") is not None:
            options["temperature"] = self.config["temperature"]
        if self.config.get("maxOutputTokens") is not None:
            options["max_output_tokens"] = self.config["maxOutputTokens"]
        try:
            with client.responses.create(
                model=self.model, input=inputs, store=False, stream=True, **options
            ) as stream:
                for event in stream:
                    if event.type == "response.completed":
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
        usage = final.usage
        record = {
            "step": self.current,
            "input": usage.input_tokens if usage else None,
            "output": usage.output_tokens if usage else None,
        }
        self.usage.append(record)
        self.emit("usage", record)
        return final.output_text


def builtin_tools(a, emit, llm, catalog):
    assigned = []

    def tracked(name, fn, llm=llm):
        def wrapper(**args):
            emit("tool_started", {"step": llm.current, "name": name, "input": args})
            result = fn(**args)
            emit(
                "tool_completed",
                {"step": llm.current, "name": name, "output": result},
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
    assigned.extend(http_tools(a, catalog, emit, llm))
    return assigned


def execute(state, body, emit, config=None):
    config = dict(config or auth.settings())
    team = next((t for t in state["teams"] if t["id"] == body.get("team")), None)
    if not team:
        raise ValueError("Choose a team.")
    members = [next(a for a in state["agents"] if a["id"] == i) for i in team["agents"]]
    if body.get("mode") == "one":
        members = members[:1]
    goal = body.get("goal", "").strip()
    if not goal or len(goal) > 500 or not members:
        raise ValueError("Add a goal and at least one helper.")
    agents = []
    tasks = []
    steps = []
    for i, original in enumerate(members):
        a = profiles.validate(original)
        agent_config = dict(config)
        agent_config["provider"] = a["model"]["connection"]
        agent_config["model"] = a["model"]["name"]
        if not agent_config["model"]:
            raise ValueError(f"{a['name']}: choose a model in Profile before running AI.")
        agent_config.update(
            {k: a["model"][k] for k in ["temperature", "maxOutputTokens", "contextWindow"]}
        )
        llm = ResponsesLLM(agent_config, emit)
        llm.current = i
        assigned = builtin_tools(a, emit, llm, state["catalog"]["mcp"])
        skill = ""
        for skill_id in a["skills"]:
            definition = next(x for x in state["catalog"]["skills"] if x["id"] == skill_id)
            missing = set(definition["requires"]) - set(a["tools"] + a["mcp"])
            if missing:
                raise ValueError(
                    f"{a['name']}: skill {definition['name']} needs explicit permission for "
                    + ", ".join(sorted(missing))
                )
            skill += " " + definition["instructions"]
        agent = Agent(
            role=a["role"],
            goal=a["goal"] + skill,
            backstory="You are a helpful teaching assistant. Do not reveal private reasoning.\n"
            + profiles.prompt_context(a),
            llm=llm,
            tools=assigned,
            allow_delegation=False,
            verbose=False,
            max_iter=a["behavior"]["maxIterations"],
            max_retry_limit=a["behavior"]["maxRetries"],
            max_execution_time=a["behavior"]["maxExecutionSeconds"],
            max_rpm=a["behavior"]["maxRequestsPerMinute"] or None,
            respect_context_window=a["behavior"]["respectContextWindow"],
        )

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
            emit("step_completed", {"index": i, "result": result})
            if i + 1 < len(members):
                emit("step_started", {"index": i + 1, "agent": members[i + 1]["name"]})

        task = Task(
            description=f"Current goal: {goal}\nYour job: {a['goal']}.{skill}\nAgent instructions: {a['instructions']}\nUse previous task results when provided.",
            expected_output=a["expectedOutput"],
            agent=agent,
            context=list(tasks),
            callback=callback,
        )
        agents.append(agent)
        tasks.append(task)
    emit("step_started", {"index": 0, "agent": members[0]["name"]})
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
