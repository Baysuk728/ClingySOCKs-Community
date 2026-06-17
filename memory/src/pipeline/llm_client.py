"""
Resilient LLM client wrapper for the harvest pipeline.

Every pipeline pass (narrative, data, echo, synthesis, factual, edges) routes
its `litellm.acompletion` calls through `acompletion()` here so they all share:

  • a hard per-call timeout       — a hung request can't freeze the pipeline
  • retry with exponential backoff — transient 429 / 5xx / timeout self-heal
  • a global throttle             — calls stay SEQUENTIAL and spaced out so a
                                    long harvest (many chunks × passes) doesn't
                                    burst dozens of requests at the provider and
                                    trip rate limits

The throttle is deliberately conservative (concurrency of 1 + an optional
minimum gap between calls) because the harvest pipeline makes many calls back
to back. Tune via env vars (see src/config.py): LLM_TIMEOUT_SECONDS,
LLM_MAX_RETRIES, LLM_MAX_CONCURRENCY, LLM_MIN_REQUEST_INTERVAL,
LLM_RETRY_BASE_DELAY, LLM_RETRY_MAX_DELAY.

This is a drop-in replacement for `litellm.acompletion`: callers may pass
`timeout` / `num_retries` per call (the pipeline passes already compute a
per-model timeout via get_llm_timeout) and they are respected; otherwise the
configured defaults apply.
"""

import asyncio
import random
import re
import time

import litellm

from src.config import (
    LLM_TIMEOUT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_MAX_CONCURRENCY,
    LLM_MIN_REQUEST_INTERVAL,
    LLM_RETRY_BASE_DELAY,
    LLM_RETRY_MAX_DELAY,
)

# Bound how many harvest LLM calls can be in flight at once. Default 1 keeps the
# pipeline strictly sequential — important for staying under provider rate
# limits when chunking a long conversation into many calls.
_semaphore = asyncio.Semaphore(max(1, LLM_MAX_CONCURRENCY))

# Serialize the "space out requests" bookkeeping so concurrent callers (if
# LLM_MAX_CONCURRENCY > 1) still respect the minimum interval between launches.
_rate_lock = asyncio.Lock()
_last_call_monotonic = 0.0

# Status codes worth retrying — transient server/rate-limit conditions.
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

# Substrings that mark an error as transient even when no status code is exposed
# (LiteLLM wraps provider errors inconsistently across Gemini/OpenAI/OpenRouter).
_RETRYABLE_MARKERS = (
    "429", "rate limit", "ratelimit", "resource exhausted", "quota",
    "overloaded", "is overloaded", "try again", "temporarily unavailable",
    "timeout", "timed out", "deadline", "connection reset", "connection error",
    "502", "503", "504", "service unavailable", "internal server error",
)

# Pull a server-suggested delay out of an error message when present
# (e.g. Gemini "retryDelay": "37s", or a generic "Retry-After: 12").
_RETRY_DELAY_RE = re.compile(
    r"(?:retry[-_ ]?after|retrydelay)\D{0,12}?(\d+(?:\.\d+)?)\s*(m?s|s)?",
    re.IGNORECASE,
)


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    try:
        if status is not None and int(status) in _RETRYABLE_STATUS:
            return True
    except (TypeError, ValueError):
        pass
    msg = str(exc).lower()
    return any(marker in msg for marker in _RETRYABLE_MARKERS)


def _server_suggested_delay(exc: Exception) -> float | None:
    m = _RETRY_DELAY_RE.search(str(exc))
    if not m:
        return None
    try:
        value = float(m.group(1))
    except (TypeError, ValueError):
        return None
    unit = (m.group(2) or "s").lower()
    if unit == "ms":
        value /= 1000.0
    # Clamp absurd server hints so one bad header can't stall the run for minutes.
    return min(value, LLM_RETRY_MAX_DELAY)


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with full jitter. attempt is 1-based."""
    raw = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
    capped = min(raw, LLM_RETRY_MAX_DELAY)
    return random.uniform(0, capped)


async def _throttle() -> None:
    """Block until at least LLM_MIN_REQUEST_INTERVAL has passed since the last launch."""
    global _last_call_monotonic
    if LLM_MIN_REQUEST_INTERVAL <= 0:
        return
    async with _rate_lock:
        now = time.monotonic()
        wait = LLM_MIN_REQUEST_INTERVAL - (now - _last_call_monotonic)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_monotonic = time.monotonic()


async def acompletion(**kwargs):
    """Drop-in replacement for `litellm.acompletion` with timeout, retry and throttle.

    Accepts the same kwargs as `litellm.acompletion`. `timeout` and
    `num_retries` may be overridden per-call; otherwise the configured defaults
    apply. Retries only transient failures — a malformed-request (4xx other than
    429) raises immediately so we don't loop on a real bug.
    """
    timeout = kwargs.pop("timeout", LLM_TIMEOUT_SECONDS)
    max_retries = kwargs.pop("num_retries", LLM_MAX_RETRIES)

    attempt = 0
    while True:
        await _throttle()
        try:
            async with _semaphore:
                return await litellm.acompletion(timeout=timeout, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — classify below
            attempt += 1
            if attempt > max_retries or not _is_retryable(exc):
                raise
            delay = _server_suggested_delay(exc)
            if delay is None:
                delay = _backoff_delay(attempt)
            print(
                f"    ⏳ LLM call transient failure (attempt {attempt}/{max_retries}): "
                f"{str(exc)[:140]} — retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
