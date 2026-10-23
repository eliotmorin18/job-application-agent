import type { CvSummary } from "@/services/api/cvTypes";

/** Formats a Unix timestamp (seconds, as returned by FastAPI) as "18 oct. 2026"; "Date inconnue" without a date. */
export function formatTimestamp(seconds: number | null | undefined): string {
  const d = new Date((seconds ?? NaN) * 1000);
  if (seconds === null || seconds === undefined || Number.isNaN(d.getTime()))
    return "Date inconnue";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(d);
}

/** Title of an application: the job title of the offer, else the role written in the CV, else its folder name. */
export function applicationTitle(cv: Pick<CvSummary, "id" | "role" | "job_title">): string {
  return cv.job_title || cv.role || cv.id;
}

// "Par exemple, tu pourrais …", "Tu pourrais aussi …", "For example, you could …"
const TASK_PREFIX =
  /^\s*(?:(?:par exemple|for example|e\.g\.)\s*[,:]?\s*)?(?:(?:tu pourrais|vous pourriez|tu pourras|vous pourrez|you could|you might)\s+(?:(?:aussi|également|also)\s+)?)?/i;

/**
 * Display-only text of an "exemple de tâche possible" without its repeated opening
 * ("Par exemple, tu pourrais dépouiller…" -> "Dépouiller…"). The list is introduced once as hypothetical,
 * so the meaning is kept; analysis.json is not changed. A text without that opening is returned as is.
 */
export function taskText(text: string): string {
  const rest = text.replace(TASK_PREFIX, "").trim();
  if (!rest || rest === text.trim()) return text.trim();
  return rest.charAt(0).toLocaleUpperCase("fr-FR") + rest.slice(1);
}

const SHORT_MONTHS = [
  "janv.",
  "févr.",
  "mars",
  "avr.",
  "mai",
  "juin",
  "juil.",
  "août",
  "sept.",
  "oct.",
  "nov.",
  "déc.",
];

/** "2026-03" -> "mars 2026", "2026-03-13" -> "13 mars 2026". */
export function sourceDate(value: string | null): string | null {
  const match = value?.match(/^(\d{4})-(\d{2})(?:-(\d{2}))?$/);
  if (!match) return null;
  const month = SHORT_MONTHS[Number(match[2]) - 1];
  if (!month) return null;
  return [match[3] ? String(Number(match[3])) : null, month, match[1]].filter(Boolean).join(" ");
}

// A sentence ends with . ! ? or … followed by a space and an upper-case letter (or an opening quote).
const SENTENCE_BREAK = /(?<=[.!?…])\s+(?=[A-ZÀ-ÖØ-Þ«"“])/u;

/**
 * Splits a text after its first `count` sentences ("Vue d'ensemble": short summary first, the rest on
 * demand). Display only: `lead` + " " + `rest` gives back the whole text; `rest` is "" when nothing is cut;
 * `count` is the number of sentences of the whole text.
 */
/** Sentences of a text (none for an empty text). */
export function splitSentences(text: string): string[] {
  return text.trim() ? text.trim().split(SENTENCE_BREAK) : [];
}

export function leadSentences(
  text: string,
  count: number,
): { lead: string; rest: string; count: number } {
  const sentences = splitSentences(text);
  return {
    lead: sentences.slice(0, count).join(" "),
    rest: sentences.slice(count).join(" "),
    count: sentences.length,
  };
}
