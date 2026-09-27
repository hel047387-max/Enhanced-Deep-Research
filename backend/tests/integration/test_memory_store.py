import sqlite3
from datetime import UTC, datetime

import pytest

from deep_research.domain.evidence import EvidenceItem, Relevance, Source, SourceType
from deep_research.domain.plan import ResearchBrief
from deep_research.domain.review import ReportDraft, ReportParagraph, ReportSection
from deep_research.persistence.memory_store import MemoryStore


def sample_state():
    now = datetime.now(UTC)
    source = Source(
        source_id="source-1",
        url="https://example.com/a",
        canonical_url="https://example.com/a",
        title="Research source",
        domain="example.com",
        retrieved_at=now,
        content_hash="abc",
        source_type=SourceType.WEB,
    )
    evidence = EvidenceItem(
        evidence_id="evidence-1",
        task_id="task-1",
        source_id="source-1",
        claim="Battery capacity increased",
        excerpt="Capacity rose by ten percent.",
        context="A measured comparison.",
        relevance=Relevance.HIGH,
        discovered_in_round=1,
        citation_label="1",
    )
    return {
        "research_brief": ResearchBrief(main_question="电池容量趋势", scope="2025"),
        "draft_report": ReportDraft(
            title="Battery report",
            executive_summary=[
                ReportParagraph(
                    paragraph_id="summary-1",
                    text="Capacity increased.",
                    evidence_ids=["evidence-1"],
                )
            ],
            sections=[
                ReportSection(
                    section_id="findings",
                    heading="Findings",
                    paragraphs=[],
                )
            ],
            limitations=["Only one source was available."],
            suggested_actions=[],
        ),
        "sources": {"source-1": source},
        "evidence": {"evidence-1": evidence},
        "tasks": {},
        "final_report": "# Battery report\n\nCapacity increased. [1]",
    }


@pytest.mark.asyncio
async def test_archive_is_idempotent_and_restores_evidence(tmp_path):
    store = MemoryStore(tmp_path / "research.db")
    await store.initialize()
    state = sample_state()

    await store.archive("thread-1", "run-1", state)
    await store.archive("thread-1", "run-1", state)

    archives = await store.list_archives()
    detail = await store.get_archive("thread-1")
    assert len(archives) == 1
    assert detail is not None
    assert detail["report"] == state["final_report"]
    assert detail["evidence"][0]["source_id"] == "source-1"
    assert detail["cards"][0]["evidence_ids"] == ["evidence-1"]
    with sqlite3.connect(tmp_path / "research.db") as connection:
        source = connection.execute(
            "SELECT canonical_url, published_at, retrieved_at FROM archive_sources"
        ).fetchone()
        archived_evidence = connection.execute(
            "SELECT task_id, claim FROM archive_evidence"
        ).fetchone()
    assert source[0] == "https://example.com/a"
    assert source[1] is None
    assert source[2] is not None
    assert archived_evidence == ("task-1", "Battery capacity increased")


@pytest.mark.asyncio
async def test_short_chinese_query_finds_archived_research(tmp_path):
    store = MemoryStore(tmp_path / "research.db")
    await store.initialize()
    await store.archive("thread-1", "run-1", sample_state())

    results = await store.search("电池")

    assert [item["thread_id"] for item in results["researches"]] == ["thread-1"]
    long_results = await store.search("电池容量")
    assert [item["thread_id"] for item in long_results["researches"]] == ["thread-1"]


@pytest.mark.asyncio
async def test_invalid_card_evidence_does_not_commit_archive(tmp_path):
    store = MemoryStore(tmp_path / "research.db")
    await store.initialize()
    state = sample_state()
    state["draft_report"] = state["draft_report"].model_copy(
        update={
            "executive_summary": [
                ReportParagraph(
                    paragraph_id="summary-1",
                    text="Unsupported.",
                    evidence_ids=["missing"],
                )
            ],
        }
    )

    with pytest.raises(ValueError, match="evidence"):
        await store.archive("thread-1", "run-1", state)

    assert await store.list_archives() == []


@pytest.mark.asyncio
async def test_memory_api_lists_searches_and_reads_archived_report(tmp_path):
    from types import SimpleNamespace

    from httpx import ASGITransport, AsyncClient

    from deep_research.api.main import create_app
    from deep_research.auth.dependencies import require_owner

    store = MemoryStore(tmp_path / "research.db")
    await store.initialize()
    await store.archive("thread-1", "run-1", sample_state())
    app = create_app(SimpleNamespace(memory_store=store))
    app.dependency_overrides[require_owner] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        listing = await client.get("/api/v1/memories/researches")
        search = await client.get("/api/v1/memories/search", params={"q": "电池"})
        detail = await client.get("/api/v1/memories/researches/thread-1")

    assert listing.status_code == 200
    assert listing.json()["items"][0]["thread_id"] == "thread-1"
    assert search.json()["researches"][0]["thread_id"] == "thread-1"
    assert detail.json()["report"] == sample_state()["final_report"]
    assert detail.json()["evidence"][0]["evidence_id"] == "evidence-1"


@pytest.mark.asyncio
async def test_history_pages_do_not_repeat_archives(tmp_path):
    store = MemoryStore(tmp_path / "research.db")
    await store.initialize()
    await store.archive("thread-1", "run-1", sample_state())
    await store.archive("thread-2", "run-2", sample_state())

    first = await store.list_archives(limit=1, offset=0)
    second = await store.list_archives(limit=1, offset=1)

    assert len(first) == len(second) == 1
    assert {first[0]["thread_id"], second[0]["thread_id"]} == {"thread-1", "thread-2"}
