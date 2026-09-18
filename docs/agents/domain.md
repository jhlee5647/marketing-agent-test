# 도메인 문서

엔지니어링 스킬이 코드베이스를 탐색할 때 이 저장소의 도메인 문서를 어떻게 읽는지 정합니다.

## 탐색 전에 읽을 것

- 루트의 **`CONTEXT.md`**, 또는
- 루트에 **`CONTEXT-MAP.md`**가 있으면 그것: 컨텍스트마다 하나씩 있는 `CONTEXT.md`를 가리킵니다. 주제와 관련된 것을 모두 읽습니다.
- **`docs/adr/`**: 작업할 영역에 걸친 ADR을 읽습니다. 멀티 컨텍스트 저장소라면 `src/<context>/docs/adr/`의 컨텍스트별 결정도 확인합니다.

이 파일들이 없으면 **조용히 진행합니다.** 없다고 지적하지 않고, 미리 만들자고 제안하지도 않습니다. `/domain-modeling` 스킬(`/grill-with-docs`, `/improve-codebase-architecture`에서 호출됨)이 용어나 결정이 실제로 정해질 때 필요한 만큼 만듭니다.

## 파일 구조

이 저장소는 single-context입니다:

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

멀티 컨텍스트 저장소(루트에 `CONTEXT-MAP.md`가 있음):

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← 시스템 전체 결정
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← 컨텍스트별 결정
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## 용어집의 어휘를 쓴다

산출물(이슈 제목, 리팩터링 제안, 가설, 테스트 이름)에서 도메인 개념을 부를 때는 `CONTEXT.md`에 정의된 용어를 씁니다. 용어집이 피하라고 한 동의어로 흘러가지 않습니다.

필요한 개념이 용어집에 아직 없다면 신호입니다. 프로젝트가 쓰지 않는 말을 지어내고 있거나(다시 생각한다), 실제로 빈 곳이 있는 것입니다(`/domain-modeling`용으로 기록해 둔다).

## ADR과 충돌하면 드러낸다

산출물이 기존 ADR과 어긋나면 조용히 덮어쓰지 말고 명시적으로 밝힙니다:

> _ADR-0007(이벤트 소싱 주문)과 충돌하지만, 다음 이유로 다시 열어 볼 만합니다…_
