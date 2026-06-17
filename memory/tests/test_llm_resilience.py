"""
Unit tests for the resilient harvest LLM client (src/pipeline/llm_client.py).

Pure logic — no network. Guards the retry classifier and backoff math that keep
a long harvest from stalling on a transient provider error.
"""

import pytest

from src.pipeline import llm_client as lc


class TestRetryClassification:
    @pytest.mark.parametrize("msg", [
        "litellm.RateLimitError: 429 Too Many Requests",
        "Error: rate limit exceeded, please slow down",
        "RESOURCE_EXHAUSTED: quota",
        "The model is overloaded. Please try again later.",
        "503 Service Unavailable",
        "502 Bad Gateway",
        "Read timed out.",
        "connection reset by peer",
        "Internal Server Error",
    ])
    def test_transient_errors_retry(self, msg):
        assert lc._is_retryable(Exception(msg)) is True

    @pytest.mark.parametrize("msg", [
        "400 Bad Request: invalid 'messages' field",
        "AuthenticationError: incorrect API key provided",
        "This model's maximum context length is 128000 tokens",
        "PermissionDenied: model not available to your account",
    ])
    def test_permanent_errors_do_not_retry(self, msg):
        assert lc._is_retryable(Exception(msg)) is False

    def test_status_code_attribute_is_respected(self):
        e429 = Exception("opaque"); e429.status_code = 429
        e400 = Exception("opaque"); e400.status_code = 400
        assert lc._is_retryable(e429) is True
        assert lc._is_retryable(e400) is False


class TestServerSuggestedDelay:
    def test_parses_gemini_retry_delay_seconds(self):
        assert lc._server_suggested_delay(Exception('"retryDelay": "37s"')) == 37.0

    def test_parses_retry_after_header(self):
        assert lc._server_suggested_delay(Exception("Retry-After: 12")) == 12.0

    def test_parses_milliseconds(self):
        assert lc._server_suggested_delay(Exception("retryDelay: 500ms")) == 0.5

    def test_clamped_to_max(self):
        assert lc._server_suggested_delay(Exception("retryDelay: 99999s")) == lc.LLM_RETRY_MAX_DELAY

    def test_none_when_no_hint(self):
        assert lc._server_suggested_delay(Exception("generic failure")) is None


class TestBackoff:
    def test_backoff_within_bounds(self):
        # Full-jitter backoff must always stay within [0, ceiling] and never
        # explode as the attempt count grows.
        for attempt in range(1, 8):
            d = lc._backoff_delay(attempt)
            assert 0.0 <= d <= lc.LLM_RETRY_MAX_DELAY
