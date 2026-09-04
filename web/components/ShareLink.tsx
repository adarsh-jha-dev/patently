"use client";

import { Check, Link2 } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Copy the permalink for a saved analysis.
 *
 * The URL is built in an effect rather than during render because it depends
 * on `window.location.origin`, which does not exist during the server pass —
 * reading it inline would hydrate mismatched.
 */
export function ShareLink({ slug }: { slug: string }) {
  const [url, setUrl] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setUrl(`${window.location.origin}/a/${slug}`);
  }, [slug]);

  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1800);
    return () => clearTimeout(t);
  }, [copied]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      // Clipboard is permission-gated and blocked outright in some embedded
      // contexts. The input beside the button still holds the URL, so failing
      // silently here leaves the user with a working manual path.
    }
  };

  return (
    <div className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2">
      <Link2
        size={13}
        strokeWidth={1.75}
        className="shrink-0 text-[var(--text-faint)]"
      />
      <input
        readOnly
        value={url}
        onFocus={(e) => e.currentTarget.select()}
        aria-label="Permalink to this analysis"
        className="mono min-w-0 flex-1 bg-transparent text-[11.5px] text-[var(--text-muted)] outline-none"
      />
      <button
        type="button"
        onClick={copy}
        className={cn(
          "inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-medium transition-colors",
          copied
            ? "text-[var(--absent)]"
            : "text-[var(--text-muted)] hover:text-[var(--text)]",
        )}
      >
        {copied ? <Check size={12} strokeWidth={2.5} /> : null}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
