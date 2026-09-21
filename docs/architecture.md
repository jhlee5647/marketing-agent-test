# 아키텍처 개요: 리뷰 질의 에이전트 MVP

MVP가 완성되었을 때의 모습을 미리 보여 주는 문서다. 결정의 원본은 스펙 #1이고, 이 문서는 그 결정들이 맞물려 돌아가는 방식을 그림과 예시로 보여 준다. 용어는 `CONTEXT.md`를 따른다.

## 한눈에 보기

시스템은 **적재**(가끔 한 번 실행)와 **질의**(마케터가 매번 쓰는 것) 두 흐름으로 나뉜다. 두 흐름은 **적재 데이터**(SQLite + 리뷰 벡터 저장소)를 통해서만 만난다.

```mermaid
flowchart LR
    subgraph 외부
        UCSD[(UCSD<br/>메타·리뷰 .jsonl.gz)]
        EMB[OpenAI<br/>text-embedding-3-small]
        LLM[OpenAI<br/>mini급 채팅 모델]
    end

    subgraph 적재["적재 (한 번 실행)"]
        STREAM[스트리밍 리더]
        LOADER[적재 기능<br/>필터 · 상위 N개 선정 · 변환]
    end

    subgraph 적재데이터["적재 데이터 (git 제외)"]
        SQL[(SQLite<br/>products · reviews)]
        VEC[(벡터 저장소<br/>리뷰 임베딩 float32 행렬 파일)]
    end

    subgraph 질의["질의 (매 세션)"]
        CLI[에이전트 CLI<br/>REPL]
        AGENT[에이전트<br/>create_agent + InMemorySaver]
        T1[run_sql]
        T2[search_reviews]
    end

    UCSD --> STREAM --> LOADER
    LOADER --> SQL
    LOADER -- 리뷰 텍스트 --> EMB -- 벡터 --> VEC

    마케터((마케터)) <--> CLI <--> AGENT
    AGENT <--> LLM
    AGENT --> T1 --> SQL
    AGENT --> T2 --> VEC
    T2 -- 검색어 --> EMB
```

## 구성요소

### 적재 흐름

| 구성요소 | 하는 일 | 만드는 티켓 |
|---|---|---|
| **스트리밍 리더** | UCSD의 메타·리뷰 `.gz`를 HTTP로 받으며 압축을 풀어 한 줄씩 넘긴다. 디스크에 원본을 저장하지 않는다. 적재 기능과 분리된 얇은 진입점이다. | #2 |
| **적재 기능** | 줄 스트림을 받아 적재 데이터를 만든다. (1) 메타에서 얼굴 보습 제품을 고른다. (2) 리뷰 중 그 상품의 2023년 리뷰만 남긴다. (3) 2023년 리뷰 수 상위 N개 상품을 고른다. (4) SQLite에 쓴다. (5) 리뷰를 임베딩해 벡터 저장소 파일에 쓴다. 실행할 때마다 처음부터 다시 만든다. | #2 (SQLite), #4 (벡터 저장소) |

적재 기능은 URL이 아니라 **줄 스트림**, **`Embeddings` 객체**, **저장 위치**를 인자로 받는다. 그래서 테스트에서는 픽스처 줄, 가짜 임베딩, 임시 디렉터리를 넣어 네트워크 없이 돌릴 수 있다.

### 적재 데이터

| 저장소 | 담는 것 | 누가 읽나 |
|---|---|---|
| **SQLite `products`** | 상품 한 행: `parent_asin`, 상품명, 평균 별점, 평점 수, 가격, 스토어, 카테고리, 특징, 상세 | `run_sql` |
| **SQLite `reviews`** | 리뷰 한 행: `review_id`, `parent_asin`, `asin`, 별점, 제목, 본문, `reviewed_at`, 도움돼요 수, 구매 인증 | `run_sql` |
| **리뷰 벡터 저장소** (`data/vectors.npz`) | 리뷰 임베딩을 L2 정규화한 float32 행렬 하나(`vectors`)와, 행마다 `review_id`(`ids`)·필터용 `parent_asin`·`rating`·`verified_purchase`. 검색과 필터에 필요한 것만 담고, 리뷰 제목·본문은 SQLite `reviews`에서 읽는다(ADR-0004). | `search_reviews` |

