"""The single path to the LLM. Nothing else calls Groq directly."""
import os
import threading
import time
from collections import deque

from groq import Groq

from pii_scrubber import scrub

_client = None

# Client-side throttle. Without it, concurrent judge calls blow through the
# account's per-minute limits and most requests come back 429 and retry,
# which is slower than simply pacing them. Set these to your Groq tier.
GROQ_RPM = int(os.environ.get("GROQ_RPM", "30"))
GROQ_TPM = int(os.environ.get("GROQ_TPM", "8000"))

_window: deque = deque()  # (timestamp, tokens) of calls in the last minute
_window_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")
        # The SDK still retries the odd 429 with backoff.
        _client = Groq(api_key=key, max_retries=5)
    return _client


def _reserve(tokens: int) -> list:
    """Block until a call of ~`tokens` fits in the last-60s window, then book it."""
    while True:
        with _window_lock:
            now = time.monotonic()
            while _window and now - _window[0][0] > 60:
                _window.popleft()
            used = sum(t for _, t in _window)
            if len(_window) < GROQ_RPM and (used + tokens <= GROQ_TPM or not _window):
                entry = [now, tokens]
                _window.append(entry)
                return entry
            wait = 60 - (now - _window[0][0]) + 0.05
        time.sleep(max(wait, 0.05))


def ask(prompt: str, system: str = "", model: str = "openai/gpt-oss-120b",
        max_tokens: int = 1000, names: set[str] | None = None, **options) -> str:
    """Scrub, then send. The scrub is not optional and not skippable.

    Extra keyword options (e.g. reasoning_effort) pass through to Groq.
    """
    safe_prompt = scrub(prompt, extra_names=names)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": safe_prompt})

    # ~4 characters per token, plus the output budget.
    entry = _reserve((len(safe_prompt) + len(system)) // 4 + max_tokens)
    response = _get_client().chat.completions.create(
        model=model, max_tokens=max_tokens, messages=messages, **options,
    )
    usage = getattr(response, "usage", None)
    if usage is not None and getattr(usage, "total_tokens", None):
        with _window_lock:
            entry[1] = usage.total_tokens  # replace the estimate with what was billed
    return response.choices[0].message.content or ""
