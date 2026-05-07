"""
LLM client — NVIDIA free API (OpenAI-compatible) with graceful fallback.

If NVIDIA_API_KEY is not set or the API fails, returns None so callers
can fall back to hardcoded templates.
"""

import json
import logging
from config import NVIDIA_API_KEY, NVIDIA_MODEL, NVIDIA_BASE_URL

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0


def llm_generate(prompt: str, system: str = "", temperature: float = 0.8, max_tokens: int = 600) -> str | None:
    """Call the NVIDIA LLM API. Returns the response text, or None on failure."""
    if not NVIDIA_API_KEY:
        return None

    try:
        resp = httpx.post(
            f"{NVIDIA_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": NVIDIA_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("[llm_client] NVIDIA API call failed: %s", e)
        return None


def llm_generate_json(prompt: str, system: str = "", temperature: float = 0.7) -> dict | list | None:
    """Call LLM and parse the response as JSON. Returns None on failure."""
    raw = llm_generate(prompt, system=system, temperature=temperature, max_tokens=800)
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1:
            start = raw.find("[")
            end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except (json.JSONDecodeError, ValueError):
                pass
        logger.warning("[llm_client] Failed to parse LLM response as JSON")
        return None
