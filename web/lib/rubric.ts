/**
 * The guided disclosure form.
 *
 * Every field here has to earn its place by changing the search, because each
 * one is a question a nervous first-time inventor has to answer before they
 * get anything back. The test is simple: if the analysis would be identical
 * whether or not the field were answered, the field should not exist.
 *
 *   field, context   set the terminology the query angles are written in
 *   kind             decides whether elements decompose as steps or structure
 *   components, io   supply the mechanism detail a paragraph usually omits
 *   prior_approach   supplies the closest-art angle, the hardest one to guess
 *   novelty          orders the elements so the claimed advance is tested first
 *
 * The free-text description is deliberately NOT duplicated here as a
 * "mechanism" field — asking the same question twice just teaches people to
 * paste the same paragraph into both boxes.
 *
 * `UNSURE` is a first-class answer, not a skip. A novice who cannot name their
 * technical field must still be able to complete the form, and saying so
 * explicitly is more honest than a blank that could mean either "unknown" or
 * "not looked at yet". The backend drops these before building the prompt, so
 * an unknown never becomes a wrong prior — see patently/analyze.py.
 */

export const UNSURE = "unsure";

export type RubricId =
  | "field"
  | "kind"
  | "components"
  | "io"
  | "prior_approach"
  | "novelty"
  | "context";

export type RubricValues = Record<RubricId, string>;

interface Base {
  id: RubricId;
  label: string;
  help: string;
  /** Wording of the escape hatch. "No idea" reads less like a failure than
   *  "Not sure" on the one question a novice is most likely to stall on. */
  unsureLabel: string;
}

export type RubricField =
  | (Base & { type: "choice"; options: string[] })
  | (Base & { type: "text"; placeholder: string });

export interface RubricSection {
  title: string;
  caption: string;
  fields: RubricField[];
}

export const SECTIONS: RubricSection[] = [
  {
    title: "The invention",
    caption: "Sets the vocabulary the search is written in.",
    fields: [
      {
        id: "field",
        type: "choice",
        label: "Technical field",
        help: "Patents in different fields describe the same mechanism with completely different words. This picks which vocabulary to search in.",
        unsureLabel: "Not sure",
        options: [
          "Software and computing",
          "Signal and data processing",
          "Electronics and hardware",
          "Optics, imaging and sensing",
          "Mechanical and industrial systems",
          "Materials and chemistry",
          "Biotech and medical devices",
          "Energy, power and storage",
        ],
      },
      {
        id: "kind",
        type: "choice",
        label: "What form does it take?",
        help: "A process breaks down into ordered steps; a device breaks down into parts and how they connect. This decides how your invention is split up.",
        unsureLabel: "Not sure",
        options: [
          "Method or process",
          "Device or apparatus",
          "System or architecture",
          "Software or algorithm",
          "Material or composition",
        ],
      },
    ],
  },
  {
    title: "How it works",
    caption: "The mechanism detail a paragraph usually leaves out.",
    fields: [
      {
        id: "components",
        type: "text",
        label: "Key parts or steps",
        help: "The main pieces and how they connect, or the steps in order. Rough notes are fine — this is not claim language.",
        unsureLabel: "Not sure",
        placeholder:
          "e.g. a phase-change coolant channel between cells; a pump; a controller that predicts cell temperature 30s ahead",
      },
      {
        id: "io",
        type: "text",
        label: "What goes in, what comes out",
        help: "For a process or algorithm, its inputs and outputs. For a device, what it takes in and what it produces.",
        unsureLabel: "Not sure",
        placeholder: "e.g. in: current draw and ambient temperature. out: pump rate",
      },
    ],
  },
  {
    title: "What makes it different",
    caption: "The part a search engine cannot infer on its own.",
    fields: [
      {
        id: "prior_approach",
        type: "text",
        label: "Closest existing way this is done today",
        help: "How would someone solve this without your invention? This is the single most useful answer on the form — it points the search straight at the art most likely to conflict. A rough guess beats nothing.",
        unsureLabel: "No idea",
        placeholder:
          "e.g. a thermostat that reacts after cell temperature has already risen",
      },
      {
        id: "novelty",
        type: "text",
        label: "What you think is new",
        help: "The one thing you would point to if someone told you this already exists. Treated as a hypothesis to test, never as a finding.",
        unsureLabel: "Not sure",
        placeholder: "e.g. predicting the temperature rise instead of reacting to it",
      },
      {
        id: "context",
        type: "choice",
        label: "Where does it run?",
        help: "The operating context narrows which of several near-identical mechanisms is actually yours.",
        unsureLabel: "Not sure",
        options: [
          "On-device or embedded",
          "Cloud or datacenter",
          "Industrial or factory floor",
          "Consumer product",
          "Laboratory or clinical",
          "Vehicle or mobile platform",
          "Networked or distributed",
        ],
      },
    ],
  },
];

export const ALL_FIELDS: RubricField[] = SECTIONS.flatMap((s) => s.fields);

export const EMPTY_RUBRIC: RubricValues = Object.fromEntries(
  ALL_FIELDS.map((f) => [f.id, ""]),
) as RubricValues;

/** Minimum description length the API will accept (AnalyzeRequest.description). */
export const MIN_DESCRIPTION = 40;

export const isAnswered = (v: string | undefined) => Boolean(v && v.trim());

/**
 * Completion for the submit gate: every rubric field carries a value, and the
 * description clears the API's minimum. "Not sure" counts as answered — the
 * gate is there to stop someone submitting a half-read form, not to force
 * knowledge they do not have.
 */
export function completion(values: RubricValues, description: string) {
  const answered = ALL_FIELDS.filter((f) => isAnswered(values[f.id])).length;
  const total = ALL_FIELDS.length + 1; // + the description
  const descriptionOk = description.trim().length >= MIN_DESCRIPTION;
  return {
    answered: answered + (descriptionOk ? 1 : 0),
    total,
    descriptionOk,
    complete: answered === ALL_FIELDS.length && descriptionOk,
  };
}

export function sectionAnswered(section: RubricSection, values: RubricValues) {
  return section.fields.filter((f) => isAnswered(values[f.id])).length;
}

/** How much real signal the user gave, ignoring the "not sure" answers. */
export function knownCount(values: RubricValues) {
  return ALL_FIELDS.filter(
    (f) => isAnswered(values[f.id]) && values[f.id] !== UNSURE,
  ).length;
}
