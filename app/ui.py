from __future__ import annotations

import queue
import threading
from collections import deque
from dataclasses import dataclass
from tkinter import BOTH, LEFT, RIGHT, Button, Frame, Label, Message, StringVar, Tk, X, messagebox

from .config import AppConfig
from .gemini import GeminiClient
from .schemas import AssistCard, AssistRequest, TranscriptSegment
from .transcription import LoopbackTranscriber


@dataclass(slots=True)
class UiEvent:
    kind: str
    payload: object


class CaptionExplainerApp:
    def __init__(self, root: Tk, config: AppConfig) -> None:
        self.root = root
        self.config = config
        self.events: "queue.Queue[UiEvent]" = queue.Queue()
        self.transcriber: LoopbackTranscriber | None = None
        self.recent_segments: deque[TranscriptSegment] = deque(maxlen=10)
        self.partial_text = ""
        self.assist_after_id: str | None = None
        self.last_request_text = ""
        self.drag_origin_x = 0
        self.drag_origin_y = 0

        self.gemini = GeminiClient(
            api_key=config.api_key,
            model=config.gemini_model,
            timeout_seconds=config.request_timeout_seconds,
        )

        self.status_var = StringVar(value="Ready. Add a Vosk model and press Start Listening.")
        self.caption_var = StringVar(value="Live captions will appear here.")
        self.meaning_var = StringVar(value="Gemini will rewrite the recent transcript in simple English.")
        self.explanation_var = StringVar(value="Short technical explanations will appear here.")
        self.reply_var = StringVar(
            value="An honest follow-up line will appear here when the transcript needs clarification."
        )

        self.start_button: Button | None = None
        self.stop_button: Button | None = None

        self._configure_root()
        self._build_ui()
        self._bind_shortcuts()
        self.root.after(120, self._process_events)

    def _configure_root(self) -> None:
        self.root.title("Live Caption + Simple Explanation")
        self.root.geometry(f"{self.config.initial_width}x{self.config.initial_height}")
        self.root.minsize(480, 620)
        self.root.configure(bg="#f4efe6")
        self.root.attributes("-topmost", True)
        self.snap_below_camera()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self) -> None:
        palette = {
            "bg": "#f4efe6",
            "panel": "#fffdf8",
            "ink": "#1f2933",
            "muted": "#5f6c7b",
            "accent": "#0f5d73",
            "accent_soft": "#d8eaf0",
            "warning": "#8a3b12",
            "warning_bg": "#ffe9da",
        }

        header = Frame(self.root, bg=palette["bg"], padx=18, pady=16)
        header.pack(fill=X)
        header.bind("<ButtonPress-1>", self._start_drag)
        header.bind("<B1-Motion>", self._drag_window)

        title = Label(
            header,
            text="Live Caption + Simple Explanation",
            bg=palette["bg"],
            fg=palette["ink"],
            font=("Segoe UI Semibold", 18),
        )
        title.pack(anchor="w")
        title.bind("<ButtonPress-1>", self._start_drag)
        title.bind("<B1-Motion>", self._drag_window)

        subtitle = Label(
            header,
            text="Built for visible accessibility support during technical meetings.",
            bg=palette["bg"],
            fg=palette["muted"],
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(4, 0))
        subtitle.bind("<ButtonPress-1>", self._start_drag)
        subtitle.bind("<B1-Motion>", self._drag_window)

        warning = Frame(self.root, bg=palette["warning_bg"], padx=18, pady=10)
        warning.pack(fill=X, padx=18)
        Label(
            warning,
            text="Share only a browser tab or app window if you present. Full-screen sharing will show this app.",
            bg=palette["warning_bg"],
            fg=palette["warning"],
            font=("Segoe UI Semibold", 10),
            wraplength=480,
            justify=LEFT,
        ).pack(anchor="w")

        controls = Frame(self.root, bg=palette["bg"], padx=18, pady=14)
        controls.pack(fill=X)

        self.start_button = Button(
            controls,
            text="Start Listening",
            command=self.start_listening,
            bg=palette["accent"],
            fg="white",
            activebackground="#0a4a5b",
            activeforeground="white",
            relief="flat",
            padx=14,
            pady=8,
        )
        self.start_button.pack(side=LEFT)

        self.stop_button = Button(
            controls,
            text="Stop",
            command=self.stop_listening,
            bg="#d0d7de",
            fg=palette["ink"],
            activebackground="#bcc6d0",
            relief="flat",
            padx=14,
            pady=8,
            state="disabled",
        )
        self.stop_button.pack(side=LEFT, padx=(10, 0))

        Button(
            controls,
            text="Snap Below Camera",
            command=self.snap_below_camera,
            bg=palette["panel"],
            fg=palette["ink"],
            relief="groove",
            padx=14,
            pady=8,
        ).pack(side=RIGHT)

        Button(
            controls,
            text="Clear",
            command=self.clear_panels,
            bg=palette["panel"],
            fg=palette["ink"],
            relief="groove",
            padx=14,
            pady=8,
        ).pack(side=RIGHT, padx=(0, 10))

        status_bar = Label(
            self.root,
            textvariable=self.status_var,
            bg=palette["bg"],
            fg=palette["muted"],
            font=("Segoe UI", 10),
            padx=18,
            pady=2,
            justify=LEFT,
            wraplength=500,
        )
        status_bar.pack(fill=X)

        cards = Frame(self.root, bg=palette["bg"], padx=18, pady=12)
        cards.pack(fill=BOTH, expand=True)

        self._build_card(cards, "Live Caption", self.caption_var, palette["panel"], palette["ink"], 520)
        self._build_card(cards, "Simple English", self.meaning_var, palette["accent_soft"], palette["ink"], 520)
        self._build_card(cards, "Technical Explanation", self.explanation_var, palette["panel"], palette["ink"], 520)
        self._build_card(cards, "Honest Follow-up Line", self.reply_var, palette["accent_soft"], palette["ink"], 520)

        footer_text = "Ctrl+L start/stop | Ctrl+K clear | Esc close"
        if self.config.vosk_model_path:
            footer_text += f" | Model: {self.config.vosk_model_path.name}"
        else:
            footer_text += " | Model: missing"

        Label(
            self.root,
            text=footer_text,
            bg=palette["bg"],
            fg=palette["muted"],
            font=("Segoe UI", 9),
            padx=18,
            pady=10,
            wraplength=520,
            justify=LEFT,
        ).pack(fill=X)

    def _build_card(
        self,
        parent: Frame,
        title: str,
        variable: StringVar,
        background: str,
        foreground: str,
        width: int,
    ) -> None:
        card = Frame(parent, bg=background, bd=0, highlightthickness=0, padx=16, pady=14)
        card.pack(fill=X, pady=(0, 12))

        Label(
            card,
            text=title,
            bg=background,
            fg="#0f5d73",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w")

        Message(
            card,
            textvariable=variable,
            bg=background,
            fg=foreground,
            font=("Segoe UI", 11),
            width=width,
            justify=LEFT,
        ).pack(anchor="w", pady=(8, 0))

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-l>", lambda _event: self.toggle_listening())
        self.root.bind("<Control-k>", lambda _event: self.clear_panels())
        self.root.bind("<Escape>", lambda _event: self.close())

    def _start_drag(self, event) -> None:
        self.drag_origin_x = event.x_root - self.root.winfo_x()
        self.drag_origin_y = event.y_root - self.root.winfo_y()

    def _drag_window(self, event) -> None:
        x_pos = event.x_root - self.drag_origin_x
        y_pos = event.y_root - self.drag_origin_y
        self.root.geometry(f"+{x_pos}+{y_pos}")

    def snap_below_camera(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_width() or self.config.initial_width
        x_pos = int((self.root.winfo_screenwidth() - width) / 2)
        y_pos = 36
        self.root.geometry(f"+{x_pos}+{y_pos}")

    def toggle_listening(self) -> None:
        if self.transcriber:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self) -> None:
        if self.transcriber:
            return
        if not self.config.vosk_model_path:
            messagebox.showerror(
                "Missing Vosk Model",
                "Add an extracted Vosk English model folder under models/ or set VOSK_MODEL_PATH in .env first.",
            )
            return

        self.transcriber = LoopbackTranscriber(
            model_path=self.config.vosk_model_path,
            sample_rate=self.config.sample_rate,
            block_size=self.config.block_size,
        )
        self.transcriber.start(
            on_partial=lambda text: self.events.put(UiEvent("partial", text)),
            on_final=lambda segment: self.events.put(UiEvent("final", segment)),
            on_status=lambda text: self.events.put(UiEvent("status", text)),
            on_error=lambda text: self.events.put(UiEvent("error", text)),
        )
        self.status_var.set("Starting loopback capture...")
        if self.start_button:
            self.start_button.config(state="disabled")
        if self.stop_button:
            self.stop_button.config(state="normal")

    def stop_listening(self) -> None:
        if not self.transcriber:
            return
        self.transcriber.stop()
        self.transcriber = None
        self.status_var.set("Stopped.")
        if self.start_button:
            self.start_button.config(state="normal")
        if self.stop_button:
            self.stop_button.config(state="disabled")

    def clear_panels(self) -> None:
        self.partial_text = ""
        self.recent_segments.clear()
        self.last_request_text = ""
        self.caption_var.set("Live captions will appear here.")
        self.meaning_var.set("Gemini will rewrite the recent transcript in simple English.")
        self.explanation_var.set("Short technical explanations will appear here.")
        self.reply_var.set(
            "An honest follow-up line will appear here when the transcript needs clarification."
        )
        self.status_var.set("Cleared.")

    def _render_caption(self) -> None:
        final_text = " ".join(segment.text for segment in self.recent_segments)
        display = final_text.strip()
        if self.partial_text:
            display = f"{display}\n\nLive: {self.partial_text}".strip()
        self.caption_var.set(display or "Listening for speech...")

    def _schedule_explanation(self) -> None:
        if self.assist_after_id:
            self.root.after_cancel(self.assist_after_id)
        self.assist_after_id = self.root.after(self.config.explanation_debounce_ms, self._request_explanation)

    def _request_explanation(self) -> None:
        transcript = self._build_recent_transcript()
        if not transcript or transcript == self.last_request_text:
            return

        self.last_request_text = transcript
        self.status_var.set("Generating simple explanation...")
        request = AssistRequest(recent_transcript=transcript)

        def worker() -> None:
            card = self.gemini.generate_explanation(request)
            self.events.put(UiEvent("assist", card))

        threading.Thread(target=worker, daemon=True).start()

    def _build_recent_transcript(self) -> str:
        collected: list[str] = []
        total = 0
        for segment in reversed(self.recent_segments):
            segment_text = segment.text.strip()
            if not segment_text:
                continue
            total += len(segment_text)
            if total > self.config.transcript_context_limit and collected:
                break
            collected.append(segment_text)
        return " ".join(reversed(collected))

    def _handle_assist(self, card: AssistCard) -> None:
        self.meaning_var.set(card.simple_english)
        self.explanation_var.set(card.technical_explanation)
        self.reply_var.set(card.clarifying_reply)
        if card.fallback_mode == "live":
            self.status_var.set(f"Updated explanation. Confidence: {card.confidence:.2f}")
        else:
            self.status_var.set(card.technical_explanation)

    def _process_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event.kind == "partial":
                    self.partial_text = str(event.payload or "")
                    self._render_caption()
                elif event.kind == "final":
                    segment = event.payload
                    if isinstance(segment, TranscriptSegment):
                        self.partial_text = ""
                        self.recent_segments.append(segment)
                        self._render_caption()
                        self._schedule_explanation()
                elif event.kind == "assist" and isinstance(event.payload, AssistCard):
                    self._handle_assist(event.payload)
                elif event.kind == "status":
                    self.status_var.set(str(event.payload))
                elif event.kind == "error":
                    self.status_var.set(f"Error: {event.payload}")
                    self.stop_listening()
                    messagebox.showerror("Live Caption Error", str(event.payload))
        except queue.Empty:
            pass
        finally:
            self.root.after(120, self._process_events)

    def close(self) -> None:
        self.stop_listening()
        self.root.destroy()
