import type { Plan } from "@/lib/types";

const STAGES = [
  { key: "decompose", label: "Reading the invention" },
  { key: "retrieve", label: "Searching prior art" },
  { key: "assess", label: "Mapping claim elements" },
] as const;

/**
 * Progress rail.
 *
 * The decomposition is streamed and shown as soon as it lands, before search
 * results exist. That is deliberate: seeing the claim elements early is how
 * you tell whether the system understood your invention, and it makes a
 * 20-second wait feel like it is doing something rather than hanging.
 */
export function Progress({
  stage,
  message,
  plan,
}: {
  stage: string;
  message: string;
  plan: Plan | null;
}) {
  const index = STAGES.findIndex((s) => stage.startsWith(s.key));
  const current = index === -1 ? (stage === "retrieved" ? 1 : 0) : index;

  return (
    <div className="rise space-y-5">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <ol className="space-y-2.5">
          {STAGES.map((s, i) => {
            const done = i < current;
            const active = i === current;
            return (
              <li
                key={s.key}
                className="flex items-center gap-3 text-[13px]"
                style={{
                  color: done
                    ? "var(--text-muted)"
                    : active
                      ? "var(--text)"
                      : "var(--text-faint)",
                }}
              >
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${active ? "pulse-soft" : ""}`}
                  style={{
                    background: done
                      ? "var(--text-faint)"
                      : active
                        ? "var(--accent)"
                        : "var(--border-strong)",
                  }}
                />
                <span>{active && message ? message : s.label}</span>
              </li>
            );
          })}
        </ol>
      </div>

      {plan && (
        <div className="rise rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <span className="eyebrow">Claim elements</span>
          <p className="mt-1.5 text-[13px] text-[var(--text-muted)]">
            {plan.restatement}
          </p>
          <ul className="mt-3 space-y-1.5">
            {plan.elements.map((e) => (
              <li key={e.id} className="text-[13px]">
                <span className="mono mr-2 text-[11px] text-[var(--text-faint)]">
                  {e.id}
                </span>
                <span className="font-medium">{e.label}</span>
                <span className="text-[var(--text-muted)]"> — {e.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
