# 평가 비교: skin-care-face-creams-moisturizers-n20-515b956-5f30d7 (현재) vs skin-care-face-creams-moisturizers-n20-f4b26e4-cf50e7 (기준선)

**판정: 이상 없음**

| 조건 | 기준선 | 현재 |
|---|---|---|
| 규모 | skin-care-face-creams-moisturizers-n20 (상품 20 · 리뷰 4744) | skin-care-face-creams-moisturizers-n20 (상품 20 · 리뷰 4744) |
| 모델 | gpt-5.4-mini | gpt-5.4-mini |
| 심판 | gpt-5.4 | gpt-5.4 |
| 프롬프트 해시 | ac32c759 | ac32c759 |
| 커밋 | f4b26e4 | 515b956 |

## 회귀한 케이스

없음

## 새로 통과하게 된 케이스

없음

## 한쪽에만 있는 케이스 (견주지 않았다)

없음

## 통과율 (판정에는 쓰지 않는다)

전체 54/54 → 49/54

## 소요 시간과 토큰 (판정에는 쓰지 않는다)

| 값 | 기준선 | 현재 |
|---|---|---|
| 질문당 중앙값 | 3.5s | 3.0s |
| 질문당 최대 | 9.5s | 7.7s |
| 모듈별 | llm 207.1s · run_sql 0.1s · search_reviews 14.7s · embed_query 12.2s | llm 169.3s · run_sql 0.1s · search_reviews 10.2s · embed_query 10.1s |
| 로컬 유사도 계산 | 2.5s / 62회 = 40ms/실행 | 0.1s / 51회 = 3ms/실행 |
| 토큰 입력 | 380648 | 353461 |
| 토큰 출력 | 20903 | 19665 |
| 심판 토큰 | 18559 | 18218 |
| 벡터 저장소 로드 | 3.2s | 0.2s |
| 적재 | 2.9분 (임베딩 0.2분) · SQLite 2MB · 벡터 193MB | 2.8분 (임베딩 0.2분) · SQLite 2MB · 벡터 29MB |

실패한 회차의 답변 전문은 `evals/details/skin-care-face-creams-moisturizers-n20-515b956-5f30d7.json`에 있다.
