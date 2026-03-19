from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReferenceResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(..., gt=0)
    y: int = Field(..., gt=0)


class NormalizedBounds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    w: float = Field(..., gt=0.0, le=1.0)
    h: float = Field(..., gt=0.0, le=1.0)


class ComponentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    typeName: str
    properties: dict[str, Any] = Field(default_factory=dict)


class SafeAreaRootSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "SafeAreaRoot"
    components: list[ComponentSpec] = Field(default_factory=list)


class PaddingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: int = 0
    right: int = 0
    top: int = 0
    bottom: int = 0


class ImageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["Simple", "Sliced", "Tiled", "Filled"] = "Simple"
    preserveAspect: bool | None = None
    raycastTarget: bool | None = None
    color: str | None = None


class TextSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    fontQueryText: str | None = None
    fontPreferredKind: str | None = None
    fontBindingPolicy: str | None = None
    fontMinScore: float | None = Field(default=None, ge=0.0, le=1.0)
    fontSize: float | None = None
    enableAutoSizing: bool | None = None
    raycastTarget: bool | None = None
    alignment: str | None = None
    color: str | None = None


class LayoutGroupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["Horizontal", "Vertical", "Grid"]
    padding: PaddingSpec | None = None
    childAlignment: str | None = None
    spacing: float | None = None
    childControlWidth: bool | None = None
    childControlHeight: bool | None = None
    childForceExpandWidth: bool | None = None
    childForceExpandHeight: bool | None = None
    childScaleWidth: bool | None = None
    childScaleHeight: bool | None = None
    cellSize: dict[str, float] | None = None
    constraint: str | None = None
    constraintCount: int | None = None
    startCorner: str | None = None
    startAxis: str | None = None


class LayoutElementSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minWidth: float | None = None
    minHeight: float | None = None
    preferredWidth: float | None = None
    preferredHeight: float | None = None
    flexibleWidth: float | None = None
    flexibleHeight: float | None = None
    ignoreLayout: bool | None = None


class ReferenceLayoutRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    kind: Literal["container", "image", "prefab_instance", "tmp_text"]
    parentId: str | None = None
    regionType: str | None = None
    queryText: str | None = None
    preferredKind: str | None = None
    bindingPolicy: Literal["require_confident", "best_match"] | None = None
    minScore: float | None = Field(default=None, ge=0.0, le=1.0)
    topK: int | None = Field(default=None, ge=1, le=20)
    normalizedBounds: NormalizedBounds | None = None
    stretchToParent: bool | None = None
    repeatCount: int | None = Field(default=None, ge=1)
    interactionLevel: Literal["static", "read_only", "interactive"] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    image: ImageSpec | None = None
    text: TextSpec | None = None
    layoutGroup: LayoutGroupSpec | None = None
    layoutElement: LayoutElementSpec | None = None
    components: list[ComponentSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_region(self) -> "ReferenceLayoutRegion":
        if not self.stretchToParent and self.normalizedBounds is None:
            raise ValueError("Region requires normalizedBounds unless stretchToParent is true.")

        if self.kind in {"image", "prefab_instance"} and not self.queryText:
            raise ValueError("image and prefab_instance regions require queryText.")

        if self.kind == "tmp_text" and self.text is None:
            raise ValueError("tmp_text regions require a text block.")

        return self


class ReferenceLayoutPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screenName: str
    referenceResolution: ReferenceResolution
    safeAreaRoot: SafeAreaRootSpec = Field(default_factory=SafeAreaRootSpec)
    regions: list[ReferenceLayoutRegion] = Field(default_factory=list)
