// Minimal fetch wrapper for the local FastAPI backend (api/main.py).
// In development, Vite proxies /api to http://127.0.0.1:8000 (see vite.config.ts).

const BASE_URL = (import.meta.env["VITE_API_BASE_URL"] ?? "").replace(/\/$/, "");

const UNREACHABLE =
  "Impossible de joindre l'API locale. Lance-la depuis la racine du projet : uvicorn api.main:app --reload";

/**
 * Error returned by the API: `problems` are the readable messages of the Python backend,
 * `title` its short summary (detail.message, e.g. "CV non modifiable"), empty when there is none.
 */
export class ApiError extends Error {
  status: number;
  problems: string[];
  title: string;

  constructor(status: number, message: string, problems: string[], title = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.problems = problems;
    this.title = title;
  }
}

function problemsFrom(body: unknown): string[] {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return [detail];
  if (Array.isArray(detail)) {
    // FastAPI validation error: [{loc, msg}, ...]
    return detail.map((d) => String((d as { msg?: unknown }).msg ?? d));
  }
  const problems = (detail as { problems?: unknown } | undefined)?.problems;
  return Array.isArray(problems) ? problems.map(String) : [];
}

/** Encodes one URL segment (skills or languages may contain "/", "#", spaces...). */
export const segment = (value: string) => encodeURIComponent(value);

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  let response: Response;
  try {
    const init: RequestInit = { method };
    if (isForm) init.body = body;
    else if (body !== undefined) {
      init.body = JSON.stringify(body);
      init.headers = { "Content-Type": "application/json" };
    }
    response = await fetch(`${BASE_URL}/api${path}`, init);
  } catch {
    throw new ApiError(0, UNREACHABLE, [UNREACHABLE]);
  }

  const text = await response.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!response.ok) {
    // The Vite proxy answers 5xx without JSON when the backend is not running
    if (data === null && response.status >= 500)
      throw new ApiError(response.status, UNREACHABLE, [UNREACHABLE]);
    const problems = problemsFrom(data);
    const message = problems.length ? problems.join(" ") : `Erreur ${response.status}`;
    const title = (data as { detail?: { message?: unknown } } | null)?.detail?.message;
    throw new ApiError(
      response.status,
      message,
      problems.length ? problems : [message],
      typeof title === "string" ? title : "",
    );
  }
  return data as T;
}
