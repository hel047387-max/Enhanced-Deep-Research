from __future__ import annotations


def query_routing_prompt() -> str:
    return (
        "Classify a literature-search query into exactly one retrieval mode. "
        "Use direct for specific factual or known-item queries, mqe for broad or "
        "multi-aspect questions, and hyde for conceptual questions whose relevant "
        "passage may use different wording. Return a concise reason."
    )


def multi_query_prompt() -> str:
    return (
        "Generate one to three short, distinct literature-search queries that cover "
        "the user's intent. Preserve names, dates, and technical constraints. "
        "Return only retrieval queries; they are search keys, not evidence."
    )


def hyde_prompt() -> str:
    return (
        "Write one concise hypothetical passage that a relevant scholarly source "
        "could contain. Use it only as a semantic retrieval key. It is not evidence "
        "and must never be cited or presented as a factual source."
    )

def literature_answer_prompt() -> str:
    return (
        "Answer the question only from the supplied literature context. "
        "Return a concise answer and the unit_id values that directly support it. "
        "Every factual claim must be supported by those units. If the context does "
        "not support an answer, do not invent facts or identifiers."
    )
