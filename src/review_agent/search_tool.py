import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from langchain_core.embeddings import Embeddings

EMBEDDING_MODEL = "text-embedding-3-small"
EXCERPT_CHARS = 500


def document_prefix(title: str) -> str:
    """임베딩 문서에서 본문 앞에 붙는 리뷰 제목 부분. 문서는 이 접두어와 본문을 이은 것이다."""
    return f"{title}\n\n"


@dataclass
class ReviewVectorStore:
    """적재 데이터의 리뷰 벡터. 검색과 필터에 필요한 것만 들고, 리뷰 제목·본문은 SQLite에서 읽는다.

    벡터는 L2 정규화된 float32 행렬 하나로 상주한다. 검색 한 번은 그 행렬과 질의 벡터의 곱이라
    저장된 것을 다시 복사하지 않는다.
    """

    embeddings: Embeddings
    db_path: Path
    ids: np.ndarray
    vectors: np.ndarray
    parent_asins: np.ndarray
    ratings: np.ndarray
    verified: np.ndarray


def open_store(vectors_path: Path, db_path: Path, embeddings: Embeddings) -> ReviewVectorStore:
    """적재 데이터의 리뷰 벡터 저장소를 파일에서 읽어 연다."""
    with np.load(vectors_path) as stored:
        return ReviewVectorStore(
            embeddings, db_path,
            ids=stored["ids"], vectors=stored["vectors"], parent_asins=stored["parent_asins"],
            ratings=stored["ratings"], verified=stored["verified"],
        )


def search_reviews(
    store: ReviewVectorStore,
    query: str,
    parent_asin: str | None = None,
    min_rating: float | None = None,
    max_rating: float | None = None,
    verified_only: bool = False,
    k: int = 10,
) -> list[dict]:
    """리뷰를 의미 검색하고 상품, 별점 범위, 구매 인증으로 거른다.

    Returns:
        가까운 순서대로 최대 `k`개 리뷰. 각 리뷰는 `review_id`, `parent_asin`, `rating`, `title`, 본문 앞부분 `text`를 담은 dict.
    """
    matching = np.ones(len(store.ids), dtype=bool)
    if parent_asin is not None:
        matching &= store.parent_asins == parent_asin
    if min_rating is not None:
        matching &= store.ratings >= min_rating
    if max_rating is not None:
        matching &= store.ratings <= max_rating
    if verified_only:
        matching &= store.verified

    embedded = np.asarray(store.embeddings.embed_query(query), dtype=np.float32)
    similarity = store.vectors @ (embedded / np.linalg.norm(embedded))
    candidates = np.flatnonzero(matching)
    nearest = candidates[np.argsort(-similarity[candidates])[:k]]
    return _reviews_of(store.db_path, [int(review_id) for review_id in store.ids[nearest]])


def _reviews_of(db_path: Path, review_ids: list[int]) -> list[dict]:
    """리뷰 제목과 본문은 벡터 저장소가 아니라 적재 데이터 SQLite에서 읽는다. 찾은 순서를 그대로 지킨다."""
    if not review_ids:
        return []
    with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        found = {
            row[0]: {"review_id": row[0], "parent_asin": row[1], "rating": row[2], "title": row[3],
                     "text": row[4][:EXCERPT_CHARS]}
            for row in conn.execute(
                "SELECT review_id, parent_asin, rating, title, text FROM reviews WHERE review_id IN"
                f" ({','.join('?' * len(review_ids))})",
                review_ids,
            )
        }
    return [found[review_id] for review_id in review_ids]
