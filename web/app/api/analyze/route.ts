import { NextRequest } from "next/server";

const SERVICE_URL = process.env.EMBEDDINGS_URL ?? "http://127.0.0.1:8000";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// An analysis is 12-30s warm. Vercel's Hobby ceiling is 60s for a standard
// function (300s with Fluid Compute), and streamed bytes count toward it.
export const maxDuration = 60;

// Long enough to absorb a slow analysis, short enough to fail before the
// platform kills the function without explanation. A sleeping free-tier
// container can take longer than this to wake, which is the case the timeout
// message is written for.
const UPSTREAM_TIMEOUT_MS = 55_000;

/**
 * Proxies the analysis stream from the Python service.
 *
 * Going through a route handler rather than calling the service from the
 * browser keeps its URL and any future auth server-side, and means the browser
 * only ever talks to one origin.
 */
export async function POST(req: NextRequest) {
  const body = await req.text();
  const abort = AbortSignal.timeout(UPSTREAM_TIMEOUT_MS);

  let upstream: Response;
  try {
    upstream = await fetch(`${SERVICE_URL}/analyze/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      signal: abort,
    });
  } catch (e) {
    const timedOut = (e as Error)?.name === "TimeoutError";
    return sseError(
      timedOut
        ? "The analysis service didn't respond in time. It sleeps when idle and can take a minute to wake — try once more."
        : `Cannot reach the analysis service. If you're running locally: cd embeddings && uvicorn main:app --port 8000`,
    );
  }

  // 429 is expected in the public deployment, not a fault — the service caps
  // analyses per visitor and per day because they run on one shared API key.
  // Its body already says which limit was hit and when it resets.
  if (upstream.status === 429) {
    const detail = await upstream.text().catch(() => "");
    return sseError(extractDetail(detail) ?? "Rate limit reached. Try again later.");
  }

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    return sseError(
      extractDetail(detail) ?? `Service returned ${upstream.status}.`,
    );
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}

/** FastAPI wraps errors as {"detail": "..."}; show that rather than raw JSON. */
function extractDetail(body: string): string | null {
  try {
    const parsed = JSON.parse(body);
    if (typeof parsed?.detail === "string") return parsed.detail;
  } catch {
    // Not JSON — fall through to the caller's default.
  }
  return body.trim() ? body.slice(0, 300) : null;
}

/** Surface failures as an SSE `error` event so the client has one code path. */
function sseError(message: string) {
  const payload = `event: error\ndata: ${JSON.stringify({ message })}\n\n`;
  return new Response(payload, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}
