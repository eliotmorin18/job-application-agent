import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, cvApi } from "@/services/api/cvApi";
import { documentFixture, summary } from "./fixtures/cvFixtures";

type Call = { url: string; method: string; body: unknown };

/** Replaces fetch by a fake backend answering `status` + JSON `body`, and records the calls. */
function fakeFetch(status: number, body?: unknown): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({
        url,
        method: init.method ?? "GET",
        body: init.body ? JSON.parse(String(init.body)) : undefined,
      });
      return new Response(body === undefined ? null : JSON.stringify(body), { status });
    }),
  );
  return calls;
}

const backendError = (message: string, problems: string[]) => ({ detail: { message, problems } });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("cvApi (HTTP, no mock fallback)", () => {
  it("lists the CVs from GET /api/cvs", async () => {
    const calls = fakeFetch(200, [summary()]);
    await expect(cvApi.listCvs()).resolves.toEqual([summary()]);
    expect(calls).toEqual([{ url: "/api/cvs", method: "GET", body: undefined }]);
  });

  it("returns an empty list as is (no demo CV)", async () => {
    fakeFetch(200, []);
    await expect(cvApi.listCvs()).resolves.toEqual([]);
  });

  it("reports a backend that cannot be reached instead of falling back to demo data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await cvApi.listCvs().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).message).toContain("Impossible de joindre l'API locale");
  });

  it("treats a 5xx without JSON from the Vite proxy as a backend that is down", async () => {
    fakeFetch(502);
    const error = (await cvApi.listCvs().catch((e: unknown) => e)) as ApiError;
    expect(error.message).toContain("Impossible de joindre l'API locale");
  });

  it("rejects with 409 and the backend title for a CV created before cv.json", async () => {
    fakeFetch(
      409,
      backendError("CV non modifiable", [
        "ce CV a été créé avant cv.json : seul son PDF est consultable.",
      ]),
    );
    const error = (await cvApi.getCv("old-cv").catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(409);
    expect(error.title).toBe("CV non modifiable");
    expect(error.problems).toEqual([
      "ce CV a été créé avant cv.json : seul son PDF est consultable.",
    ]);
  });

  it("returns null when there is no analysis or no layout (404), and throws other errors", async () => {
    fakeFetch(404, backendError("Analyse non disponible", ["aucune analyse"]));
    await expect(cvApi.getAnalysis("x")).resolves.toBeNull();
    await expect(cvApi.getLayout("x")).resolves.toBeNull();
    fakeFetch(500, backendError("Erreur", ["boom"]));
    await expect(cvApi.getAnalysis("x")).rejects.toBeInstanceOf(ApiError);
  });

  it("sends the whole document on PUT and surfaces 422 problems", async () => {
    const calls = fakeFetch(
      422,
      backendError("La compilation a échoué : la version précédente du CV a été conservée.", [
        "Undefined control sequence.",
      ]),
    );
    const error = (await cvApi
      .updateCv("fictive", documentFixture())
      .catch((e: unknown) => e)) as ApiError;
    expect(calls[0]).toMatchObject({
      url: "/api/cvs/fictive",
      method: "PUT",
      body: documentFixture(),
    });
    expect(error.status).toBe(422);
    expect(error.title).toContain("version précédente");
    expect(error.message).toBe("Undefined control sequence.");
  });

  it("deletes with DELETE and surfaces 404 / 409", async () => {
    const calls = fakeFetch(204);
    await expect(cvApi.deleteCv("fictive")).resolves.toBeUndefined();
    expect(calls[0]).toMatchObject({ url: "/api/cvs/fictive", method: "DELETE" });

    fakeFetch(404, backendError("CV introuvable", ["aucun CV « fictive »."]));
    await expect(cvApi.deleteCv("fictive")).rejects.toMatchObject({ status: 404 });
    fakeFetch(
      409,
      backendError("Suppression impossible pour le moment", ["une génération est en cours"]),
    );
    await expect(cvApi.deleteCv("fictive")).rejects.toMatchObject({
      status: 409,
      title: "Suppression impossible pour le moment",
    });
  });

  it("starts generation and analysis tasks and polls them", async () => {
    let calls = fakeFetch(202, { task_id: "t1", status: "pending" });
    await cvApi.startGeneration("https://jobs.example.com/1");
    expect(calls[0]).toMatchObject({
      url: "/api/cvs/generate",
      method: "POST",
      body: { url: "https://jobs.example.com/1" },
    });
    calls = fakeFetch(202, { task_id: "t2", status: "pending" });
    await cvApi.startAnalysis("fictive");
    expect(calls[0]).toMatchObject({ url: "/api/cvs/fictive/analysis", method: "POST" });
    calls = fakeFetch(200, { task_id: "t2" });
    await cvApi.getTask("t2");
    expect(calls[0]!.url).toBe("/api/cvs/tasks/t2");
  });

  it("surfaces a refused URL (422)", async () => {
    fakeFetch(422, backendError("URL refusée", ["adresse privée refusée"]));
    await expect(cvApi.startGeneration("http://127.0.0.1")).rejects.toMatchObject({
      status: 422,
      title: "URL refusée",
    });
  });

  it("encodes ids and versions the PDF URL", () => {
    expect(cvApi.pdfUrl("a b/c")).toBe("/api/cvs/a%20b%2Fc/pdf");
    expect(cvApi.pdfUrl("cv", 1792000100.25)).toBe("/api/cvs/cv/pdf?v=1792000100.25");
  });
});
