from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, field_validator, model_validator

from deep_research.domain.plan import ResearchBrief
from deep_research.llm import StructuredModel
from deep_research.prompts.scope import clarification_prompt, research_brief_prompt


class ClarificationDecision(BaseModel, frozen=True):
    needs_clarification: bool
    question: str | None = None
    reason: str

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def required_question_is_present(self) -> "ClarificationDecision":
        if self.needs_clarification and self.question is None:
            raise ValueError("a required clarification must include a non-empty question")
        return self


def _messages(values: list[Any]) -> list[BaseMessage]:
    return [value if isinstance(value, BaseMessage) else HumanMessage(content=str(value)) for value in values]


async def clarify_request(
    state: dict[str, Any],
    model: StructuredModel,
) -> dict[str, Any]:
    prompt = clarification_prompt(state.get("source_preferences"))
    raw = await model.ainvoke([SystemMessage(content=prompt), *_messages(state.get("messages", []))])
    decision = ClarificationDecision.model_validate(raw)
    if decision.needs_clarification and state.get("clarification_count", 0) == 0:
        return {
            "interrupt_question": decision.question,
            "clarification_count": 1,
            "status": "waiting_for_user",
        }
    if decision.needs_clarification:
        return {"clarification_assumptions": [decision.reason], "status": "running"}
    return {"status": "running"}


async def write_research_brief(
    state: dict[str, Any],
    model: StructuredModel,
) -> dict[str, ResearchBrief]:
    prompt = research_brief_prompt(state.get("source_preferences"))
    raw = await model.ainvoke([SystemMessage(content=prompt), *_messages(state.get("messages", []))])
    return {"research_brief": ResearchBrief.model_validate(raw)}
