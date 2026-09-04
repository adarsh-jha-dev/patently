"use client";

import { useState } from "react";
import type { AnalyzeResult, CoverageLevel } from "@/lib/types";
import { LEVEL_META } from "@/lib/types";

/**
 * Element × reference coverage grid.
 *
 * This is the answer to "why isn't this just a search box": a ranked list of
 * similar patents tells you nothing about *which part* of your invention is
 * already taught. Rows are your claim elements, columns are references, and
 * every filled cell is backed by a quote that was verified against the source
 * abstract.
 *
 * Cells encode state with a glyph as well as a tint, so the grid survives
 * colour-vision deficiency, greyscale printing, and forced-colors mode.
 */
export function CoverageMatrix({ result }: { result: AnalyzeResult }) {
  const [hover, setHover] = useState<{ e: string; r: string } | null>(null);
  const { elements, references } = result;

  if (!references.length) return null;

  const cell = (elementId: string, refId: string): CoverageLevel => {
    const ref = references.find((r) => r.ref_id === refId);
    return (ref?.coverage.find((c) => c.element_id === elementId)?.level ??
      "absent") as CoverageLevel;
  };

  const quoteFor = (elementId: string, refId: string) =>
    references
      .find((r) => r.ref_id === refId)
      ?.coverage.find((c) => c.element_id === elementId);

  const active = hover ? quoteFor(hover.e, hover.r) : null;
  const activeElement = hover
    ? elements.find((e) => e.id === hover.e)
    : null;

  return (
    <section className="rise">
      <header className="mb-3 flex items-baseline justify-between gap-4">
        <div>
          <h2 className="text-[15px] font-medium tracking-tight">
            Coverage map
          </h2>
          <p className="mt-0.5 text-[13px] text-[var(--text-muted)]">
            Which references teach which parts of your invention.
          </p>
        </div>
        <Legend />
      </header>

      <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--surface)]">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 min-w-[220px] bg-[var(--surface)] p-3 text-left align-bottom">
                <span className="eyebrow">Claim element</span>
              </th>
              {references.map((r) => (
                <th
                  key={r.ref_id}
                  className="p-2 pb-3 text-center align-bottom"
                  title={r.title}
                >
                  <span className="mono text-[11px] text-[var(--text-muted)]">
                    {r.ref_id}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {elements.map((e, i) => (
              <tr
                key={e.id}
                className={i % 2 ? "bg-[var(--surface-sunk)]/40" : undefined}
              >
                <th
                  scope="row"
                  className={`sticky left-0 z-10 max-w-[260px] p-3 text-left font-normal ${
                    i % 2 ? "bg-[var(--surface-sunk)]" : "bg-[var(--surface)]"
                  }`}
                >
                  <span className="mono mr-2 text-[11px] text-[var(--text-faint)]">
                    {e.id}
                  </span>
                  <span className="text-[13px]">{e.label}</span>
                </th>
                {references.map((r) => {
                  const level = cell(e.id, r.ref_id);
                  const meta = LEVEL_META[level];
                  const isHot =
                    hover?.e === e.id && hover?.r === r.ref_id;
                  return (
                    <td key={r.ref_id} className="p-1 text-center">
                      <button
                        type="button"
                        onMouseEnter={() => setHover({ e: e.id, r: r.ref_id })}
                        onMouseLeave={() => setHover(null)}
                        onFocus={() => setHover({ e: e.id, r: r.ref_id })}
                        onBlur={() => setHover(null)}
                        aria-label={`${e.label} — ${r.ref_id}: ${meta.label}`}
                        // 2px gap between fills, per mark spec: the inset keeps
                        // adjacent cells from reading as one continuous block.
                        className="flex h-8 w-full min-w-[34px] items-center justify-center rounded-[5px] leading-none transition-[transform,box-shadow] duration-150"
                        style={{
                          background: `var(${meta.tint})`,
                          color: `var(${meta.varName})`,
                          boxShadow: isHot
                            ? `inset 0 0 0 1.5px var(${meta.varName})`
                            : undefined,
                          transform: isHot ? "scale(1.06)" : undefined,
                        }}
                      >
                        {meta.glyph}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Evidence panel: fixed height so hovering the grid never reflows the
          page underneath it. */}
      <div className="mt-2 min-h-[68px] rounded-lg border border-dashed border-[var(--border)] px-4 py-3 text-[13px]">
        {active && activeElement ? (
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="mono text-[11px] text-[var(--text-faint)]">
                {hover?.r} × {activeElement.id}
              </span>
              <span
                className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                style={{
                  background: `var(${LEVEL_META[active.level].tint})`,
                  color: `var(${LEVEL_META[active.level].varName})`,
                }}
              >
                {LEVEL_META[active.level].glyph} {LEVEL_META[active.level].label}
              </span>
              {!active.quote_verified && (
                <span className="text-[11px] text-[var(--text-faint)]">
                  quote unverified — finding downgraded
                </span>
              )}
            </div>
            <p className="mt-1.5 text-[var(--text-muted)]">
              {active.quote ? (
                <>&ldquo;{active.quote}&rdquo;</>
              ) : (
                <span className="text-[var(--text-faint)]">
                  Nothing in this abstract supports {activeElement.label}.
                </span>
              )}
            </p>
          </div>
        ) : (
          <p className="text-[var(--text-faint)]">
            Hover a cell to see the verbatim passage behind the finding.
          </p>
        )}
      </div>
    </section>
  );
}

function Legend() {
  return (
    <div className="flex shrink-0 items-center gap-3 text-[11px] text-[var(--text-muted)]">
      {(["covered", "partial", "absent"] as const).map((k) => (
        <span key={k} className="flex items-center gap-1.5">
          <span style={{ color: `var(${LEVEL_META[k].varName})` }}>
            {LEVEL_META[k].glyph}
          </span>
          {LEVEL_META[k].label}
        </span>
      ))}
    </div>
  );
}
