import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { notFound } from "next/navigation";
import { Report } from "@/components/Report";
import { ShareLink } from "@/components/ShareLink";
import type { AnalyzeResult } from "@/lib/types";

/** A saved analysis, by slug. Fetched server-side so it renders on first
 *  paint and the service URL stays off the client. */

export const dynamic = "force-dynamic";

const SERVICE_URL = process.env.EMBEDDINGS_URL ?? "http://127.0.0.1:8000";

interface Saved {
  slug: string;
  created_at: string;
  title: string;
  corpus: string;
  corpus_size: number;
  model: string;
  description: string;
  result: AnalyzeResult;
}

async function fetchSaved(slug: string): Promise<Saved | null> {
  try {
    const res = await fetch(
      `${SERVICE_URL}/analyses/${encodeURIComponent(slug)}`,
      { cache: "no-store", signal: AbortSignal.timeout(20_000) },
    );
    if (!res.ok) return null;
    return (await res.json()) as Saved;
  } catch {
    // Service down. Indistinguishable from "no such analysis" to the reader,
    // and a 404 is the less alarming of the two.
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const saved = await fetchSaved((await params).slug);
  return { title: saved ? `${saved.title} · Patently` : "Patently" };
}

export default async function SavedAnalysis({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const saved = await fetchSaved(slug);
  if (!saved) notFound();

  const when = new Date(saved.created_at).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <main className="mx-auto max-w-4xl px-6 py-14 sm:py-20">
      <header className="mb-8">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-[12px] text-[var(--text-muted)] transition-colors hover:text-[var(--text)]"
        >
          <ArrowLeft size={13} strokeWidth={2} />
          New analysis
        </Link>
        <h1 className="mt-4 text-[15px] font-medium tracking-tight">
          Saved analysis
        </h1>
        <p className="mt-1 text-[12px] text-[var(--text-faint)]">
          Run {when} · {saved.model}
        </p>
      </header>

      <div className="mb-8">
        <ShareLink slug={saved.slug} />
      </div>

      <details className="mb-8 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
        <summary className="cursor-pointer text-[12.5px] font-medium">
          The disclosure as submitted
        </summary>
        <p className="mt-3 whitespace-pre-wrap text-[13px] leading-relaxed text-[var(--text-muted)]">
          {saved.description}
        </p>
      </details>

      <Report
        result={saved.result}
        corpus={{ name: saved.corpus, size: saved.corpus_size }}
      />
    </main>
  );
}
