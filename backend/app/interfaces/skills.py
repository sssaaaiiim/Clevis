from typing import Protocol

from app.core.events import Model


class Skill(Model):
    name: str
    instructions: str


class SkillProvider(Protocol):
    async def get_skills(self, goal: str, url: str) -> list[Skill]: ...


class EmptySkillProvider:
    async def get_skills(self, goal: str, url: str) -> list[Skill]:
        return []
