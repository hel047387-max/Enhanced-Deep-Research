from typing import Any, Protocol, TypeVar

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from deep_research.config import Settings

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class StructuredModel(Protocol):
    async def ainvoke(self, input: list[BaseMessage]) -> BaseModel | dict[str, object]: ...


def create_structured_model(
    settings: Settings,
    schema: type[StructuredOutput],
) -> Any:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise RuntimeError(
            "Missing model dependency; install the 'langchain-openai' package."
        ) from None

    try:
        model = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
    except Exception as exc:
        raise RuntimeError(
            "Could not initialize the OpenAI model; verify the langchain-openai "
            "installation and model settings."
        ) from exc
    return model.with_structured_output(schema)
