"""
Verify the reasoning provider is actually usable, before a real analysis
fails halfway through.

Checks, in order: key present -> model reachable -> a real schema-constrained
call returns valid JSON. Also lists the models your key can see, which is the
fastest way to find a current cheap one — model ids go stale, and the API
knows the truth.

    python scripts/check_provider.py            # the configured provider
    python scripts/check_provider.py --all      # both
    python scripts/check_provider.py --models   # just list models
"""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "embeddings"))

from patently import config, llm  # noqa: E402

OK, BAD, INFO = "  ok  ", " FAIL ", "      "

PROBE_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "elements": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ok", "elements"],
    "additionalProperties": False,
}


async def list_models(provider: str, key: str) -> list[str]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        if provider == "gemini":
            r = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": key},
            )
            r.raise_for_status()
            return [
                m["name"].replace("models/", "")
                for m in r.json().get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
        r = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        r.raise_for_status()
        return sorted(m["id"] for m in r.json().get("data", []))


async def check(provider: str, show_models: bool) -> bool:
    key = config.GEMINI_API_KEY if provider == "gemini" else config.OPENAI_API_KEY
    model = config.GEMINI_MODEL if provider == "gemini" else config.OPENAI_MODEL
    env = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"

    print(f"\n{provider}  (model: {model})")

    if not key:
        print(f"{BAD} {env} is empty in .env")
        return False
    print(f"{OK} {env} present")

    try:
        models = await list_models(provider, key)
    except Exception as e:
        print(f"{BAD} could not list models: {type(e).__name__}: {str(e)[:160]}")
        return False
    print(f"{OK} key accepted — {len(models)} models visible")

    if model not in models:
        print(f"{BAD} '{model}' is not among them")
        # Surface the near-misses rather than the whole list; a stale id is
        # usually one version away from a live one.
        stem = model.split("-")[0]
        near = [m for m in models if m.startswith(stem)][:12]
        if near:
            print(f"{INFO} closest available: {', '.join(near)}")
        return False
    print(f"{OK} '{model}' is available")

    # Only the configured provider can be exercised, since the adapter reads
    # the module-level setting.
    original = config.LLM_PROVIDER
    config.LLM_PROVIDER = provider
    try:
        out = await llm.complete_json(
            system="You return JSON matching the schema. Nothing else.",
            user="Set ok to true and elements to exactly [\"a\", \"b\"].",
            schema=PROBE_SCHEMA,
            max_tokens=2000,
            retries=0,
        )
    except Exception as e:
        print(f"{BAD} live call failed: {str(e)[:300]}")
        return False
    finally:
        config.LLM_PROVIDER = original

    if not isinstance(out, dict) or "ok" not in out or "elements" not in out:
        print(f"{BAD} response did not match the schema: {out}")
        return False
    print(f"{OK} schema-constrained call returned {out}")

    if show_models:
        print(f"{INFO} all models: {', '.join(models)}")
    return True


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="Check both providers.")
    ap.add_argument("--models", action="store_true", help="List every model id.")
    args = ap.parse_args()

    providers = ["gemini", "openai"] if args.all else [config.LLM_PROVIDER]
    results = [await check(p, args.models) for p in providers]

    print()
    if all(results):
        print("All checks passed.")
        return 0
    if any(results):
        print("Some providers failed — see above. The passing one still works; "
              "switch with PATENTLY_LLM_PROVIDER in .env.")
        return 1
    print("No provider is usable. Fix the key or model id above.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
