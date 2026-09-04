import type { AnalyzeResult } from "@/lib/types";

/**
 * The headline. A hero number plus one thin meter — no gauge, no dial.
 *
 * The two risk figures underneath are the ones that matter legally and they
 * are kept distinct on purpose: a single reference reading on everything is a
 * §102 anticipation problem, while two references that only together cover
 * everything is a §103 obviousness problem. Collapsing them into one number
 * would hide which conversation you are actually in.
 */
export function VerdictPanel({ result }: { result: AnalyzeResult }) {
  const { verdict, elements, whitespace, stats } = result;
  // An inconclusive run must never wear the "clear" colour or show a score —
  // a green 100 next to "we found nothing" is the one way this tool could
  // actively mislead someone.
  const tone = !verdict.conclusive
    ? "--text-faint"
    : verdict.novelty_score >= 70
      ? "--absent"
      : verdict.novelty_score >= 40
        ? "--partial"
        : "--covered";

  return (
    <section className="rise rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <span className="eyebrow">Assessment</span>
          <h2 className="mt-1.5 text-[19px] font-medium tracking-tight">
            {result.title}
          </h2>
          <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-[var(--text-muted)]">
            {verdict.summary}
          </p>
        </div>

        <div className="shrink-0 text-right">
          <div
            className="tnum text-[44px] font-light leading-none tracking-tight"
            style={{ color: `var(${tone})` }}
          >
            {verdict.conclusive ? verdict.novelty_score : "—"}
          </div>
          <div className="mt-1 text-[12px] font-medium">{verdict.label}</div>
          <div className="text-[11px] text-[var(--text-faint)]">
            {verdict.conclusive ? "novelty headroom" : "not enough signal"}
          </div>
        </div>
      </div>

      {/* 2px meter, rounded data-end, anchored at the left baseline. */}
      {verdict.conclusive && (
      <div
        className="mt-5 h-[6px] w-full overflow-hidden rounded-full bg-[var(--surface-sunk)]"
        role="img"
        aria-label={`Novelty headroom ${verdict.novelty_score} of 100`}
      >
        <div
          className="h-full rounded-full transition-[width] duration-700 ease-out"
          style={{
            width: `${Math.max(verdict.novelty_score, 2)}%`,
            background: `var(${tone})`,
          }}
        />
      </div>
      )}

      <dl className="mt-5 grid grid-cols-2 gap-x-8 gap-y-3 border-t border-[var(--border)] pt-4 text-[13px] sm:grid-cols-4">
        <Stat
          label="Closest single reference"
          value={`${Math.round(verdict.anticipation_risk * 100)}%`}
          hint="§102 anticipation"
        />
        <Stat
          label="Best two-reference combo"
          value={`${Math.round(verdict.combination_risk * 100)}%`}
          hint="§103 obviousness"
        />
        <Stat
          label="Untouched elements"
          value={`${whitespace.length} of ${elements.length}`}
          hint="nothing found teaches these"
        />
        <Stat
          label="Corpus reached"
          value={String(stats.pool ?? 0)}
          hint={`${stats.assessed ?? 0} assessed in depth`}
        />
      </dl>

      {typeof stats.quotes_demoted === "number" && stats.quotes_demoted > 0 && (
        <p className="mt-3 text-[12px] text-[var(--text-faint)]">
          {stats.quotes_demoted} finding
          {stats.quotes_demoted === 1 ? "" : "s"} downgraded because the cited
          passage could not be located verbatim in the source abstract.
        </p>
      )}
    </section>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div>
      <dt className="text-[11px] text-[var(--text-faint)]">{label}</dt>
      <dd className="tnum mt-0.5 text-[17px] font-medium tracking-tight">
        {value}
      </dd>
      <dd className="text-[11px] text-[var(--text-faint)]">{hint}</dd>
    </div>
  );
}
