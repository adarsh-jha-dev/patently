export type CoverageLevel = "covered" | "partial" | "absent";

/** Mirrors patently.schemas.Rubric. Values are the human-readable answer text,
 *  or the literal "unsure" sentinel, which the backend drops before prompting. */
export interface Rubric {
  field: string;
  kind: string;
  components: string;
  io: string;
  prior_approach: string;
  novelty: string;
  context: string;
}

export interface Element {
  id: string;
  label: string;
  text: string;
}

export interface Query {
  id: string;
  angle: string;
  text: string;
}

export interface ElementCoverage {
  element_id: string;
  level: CoverageLevel;
  quote: string;
  quote_verified: boolean;
}

export interface Reference {
  ref_id: string;
  patent_id: string;
  title: string;
  abstract: string;
  score: number;
  found_by: string[];
  relevance: number;
  note: string;
  coverage: ElementCoverage[];
}

export interface ElementRisk {
  element_id: string;
  level: CoverageLevel;
  covered_by: string[];
  partial_by: string[];
}

export interface Combination {
  ref_ids: string[];
  covers: string[];
  missing: string[];
  coverage_fraction: number;
}

export interface Verdict {
  novelty_score: number;
  label: string;
  anticipation_risk: number;
  combination_risk: number;
  summary: string;
  conclusive: boolean;
  top_relevance: number;
}

export interface AnalyzeResult {
  title: string;
  restatement: string;
  elements: Element[];
  queries: Query[];
  references: Reference[];
  element_risk: ElementRisk[];
  whitespace: string[];
  combinations: Combination[];
  verdict: Verdict;
  stats: Record<string, number>;
  elapsed_ms?: number;
  /** Present once the analysis has been saved; absent when DATABASE_URL is
   *  unset, in which case there is nothing to link to. */
  slug?: string | null;
}

/** The decomposition arrives before the results, so the UI can show it early. */
export interface Plan {
  title: string;
  restatement: string;
  elements: Element[];
  queries: Query[];
}

export const LEVEL_META: Record<
  CoverageLevel,
  { glyph: string; label: string; varName: string; tint: string }
> = {
  // Glyphs are mandatory, not decorative: the status palette must never carry
  // meaning by colour alone (CVD, print, forced-colors).
  covered: { glyph: "●", label: "Taught", varName: "--covered", tint: "--covered-tint" },
  partial: { glyph: "◐", label: "Adjacent", varName: "--partial", tint: "--partial-tint" },
  absent: { glyph: "○", label: "Not found", varName: "--none-ink", tint: "--none-tint" },
};
