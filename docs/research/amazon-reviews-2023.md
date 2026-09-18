# Amazon Reviews 2023 데이터셋 조사

리뷰 질의 에이전트 MVP에 적재할 원본 데이터의 스키마, 파일 구성, 받는 방법을 정리한다. 적재 설계에서 무엇을 쓰고 무엇을 버릴지는 이 문서가 아니라 스펙에서 정한다.

## 출처

- **SITE**: https://amazon-reviews-2023.github.io/
- **CARD**: https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023 (README)
- **HFAPI**: https://huggingface.co/api/datasets/McAuley-Lab/Amazon-Reviews-2023
- **RAW**: HF 저장소의 `resolve/main/raw/...` 파일. HTTP Range 요청으로 앞 10MB를 받아 직접 세어 봤다.
- **논문**: arXiv 2403.03952, "Bridging Language and Items for Retrieval and Recommendation" (Hou 외, McAuley)

## 개요

- 수집 기간은 1996년 5월부터 2023년 9월까지이고, 리뷰는 전체 571.54M건이다. (SITE, CARD)
- 언어 태그는 `en`이다. (CARD, HFAPI) 비영어 리뷰를 걸러냈다는 명시적 서술은 없지만, US 마켓플레이스 데이터로 보인다.
- 카테고리마다 **리뷰 파일**과 **메타 파일**(상품 정보)이 한 쌍으로 있다.

## 리뷰 파일 스키마

출처: SITE, CARD

| 필드 | 타입 | 의미 |
|---|---|---|
| `rating` | float | 별점 1.0–5.0 |
| `title` | str | 리뷰 제목 |
| `text` | str | 리뷰 본문 |
| `images` | list | 리뷰어가 올린 이미지. 원소마다 `small_image_url`, `medium_image_url`, `large_image_url`, `attachment_type` 키가 있다. (RAW) |
| `asin` | str | 상품 변형(색상·용량 등) ID |
| `parent_asin` | str | 변형을 묶은 부모 상품 ID |
| `user_id` | str | 리뷰어 ID |
| `timestamp` | int | Unix time. 단위는 **밀리초**다. 예: `1588687728923`은 2020-05다. (RAW, HFAPI) |
| `helpful_vote` | int | "도움이 됨" 투표 수 |
| `verified_purchase` | bool | 구매 인증 여부 |

예시 행 (RAW, `All_Beauty.jsonl` 첫 행):

```json
{"rating": 5.0, "title": "Such a lovely scent but not overpowering.", "text": "This spray is really nice. ...", "images": [], "asin": "B00YQ6X8EO", "parent_asin": "B00YQ6X8EO", "user_id": "AGKHLEW2SOWHNMFQIJGBECAF7INQ", "timestamp": 1588687728923, "helpful_vote": 0, "verified_purchase": true}
```

## 메타 파일 스키마

출처: SITE, CARD

| 필드 | 타입 | 의미 |
|---|---|---|
| `main_category` | str | 상품 도메인 |
| `title` | str | 상품명 |
| `average_rating` | float | 상품 페이지의 평균 별점 |
| `rating_number` | int | 평점 개수 |
| `features` | list[str] | 불릿 형식의 특징 설명 |
| `description` | list[str] | 상품 설명 |
| `price` | float 또는 null | 크롤링 시점 USD 가격. SITE는 float, CARD의 HF feature 정의는 `string`이라고 적었다. RAW JSON에는 숫자 또는 `null`이 들어 있다. |
| `images` | list | 원소마다 `thumb`, `large`, `hi_res`, `variant`(예: `MAIN`, `PT01`) 키가 있다. |
| `videos` | list | 원소마다 `title`, `url` 등이 있다. |
| `store` | str | 스토어(판매자) 이름 |
| `categories` | list[str] | 계층 카테고리 경로. 최상위부터 순서대로 담은 리스트다. |
| `details` | dict | 자유 형식 키-값. 예: `Brand`, `Item Form`, `Manufacturer`, `UPC`, `Use for` |
| `parent_asin` | str | 부모 상품 ID |
| `bought_together` | list | 함께 구매한 번들 |

메타 파일에는 `asin` 필드가 없다.

예시 행 (RAW, `meta_Beauty_and_Personal_Care.jsonl`, `images` 생략):

```json
{"main_category": "All Beauty", "title": "Skinfix Resurface AHA Renewing Cream 0.35 fl.oz. 10 ml. Travel size New", "average_rating": 4.2, "rating_number": 15, "features": ["...", "Formulation: Cream", "Brand: Skinfix", "Type: Day Cream"], "description": ["Condition: New without box: ..."], "price": null, "videos": [], "store": "Bissport", "categories": ["Beauty & Personal Care", "Skin Care", "Face", "Creams & Moisturizers", "Face Moisturizers"], "details": {"Brand": "Bissport", "Item Form": "Cream", "Unit Count": "1.00 Count", "Number of Items": "1", "Use for": "Face", "Manufacturer": "Bissport"}, "parent_asin": "B08PFNJF1X", "bought_together": null}
```

## 리뷰와 메타의 연결

- 조인 키는 **`parent_asin`** 이다. 공식 문서 원문: "Products with different colors, styles, sizes usually belong to the same parent ID. The 'asin' in previous Amazon datasets is actually parent ID. Please use parent ID to find product meta." (SITE, CARD)
- "Note that some items lack metadata." (CARD) 메타가 없는 `parent_asin`의 리뷰가 있을 수 있다.

## 필드 품질

공식 문서에는 적혀 있지 않다. RAW 파일 앞 10MB를 직접 센 값이다.

