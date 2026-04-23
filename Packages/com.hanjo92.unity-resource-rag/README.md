# Unity Resource RAG

`com.hanjo92.unity-resource-rag`는 Unity 프로젝트 리소스를 카탈로그화하고, 실제 sprite/prefab/font 자산을 사용해 UI 블루프린트를 적용하기 위한 Editor 전용 UPM 패키지다.

포함 기능:

- `index_project_resources`
- `query_ui_asset_catalog`
- `ui_asset_catalog` resource
- `apply_ui_blueprint`
- `Window > Unity Resource RAG` editor window

패키지 구조:

- `Editor/ResourceIndexing/`
- `Documentation~/`
- `Samples~/Blueprints/`

이 패키지는 Unity 안쪽 실행 레이어만 담는다.
벡터화/검색용 sidecar 스크립트는 저장소 루트의 `pipeline/` 아래에 유지한다.

빠른 시작:

1. 이 패키지를 Unity 프로젝트의 `Packages/` 아래에 두거나 git path로 설치한다.
2. 개발자는 local checkout의 `file:` 경로를, non-dev 사용자는 portable sidecar bundle 경로를 sidecar runtime root로 연결한다. `Window > Unity Resource RAG`의 one-click build는 루트 `pipeline/` sidecar에 접근해야 한다.
3. `unity-mcp`가 설치된 프로젝트에서 `Window > Unity Resource RAG`를 열고 `Quick Setup`을 누른다.
4. Quick Setup 안의 sign-in method는 기본적으로 `Use my Codex sign-in (Recommended)`로 두는 것을 권장한다. API key 자체를 Unity에 붙여넣는 대신, 이미 로그인된 Codex 세션이나 기존 environment variable을 재사용하는 흐름이다.
5. Readiness Dashboard에서 막힌 항목을 확인한다. Python이 막혀 있으면 `Bootstrap Python Runtime`으로 sidecar-local `.venv`를 준비한다.
6. 같은 창에서 reference 이미지를 넣거나, `Draft Template`을 `Popup / HUD / List` 중 하나로 고른 뒤 goal/title/body를 채우고 `Start UI Build`를 누른다.
7. build 후에는 같은 창에서 `Capture Result`, `Run Repair Handoff`, `Last Run Artifacts`, `Export Case Report`까지 이어서 진행할 수 있다.
8. 필요하면 `index_project_resources`, `query_ui_asset_catalog`, `apply_ui_blueprint`를 custom tool로 직접 호출해 세부 동작을 따로 확인한다.
9. `ui_asset_catalog`는 callable tool이 아니라 MCP resource라는 점을 기억한다.

Windows 메모:

- Python 3.11+가 필요하다. `python3`가 없더라도 `Bootstrap Python Runtime`은 `py -3.12`, `py -3.11`, `py -3`, `python` 같은 일반적인 Python 명령을 자동 감지하도록 설계되어 있다.
- `Advanced Paths & Overrides`의 `Python Command`에는 `py -3.12`처럼 명령+인자 형태를 그대로 넣을 수 있다.

`Quick Setup`이 하는 일:

- Unity MCP를 HTTP Local transport로 맞춤
- `Project Scoped Tools`를 꺼서 custom tool이 직접 노출되게 함
- `index_project_resources`, `query_ui_asset_catalog`, `apply_ui_blueprint`, `ui_asset_catalog`를 활성화 시도
- Local HTTP Server / bridge 재시작 시도
- `~/.codex/config.toml`에 `unityResourceRag` sidecar entry 동기화

`Readiness Dashboard`가 하는 일:

- `sidecar / python / AI access / Unity Editor connection / build input` 상태를 `Ready / Attention / Blocked`로 요약
- raw MCP jargon 대신 다음 액션 중심 문장으로 현재 막힌 지점을 설명
- `Refresh Readiness`로 현재 상태를 다시 확인
- `Bootstrap Python Runtime`으로 sidecar-local `.venv` 생성과 requirements 설치 시도

`Sign-in Method`가 의미하는 것:

- `Use my Codex sign-in (Recommended)`: 현재 Codex 로그인 상태를 재사용한다. 기본 auth file 위치가 아니면 `Advanced Paths & Overrides`에서 custom auth file만 지정하면 된다.
- `Use an API key from my environment`: API key 문자열이 아니라 environment variable 이름만 Unity에 저장한다.
- `Stay offline with local fallback`: hosted model 없이 catalog-first draft와 Unity apply 흐름만 검증한다.

`Start UI Build`가 하는 일:

- reference image가 있으면 `reference-first` path
- 없으면 선택한 `Draft Template`에 맞는 `catalog-first draft` path
- 내부적으로 루트 `pipeline/mcp/local_runner.py`를 호출해서 readiness 확인과 `unity_rag.start_ui_build`를 순차 실행
- doctor diagnostics와 Unity apply까지 한 번에 시도
- 최근 build/capture/repair/case export 결과를 `Last Run Artifacts`에서 바로 다시 열 수 있게 유지
- 성공 후에는 같은 창에서 `Capture Result`, `Run Repair Handoff`, `Export Case Report`로 이어질 수 있게 결과를 유지

샘플:

- `Samples~/Blueprints/sample-popup-blueprint.json`
- `Samples~/Blueprints/sample-popup-blueprint-template.json`

구현 메모는 `Documentation~/resource-indexing-mvp.md`를 참고하면 된다.

MCP sidecar contract는 [mcp-sidecar-contract.md](https://github.com/Hanjo92/unity-resource-rag/blob/main/specs/mcp-sidecar-contract.md)와 [examples/mcp/end-to-end-usage.md](https://github.com/Hanjo92/unity-resource-rag/blob/main/examples/mcp/end-to-end-usage.md)를 보면 된다.

portable sidecar bundle 전략과 build script는 [packaged-sidecar-distribution-strategy.md](https://github.com/Hanjo92/unity-resource-rag/blob/main/docs/decisions/packaged-sidecar-distribution-strategy.md)에서 확인할 수 있다.

full checkout에서 bundle을 직접 만들 때는 저장소 루트에서 아래 명령을 사용한다.

```bash
python3 scripts/build_sidecar_bundle.py --output-dir dist
```
