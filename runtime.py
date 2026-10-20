"""Real CrewAI sequential tasks with a Responses adapter and allowlisted tools."""

import ast
import asyncio
import operator
import os
import sys

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_TELEMETRY_ENABLED"] = "false"
from pathlib import Path

from crewai import Agent, BaseLLM, Crew, Process, Task
from crewai.tools import tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI

import auth

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
        return 32000

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
        with client.responses.create(
            model=self.model, input=inputs, store=False, stream=True
        ) as stream:
            for event in stream:
                if event.type == "response.completed":
                    final = event.response
                elif event.type in ("response.failed", "response.incomplete", "error"):
                    raise ValueError(
                        "The provider did not complete this request. Check connection and usage limits."
                    )
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


def execute(state, body, emit, config=None):
    config = dict(config or auth.settings())
    if config["provider"] == "demo":
        raise ValueError("Choose a real provider in Connection setup.")
    if not config.get("model"):
        raise ValueError("Choose a model in Connection setup.")
    team = next((t for t in state["teams"] if t["id"] == body.get("team")), None)
    if not team:
        raise ValueError("Choose a team.")
    members = [next(a for a in state["agents"] if a["id"] == i) for i in team["agents"]]
    if body.get("mode") == "one":
        members = members[:1]
    goal = body.get("goal", "").strip()
    if not goal or len(goal) > 500 or not members:
        raise ValueError("Add a goal and at least one helper.")
    llm = ResponsesLLM(config, emit)
    agents = []
    tasks = []
    steps = []
    for i, a in enumerate(members):
        assigned = []

        def tracked(name, fn):
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
            role=a["name"],
            goal=a["job"] + skill,
            backstory="You are a helpful teaching assistant. Give only useful answers. Do not reveal private reasoning.",
            llm=llm,
            tools=assigned,
            allow_delegation=False,
            verbose=False,
            max_iter=6,
            max_retry_limit=0,
        )

        def callback(output, i=i, a=a):
            result = {
                "agent": a["name"],
                "agentId": a["id"],
                "input": goal if i == 0 else steps[-1]["output"],
                "output": output.raw,
                "why": f"Teaching explanation: {a['name']} was assigned this job: {a['job']}. This describes the setup, not private reasoning.",
                "assignments": {k: a[k] for k in ["tools", "skills", "mcp"]},
                "inputTokens": None,
                "outputTokens": None,
            }
            usage = [u for u in llm.usage if u["step"] == i]
            if usage and all(u["input"] is not None for u in usage):
                result["inputTokens"] = sum(u["input"] for u in usage)
                result["outputTokens"] = sum(u["output"] for u in usage)
            steps.append(result)
            emit("step_completed", {"index": i, "result": result})
            llm.current = i + 1
            if i + 1 < len(members):
                emit("step_started", {"index": i + 1, "agent": members[i + 1]["name"]})

        task = Task(
            description=f"Goal: {goal}\nYour job: {a['job']}.{skill}\nUse previous task results when provided.",
            expected_output="A short, helpful answer in plain English.",
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
