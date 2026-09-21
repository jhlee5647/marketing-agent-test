import os
import time
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from langchain_core.embeddings import Embeddings
from langchain_core.tracers.run_collector import RunCollectorCallbackHandler
from langchain_core.vectorstores import InMemoryVectorStore

from review_agent.eval.harness import TurnResult
from review_agent.search_tool import open_store

READ_CHUNK_BYTES = 8 << 20


def cold_store_load(vectors_path: Path, embeddings: Embeddings) -> tuple[InMemoryVectorStore, dict]:
    """페이지 캐시를 버리고 벡터 저장소를 열어, 콜드 로드 시간과 실효 I/O 처리량을 함께 잰다.

    사람이 실제로 겪는 것이 콜드이고, 큰 규모에서는 벡터 파일과 파싱된 구조가 함께 RAM에 들어가지 않아
    웜이 애초에 불가능하다. 콜드로 통일해야 작은 규모와 큰 규모가 같은 자로 재어진다.

    파일을 두 번 콜드로 지나간다. 먼저 순수하게 읽기만 해서 볼륨이 내는 처리량을 재고, 다시 캐시를 버린 뒤
    실제 로드를 잰다. 로드에서 읽기를 뺀 나머지가 파싱이라, 큰 규모에서 로드가 튈 때 파싱 탓인지 볼륨 탓인지
    구분된다. 한 번 더 지나가는 값은 가장 큰 점에서도 1분 미만이다.

    Returns:
        (열린 벡터 저장소, 콜드 로드·순수 읽기·파싱 소요 시간과 실효 I/O 처리량을 담은 dict).
    """
    size = vectors_path.stat().st_size
    _drop_page_cache(vectors_path)
    read_ms = _timed_read(vectors_path)
    _drop_page_cache(vectors_path)
    start = time.perf_counter()
    store = open_store(vectors_path, embeddings)
    open_ms = (time.perf_counter() - start) * 1000
    return store, {
        "vector_store_open_ms": open_ms,
        "vector_store_read_ms": read_ms,
        "vector_store_parse_ms": open_ms - read_ms,
        "vector_store_mb_per_second": size / 1e6 / (read_ms / 1000),
        "vector_store_bytes": size,
    }


def _drop_page_cache(path: Path) -> None:
    """이 파일이 페이지 캐시에 올려 둔 것을 버린다. 루트 권한이 필요 없다."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    finally:
        os.close(fd)


def _timed_read(path: Path) -> float:
    """파일을 순차로 읽기만 하는 데 드는 밀리초. 파싱이 섞이지 않은 순수 I/O다."""
    start = time.perf_counter()
    with path.open("rb") as file:
        while file.read(READ_CHUNK_BYTES):
            pass
    return (time.perf_counter() - start) * 1000


class TimingEmbeddings(Embeddings):
    """임베딩 호출의 횟수와 소요 시간을 재는 래퍼.

    LangChain에는 임베딩용 콜백이 없어서 이 구간만은 직접 재야 한다. 운영 코드에 계측을 심지 않으려고
    평가할 때만 끼운다.
    """

    def __init__(self, inner: Embeddings):
        self._inner = inner
        self._calls = 0
        self._durations_ms: list[float] = []

    def embed_query(self, text: str) -> list[float]:
        return self._timed(self._inner.embed_query, text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._timed(self._inner.embed_documents, texts)

    def _timed(self, call, argument):
        start = time.perf_counter()
        try:
            return call(argument)
        finally:
            self._durations_ms.append((time.perf_counter() - start) * 1000)
            self._calls += 1

    def take(self) -> tuple[int, list[float]]:
        """마지막으로 가져간 뒤의 호출 수와 소요 시간을 돌려주고 비운다.

        Returns:
            (호출 수, 호출별 소요 시간 밀리초).
        """
        calls, durations = self._calls, self._durations_ms
        self._calls, self._durations_ms = 0, []
        return calls, durations


def agent_executor(agent, embeddings: TimingEmbeddings):
    """에이전트를 실제로 불러 답변·궤적·소요 시간·토큰을 관측하는 실행기를 만든다.

    케이스 하나가 대화 하나다. 한 케이스의 턴들은 같은 `thread_id`를 쓰므로 뒤 턴이 앞 대화를 이어받는다.

    Returns:
        질문들을 받아 턴별 결과를 돌려주는 함수.
    """
    def execute(questions: Sequence[str]) -> list[TurnResult]:
        config = {"configurable": {"thread_id": str(uuid4())}}
        results, seen = [], 0
        for question in questions:
            collector = RunCollectorCallbackHandler()
            embeddings.take()
            start = time.perf_counter()
            output = agent.invoke(
                {"messages": [{"role": "user", "content": question}]},
                {**config, "callbacks": [collector]},
            )
            total_ms = (time.perf_counter() - start) * 1000
            messages = output["messages"][seen:]
            seen = len(output["messages"])
            embedding_calls, embed_ms = embeddings.take()
            timings = timings_of(collector.traced_runs)
            timings["total"] = [total_ms]
            if embed_ms:
                timings["embed_query"] = embed_ms
            results.append(
                TurnResult(
                    answer=messages[-1].content,
                    trajectory=tool_calls_of(messages),
                    timings_ms=timings,
                    tokens=tokens_of(messages),
                    embedding_calls=embedding_calls,
                )
            )
        return results

    return execute


def timings_of(runs) -> dict[str, list[float]]:
    """수집한 실행 트리에서 LLM 턴과 도구 호출의 소요 시간을 꺼낸다.

    Returns:
        `llm`과 도구 이름별 소요 시간 밀리초 목록.
    """
    timings: dict[str, list[float]] = {}
    for run in _walk(runs):
        if run.end_time is None or run.run_type not in ("llm", "tool"):
            continue
        label = "llm" if run.run_type == "llm" else run.name
        timings.setdefault(label, []).append((run.end_time - run.start_time).total_seconds() * 1000)
    return timings


def tool_calls_of(messages) -> list[dict]:
    """메시지에서 에이전트가 부른 도구의 이름과 인자를 순서대로 꺼낸다."""
    return [
        {"tool": call["name"], "args": call["args"]}
        for message in messages
        for call in getattr(message, "tool_calls", None) or []
    ]


def tokens_of(messages) -> dict[str, int]:
    """메시지의 사용량 메타데이터에서 입력·출력 토큰을 더한다."""
    totals = {"input": 0, "output": 0}
    for message in messages:
        usage = getattr(message, "usage_metadata", None) or {}
        totals["input"] += usage.get("input_tokens", 0)
        totals["output"] += usage.get("output_tokens", 0)
    return totals


def _walk(runs):
    for run in runs:
        yield run
        yield from _walk(run.child_runs or [])
