"use client";

import { useState } from "react";
import type { AnalyzeResult, Element } from "@/lib/types";
import { LEVEL_META } from "@/lib/types";

/**
 * Whitespace — the elements no reference in the corpus teaches.
 *
 * Arguably the most useful output in the whole product, because it is the one
 * a search engine structurally cannot give you: an absence is only meaningful
 * if you know what was searched for and what came back.
 */
export function Whitespace({ result }: { result: AnalyzeResult }) {
  const open = result.elements.filter((e) => result.whitespace.includes(e.id));

  return (
    <section className="rise rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <span className="eyebrow">Novelty whitespace</span>
      {open.length === 0 ? (
        <p className="mt-2 text-[13px] text-[var(--text-muted)]">
          Every element you described is taught, at least in part, by something
          in the corpus. Novelty likely has to come from the specific
          combination or from a narrower limitation than the description states.
        </p>
      ) : (
        <>
          <p className="mt-2 text-[13px] text-[var(--text-muted)]">
            Nothing retrieved teaches {open.length === 1 ? "this" : "these"}{" "}
            {open.length === 1 ? "element" : "elements"}. This is where the
            claim is most defensible.
          </p>
          <ul className="mt-3 space-y-2">
            {open.map((e) => (
              <li
                key={e.id}
                className="rounded-lg border-l-2 py-1.5 pl-3 text-[13px]"
                style={{ borderColor: "var(--absent)" }}
              >
                <span className="mono mr-2 text-[11px] text-[var(--text-faint)]">
                  {e.id}
                </span>
                <span className="font-medium">{e.label}</span>
                <p className="mt-0.5 text-[var(--text-muted)]">{e.text}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
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

  const nameOf = (id: string) =>
    elements.find((e) => e.id === id)?.label ?? id;

  return (
    <section className="rise rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <span className="eyebrow">Combination risk</span>
      <p className="mt-2 text-[13px] text-[var(--text-muted)]">
        Pairs that together read on more of the invention than either does
        alone — the shape of an obviousness rejection.
      </p>
      <ul className="mt-3 space-y-2.5">
        {combinations.map((c) => (
          <li
            key={c.ref_ids.join("+")}
            className="rounded-lg bg-[var(--surface-sunk)] px-3.5 py-3 text-[13px]"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="mono font-medium">{c.ref_ids.join(" + ")}</span>
              <span className="tnum text-[var(--text-muted)]">
                covers {Math.round(c.coverage_fraction * 100)}% of the invention
              </span>
            </div>
            {c.missing.length > 0 ? (
              <p className="mt-1 text-[var(--text-muted)]">
                Still missing: {c.missing.map(nameOf).join(", ")}.
              </p>
            ) : (
              <p className="mt-1" style={{ color: "var(--covered)" }}>
                Together these two reach every element you described.
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Search angles the agent generated — shown so the retrieval is auditable. */
export function Angles({ result }: { result: AnalyzeResult }) {
  return (
    <section className="rise rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <span className="eyebrow">Search angles</span>
      <p className="mt-2 text-[13px] text-[var(--text-muted)]">
        One embedding of a whole description averages away the specifics. These
        angles were searched separately and the rankings fused.
      </p>
      <ul className="mt-3 space-y-2">
        {result.queries.map((q) => (
          <li key={q.id} className="text-[13px]">
            <span className="mono mr-2 text-[11px] text-[var(--text-faint)]">
              {q.id}
            </span>
            <span className="font-medium">{q.angle}</span>
            <p className="mt-0.5 text-[var(--text-muted)]">{q.text}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Reference cards, expandable to the abstract and the per-element evidence. */
export function References({ result }: { result: AnalyzeResult }) {
  const [open, setOpen] = useState<string | null>(null);
  const byId = new Map<string, Element>(result.elements.map((e) => [e.id, e]));

  if (!result.references.length) {
    return (
      <section className="rounded-xl border border-dashed border-[var(--border)] p-6 text-center text-[13px] text-[var(--text-muted)]">
        No references retrieved. Is the index populated?
      </section>
    );
  }

  return (
    <section className="rise">
      <h2 className="mb-3 text-[15px] font-medium tracking-tight">
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
                <span className="mono mt-0.5 shrink-0 text-[11px] text-[var(--text-faint)]">
                  {r.ref_id}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] leading-snug">
                    {r.title}
                  </span>
                  {r.note && (
                    <span className="mt-1 block text-[12px] text-[var(--text-muted)]">
                      {r.note}
                    </span>
                  )}
                  <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--text-faint)]">
                    <span className="mono">{r.patent_id}</span>
                    <span className="tnum">relevance {r.relevance}</span>
                    <span>found by {r.found_by.join(", ")}</span>
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1 pt-0.5">
                  {r.coverage.map((c) => (
                    <span
                      key={c.element_id}
                      title={`${byId.get(c.element_id)?.label}: ${LEVEL_META[c.level].label}`}
                      className="text-[10px] leading-none"
                      style={{ color: `var(${LEVEL_META[c.level].varName})` }}
                    >
                      {LEVEL_META[c.level].glyph}
                    </span>
                  ))}
                </span>
              </button>

              {isOpen && (
                <div className="border-t border-[var(--border)] px-4 py-4 text-[13px]">
                  {hits.length > 0 && (
                    <ul className="mb-4 space-y-2.5">
                      {hits.map((c) => (
                        <li key={c.element_id}>
                          <div className="flex items-center gap-2">
                            <span
                              className="text-[10px]"
                              style={{
                                color: `var(${LEVEL_META[c.level].varName})`,
                              }}
                            >
                              {LEVEL_META[c.level].glyph}
                            </span>
                            <span className="text-[12px] font-medium">
                              {byId.get(c.element_id)?.label}
                            </span>
                            <span className="text-[11px] text-[var(--text-faint)]">
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
                  <p className="text-[12px] leading-relaxed text-[var(--text-muted)]">
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
