from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(slots=True)
class TranscriptSegment:
    id: str
    text: str
    started_at: datetime
    ended_at: datetime
    confidence: float

    @classmethod
    def create(cls, text: str, confidence: float, started_at: datetime, ended_at: datetime) -> "TranscriptSegment":
        return cls(
            id=str(uuid4()),
            text=text.strip(),
            started_at=started_at,
            ended_at=ended_at,
            confidence=max(0.0, min(confidence, 1.0)),
        )


@dataclass(slots=True)
class AssistRequest:
    recent_transcript: str
    domain_hint: str = "software engineering meeting"
    response_style: str = "plain English explanation for a non-native speaker"


@dataclass(slots=True)
class AssistCard:
    simple_english: str
    technical_explanation: str
    clarifying_reply: str
    confidence: float
    fallback_mode: str = "live"
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
