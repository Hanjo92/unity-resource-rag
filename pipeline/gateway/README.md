# Gateway Server

`pipeline.gateway`는 `unity-resource-rag` sidecar가 사용할 로컬/팀용 provider gateway다.

현재 구현 범위:

- endpoint: `POST /v1/capabilities/run`
- capability: `vision_layout_extraction`
- capability: `vision_layout_repair_analysis`
- capability: `text_embedding`
- capability: `image_embedding` preview
- adapters: `gemini_direct`, `verification_pipeline`, `local_text_embedding`, `local_image_embedding_preview`

## Run

```bash
python3 -m pipeline.gateway
```

기본 바인딩:

- host: `127.0.0.1`
- port: `8090`

환경변수:

- `UNITY_RESOURCE_RAG_GATEWAY_HOST`
- `UNITY_RESOURCE_RAG_GATEWAY_PORT`
- `UNITY_RESOURCE_RAG_GATEWAY_TOKEN`

`UNITY_RESOURCE_RAG_GATEWAY_TOKEN`이 설정되면 `Authorization: Bearer ...`가 필요하다.

기본 포트는 Unity MCP HTTP Local이 자주 쓰는 `127.0.0.1:8080`과 겹치지 않도록 `8090`을 사용한다. 이미 다른 포트를 쓰고 있다면 `UNITY_RESOURCE_RAG_GATEWAY_PORT`로 override하면 된다.

간단한 시작 예시는 아래와 같다.

```bash
export UNITY_RESOURCE_RAG_GATEWAY_TOKEN=your-token
python3 -m pipeline.gateway
```

## Gemini Adapter Auth Modes

### 1. API key

```bash
export GEMINI_API_KEY=...
```

기본 `auto` 모드에서는 `GEMINI_API_KEY`가 있으면 이 경로를 사용한다.

### 2. ADC / OAuth-backed local auth

공식 quickstart 흐름에 맞춰 로컬에서 ADC를 준비한다.

```bash
gcloud auth application-default login
```

필요하면:

```bash
export GEMINI_AUTH_MODE=adc
export GEMINI_PROJECT_ID=<your-google-cloud-project-id>
```

### 3. OAuth token file

브라우저 로그인으로 reusable token file을 만들고 gateway가 그 파일을 읽어 refresh하게 할 수 있다.

```bash
python3 pipeline/gateway/bootstrap_gemini_oauth.py \
  --client-secret /absolute/path/to/client_secret.json \
  --project-id <your-google-cloud-project-id>
```

그다음:

```bash
export GEMINI_AUTH_MODE=oauth_token_file
export GEMINI_OAUTH_TOKEN_FILE=~/.config/unity-resource-rag/gemini-oauth-token.json
export GEMINI_PROJECT_ID=<your-google-cloud-project-id>
```

### 4. Pre-issued access token

```bash
export GEMINI_AUTH_MODE=access_token
export GEMINI_ACCESS_TOKEN=...
export GEMINI_PROJECT_ID=<your-google-cloud-project-id>
```

## Planner Usage

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider gateway \
  --gateway-url http://127.0.0.1:8090
```

또는:

```bash
export UNITY_RESOURCE_RAG_GATEWAY_URL=http://127.0.0.1:8090
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider auto
```

## Notes

- `vision_layout_extraction`은 `ReferenceLayoutPlan` structured output을 Gemini에 직접 요청한다.
- `vision_layout_repair_analysis`는 기존 verification 분석과 repair patch candidate 생성을 gateway capability로 감싼다.
- `text_embedding`은 현재 retrieval integration seam용 로컬 `token-frequency-v1` 출력을 제공한다.
- `image_embedding`은 preview-only local capability이며, ASCII `P2/P3` portable image data URL 또는 caller-supplied `visualTokens`를 `visual-token-sparse-v1`로 변환한다.
- production provider-backed image embedding rollout은 `0.3.x`로 defer 되어 있다.
- `auto` 모드에서는 `GEMINI_API_KEY` -> `GEMINI_OAUTH_TOKEN_FILE` -> 로컬에서 감지된 ADC 순서로 인증 경로를 시도한다.
- ADC 관련 파일이나 `GOOGLE_APPLICATION_CREDENTIALS`가 보이지 않으면 `auto`는 metadata 탐색을 하지 않고 바로 `auth_required`를 반환한다.

## Troubleshooting

- `401 auth_required`가 나오면 gateway 프로세스와 호출 쪽이 같은 토큰을 보고 있는지 확인한다.
- 호출 쪽은 `Authorization: Bearer <token>`을 보내야 하고, CLI에서는 `--gateway-auth-token-env`로 토큰 env 이름을 맞춰야 한다.
- 시작 로그의 `supportedCapabilities` 목록에 없는 capability 이름은 거절된다.
- 더 긴 체크리스트는 [docs/troubleshooting/v0.3.0-gateway-benchmark-troubleshooting.md](../../docs/troubleshooting/v0.3.0-gateway-benchmark-troubleshooting.md)를 본다.
