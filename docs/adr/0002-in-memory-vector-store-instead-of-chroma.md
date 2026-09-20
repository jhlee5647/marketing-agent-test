---
Status: accepted
---

# 리뷰 벡터 저장소는 Chroma 대신 InMemoryVectorStore를 JSON 파일로 저장해 쓴다

스펙 #1은 리뷰 임베딩을 Chroma에 넣기로 했다. 그런데 개발 PC(Windows 11, Intel i7-6700HQ)에서 chromadb의 Rust 백엔드가 쓰기(`add`/`upsert`)를 할 때마다 access violation으로 프로세스째 죽는다. chromadb 1.1.1, 1.3.7, 1.4.1, 1.5.8, 1.5.9에서 모두 재현되고, `PersistentClient`와 `EphemeralClient`가 똑같이 죽는다. 순수 Python 구현이던 0.6.3은 의존성 `chroma-hnswlib` 빌드에 실패한다. 업스트림 이슈(chroma-core/chroma#6052)도 열린 채로 해결책이 없다.

그래서 `langchain_core`의 `InMemoryVectorStore`를 쓴다. 적재할 때 리뷰를 임베딩해 JSON 파일(`data/vectors.json`)로 저장하고, CLI가 시작할 때 한 번 읽어 메모리에 올린다. 필터는 Python 함수로 건다.

## 고려한 대안

- **FAISS(`faiss-cpu` + `langchain-community`)**: 이 PC에서 필터까지 동작했다. 하지만 `langchain-community`는 유지보수가 중단되는 중이고, 저장 파일을 읽을 때 pickle을 풀어야 한다(`allow_dangerous_deserialization`).
- **Chroma를 다른 환경(WSL·Docker 서버)에서 돌리기**: 개발 PC에서 테스트가 돌지 않는다.

## Consequences

- 벡터 DB 의존성이 없다. `InMemoryVectorStore`의 코사인 유사도 계산에 필요한 `numpy`만 추가했다.
- 검색은 전수 비교다. 적재 데이터(리뷰 수천 건)에서는 충분하지만, 대량 데이터 아키텍처를 정할 때는 다시 고른다. 스펙이 Chroma를 MVP용 임시 선택으로 둔 것과 같은 위치다.
- 벡터 파일은 들여쓰기된 JSON이라 크다. 가짜 벡터로 리뷰 4,744건 × 1,536차원을 재 보면 개발 PC에서 파일은 약 205MB이고 읽는 데 약 21초가 걸린다. 검색 자체는 0.1초 안이다. 시간 대부분은 JSON 실수 파싱이라, CLI 시작이 문제가 되면 벡터를 바이너리(numpy 등)로 저장하도록 바꾼다.
- 도구는 LangChain vectorstore 인터페이스 뒤에 있으므로(ADR-0001), 저장소를 바꿔도 `search_reviews`의 입출력과 테스트는 그대로다.
