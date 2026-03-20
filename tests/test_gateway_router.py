from __future__ import annotations

import unittest
from unittest.mock import patch

from pipeline.gateway.models import GatewayRequestEnvelope
from pipeline.gateway.router import GatewayCapabilityRouter, GatewayRouteError, create_default_gateway_router


def _request_payload(capability: str = "vision_layout_extraction") -> dict[str, object]:
    return {
        "capability": capability,
        "providerPreference": ["gateway:auto"],
        "input": {
            "screenName": "RewardPopup",
            "imageDataUrl": "data:image/png;base64,AAAA",
            "projectHints": ["mobile reward popup"],
        },
        "outputSchema": "reference_layout_plan_v1",
        "options": {
            "detail": "high",
            "timeoutMs": 30000,
            "modelHint": "gemini-2.5-flash",
        },
    }


class GatewayRouterTests(unittest.TestCase):
    def test_unknown_capability_raises_unsupported_capability(self) -> None:
        router = GatewayCapabilityRouter()
        router.register(
            "vision_layout_extraction",
            lambda request: {"capability": request.capability},
            adapter_id="gemini_direct",
        )

        with self.assertRaises(GatewayRouteError) as ctx:
            router.dispatch(GatewayRequestEnvelope.model_validate(_request_payload("unknown_capability")))

        self.assertEqual(ctx.exception.code, "unsupported_capability")
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual(ctx.exception.details["capability"], "unknown_capability")

    def test_invalid_request_raises_invalid_request(self) -> None:
        router = GatewayCapabilityRouter()

        with self.assertRaises(GatewayRouteError) as ctx:
            router.handle_payload({"capability": "vision_layout_extraction"})

        self.assertEqual(ctx.exception.code, "invalid_request")
        self.assertFalse(ctx.exception.retryable)
        self.assertIn("errors", ctx.exception.details)

    def test_default_router_routes_vision_layout_extraction(self) -> None:
        with patch(
            "pipeline.gateway.capabilities.vision_layout_extraction.run_gemini_layout_extraction",
            return_value={
                "adapterId": "gemini_direct",
                "authMode": "api_key",
                "providerFamily": "google",
                "output": {"screenName": "RewardPopup"},
            },
        ) as run_layout_extraction:
            router = create_default_gateway_router()
            result = router.handle_payload(_request_payload())

        self.assertEqual(result["adapterId"], "gemini_direct")
        self.assertEqual(result["providerFamily"], "google")
        run_layout_extraction.assert_called_once()
        self.assertEqual(
            router.supported_capabilities,
            (
                "vision_layout_extraction",
                "vision_layout_repair_analysis",
                "text_embedding",
            ),
        )
        self.assertEqual(
            router.supported_adapters,
            (
                "gemini_direct",
                "verification_pipeline",
                "local_text_embedding",
            ),
        )
