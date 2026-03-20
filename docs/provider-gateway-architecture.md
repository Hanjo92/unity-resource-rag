# Provider Gateway Architecture

## Goal

이 문서는 provider API key를 sidecar나 MCP client에 직접 퍼뜨리지 않으면서도, 여러 provider를 유연하게 붙일 수 있는 구조를 정의한다.

핵심 방향:

`sidecar -> OAuth-protected gateway -> provider adapters -> upstream providers`

## Problem

현재 저장소의 provider 경계는 비교적 단순하다.

- `local_heuristic`
- `openai`
- `openai_compatible`

이 구조는 빠르게 시작하기엔 좋지만, 아래 문제가 있다.

- provider key를 직접 sidecar 환경에 넣기 쉽다.
- provider가 늘어날수록 sidecar 코드가 복잡해진다.
- OAuth, cloud IAM, API key가 섞이면 인증 모델이 지저분해진다.
- provider failover와 routing 정책이 분산된다.

## Recommended Architecture

### Layer 1. Sidecar

역할:

- reference extraction workflow 시작
- capability와 output schema 표현
- artifact와 workflow report 생성

sidecar는 가급적 provider 세부사항을 모른다.

### Layer 2. Gateway

역할:

- MCP client 또는 sidecar의 인증 경계
- provider adapter 선택
- provider fallback and routing
- usage/tracing/quotas 통합

여기가 인증과 라우팅의 중심이다.

### Layer 3. Provider Adapters

역할:

- OpenAI direct
- Gemini direct
- Vertex AI
- Claude on Vertex
- Claude on Bedrock

같은 capability를 provider별로 구현한다.

### Layer 4. Upstream Providers

실제 모델 제공자.

## Current Implementation Status

현재 저장소에는 minimal gateway가 이미 들어가 있다.

- module: `pipeline.gateway`
- endpoint: `POST /v1/capabilities/run`
- implemented adapter: `gemini_direct`
- implemented capability: `vision_layout_extraction`

즉, 현재 상태는 "문서만 있는 상태"가 아니라, 첫 adapter vertical slice가 들어간 상태다.

## Why OAuth Belongs On The Gateway

OAuth를 sidecar에 직접 붙이면 다음 문제가 생긴다.

- MCP tool 호출 환경마다 token lifecycle을 구현해야 한다.
- artifact에 token 관련 정보가 새기기 쉽다.
- provider별 redirect/callback 관리가 sidecar 쪽으로 번진다.

반대로 gateway에 OAuth를 두면:

- 사용자나 클라이언트는 gateway 한 곳만 인증하면 된다.
- provider별 credential 차이를 gateway 내부에서 흡수할 수 있다.
- sidecar는 provider-neutral contract를 유지할 수 있다.

## Provider Strategy

### Strategy A. Keep direct providers for dev velocity

초기 개발 생산성을 위해 아래 경로는 유지 가능하다.

- `local_heuristic`
- `openai`
- `openai_compatible`

이 경로는 구현이 단순하고 빠르다.

### Strategy B. Introduce `gateway` as the team-safe default

팀 공유 환경, 사내 배포, 장기 운영에서는 `gateway`를 기본값으로 권장한다.

### Strategy C. Move breadth behind the gateway

새 provider를 repo 밖으로 숨기고 gateway adapter로 추가한다.

예:

- `gemini_direct`
- `vertex_ai_vision`
- `claude_vertex_reasoning`
- `bedrock_claude_reasoning`

repo 표면에서는 단순히 `gateway` 하나만 추가된다.

## Recommended Provider Surface For This Repo

repo 외부에 보이는 provider 이름은 이 정도로 제한하는 것이 좋다.

- `auto`
- `local_heuristic`
- `openai`
- `openai_compatible`
- `gateway`

그리고 `auto`는 장기적으로 이렇게 진화하면 된다.

- local key가 있으면 direct provider
- gateway URL이 있으면 gateway
- 둘 다 없으면 `local_heuristic`

## Auth Model By Layer

### MCP Client -> Gateway

- OAuth 2.0 권장
- 또는 trusted local dev라면 no-auth / dev token 허용

### Gateway -> Provider

- OpenAI: API key
- Gemini direct: OAuth or API key
- Vertex AI: ADC / service account
- Claude direct: API key
- Claude on Vertex: ADC / service account
- Claude on Bedrock: AWS IAM

## Deployment Shapes

### Option 1. Localhost Gateway

개발용.

- sidecar는 `http://127.0.0.1:...`
- gateway는 로컬 keychain이나 env에서 credential 사용

장점:

- 간단하다

단점:

- 팀 공유에는 약하다

### Option 2. Team Gateway

협업용.

- gateway는 내부 서버로 운영
- users or apps는 OAuth로 인증
- provider credential은 중앙 관리

장점:

- 운영과 감사를 한곳에 모을 수 있다

단점:

- 인프라가 필요하다

## Migration Plan

### Phase 1. Contract First

- `provider-auth-matrix`
- `provider-gateway-contract`
- sidecar 코드에는 아직 `gateway` 구현을 넣지 않더라도 문서와 경계를 먼저 고정

### Phase 2. Minimal `gateway` provider in sidecar

- provider enum에 `gateway` 추가
- `extract_reference_layout.py`가 normalized gateway request를 호출하도록 연결
- 초기 endpoint는 `POST /v1/capabilities/run` 기준으로 가정

### Phase 3. First adapter pair

- `openai_responses`
- `gemini_direct` or `vertex_ai_vision`

### Phase 4. Auth-aware fallback

- gateway가 사용자 인증 상태와 provider availability에 따라 fallback

## Design Rules

### Rule 1. Sidecar artifacts stay provider-neutral

artifact에는 `resolvedProvider`, `adapterId`, `requestId` 정도만 남기고 secret은 남기지 않는다.

### Rule 2. Gateway owns auth complexity

OAuth refresh, token exchange, cloud credential loading은 gateway 책임이다.

### Rule 3. Capabilities over vendors

repo 설계는 vendor 이름보다 capability를 중심으로 진화한다.

### Rule 4. Local fallback remains mandatory

네트워크나 인증이 없어도 개발 가능한 최소 경로로 `local_heuristic`는 유지한다.

## Immediate Recommendation

지금 바로 구현을 시작한다면 순서는 이렇다.

1. `gateway` provider를 문서와 계약에 먼저 추가
2. `vision_layout_extraction` capability만 다루는 minimal gateway adapter 설계
3. sidecar에는 `gateway` provider 하나만 추가
4. Gemini 또는 Vertex AI 계열을 첫 OAuth/IAM-backed adapter로 붙이기
5. 그 다음 OpenAI direct는 gateway 내부 adapter로 흡수할지 판단
