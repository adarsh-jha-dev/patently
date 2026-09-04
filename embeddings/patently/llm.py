"""
Provider-neutral JSON-mode LLM adapter (Gemini + OpenAI).

The whole reasoning layer needs exactly one capability: "given a prompt and a
JSON schema, return an object matching that schema." Both providers support
that natively — Gemini via `responseSchema`, OpenAI via `response_format:
json_schema` with `strict` — so this module normalises the two request shapes
and hands back a plain dict.

Why raw HTTP instead of the vendor SDKs: this is the only place either API is
touched, the two payloads are ~15 lines each, and httpx is already a
transitive dependency. Two fewer packages to keep pinned.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from . import config


class LLMError(RuntimeError):
    """Raised when a provider is misconfigured or returns something unusable."""


# Gemini rejects a handful of JSON Schema keywords that OpenAI requires
# (notably `additionalProperties`), so schemas are authored in OpenAI's
# stricter dialect and down-converted here.
_GEMINI_UNSUPPORTED = {"additionalProperties", "$schema", "strict", "default"}


def _to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _GEMINI_UNSUPPORTED:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {k: _to_gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            out[key] = _to_gemini_schema(value)
        else:
            out[key] = value
    return out


def active_provider() -> str:
    return config.LLM_PROVIDER


def provider_status() -> dict[str, Any]:
    """Reported by /health so a misconfigured key is visible before a request."""
    return {
        "provider": config.LLM_PROVIDER,
        "model": (
            config.GEMINI_MODEL
            if config.LLM_PROVIDER == "gemini"
            else config.OPENAI_MODEL
        ),
        "key_present": bool(
            config.GEMINI_API_KEY
            if config.LLM_PROVIDER == "gemini"
            else config.OPENAI_API_KEY
        ),
    }


async def _call_gemini(
    system: str, user: str, schema: dict[str, Any], max_tokens: int
) -> dict[str, Any]:
    if not config.GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is not set")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODEL}:generateContent"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
            "responseSchema": _to_gemini_schema(schema),
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url, json=payload, headers={"x-goog-api-key": config.GEMINI_API_KEY}
        )
    if resp.status_code >= 400:
        raise LLMError(f"gemini {resp.status_code}: {resp.text[:400]}")

    body = resp.json()
    candidates = body.get("candidates") or []
    if not candidates:
        # Usually a safety block or an empty prompt — surface the reason rather
        # than failing later with an opaque KeyError.
        raise LLMError(f"gemini returned no candidates: {json.dumps(body)[:400]}")

    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    return _parse_json(text, "gemini")


# OpenAI's parameter surface differs across model families, and which family a
# model id belongs to is not something we can reliably infer from the string —
# that guess is exactly what goes stale. Instead we send the modern parameters
# and let a 400 teach us what this model actually accepts, then remember it for
# the rest of the process. One wasted round trip per process, no model table to
# maintain.
_OPENAI_QUIRKS: set[str] = set()

_OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"


def _openai_payload(
    system: str, user: str, schema: dict[str, Any], max_tokens: int
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "result", "strict": True, "schema": schema},
        },
    }

    # `max_tokens` is deprecated and rejected outright by the reasoning models;
    # `max_completion_tokens` is the current spelling everywhere else.
    if "legacy_max_tokens" in _OPENAI_QUIRKS:
        payload["max_tokens"] = max_tokens
    else:
        payload["max_completion_tokens"] = max_tokens

    # Reasoning models only accept the default temperature. Everything else
    # benefits from a low one for extraction work.
    if "no_temperature" not in _OPENAI_QUIRKS:
        payload["temperature"] = 0.1

    return payload


def _learn_openai_quirk(message: str) -> bool:
    """Record what the API just rejected. Returns True if a retry is worthwhile."""
    m = message.lower()
    if "max_completion_tokens" in m and "legacy_max_tokens" not in _OPENAI_QUIRKS:
        # Older deployments predate the rename.
        _OPENAI_QUIRKS.add("legacy_max_tokens")
        return True
    if "max_tokens" in m and "not supported" in m:
        _OPENAI_QUIRKS.discard("legacy_max_tokens")
        return True
    if "temperature" in m and "no_temperature" not in _OPENAI_QUIRKS:
        _OPENAI_QUIRKS.add("no_temperature")
        return True
    return False


async def _call_openai(
    system: str, user: str, schema: dict[str, Any], max_tokens: int
) -> dict[str, Any]:
    if not config.OPENAI_API_KEY:
        raise LLMError(
            "OPENAI_API_KEY is not set. Add it to .env, or switch providers "
            "with PATENTLY_LLM_PROVIDER=gemini."
        )

    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}

    async with httpx.AsyncClient(timeout=180.0) as client:
        for attempt in range(3):  # at most two parameter corrections
            payload = _openai_payload(system, user, schema, max_tokens)
            resp = await client.post(_OPENAI_ENDPOINT, json=payload, headers=headers)

            if resp.status_code == 400:
                detail = resp.text
                try:
                    detail = resp.json()["error"]["message"]
                except Exception:
                    pass
                if attempt < 2 and _learn_openai_quirk(detail):
                    continue
                raise LLMError(f"openai 400: {detail[:400]}")

            if resp.status_code == 401:
                raise LLMError("openai 401: the OPENAI_API_KEY in .env was rejected")
            if resp.status_code == 404:
                raise LLMError(
                    f"openai 404: model '{config.OPENAI_MODEL}' is not available "
                    "to this key. Run scripts/check_provider.py to list what is."
                )
            if resp.status_code >= 400:
                raise LLMError(f"openai {resp.status_code}: {resp.text[:400]}")
            break

    body = resp.json()
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}

    # A refusal comes back as a 200 with `content: null`, so it has to be
    # checked explicitly or it surfaces later as an unhelpful JSON parse error.
    if message.get("refusal"):
        raise LLMError(f"openai declined the request: {message['refusal'][:200]}")
    if choice.get("finish_reason") == "length":
        raise LLMError(
            "openai hit the output token cap before finishing the JSON. "
            "Lower PATENTLY_ASSESS_TOP_K or raise the call's max_tokens."
        )

    return _parse_json(message.get("content"), "openai")


def _parse_json(text: str | None, provider: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise LLMError(f"{provider} returned an empty response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Both providers honour JSON mode reliably, but a truncated response
        # (max_tokens hit) lands here. Salvage the outermost object if we can.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise LLMError(f"{provider} returned non-JSON: {text[:300]}")


async def complete_json(
    system: str,
    user: str,
    schema: dict[str, Any],
    max_tokens: int = 8000,
    retries: int = 1,
) -> dict[str, Any]:
    """Run one schema-constrained completion against the configured provider."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            if config.LLM_PROVIDER == "gemini":
                return await _call_gemini(system, user, schema, max_tokens)
            if config.LLM_PROVIDER == "openai":
                return await _call_openai(system, user, schema, max_tokens)
            raise LLMError(
                f"unknown PATENTLY_LLM_PROVIDER '{config.LLM_PROVIDER}' "
                "(expected 'gemini' or 'openai')"
            )
        except LLMError as e:
            last = e
            if attempt < retries:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]
