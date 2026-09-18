# 브랜치 전략

GitHub Flow 변형입니다. 계획 문서는 `main`에 직접 한 번에 커밋하고, 구현은 티켓마다 단기 브랜치를 두어 PR로 올린 뒤 **merge commit**으로 머지합니다.

## 계획 단계: 커밋 금지

`/to-spec`, `/to-tickets`, `/grilling`, `/domain-modeling`으로 만든 계획 문서(`CONTEXT.md`, `docs/adr/`, `docs/agents/`, 스펙 등)는 계획이 끝날 때까지 **커밋하지 않고** 작업 트리에만 둡니다.

## `/implement` 직전: 계획 문서를 `main`에 한 번에

계획 문서를 **`main`에 커밋 하나로** 묶어 직접 커밋하고 push합니다(`docs: ...`). PR은 거치지 않습니다. 저장소의 첫 커밋도 이 커밋입니다.

## 구현: 브랜치 → 커밋 → PR

1. `main`에서 브랜치를 땁니다. 티켓이 있으면 `<type>/<NN>-<slug>`, 없으면 `<type>/<slug>`로 이름을 짓습니다. `type`은 커밋 프리픽스 어휘를 그대로 씁니다(`feat`, `fix`, `docs`, `refactor`, `chore`).
2. `/implement`로 구현 슬라이스 커밋을 쌓습니다.
3. push하고 PR을 엽니다(`gh pr create`).

**에이전트는 PR을 여는 데까지만 합니다.** PR 머지는 사용자가 직접 합니다. 에이전트는 `gh pr merge`를 실행하지 않습니다.

## 규칙

- 브랜치 하나 = 티켓 하나. 티켓 두 개를 한 브랜치에 담지 않습니다.
- 브랜치는 `main`에서 따고 `main`으로만 돌아옵니다.
- 구현의 `main` 반영은 PR과 **merge commit**으로만 합니다. squash와 rebase 머지는 쓰지 않습니다. 머지와 머지 후 브랜치 삭제는 사용자가 합니다.
- 브랜치가 뒤처지면 `git merge origin/main`으로 따라잡습니다. **이미 push한 커밋은 rebase·amend·force-push하지 않습니다.**
- 핫픽스도 같은 경로로 처리합니다(`fix/<slug>` → PR → merge commit).
- 릴리스가 필요해지면 `main`에 태그만 붙입니다. 릴리스 브랜치는 두지 않습니다.
