"""Validated agent profiles and backward-compatible persisted migration."""

import copy
import math

BASE = {"id", "name", "job", "tools", "skills", "mcp", "example", "avatar"}
TEXT = {
    "role": 160,
    "goal": 1000,
    "backstory": 4000,
    "instructions": 4000,
    "purpose": 1000,
    "exampleInput": 2000,
    "exampleOutput": 2000,
    "expectedOutput": 2000,
}
EXTRA = set(TEXT) | {"model", "behavior", "profileVersion"}


def normalize(agent):
    if not isinstance(agent, dict) or set(agent) - BASE - EXTRA:
        raise ValueError("Unknown agent fields. Executable uploads are not accepted.")
    result = copy.deepcopy(agent)
    result.setdefault("role", result.get("name", ""))
    result.setdefault("goal", result.get("job", ""))
    result["avatar"] = result.get("avatar") or {
        "Researcher": "researcher",
        "Writer": "writer",
        "Reviewer": "reviewer",
    }.get(result.get("name"), "robot")
    result["job"] = result["goal"]
    for k in TEXT:
        result.setdefault(k, "")
    result.setdefault("expectedOutput", "A short, helpful answer in plain English.")
    if not result["expectedOutput"]:
        result["expectedOutput"] = "A short, helpful answer in plain English."
    result.setdefault(
        "model", {"mode": "inherit", "name": "", "temperature": None, "maxOutputTokens": None}
    )
    result.setdefault(
        "behavior",
        {
            "maxIterations": 6,
            "maxRetries": 0,
            "maxExecutionSeconds": 120,
            "maxRequestsPerMinute": 0,
            "respectContextWindow": True,
        },
    )
    result["model"] = {
        "mode": "inherit",
        "name": "",
        "temperature": None,
        "maxOutputTokens": None,
        "contextWindow": 32000,
        "connection": "chatgpt",
    } | result["model"]
    result["profileVersion"] = 1
    return result


def validate(agent):
    a = normalize(agent)
    if a["avatar"] not in ("researcher", "writer", "reviewer", "robot"):
        raise ValueError("Choose one of the available character portraits.")
    for key, limit in TEXT.items():
        if (
            not isinstance(a[key], str)
            or len(a[key]) > limit
            or (key in ("role", "goal") and not a[key].strip())
        ):
            raise ValueError(
                f"Agent {key} must be plain text (up to {limit} characters); role and goal cannot be empty."
            )
    m = a["model"]
    if (
        not isinstance(m, dict)
        or set(m)
        != {"mode", "name", "temperature", "maxOutputTokens", "contextWindow", "connection"}
        or m["mode"] not in ("inherit", "custom")
    ):
        raise ValueError("Choose the shared model or a custom model for this agent.")
    if m["connection"] not in ("chatgpt", "api"):
        raise ValueError("Choose ChatGPT or your API connection for this agent.")
    if not isinstance(m["name"], str) or len(m["name"]) > 150:
        raise ValueError("Enter the custom model name.")
    if m["temperature"] is not None and (
        type(m["temperature"]) not in (int, float)
        or not math.isfinite(m["temperature"])
        or not 0 <= m["temperature"] <= 2
    ):
        raise ValueError("Temperature must be blank or a number from 0 to 2.")
    if m["maxOutputTokens"] is not None and (
        type(m["maxOutputTokens"]) is not int or not 16 <= m["maxOutputTokens"] <= 16000
    ):
        raise ValueError("Output token limit must be blank or an integer from 16 to 16000.")
    if type(m["contextWindow"]) is not int or not 4096 <= m["contextWindow"] <= 2000000:
        raise ValueError("Context budget must be 4096–2000000 tokens.")
    b = a["behavior"]
    bounds = {
        "maxIterations": (1, 20),
        "maxRetries": (0, 2),
        "maxExecutionSeconds": (10, 600),
        "maxRequestsPerMinute": (0, 120),
    }
    if (
        not isinstance(b, dict)
        or set(b) != set(bounds) | {"respectContextWindow"}
        or type(b["respectContextWindow"]) is not bool
    ):
        raise ValueError("Invalid agent behavior settings.")
    for key, (low, high) in bounds.items():
        if type(b[key]) is not int or not low <= b[key] <= high:
            raise ValueError(f"{key} must be a whole number from {low} to {high}.")
    return a


def prompt_context(a):
    parts = [a["backstory"], a["instructions"]]
    if a["purpose"]:
        parts.append("Purpose: " + a["purpose"])
    if a["exampleInput"] or a["exampleOutput"]:
        parts.append(
            "<teaching_examples>\nThese are style examples only, not the current goal or verified facts.\nExample input: "
            + a["exampleInput"]
            + "\nExample answer: "
            + a["exampleOutput"]
            + "\n</teaching_examples>"
        )
    return "\n\n".join(p for p in parts if p)
