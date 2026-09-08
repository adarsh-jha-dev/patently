"use client";

import { VerdictPanel } from "@/components/Verdict";
import { CoverageMatrix } from "@/components/CoverageMatrix";
import { ElementCoverage } from "@/components/ElementCoverage";
import { Angles, Combinations, References, Whitespace } from "@/components/Findings";
import type { AnalyzeResult } from "@/lib/types";
import { ReportNav, type NavSection } from "@/components/ReportNav";

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
  const sections: NavSection[] = [
    { id: "assessment", label: "Assessment" },
    { id: "elements", label: "Element coverage" },
    { id: "matrix", label: "Coverage map" },
    { id: "whitespace", label: "Whitespace" },
    ...(result.combinations.length
      ? [{ id: "combinations", label: "Combination risk" }]
      : []),
    { id: "references", label: "References" },
    { id: "angles", label: "Search angles" },
  ];

  return (
    // The rail appears only when there is genuinely room for it. Below xl this
    // collapses to the single column the content was designed for.
    <div className="xl:grid xl:grid-cols-[minmax(0,1fr)_200px] xl:items-start xl:gap-10">
      <div className="min-w-0 space-y-8">
        <section id="assessment" className="scroll-mt-8">
          <VerdictPanel result={result} />
        </section>
        <section id="elements" className="scroll-mt-8">
          <ElementCoverage result={result} />
        </section>
        <section id="matrix" className="scroll-mt-8">
          <CoverageMatrix result={result} />
        </section>
        <section id="whitespace" className="scroll-mt-8">
          <Whitespace result={result} />
        </section>
        {result.combinations.length > 0 && (
          <section id="combinations" className="scroll-mt-8">
            <Combinations result={result} />
          </section>
        )}
        <section id="references" className="scroll-mt-8">
          <References result={result} />
        </section>
        <section id="angles" className="scroll-mt-8">
          <Angles result={result} />
        </section>

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

      <aside className="hidden xl:block">
        <ReportNav sections={sections} />
      </aside>
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
