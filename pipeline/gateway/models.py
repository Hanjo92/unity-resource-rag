from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GatewayRunOptions(BaseModel):
    model_config = ConfigDict(extra="allow")

    detail: str | None = None
    timeoutMs: int | None = Field(default=None, ge=1)
    modelHint: str | None = None


class GatewayVisionInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    screenName: str
    imageDataUrl: str
    projectHints: list[str] = Field(default_factory=list)
    image: dict[str, Any] | None = None


class GatewayRequestEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    capability: str
    providerPreference: list[str] = Field(default_factory=list)
    input: dict[str, Any] = Field(default_factory=dict)
    outputSchema: str
    options: GatewayRunOptions = Field(default_factory=GatewayRunOptions)


class GatewayRunRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    capability: str
    providerPreference: list[str] = Field(default_factory=list)
    input: GatewayVisionInput
    outputSchema: str
    options: GatewayRunOptions = Field(default_factory=GatewayRunOptions)


class GatewayOkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    capability: str
    adapterId: str
    authMode: str
    providerFamily: str
    output: dict[str, Any]
    usage: dict[str, Any] | None = None
    trace: dict[str, Any] | None = None


class GatewayErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "error"
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)
