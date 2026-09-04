import { NextRequest } from "next/server";

const SERVICE_URL = process.env.EMBEDDINGS_URL ?? "http://127.0.0.1:8000";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Proxies the analysis stream from the Python service.
 *
 * Going through a route handler rather than calling the service from the
 * browser keeps its URL and any future auth server-side, and means the
 * browser only ever talks to one origin.
 */
export async function POST(req: NextRequest) {
  const body = await req.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${SERVICE_URL}/analyze/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch {
    return sseError(
      `Cannot reach the embeddings service at ${SERVICE_URL}. Start it with: cd embeddings && uvicorn main:app --port 8000`,
    );
  }

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    return sseError(`Service returned ${upstream.status}. ${detail.slice(0, 300)}`);
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}

/** Surface failures as an SSE `error` event so the client has one code path. */
function sseError(message: string) {
  const payload = `event: error\ndata: ${JSON.stringify({ message })}\n\n`;
  return new Response(payload, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}
