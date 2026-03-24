from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundcard as sc
from vosk import KaldiRecognizer, Model

from .schemas import TranscriptSegment

PartialCallback = Callable[[str], None]
FinalCallback = Callable[[TranscriptSegment], None]
StatusCallback = Callable[[str], None]
ErrorCallback = Callable[[str], None]


def _pcm16_bytes(audio_block: np.ndarray) -> bytes:
    if audio_block.ndim > 1:
        audio_block = audio_block.mean(axis=1)
    samples = np.clip(audio_block, -1.0, 1.0)
    return (samples * 32767).astype(np.int16).tobytes()


def _confidence_from_result(result_payload: dict) -> float:
    words = result_payload.get("result") or []
    confidences = [float(word.get("conf", 0.0)) for word in words if isinstance(word, dict)]
    if confidences:
        return sum(confidences) / len(confidences)
    return 0.0


class LoopbackTranscriber:
    def __init__(self, model_path: Path, sample_rate: int = 16000, block_size: int = 4096) -> None:
        self.model_path = Path(model_path)
        self.sample_rate = sample_rate
        self.block_size = block_size
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(
        self,
        on_partial: PartialCallback,
        on_final: FinalCallback,
        on_status: StatusCallback,
        on_error: ErrorCallback,
    ) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(on_partial, on_final, on_status, on_error),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def _run(
        self,
        on_partial: PartialCallback,
        on_final: FinalCallback,
        on_status: StatusCallback,
        on_error: ErrorCallback,
    ) -> None:
        try:
            if not self.model_path.exists():
                raise FileNotFoundError(f"Vosk model folder not found: {self.model_path}")

            model = Model(str(self.model_path))
            recognizer = KaldiRecognizer(model, self.sample_rate)
            recognizer.SetWords(True)

            speaker = sc.default_speaker()
            if speaker is None:
                raise RuntimeError("No default speaker output device is available.")

            microphone = sc.get_microphone(id=str(speaker.name), include_loopback=True)
            if microphone is None:
                raise RuntimeError("Could not open loopback audio for the default speaker.")

            on_status(f"Listening to system audio from: {speaker.name}")
            segment_started = datetime.now(timezone.utc)

            with microphone.recorder(
                samplerate=self.sample_rate,
                channels=1,
                blocksize=self.block_size,
            ) as recorder:
                while not self._stop_event.is_set():
                    audio_block = recorder.record(numframes=self.block_size)
                    if audio_block.size == 0:
                        time.sleep(0.05)
                        continue

                    if recognizer.AcceptWaveform(_pcm16_bytes(audio_block)):
                        result_payload = json.loads(recognizer.Result())
                        final_text = str(result_payload.get("text", "")).strip()
                        if final_text:
                            ended_at = datetime.now(timezone.utc)
                            on_final(
                                TranscriptSegment.create(
                                    text=final_text,
                                    confidence=_confidence_from_result(result_payload),
                                    started_at=segment_started,
                                    ended_at=ended_at,
                                )
                            )
                            segment_started = ended_at
                    else:
                        partial_payload = json.loads(recognizer.PartialResult())
                        partial_text = str(partial_payload.get("partial", "")).strip()
                        on_partial(partial_text)

            on_status("Listening stopped.")
        except Exception as exc:  # noqa: BLE001
            on_error(str(exc))
