import os
import unittest
from unittest.mock import patch

from app.core.config import Settings


class SettingsTests(unittest.TestCase):
    def test_ai_provider_settings_are_read_from_environment(self):
        env = {
            "LLM_BASE_URL": "https://llm.example/v1",
            "LLM_API_KEY": "test-llm-key",
            "LLM_TEMPERATURE": "0.2",
            "LLM_TOP_P": "0.8",
            "EMBEDDING_BASE_URL": "https://embedding.example/v1",
            "EMBEDDING_API_KEY": "test-embedding-key",
            "EMBEDDING_MODEL": "text-embedding-test",
            "RETRIEVAL_TOP_K": "4",
            "RETRIEVAL_MIN_SCORE": "0.12",
            "HYBRID_DENSE_WEIGHT": "0.65",
            "HYBRID_SPARSE_WEIGHT": "0.35",
        }

        with patch.dict(os.environ, env, clear=False):
            settings = Settings()

        self.assertEqual(settings.llm_base_url, env["LLM_BASE_URL"])
        self.assertEqual(settings.llm_api_key, env["LLM_API_KEY"])
        self.assertEqual(settings.llm_temperature, 0.2)
        self.assertEqual(settings.llm_top_p, 0.8)
        self.assertEqual(settings.embedding_base_url, env["EMBEDDING_BASE_URL"])
        self.assertEqual(settings.embedding_api_key, env["EMBEDDING_API_KEY"])
        self.assertEqual(settings.embedding_model, env["EMBEDDING_MODEL"])
        self.assertEqual(settings.retrieval_top_k, 4)
        self.assertEqual(settings.retrieval_min_score, 0.12)
        self.assertEqual(settings.hybrid_dense_weight, 0.65)
        self.assertEqual(settings.hybrid_sparse_weight, 0.35)


if __name__ == "__main__":
    unittest.main()
