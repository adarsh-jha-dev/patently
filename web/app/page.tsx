import Link from "next/link";
import {
  ArrowRight,
  Code2,
  Quote,
  ScanSearch,
  ShieldQuestion,
  Split,
  Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { CorpusStat } from "@/components/CorpusStat";

export const metadata = {
  title: "Patently — prior art analysis, element by element",
  description:
    "Describe an invention in plain English and get a claim-element map of the prior art that reads on it, with the passage behind every finding.",
};

const REPO = "https://github.com/adarsh-jha-dev/patently";

export default function Landing() {
  return (
    <main className="mx-auto max-w-5xl px-5 sm:px-6">
      <nav className="flex items-center justify-between gap-4 py-6">
        <span className="flex items-center gap-2.5">
          <span
            aria-hidden
            className="grid size-8 place-items-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]"
          >
            <ScanSearch size={18} strokeWidth={2} />
          </span>
          <span className="text-lg font-semibold tracking-tight">Patently</span>
        </span>
        <span className="flex items-center gap-2">
          <Button variant="ghost" size="icon" asChild>
            <a href={REPO} target="_blank" rel="noreferrer" aria-label="Source on GitHub">
              <Code2 size={18} strokeWidth={1.9} />
            </a>
          </Button>
          <ThemeToggle />
        </span>
      </nav>

      {/* Hero */}
      <section className="py-14 sm:py-20">
        <p className="eyebrow">Prior art analysis</p>
        <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-[1.12] tracking-tight sm:text-5xl">
          A search box tells you what looks similar.
          <span className="block text-[var(--text-muted)]">
            This tells you which parts are already taken.
          </span>
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-[var(--text-muted)]">
          Describe an invention in plain English. Patently breaks it into the
          discrete features a novelty search has to clear, then shows which of
          them the prior art already teaches — every finding backed by a passage
          quoted verbatim from the patent it came from.
        </p>

        <div className="mt-9 flex flex-wrap items-center gap-3">
          <Button size="lg" asChild>
            <Link href="/analyze">
              Try it
              <ArrowRight size={17} strokeWidth={2} />
            </Link>
          </Button>
          <Button variant="secondary" size="lg" asChild>
            <a href={REPO} target="_blank" rel="noreferrer">
              <Code2 size={17} strokeWidth={1.9} />
              Read the code
            </a>
          </Button>
        </div>

        <CorpusStat />
      </section>

      {/* What makes it different */}
      <section className="border-t border-[var(--border)] py-14 sm:py-16">
        <h2 className="max-w-2xl text-2xl font-semibold tracking-tight">
          Four things a similarity search cannot give you
        </h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <Feature
            Icon={Split}
            title="Claim-element decomposition"
            body="Your description is split into the discrete technical features an independent claim's limitations decompose into — not treated as one blob of text."
          />
          <Feature
            Icon={Layers}
            title="Multi-angle retrieval"
            body="One embedding of a paragraph averages away the specifics that determine novelty. Patently searches 4–6 targeted angles and fuses the rankings."
          />
          <Feature
            Icon={Quote}
            title="Evidence you can check"
            body="Every filled cell carries a quote verified character-for-character against the source abstract. A citation that can't be located is downgraded automatically."
          />
          <Feature
            Icon={ShieldQuestion}
            title="It admits when it can't tell"
            body="When the corpus holds nothing close to your field, it says so rather than reporting a clean score. An absence of evidence is not evidence of novelty."
          />
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-[var(--border)] py-14 sm:py-16">
        <h2 className="text-2xl font-semibold tracking-tight">How it works</h2>
        <ol className="mt-8 grid gap-4 sm:grid-cols-4">
          {[
            ["Decompose", "One model call turns the disclosure into claim elements and search angles."],
            ["Retrieve", "Angles are embedded and searched in parallel, then fused by Reciprocal Rank Fusion."],
            ["Assess", "One model call maps every element against every candidate, with a quote for each."],
            ["Synthesise", "Grounding checks, whitespace, and §103 pairs — computed, not asked."],
          ].map(([title, body], i) => (
            <li key={title} className="relative">
              <span className="mono text-2xs text-[var(--text-faint)]">
                0{i + 1}
              </span>
              <h3 className="mt-1.5 text-base font-semibold">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-muted)]">
                {body}
              </p>
            </li>
          ))}
        </ol>
        <p className="mt-8 text-sm text-[var(--text-muted)]">
          Two model calls per analysis, regardless of how many candidates come
          back. Everything that can be computed is computed rather than asked.
        </p>
      </section>

      {/* Honest limits — deliberately on the landing page, not buried */}
      <section className="border-t border-[var(--border)] py-14 sm:py-16">
        <h2 className="text-2xl font-semibold tracking-tight">
          What it is not
        </h2>
        <ul className="mt-6 max-w-3xl space-y-3 text-base leading-relaxed text-[var(--text-muted)]">
          <li className="flex gap-3">
            <span aria-hidden className="text-[var(--text-faint)]">—</span>
            <span>
              It searches an indexed corpus of US patent abstracts ending around
              2014, not the full patent literature. A recent idea will honestly
              come back inconclusive.
            </span>
          </li>
          <li className="flex gap-3">
            <span aria-hidden className="text-[var(--text-faint)]">—</span>
            <span>
              Coverage is judged from abstracts, not full claim text. An abstract
              can omit something the claims teach.
            </span>
          </li>
          <li className="flex gap-3">
            <span aria-hidden className="text-[var(--text-faint)]">—</span>
            <span>
              It is a research tool, not a freedom-to-operate opinion, and not
              legal advice.
            </span>
          </li>
        </ul>

        <div className="mt-10">
          <Button size="lg" asChild>
            <Link href="/analyze">
              Analyse an invention
              <ArrowRight size={17} strokeWidth={2} />
            </Link>
          </Button>
        </div>
      </section>

      <footer className="border-t border-[var(--border)] py-8 text-sm text-[var(--text-faint)]">
        Built by{" "}
        <a
          href="https://github.com/adarsh-jha-dev"
          target="_blank"
          rel="noreferrer"
          className="underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--text)]"
        >
          Adarsh Jha
        </a>
      </footer>
    </main>
  );
}

function Feature({
  Icon,
  title,
  body,
}: {
  Icon: typeof Split;
  title: string;
  body: string;
}) {
  return (
    <Card className="p-5">
      <span
        aria-hidden
        className="grid size-9 place-items-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]"
      >
        <Icon size={18} strokeWidth={1.9} />
      </span>
      <h3 className="mt-3.5 text-base font-semibold tracking-tight">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-[var(--text-muted)]">
        {body}
      </p>
    </Card>
  );
}
