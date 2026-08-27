from collections.abc import Mapping

from pydantic import BaseModel

from deep_research.domain.evidence import EvidenceItem, Source
from deep_research.domain.review import ReportDraft, ReportParagraph


class CitationIssue(BaseModel, frozen=True):
    section_id: str | None = None
    paragraph_id: str | None = None
    evidence_id: str | None = None
    message: str


class CitationValidationError(ValueError):
    """Raised when a report draft contains an invalid evidence reference."""

    def __init__(self, issues: list[CitationIssue]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


def _paragraphs(draft: ReportDraft) -> list[tuple[str | None, ReportParagraph]]:
    paragraphs: list[tuple[str | None, ReportParagraph]] = [
        (None, paragraph) for paragraph in draft.executive_summary
    ]
    paragraphs.extend(
        (section.section_id, paragraph)
        for section in draft.sections
        for paragraph in section.paragraphs
    )
    return paragraphs


def validate_draft(
    draft: ReportDraft,
    evidence: Mapping[str, EvidenceItem],
    sources: Mapping[str, Source],
) -> list[CitationIssue]:
    issues: list[CitationIssue] = []
    for section_id, paragraph in _paragraphs(draft):
        for evidence_id in paragraph.evidence_ids:
            item = evidence.get(evidence_id)
            if item is None:
                issues.append(
                    CitationIssue(
                        section_id=section_id,
                        paragraph_id=paragraph.paragraph_id,
                        evidence_id=evidence_id,
                        message=f"Unknown evidence ID: {evidence_id}",
                    )
                )
                continue
            if item.source_id not in sources:
                issues.append(
                    CitationIssue(
                        section_id=section_id,
                        paragraph_id=paragraph.paragraph_id,
                        evidence_id=evidence_id,
                        message=f"Evidence {evidence_id} references unknown source ID: {item.source_id}",
                    )
                )
    return issues


def render_report(
    draft: ReportDraft,
    evidence: Mapping[str, EvidenceItem],
    sources: Mapping[str, Source],
) -> str:
    issues = validate_draft(draft, evidence, sources)
    if issues:
        raise CitationValidationError(issues)

    source_numbers: dict[str, int] = {}

    def render_paragraph(paragraph: ReportParagraph) -> str:
        markers: list[str] = []
        for evidence_id in paragraph.evidence_ids:
            source_id = evidence[evidence_id].source_id
            if source_id not in source_numbers:
                source_numbers[source_id] = len(source_numbers) + 1
            marker = f"[{source_numbers[source_id]}]"
            if marker not in markers:
                markers.append(marker)
        suffix = f" {' '.join(markers)}" if markers else ""
        return f"{paragraph.text}{suffix}"

    lines = [f"# {draft.title}"]
    if draft.executive_summary:
        lines.extend(["", "## Executive summary", ""])
        lines.extend(render_paragraph(paragraph) for paragraph in draft.executive_summary)
    for section in draft.sections:
        lines.extend(["", f"## {section.heading}", ""])
        lines.extend(render_paragraph(paragraph) for paragraph in section.paragraphs)
    if draft.limitations:
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {limitation}" for limitation in draft.limitations)
    if draft.suggested_actions:
        lines.extend(["", "## Suggested actions", ""])
        lines.extend(f"- {action}" for action in draft.suggested_actions)
    if source_numbers:
        lines.extend(["", "## References", ""])
        lines.extend(
            f"[{number}] {sources[source_id].title} — {sources[source_id].url}"
            for source_id, number in source_numbers.items()
        )
    return "\n".join(lines)
