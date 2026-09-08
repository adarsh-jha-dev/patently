"use client";

import { VerdictPanel } from "@/components/Verdict";
import { CoverageMatrix } from "@/components/CoverageMatrix";
import { ElementCoverage } from "@/components/ElementCoverage";
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
      <ElementCoverage result={result} />
      <CoverageMatrix result={result} />
      <Whitespace result={result} />
      <Combinations result={result} />
      <References result={result} />
      <Angles result={result} />

      <footer className="border-t border-[var(--border)] pt-6 text-2xs leading-relaxed text-[var(--text-faint)]">
        <dl className="mb-5 flex flex-wrap gap-x-10 gap-y-4">
          <RunStat label="Model calls" value={String(result.stats.llm_calls ?? 0)} />
          <RunStat label="Patents reached" value={(result.stats.pool ?? 0).toLocaleString()} />
          <RunStat label="Assessed in depth" value={String(result.stats.assessed ?? 0)} />
          {result.elapsed_ms ? (
            <RunStat label="Elapsed" value={`${(result.elapsed_ms / 1000).toFixed(1)}s`} />
          ) : null}
          {corpus ? (
            <RunStat label="Corpus searched" value={corpus.size.toLocaleString()} />
          ) : null}
        </dl>
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

function RunStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-2xs text-[var(--text-faint)]">{label}</dt>
      <dd className="tnum mt-0.5 text-lg font-semibold tracking-tight text-[var(--text)]">
        {value}
      </dd>
    </div>
  );
}
