# 평가 결과: skin-care-n5000-ecd44b5-86f170

비교할 기준선이 없습니다. 이 결과가 기준선이 됩니다.

| 조건 | 값 |
|---|---|
| 규모 | skin-care-n5000 (상품 5000 · 리뷰 178256) |
| 모델 | gpt-5.4-mini |
| 심판 | gpt-5.4 |
| 프롬프트 해시 | ac32c759 |
| 커밋 | ecd44b5 |

## 통과

전체 52/54 회차 · 유형별 집계 9/9 · 주제 9/9 · 혼합 7/9 · 후속 9/9 · 거절 9/9 · 범위 밖 9/9

### 케이스별

- `agg-total-reviews` (집계) 3/3
- `agg-top3-review-count` (집계) 3/3
- `agg-rating-distribution` (집계) 3/3
- `topic-stickiness` (주제) 3/3
- `topic-irritation` (주제) 3/3
- `topic-scent` (주제) 3/3
- `mix-low-rating-complaints` (혼합) 1/3 — 1~2점 리뷰 수치(251건)와 반복 불만 2가지 이상, review_id+영문 인용은 있으나 검색 결과의 빈도를 전체 리뷰 빈도인 것처럼 단정하지 말아야 하는데 '가장 많이 나오는 불만'으로 단정했다. · 1~2점 반복 불만 2가지는 제시했고 review_id와 영어 인용도 있지만, 1~2점 리뷰 총 건수를 수치로 밝히지 않았다.
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

- 질문당 중앙값 5.1s · 최대 36.5s
- 모듈별 llm 241.6s · run_sql 2.3s · search_reviews 215.7s · embed_query 14.3s
- 토큰 입력 443727 · 출력 23063 · 질문당 중앙값 6542
- 심판 토큰 입력 16625 · 출력 1331
- 심판이 사람 라벨과 일치 19/21

## 적재

15.2분 (임베딩 8.8분) · SQLite 71MB · 벡터 7254MB

답변 전문은 `evals/details/skin-care-n5000-ecd44b5-86f170.json`에 있다.
