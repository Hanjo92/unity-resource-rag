from __future__ import annotations

from typing import Any

from ..adapters.gemini_direct import run_gemini_layout_extraction
from ..models import GatewayRequestEnvelope, GatewayRunRequest
from ..router import GatewayCapabilityRouter


CAPABILITY_NAME = "vision_layout_extraction"
ADAPTER_ID = "gemini_direct"


def _normalize_request(request: GatewayRequestEnvelope) -> GatewayRunRequest:
    return GatewayRunRequest.model_validate(
        {
            "capability": request.capability,
            "providerPreference": request.providerPreference,
            "input": request.input,
            "outputSchema": request.outputSchema,
            "options": request.options.model_dump(mode="python"),
        }
    )


def handle(request: GatewayRequestEnvelope) -> dict[str, Any]:
    return run_gemini_layout_extraction(_normalize_request(request))


def register(router: GatewayCapabilityRouter) -> None:
    router.register(
        CAPABILITY_NAME,
        handle,
        adapter_id=ADAPTER_ID,
    )
