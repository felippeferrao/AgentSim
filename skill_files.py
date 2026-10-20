"""Codex SKILL.md ingestion. Imported instructions never execute uploaded code."""

import re

import yaml


def parse_markdown(text):
    if not isinstance(text, str) or len(text.encode()) > 100_000:
        raise ValueError("SKILL.md must be UTF-8 Markdown, up to 100 KB.")
    match = re.match(r"\A\ufeff?---\s*\r?\n(.*?)\r?\n---\s*\r?\n(.*)\Z", text, re.S)
    if not match:
        raise ValueError(
            "Use Codex SKILL.md format: YAML front matter with name and description, followed by Markdown instructions."
        )
    try:
        metadata = yaml.safe_load(match[1])
    except yaml.YAMLError:
        raise ValueError("Invalid YAML front matter.") from None
    if not isinstance(metadata, dict):
        raise ValueError("Skill front matter must be a mapping.")
    name, description = metadata.get("name"), metadata.get("description")
    if (
        not isinstance(name, str)
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
        or len(name) > 64
    ):
        raise ValueError(
            "Skill name must use lowercase letters, numbers and single hyphens (up to 64 characters)."
        )
    if (
        not isinstance(description, str)
        or not 0 < len(description.strip()) <= 1024
        or not match[2].strip()
    ):
        raise ValueError("Provide a description (up to 1024 characters) and Markdown instructions.")
    requires = (
        metadata.get("metadata", {}).get("requires", [])
        if isinstance(metadata.get("metadata", {}), dict)
        else []
    )
    if not isinstance(requires, list) or not all(isinstance(r, str) for r in requires):
        raise ValueError("metadata.requires must be a list of tool ids.")
    return {
        "id": name,
        "name": name,
        "description": description.strip(),
        "instructions": match[2].strip(),
        "requires": requires,
        "markdown": text,
        "format": "codex-skill",
    }
