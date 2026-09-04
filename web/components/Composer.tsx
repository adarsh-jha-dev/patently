"use client";

import { useRef } from "react";

const EXAMPLES = [
  {
    label: "Vector cache",
    text: "A caching layer for LLM inference that stores prompt embeddings rather than exact prompt strings. Incoming prompts are embedded and matched against the cache by cosine similarity; a hit above a tuned threshold returns the stored completion. The threshold adapts per-tenant based on observed downstream correction rates, so tenants whose users frequently regenerate get a stricter threshold automatically.",
  },
  {
    label: "Battery thermals",
    text: "A battery pack thermal management system that routes coolant through phase-change material channels between cells. The pump rate is set by a model that predicts cell temperature 30 seconds ahead from current draw and ambient temperature, instead of reacting to measured cell temperature after it rises.",
  },
  {
    label: "Warehouse routing",
    text: "A warehouse robot fleet controller that assigns picking routes by auctioning each task among idle robots, where each robot bids using its own battery state and current congestion along its projected path. Bids are recomputed whenever an aisle blockage is detected, so routes re-plan without a central re-solve.",
  },
];

export function Composer({
  value,
  onChange,
  onSubmit,
  running,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  running: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const tooShort = value.trim().length < 40;

  return (
    <div>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] focus-within:border-[var(--border-strong)]">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            // Cmd/Ctrl+Enter submits — the field is long enough that a bare
            // Enter has to stay a newline.
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !tooShort) {
              e.preventDefault();
              onSubmit();
            }
          }}
          rows={7}
          disabled={running}
          placeholder="Describe your invention in plain English. What does it do, and how? The more specific the mechanism, the sharper the search."
          className="w-full resize-none bg-transparent p-4 text-[14px] leading-relaxed outline-none placeholder:text-[var(--text-faint)] disabled:opacity-60"
        />
        <div className="flex items-center justify-between gap-4 border-t border-[var(--border)] px-4 py-2.5">
          <span className="tnum text-[11px] text-[var(--text-faint)]">
            {value.trim().length} characters
            {tooShort && value.length > 0 && " · need at least 40"}
          </span>
          <button
            type="button"
            onClick={onSubmit}
            disabled={running || tooShort}
            className="rounded-md bg-[var(--text)] px-3.5 py-1.5 text-[13px] font-medium text-[var(--bg)] transition-opacity disabled:opacity-30"
          >
            {running ? "Analyzing…" : "Analyze"}
          </button>
        </div>
      </div>

      {!running && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[11px] text-[var(--text-faint)]">Try:</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              type="button"
              onClick={() => {
                onChange(ex.text);
                ref.current?.focus();
              }}
              className="rounded-full border border-[var(--border)] px-2.5 py-1 text-[11px] text-[var(--text-muted)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text)]"
            >
              {ex.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
