from __future__ import annotations

import json
import time
from typing import Any

import requests

from .schemas import AssistCard, AssistRequest

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0


class GeminiError(RuntimeError):
    """Raised when Gemini returns an invalid response."""


def build_prompt(request: AssistRequest) -> str:
    return (
        "You help a developer understand spoken English during a live technical meeting.\n"
        "Rewrite the transcript in simple English, explain the likely technical meaning briefly, "
        "and give one honest follow-up line the user can say if they want to confirm understanding.\n"
        "Return only JSON with these keys:\n"
        "simple_english: string\n"
        "technical_explanation: string\n"
        "clarifying_reply: string\n"
        "confidence: number from 0 to 1\n"
        "Rules:\n"
        "- Be truthful and do not invent project details or experience.\n"
        "- If the transcript is unclear, say that plainly and lower confidence.\n"
        "- Keep technical_explanation to 2 or 3 short sentences.\n"
        "- Keep clarifying_reply to 1 short sentence.\n"
        "- No markdown.\n"
        f"Context: {request.domain_hint}\n"
        f"Style: {request.response_style}\n"
        f"Transcript:\n{request.recent_transcript.strip()}"
    )


def extract_candidate_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise GeminiError("Gemini returned no candidates.")

    parts = candidates[0].get("content", {}).get("parts", [])
    text_chunks = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")]
    text = "".join(text_chunks).strip()
    if not text:
        raise GeminiError("Gemini returned an empty text response.")
    return text


def strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    return cleaned


def parse_assist_text(text: str) -> dict[str, Any]:
    cleaned = strip_json_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise GeminiError("Gemini did not return a JSON object.")

    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise GeminiError("Gemini returned malformed JSON.") from exc


def normalize_assist_card(data: dict[str, Any], transcript: str, fallback_mode: str = "live") -> AssistCard:
    simple_english = str(data.get("simple_english", "")).strip() or transcript.strip()
    technical_explanation = str(data.get("technical_explanation", "")).strip() or (
        "This sounds like a technical question, but the explanation service did not return a full summary."
    )
    clarifying_reply = str(data.get("clarifying_reply", "")).strip() or (
        "Could you please repeat that a bit more slowly so I can make sure I understood you?"
    )

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return AssistCard(
        simple_english=simple_english,
        technical_explanation=technical_explanation,
        clarifying_reply=clarifying_reply,
        confidence=max(0.0, min(confidence, 1.0)),
        fallback_mode=fallback_mode,
    )


def build_fallback_card(transcript: str, reason: str) -> AssistCard:
    return AssistCard(
        simple_english=transcript.strip() or "No transcript available yet.",
        technical_explanation=reason,
        clarifying_reply="Could you please repeat that in a simpler way so I can respond accurately?",
        confidence=0.0,
        fallback_mode="fallback",
    )


class GeminiClient:
    def __init__(
        self,
        api_key: str | None,
        model: str = "gemini-2.0-flash",
        timeout_seconds: float = 12.0,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    @property
    def endpoint(self) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    def generate_explanation(self, request: AssistRequest) -> AssistCard:
        transcript = request.recent_transcript.strip()
        if not transcript:
            return build_fallback_card("", "Waiting for enough transcript text to explain.")

        if not self.api_key:
            return build_fallback_card(
                transcript,
                "Gemini is not configured yet. Add GEMINI_API_KEY to your local .env file for explanations.",
            )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": build_prompt(request)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.9,
                "maxOutputTokens": 240,
                "responseMimeType": "application/json",
            },
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )

                # If rate-limited, wait and retry
                if response.status_code == 429:
                    wait = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                    time.sleep(wait)
                    last_exc = requests.HTTPError(
                        f"Rate limited (429). Retried {attempt + 1}/{MAX_RETRIES}, waited {wait:.1f}s.",
                        response=response,
                    )
                    continue

                response.raise_for_status()
                model_text = extract_candidate_text(response.json())
                parsed = parse_assist_text(model_text)
                return normalize_assist_card(parsed, transcript, fallback_mode="live")

            except (requests.RequestException, GeminiError, ValueError) as exc:
                last_exc = exc
                # Only retry on rate-limit; break on other errors
                break

        return build_fallback_card(
            transcript,
            f"Gemini is temporarily unavailable. Showing the transcript only. Details: {last_exc}",
        )
