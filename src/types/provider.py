from typing import Any

from pydantic import BaseModel


class ModelLimit(BaseModel):
    context: int | None = None
    output: int | None = None


class Modalities(BaseModel):
    input: list[str] = []
    output: list[str] = []


class ReasoningOptionEffort(BaseModel):
    type: str
    values: list[str]


class ReasoningOptionBudget(BaseModel):
    type: str
    min: int


class ReasoningOptionToggle(BaseModel):
    type: str


class TierCondition(BaseModel):
    type: str
    size: int


class CostTier(BaseModel):
    input: float
    output: float
    cache_read: float | None = None


class CostTierEntry(BaseModel):
    input: float
    output: float
    cache_read: float | None = None
    tier: TierCondition


class Cost(BaseModel):
    input: float | None = None
    output: float | None = None
    cache_read: float | None = None
    cache_write: float | None = None
    input_audio: float | None = None
    output_audio: float | None = None
    reasoning: float | None = None
    tiers: list[CostTierEntry] | None = None
    context_over_200k: CostTier | None = None


class Model(BaseModel):
    id: str
    name: str
    family: str | None = None
    attachment: bool | None = None
    reasoning: bool | None = None
    reasoning_options: list[ReasoningOptionEffort | ReasoningOptionBudget | ReasoningOptionToggle] | None = None
    tool_call: bool | None = None
    structured_output: bool | None = None
    temperature: bool | None = None
    interleaved: bool | dict[str, Any] | None = None
    experimental: dict[str, Any] | None = None
    knowledge: str | None = None
    release_date: str | None = None
    last_updated: str | None = None
    status: str | None = None
    modalities: Modalities | None = None
    open_weights: bool | None = None
    limit: ModelLimit | None = None
    cost: Cost | None = None


class Provider(BaseModel):
    id: str
    name: str
    npm: str
    api: str | None = None
    env: list[str] = []
    doc: str | None = None
    models: dict[str, Model] = {}


__all__ = [
    "Provider",
    "Model",
    "ModelLimit",
    "Modalities",
    "Cost",
    "CostTier",
    "CostTierEntry",
    "TierCondition",
]
