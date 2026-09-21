# 평가 결과: skin-care-all-515b956-2a3517

비교할 기준선이 없습니다. 이 결과가 기준선이 됩니다.

| 조건 | 값 |
|---|---|
| 규모 | skin-care-all (상품 40215 · 리뷰 269114) |
| 모델 | gpt-5.4-mini |
| 심판 | gpt-5.4 |
| 프롬프트 해시 | ac32c759 |
| 커밋 | 515b956 |

## 통과

전체 49/54 회차 · 유형별 집계 9/9 · 주제 5/9 · 혼합 8/9 · 후속 9/9 · 거절 9/9 · 범위 밖 9/9

### 케이스별

- `agg-total-reviews` (집계) 3/3
- `agg-top3-review-count` (집계) 3/3
- `agg-rating-distribution` (집계) 3/3
- `topic-stickiness` (주제) 3/3
- `topic-irritation` (주제) 1/3 — review_id와 영어 인용으로 3건 이상 제시는 충족했지만, 반복 표현 2가지 이상을 명시적으로 요약하지 않았고 진정·완화 사례까지 섞어 질문 범위를 흐렸다. · 피부 트러블·자극을 겪었다는 리뷰 3건 이상 제시가 없고, 제시된 예시는 대부분 ‘자극 없다’는 내용이라 질문 취지와 루브릭 1을 충족하지 못했다.
- `topic-scent` (주제) 1/3 — 기대한 호출이 없거나 순서가 어긋났다: {'tool': 'search_reviews'} · 향 언급 리뷰는 review_id와 영어 인용이 2건만 제시됐고, 반복 표현도 2가지 이상으로 요약되지 않았다.
- `mix-low-rating-complaints` (혼합) 2/3 — 반복 불만 두 가지 이상, review_id와 영어 인용, 1~2점 리뷰 수치(251건)는 있으나 검색 결과 빈도를 전체 리뷰 빈도처럼 단정하지 말아야 하는데 '가장 많이 나오는 불만'과 구체 건수로 단정했다.
- `mix-verified-praise` (혼합) 3/3
- `mix-low-rating-count` (혼합) 3/3
- `followup-five-star-praise` (후속) 3/3
- `followup-second-product-rating` (후속) 3/3
- `followup-narrow-to-low-ratings` (후속) 3/3
- `refuse-korea-sales` (거절) 3/3
- `refuse-reviewer-age` (거절) 3/3
- `refuse-offline-sales` (거절) 3/3
- `scope-hair-shampoo` (범위 밖) 3/3
- `scope-2022-reviews` (범위 밖) 3/3
- `scope-non-beauty-product` (범위 밖) 3/3

## 소요 시간과 토큰

- 질문당 중앙값 3.5s · 최대 11.2s
- 모듈별 llm 181.3s · run_sql 5.7s · search_reviews 17.0s · embed_query 9.7s
- 토큰 입력 418922 · 출력 22409 · 질문당 중앙값 6755
- 심판 토큰 입력 16532 · 출력 1383
- 심판이 사람 라벨과 일치 17/21

## 적재

16.3분 (임베딩 13.5분) · SQLite 152MB · 벡터 1668MB

답변 전문은 `evals/details/skin-care-all-515b956-2a3517.json`에 있다.
