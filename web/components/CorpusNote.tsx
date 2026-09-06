const SERVICE_URL = process.env.EMBEDDINGS_URL ?? "http://127.0.0.1:8000";

/**
 * What the visitor is actually searching, stated before they type.
 *
 * Without this the deployed demo has a bad first run built into it: someone
 * tries a 2024 idea, gets "Inconclusive" because BIGPATENT stops around 2014,
 * and reasonably concludes the tool is broken rather than honest. Saying the
 * corpus size and vintage up front turns that from a failure into an expected
 * result.
 *
 * Server-rendered and failure-tolerant: if the service is asleep or
 * unreachable this renders nothing rather than blocking the page, since the
 * form still works once the service wakes.
 */

interface Health {
  indexed_points: number | null;
  store_mode: string | null;
}

async function fetchHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${SERVICE_URL}/health`, {
      // Cached briefly: the count only changes when the corpus is re-indexed,
      // and this should not add a round trip to every page view.
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return null;
    return (await res.json()) as Health;
  } catch {
    return null;
  }
}

export async function CorpusNote() {
  const health = await fetchHealth();
  const points = health?.indexed_points;
  if (!points || points < 0) return null;

  return (
    <p className="mt-3 text-[12px] leading-relaxed text-[var(--text-faint)]">
      Searching <span className="tnum">{points.toLocaleString()}</span> US patent
      abstracts (BIGPATENT, subset G — physics and computing, grants through
      roughly 2014). Nothing filed after that is in the index, so a recent idea
      will honestly come back inconclusive.
    </p>
  );
}
