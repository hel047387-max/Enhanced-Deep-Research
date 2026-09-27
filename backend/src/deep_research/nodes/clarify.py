from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, field_validator, model_validator

from deep_research.domain.plan import ResearchBrief
from deep_research.llm import StructuredModel
from deep_research.prompts.scope import clarification_prompt, research_brief_prompt


#保存模型对“是否需要向用户追问”的判断，并保证当需要追问时，必须存在有效问题
class ClarificationDecision(BaseModel, frozen=True):
    needs_clarification: bool
    question: str | None = None#可以是字符串，也可以是 None，默认值是 None。
    reason: str

    @field_validator("question")#单独验证question字段，要求验证器是类方法
    @classmethod
    def normalize_question(cls, value: str | None) -> str | None:#可以是字符串，也可以是 None，但必须传值
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")#在模型创建完成后执行，用于校验多个字段之间的关系是否合理。
    def required_question_is_present(self) -> "ClarificationDecision":#返回一个 ClarificationDecision 类型的对象。
        if self.needs_clarification and self.question is None:
            raise ValueError("a required clarification must include a non-empty question")#二选一
        return self

#把列表里的所有内容统一转换成 LangChain 的消息对象。
def _messages(values: list[Any]) -> list[BaseMessage]:
    return [value if isinstance(value, BaseMessage) else HumanMessage(content=str(value)) for value in values]

#判断“用户的需求够不够清楚”。三种情况
async def clarify_request(
    state: dict[str, Any],
    model: StructuredModel,
) -> dict[str, Any]:
    """判断问题是否需要澄清，并返回中断或继续执行的状态补丁。"""
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

#把已经足够清楚的需求整理成 Planner 能使用的数据
async def write_research_brief(
    state: dict[str, Any],
    model: StructuredModel,
) -> dict[str, ResearchBrief]:
    """根据用户消息生成供 Planner 使用的结构化研究简报。"""
    prompt = research_brief_prompt(state.get("source_preferences"))
    raw = await model.ainvoke([SystemMessage(content=prompt), *_messages(state.get("messages", []))])
    return {"research_brief": ResearchBrief.model_validate(raw)}