같은 리뷰가 SQLite와 벡터 저장소에 **같은 `review_id`** 로 들어 있다. 그래서 검색으로 찾은 리뷰를 SQL로 다시 조회하거나, 반대로 SQL로 찾은 리뷰를 인용할 수 있다.

### 질의 흐름

| 구성요소 | 하는 일 | 만드는 티켓 |
|---|---|---|
| **에이전트 CLI** | `.env`를 읽고, 에이전트를 만들고, 마케터의 입력을 받아 답변을 출력하는 REPL. 세션마다 `thread_id`를 하나 쓴다. | #3 |
| **에이전트** | LangChain `create_agent`로 만든 ReAct 에이전트. LLM이 도구를 부를지, 어떤 인자로 부를지, 언제 답할지를 판단한다. `InMemorySaver`가 세션 안의 대화를 기억한다. | #3 |
| **시스템 프롬프트** | 스키마 설명, 적재 범위, 한국어 답변, 근거 표시, 거절 규칙, 상품명으로 `parent_asin` 찾기, 브랜드는 `title`로 판단, 검색어는 영어로 넘기기 | #3, #4 |
| **`run_sql`** | 읽기 전용 SELECT를 실행하고 최대 50행을 돌려준다. 오류는 메시지로 돌려준다. | #2 |
| **`search_reviews`** | 검색어를 임베딩해 벡터 저장소에서 의미 검색을 하고, `parent_asin`·별점 범위·구매 인증 필터를 건다. 기본 10건을 돌려준다. | #4 |

## 동작 방식: end-to-end 예시

> 아래 상품명, 수치, 리뷰 ID, 인용문은 **모두 설명을 위해 지어낸 값**이다. 실제 값은 적재 후에 정해진다. 명령 이름도 구현 시 정해진다.

### 1. 적재 (개발자, 한 번)

```text
$ uv run <적재 명령>
메타 스트리밍 중... 얼굴 보습 제품 18,402개 발견
리뷰 스트리밍 중... 대상 리뷰 1,204,331건
리뷰 수 상위 20개 상품 선정
SQLite 적재 완료
임베딩·벡터 저장소 적재 중... (OpenAI text-embedding-3-small)
완료: 상품 20개, 리뷰 187,540건
```

내부에서 일어나는 일:
1. 스트리밍 리더가 메타 파일(gz 약 711MB)을 한 줄씩 넘긴다. 적재 기능은 `categories`가 `Skin Care > Face > Creams & Moisturizers` 아래인 상품만 모은다.
2. 스트리밍 리더가 리뷰 파일(gz 약 2.96GB)을 한 줄씩 넘긴다. 적재 기능은 1에서 모은 상품의 2023년 리뷰만 남기고 상품별로 센다.
3. 2023년 리뷰가 가장 많은 20개 상품을 고른다. 메타가 없는 리뷰는 버린다.
4. SQLite에 `products` 20행과 `reviews` 전부를 쓴다. 이때 `review_id`를 부여하고 `timestamp`를 `reviewed_at`으로 바꾼다.
5. 같은 리뷰를 임베딩해 벡터 저장소 파일에 쓴다.

### 2. 질의 (마케터, 매 세션)

**질문 1: 조회와 검색을 섞는 질문 (MVP 완료 기준 3번)**

```text
$ uv run <CLI 명령>
> 하이드라 크림의 1~2점 리뷰에서 가장 많이 나오는 불만은?
```

에이전트 내부의 ReAct 루프:

```mermaid
sequenceDiagram
    actor M as 마케터
    participant A as 에이전트(LLM)
    participant S as run_sql
    participant R as search_reviews

    M->>A: 하이드라 크림의 1~2점 리뷰에서 가장 많이 나오는 불만은?
    A->>S: SELECT parent_asin, title FROM products WHERE title LIKE '%Hydra%Cream%'
    S-->>A: B0XXXX1 | "Hydra Boost Water Cream 1.7oz"
    A->>S: SELECT COUNT(*) FROM reviews WHERE parent_asin='B0XXXX1' AND rating<=2
    S-->>A: 1,283
    A->>R: query="complaints problems", parent_asin=B0XXXX1, max_rating=2
    R-->>A: 리뷰 10건 (#40211 "broke me out"..., #40587 "sticky"...)
    A->>R: query="caused breakouts or irritation", parent_asin=B0XXXX1, max_rating=2
    R-->>A: 리뷰 10건
    A-->>M: 한국어 답변 + 근거
```

