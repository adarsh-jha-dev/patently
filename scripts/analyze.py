"""
Run a prior-art analysis from the terminal.

Useful for evaluating retrieval quality without the web app in the loop, and
for scripting the pipeline over a batch of disclosures.

    python scripts/analyze.py "an invention description..."
    python scripts/analyze.py --file disclosure.txt --json > report.json
    cat disclosure.txt | python scripts/analyze.py
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "embeddings"))

from patently import config  # noqa: E402
from patently.analyze import run_analysis  # noqa: E402
from patently.llm import LLMError  # noqa: E402
from patently.retrieval import Embedder, Store  # noqa: E402

GLYPH = {"covered": "●", "partial": "◐", "absent": "○"}


def render(r) -> str:
    out: list[str] = []
    w = out.append

    w(f"\n{r.title}")
    w(f"{r.restatement}\n")
    w(f"  {r.verdict.novelty_score}/100  {r.verdict.label}")
    w(f"  {r.verdict.summary}\n")

    w("CLAIM ELEMENTS")
    for e in r.elements:
        w(f"  {e.id}  {e.label} — {e.text}")

    if r.references:
        w("\nCOVERAGE" + " " * 26 + "  ".join(x.ref_id.rjust(3) for x in r.references))
        for e in r.elements:
            cells = "  ".join(
                GLYPH[next(c.level for c in ref.coverage if c.element_id == e.id)].rjust(3)
                for ref in r.references
            )
            w(f"  {e.id:<4}{e.label[:26]:<28}{cells}")
        w("        ● taught   ◐ adjacent   ○ not found")

    if r.whitespace:
        names = [e.label for e in r.elements if e.id in r.whitespace]
        w(f"\nWHITESPACE  nothing found teaches: {', '.join(names)}")
    else:
        w("\nWHITESPACE  none — every element is at least partly taught")

    if r.combinations:
        w("\nCOMBINATION RISK")
        for c in r.combinations:
            miss = (
                f"still missing {', '.join(c.missing)}"
                if c.missing
                else "covers every element"
            )
            w(f"  {' + '.join(c.ref_ids):<12} {c.coverage_fraction:.0%}  {miss}")

    w("\nREFERENCES")
    for ref in r.references:
        w(f"  {ref.ref_id}  [{ref.relevance:>3}] {ref.patent_id}  {ref.title[:70]}")
        if ref.note:
            w(f"        {ref.note}")
        for c in ref.coverage:
            if c.quote:
                flag = "" if c.quote_verified else "  (unverified)"
                w(f'        {GLYPH[c.level]} {c.element_id}: "{c.quote[:88]}"{flag}')

    w(f"\n{json.dumps(r.stats)}")
    w("Research tool, not a freedom-to-operate opinion.\n")
    return "\n".join(out)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("description", nargs="?", help="Invention description.")
    ap.add_argument("--file", type=Path, help="Read the description from a file.")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--json", action="store_true", help="Emit raw JSON.")
    args = ap.parse_args()

    if args.file:
        text = args.file.read_text()
    elif args.description:
        text = args.description
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        ap.error("provide a description, --file, or pipe text on stdin")

    if len(text.strip()) < 40:
        print("Description is too short to analyse (need 40+ chars).", file=sys.stderr)
        return 2

    store = Store.from_env()
    if store is None:
        print("Set QDRANT_URL (cloud) or QDRANT_PATH (local) in .env.", file=sys.stderr)
        return 1

    print(f"Loading {config.EMBED_MODEL}...", file=sys.stderr)
    embedder = Embedder()

    async def progress(stage, payload):
        if payload.get("message"):
            print(f"  {payload['message']}", file=sys.stderr)

    try:
        result = await run_analysis(
            text, embedder, store, top_k=args.top_k, on_progress=progress
        )
    except LLMError as e:
        # A missing key or a dead model id is an expected operator error, not
        # a crash — say what to do about it in one line.
        print(f"\n{config.LLM_PROVIDER}: {e}", file=sys.stderr)
        print("Run scripts/check_provider.py to diagnose.", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    finally:
        store.close()

    print(json.dumps(result.model_dump(), indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
