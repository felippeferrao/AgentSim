"""Portable comic studio configuration and an explicitly sanitized seed database."""

import copy
import json
import sqlite3
from pathlib import Path

TEAM_ID = "comic-story-studio"
SPECIALISTS = (
    "scriptwriter",
    "illustrator",
    "layout-designer",
    "quality-validator",
    "pdf-generator",
)
DIRECTORY = Path(__file__).parent / "examples" / "comic-studio"


def build(catalog):
    from skill_files import parse_markdown

    state = json.loads((DIRECTORY / "configuration.json").read_text())
    state["catalog"] = copy.deepcopy(catalog) | state["catalog"]
    for name in ("minimax-pdf", "magazine-layout"):
        skill = parse_markdown((Path(__file__).parent / "skills" / name / "SKILL.md").read_text())
        if not any(s["id"] == skill["id"] for s in state["catalog"]["skills"]):
            state["catalog"]["skills"].append(skill)
    return state


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