1. **상품 찾기**: 마케터는 상품명만 말했다. 에이전트는 `run_sql`로 `products.title`을 검색해 `parent_asin`을 알아낸다.
2. **규모 확인**: `run_sql`로 1~2점 리뷰가 몇 건인지 센다.
3. **의미 검색**: `search_reviews`에 영어 검색어와 필터(`parent_asin`, `max_rating=2`)를 넘긴다.
4. **다시 판단**: 결과에 트러블 이야기가 많자, 그 주제로 한 번 더 검색해 빈도를 확인한다. 몇 번 더 부를지는 LLM이 판단한다.
5. **답변**: 모은 내용을 한국어로 요약하고 근거를 붙인다.

```text
하이드라 부스트 워터 크림(B0XXXX1)의 1~2점 리뷰는 1,283건입니다.
검색한 리뷰에서 반복되는 불만은 다음과 같습니다.

1. 트러블·자극: 바른 뒤 뾰루지나 따가움이 생겼다는 내용이 가장 많습니다.
   - #40211: "broke me out within two days"
   - #40932: "burning sensation on my cheeks"
2. 끈적임: 흡수가 느리고 끈적인다는 불만입니다.
   - #40587: "stays sticky for hours"
3. 용기·용량: ...

근거:
- SQL: SELECT COUNT(*) FROM reviews WHERE parent_asin='B0XXXX1' AND rating<=2 → 1283
- 인용한 리뷰는 의미 검색으로 찾은 20건 중 일부입니다. 불만의 순서는 검색 결과에서 본 빈도이고, 1,283건 전체를 센 값이 아닙니다.
```

**질문 2: 후속 질문 (MVP 완료 기준 4번)**

```text
> 그럼 5점 리뷰에서는 뭘 칭찬해?
```

`InMemorySaver`가 이전 대화를 기억하므로, 에이전트는 "그럼"이 같은 상품(B0XXXX1)을 가리킨다고 판단한다. 그래서 상품 찾기를 건너뛰고 곧바로 `search_reviews(query="what users love", parent_asin=B0XXXX1, min_rating=5)`를 호출한다.

**질문 3: 답할 수 없는 질문 (MVP 완료 기준 5번)**

```text
> 이 상품의 한국 매출은?
적재 데이터로는 답할 수 없습니다. 적재된 데이터는 미국 Amazon의 상품 정보와 리뷰뿐이고,
매출이나 국가별 판매 정보는 없습니다. 대신 리뷰 수와 평점 수는 알려 드릴 수 있습니다.
```

에이전트는 시스템 프롬프트의 스키마 설명을 보고 매출 컬럼이 없다는 것을 안다. 도구를 부르지 않거나, 불러서 확인한 뒤 거절한다.

## 경계와 이후 확장

- **에이전트가 아는 것은 도구 이름과 입출력뿐이다.** 저장소를 SQLite + 벡터 저장소 파일에서 다른 것(예: Postgres + pgvector)으로 바꿀 때 영향받는 범위는 다음 세 곳이다.
  - 적재 기능
  - 두 도구의 구현
  - 시스템 프롬프트의 스키마 설명(SQL 방언이 바뀌므로)
- **자동 테스트 경계는 "적재한 뒤 두 도구로 조회"** 이다(스펙 #1 Testing Decisions). 에이전트, 시스템 프롬프트, CLI는 사람이 완료 기준 다섯 질문으로 확인한다. 이 부분의 자동화는 MVP 다음의 평가 하네스가 맡는다.
- **MVP에 없는 것**: 웹 UI, 여러 사용자, 세션 간 대화 저장, 얼굴 보습 제품 외 카테고리, 질문 유형별 전용 도구
