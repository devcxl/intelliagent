"""Provider 配置模型（ADR 0011）：线协议、端点、密钥来源与模型清单。

模型元数据全量声明；未消费字段（reasoning/cost/modalities 等）由文档标注「仅声明」，
不在这里做能力推断。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Protocol = Literal["openai", "openai-compatible", "anthropic"]
"""线协议：openai（Responses）、openai-compatible（Chat Completions）、anthropic（Messages）。"""


class Limits(BaseModel):
    """模型 token 限额。"""

    model_config = ConfigDict(extra="forbid")

    context: int | None = Field(default=None, ge=1)
    output: int | None = Field(default=None, ge=1)


class Cost(BaseModel):
    """每百万 token 单价（仅声明，当前不参与成本计算）。"""

    model_config = ConfigDict(extra="forbid")

    input: float | None = None
    output: float | None = None
    reasoning: float | None = None
    cache_read: float | None = None


class Modalities(BaseModel):
    """输入/输出模态声明（仅声明）。"""

    model_config = ConfigDict(extra="forbid")

    input: list[str] = Field(default_factory=list)
    output: list[str] = Field(default_factory=list)


class Interleaved(BaseModel):
    """交错思考字段声明（仅声明）。"""

    model_config = ConfigDict(extra="forbid")

    field: str


class ModelConfig(BaseModel):
    """一个模型条目的声明。

    Attributes:
        id: 发给上游的模型名；缺省等于模型条目键。
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str | None = None
    description: str | None = None
    attachment: bool = False
    reasoning: bool = False
    reasoning_level: list[str] = Field(default_factory=list)
    tool_call: bool = True
    interleaved: Interleaved | None = None
    structured_output: bool = False
    temperature: bool = True
    modalities: Modalities = Field(default_factory=Modalities)
    limit: Limits = Field(default_factory=Limits)
    cost: Cost | None = None


class ProviderConfig(BaseModel):
    """一个 provider 条目的声明。"""

    model_config = ConfigDict(extra="forbid")

    type: Protocol
    api: str | None = None
    env: list[str] = Field(default_factory=list)
    name: str | None = None
    models: dict[str, ModelConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_api_for_openai_compatible(self) -> ProviderConfig:
        if self.type == "openai-compatible" and not self.api:
            raise ValueError("openai-compatible provider requires api")
        return self
