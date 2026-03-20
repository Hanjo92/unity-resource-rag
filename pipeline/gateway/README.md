# Gateway Server

`pipeline.gateway`는 `unity-resource-rag` sidecar가 사용할 로컬/팀용 provider gateway다.

현재 구현 범위:

- endpoint: `POST /v1/capabilities/run`
- capability: `vision_layout_extraction`
- adapter: `gemini_direct`

## Run

```bash
python3 -m pipeline.gateway
```

기본 바인딩:

- host: `127.0.0.1`
- port: `8080`

환경변수:

- `UNITY_RESOURCE_RAG_GATEWAY_HOST`
- `UNITY_RESOURCE_RAG_GATEWAY_PORT`
- `UNITY_RESOURCE_RAG_GATEWAY_TOKEN`

`UNITY_RESOURCE_RAG_GATEWAY_TOKEN`이 설정되면 `Authorization: Bearer ...`가 필요하다.

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
  --gateway-url http://127.0.0.1:8080
```

또는:

```bash
export UNITY_RESOURCE_RAG_GATEWAY_URL=http://127.0.0.1:8080
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider auto
```

## Notes

- 현재 adapter는 `ReferenceLayoutPlan` structured output을 Gemini에 직접 요청한다.
- 초기 구현이라 `vision_layout_extraction`만 지원한다.
- 향후 `text_embedding`, `image_embedding`, `vision_layout_repair_analysis` capability를 추가할 수 있다.
- `auto` 모드에서는 `GEMINI_API_KEY` -> `GEMINI_OAUTH_TOKEN_FILE` -> 로컬에서 감지된 ADC 순서로 인증 경로를 시도한다.
- ADC 관련 파일이나 `GOOGLE_APPLICATION_CREDENTIALS`가 보이지 않으면 `auto`는 metadata 탐색을 하지 않고 바로 `auth_required`를 반환한다.
