"""
LYFTR AI Chatbot - Chat Service
Multi-key LiteLLM integration with automatic failover, caching, and observability.
"""

import os
import time
import base64
import logging
from typing import Optional

from dotenv import load_dotenv, find_dotenv

# find_dotenv walks up from __file__ directory until it finds .env
load_dotenv(find_dotenv(usecwd=False))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MODEL = os.getenv("LITELLM_MODEL", "gemini/gemini-3.5-flash-lite")

# Retryable HTTP status codes (429 rate limit + 5xx server errors)
RETRYABLE_STATUSES = {429, 500, 502, 503, 504, 529}


def _load_api_keys() -> list[dict]:
    """Load API keys from LLM_API_KEYS (or single-key fallbacks)."""
    raw_keys = [k.strip() for k in os.getenv("LLM_API_KEYS", "").split(",") if k.strip()]
    if not raw_keys:
        single = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        if single.strip():
            raw_keys = [single.strip()]
    return [{"key": k, "key_id": f"key-{i + 1}"} for i, k in enumerate(raw_keys)]


API_KEYS: list[dict] = _load_api_keys()

# Round-robin counter
_rr_index = 0


def get_api_keys() -> list[dict]:
    """Return the active list of configured API key entries."""
    return API_KEYS


def reload_api_keys() -> list[dict]:
    """Reload API keys from environment variables."""
    global API_KEYS, _rr_index
    API_KEYS = _load_api_keys()
    _rr_index = 0
    return API_KEYS


def _mask_key(key: str) -> str:
    """Return a safe, non-reversible key identifier for logs."""
    return f"...{key[-4:]}" if len(key) > 4 else "***"


def _sanitize_error(message: str, keys: list[dict]) -> str:
    """Redact any raw API keys from error messages before logging or returning."""
    sanitized = message
    for entry in keys:
        raw = entry.get("key", "")
        if raw and raw in sanitized:
            sanitized = sanitized.replace(raw, f"[REDACTED:{entry['key_id']}]")
    return sanitized


def _next_key_index(num_keys: int) -> int:
    """Advance the round-robin counter and return the next index."""
    global _rr_index
    if num_keys <= 0:
        return 0
    idx = _rr_index % num_keys
    _rr_index += 1
    return idx


# ---------------------------------------------------------------------------
# LiteLLM caching setup (in-memory)
# ---------------------------------------------------------------------------

_cache_initialized = False


def ensure_cache() -> bool:
    """Enable LiteLLM's built-in in-memory response cache (once)."""
    global _cache_initialized
    if _cache_initialized:
        return True
    try:
        import litellm  # type: ignore
        litellm.cache = litellm.Cache(type="local")
        _cache_initialized = True
        logger.info("LiteLLM in-memory cache enabled.")
        return True
    except Exception as e:
        logger.warning("Could not enable LiteLLM cache: %s", e)
        return False


