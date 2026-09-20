from dataclasses import dataclass, field

from langchain.chat_models import init_chat_model

JUDGE_PROMPT = """너는 리뷰 질의 에이전트의 답변을 루브릭에 비추어 채점하는 심판이다.

루브릭이 요구하는 것이 답변에 있으면 통과, 하나라도 빠졌으면 실패다. 답변의 문체나 길이,
루브릭이 요구하지 않은 것은 보지 않는다. 사실 확인은 네 일이 아니다 — 근거의 실재 여부는 따로 검증한다.

판정 근거는 한 줄로 쓴다. 통과면 무엇이 있어서 통과인지, 실패면 무엇이 빠졌는지 적는다.

## 마케터의 질문
{question}

## 루브릭
{rubric}

## 답변
{answer}
"""


@dataclass
class JudgeVerdict:
    """심판이 케이스 하나의 답변에 내린 판정."""

    passed: bool
    reason: str
    tokens: dict[str, int] = field(default_factory=dict)


def openai_judge(model: str):
    """설정한 모델로 루브릭 채점을 하는 심판을 만든다.

    에이전트와 다른 모델을 쓴다. 같은 모델이면 같은 맹점을 공유해, 에이전트가 놓친 것을 심판도 놓친다.

    Returns:
        루브릭·질문·답변을 받아 `JudgeVerdict`를 돌려주는 함수.
    """
    chat = init_chat_model(f"openai:{model}").with_structured_output(
        {
            "title": "verdict",
            "description": "루브릭에 비춘 통과 여부와 그 이유",
            "type": "object",
            "properties": {
                "passed": {"type": "boolean", "description": "루브릭이 요구하는 것이 답변에 다 있으면 true"},
                "reason": {"type": "string", "description": "판정 근거 한 줄"},
            },
            "required": ["passed", "reason"],
        },
        include_raw=True,
    )

    def judge(rubric: str, question: str, answer: str) -> JudgeVerdict:
        result = chat.invoke(JUDGE_PROMPT.format(question=question, rubric=rubric, answer=answer))
        usage = getattr(result["raw"], "usage_metadata", None) or {}
        return JudgeVerdict(
            passed=result["parsed"]["passed"],
            reason=result["parsed"]["reason"],
            tokens={"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)},
        )

    return judge
