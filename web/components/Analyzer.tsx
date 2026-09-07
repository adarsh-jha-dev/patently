"use client";

import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { ArrowLeft, ScanSearch, TriangleAlert } from "lucide-react";
import { RubricForm } from "@/components/RubricForm";
import { Progress } from "@/components/Progress";
import { Report } from "@/components/Report";
import { ShareLink } from "@/components/ShareLink";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Button } from "@/components/ui/button";
import { EMPTY_RUBRIC, type RubricValues } from "@/lib/rubric";
import type { AnalyzeResult, Plan } from "@/lib/types";

export function Analyzer({ corpusNote }: { corpusNote?: React.ReactNode }) {
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
    <main className="mx-auto max-w-4xl px-5 py-10 sm:px-6 sm:py-16">
      <header className="mb-10">
        <div className="mb-7 flex items-start justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <Link href="/" aria-label="Patently home" className="flex items-center gap-2.5">
              <span
              aria-hidden
              className="grid size-8 place-items-center rounded-lg bg-(--accent-soft) text-accent"
            >
              <ScanSearch size={18} strokeWidth={2} />
            </span>
            <span className="text-lg font-semibold tracking-tight">Patently</span>
            </Link>
          </div>
          <ThemeToggle />
        </div>

        <h1 className="max-w-2xl text-2xl font-semibold tracking-tight">
          Which parts of your invention does the prior art already teach?
        </h1>
        <p className="mt-3 max-w-2xl text-lg leading-relaxed text-[var(--text-muted)]">
          Describe it in plain English. You get back a claim-element map — each
          finding backed by a passage quoted verbatim from the patent it came
          from.
        </p>
        {corpusNote}
      </header>

      {error && (
        <div
          role="alert"
          className="mb-6 flex items-start gap-3 rounded-xl border px-4 py-3.5 text-sm leading-relaxed"
          style={{
            borderColor: "var(--covered)",
            background: "var(--covered-tint)",
          }}
        >
          <TriangleAlert
            size={17}
            strokeWidth={2}
            className="mt-0.5 shrink-0"
            style={{ color: "var(--covered)" }}
          />
          <span>{error}</span>
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
            <Button variant="ghost" size="sm" onClick={backToForm}>
              <ArrowLeft size={15} strokeWidth={2} />
              Back to the form
            </Button>
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
