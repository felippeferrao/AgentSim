"""Manager-led CrewAI execution with scoped, public interaction telemetry."""

from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.tools.agent_tools.ask_question_tool import AskQuestionTool
from crewai.tools.agent_tools.delegate_work_tool import DelegateWorkTool
from pydantic import Field

import profiles
from runtime import build_agent


class InteractionTool:
    """Track public delegation payloads, never raw LLM reasoning."""

    def _execute(self, agent_name, task, context=None):
        target = next(
            (
                a
                for a in self.agents
                if self.sanitize_agent_name(a.role) == self.sanitize_agent_name(agent_name)
            ),
            None,
        )
        if target is None:
            return super()._execute(agent_name, task, context)
        sender = self.owner
        recipient = target.profile_data
        route = {
            "fromId": sender["id"],
            "from": sender["name"],
            "toId": recipient["id"],
            "to": recipient["name"],
        }
        self.event_sink("agent_waiting", {"agentId": sender["id"]})
        self.event_sink(
            "delegation", {**route, "kind": self.kind, "message": task, "context": context or ""}
        )
        result = super()._execute(agent_name, task, context)
        self.event_sink(
            "reply",
            {
                "fromId": recipient["id"],
                "from": recipient["name"],
                "toId": sender["id"],
                "to": sender["name"],
                "message": result,
            },
        )
        self.event_sink("agent_resumed", {"agentId": sender["id"]})
        return result


class TrackedDelegate(InteractionTool, DelegateWorkTool):
    owner: dict = Field(exclude=True)
    event_sink: Any = Field(exclude=True)
    kind: str = "task"


class TrackedQuestion(InteractionTool, AskQuestionTool):
    owner: dict = Field(exclude=True)
    event_sink: Any = Field(exclude=True)
    kind: str = "question"


class ObservedAgent(Agent):
    profile_data: dict = Field(exclude=True)
    event_sink: Any = Field(exclude=True)
    results: Any = Field(exclude=True)
    is_manager: bool = False

    def get_delegation_tools(self, agents):
        args = {"agents": list(agents), "owner": self.profile_data, "event_sink": self.event_sink}
        from crewai.utilities.i18n import I18N_DEFAULT

        coworkers = ", ".join(a.role for a in agents)
        return [
            TrackedDelegate(
                **args, description=I18N_DEFAULT.tools("delegate_work").format(coworkers=coworkers)
            ),
            TrackedQuestion(
                **args, description=I18N_DEFAULT.tools("ask_question").format(coworkers=coworkers)
            ),
        ]

    def execute_task(self, task, context=None, tools=None):
        a = self.profile_data
        start = len(self.llm.usage)
        self.event_sink(
            "agent_started",
            {
                "agentId": a["id"],
                "agent": a["name"],
                "task": task.description,
                "context": context or "",
            },
        )
        try:
            output = super().execute_task(task, context, tools)
        except Exception:
            self.event_sink("agent_failed", {"agentId": a["id"], "agent": a["name"]})
            raise
        usage = self.llm.usage[start:]
        result = {
            "agentId": a["id"],
            "agent": a["name"],
            "avatar": a["avatar"],
            "input": task.description,
            "context": context or "",
            "output": output,
            "why": "Manager coordinating the goal."
            if self.is_manager
            else "Task delegated by the team's manager.",
            "assignments": {
                k: ([] if self.is_manager and k in ("tools", "mcp") else a[k])
                for k in ("tools", "skills", "mcp")
            },
            "model": a["model"]["name"],
            "inputTokens": sum(u["input"] for u in usage)
            if usage and all(u["input"] is not None for u in usage)
            else None,
            "outputTokens": sum(u["output"] for u in usage)
            if usage and all(u["output"] is not None for u in usage)
            else None,
        }
        self.results.append(result)
        self.event_sink(
            "agent_completed",
            {"agentId": a["id"], "agent": a["name"], "manager": self.is_manager, "output": output},
        )
        self.event_sink("step_completed", {"index": len(self.results) - 1, "result": result})
        return output


def execute_managed(state, body, emit, config):
    team = next(t for t in state["teams"] if t["id"] == body["team"])
    members = [
        profiles.validate(next(a for a in state["agents"] if a["id"] == ident))
        for ident in team["agents"]
    ]
    manager_profile = next((a for a in members if a["id"] == team["manager"]), None)
    if manager_profile is None or len(members) < 2:
        raise ValueError("Choose a manager and at least one other agent in Teams.")
    goal = body.get("goal", "").strip()
    if not goal or len(goal) > 500:
        raise ValueError("Add a goal (up to 500 characters).")
    results = []
    workers = []
    manager = None
    for i, a in enumerate(members):
        is_manager = a["id"] == manager_profile["id"]
        agent, llm, _, _ = build_agent(
            a,
            state,
            config,
            emit,
            agent_class=ObservedAgent,
            manager=is_manager,
            profile_data=a,
            event_sink=emit,
            results=results,
            is_manager=is_manager,
        )
        llm.current = i
        # Distinct, readable routing names also support agents with the same specialty.
        agent.role = f"{i + 1}. {a['name']} — {a['role']}"
        if is_manager:
            manager = agent
        else:
            workers.append(agent)
    roster = "\n".join(
        f"- {a.role}: {a.profile_data['goal']}. Expected result: {a.profile_data['expectedOutput']}"
        for a in workers
    )
    task = Task(
        description=(
            f"Current goal: {goal}\nYou are the team's manager. Decide which agents to involve and in what order. "
            "Delegate work or ask questions using the coworker tools, then assess their replies. "
            "You may revisit an agent, skip irrelevant agents or answer directly when appropriate. "
            "There is no fixed pipeline. Do not invent conversations or claim unperformed work. "
            "Give a final answer for the user's goal.\n"
            f"Available agents:\n{roster}\nManager instructions: {manager_profile['instructions']}"
        ),
        expected_output=manager_profile["expectedOutput"],
    )
    emit("run_started", {"orchestration": "managed", "managerId": manager_profile["id"]})
    Crew(
        agents=workers,
        manager_agent=manager,
        tasks=[task],
        process=Process.hierarchical,
        verbose=False,
        memory=False,
        cache=False,
        share_crew=False,
    ).kickoff()
    return results
