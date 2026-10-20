"""Explicit skill selection and progressive disclosure in the agent loop."""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class SkillArgs(BaseModel):
    skill_id: str
    reason: str = Field(
        description="Short public explanation of why this skill fits the task; no private reasoning."
    )
    agent_id: str = Field(
        default="", description="Manager only: target member id. Blank applies to yourself."
    )


class SkillSelector(BaseTool):
    name: str = "use_skill"
    description: str = "Load a registered skill only when needed. State a short public reason. Skills do not grant tool permissions. Managers may select a skill for a team member before delegating."
    args_schema: type[BaseModel] = SkillArgs
    actor: dict = Field(exclude=True)
    catalog: list = Field(exclude=True)
    members: list = Field(exclude=True)
    selections: object = Field(exclude=True)
    event_sink: object = Field(exclude=True)
    manager: bool = False

    def _run(self, skill_id, reason, agent_id=""):
        try:
            return self._select(skill_id, reason, agent_id)
        except ValueError as exc:
            self.event_sink(
                "skill_selection_failed",
                {
                    "agentId": self.actor["id"],
                    "skillId": skill_id,
                    "error": str(exc),
                    "implementation": "skill_runtime.SkillSelector",
                    "where": "Local skill registry",
                    "explanation": "The requested skill could not be applied; tool permissions were not changed.",
                },
            )
            raise

    def _select(self, skill_id, reason, agent_id=""):
        target_id = agent_id or self.actor["id"]
        if not reason.strip() or len(reason) > 1500:
            raise ValueError("Provide a short public explanation of the skill choice.")
        target = next((a for a in self.members if a["id"] == target_id), None)
        if not target or (not self.manager and target_id != self.actor["id"]):
            raise ValueError("Skill target must be an authorized member of this team.")
        skill = next((s for s in self.catalog if s["id"] == skill_id), None)
        if not skill or (not self.manager and skill_id not in self.actor["skills"]):
            raise ValueError("This skill is not available to this agent.")
        missing = set(skill["requires"]) - set(target["tools"] + target["mcp"])
        if missing:
            raise ValueError(
                "Skill requires explicit tool permissions: " + ", ".join(sorted(missing))
            )
        self.selections.setdefault(target_id, {})[skill_id] = skill
        self.event_sink(
            "skill_selected",
            {
                "agentId": target_id,
                "agent": target["name"],
                "selectedBy": self.actor["name"],
                "skillId": skill_id,
                "skill": skill["name"],
                "reason": reason,
                "implementation": "skill_runtime.SkillSelector",
                "where": "Local harness · SKILL.md registry",
                "explanation": "The agent explicitly chose this skill; its instructions were loaded without granting tools.",
            },
        )
        return f"Selected {skill['name']} for {target['name']}.\n{skill['instructions']}"


def available_skills(catalog, actor, manager=False):
    return "\n".join(
        f"- {s['id']}: {s['description']} (requires: {', '.join(s['requires']) or 'none'})"
        for s in catalog
        if manager or s["id"] in actor["skills"]
    )
