from typing import Any, Protocol, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel

from deep_research.config import Settings

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class StructuredModel(Protocol):
    async def ainvoke(self, input: list[BaseMessage]) -> BaseModel | dict[str, object]: ...


class _RepairingStructuredModel:
    """对结构化模型增加一次解析失败修复重试。"""
    def __init__(self, model: Any) -> None:
        self._model = model

    async def ainvoke(
        self,
        input: list[BaseMessage],
    ) -> BaseModel | dict[str, object]:
        """调用底层模型，解析失败时最多请求一次修复。"""
        messages = list(input)
        for attempt in range(2):
            result = await self._model.ainvoke(messages)
            parsed = result.get("parsed")
            if parsed is not None:
                return parsed

            parsing_error = result.get("parsing_error")
            raw_output = str(result.get("raw"))[:8000]
            if attempt == 1:
                if isinstance(parsing_error, Exception):
                    raise parsing_error
                raise ValueError("Model did not return a parseable structured output.")

            messages = [
                *messages,
                HumanMessage(
                    content=(
                        "Correct the previous structured output so it matches the "
                        "required schema exactly. Return only the corrected structured "
                        f"output. Previous output: {raw_output}. "
                        f"Parsing error: {parsing_error}"
                    )
                ),
            ]

        raise AssertionError("structured output repair loop exhausted")


def create_structured_model(
    settings: Settings,
    schema: type[StructuredOutput],
) -> Any:
    """创建 OpenAI 兼容的结构化模型，并按供应商配置稳定输出参数。"""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise RuntimeError(
            "Missing model dependency; install the 'langchain-openai' package."
        ) from None

    try:
        model_options: dict[str, Any] = {
            "model": settings.llm_model,
            "api_key": settings.llm_api_key,
            "base_url": settings.llm_base_url,
            "temperature": 0,
        }
        if settings.llm_provider.lower() == "deepseek" or "deepseek" in (
            settings.llm_base_url or ""
        ).lower():
            model_options["extra_body"] = {"thinking": {"type": "disabled"}}
        model = ChatOpenAI(**model_options)
    except Exception as exc:
        raise RuntimeError(
            "Could not initialize the OpenAI model; verify the langchain-openai "
            "installation and model settings."
        ) from exc
    structured = model.with_structured_output(
        schema.model_json_schema(),
        method="function_calling",
        include_raw=True,
    )
    return _RepairingStructuredModel(structured)
