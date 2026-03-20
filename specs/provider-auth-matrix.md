# Provider Auth Matrix

## Goal

이 문서는 `unity-resource-rag`가 다루게 될 provider 인증 방식을 정리한다.

핵심 구분은 세 가지다.

1. provider direct API key
2. provider-native OAuth or cloud IAM
3. OAuth-protected gateway

중요한 원칙:

- 외부 provider를 호출하는 순간, 어디선가는 자격 증명이 필요하다.
- 에이전트 프로그램이 키를 "없애는" 것은 불가능하다.
- 대신 자격 증명 위치를 `agent -> gateway -> provider` 구조로 옮겨 노출 범위를 줄일 수 있다.

## Terms

### Direct API Key

sidecar가 provider REST API를 직접 호출하고, 환경변수나 secret store에서 provider API key를 읽는 방식.

### Provider-Native OAuth

provider가 공식적으로 OAuth 2.0 user flow 또는 service-to-service credential flow를 제공하는 방식.

### Cloud IAM

provider direct key 대신 cloud IAM, ADC, service account, instance role 같은 상위 플랫폼 인증을 사용하는 방식.

### OAuth-Protected Gateway

sidecar는 자체 gateway만 호출하고, gateway가 내부 adapter를 통해 provider를 호출한다. 사용자나 MCP client는 gateway OAuth만 다룬다.

## Matrix

| Provider Path | Upstream Auth | OAuth 가능 여부 | Sidecar direct 권장 | Gateway 권장 | Notes |
| --- | --- | --- | --- | --- | --- |
| `local_heuristic` | none | 해당 없음 | 예 | 선택 | 로컬 fallback |
| `openai` direct | API key | direct OAuth 아님 | 예 | 예 | direct API는 API key 기반 |
| `openai_compatible` | provider-specific | 구현체마다 다름 | 예 | 예 | 스펙 불일치 가능성 주의 |
| `gemini` direct | API key or OAuth | 예 | 조건부 | 예 | user OAuth 또는 service auth 가능 |
| `vertex_ai` | ADC / service account / OAuth | 예 | 조건부 | 예 | cloud-native auth에 적합 |
| `anthropic` direct | API key | direct OAuth 아님 | 예 | 예 | direct API는 key 기반 |
| `claude_on_vertex` | ADC / service account / OAuth | 예 | 조건부 | 예 | Anthropic direct와 분리해서 봐야 함 |
| `claude_on_bedrock` | AWS IAM | user OAuth 아님 | 조건부 | 예 | IAM role / credentials 사용 |
| `gateway` | gateway OAuth | 예 | 아니오 | 기준 경로 | 추천 기본 경로 |

## What This Means For This Repo

현재 저장소 기준:

- 이미 있는 것:
  - `local_heuristic`
  - `openai`
  - `openai_compatible`
- 아직 없는 것:
  - `gateway`
  - `gemini`
  - `vertex_ai`
  - `claude_on_vertex`
  - `claude_on_bedrock`

## Recommended Default

개발 단계 기본값:

- `local_heuristic`
- 필요 시 `openai`

실서비스 또는 팀 공유 환경 기본값:

- `gateway`

이유:

- provider key를 sidecar/MCP client에 직접 뿌리지 않아도 된다.
- provider 교체나 다중 provider 라우팅이 쉬워진다.
- OAuth는 gateway 경계에서 통합하는 편이 운영이 단순하다.

## Decision Rules

### Rule 1. OpenAI direct와 Anthropic direct는 key 기반으로 본다

이 경로는 OAuth로 대체할 수 있다고 가정하지 않는다.

### Rule 2. Gemini/Vertex/Bedrock는 cloud-native auth 경로로 분리한다

이 경로는 `direct API key provider`와 같은 취급을 하지 않는다.

### Rule 3. MCP client에는 되도록 provider credential을 두지 않는다

OAuth를 쓸 거면 client-to-gateway 경계에서 쓰고, upstream credential은 gateway가 들고 있는 구조를 우선한다.

### Rule 4. `gateway`는 capability-based routing point다

sidecar는 "어느 회사 API인지"보다 "어떤 capability가 필요한지"를 우선 표현한다.

예:

- `vision_layout_extraction`
- `text_embedding`
- `image_embedding`
- `repair_reasoning`

## Security Notes

- provider API key는 MCP tool argument로 넘기지 않는다.
- OAuth access token도 blueprint, handoff bundle, report artifact에 기록하지 않는다.
- gateway는 provider raw error를 그대로 노출하지 않고 normalized error로 변환한다.
- sidecar artifact에는 `requestedProvider`, `resolvedProvider`, `adapterId` 정도만 남기고 secret material은 남기지 않는다.
