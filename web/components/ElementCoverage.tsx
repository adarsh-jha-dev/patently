"use client";

import { LEVEL_META, type AnalyzeResult, type CoverageLevel } from "@/lib/types";
import { Card } from "@/components/ui/card";

/**
 * How many references teach each claim element.
 *
 * The form is a horizontal stacked bar per element — the job is composition
 * within a category, across 3-8 categories. Sorted most-taught first, so the
 * empty bars collect at the bottom: that is the whitespace, and it reads as an
 * absence you can see rather than a list of ids you have to cross-reference.
 *
 * Built in CSS rather than a chart library. Recharts would add ~100 KB to draw
 * eight divs, and its colours are JS values that don't follow `data-theme`
 * without a re-render — these segments are `var(--covered)` and update with the
 * theme for free.
 *
 * Colour is never alone: each segment carries a count, the legend names every
 * level, and the whitespace rows are labelled in words. That is also the relief
 * the palette validation requires — amber sits at 2.27:1 on white.
 */

const ORDER: CoverageLevel[] = ["covered", "partial", "absent"];

export function ElementCoverage({ result }: { result: AnalyzeResult }) {
  const { elements, references } = result;
  if (!references.length || !elements.length) return null;

  const rows = elements.map((el) => {
    const counts = { covered: 0, partial: 0, absent: 0 };
    for (const ref of references) {
      const cell = ref.coverage.find((c) => c.element_id === el.id);
      if (cell) counts[cell.level] += 1;
    }
    const taught = counts.covered + counts.partial;
    return { el, counts, taught, total: references.length };
  });

  const ranked = [...rows].sort(
    (a, b) => b.counts.covered - a.counts.covered || b.taught - a.taught,
  );
  const untouched = ranked.filter((r) => r.taught === 0).length;

  return (
    <Card className="rise p-5 sm:p-6">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">
          How crowded is each element
        </h2>
        <Legend />
      </div>
      <p className="mb-5 max-w-prose text-sm text-[var(--text-muted)]">
        Of the {references.length} references assessed, how many teach each part
        of your invention.
        {untouched > 0 && (
          <>
            {" "}
            <span className="font-medium text-[var(--text)]">
              {untouched} element{untouched === 1 ? "" : "s"}
            </span>{" "}
            nothing found teaches at all.
          </>
        )}
      </p>

      <ul className="space-y-4">
        {ranked.map(({ el, counts, taught, total }) => (
          <li key={el.id}>
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate text-sm font-medium">
                <span className="mono mr-2 text-2xs text-[var(--text-faint)]">
                  {el.id}
                </span>
                {el.label}
              </span>
              <span
                className="tnum shrink-0 text-2xs"
                style={{
                  color: taught ? "var(--text-muted)" : "var(--absent)",
                  fontWeight: taught ? 400 : 600,
                }}
              >
                {taught ? `${taught} of ${total}` : "nothing found"}
              </span>
            </div>

            {/* 8px rail, rounded ends, 2px surface gaps between segments. */}
            <div
              className="flex h-2 w-full gap-[2px] overflow-hidden rounded-full"
              style={{ background: "var(--none-tint)" }}
              role="img"
              aria-label={`${el.label}: ${counts.covered} taught, ${counts.partial} adjacent, ${counts.absent} not found, of ${total} references`}
            >
              {ORDER.filter((lvl) => lvl !== "absent").map((lvl) =>
                counts[lvl] ? (
                  <span
                    key={lvl}
                    className="h-full rounded-full first:rounded-l-full"
                    style={{
                      width: `${(counts[lvl] / total) * 100}%`,
                      background: `var(${LEVEL_META[lvl].varName})`,
                    }}
                  />
                ) : null,
              )}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Legend() {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {ORDER.map((lvl) => (
        <li
          key={lvl}
          className="flex items-center gap-1.5 text-2xs text-[var(--text-muted)]"
        >
          <span
            aria-hidden
            className="size-2.5 rounded-full"
            style={{
              background:
                lvl === "absent"
                  ? "var(--none-tint)"
                  : `var(${LEVEL_META[lvl].varName})`,
              boxShadow:
                lvl === "absent" ? "inset 0 0 0 1px var(--none-ink)" : undefined,
            }}
          />
          {LEVEL_META[lvl].label}
        </li>
      ))}
    </ul>
  );
}
