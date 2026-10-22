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
