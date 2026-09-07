"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
] as const;

/**
 * Three-way theme control.
 *
 * A segmented control rather than a two-state switch, because "follow my OS"
 * is a distinct answer from either colour — a toggle silently collapses it and
 * leaves people unable to say "match my system".
 *
 * Renders a fixed-size placeholder until mounted: the active theme is only
 * known on the client, and swapping in the real control without reserving the
 * space shifts the header on hydration.
 */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return <div aria-hidden className="h-9 w-[104px] rounded-lg" />;
  }

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="inline-flex items-center gap-0.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-0.5"
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            className={cn(
              "inline-flex size-8 items-center justify-center rounded-md transition-colors",
              active
                ? "bg-[var(--surface-sunk)] text-[var(--text)]"
                : "text-[var(--text-faint)] hover:text-[var(--text-muted)]",
            )}
          >
            <Icon size={16} strokeWidth={1.9} />
          </button>
        );
      })}
    </div>
  );
}
