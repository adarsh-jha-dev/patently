const SERVICE_URL = process.env.EMBEDDINGS_URL ?? "http://127.0.0.1:8000";

/**
 * The live corpus size, on the landing page.
 *
 * Reads the real indexed count rather than hardcoding a number that will drift
 * the moment the corpus changes. Renders nothing if the service is unreachable
 * — a landing page should not fail because a backend is cold.
 */
async function count(): Promise<number | null> {
  try {
    const res = await fetch(`${SERVICE_URL}/health`, {
      next: { revalidate: 600 },
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { indexed_points?: number };
    return data.indexed_points && data.indexed_points > 0
      ? data.indexed_points
      : null;
  } catch {
    return null;
  }
}

export async function CorpusStat() {
  const points = await count();
  if (!points) return null;

  return (
    <dl className="mt-12 flex flex-wrap gap-x-12 gap-y-6">
      <div>
        <dt className="text-2xs text-[var(--text-faint)]">Patents indexed</dt>
        <dd className="tnum mt-1 text-2xl font-semibold tracking-tight">
          {points.toLocaleString()}
        </dd>
      </div>
      <div>
        <dt className="text-2xs text-[var(--text-faint)]">Model calls per analysis</dt>
        <dd className="tnum mt-1 text-2xl font-semibold tracking-tight">2</dd>
      </div>
      <div>
        <dt className="text-2xs text-[var(--text-faint)]">Typical run</dt>
        <dd className="tnum mt-1 text-2xl font-semibold tracking-tight">
          ~15s
        </dd>
      </div>
    </dl>
  );
}
