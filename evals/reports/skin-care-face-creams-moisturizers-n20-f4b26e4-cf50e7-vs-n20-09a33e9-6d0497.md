# 평가 비교: skin-care-face-creams-moisturizers-n20-f4b26e4-cf50e7 (현재) vs n20-09a33e9-6d0497 (기준선)

**판정: 이상 없음**

| 조건 | 기준선 | 현재 |
|---|---|---|
| 규모 | skin-care-face-creams-moisturizers-n20 (상품 20 · 리뷰 4744) | skin-care-face-creams-moisturizers-n20 (상품 20 · 리뷰 4744) |
| 모델 | gpt-5.4-mini | gpt-5.4-mini |
| 심판 | gpt-5.4 | gpt-5.4 |
| 프롬프트 해시 | da36ae89 | ac32c759 |
| 커밋 | 09a33e9 | f4b26e4 |

## 회귀한 케이스

없음

## 새로 통과하게 된 케이스

- `topic-stickiness` (주제) 2/3 → 3/3
- `topic-scent` (주제) 2/3 → 3/3
- `followup-five-star-praise` (후속) 1/3 → 3/3

## 한쪽에만 있는 케이스 (견주지 않았다)

- `scope-hair-shampoo` 새 케이스라 기준선에 견줄 값이 없다
- `scope-non-beauty-product` 새 케이스라 기준선에 견줄 값이 없다
- `scope-body-lotion` 기준선에만 있고 지금은 없다
- `scope-unloaded-product` 기준선에만 있고 지금은 없다

## 통과율 (판정에는 쓰지 않는다)

전체 50/54 → 54/54

## 소요 시간과 토큰 (판정에는 쓰지 않는다)

| 값 | 기준선 | 현재 |
|---|---|---|
| 질문당 중앙값 | 3.4s | 3.5s |
| 질문당 최대 | 8.9s | 9.5s |
| 모듈별 | llm 176.5s · run_sql 0.1s · search_reviews 16.4s · embed_query 13.2s | llm 207.1s · run_sql 0.1s · search_reviews 14.7s · embed_query 12.2s |
| 로컬 유사도 계산 | 3.1s / 70회 = 45ms/실행 | 2.5s / 62회 = 40ms/실행 |
| 토큰 입력 | 397091 | 380648 |
| 토큰 출력 | 21039 | 20903 |
| 심판 토큰 | 18258 | 18559 |
| 벡터 저장소 로드 | 2.1s | 3.2s |
| 적재 | 3.0분 (임베딩 0.3분) · SQLite 2MB · 벡터 193MB | 2.9분 (임베딩 0.2분) · SQLite 2MB · 벡터 193MB |

실패한 회차의 답변 전문은 `evals/details/skin-care-face-creams-moisturizers-n20-f4b26e4-cf50e7.json`에 있다.