def is_cache_enabled() -> bool:
    """Return whether LiteLLM response caching is currently enabled."""
    return _cache_initialized


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception represents a 429, quota, or 5xx error."""
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and (status_code == 429 or 500 <= status_code < 600):
        return True

    exc_name = type(exc).__name__.lower()
    if any(name in exc_name for name in ("ratelimit", "serviceunavailable", "internalserver", "apiconnection", "timeout")):
        return True

    raw = str(exc)
    msg = raw.lower()
    for code in RETRYABLE_STATUSES:
        if str(code) in raw:
            return True

    if any(
        kw in msg
        for kw in (
            "rate limit",
            "ratelimit",
            "quota",
            "resource exhausted",
            "resource_exhausted",
            "too many requests",
            "overloaded",
            "service unavailable",
            "internal server error",
            "bad gateway",
            "gateway timeout",
        )
    ):
        return True

    return False


def _build_simulated_exception(failure_type: str) -> Exception:
    """Create a simulated retryable exception for X-Simulate-Failure."""
    ft = failure_type.lower().strip()
    if ft in ("429", "rate_limit"):
        err = Exception("Simulated 429 Too Many Requests: rate limit exceeded")
        setattr(err, "status_code", 429)
        return err
    if ft == "quota":
        err = Exception("Simulated 429 ResourceExhausted: quota exceeded")
        setattr(err, "status_code", 429)
        return err
    if ft in ("500", "502", "503", "504", "5xx", "server_error"):
        code = int(ft) if ft.isdigit() else 500
        err = Exception(f"Simulated {code} Internal Server Error")
        setattr(err, "status_code", code)
        return err
    if ft == "all_keys_fail":
        err = Exception("Simulated 503 Service Unavailable: all keys failing")
        setattr(err, "status_code", 503)
        return err
    raise RuntimeError(f"Unknown simulate-failure type: {failure_type}")


def _parse_simulate_failure(sim_header: Optional[str]) -> tuple[Optional[str], dict[str, str]]:
    """
    Parse X-Simulate-Failure header.
    Supports both simple modes ('429', '500', 'all_keys_fail') and
    per-key / wildcard mappings ('key_1=429', 'key_1=429,key_2=500', '*=429').
    Returns (legacy_mode, key_failure_map).
    """
    if not sim_header or not sim_header.strip():
        return None, {}
    raw = sim_header.strip().lower()
    if "=" not in raw:
        _build_simulated_exception(raw)
        return raw, {}

    sim_map: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise RuntimeError(f"Invalid simulate-failure entry: {part}")
        target, code = [x.strip() for x in part.split("=", 1)]
        _build_simulated_exception(code)
        norm_target = "*" if target == "*" else target.replace("_", "-")
        sim_map[norm_target] = code
    if not sim_map:
        raise RuntimeError(f"Unknown simulate-failure type: {sim_header}")
    return None, sim_map


# ---------------------------------------------------------------------------
# Core completion with failover
# ---------------------------------------------------------------------------

async def get_ai_response(
    messages: list[dict],
    model: Optional[str] = None,
    simulate_failure: Optional[str] = None,
    bypass_cache: bool = False,
) -> dict:
    """
    Send messages to LiteLLM with automatic key failover and response caching.

    Parameters
    ----------
    messages : list[dict]
        The conversation messages in OpenAI format.
    model : str | None
        LiteLLM model identifier (default from env).
    simulate_failure : str | None
        If set (e.g. via X-Simulate-Failure header), simulates a failure and
        bypasses LiteLLM cache:
        - "429" / "rate_limit" / "quota" : fail first key, failover to next
        - "500" / "502" / "503" / "5xx" / "server_error" : fail first key, failover to next
        - "all_keys_fail" : fail all keys
        - "key_1=429" / "key_1=429,key_2=500" / "*=429" : per-key or wildcard failure

    Returns
    -------
    dict with keys: content, model, resolution_source, latency_ms, input_tokens,
                    output_tokens, key_id, fallback_attempts
    """
    chosen_model = model or os.getenv("LITELLM_MODEL", DEFAULT_MODEL)
    keys = get_api_keys()

    # ----- Validate simulate_failure early if provided -----
    sim_mode, sim_map = _parse_simulate_failure(simulate_failure)
    sim_active = bool(sim_mode or sim_map)
    if sim_mode == "all_keys_fail" or (sim_active and not keys):
        exc = _build_simulated_exception(sim_mode or next(iter(sim_map.values())))
        raise RuntimeError(f"Simulated failure ({simulate_failure}): {exc}")

    # ----- No keys configured -----
    if not keys:
        logger.warning("No API keys configured.")
        raise RuntimeError(
            "No API keys configured. Set LLM_API_KEYS or GEMINI_API_KEY in your .env file."
        )

    # ----- Try LiteLLM import -----
    try:
        import litellm  # type: ignore
        from litellm import acompletion  # type: ignore
        litellm.drop_params = True
    except ImportError:
        logger.warning("LiteLLM is not installed.")
        raise RuntimeError("LiteLLM is not installed. Run `pip install litellm` and restart the server.")

    ensure_cache()

    # ----- Attempt completion with key failover -----
    start_index = 0 if sim_active else _next_key_index(len(keys))
    max_attempts = len(keys)
    last_error: Optional[Exception] = None

    for attempt in range(max_attempts):
        key_entry = keys[(start_index + attempt) % len(keys)]
        api_key = key_entry["key"]
        key_id = key_entry["key_id"]

        try:
            # Simulate failure when configured for this key / wildcard / attempt 0
            if sim_mode == "all_keys_fail" or (sim_mode and attempt == 0):
                raise _build_simulated_exception(sim_mode)
            if "*" in sim_map:
                raise _build_simulated_exception(sim_map["*"])
            if key_id in sim_map:
                raise _build_simulated_exception(sim_map[key_id])

            has_multimodal = any(isinstance(m.get("content"), list) for m in messages)
            no_cache = sim_active or bypass_cache or has_multimodal

            kwargs = {
                "model": chosen_model,
                "messages": messages,
                "api_key": api_key,
                "temperature": 0.7,
                "max_tokens": 2048,
            }
            if no_cache:
                # Simulated failures and multimodal/image requests must bypass text cache
                kwargs["cache"] = {"no-cache": True}

            start = time.perf_counter()
            response = await acompletion(**kwargs)
            latency_ms = round((time.perf_counter() - start) * 1000, 1)

            content = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
            output_tokens = getattr(usage, "completion_tokens", None) if usage else None
            input_tokens = int(input_tokens) if input_tokens is not None else 0
            output_tokens = int(output_tokens) if output_tokens is not None else 0

            hidden = getattr(response, "_hidden_params", None) or {}
            cache_hit = bool(hidden.get("cache_hit", False)) and not no_cache
            resolution_source = "LLM_CACHE" if cache_hit else "LIVE_INFERENCE"

            logger.info(
                "Completion OK — key=%s model=%s resolution_source=%s latency=%.1fms fallback_attempts=%d",
                key_id, chosen_model, resolution_source, latency_ms, attempt,
            )

            return {
                "content": content,
                "model": chosen_model,
                "resolution_source": resolution_source,
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "key_id": None if cache_hit else key_id,
                "fallback_attempts": 0 if cache_hit else attempt,
            }

        except Exception as e:
            last_error = e
            safe_err = _sanitize_error(str(e), keys)
            logger.warning(
                "Key %s failed (attempt %d/%d): %s",
                key_id, attempt + 1, max_attempts, safe_err,
            )
            if not _is_retryable(e):
                break

    error_msg = _sanitize_error(str(last_error) if last_error else "Unknown error", keys)
    logger.error("All API keys exhausted. Last error: %s", error_msg)
    raise RuntimeError(
        f"All API keys failed after {max_attempts} attempt(s). Last error: {error_msg}"
    )


IMAGE_SYSTEM_PROMPT = (
    "You are LYFTR AI's multimodal vision analyst. Describe the attached image accurately and "
    "answer the user's question based strictly on what is visible. "
    "If the image shows crops, plants, leaves, soil, or agricultural scenes: "
    "1) Identify visible crop/plant characteristics, "
    "2) Note any visible disease symptoms, pest damage, or nutrient stress (and distinguish clearly from healthy tissue), "
    "3) Only provide an estimated yield range if sufficient visual and contextual information exists, and clearly state the uncertainty and missing field data (such as acreage, cultivar, soil nutrients, and weather history). "
    "Never fabricate observations that are not visible in the image."
)


async def analyze_image_with_gemini(
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    model: Optional[str] = None,
    simulate_failure: Optional[str] = None,
) -> dict:
    """Run genuine multimodal Gemini image analysis, bypassing text response cache."""
    encoded = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"
    user_text = (prompt or "").strip() or (
        "Analyze this image in detail. If it is agricultural or shows a plant/crop, "
        "describe visible crop characteristics, any disease or stress symptoms, and "
        "whether yield can be reasonably estimated with clear uncertainty."
    )
    messages = [
        {"role": "system", "content": IMAGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]
    return await get_ai_response(
        messages,
        model=model,
        simulate_failure=simulate_failure,
        bypass_cache=True,
    )
