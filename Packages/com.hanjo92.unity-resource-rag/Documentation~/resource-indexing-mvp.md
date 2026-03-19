# Resource Indexing MVP

이 문서는 `com.hanjo92.unity-resource-rag` 패키지 안의 첫 MVP 범위를 설명한다.

포함 내용:

- `index_project_resources` custom tool
- `ui_asset_catalog` custom resource
- `apply_ui_blueprint` custom tool
- JSONL catalog writer
- preview PNG exporter
- TMP/layout/custom component capable blueprint runtime

기본 출력 위치:

- `Library/ResourceRag/resource_catalog.jsonl`
- `Library/ResourceRag/resource_catalog_manifest.json`
- `Library/ResourceRag/previews/`

의도:

1. Unity 프로젝트 안의 UI 관련 리소스를 정규화한다.
2. 외부 sidecar/vector pipeline이 읽을 수 있는 포맷으로 export한다.
3. 이후 `apply_ui_blueprint`로 실제 sprite/prefab 기반 UI 조립까지 연결한다.
4. TMP text, layout group, safe-area-like custom components까지 블루프린트로 명시한다.

예상 호출 예시:

```json
{
  "outputPath": "Library/ResourceRag/resource_catalog.jsonl",
  "includePreviews": true,
  "assetTypes": ["Sprite", "Prefab", "TMP_FontAsset", "Material"]
}
```

블루프린트 예시는 패키지 sample을 참고하면 된다.

- `Samples~/Blueprints/sample-popup-blueprint.json`
