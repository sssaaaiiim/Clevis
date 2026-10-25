"""Validated per-run ceilings and capabilities; no environment reads during validation."""

from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agent.policy.domains import parse_domains

if TYPE_CHECKING:
    from app.config import Settings


class RunPermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    allow_form_submit: bool = True
    allow_downloads: bool = False
    allow_uploads: bool = False
    allow_send_message: bool = True
    allow_cross_domain_data: bool = False
    max_steps: int | None = Field(default=None, ge=1)
    max_cost_usd: float | None = Field(default=None, ge=0.01, allow_inf_nan=False)
    max_handoffs: int | None = Field(default=None, ge=0)

    @field_validator("allowed_domains", "blocked_domains")
    @classmethod
    def domains(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip() or "," in value:
                raise ValueError("Each domain must be one hostname or *.")
            parse_domains(value)
        return sorted({v.strip().lower().rstrip(".") for v in values})

    @model_validator(mode="after")
    def disjoint(self) -> Self:
        if set(self.allowed_domains) & set(self.blocked_domains):
            raise ValueError("A domain cannot be both allowed and blocked.")
        return self


def resolve_permissions(request: RunPermissions | None, settings: "Settings") -> RunPermissions:
    permissions = (request or RunPermissions()).model_copy(deep=True)
    if permissions.max_steps is not None and permissions.max_steps > settings.max_steps:
        raise ValueError("max_steps must not exceed MAX_STEPS.")
    if (
        permissions.max_cost_usd is not None
        and settings.max_cost_usd > 0
        and permissions.max_cost_usd > settings.max_cost_usd
    ):
        raise ValueError("max_cost_usd must not exceed MAX_COST_USD.")
    if permissions.max_handoffs is not None and permissions.max_handoffs > settings.max_handoffs:
        raise ValueError("max_handoffs must not exceed MAX_HANDOFFS.")
    permissions.allowed_domains = permissions.allowed_domains or sorted(
        parse_domains(settings.allowed_domains)
    )
    permissions.blocked_domains = sorted(
        set(permissions.blocked_domains) | parse_domains(settings.blocked_domains)
    )
    if set(permissions.allowed_domains) & set(permissions.blocked_domains):
        raise ValueError("An allowed domain is blocked by global policy.")
    # Global deny rules cannot be removed by a per-run request.
    permissions.max_steps = (
        permissions.max_steps if permissions.max_steps is not None else settings.max_steps
    )
    permissions.max_cost_usd = (
        permissions.max_cost_usd
        if permissions.max_cost_usd is not None
        else (settings.max_cost_usd or None)
    )
    permissions.max_handoffs = (
        permissions.max_handoffs if permissions.max_handoffs is not None else settings.max_handoffs
    )
    return permissions
