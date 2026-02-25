"""Shared retry logic for transient API errors (503, 429, etc.)."""

import time


def embed_with_retry(callable_fn, retries: int = 5, initial_delay_s: float = 5.0):
    """Retry transient API failures with exponential backoff.

    Catches 429, 503, RESOURCE_EXHAUSTED, UNAVAILABLE errors and retries.
    Non-transient errors are re-raised immediately.
    """
    delay_s = initial_delay_s
    for attempt in range(retries + 1):
        try:
            return callable_fn()
        except Exception as e:
            msg = str(e).upper()
            transient_error = (
                "429" in msg
                or "RESOURCE_EXHAUSTED" in msg
                or "503" in msg
                or "UNAVAILABLE" in msg
            )
            should_retry = transient_error and attempt < retries
            if not should_retry:
                raise
            print(
                f"    retrieval transient API error (attempt {attempt + 1}/{retries}): "
                f"{type(e).__name__}; retrying in {delay_s:.1f}s"
            )
            time.sleep(delay_s)
            delay_s *= 2
