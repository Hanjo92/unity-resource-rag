# Provider Gateway Contract

## Goal

이 문서는 `unity-resource-rag` sidecar가 미래에 `gateway` provider를 사용할 때 필요한 최소 계약을 정의한다.

목표는:

- sidecar는 단일 provider contract만 알게 한다.
- gateway는 내부에서 여러 provider adapter를 선택할 수 있게 한다.
- 인증은 sidecar와 upstream provider에서 분리한다.

## Boundary

기준 호출 경계:

`sidecar -> gateway -> provider adapter -> upstream provider`

여기서 sidecar는 provider company-specific request를 직접 만들지 않는다.

## Core Concepts

### Capability

sidecar가 원하는 기능 단위.

예:

- `vision_layout_extraction`
- `text_embedding`
- `image_embedding`
- `repair_reasoning`

### Adapter

특정 upstream provider를 감싸는 구현.

예:

- `openai_responses`
- `gemini_direct`
- `vertex_ai_vision`
- `claude_vertex_reasoning`

### Auth Mode

gateway가 adapter에 접근할 때 사용하는 upstream 인증 방식.

예:

- `api_key`
- `oauth_user_token`
- `service_account`
- `adc`
- `aws_iam`

## Sidecar To Gateway Request

예시:

```json
{
  "capability": "vision_layout_extraction",
  "providerPreference": [
    "gateway:auto",
    "gateway:gemini_direct",
    "gateway:openai_responses"
  ],
  "input": {
    "screenName": "RewardPopup",
    "imageDataUrl": "data:image/png;base64,...",
    "projectHints": [
      "mobile reward popup",
      "safe area required"
    ]
  },
  "outputSchema": "reference_layout_plan_v1",
  "options": {
    "detail": "high",
    "timeoutMs": 30000
  }
}
```

## Sidecar To Gateway Response

예시:

```json
{
  "status": "ok",
  "capability": "vision_layout_extraction",
  "adapterId": "gemini_direct",
  "authMode": "oauth_user_token",
  "providerFamily": "google",
  "output": {
    "screenName": "RewardPopup",
    "regions": []
  },
  "usage": {
    "inputTokens": 1200,
    "outputTokens": 380
  },
  "trace": {
    "requestId": "gw_req_123",
    "upstreamRequestId": "provider_req_456"
  }
}
```

## Error Contract

예시:

```json
{
  "status": "error",
  "code": "auth_required",
  "message": "Gateway authentication is required.",
  "retryable": false,
  "details": {
    "capability": "vision_layout_extraction",
    "providerFamily": "google"
  }
}
```

정규화할 오류 코드:

- `auth_required`
- `auth_expired`
- `provider_unavailable`
- `provider_timeout`
- `quota_exceeded`
- `unsupported_capability`
- `invalid_request`
- `schema_validation_failed`
- `internal_error`

## Adapter Interface

모든 adapter는 아래 의미 계약을 만족해야 한다.

### Input

- normalized capability name
- normalized input payload
- normalized output schema target
- timeout and quality hints

### Output

- normalized structured result
- normalized usage summary
- normalized trace ids
- no secret material

### Adapter Responsibilities

- upstream provider request shape 생성
- upstream auth 처리
- upstream response를 normalized output으로 변환
- upstream error를 normalized error로 변환

### Sidecar Responsibilities

- capability 선택
- schema target 제공
- fallback order 결정
- artifact에 provider-neutral metadata만 기록

## Gateway Routing Rules

### Rule 1. Capability first

라우팅은 provider 이름보다 capability 우선으로 본다.

### Rule 2. Auth-aware fallback

예:

- user OAuth 세션이 있으면 `gemini_direct`
- 없으면 `openai_responses`
- 그것도 없으면 `local_heuristic`

### Rule 3. Structured-output preference

`reference_layout_plan_v1` 같이 schema adherence가 중요한 경우, structured output 안정성이 높은 adapter를 우선한다.

### Rule 4. Secret locality

sidecar는 upstream secret을 몰라도 동작해야 한다.

## Initial Capability Set

`v0.2.x` 기준 추천 capability:

- `vision_layout_extraction`
- `vision_layout_repair_analysis`
- `text_embedding`
- `image_embedding`

## Integration Note For This Repo

현재 `extract_reference_layout.py`는 provider string 기반 분기다.

미래 방향은 아래와 같다.

- 현재:
  - `openai`
  - `openai_compatible`
  - `local_heuristic`
- 다음 단계:
  - `gateway`
- 그 다음:
  - gateway 내부 adapter family 도입

즉, repo 안의 provider surface는 좁게 유지하고, 복잡성은 gateway 내부로 밀어넣는 것이 기준이다.
