from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class AppConfig:
    base_dir: Path
    api_key: str | None
    gemini_model: str
    vosk_model_path: Path | None
    sample_rate: int
    block_size: int
    explanation_debounce_ms: int
    transcript_context_limit: int
    request_timeout_seconds: float
    initial_width: int
    initial_height: int


def discover_vosk_model(models_dir: Path) -> Path | None:
    if not models_dir.exists():
        return None

    candidates = sorted(
        path for path in models_dir.iterdir() if path.is_dir() and path.name.startswith("vosk-model")
    )
    return candidates[0] if candidates else None


def load_config(base_dir: Path | None = None) -> AppConfig:
    root = base_dir or Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")

    raw_model_path = os.getenv("VOSK_MODEL_PATH", "").strip()
    vosk_model_path = Path(raw_model_path) if raw_model_path else discover_vosk_model(root / "models")
    if vosk_model_path and not vosk_model_path.is_absolute():
        vosk_model_path = (root / vosk_model_path).resolve()

    api_key = os.getenv("GEMINI_API_KEY", "").strip() or None

    return AppConfig(
        base_dir=root,
        api_key=api_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash",
        vosk_model_path=vosk_model_path,
        sample_rate=int(os.getenv("CAPTION_SAMPLE_RATE", "16000")),
        block_size=int(os.getenv("CAPTION_BLOCK_SIZE", "4096")),
        explanation_debounce_ms=int(os.getenv("EXPLANATION_DEBOUNCE_MS", "1400")),
        transcript_context_limit=int(os.getenv("TRANSCRIPT_CONTEXT_LIMIT", "700")),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "12")),
        initial_width=int(os.getenv("WINDOW_WIDTH", "560")),
        initial_height=int(os.getenv("WINDOW_HEIGHT", "760")),
    )
