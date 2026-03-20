from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import ValidationError

from pipeline.gateway.models import GatewayRunRequest
from pipeline.planner.extract_reference_layout import SYSTEM_PROMPT, build_user_prompt
from pipeline.planner.reference_layout_models import ReferenceLayoutPlan


GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/{model}:generateContent"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_AUTH_MODE = "auto"
DEFAULT_GEMINI_TIMEOUT_MS = 30000
DEFAULT_GEMINI_OAUTH_TOKEN_FILE = os.path.expanduser("~/.config/unity-resource-rag/gemini-oauth-token.json")
DEFAULT_GEMINI_OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/generative-language.retriever",
)
DEFAULT_ADC_HINT_PATHS = (
    "~/.config/gcloud/application_default_credentials.json",
    "~/Library/Application Support/gcloud/application_default_credentials.json",
)


class GatewayAdapterError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details or {}


@dataclass(frozen=True)
class GeminiConfig:
    auth_mode: str
    model: str
    timeout_ms: int
    api_key: str | None
    access_token: str | None
    project_id: str | None
    oauth_token_file: str | None
    oauth_scopes: tuple[str, ...]


def _normalize_model_name(model: str) -> str:
    stripped = model.strip()
    if not stripped:
        stripped = DEFAULT_GEMINI_MODEL
    if stripped.startswith("models/"):
        return stripped
    return f"models/{stripped}"


def _decode_data_url(data_url: str) -> tuple[str, str]:
    if not data_url.startswith("data:") or "," not in data_url:
        raise GatewayAdapterError(
            "invalid_request",
            "Gemini adapter expected imageDataUrl to be a valid data URL.",
            retryable=False,
        )

    header, encoded = data_url.split(",", 1)
    mime_type = "image/png"
    if ";" in header:
        mime_type = header[5:].split(";", 1)[0] or mime_type
    return mime_type, encoded


def _load_adc_credentials(scopes: tuple[str, ...]) -> tuple[str, str | None]:
    try:
        import google.auth
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise GatewayAdapterError(
            "auth_required",
            "google-auth is required for Gemini ADC authentication.",
            retryable=False,
            details={"missingDependency": "google-auth"},
        ) from exc

    credentials, project_id = google.auth.default(scopes=list(scopes))
    credentials.refresh(Request())
    token = getattr(credentials, "token", None)
    if not token:
        raise GatewayAdapterError(
            "auth_required",
            "ADC credentials were found but no access token could be refreshed.",
            retryable=False,
        )
    return token, project_id


def _adc_credentials_likely_available() -> bool:
    explicit_credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if explicit_credentials and os.path.exists(os.path.expanduser(explicit_credentials)):
        return True

    for path in DEFAULT_ADC_HINT_PATHS:
        if os.path.exists(os.path.expanduser(path)):
            return True

    return False


def _load_oauth_token_file_credentials(
    *,
    token_file: str | None,
    scopes: tuple[str, ...],
) -> str:
    if not token_file:
        raise GatewayAdapterError(
            "auth_required",
            "GEMINI_OAUTH_TOKEN_FILE is required when GEMINI_AUTH_MODE=oauth_token_file.",
            retryable=False,
        )

    expanded = os.path.expanduser(token_file)
    if not os.path.exists(expanded):
        raise GatewayAdapterError(
            "auth_required",
            f"Gemini OAuth token file was not found: {expanded}",
            retryable=False,
        )

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise GatewayAdapterError(
            "auth_required",
            "google-auth is required for Gemini OAuth token file authentication.",
            retryable=False,
            details={"missingDependency": "google-auth"},
        ) from exc

    try:
        credentials = Credentials.from_authorized_user_file(expanded, list(scopes))
    except Exception as exc:
        raise GatewayAdapterError(
            "auth_required",
            f"Failed to load Gemini OAuth token file: {exc}",
            retryable=False,
        ) from exc

    if not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception as exc:
                raise GatewayAdapterError(
                    "auth_expired",
                    f"Failed to refresh Gemini OAuth token: {exc}",
                    retryable=False,
                ) from exc
        else:
            raise GatewayAdapterError(
                "auth_expired",
                "Gemini OAuth token file is invalid and cannot be refreshed.",
                retryable=False,
            )

    if not credentials.token:
        raise GatewayAdapterError(
            "auth_required",
            "Gemini OAuth token file did not produce an access token.",
            retryable=False,
        )

    return credentials.token


