from __future__ import annotations

from typing import Any

from ..adapters.gemini_direct import run_gemini_layout_extraction
from ..models import GatewayRunRequest
from ..router import GatewayCapabilityRouter


CAPABILITY_NAME = "vision_layout_extraction"
ADAPTER_ID = "gemini_direct"


def handle(request: GatewayRunRequest) -> dict[str, Any]:
    return run_gemini_layout_extraction(request)


def register(router: GatewayCapabilityRouter) -> None:
    router.register(
        CAPABILITY_NAME,
        handle,
        adapter_id=ADAPTER_ID,
    )
