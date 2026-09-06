import { Analyzer } from "@/components/Analyzer";
import { CorpusNote } from "@/components/CorpusNote";

/**
 * Server shell around the client-side analyzer.
 *
 * Exists so CorpusNote can be a server component — it reads the live indexed
 * point count from the service, which should not become a client round trip on
 * every page load. Passing it down as a node is the standard way to nest a
 * server component inside a client one.
 */
export default function Page() {
  return <Analyzer corpusNote={<CorpusNote />} />;
}
