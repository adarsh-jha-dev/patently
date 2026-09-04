"use client";

import { useCallback, useRef, useState } from "react";
import { Composer } from "@/components/Composer";
import { Progress } from "@/components/Progress";
import { VerdictPanel } from "@/components/Verdict";
import { CoverageMatrix } from "@/components/CoverageMatrix";
import { Angles, Combinations, References, Whitespace } from "@/components/Findings";
import type { AnalyzeResult, Plan } from "@/lib/types";

export default function Home() {
  const [text, setText] = useState("");
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState("");
  const [message, setMessage] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  const run = useCallback(async () => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;

    setRunning(true);
    setError(null);
    setResult(null);
    setPlan(null);
    setStage("decompose");
    setMessage("");

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: text }),
        signal: controller.signal,
      });
      if (!res.body) throw new Error("No response stream");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // Minimal SSE parser. EventSource can't POST, and the payload is a
      // single-shot stream, so hand-parsing the frames is less machinery than
      // reworking the API into a GET with the description in the query string.
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let split: number;
        while ((split = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, split);
          buffer = buffer.slice(split + 2);

          let event = "message";
          const dataLines: string[] = [];
          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
          }
          if (!dataLines.length) continue;

          let data: Record<string, unknown>;
          try {
            data = JSON.parse(dataLines.join("\n"));
          } catch {
            continue;
          }

          if (event === "error") {
            setError(String(data.message ?? "Analysis failed"));
            setRunning(false);
            return;
          }
          if (event === "plan") {
            setPlan(data as unknown as Plan);
          }
          if (event === "result") {
            setResult(data as unknown as AnalyzeResult);
            setRunning(false);
            return;
          }
          setStage(event);
          if (typeof data.message === "string") setMessage(data.message);
        }
      }
      setRunning(false);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError((e as Error).message);
      }
      setRunning(false);
    }
  }, [text]);

  return (
    <main className="mx-auto max-w-4xl px-6 py-14 sm:py-20">
      <header className="mb-10">
        <h1 className="text-[15px] font-medium tracking-tight">Patently</h1>
        <p className="mt-1 max-w-xl text-[14px] leading-relaxed text-[var(--text-muted)]">
          Describe an invention. Get back which parts of it the prior art
          already teaches — element by element, with the passage behind every
          finding.
        </p>
      </header>

      <Composer
        value={text}
        onChange={setText}
        onSubmit={run}
        running={running}
      />

      {error && (
        <div
          role="alert"
          className="mt-8 rounded-lg border px-4 py-3 text-[13px]"
          style={{
            borderColor: "var(--covered)",
            background: "var(--covered-tint)",
          }}
        >
          {error}
        </div>
      )}

      {running && (
        <div className="mt-10">
          <Progress stage={stage} message={message} plan={plan} />
        </div>
      )}

      {result && (
        <div className="mt-12 space-y-8">
          <VerdictPanel result={result} />
          <CoverageMatrix result={result} />
          <div className="grid items-start gap-4 md:grid-cols-2">
            <Whitespace result={result} />
            <Combinations result={result} />
          </div>
          <References result={result} />
          <Angles result={result} />

          <footer className="border-t border-[var(--border)] pt-5 text-[11px] leading-relaxed text-[var(--text-faint)]">
            <p>
              {result.stats.llm_calls} model calls ·{" "}
              {result.stats.pool} patents reached ·{" "}
              {result.stats.assessed} assessed
              {result.elapsed_ms
                ? ` · ${(result.elapsed_ms / 1000).toFixed(1)}s`
                : ""}
            </p>
            <p className="mt-1.5 max-w-2xl">
              Patently searches an indexed corpus, not the full patent
              literature — an empty result means nothing was found in what was
              indexed, not that nothing exists. This is a research tool and not
              a freedom-to-operate opinion or legal advice.
            </p>
          </footer>
        </div>
      )}
    </main>
  );
}
