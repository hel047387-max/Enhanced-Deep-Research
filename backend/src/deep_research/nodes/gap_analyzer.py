from langchain_core.messages import HumanMessage, SystemMessage

from deep_research.domain.plan import GapAssessment
from deep_research.llm import StructuredModel
from deep_research.nodes.researcher import ResearcherState, researcher_failure_patch
from deep_research.prompts.research import gap_analysis_prompt
from deep_research.runtime import CancellationChecker, EventSink


def assess_gap_node(
    gap_model: StructuredModel,
    event_sink: EventSink,
    cancellation_checker: CancellationChecker,
):
    async def assess_gap(state: ResearcherState) -> dict[str, object]:
        cancellation_checker.raise_if_cancelled()
        try:
            raw = await gap_model.ainvoke(
                [
                    SystemMessage(
                        content=gap_analysis_prompt(
                            state["research_brief"], state["task"]
                        )
                    ),
                    HumanMessage(
                        content="\n".join(
                            item.claim for item in state.get("evidence", {}).values()
                        )
                    ),
                ]
            )
            gap = GapAssessment.model_validate(raw)
            if gap.task_id != state["task"].task_id:
                raise ValueError("gap assessment task_id mismatch")
        except Exception:  # noqa: BLE001 - converted to a stable public error
            return researcher_failure_patch(state, "gap_analysis_failed")
        await event_sink.emit(
            "gap_assessed",
            {
                "task_id": gap.task_id,
                "coverage": gap.coverage.value,
                "should_continue": gap.should_continue,
            },
        )
        return {"gap_assessment": gap}

    return assess_gap
