import { ApiError, request, segment } from "./httpClient";
import type { CvAnalysis, CvApi, CvLayout } from "./cvTypes";

/** null for a 404 (no analysis / no layout yet); every other error is thrown as is. */
async function orNull<T>(call: Promise<T>): Promise<T | null> {
  try {
    return await call;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

const BASE_URL = (import.meta.env["VITE_API_BASE_URL"] ?? "").replace(/\/$/, "");

/**
 * "Mes CV" through the local FastAPI backend (api/cvs.py). Single entry point used by every
 * component: no demo data, no fallback — errors (backend down, 404, 409, 422) are surfaced as they are.
 */
export const cvApi: CvApi = {
  listCvs: () => request("GET", "/cvs"),
  getCv: (id) => request("GET", `/cvs/${segment(id)}`),
  getAnalysis: (id) => orNull(request<CvAnalysis>("GET", `/cvs/${segment(id)}/analysis`)),
  getLayout: (id) => orNull(request<CvLayout>("GET", `/cvs/${segment(id)}/layout`)),
  pdfUrl: (id, version) =>
    `${BASE_URL}/api/cvs/${segment(id)}/pdf${version ? `?v=${version}` : ""}`,
  updateCv: (id, document) => request("PUT", `/cvs/${segment(id)}`, document),
  async deleteCv(id) {
    await request("DELETE", `/cvs/${segment(id)}`);
  },
  startGeneration: (url) => request("POST", "/cvs/generate", { url }),
  startAnalysis: (id) => request("POST", `/cvs/${segment(id)}/analysis`),
  getTask: (taskId) => request("GET", `/cvs/tasks/${segment(taskId)}`),
};

export { ApiError } from "./httpClient";
export * from "./cvTypes";
