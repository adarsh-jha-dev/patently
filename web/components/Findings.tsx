"use client";

import { useState } from "react";
import type { AnalyzeResult, Element } from "@/lib/types";
import { LEVEL_META } from "@/lib/types";
import { Card } from "@/components/ui/card";

/**
 * Whitespace — the elements no reference in the corpus teaches.
 *
 * Arguably the most useful output in the whole product, because it is the one
 * a search engine structurally cannot give you: an absence is only meaningful
 * if you know what was searched for and what came back.
 */
export function Whitespace({ result }: { result: AnalyzeResult }) {
  const open = result.elements.filter((e) => result.whitespace.includes(e.id));
  const total = result.elements.length;

  if (open.length === 0) {
    return (
      <Card className="rise p-5 sm:p-6">
        <span className="eyebrow">Novelty whitespace</span>
        <p className="mt-3 max-w-prose text-base leading-relaxed text-[var(--text-muted)]">
          Every element you described is taught, at least in part, by something
          in the corpus. Novelty likely has to come from the specific
          combination, or from a limitation narrower than the description
          states.
        </p>
      </Card>
    );
  }

  return (
    <Card
      className="rise overflow-hidden p-0"
      style={{ borderColor: "var(--absent)" }}
    >
      <div
        className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-4 sm:px-6"
        style={{ background: "var(--absent-tint)" }}
      >
        <span
          className="tnum text-5xl font-semibold leading-none tracking-tight"
          style={{ color: "var(--absent)" }}
        >
          {open.length}
        </span>
        <span className="min-w-0">
          <span className="block text-lg font-semibold tracking-tight">
            of {total} element{total === 1 ? "" : "s"} nothing teaches
          </span>
          <span className="block text-sm text-[var(--text-muted)]">
            The part of the claim that is most defensible — and the output a
            similarity search structurally cannot give you.
          </span>
        </span>
      </div>

      <ul className="divide-y divide-[var(--border)]">
        {open.map((e) => (
          <li key={e.id} className="flex gap-3 px-5 py-4 sm:px-6">
            <span
              aria-hidden
              className="mt-1.5 size-2 shrink-0 rounded-full"
              style={{ background: "var(--absent)" }}
            />
            <span className="min-w-0">
              <span className="mono mr-2 text-2xs text-[var(--text-faint)]">
                {e.id}
              </span>
              <span className="text-base font-semibold">{e.label}</span>
              <p className="mt-1 max-w-prose text-sm leading-relaxed text-[var(--text-muted)]">
                {e.text}
              </p>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/**
 * §103-shaped combinations: pairs of references that between them read on more
 * than either does alone. Found by exhaustive set arithmetic over the coverage
 * matrix, not by asking a model — so the same inputs always give the same
 * pairs.
 */
export function Combinations({ result }: { result: AnalyzeResult }) {
  const { combinations, elements } = result;
  if (!combinations.length) return null;

  const nameOf = (id: string) => elements.find((e) => e.id === id)?.label ?? id;

  return (
    <Card className="rise p-5 sm:p-6">
      <h2 className="text-xl font-semibold tracking-tight">Combination risk</h2>
      <p className="mt-1.5 max-w-prose text-sm leading-relaxed text-[var(--text-muted)]">
        Pairs that together read on more of the invention than either does
        alone — the shape of an obviousness rejection. Found by set arithmetic
        over the coverage matrix, so the same inputs always give the same pairs.
      </p>

      <ul className="mt-5 space-y-4">
        {combinations.map((c) => {
          const pct = Math.round(c.coverage_fraction * 100);
          return (
            <li key={c.ref_ids.join("+")}>
              <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <span className="flex items-center gap-1.5">
                  {c.ref_ids.map((id, i) => (
                    <span key={id} className="flex items-center gap-1.5">
                      {i > 0 && (
                        <span className="text-[var(--text-faint)]">+</span>
                      )}
                      <span className="mono rounded-md bg-[var(--surface-sunk)] px-2 py-0.5 text-2xs font-medium">
                        {id}
                      </span>
                    </span>
                  ))}
                </span>
                <span className="tnum text-sm font-semibold">
                  {pct}%{" "}
                  <span className="font-normal text-[var(--text-muted)]">
                    of the invention
                  </span>
                </span>
              </div>

              <div
                className="h-2 w-full overflow-hidden rounded-full"
                style={{ background: "var(--none-tint)" }}
                role="img"
                aria-label={`${c.ref_ids.join(" and ")} together cover ${pct}% of the invention`}
              >
                <div
                  className="h-full rounded-full transition-[width] duration-700 ease-out"
                  style={{
                    width: `${Math.max(pct, 2)}%`,
                    background:
                      pct >= 75 ? "var(--covered)" : "var(--partial)",
                  }}
                />
              </div>

              {c.missing.length > 0 ? (
                <p className="mt-2 flex flex-wrap items-center gap-1.5 text-2xs text-[var(--text-muted)]">
                  <span>Still missing</span>
                  {c.missing.map((id) => (
                    <span
                      key={id}
                      className="rounded-md px-1.5 py-0.5 font-medium"
                      style={{
                        background: "var(--absent-tint)",
                        color: "var(--absent)",
                      }}
                    >
                      {nameOf(id)}
                    </span>
                  ))}
                </p>
              ) : (
                <p
                  className="mt-2 text-2xs font-medium"
                  style={{ color: "var(--covered)" }}
                >
                  Together these two reach every element you described.
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/**
 * The search angles, with how much each one actually contributed.
 *
 * `found_by` on every reference already records which angles surfaced it, but
 * nothing displayed it. Counting it turns an auditable list into evidence that
 * the multi-angle fusion is doing work: an angle that surfaced nothing is
 * visible, and so is the one that carried the retrieval.
 */
export function Angles({ result }: { result: AnalyzeResult }) {
  const hits = new Map<string, number>();
  for (const ref of result.references) {
    for (const qid of ref.found_by) {
      hits.set(qid, (hits.get(qid) ?? 0) + 1);
    }
  }
  const max = Math.max(1, ...hits.values());
  const assessed = result.references.length;

  return (
    <Card className="rise p-5 sm:p-6">
      <h2 className="text-xl font-semibold tracking-tight">Search angles</h2>
      <p className="mt-1.5 max-w-prose text-sm leading-relaxed text-[var(--text-muted)]">
        One embedding of a whole description averages away the specifics. These
        were searched separately and the rankings fused — the bars show how many
        of the {assessed} assessed references each angle surfaced.
      </p>

      <ul className="mt-5 space-y-4">
        {result.queries.map((q) => {
          const n = hits.get(q.id) ?? 0;
          return (
            <li key={q.id}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <span className="min-w-0 text-sm font-semibold">
                  <span className="mono mr-2 text-2xs font-normal text-[var(--text-faint)]">
                    {q.id}
                  </span>
                  {q.angle}
                </span>
                <span
                  className="tnum shrink-0 text-2xs"
                  style={{
                    color: n ? "var(--text-muted)" : "var(--text-faint)",
                  }}
                >
                  {n ? `${n} of ${assessed}` : "surfaced nothing"}
                </span>
              </div>

              <div
                className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full"
                style={{ background: "var(--none-tint)" }}
                role="img"
                aria-label={`${q.angle} surfaced ${n} of ${assessed} assessed references`}
              >
                <div
                  className="h-full rounded-full transition-[width] duration-700 ease-out"
                  style={{
                    width: `${(n / max) * 100}%`,
                    background: "var(--accent)",
                  }}
                />
              </div>

              <p className="mt-2 max-w-prose text-sm leading-relaxed text-[var(--text-muted)]">
                {q.text}
              </p>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

export function References({ result }: { result: AnalyzeResult }) {
  const [open, setOpen] = useState<string | null>(null);
  const byId = new Map<string, Element>(result.elements.map((e) => [e.id, e]));

  if (!result.references.length) {
    return (
      <section className="rounded-xl border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--text-muted)]">
        No references retrieved. Is the index populated?
      </section>
    );
  }

  return (
    <section className="rise">
      <h2 className="mb-3 text-xl font-semibold tracking-tight">
        References{" "}
        <span className="tnum font-normal text-[var(--text-faint)]">
          {result.references.length}
        </span>
      </h2>
      <ul className="space-y-2">
        {result.references.map((r) => {
          const isOpen = open === r.ref_id;
          const hits = r.coverage.filter((c) => c.level !== "absent");
          return (
            <li
              key={r.ref_id}
              className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface)]"
            >
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : r.ref_id)}
                aria-expanded={isOpen}
                className="flex w-full items-start gap-3 p-4 text-left"
              >
                <span className="mono mt-0.5 shrink-0 text-2xs text-[var(--text-faint)]">
                  {r.ref_id}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm leading-snug">
                    {r.title}
                  </span>
                  {r.note && (
                    <span className="mt-1 block text-xs text-[var(--text-muted)]">
                      {r.note}
                    </span>
                  )}
                  <span className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-2xs text-[var(--text-faint)]">
                    <span className="mono">{r.patent_id}</span>
                    {/* Relevance is a magnitude, so it gets a rail. The number
                        stays beside it — the rail alone would be unreadable at
                        this size, and colour is never the only encoding. */}
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        aria-hidden
                        className="inline-block h-1 w-12 overflow-hidden rounded-full align-middle"
                        style={{ background: "var(--none-tint)" }}
                      >
                        <span
                          className="block h-full rounded-full"
                          style={{
                            width: `${Math.max(r.relevance, 2)}%`,
                            background:
                              r.relevance >= 60
                                ? "var(--covered)"
                                : r.relevance >= 35
                                  ? "var(--partial)"
                                  : "var(--none-ink)",
                          }}
                        />
                      </span>
                      <span className="tnum">relevance {r.relevance}</span>
                    </span>
                    <span>found by {r.found_by.join(", ")}</span>
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1 pt-0.5">
                  {r.coverage.map((c) => (
                    <span
                      key={c.element_id}
                      title={`${byId.get(c.element_id)?.label}: ${LEVEL_META[c.level].label}`}
                      className="text-sm leading-none"
                      style={{ color: `var(${LEVEL_META[c.level].varName})` }}
                    >
                      {LEVEL_META[c.level].glyph}
                    </span>
                  ))}
                </span>
              </button>

              {isOpen && (
                <div className="border-t border-[var(--border)] px-4 py-4 text-sm">
                  {hits.length > 0 && (
                    <ul className="mb-4 space-y-2.5">
                      {hits.map((c) => (
                        <li key={c.element_id}>
                          <div className="flex items-center gap-2">
                            <span
                              className="text-2xs"
                              style={{
                                color: `var(${LEVEL_META[c.level].varName})`,
                              }}
                            >
                              {LEVEL_META[c.level].glyph}
                            </span>
                            <span className="text-xs font-medium">
                              {byId.get(c.element_id)?.label}
                            </span>
                            <span className="text-2xs text-[var(--text-faint)]">
                              {LEVEL_META[c.level].label}
                              {!c.quote_verified && " · unverified"}
                            </span>
                          </div>
                          {c.quote && (
                            <blockquote className="mt-1 border-l-2 border-[var(--border-strong)] pl-3 text-[var(--text-muted)]">
                              {c.quote}
                            </blockquote>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="text-xs leading-relaxed text-[var(--text-muted)]">
                    {r.abstract}
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
