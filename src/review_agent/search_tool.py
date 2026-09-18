from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

EXCERPT_CHARS = 500


def document_prefix(title: str) -> str:
    """임베딩 문서에서 본문 앞에 붙는 리뷰 제목 부분. 문서는 이 접두어와 본문을 이은 것이다."""
    return f"{title}\n\n"


def open_store(vectors_path: Path, embeddings: Embeddings) -> InMemoryVectorStore:
    """적재 데이터의 리뷰 벡터 저장소를 파일에서 읽어 연다."""
    return InMemoryVectorStore.load(str(vectors_path), embeddings)


def search_reviews(
    store: InMemoryVectorStore,
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
    def matches(doc: Document) -> bool:
        m = doc.metadata
        return (
            (parent_asin is None or m["parent_asin"] == parent_asin)
            and (min_rating is None or m["rating"] >= min_rating)
            and (max_rating is None or m["rating"] <= max_rating)
            and (not verified_only or m["verified_purchase"])
        )

    return [
        {
            "review_id": int(d.id),
            "parent_asin": d.metadata["parent_asin"],
            "rating": d.metadata["rating"],
            "title": d.metadata["title"],
            "text": d.page_content.removeprefix(document_prefix(d.metadata["title"]))[:EXCERPT_CHARS],
        }
        for d in store.similarity_search(query, k=k, filter=matches)
    ]
