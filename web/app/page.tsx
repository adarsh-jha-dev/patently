"use client";

import { useCallback, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { RubricForm } from "@/components/RubricForm";
import { Progress } from "@/components/Progress";
import { Report } from "@/components/Report";
import { ShareLink } from "@/components/ShareLink";
import { EMPTY_RUBRIC, type RubricValues } from "@/lib/rubric";
import type { AnalyzeResult, Plan } from "@/lib/types";

export default function Home() {
  const [text, setText] = useState("");
  const [rubric, setRubric] = useState<RubricValues>(EMPTY_RUBRIC);
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState("");
  const [message, setMessage] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    setText("");
    setRubric(EMPTY_RUBRIC);
    setError(null);
  }, []);

  const backToForm = useCallback(() => {
    setResult(null);
    setPlan(null);
    setError(null);
  }, []);

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
        // The rubric rides alongside the description. Fields the user marked
        // "not sure" are sent as-is and dropped server-side, so the client
        // never has to decide what counts as knowledge.
        body: JSON.stringify({ description: text, rubric }),
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
  }, [text, rubric]);

  return (
    <main className="mx-auto max-w-4xl px-6 py-14 sm:py-20">
      <header className="mb-8">
        <h1 className="text-[15px] font-medium tracking-tight">Patently</h1>
        <p className="mt-1 max-w-xl text-[14px] leading-relaxed text-[var(--text-muted)]">
          Describe an invention. Get back which parts of it the prior art
          already teaches — element by element, with the passage behind every
          finding.
        </p>
      </header>

      {error && (
        <div
          role="alert"
          className="mb-6 rounded-lg border px-4 py-3 text-[13px]"
          style={{
            borderColor: "var(--covered)",
            background: "var(--covered-tint)",
          }}
        >
          {error}
        </div>
      )}

      {running && (
        <Progress stage={stage} message={message} plan={plan} />
      )}

      {!running && !result && (
        <RubricForm
          description={text}
          onDescription={setText}
          values={rubric}
          onChange={setRubric}
          onSubmit={run}
          onReset={reset}
          running={running}
        />
      )}

      {!running && result && (
        <div className="space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button
              type="button"
              onClick={backToForm}
              className="inline-flex items-center gap-1.5 text-[12px] text-[var(--text-muted)] transition-colors hover:text-[var(--text)]"
            >
              <ArrowLeft size={13} strokeWidth={2} />
              Back to the form
            </button>
          </div>

          {/* Only offered when the analysis was actually filed — a link that
              404s is worse than no link. */}
          {result.slug && <ShareLink slug={result.slug} />}

          <Report result={result} />
        </div>
      )}

    </main>
  );
}
