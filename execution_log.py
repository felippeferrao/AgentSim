"""Public event explanations and implementation provenance; never hidden reasoning."""

RULES = {
    "run_started": (
        "orchestration.execute_managed",
        "Local CrewAI manager",
        "The configured manager began coordinating the goal.",
    ),
    "agent_started": (
        "orchestration.ObservedAgent",
        "Local CrewAI agent",
        "An agent received this task and context.",
    ),
    "agent_waiting": (
        "orchestration.InteractionTool",
        "Local CrewAI delegation",
        "The manager is waiting for a delegated task or question.",
    ),
    "agent_resumed": (
        "orchestration.InteractionTool",
        "Local CrewAI delegation",
        "A reply returned; the manager can decide its next action.",
    ),
    "delegation": (
        "orchestration.InteractionTool",
        "Local CrewAI delegation",
        "The manager chose the named recipient and sent this actual task/question.",
    ),
    "reply": (
        "orchestration.InteractionTool",
        "Local CrewAI delegation",
        "The recipient returned this result to the manager.",
    ),
    "model_started": (
        "runtime.ResponsesLLM",
        "Selected provider model",
        "An inference request began using this agent's configured model.",
    ),
    "usage": (
        "runtime.ResponsesLLM",
        "Provider response",
        "Token counts were reported by the provider.",
    ),
    "agent_completed": (
        "orchestration.ObservedAgent",
        "Local CrewAI agent",
        "The agent completed its task and returned a public answer.",
    ),
    "agent_failed": (
        "orchestration.ObservedAgent",
        "Local CrewAI agent",
        "The agent could not complete this task.",
    ),
    "step_completed": (
        "runtime.execute / orchestration.ObservedAgent",
        "Local harness",
        "A completed task result was recorded.",
    ),
    "tool_started": (
        "runtime.builtin_tools / runtime.HTTPMCPTool",
        "Assigned tool",
        "The agent requested an explicitly granted tool.",
    ),
    "tool_completed": (
        "runtime.builtin_tools / runtime.HTTPMCPTool",
        "Assigned tool",
        "The real tool result was returned to the agent.",
    ),
    "tool_failed": (
        "runtime.HTTPMCPTool",
        "Assigned tool",
        "The tool failed; no fabricated result was substituted.",
    ),
    "run_failed": (
        "server.Handler.work",
        "Local execution worker",
        "The run stopped with an error; earlier events and outputs are preserved.",
    ),
}


def enrich(kind, data, agents=()):
    implementation, where, explanation = RULES.get(
        kind, ("server.Handler", "Local harness", kind.replace("_", " ").capitalize())
    )
    result = {"implementation": implementation, "where": where, "explanation": explanation, **data}
    actor_id = (
        (data.get("selectedById") if kind == "skill_selected" else None)
        or data.get("fromId")
        or data.get("agentId")
        or data.get("result", {}).get("agentId")
    )
    actor = next((a for a in agents if a["id"] == actor_id), None)
    if actor:
        result["actor"] = {
            "agentId": actor["id"],
            "agent": actor["name"],
            "avatar": actor["avatar"],
        }
    return result
