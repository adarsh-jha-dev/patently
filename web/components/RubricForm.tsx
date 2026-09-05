"use client";

import { motion } from "motion/react";
import { ArrowRight, Check } from "lucide-react";
import { useMemo } from "react";
import { cn } from "@/lib/utils";
import {
  ChoiceAnswer,
  FieldShell,
  TextAnswer,
} from "@/components/ui/form-primitives";
import {
  ALL_FIELDS,
  EMPTY_RUBRIC,
  MIN_DESCRIPTION,
  SECTIONS,
  UNSURE,
  completion,
  isAnswered,
  knownCount,
  sectionAnswered,
  type RubricValues,
} from "@/lib/rubric";

/**
 * One scrolling column rather than a wizard — nine short questions is less
 * daunting than an unknown number of steps. Progress sits in a sticky footer.
 */

interface Example {
  label: string;
  description: string;
  rubric: RubricValues;
}

const EXAMPLES: Example[] = [
  {
    label: "Vector cache",
    description:
      "A caching layer for LLM inference that stores prompt embeddings rather than exact prompt strings. Incoming prompts are embedded and matched against the cache by cosine similarity; a hit above a tuned threshold returns the stored completion. The threshold adapts per-tenant based on observed downstream correction rates, so tenants whose users frequently regenerate get a stricter threshold automatically.",
    rubric: {
      field: "Software and computing",
      kind: "System or architecture",
      components:
        "an embedding model; a vector store of prompt embeddings; a similarity matcher; a per-tenant threshold controller driven by regeneration rates",
      io: "in: a prompt and a tenant id. out: either a cached completion or a cache miss",
      prior_approach:
        "exact-string or hash-keyed prompt caching, which misses on any rewording",
      novelty:
        "the similarity threshold is tuned per tenant from observed correction behaviour rather than fixed globally",
      context: "Cloud or datacenter",
    },
  },
  {
    label: "Battery thermals",
    description:
      "A battery pack thermal management system that routes coolant through phase-change material channels between cells. The pump rate is set by a model that predicts cell temperature 30 seconds ahead from current draw and ambient temperature, instead of reacting to measured cell temperature after it rises.",
    rubric: {
      field: "Energy, power and storage",
      kind: "System or architecture",
      components:
        "phase-change material channels between cells; a coolant pump; a predictive controller",
      io: "in: current draw and ambient temperature. out: pump rate",
      prior_approach:
        "reactive thermostat control that responds after cell temperature has already risen",
      novelty:
        "predicting the temperature rise 30 seconds ahead rather than reacting to it",
      context: "Vehicle or mobile platform",
    },
  },
  {
    label: "Warehouse routing",
    description:
      "A warehouse robot fleet controller that assigns picking routes by auctioning each task among idle robots, where each robot bids using its own battery state and current congestion along its projected path. Bids are recomputed whenever an aisle blockage is detected, so routes re-plan without a central re-solve.",
    rubric: {
      field: "Mechanical and industrial systems",
      kind: "Method or process",
      components:
        "a task auctioneer; per-robot bidding using battery state and projected path congestion; a blockage detector that triggers re-auction",
      io: "in: picking tasks, robot battery states, aisle congestion. out: task assignments",
      prior_approach:
        "a central planner that re-solves the whole fleet assignment when anything changes",
      novelty: "re-planning through local re-bidding instead of a central re-solve",
      context: "Industrial or factory floor",
    },
  },
];

