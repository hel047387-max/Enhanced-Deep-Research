from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deep_research.domain.evidence import EvidenceItem, Relevance, Source, SourceType
from deep_research.domain.review import (
    ReportDraft,
    ReportParagraph,
    ReportSection,
    ReviewIssue,
    ReviewResult,
    ReviewVerdict,
)
from deep_research.services.citations import (
    CitationValidationError,
    render_report,
    validate_draft,
)


@pytest.fixture
def source_map() -> dict[str, Source]:
    return {
        "src-1": Source(
            source_id="src-1",
            url="https://example.com/source",
            canonical_url="https://example.com/source",
            title="Example Source",
            domain="example.com",
            retrieved_at=datetime(2026, 8, 26, tzinfo=UTC),
            content_hash="hash-1",
            source_type=SourceType.WEB,
        ),
        "src-2": Source(
            source_id="src-2",
            url="https://example.com/other",
            canonical_url="https://example.com/other",
            title="Other Source",
            domain="example.com",
            retrieved_at=datetime(2026, 8, 26, tzinfo=UTC),
            content_hash="hash-2",
            source_type=SourceType.OFFICIAL,
        ),
    }


@pytest.fixture
def evidence_map() -> dict[str, EvidenceItem]:
    return {
        evidence_id: EvidenceItem(
            evidence_id=evidence_id,
            task_id="task-1",
            source_id=source_id,
            claim=claim,
            excerpt=claim,
            context="Research context",
            relevance=Relevance.HIGH,
            discovered_in_round=1,
            citation_label=evidence_id.upper(),
        )
        for evidence_id, source_id, claim in (
            ("ev-1", "src-1", "First fact"),
            ("ev-2", "src-1", "Second fact"),
            ("ev-3", "src-2", "Third fact"),
        )
    }


def test_renderer_reuses_one_number_for_evidence_from_same_source(source_map, evidence_map) -> None:
    draft = ReportDraft(
        title="Report",
        executive_summary=[],
        sections=[
            ReportSection(
                section_id="findings",
                heading="Findings",
                paragraphs=[
                    ReportParagraph(paragraph_id="p-1", text="First fact.", evidence_ids=["ev-1"]),
                    ReportParagraph(paragraph_id="p-2", text="Second fact.", evidence_ids=["ev-2"]),
                ],
            )
        ],
        limitations=[],
        suggested_actions=[],
    )
    markdown = render_report(draft, evidence_map, source_map)
    assert "First fact. [1]" in markdown
    assert "Second fact. [1]" in markdown
    assert markdown.count("https://example.com/source") == 1
    assert markdown.count("[1] Example Source —") == 1


def test_renderer_numbers_sources_in_first_use_order_and_renders_references_once(source_map, evidence_map) -> None:
    draft = ReportDraft(
        title="Report",
        executive_summary=[ReportParagraph(paragraph_id="summary", text="Third fact.", evidence_ids=["ev-3"])],
        sections=[
            ReportSection(
                section_id="findings",
                heading="Findings",
                paragraphs=[
                    ReportParagraph(paragraph_id="p-1", text="First fact.", evidence_ids=["ev-1", "ev-3"]),
                    ReportParagraph(paragraph_id="p-2", text="Second fact.", evidence_ids=["ev-2"]),
                ],
            )
        ],
        limitations=["Limited scope"],
        suggested_actions=["Review later"],
    )
    markdown = render_report(draft, evidence_map, source_map)
    assert "Third fact. [1]" in markdown
    assert "First fact. [2] [1]" in markdown
    assert "Second fact. [2]" in markdown
    assert markdown.count("[1] Other Source — https://example.com/other") == 1
    assert markdown.count("[2] Example Source — https://example.com/source") == 1
    assert "## Limitations\n\n- Limited scope" in markdown
    assert "## Suggested actions\n\n- Review later" in markdown


def test_renderer_rejects_unknown_evidence_id(source_map, evidence_map) -> None:
    draft = ReportDraft(
        title="Report",
        executive_summary=[],
        sections=[
            ReportSection(
                section_id="findings",
                heading="Findings",
                paragraphs=[ReportParagraph(paragraph_id="p-1", text="Fact.", evidence_ids=["ev-missing"])],
            )
        ],
        limitations=[],
        suggested_actions=[],
    )
    with pytest.raises(CitationValidationError):
        render_report(draft, evidence_map, source_map)


def test_validation_reports_missing_source_for_known_evidence(source_map, evidence_map) -> None:
    evidence_map["ev-1"] = evidence_map["ev-1"].model_copy(update={"source_id": "src-missing"})
    draft = ReportDraft(
        title="Report",
        executive_summary=[],
        sections=[
            ReportSection(
                section_id="findings",
                heading="Findings",
                paragraphs=[ReportParagraph(paragraph_id="p-1", text="Fact.", evidence_ids=["ev-1"])],
            )
        ],
        limitations=[],
        suggested_actions=[],
    )
    issues = validate_draft(draft, evidence_map, source_map)
    assert len(issues) == 1
    assert issues[0].paragraph_id == "p-1"
    assert issues[0].evidence_id == "ev-1"
    assert "source" in issues[0].message.lower()


def test_validation_is_run_scoped_and_does_not_accept_evidence_outside_mapping(source_map, evidence_map) -> None:
    draft = ReportDraft(
        title="Report",
        executive_summary=[],
        sections=[
            ReportSection(
                section_id="findings",
                heading="Findings",
                paragraphs=[ReportParagraph(paragraph_id="p-1", text="Fact.", evidence_ids=["ev-1"])],
            )
        ],
        limitations=[],
        suggested_actions=[],
    )
    assert validate_draft(draft, {}, source_map)[0].evidence_id == "ev-1"


def test_review_contracts_bound_verdict_and_follow_up_tasks() -> None:
    issue = ReviewIssue(message="Needs support")
    result = ReviewResult(verdict=ReviewVerdict.REVISE, blocking_issues=[issue])
    assert result.verdict is ReviewVerdict.REVISE
    with pytest.raises(ValidationError):
        ReviewResult(verdict="invalid")
