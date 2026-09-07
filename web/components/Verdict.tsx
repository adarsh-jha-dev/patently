import type { AnalyzeResult } from "@/lib/types";
import { Card } from "@/components/ui/card";

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
    <Card className="rise p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <span className="eyebrow">Assessment</span>
          <h2 className="mt-1.5 text-xl font-medium tracking-tight">
            {result.title}
          </h2>
          <p className="mt-2 max-w-2xl text-base leading-relaxed text-[var(--text-muted)]">
            {verdict.summary}
          </p>
        </div>

        <div className="shrink-0 text-right">
          <div
            className="tnum text-5xl font-light leading-none tracking-tight"
            style={{ color: `var(${tone})` }}
          >
            {verdict.conclusive ? verdict.novelty_score : "—"}
          </div>
          <div className="mt-1 text-xs font-medium">{verdict.label}</div>
          <div className="text-2xs text-[var(--text-faint)]">
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

      <dl className="mt-5 grid grid-cols-2 gap-x-8 gap-y-3 border-t border-[var(--border)] pt-4 text-sm sm:grid-cols-4">
        <Stat
          label="Closest single reference"
          value={`${Math.round(verdict.anticipation_risk * 100)}%`}
          hint="§102 anticipation"
          fraction={verdict.anticipation_risk}
        />
        <Stat
          label="Best two-reference combo"
          value={`${Math.round(verdict.combination_risk * 100)}%`}
          hint="§103 obviousness"
          fraction={verdict.combination_risk}
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
        <p className="mt-3 text-xs text-[var(--text-faint)]">
          {stats.quotes_demoted} finding
          {stats.quotes_demoted === 1 ? "" : "s"} downgraded because the cited
          passage could not be located verbatim in the source abstract.
        </p>
      )}
    </Card>
  );
}

function Stat({
  label,
  value,
  hint,
  fraction,
}: {
  label: string;
  value: string;
  hint: string;
  /** When present, draws a magnitude rail so two stats can be compared by eye
   *  rather than by reading two numbers and doing the subtraction. */
  fraction?: number;
}) {
  return (
    <div>
      <dt className="text-2xs text-[var(--text-faint)]">{label}</dt>
      <dd className="tnum mt-0.5 text-xl font-medium tracking-tight">
        {value}
      </dd>
      {typeof fraction === "number" && (
        <dd
          aria-hidden
          className="mt-1.5 h-1 w-full overflow-hidden rounded-full"
          style={{ background: "var(--none-tint)" }}
        >
          <div
            className="h-full rounded-full transition-[width] duration-700 ease-out"
            style={{
              width: `${Math.max(fraction * 100, 1.5)}%`,
              background:
                fraction >= 0.6
                  ? "var(--covered)"
                  : fraction >= 0.3
                    ? "var(--partial)"
                    : "var(--absent)",
            }}
          />
        </dd>
      )}
      <dd className="mt-1 text-2xs text-[var(--text-faint)]">{hint}</dd>
    </div>
  );
}