export function RubricForm({
  description,
  onDescription,
  values,
  onChange,
  onSubmit,
  onReset,
  running,
}: {
  description: string;
  onDescription: (v: string) => void;
  values: RubricValues;
  onChange: (next: RubricValues) => void;
  onSubmit: () => void;
  onReset: () => void;
  running: boolean;
  }) {
  const status = useMemo(
    () => completion(values, description),
    [values, description],
  );
  const known = knownCount(values);
  const set = (id: keyof RubricValues, v: string) =>
    onChange({ ...values, [id]: v });

  const applyExample = (ex: Example) => {
    onDescription(ex.description);
    onChange({ ...EMPTY_RUBRIC, ...ex.rubric });
  };

  const descriptionShort =
    description.trim().length > 0 && !status.descriptionOk;

  return (
    <div className="pb-28">
      {/* Description first: it carries the mechanism, and everything the
          rubric collects only qualifies it. */}
      <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <div className="mb-2.5 flex flex-wrap items-center gap-1.5">
          <span
            aria-hidden
            className={cn(
              "size-1.5 shrink-0 rounded-full transition-colors",
              status.descriptionOk
                ? "bg-[var(--accent)]"
                : "bg-[var(--border-strong)]",
            )}
          />
          <span className="text-[13px] font-medium">Describe your invention</span>
        </div>
        <textarea
          value={description}
          onChange={(e) => onDescription(e.target.value)}
          onKeyDown={(e) => {
            // Cmd/Ctrl+Enter submits. A bare Enter has to stay a newline in a
            // field this size.
            if (
              (e.metaKey || e.ctrlKey) &&
              e.key === "Enter" &&
              status.complete &&
              !running
            ) {
              e.preventDefault();
              onSubmit();
            }
          }}
          rows={6}
          disabled={running}
          placeholder="What does it do, and how? Plain English is fine — the more specific the mechanism, the sharper the search."
          className="w-full resize-none rounded-lg border border-[var(--border)] bg-[var(--bg)] p-3 text-[14px] leading-relaxed outline-none transition-colors placeholder:text-[var(--text-faint)] focus:border-[var(--border-strong)] disabled:opacity-60"
        />
        <div className="mt-1.5 flex items-center justify-between gap-3">
          <span className="tnum text-[11px] text-[var(--text-faint)]">
            {description.trim().length} characters
            {descriptionShort && ` · need at least ${MIN_DESCRIPTION}`}
          </span>
          {!running && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-[var(--text-faint)]">
                Fill an example:
              </span>
              {EXAMPLES.map((ex) => (
                <button
                  key={ex.label}
                  type="button"
                  onClick={() => applyExample(ex)}
                  className="rounded-full border border-[var(--border)] px-2.5 py-1 text-[11px] text-[var(--text-muted)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text)]"
                >
                  {ex.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      {SECTIONS.map((section, i) => {
        const done = sectionAnswered(section, values);
        const full = done === section.fields.length;
        return (
          <motion.section
            key={section.title}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.3,
              delay: 0.04 * i,
              ease: [0.22, 1, 0.36, 1],
            }}
            className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5"
          >
            <header className="mb-1 flex items-baseline justify-between gap-4 border-b border-[var(--border)] pb-3">
              <div>
                <h2 className="text-[13.5px] font-medium tracking-tight">
                  {section.title}
                </h2>
                <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">
                  {section.caption}
                </p>
              </div>
              <span
                className={cn(
                  "tnum inline-flex shrink-0 items-center gap-1 text-[11px]",
                  full ? "text-[var(--accent)]" : "text-[var(--text-faint)]",
                )}
              >
                {full && <Check size={12} strokeWidth={2.5} />}
                {done}/{section.fields.length}
              </span>
            </header>

            <div className="divide-y divide-[var(--border)]">
              {section.fields.map((f) => (
                <FieldShell
                  key={f.id}
                  label={f.label}
                  help={f.help}
                  answered={isAnswered(values[f.id])}
                >
                  {f.type === "choice" ? (
                    <ChoiceAnswer
                      options={f.options}
                      value={values[f.id]}
                      onChange={(v) => set(f.id, v)}
                      unsureLabel={f.unsureLabel}
                      disabled={running}
                    />
                  ) : (
                    <TextAnswer
                      value={values[f.id]}
                      onChange={(v) => set(f.id, v)}
                      placeholder={f.placeholder}
                      unsureLabel={f.unsureLabel}
                      disabled={running}
                    />
                  )}
                </FieldShell>
              ))}
            </div>
          </motion.section>
        );
      })}

      {/* Sticky submit. The gate is completion, not knowledge: nine answers,
          any of which may be "not sure". */}
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-[var(--border)] bg-[var(--bg)]/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-4xl items-center gap-4 px-6 py-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <span className="tnum text-[12px] font-medium">
                {status.answered}/{status.total}
              </span>
              <span className="truncate text-[11.5px] text-[var(--text-faint)]">
                {status.complete
                  ? known === ALL_FIELDS.length
                    ? "Every question answered."
                    : `${ALL_FIELDS.length - known} answered “not sure” — those axes will be searched broadly.`
                  : "Answer every question to run the analysis."}
              </span>
            </div>
            <div className="mt-1.5 h-[3px] w-full overflow-hidden rounded-full bg-[var(--surface-sunk)]">
              <motion.div
                className="h-full rounded-full bg-[var(--accent)]"
                initial={false}
                animate={{ width: `${(status.answered / status.total) * 100}%` }}
                transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
          </div>

          {status.answered > 0 && !running && (
            <button
              type="button"
              onClick={onReset}
              className="shrink-0 text-[12px] text-[var(--text-faint)] transition-colors hover:text-[var(--text)]"
            >
              Clear
            </button>
          )}

          <button
            type="button"
            onClick={onSubmit}
            disabled={running || !status.complete}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-[var(--text)] px-4 py-2 text-[13px] font-medium text-[var(--bg)] transition-opacity disabled:opacity-25"
          >
            {running ? "Analyzing…" : "Analyze"}
            {!running && <ArrowRight size={14} strokeWidth={2} />}
          </button>
        </div>
      </div>
    </div>
  );
}
