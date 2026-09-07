"use client";

import { VerdictPanel } from "@/components/Verdict";
import { CoverageMatrix } from "@/components/CoverageMatrix";
import { Angles, Combinations, References, Whitespace } from "@/components/Findings";
import type { AnalyzeResult } from "@/lib/types";

/**
 * Shared by the live analysis and the saved permalink, so a shared link cannot
 * drift from what the sender saw. `corpus` is passed separately because only a
 * saved row knows what it was searched against.
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

      <footer className="border-t border-[var(--border)] pt-5 text-2xs leading-relaxed text-[var(--text-faint)]">
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