def _parse_oauth_scopes(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value or not raw_value.strip():
        return DEFAULT_GEMINI_OAUTH_SCOPES
    scopes = tuple(item.strip() for item in raw_value.split(",") if item.strip())
    return scopes or DEFAULT_GEMINI_OAUTH_SCOPES


def _resolve_auth(config: GeminiConfig) -> tuple[str, dict[str, str]]:
    auth_mode = (config.auth_mode or DEFAULT_GEMINI_AUTH_MODE).strip().lower()

    if auth_mode not in {"auto", "api_key", "access_token", "adc", "oauth_token_file"}:
        raise GatewayAdapterError(
            "invalid_request",
            f"Unsupported Gemini auth mode: {config.auth_mode}",
            retryable=False,
        )

    if auth_mode in {"api_key", "auto"} and config.api_key:
        return "api_key", {"x-goog-api-key": config.api_key}

    if auth_mode == "access_token":
        if not config.access_token:
            raise GatewayAdapterError(
                "auth_required",
                "GEMINI_ACCESS_TOKEN is required when GEMINI_AUTH_MODE=access_token.",
                retryable=False,
            )
        headers = {"Authorization": f"Bearer {config.access_token}"}
        if config.project_id:
            headers["x-goog-user-project"] = config.project_id
        return "access_token", headers

    if auth_mode in {"oauth_token_file", "auto"} and config.oauth_token_file and os.path.exists(os.path.expanduser(config.oauth_token_file)):
        token = _load_oauth_token_file_credentials(
            token_file=config.oauth_token_file,
            scopes=config.oauth_scopes,
        )
        headers = {"Authorization": f"Bearer {token}"}
        if config.project_id:
            headers["x-goog-user-project"] = config.project_id
        return "oauth_token_file", headers

    if auth_mode == "adc":
        token, discovered_project_id = _load_adc_credentials(config.oauth_scopes)
        headers = {"Authorization": f"Bearer {token}"}
        effective_project_id = config.project_id or discovered_project_id
        if effective_project_id:
            headers["x-goog-user-project"] = effective_project_id
        return "adc", headers

    if auth_mode == "auto" and _adc_credentials_likely_available():
        token, discovered_project_id = _load_adc_credentials(config.oauth_scopes)
        headers = {"Authorization": f"Bearer {token}"}
        effective_project_id = config.project_id or discovered_project_id
        if effective_project_id:
            headers["x-goog-user-project"] = effective_project_id
        return "adc", headers

    raise GatewayAdapterError(
        "auth_required",
        "No Gemini credentials were available. Provide GEMINI_API_KEY, a Gemini OAuth token file, or configure ADC.",
        retryable=False,
    )


def _gemini_schema() -> dict[str, Any]:
    raw_schema = ReferenceLayoutPlan.model_json_schema()
    defs = raw_schema.get("$defs", {})

    def simplify(node: Any) -> Any:
        if isinstance(node, list):
            return [simplify(item) for item in node]

        if not isinstance(node, dict):
            return node

        if "$ref" in node:
            ref = node["$ref"]
            if ref.startswith("#/$defs/"):
                return simplify(defs[ref.split("/")[-1]])
            raise GatewayAdapterError(
                "internal_error",
                f"Unsupported schema ref: {ref}",
                retryable=False,
            )

        if "anyOf" in node:
            variants = [simplify(item) for item in node["anyOf"]]
            non_null = [
                item for item in variants
                if not (isinstance(item, dict) and item.get("type") == "null")
            ]
            if len(non_null) == 1:
                return non_null[0]
            return non_null[0] if non_null else {"type": "null"}

        cleaned: dict[str, Any] = {}
        for key, value in node.items():
            if key in {"$defs", "$ref", "title", "default", "examples"}:
                continue

            if key == "additionalProperties":
                if value is True:
                    continue
                elif value is False:
                    cleaned[key] = False
                else:
                    cleaned[key] = simplify(value)
                continue

            cleaned[key] = simplify(value)

        if cleaned.get("type") == "object":
            cleaned.setdefault("properties", {})

        return cleaned

    return simplify(raw_schema)


def _extract_candidate_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise GatewayAdapterError(
            "provider_unavailable",
            "Gemini returned no candidates.",
            retryable=True,
            details={"response": payload},
        )

    parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
    text_chunks = [part.get("text") for part in parts if isinstance(part, dict) and part.get("text")]
    if not text_chunks:
        raise GatewayAdapterError(
            "provider_unavailable",
            "Gemini returned no text parts for structured output.",
            retryable=True,
            details={"response": payload},
        )

    return "".join(text_chunks).strip()


def _load_generation_output(payload: dict[str, Any]) -> dict[str, Any]:
    raw_text = _extract_candidate_text(payload)
    trimmed = raw_text.strip()
    if trimmed.startswith("```"):
        trimmed = trimmed.strip("`")
        if trimmed.startswith("json"):
            trimmed = trimmed[4:].strip()

    try:
        return json.loads(trimmed)
    except json.JSONDecodeError as exc:
        raise GatewayAdapterError(
            "schema_validation_failed",
            f"Gemini returned invalid JSON: {exc}",
            retryable=True,
            details={"rawText": raw_text[:2000]},
        ) from exc


def _usage_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    usage = payload.get("usageMetadata")
    if not isinstance(usage, dict):
        return None
    return {
        "inputTokens": usage.get("promptTokenCount"),
        "outputTokens": usage.get("candidatesTokenCount"),
        "totalTokens": usage.get("totalTokenCount"),
        "thoughtsTokenCount": usage.get("thoughtsTokenCount"),
    }


def _build_request_body(request: GatewayRunRequest, config: GeminiConfig) -> dict[str, Any]:
    image_meta = request.input.image or {}
    prompt = build_user_prompt(
        screen_name=request.input.screenName,
        image_meta={
            "originalWidth": int((image_meta or {}).get("originalWidth") or 0),
            "originalHeight": int((image_meta or {}).get("originalHeight") or 0),
            "sentWidth": int((image_meta or {}).get("sentWidth") or 0),
            "sentHeight": int((image_meta or {}).get("sentHeight") or 0),
            "mimeType": (image_meta or {}).get("mimeType") or "image/png",
        },
        project_hints=request.input.projectHints,
    )
    mime_type, encoded_data = _decode_data_url(request.input.imageDataUrl)

    return {
        "systemInstruction": {
            "parts": [
                {"text": SYSTEM_PROMPT},
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": encoded_data,
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4000,
            "responseMimeType": "application/json",
            "responseJsonSchema": _gemini_schema(),
        },
    }


def run_gemini_layout_extraction(request: GatewayRunRequest) -> dict[str, Any]:
    if request.capability != "vision_layout_extraction":
        raise GatewayAdapterError(
            "unsupported_capability",
            f"Gemini adapter does not support capability: {request.capability}",
            retryable=False,
        )

    config = GeminiConfig(
        auth_mode=os.getenv("GEMINI_AUTH_MODE", DEFAULT_GEMINI_AUTH_MODE),
        model=_normalize_model_name(request.options.modelHint or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)),
        timeout_ms=int(request.options.timeoutMs or int(os.getenv("GEMINI_TIMEOUT_MS", str(DEFAULT_GEMINI_TIMEOUT_MS)))),
        api_key=os.getenv("GEMINI_API_KEY"),
        access_token=os.getenv("GEMINI_ACCESS_TOKEN"),
        project_id=os.getenv("GEMINI_PROJECT_ID"),
        oauth_token_file=os.getenv("GEMINI_OAUTH_TOKEN_FILE", DEFAULT_GEMINI_OAUTH_TOKEN_FILE),
        oauth_scopes=_parse_oauth_scopes(os.getenv("GEMINI_OAUTH_SCOPES")),
    )
    resolved_auth_mode, auth_headers = _resolve_auth(config)
    body = _build_request_body(request, config)
    request_url = GEMINI_API_ENDPOINT.format(model=config.model)
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **auth_headers,
    }
    encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    http_request = urllib_request.Request(
        request_url,
        data=encoded_body,
        headers=request_headers,
        method="POST",
    )

    try:
        with urllib_request.urlopen(http_request, timeout=max(config.timeout_ms / 1000.0, 1.0)) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw)
    except urllib_error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise GatewayAdapterError(
            "provider_unavailable" if exc.code >= 500 else "invalid_request",
            f"Gemini request failed with HTTP {exc.code}: {error_body or exc.reason}",
            retryable=exc.code >= 500 or exc.code == 429,
        ) from exc
    except urllib_error.URLError as exc:
        raise GatewayAdapterError(
            "provider_timeout",
            f"Gemini request failed: {exc.reason}",
            retryable=True,
        ) from exc

    output = _load_generation_output(payload)
    try:
        validated = ReferenceLayoutPlan.model_validate(output)
    except ValidationError as exc:
        raise GatewayAdapterError(
            "schema_validation_failed",
            "Gemini output did not validate against ReferenceLayoutPlan.",
            retryable=True,
            details={"errors": exc.errors(), "output": output},
        ) from exc

    return {
        "adapterId": "gemini_direct",
        "authMode": resolved_auth_mode,
        "providerFamily": "google",
        "output": validated.model_dump(mode="json", exclude_none=True),
        "usage": _usage_summary(payload),
        "trace": {
            "upstreamRequestId": payload.get("responseId"),
            "model": config.model,
        },
    }
