from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError

from .models import GatewayRunRequest


GatewayCapabilityHandler = Callable[[GatewayRunRequest], dict[str, Any]]


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

    def dispatch(self, request: GatewayRunRequest) -> dict[str, Any]:
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
        return route.handler(request)

    def handle_payload(self, payload: Any) -> dict[str, Any]:
        try:
            request = GatewayRunRequest.model_validate(payload)
        except ValidationError as exc:
            raise GatewayRouteError(
                "invalid_request",
                "Request body did not match GatewayRunRequest.",
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

    from .capabilities.vision_layout_extraction import register as register_vision_layout_extraction

    register_vision_layout_extraction(router)
    return router
