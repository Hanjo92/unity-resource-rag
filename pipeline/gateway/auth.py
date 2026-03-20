from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayAuthConfig:
    bearer_token: str | None


def validate_bearer_token(
    *,
    config: GatewayAuthConfig,
    authorization_header: str | None,
) -> tuple[bool, str | None]:
    expected = config.bearer_token
    if not expected:
        return True, None

    if not authorization_header:
        return False, "Missing Authorization header."

    prefix = "Bearer "
    if not authorization_header.startswith(prefix):
        return False, "Authorization header must use Bearer authentication."

    presented = authorization_header[len(prefix):].strip()
    if presented != expected:
        return False, "Invalid bearer token."

    return True, None
