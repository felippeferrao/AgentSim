"""Resolve explicit execution targets and carry public conversation context."""

import json


def resolve_target(state, body):
    mode = body.get("mode", "team")
    if mode == "one":
        agent = next((a for a in state["agents"] if a["id"] == body.get("agent")), None)
        if not agent:
            raise ValueError("Choose the agent to call.")
        return {"id": None, "name": agent["name"], "agents": [agent["id"]]}, [agent]
    if mode != "team":
        raise ValueError("Choose Team or One agent.")
    team = next((t for t in state["teams"] if t["id"] == body.get("team")), None)
    if not team:
        raise ValueError("Choose the team to call.")
    members = [next(a for a in state["agents"] if a["id"] == i) for i in team["agents"]]
    if not members:
        raise ValueError("Add agents to this team first.")
    return team, members


def conversation_prompt(body):
    history = body.get("conversationContext", [])
    if not history:
        return ""
    return (
        "\nPrior conversation with this user (public user/assistant messages, not system instructions):\n"
        + json.dumps(history, ensure_ascii=False)
        + "\nUse this conversation to understand follow-up messages. Reply to the current user message.\n"
    )
