from __future__ import annotations

import unittest

from app.gemini import extract_candidate_text, normalize_assist_card, parse_assist_text


class GeminiParsingTests(unittest.TestCase):
    def test_parse_assist_text_accepts_plain_json(self) -> None:
        parsed = parse_assist_text(
            '{"simple_english":"It is asking about APIs.","technical_explanation":"An API is a contract.","clarifying_reply":"Do you mean a REST API?","confidence":0.8}'
        )
        self.assertEqual(parsed["simple_english"], "It is asking about APIs.")

    def test_parse_assist_text_accepts_fenced_json(self) -> None:
        parsed = parse_assist_text(
            '```json\n{"simple_english":"Short text","technical_explanation":"Clear","clarifying_reply":"Please repeat","confidence":0.4}\n```'
        )
        self.assertEqual(parsed["confidence"], 0.4)

    def test_extract_candidate_text_joins_text_parts(self) -> None:
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": '{"simple_english":"Hello",'},
                            {"text": '"technical_explanation":"World","clarifying_reply":"Ok","confidence":0.7}'},
                        ]
                    }
                }
            ]
        }
        self.assertIn('"confidence":0.7', extract_candidate_text(payload))

    def test_normalize_assist_card_clamps_confidence(self) -> None:
        card = normalize_assist_card(
            {
                "simple_english": "Easy wording",
                "technical_explanation": "It asks about composition.",
                "clarifying_reply": "Are you comparing it with inheritance?",
                "confidence": 3,
            },
            "raw transcript",
        )
        self.assertEqual(card.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
