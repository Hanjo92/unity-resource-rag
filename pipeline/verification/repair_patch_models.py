from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RepairPatchNodeRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    name: str | None = None
    kind: str | None = None
    hierarchyPath: str | None = None
    assetPath: str | None = None
    overlapScore: float | None = Field(default=None, ge=0.0, le=1.0)


class RepairPatchStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    target: str | None = None
    rationale: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class RepairPatchCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    issueType: str
    severity: str
    repairType: str
    title: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    targetNodes: list[RepairPatchNodeRef] = Field(default_factory=list)
    patchSteps: list[RepairPatchStep] = Field(default_factory=list)
    boundedScope: list[str] = Field(default_factory=list)
    sourceIssue: dict[str, Any] = Field(default_factory=dict)


class RepairPatchCandidateSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = "ui_repair_patch_candidates"
    sourceVerificationReport: str | None = None
    screenName: str | None = None
    hasMeaningfulMismatch: bool = False
    candidateCount: int = 0
    candidates: list[RepairPatchCandidate] = Field(default_factory=list)
    ignoredIssues: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
