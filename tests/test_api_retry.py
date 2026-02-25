"""Tests for API retry logic used by embedding and LLM calls."""

import time
import unittest


class TestEmbedWithRetry(unittest.TestCase):
    """Test the embed_with_retry wrapper."""

    def test_succeeds_on_first_try(self):
        from src.api_retry import embed_with_retry

        call_count = 0

        def fake_embed():
            nonlocal call_count
            call_count += 1
            return {"embeddings": [1, 2, 3]}

        result = embed_with_retry(fake_embed, retries=3, initial_delay_s=0.01)
        self.assertEqual(result, {"embeddings": [1, 2, 3]})
        self.assertEqual(call_count, 1)

    def test_retries_on_503(self):
        from src.api_retry import embed_with_retry

        call_count = 0

        def fake_embed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("503 The service is currently unavailable.")
            return {"ok": True}

        result = embed_with_retry(fake_embed, retries=5, initial_delay_s=0.01)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(call_count, 3)

    def test_retries_on_429_resource_exhausted(self):
        from src.api_retry import embed_with_retry

        call_count = 0

        def fake_embed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return {"ok": True}

        result = embed_with_retry(fake_embed, retries=3, initial_delay_s=0.01)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(call_count, 2)

    def test_raises_permanent_error(self):
        from src.api_retry import embed_with_retry

        def fake_embed():
            raise ValueError("Invalid argument: bad config")

        with self.assertRaises(ValueError):
            embed_with_retry(fake_embed, retries=3, initial_delay_s=0.01)

    def test_raises_after_max_retries(self):
        from src.api_retry import embed_with_retry

        def fake_embed():
            raise RuntimeError("503 UNAVAILABLE forever")

        with self.assertRaises(RuntimeError):
            embed_with_retry(fake_embed, retries=2, initial_delay_s=0.01)

    def test_exponential_backoff(self):
        from src.api_retry import embed_with_retry

        call_count = 0
        timestamps = []

        def fake_embed():
            nonlocal call_count
            call_count += 1
            timestamps.append(time.monotonic())
            if call_count < 3:
                raise RuntimeError("503 UNAVAILABLE")
            return {"ok": True}

        embed_with_retry(fake_embed, retries=5, initial_delay_s=0.05)
        self.assertEqual(call_count, 3)
        # Second delay should be roughly 2x the first
        delay1 = timestamps[1] - timestamps[0]
        delay2 = timestamps[2] - timestamps[1]
        self.assertGreater(delay2, delay1 * 1.5)  # allow some slack


if __name__ == "__main__":
    unittest.main()
