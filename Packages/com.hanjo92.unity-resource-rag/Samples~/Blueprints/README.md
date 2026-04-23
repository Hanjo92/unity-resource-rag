# Blueprints sample

이 폴더의 샘플은 Unity 프로젝트에 맞춰 블루프린트를 바인딩하고 검색 흐름에 연결하는 방법을 보여준다.

## 포함 파일

- `sample-popup-blueprint.json`
- `sample-popup-blueprint-template.json`

## 파일별 의도

- `sample-popup-blueprint.json`은 프로젝트 전용 예시다. `Assets/UI/...` 아래의 프로젝트 자산과 `MyGame.UI.SafeAreaFitter` 같은 custom UI component binding을 직접 참조한다.
- `sample-popup-blueprint-template.json`은 템플릿이다. 자신의 프로젝트에서 자산 경로, 바인딩 이름, 검색 조건을 맞추어 수정하면서 retrieval/binding adaptation의 출발점으로 쓰는 용도다.

## 사용 방식

1. 먼저 템플릿을 복사한다.
2. 프로젝트의 실제 자산과 컴포넌트 이름에 맞게 값들을 바꾼다.
3. 직접 참조 예시가 필요하면 `sample-popup-blueprint.json`을 비교용으로 확인한다.

이 샘플들은 그대로 재사용하기보다, 각 Unity 프로젝트의 구조에 맞게 조정하는 것을 전제로 한다.
