import unittest
from unittest.mock import patch

import httpx

from app.core.config import settings
from app.services.ai_clients import EmbeddingClient, LlmClient


class EmbeddingClientTests(unittest.TestCase):
    def test_embed_retries_transient_transport_error(self):
        attempts = 0

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"embedding": [0.1, 0.2]}]}

        def post(*_args, **_kwargs):
            nonlocal attempts
            self.assertIs(_kwargs.get("trust_env"), False)
            attempts += 1
            if attempts == 1:
                raise httpx.ConnectError("ssl eof")
            return Response()

        with (
            patch.object(settings, "embedding_base_url", "https://embedding.example"),
            patch.object(settings, "embedding_api_key", "test-key"),
            patch.object(settings, "embedding_model", "embedding-test"),
            patch("app.services.ai_clients.httpx.post", side_effect=post),
        ):
            embedding = EmbeddingClient().embed("退款多久到账")

        self.assertEqual(embedding, [0.1, 0.2])
        self.assertEqual(attempts, 2)

    def test_llm_request_ignores_broken_environment_proxy(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        def post(*_args, **kwargs):
            self.assertIs(kwargs.get("trust_env"), False)
            return Response()

        with (
            patch.object(settings, "llm_base_url", "https://llm.example"),
            patch.object(settings, "llm_api_key", "test-key"),
            patch.object(settings, "llm_model", "llm-test"),
            patch("app.services.ai_clients.httpx.post", side_effect=post),
        ):
            answer = LlmClient().answer_with_context("问题", "资料")

        self.assertEqual(answer, "ok")


if __name__ == "__main__":
    unittest.main()
