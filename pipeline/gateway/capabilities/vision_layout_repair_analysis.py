from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipeline.verification.analyze_screenshot_mismatch import analyze
from pipeline.verification.build_repair_patch_candidates import build_repair_patch_candidates

from ..models import GatewayRequestEnvelope
from ..router import GatewayCapabilityRouter


CAPABILITY_NAME = "vision_layout_repair_analysis"
ADAPTER_ID = "verification_pipeline"
PROVIDER_FAMILY = "local_verification"


class _SupportsRepairAnalysisInput(Protocol):
    referenceImage: str
    capturedImage: str
    resolvedBlueprint: str | None
    outputSchema: str


class VisionLayoutRepairAnalysisOptions(BaseModel):
    model_config = ConfigDict(extra="allow")

    detail: str | None = None
    timeoutMs: int | None = Field(default=None, ge=1)
    repairIterations: int | None = Field(default=1, ge=1)


class VisionLayoutRepairAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    referenceImage: str
    capturedImage: str
    resolvedBlueprint: str | None = None
    screenName: str | None = None


class VisionLayoutRepairAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    capability: str = CAPABILITY_NAME
    providerPreference: list[str] = Field(default_factory=list)
    input: VisionLayoutRepairAnalysisInput
    outputSchema: str
    options: VisionLayoutRepairAnalysisOptions = Field(default_factory=VisionLayoutRepairAnalysisOptions)


def _load_json(path: Path) -> dict[str, Any]:
    import json

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}.")
    return payload


def _normalized_request(
    request: VisionLayoutRepairAnalysisRequest | _SupportsRepairAnalysisInput | dict[str, Any],
) -> VisionLayoutRepairAnalysisRequest:
    if isinstance(request, VisionLayoutRepairAnalysisRequest):
        return request
    if isinstance(request, dict):
        return VisionLayoutRepairAnalysisRequest.model_validate(request)
    return VisionLayoutRepairAnalysisRequest.model_validate(
        {
            "capability": getattr(request, "capability", CAPABILITY_NAME),
            "providerPreference": list(getattr(request, "providerPreference", [])),
            "input": {
                "referenceImage": getattr(request.input, "referenceImage"),
                "capturedImage": getattr(request.input, "capturedImage"),
                "resolvedBlueprint": getattr(request.input, "resolvedBlueprint", None),
                "screenName": getattr(request.input, "screenName", None),
            },
            "outputSchema": getattr(request, "outputSchema"),
            "options": getattr(request, "options", {}),
        }
    )


def run_vision_layout_repair_analysis(
    request: VisionLayoutRepairAnalysisRequest | _SupportsRepairAnalysisInput | dict[str, Any],
) -> dict[str, Any]:
    normalized_request = _normalized_request(request)
    input_data = normalized_request.input

    blueprint = None
    if input_data.resolvedBlueprint:
        blueprint = _load_json(Path(input_data.resolvedBlueprint).expanduser().resolve())

    report = analyze(
        reference_path=Path(input_data.referenceImage).expanduser().resolve(),
        captured_path=Path(input_data.capturedImage).expanduser().resolve(),
        blueprint=blueprint,
    )
    candidate_set = build_repair_patch_candidates(
        report,
        source_path=f"{input_data.referenceImage}::{input_data.capturedImage}",
    )

    result: dict[str, Any] = {
        "adapterId": ADAPTER_ID,
        "authMode": "analysis_only",
        "providerFamily": PROVIDER_FAMILY,
        "output": {
            "screenName": input_data.screenName or report.get("screenName"),
            "verificationReport": report,
            "repairPatchCandidates": candidate_set.model_dump(mode="json", exclude_none=True),
        },
        "usage": {
            "inputArtifacts": 2 + (1 if input_data.resolvedBlueprint else 0),
            "analysisMode": "local_verification",
        },
        "trace": {
            "capability": CAPABILITY_NAME,
            "sourceReferenceImage": str(Path(input_data.referenceImage).expanduser().resolve()),
            "sourceCapturedImage": str(Path(input_data.capturedImage).expanduser().resolve()),
        },
    }
    return result


def handle(request: GatewayRequestEnvelope) -> dict[str, Any]:
    return run_vision_layout_repair_analysis(
        {
            "capability": request.capability,
            "providerPreference": request.providerPreference,
            "input": request.input,
            "outputSchema": request.outputSchema,
            "options": request.options.model_dump(mode="python"),
        }
    )


def register(router: GatewayCapabilityRouter) -> None:
    router.register(
        CAPABILITY_NAME,
        handle,
        adapter_id=ADAPTER_ID,
    )


def validate_vision_layout_repair_analysis_request(
    payload: dict[str, Any],
) -> VisionLayoutRepairAnalysisRequest:
    try:
        return VisionLayoutRepairAnalysisRequest.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Request body did not match {CAPABILITY_NAME} input schema.") from exc
