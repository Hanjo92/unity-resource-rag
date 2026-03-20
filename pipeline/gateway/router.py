from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError

from .models import GatewayRequestEnvelope


GatewayCapabilityHandler = Callable[[GatewayRequestEnvelope], dict[str, Any]]


class GatewayRouteError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


@dataclass(frozen=True)
class GatewayRoute:
    capability: str
    adapter_id: str
    handler: GatewayCapabilityHandler


class GatewayCapabilityRouter:
    def __init__(self) -> None:
        self._routes: dict[str, GatewayRoute] = {}

    def register(
        self,
        capability: str,
        handler: GatewayCapabilityHandler,
        *,
        adapter_id: str,
    ) -> None:
        self._routes[capability] = GatewayRoute(
            capability=capability,
            adapter_id=adapter_id,
            handler=handler,
        )

    def dispatch(self, request: GatewayRequestEnvelope) -> dict[str, Any]:
        route = self._routes.get(request.capability)
        if route is None:
            raise GatewayRouteError(
                "unsupported_capability",
                f"No gateway capability is registered for {request.capability}.",
                retryable=False,
                details={
                    "capability": request.capability,
                    "supportedCapabilities": list(self.supported_capabilities),
                },
            )
        try:
            return route.handler(request)
        except ValidationError as exc:
            raise GatewayRouteError(
                "invalid_request",
                f"Request body did not match the expected {request.capability} input schema.",
                retryable=False,
                details={"capability": request.capability, "errors": exc.errors()},
            ) from exc
        except ValueError as exc:
            raise GatewayRouteError(
                "invalid_request",
                str(exc),
                retryable=False,
                details={"capability": request.capability},
            ) from exc

    def handle_payload(self, payload: Any) -> dict[str, Any]:
        try:
            request = GatewayRequestEnvelope.model_validate(payload)
        except ValidationError as exc:
            raise GatewayRouteError(
                "invalid_request",
                "Request body did not match GatewayRequestEnvelope.",
                retryable=False,
                details={"errors": exc.errors()},
            ) from exc
        return self.dispatch(request)

    @property
    def supported_capabilities(self) -> tuple[str, ...]:
        return tuple(self._routes.keys())

    @property
    def supported_adapters(self) -> tuple[str, ...]:
        seen: set[str] = set()
        adapters: list[str] = []
        for route in self._routes.values():
            if route.adapter_id in seen:
                continue
            seen.add(route.adapter_id)
            adapters.append(route.adapter_id)
        return tuple(adapters)


def create_default_gateway_router() -> GatewayCapabilityRouter:
    router = GatewayCapabilityRouter()

    from .capabilities.image_embedding import register as register_image_embedding
    from .capabilities.vision_layout_extraction import register as register_vision_layout_extraction
    from .capabilities.vision_layout_repair_analysis import register as register_vision_layout_repair_analysis
    from .capabilities.text_embedding import register as register_text_embedding

    register_vision_layout_extraction(router)
    register_vision_layout_repair_analysis(router)
    register_text_embedding(router)
    register_image_embedding(router)
    return router
