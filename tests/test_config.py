from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import discover_vosk_model, load_config


class ConfigTests(unittest.TestCase):
    def test_discover_vosk_model_finds_first_model_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            models_dir = Path(temp_dir) / "models"
            models_dir.mkdir()
            expected = models_dir / "vosk-model-small-en-us-0.15"
            expected.mkdir()

            discovered = discover_vosk_model(models_dir)
            self.assertEqual(discovered, expected)

    def test_load_config_resolves_relative_model_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = root / "models" / "vosk-model-small-en-us-0.15"
            model_dir.mkdir(parents=True)

            with patch.dict(
                os.environ,
                {
                    "GEMINI_API_KEY": "test-key",
                    "VOSK_MODEL_PATH": "models/vosk-model-small-en-us-0.15",
                    "GEMINI_MODEL": "gemini-2.5-flash",
                },
                clear=False,
            ):
                config = load_config(root)

            self.assertEqual(config.api_key, "test-key")
            self.assertEqual(config.vosk_model_path, model_dir.resolve())


if __name__ == "__main__":
    unittest.main()
