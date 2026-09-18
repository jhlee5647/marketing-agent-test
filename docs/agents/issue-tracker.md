# 이슈 트래커: GitHub

이 저장소의 이슈와 스펙은 GitHub 이슈로 관리합니다. 모든 작업에 `gh` CLI를 씁니다.

## 규칙

- **이슈 만들기**: `gh issue create --title "..." --body "..."`. 여러 줄 본문은 heredoc을 씁니다.
- **이슈 읽기**: `gh issue view <number> --comments`. 코멘트는 `jq`로 거르고 라벨도 함께 가져옵니다.
- **이슈 목록**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`에 필요한 `--label`, `--state` 필터를 붙입니다.
- **코멘트 달기**: `gh issue comment <number> --body "..."`
- **라벨 붙이기 / 떼기**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **닫기**: `gh issue close <number> --comment "..."`

저장소는 `git remote -v`로 알아냅니다. 클론 안에서 실행하면 `gh`가 자동으로 찾습니다.

## triage 대상으로서의 PR

**PRs as a request surface: no.** _(이 저장소가 외부 PR을 기능 요청으로 취급하면 `yes`로 바꿉니다. `/triage`가 이 플래그를 읽습니다.)_

`yes`이면 PR도 이슈와 같은 라벨과 상태를 거치며, `gh pr` 명령을 씁니다:

- **PR 읽기**: `gh pr view <number> --comments`, diff는 `gh pr diff <number>`.
- **triage할 외부 PR 목록**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`로 가져온 뒤 `authorAssociation`이 `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, `NONE`인 것만 남깁니다(`OWNER`/`MEMBER`/`COLLABORATOR`는 제외).
- **코멘트 / 라벨 / 닫기**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub는 이슈와 PR이 번호 공간을 공유하므로 `#42`만으로는 어느 쪽인지 알 수 없습니다. `gh pr view 42`로 확인하고, 없으면 `gh issue view 42`로 넘어갑니다.

## 스킬이 "이슈 트래커에 발행한다"고 할 때

GitHub 이슈를 만듭니다.

## 스킬이 "관련 티켓을 가져온다"고 할 때

`gh issue view <number> --comments`를 실행합니다.

## Wayfinding 작업

`/wayfinder`가 씁니다. **map**은 이슈 하나이고, 그 **child** 이슈들이 티켓입니다.

- **Map**: `wayfinder:map` 라벨이 붙은 이슈 하나로, 본문에 Notes / Decisions-so-far / Fog를 담습니다. `gh issue create --label wayfinder:map`.
- **Child 티켓**: map에 GitHub sub-issue로 연결된 이슈입니다(sub-issues 엔드포인트에 `gh api`). sub-issue를 쓸 수 없으면 map 본문의 task list에 child를 추가하고 child 본문 맨 위에 `Part of #<map>`을 적습니다. 라벨: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). 티켓을 맡으면 담당 개발자에게 배정합니다.
- **Blocking**: GitHub의 **네이티브 이슈 의존성**을 씁니다. UI에 보이는 표준 방식입니다. `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`로 간선을 추가합니다. `<blocker-db-id>`는 blocker의 숫자 **database id**입니다(`gh api repos/<owner>/<repo>/issues/<n> --jq .id`. `#number`나 `node_id`가 _아님_). GitHub는 `issue_dependencies_summary.blocked_by`(열린 blocker만, 실시간 게이트)를 보고합니다. 의존성 기능을 쓸 수 없으면 child 본문 맨 위에 `Blocked by: #<n>, #<n>` 줄을 둡니다. blocker가 모두 닫히면 티켓의 차단이 풀립니다.
- **Frontier 조회**: map의 열린 child를 나열하고(`gh issue list --state open`, map의 sub-issue / task list 범위), 열린 blocker가 있거나(`issue_dependencies_summary.blocked_by > 0`, 또는 `Blocked by` 줄에 열린 이슈) 담당자가 있는 것은 뺍니다. map 순서상 첫 번째가 우선입니다.
- **Claim**: `gh issue edit <n> --add-assignee @me`. 세션의 첫 쓰기 작업입니다.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, 이어서 `gh issue close <n>`, 그다음 map의 Decisions-so-far에 컨텍스트 포인터(요지 + 링크)를 덧붙입니다.
