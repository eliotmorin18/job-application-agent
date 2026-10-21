import { httpCandidateApi, httpImportApi } from "./httpCandidateApi";
import { mockCandidateApi } from "./mockCandidateApi";
import type { CandidateApi, ImportApi } from "./types";

/**
 * Single entry point used by every UI component.
 * - VITE_API_MODE=http (default): local FastAPI backend (api/main.py), real profile.
 * - VITE_API_MODE=mock: in-memory demo data, no backend needed.
 */
const MOCK = import.meta.env["VITE_API_MODE"] === "mock";

export const candidateApi: CandidateApi = MOCK ? mockCandidateApi : httpCandidateApi;

const importUnavailable = () =>
  Promise.reject(new Error("L'import de CV nécessite l'API locale (VITE_API_MODE=http)."));

export const importApi: ImportApi = MOCK
  ? {
      listImports: async () => [],
      importCv: importUnavailable,
      getReview: importUnavailable,
      applyImport: importUnavailable,
    }
  : httpImportApi;

export { ApiError } from "./httpClient";
export * from "./types";