| 항목 | `meta_All_Beauty` (5,189행) | `meta_Beauty_and_Personal_Care` (3,240행) |
|---|---|---|
| `categories`가 `[]` | 5,189 (전부) | 0 |
| `price`가 null | 4,203 (약 81%) | 1,541 (약 48%) |
| `description`이 `[]` | 4,246 | 1,540 |
| `store`가 null | 531 | 155 |
| `bought_together`가 null | 5,189 (전부) | 3,240 (전부) |

- **`main_category`는 파일 이름과 맞지 않는다.** `Beauty_and_Personal_Care` 파일인데도 대부분의 값이 `"All Beauty"`(2,596행)다. 나머지는 "Health & Personal Care", "Premium Beauty", "Amazon Home", "AMAZON FASHION" 등이다. 카테고리를 거를 때는 `categories`를 써야 한다.
- **`store`와 `details.Brand`는 브랜드로 믿기 어렵다.** 위 예시 행의 상품명은 Skinfix인데 `store`와 `details.Brand`는 재판매자인 "Bissport"다.

## 보습 제품이 들어 있는 파일

규모 (SITE, CARD):

| 파일 | #users | #items | #ratings | R_Tokens | M_Tokens |
|---|---|---|---|---|---|
| All_Beauty | 632.0K | 112.6K | 701.5K | 31.6M | 74.1M |
| Beauty_and_Personal_Care | 11.3M | 1.0M | 23.9M | 1.1B | 913.7M |

파일 크기 (HF 비압축 크기는 HFAPI tree, UCSD `.gz` 크기는 HTTP HEAD의 Content-Length로 확인):

| 파일 | HF 비압축 `.jsonl` | UCSD `.jsonl.gz` |
|---|---|---|
| `All_Beauty` 리뷰 | 326.6MB | 94.4MB |
| `meta_All_Beauty` | 213.0MB | 39.9MB |
| `Beauty_and_Personal_Care` 리뷰 | 11.02GB | 2.96GB |
| `meta_Beauty_and_Personal_Care` | 2.84GB | 711.2MB |

- `All_Beauty`는 메타의 `categories`가 비어 있어서 보습 제품만 골라낼 수 없다.
- 카테고리로 거르려면 **`Beauty_and_Personal_Care`** 를 써야 한다.

`Beauty_and_Personal_Care` 메타 앞 10MB에 나온 보습 관련 `categories` 경로 (RAW):

| 경로 (`Beauty & Personal Care > Skin Care >` 이후) | 건수 |
|---|---|
| `Face > Creams & Moisturizers > Face Moisturizers` | 34 |
| `Face > Creams & Moisturizers` (하위 없음) | 8 |
| `Face > Creams & Moisturizers > Night Creams` | 7 |
| `Face > Creams & Moisturizers > Face Oil` | 5 |
| `Face > Creams & Moisturizers > Neck & Décolleté` | 2 |
| `Body > Moisturizers > Lotions` / `Creams` / `Oils` / `Body Butters` | (바디) |
| `Lip Care > Balms & Moisturizers` | (립) |

얼굴 보습 제품은 `categories[1:4] == ["Skin Care", "Face", "Creams & Moisturizers"]` 조건으로 고를 수 있다.

## 받는 방법

형식은 JSON Lines(한 줄에 객체 하나)다. UCSD 배포본은 gzip, HF 저장소의 `raw/` 아래 파일은 비압축이다.

직접 URL:

- UCSD 리뷰 (SITE, HTTP 200 확인): `https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw/review_categories/Beauty_and_Personal_Care.jsonl.gz`
- UCSD 메타 (SITE, HTTP 200 확인): `https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw/meta_categories/meta_Beauty_and_Personal_Care.jsonl.gz`
- HF 메타: `https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw/meta_categories/meta_Beauty_and_Personal_Care.jsonl`
- CARD에는 `https://datarepo.eng.ucsd.edu/mcauley_group/data/amazon_2023/raw/...`라는 다른 호스트도 적혀 있다.

제약:

- **HF datasets viewer와 rows API는 쓸 수 없다.**
  - `is-valid` 응답이 `{"preview":false,"viewer":false,...}`이다.
  - rows API는 "doesn't support this dataset because it runs arbitrary Python code" 에러를 낸다.
  - 이 데이터셋은 로딩 스크립트(`Amazon-Reviews-2023.py`)와 `trust_remote_code=True`에 의존한다. 최신 `datasets` 라이브러리가 이 방식을 지원하는지는 확인하지 않았다.
- **HF 비압축 파일은 HTTP Range 요청을 받는다.** 앞부분만 받아 줄 단위로 파싱할 수 있다. 마지막 줄은 잘려 있으므로 버린다.
- **메타는 카테고리별로 정렬되어 있지 않다.** 얼굴 보습 제품만 모으려면 두 파일을 차례로 스트리밍해야 한다.
  1. 메타 파일 전체를 스트리밍으로 한 번 훑어 대상 `parent_asin` 집합을 만든다.
  2. 리뷰 파일을 스트리밍하면서 그 집합에 속한 리뷰만 남긴다.
- UCSD `.gz`를 스트리밍하며 압축을 풀면 디스크에 전체를 저장하지 않아도 된다. 전송량은 약 3.7GB로 줄지 않는다.

## 라이선스

- SITE, CARD, HFAPI 어디에도 데이터셋 라이선스가 명시되어 있지 않다. CARD 메타데이터에도 license 필드가 없다.
- arXiv의 CC BY 4.0은 논문 자체의 라이선스다.
- 리뷰 텍스트는 Amazon 콘텐츠이므로 내부 MVP 용도로만 쓰고 재배포하지 않는다. 이것은 추론에 따른 방침이다.
