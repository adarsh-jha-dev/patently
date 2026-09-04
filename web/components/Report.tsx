"use client";

import { VerdictPanel } from "@/components/Verdict";
import { CoverageMatrix } from "@/components/CoverageMatrix";
import { Angles, Combinations, References, Whitespace } from "@/components/Findings";
import type { AnalyzeResult } from "@/lib/types";

/**
 * The finished report.
 *
 * Extracted so a live analysis and a saved permalink render through exactly
 * the same component — if they diverged, a shared link would quietly stop
 * being the thing the sender actually saw.
 *
 * `corpus` is passed separately because a saved row knows what it was searched
 * against and a live result only knows what is in the index right now. Showing
 * it is not a footnote: a verdict of "Inconclusive" over 8,220 abstracts and
 * the same verdict over 258,935 are different claims about the world.
 */
export function Report({
  result,
  corpus,
}: {
  result: AnalyzeResult;
  corpus?: { name: string; size: number } | null;
}) {
  return (
    <div className="space-y-8">
      <VerdictPanel result={result} />
      <CoverageMatrix result={result} />
      <div className="grid items-start gap-4 md:grid-cols-2">
        <Whitespace result={result} />
        <Combinations result={result} />
      </div>
      <References result={result} />
      <Angles result={result} />

      <footer className="border-t border-[var(--border)] pt-5 text-[11px] leading-relaxed text-[var(--text-faint)]">
        <p>
          {result.stats.llm_calls} model calls · {result.stats.pool} patents
          reached · {result.stats.assessed} assessed
          {result.stats.rubric_fields
            ? ` · ${result.stats.rubric_fields} rubric answers used`
            : ""}
          {result.elapsed_ms
            ? ` · ${(result.elapsed_ms / 1000).toFixed(1)}s`
            : ""}
        </p>
        {corpus && (
          <p className="mt-1.5">
            Searched <span className="tnum">{corpus.size.toLocaleString()}</span>{" "}
            indexed abstracts from <span className="mono">{corpus.name}</span>.
          </p>
        )}
        <p className="mt-1.5 max-w-2xl">
          Patently searches an indexed corpus, not the full patent literature —
          an empty result means nothing was found in what was indexed, not that
          nothing exists. This is a research tool and not a freedom-to-operate
          opinion or legal advice.
        </p>
      </footer>
    </div>
  );
}
