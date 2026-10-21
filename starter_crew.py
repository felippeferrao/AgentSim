"""Portable comic studio configuration and an explicitly sanitized seed database."""

import copy
import json
import sqlite3
from pathlib import Path

TEAM_ID = "comic-story-studio"
STAGES = ("scriptwriter", "illustrator", "layout-designer", "quality-validator", "pdf-generator")
DIRECTORY = Path(__file__).parent / "examples" / "comic-studio"


def build(catalog):
    state = json.loads((DIRECTORY / "configuration.json").read_text())
    state["catalog"] = copy.deepcopy(catalog) | state["catalog"]
    return state


def stage_problem(results, include_publisher=True):
    required = STAGES if include_publisher else STAGES[:-1]
    latest = {r["agentId"]: (i, r) for i, r in enumerate(results)}
    missing = [ident for ident in required if ident not in latest]
    if missing:
        return "Delegate the missing production stages: " + ", ".join(missing) + "."
    positions = [latest[ident][0] for ident in required]
    if positions != sorted(positions):
        return "An earlier stage was revised. Repeat layout, validation and publication in dependency order."
    review = latest["quality-validator"][1]["output"].strip()
    if not review or review.splitlines()[0].strip().upper() != "APPROVED":
        return "Quality Validator has not approved the latest layout. Resolve her corrections and obtain a fresh APPROVED review."
    return None


def completion_guardrail(config, results, emit, pdf_check):
    def check(output):
        problem = stage_problem(results)
        if problem:
            emit(
                "workflow_validation_failed",
                {
                    "implementation": "starter_crew.completion_guardrail",
                    "where": "Local comic production stage verification",
                    "explanation": problem,
                },
            )
            return False, problem + " Do not claim the comic is finished."
        return pdf_check(output)

    return check


def write_seed(catalog):
    path = DIRECTORY / "starter.sqlite3"
    temporary = path.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    with sqlite3.connect(temporary) as db:
        db.execute("CREATE TABLE state (id INTEGER PRIMARY KEY, data TEXT)")
        db.execute("CREATE TABLE executions (id TEXT PRIMARY KEY, data TEXT)")
        db.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, data TEXT)")
        db.execute("INSERT INTO state VALUES (1,?)", (json.dumps(build(catalog)),))
    temporary.replace(path)
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build the sanitized comic studio example database."
    )
    parser.add_argument("--build-seed", action="store_true", required=True)
    parser.parse_args()
    import server

    state = server.validate(build(server.CATALOG))
    assert state["runs"] == []
    print(write_seed(server.CATALOG))
