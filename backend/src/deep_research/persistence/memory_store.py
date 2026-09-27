from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
from pydantic import TypeAdapter

from deep_research.domain.evidence import (
    EvidenceItem,
    EvidenceSource,
    LiteratureSource,
)
from deep_research.domain.plan import ResearchBrief
from deep_research.domain.review import ReportDraft

_SOURCE_ADAPTER = TypeAdapter(EvidenceSource)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row(row: aiosqlite.Row) -> dict[str, Any]:
    return dict(row)


class MemoryStore:
    """Durable research archives and bounded recall in the checkpoint SQLite file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def _connect(self) -> aiosqlite.Connection:
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        return connection

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = await self._connect()
        try:
            await connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_archives (
                    thread_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    brief_json TEXT NOT NULL,
                    draft_json TEXT NOT NULL,
                    report TEXT NOT NULL,
                    report_hash TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    archive_status TEXT NOT NULL DEFAULT 'saved',
                    search_text TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_archives_completed
                    ON research_archives(completed_at DESC);
                CREATE TABLE IF NOT EXISTS archive_sources (
                    thread_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    published_at TEXT,
                    retrieved_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY(thread_id, source_id),
                    FOREIGN KEY(thread_id) REFERENCES research_archives(thread_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS archive_evidence (
                    thread_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    claim TEXT NOT NULL,
                    excerpt TEXT NOT NULL,
                    context TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY(thread_id, evidence_id),
                    FOREIGN KEY(thread_id, source_id)
                        REFERENCES archive_sources(thread_id, source_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS memory_cards (
                    card_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    card_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    volatility TEXT NOT NULL DEFAULT 'unknown',
                    review_after TEXT,
                    superseded_by TEXT,
                    FOREIGN KEY(thread_id) REFERENCES research_archives(thread_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_cards_thread ON memory_cards(thread_id);
                CREATE TABLE IF NOT EXISTS card_evidence (
                    card_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    PRIMARY KEY(card_id, thread_id, evidence_id),
                    FOREIGN KEY(card_id) REFERENCES memory_cards(card_id) ON DELETE CASCADE,
                    FOREIGN KEY(thread_id, evidence_id)
                        REFERENCES archive_evidence(thread_id, evidence_id) ON DELETE CASCADE
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS research_archive_fts
                    USING fts5(thread_id UNINDEXED, search_text, tokenize='trigram');
                """
            )
            await connection.commit()
        finally:
            await connection.close()

    async def archive(
        self, thread_id: str, run_id: str, state: dict[str, Any]
    ) -> None:
        report = state.get("final_report")
        if not isinstance(report, str) or not report.strip():
            raise ValueError("final report is required for archiving")
        brief = ResearchBrief.model_validate(state["research_brief"])
        draft = ReportDraft.model_validate(state["draft_report"])
        sources = {
            key: _SOURCE_ADAPTER.validate_python(value)
            for key, value in state.get("sources", {}).items()
        }
        evidence = {
            key: EvidenceItem.model_validate(value)
            for key, value in state.get("evidence", {}).items()
        }
        if any(item.source_id not in sources for item in evidence.values()):
            raise ValueError("evidence source is missing")
        paragraphs = [*draft.executive_summary]
        for section in draft.sections:
            paragraphs.extend(section.paragraphs)
        if any(evidence_id not in evidence for paragraph in paragraphs
               for evidence_id in paragraph.evidence_ids):
            raise ValueError("card evidence is missing")

        report_hash = hashlib.sha256(report.encode("utf-8")).hexdigest()
        cards: list[tuple[str, str, list[str]]] = []
        cards.extend(
            ("conclusion", paragraph.text, paragraph.evidence_ids)
            for paragraph in paragraphs if paragraph.evidence_ids
        )
        cards.extend(("limitation", text, []) for text in draft.limitations)
        for gap in state.get("gap_assessments", {}).values():
            questions = gap.missing_questions if hasattr(gap, "missing_questions") else gap.get("missing_questions", [])
            cards.extend(("open_question", text, []) for text in questions)
        cards = cards[:20]
        search_text = " ".join(
            [brief.main_question, brief.scope, brief.time_range or "",
             *brief.comparison_dimensions, draft.title, *draft.limitations,
             *(card[1] for card in cards)]
        )

        connection = await self._connect()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT report_hash FROM research_archives WHERE thread_id = ?",
                (thread_id,),
            )
            existing = await cursor.fetchone()
            if existing is not None and existing["report_hash"] == report_hash:
                await connection.rollback()
                return
            if existing is not None:
                await connection.execute(
                    "DELETE FROM research_archives WHERE thread_id = ?", (thread_id,)
                )
                await connection.execute(
                    "DELETE FROM research_archive_fts WHERE thread_id = ?", (thread_id,)
                )
            await connection.execute(
                """INSERT INTO research_archives
                   (thread_id, run_id, question, brief_json, draft_json, report,
                    report_hash, completed_at, search_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    thread_id, run_id, brief.main_question,
                    brief.model_dump_json(), draft.model_dump_json(),
                    report, report_hash, _now(), search_text,
                ),
            )
            for source in sources.values():
                if isinstance(source, LiteratureSource):
                    archive_canonical_url = ""
                    archive_published_at = None
                    archive_content_hash = ""
                else:
                    archive_canonical_url = str(source.canonical_url)
                    archive_published_at = (
                        source.published_at.isoformat() if source.published_at else None
                    )
                    archive_content_hash = source.content_hash
                await connection.execute(
                    """INSERT INTO archive_sources
                       (thread_id, source_id, canonical_url, title, published_at,
                        retrieved_at, content_hash, data_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        thread_id,
                        source.source_id,
                        archive_canonical_url,
                        source.title,
                        archive_published_at,
                        source.retrieved_at.isoformat(),
                        archive_content_hash,
                        source.model_dump_json(),
                    ),
                )
            for item in evidence.values():
                await connection.execute(
                    """INSERT INTO archive_evidence
                       (thread_id, evidence_id, task_id, source_id, claim,
                        excerpt, context, data_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        thread_id, item.evidence_id, item.task_id, item.source_id,
                        item.claim, item.excerpt, item.context, item.model_dump_json(),
                    ),
                )
            for index, (kind, body, evidence_ids) in enumerate(cards):
                card_id = hashlib.sha256(
                    f"{thread_id}:{kind}:{index}:{body}".encode()
                ).hexdigest()[:24]
                await connection.execute(
                    """INSERT INTO memory_cards
                       (card_id, thread_id, card_type, text) VALUES (?, ?, ?, ?)""",
                    (card_id, thread_id, kind, body),
                )
                for evidence_id in evidence_ids:
                    await connection.execute(
                        "INSERT INTO card_evidence VALUES (?, ?, ?)",
                        (card_id, thread_id, evidence_id),
                    )
            await connection.execute(
                "INSERT INTO research_archive_fts (thread_id, search_text) VALUES (?, ?)",
                (thread_id, search_text),
            )
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def list_archives(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        connection = await self._connect()
        try:
            cursor = await connection.execute(
                """SELECT thread_id, run_id, question, completed_at, archive_status
                   FROM research_archives ORDER BY completed_at DESC
                   LIMIT ? OFFSET ?""", (limit, offset)
            )
            return [_row(row) for row in await cursor.fetchall()]
        finally:
            await connection.close()

    async def get_archive(self, thread_id: str) -> dict[str, Any] | None:
        connection = await self._connect()
        try:
            cursor = await connection.execute(
                "SELECT * FROM research_archives WHERE thread_id = ?", (thread_id,)
            )
            archive = await cursor.fetchone()
            if archive is None:
                return None
            cursor = await connection.execute(
                "SELECT data_json FROM archive_sources WHERE thread_id = ?", (thread_id,)
            )
            sources = [json.loads(row["data_json"]) for row in await cursor.fetchall()]
            cursor = await connection.execute(
                "SELECT data_json FROM archive_evidence WHERE thread_id = ?", (thread_id,)
            )
            evidence = [json.loads(row["data_json"]) for row in await cursor.fetchall()]
            cursor = await connection.execute(
                """SELECT card_id, card_type, text, status, volatility, review_after,
                          superseded_by FROM memory_cards WHERE thread_id = ?""",
                (thread_id,),
            )
            cards = [_row(row) for row in await cursor.fetchall()]
            for card in cards:
                cursor = await connection.execute(
                    "SELECT evidence_id FROM card_evidence WHERE card_id = ?",
                    (card["card_id"],),
                )
                card["evidence_ids"] = [row["evidence_id"] for row in await cursor.fetchall()]
            result = _row(archive)
            result["brief"] = json.loads(result.pop("brief_json"))
            result["draft"] = json.loads(result.pop("draft_json"))
            result.pop("search_text")
            result["sources"] = sources
            result["evidence"] = evidence
            result["cards"] = cards
            return result
        finally:
            await connection.close()

    async def search(self, query: str, *, max_researches: int = 3,
                     max_cards: int = 5) -> dict[str, list[dict[str, Any]]]:
        terms = re.findall(r"[\w]+", query.casefold())
        if not terms:
            return {"researches": [], "cards": []}
        connection = await self._connect()
        try:
            if all(len(term) >= 3 for term in terms):
                conditions = """thread_id IN (
                    SELECT thread_id FROM research_archive_fts
                    WHERE search_text MATCH ?
                )"""
                parameters = (" OR ".join(f'"{term}"' for term in terms),)
            else:
                conditions = " OR ".join("lower(search_text) LIKE ?" for _ in terms)
                parameters = tuple(f"%{term}%" for term in terms)
            cursor = await connection.execute(
                f"""SELECT thread_id, question, completed_at, search_text
                    FROM research_archives WHERE {conditions}
                    ORDER BY completed_at DESC LIMIT 100""",
                parameters,
            )
            rows = [_row(row) for row in await cursor.fetchall()]
            rows.sort(
                key=lambda row: (
                    sum(term in row["question"].casefold() for term in terms) * 2
                    + sum(term in row["search_text"].casefold() for term in terms)
                ),
                reverse=True,
            )
            researches = [
                {key: value for key, value in row.items() if key != "search_text"}
                for row in rows[:max_researches]
            ]
            if not researches:
                return {"researches": [], "cards": []}
            ids = [item["thread_id"] for item in researches]
            placeholders = ",".join("?" for _ in ids)
            cursor = await connection.execute(
                f"""SELECT card_id, thread_id, card_type, text, status, volatility,
                           review_after FROM memory_cards
                    WHERE thread_id IN ({placeholders}) AND status = 'active'""",
                ids,
            )
            cards = [_row(row) for row in await cursor.fetchall()]
            cards.sort(key=lambda card: (
                -sum(term in card["text"].casefold() for term in terms),
                ids.index(card["thread_id"]),
            ))
            return {"researches": researches, "cards": cards[:max_cards]}
        finally:
            await connection.close()


    async def recall(self, brief: ResearchBrief) -> dict[str, list[dict[str, Any]]]:
        query = " ".join([brief.main_question, *brief.comparison_dimensions])
        found = await self.search(query)
        researches = []
        for item in found["researches"]:
            detail = await self.get_archive(item["thread_id"])
            if detail is None:
                continue
            researches.append({
                "thread_id": item["thread_id"],
                "question": item["question"][:140],
                "completed_at": item["completed_at"],
                "summary": " ".join(
                    paragraph["text"] for paragraph in detail["draft"]["executive_summary"][:2]
                )[:180],
                "limitations": [text[:120] for text in detail["draft"]["limitations"][:2]],
                "source_urls": [
                    source["canonical_url"] for source in detail["sources"]
                    if source.get("source_kind", "web") == "web"
                    and len(source["canonical_url"]) <= 240
                ][:2],
            })
        cards = [
            {
                "thread_id": item["thread_id"],
                "type": item["card_type"],
                "text": item["text"][:200],
            }
            for item in found["cards"]
        ]
        return {"researches": researches, "cards": cards}
