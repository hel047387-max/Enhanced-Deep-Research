from langchain_core.messages import HumanMessage, SystemMessage

from deep_research.domain.plan import GapAssessment
from deep_research.llm import StructuredModel
from deep_research.nodes.researcher import ResearcherState
from deep_research.prompts.research import gap_analysis_prompt


def assess_gap_node(gap_model: StructuredModel):
    async def assess_gap(state: ResearcherState) -> dict[str, GapAssessment]:
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
            raise ValueError("gap assessment task_id does not match the researcher task")
        return {"gap_assessment": gap}

    return assess_gap
