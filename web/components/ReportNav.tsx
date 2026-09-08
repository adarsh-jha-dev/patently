"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Section rail for the report, shown only from xl up.
 *
 * The point of the extra desktop width is structure, not longer lines — a
 * report this tall is hard to navigate by scrolling alone, and the rail gives
 * it a spine. Below xl there is no room for one and the page reverts to a
 * single column, where scrolling is the natural affordance anyway.
 *
 * Active section comes from an IntersectionObserver rather than scroll maths:
 * it stays correct when sections resize (references expand on click) without
 * recomputing offsets.
 */

export interface NavSection {
  id: string;
  label: string;
}

export function ReportNav({ sections }: { sections: NavSection[] }) {
  const [active, setActive] = useState(sections[0]?.id);

  useEffect(() => {
    const nodes = sections
      .map((s) => document.getElementById(s.id))
      .filter((n): n is HTMLElement => Boolean(n));
    if (!nodes.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        // The topmost section currently intersecting wins, so scrolling up and
        // down settles on the same answer.
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      // Bias the band toward the top of the viewport: the section you are
      // reading is the one just under the fold, not the one centred.
      { rootMargin: "-72px 0px -55% 0px", threshold: 0 },
    );

    nodes.forEach((n) => observer.observe(n));
    return () => observer.disconnect();
  }, [sections]);

  return (
    <nav aria-label="Report sections" className="sticky top-8">
      <p className="eyebrow mb-3">On this page</p>
      <ul className="space-y-0.5 border-l border-[var(--border)]">
        {sections.map((s) => {
          const on = s.id === active;
          return (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                aria-current={on ? "true" : undefined}
                className={cn(
                  "-ml-px block border-l-2 py-1.5 pl-3 text-sm transition-colors",
                  on
                    ? "border-[var(--accent)] font-medium text-[var(--text)]"
                    : "border-transparent text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text)]",
                )}
              >
                {s.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
