import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnalysisTab } from "@/features/cvs/components/AnalysisTab";
import type { CompletedAnalysis } from "@/services/api/cvTypes";
import { analysisFixture, summary, task } from "./fixtures/cvFixtures";

/** Fake FastAPI backend: `routes` maps "METHOD /path" to [status, body] (a list = successive answers). */
function fakeBackend(routes: Record<string, [number, unknown] | [number, unknown][]>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const key = `${init.method ?? "GET"} ${url}`;
      calls.push(key);
      const route = routes[key];
      const answer = Array.isArray(route?.[0])
        ? ((route as [number, unknown][]).shift() ?? route[0])
        : route;
      if (!answer)
        return new Response(JSON.stringify({ detail: { message: "?", problems: [key] } }), {
          status: 500,
        });
      const [status, body] = answer as [number, unknown];
      return new Response(body === undefined ? null : JSON.stringify(body), { status });
    }),
  );
  return calls;
}

function renderTab(cv = summary()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AnalysisTab cv={cv} />
    </QueryClientProvider>,
  );
}

const ANALYSIS = "/api/cvs/fictive-corp-data-engineer/analysis";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AnalysisTab", () => {
  it("shows the saved analysis without the fit score", async () => {
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysisFixture(), running: false }] });
    const { container } = renderTab();
    expect(
      await screen.findByText("Construire des pipelines de données fictifs."),
    ).toBeInTheDocument();
    expect(screen.getByText("Python en production")).toBeInTheDocument();
    expect(screen.getAllByText("Connaissance de Kafka").length).toBeGreaterThan(0);
    expect(screen.getByText("Préparer un exemple de pipeline.")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/73|score|adéquation\s*:/i);
  });

  it("organizes the analysis without changing its content", async () => {
    const analysis = analysisFixture();
    analysis.overview.possible_tasks = [
      "Par exemple, tu pourrais écrire un job Spark",
      "Tu pourrais aussi documenter les flux",
      "Revue de code hebdomadaire",
    ];
    analysis.recommendations = [
      { category: "cv", text: "Mettre Kafka en avant dans le CV.", requirement_ids: [] },
      { category: "interview", text: "Préparer un exemple de pipeline.", requirement_ids: [] },
      { category: "learning", text: "Suivre un tutoriel Kafka.", requirement_ids: [] },
      { category: "obstacle", text: "Stage de 6 mois obligatoire.", requirement_ids: [] },
    ];
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();

    // Missions open by default, the other parts folded (with a chevron trigger)
    expect(await screen.findByText("Concevoir des flux de données")).toBeVisible();
    const tasks = screen.getByRole("button", { name: /Exemples de tâches possibles/ });
    expect(tasks).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: /Technologies et compétences/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    fireEvent.click(tasks);
    expect(await screen.findByText("Écrire un job Spark")).toBeVisible();
    expect(screen.getByText("Documenter les flux")).toBeVisible();
    expect(screen.getByText("Revue de code hebdomadaire")).toBeVisible();
    expect(screen.getByText(/ce poste pourrait vous amener à/)).toBeVisible();
    expect(screen.queryByText(/tu pourrais/i)).not.toBeInTheDocument();

    // Strengths keep their evidence, weaknesses their status
    expect(screen.getByText("Stagiaire data")).toBeInTheDocument();
    expect(screen.getByText("Non remplie")).toBeInTheDocument();
    expect(screen.getByText("Exigence souhaitée")).toBeInTheDocument();

    // « Préparer ma candidature » without the "cv" recommendations
    expect(screen.getByText("Préparer ma candidature")).toBeInTheDocument();
    expect(screen.getByText("Préparer un exemple de pipeline.")).toBeVisible();
    expect(screen.getByText("Suivre un tutoriel Kafka.")).toBeVisible();
    expect(screen.getByText("Stage de 6 mois obligatoire.")).toBeVisible();
    expect(screen.queryByText("Mettre Kafka en avant dans le CV.")).not.toBeInTheDocument();
    expect(screen.queryByText("Améliorer le CV")).not.toBeInTheDocument();

    // Requirements detail stays folded
    expect(screen.getByRole("button", { name: /Voir les 2 exigences/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("handles an analysis without strengths, weaknesses or shown recommendations", async () => {
    const analysis = analysisFixture();
    analysis.strengths = [];
    analysis.weaknesses = [];
    analysis.recommendations = [
      { category: "cv", text: "Seulement pour le CV.", requirement_ids: [] },
    ];
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();
    expect(await screen.findByText(/Aucun point fort/)).toBeInTheDocument();
    expect(screen.getByText(/Aucun point faible/)).toBeInTheDocument();
    expect(screen.queryByText("Préparer ma candidature")).not.toBeInTheDocument();
    expect(screen.queryByText("Seulement pour le CV.")).not.toBeInTheDocument();
  });

  it("clamps a long explanation with a toggle, never hiding it for good", async () => {
    // jsdom has no layout: a long text is "taller" than its three clamped lines
    vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(function (
      this: HTMLElement,
    ) {
      return (this.textContent?.length ?? 0) > 200 ? 120 : 40;
    });
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(60);
    const analysis = analysisFixture();
    const long = "Explication très détaillée. ".repeat(12).trim();
    analysis.strengths[0]!.explanation = long;
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();
    const text = await screen.findByText(long);
    expect(text).toHaveClass("line-clamp-3");
    fireEvent.click(screen.getByRole("button", { name: "Lire la suite" }));
    expect(text).not.toHaveClass("line-clamp-3");
    fireEvent.click(screen.getByRole("button", { name: "Réduire" }));
    expect(text).toHaveClass("line-clamp-3");
    // a short explanation that fits gets no toggle
    expect(screen.getAllByRole("button", { name: "Lire la suite" })).toHaveLength(1);
  });

  it("keeps working with an analysis saved before the interview questions", async () => {
    const analysis = analysisFixture();
    expect(analysis.interview_questions).toBeUndefined();
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();
    expect(await screen.findByText("Préparer un exemple de pipeline.")).toBeVisible();
    expect(screen.queryByText("Questions possibles")).not.toBeInTheDocument();
  });

  it("shows the interview questions folded, with their details on click", async () => {
    const analysis: CompletedAnalysis = {
      ...analysisFixture(),
      recommendations: [],
      interview_questions: [
        {
          kind: "gap",
          question: "Avez-vous déjà utilisé Kafka en production ?",
          purpose: "Vérifier l'autonomie sur le streaming.",
          answer_guidance: [
            "Dire honnêtement que le profil ne le montre pas.",
            "Relier au pipeline Spark.",
          ],
          evidence: [
            { type: "experience", id: "exp-a", label: "Stagiaire data", justification: "" },
          ],
          topics_to_review: ["Kafka", "Partitions"],
          requirement_ids: ["r2"],
        },
        {
          kind: "motivation",
          question: "Pourquoi ce poste de data engineer ?",
          purpose: "Comprendre la motivation.",
          answer_guidance: ["Partir des missions de l'offre."],
          evidence: [],
          topics_to_review: [],
          requirement_ids: [],
        },
      ],
    };
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();

    // The block exists even without "interview" recommendations; questions are visible, details folded
    expect(await screen.findByText("Questions possibles")).toBeVisible();
    expect(screen.getByText(/le recruteur ne les posera pas forcément/)).toBeVisible();
    const question = screen.getByRole("button", {
      name: /Avez-vous déjà utilisé Kafka en production/,
    });
    expect(question).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Pourquoi ce poste de data engineer ?")).toBeVisible();
    expect(screen.queryByText("Vérifier l'autonomie sur le streaming.")).not.toBeInTheDocument();

    fireEvent.click(question);
    expect(await screen.findByText("Vérifier l'autonomie sur le streaming.")).toBeVisible();
    expect(screen.getByText("Dire honnêtement que le profil ne le montre pas.")).toBeVisible();
    expect(screen.getByText("Partitions")).toBeVisible();
    expect(screen.getAllByText("Stagiaire data").length).toBeGreaterThan(1); // strength + question evidence
    // linked requirement keeps its own status (missing here, distinct from "not documented")
    const linked = screen.getByText("Exigence liée").parentElement!;
    expect(linked).toHaveTextContent("Connaissance de Kafka");
    expect(linked).toHaveTextContent("Non remplie");

    fireEvent.click(question);
    await waitFor(() =>
      expect(screen.queryByText("Vérifier l'autonomie sur le streaming.")).not.toBeInTheDocument(),
    );
  });

  it("offers to launch the analysis when there is none, then follows the task", async () => {
    const calls = fakeBackend({
      [`GET ${ANALYSIS}`]: [
        [404, { detail: { message: "Analyse non disponible", problems: ["aucune analyse"] } }],
        [200, { ...analysisFixture(), running: false }],
      ],
      [`POST ${ANALYSIS}`]: [202, { task_id: "t9", status: "pending" }],
      "GET /api/cvs/tasks/t9": [
        200,
        task({ task_id: "t9", kind: "analysis", status: "completed", step: "done" }),
      ],
      "GET /api/cvs": [200, [summary()]],
    });
    renderTab(summary({ analysis_status: "missing" }));
    fireEvent.click(await screen.findByRole("button", { name: /Analyser cette candidature/ }));
    expect(
      await screen.findByText("Construire des pipelines de données fictifs."),
    ).toBeInTheDocument();
    expect(calls).toContain(`POST ${ANALYSIS}`);
    expect(calls).toContain("GET /api/cvs/tasks/t9");
  });

  it("shows a failed analysis with its message and a relaunch button", async () => {
    fakeBackend({
      [`GET ${ANALYSIS}`]: [
        200,
        {
          schema_version: 1,
          status: "failed",
          generated_at: "x",
          error: { message: "Claude n'a pas répondu", problems: ["délai dépassé"] },
          running: false,
        },
      ],
    });
    renderTab(summary({ analysis_status: "failed" }));
    expect(await screen.findByText(/Claude n'a pas répondu délai dépassé/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Relancer l'analyse/ })).toBeInTheDocument();
  });

  it("shows the 409 of a CV without offer instead of a fake success", async () => {
    fakeBackend({
      [`GET ${ANALYSIS}`]: [
        404,
        { detail: { message: "Analyse non disponible", problems: ["aucune"] } },
      ],
      [`POST ${ANALYSIS}`]: [
        409,
        { detail: { message: "Analyse impossible", problems: ["offer.json inconnu"] } },
      ],
    });
    renderTab(summary({ analysis_status: "missing" }));
    fireEvent.click(await screen.findByRole("button", { name: /Analyser cette candidature/ }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Analyser cette candidature/ })).toBeEnabled(),
    );
    expect(screen.queryByText(/Analyse terminée/)).not.toBeInTheDocument();
    expect(screen.getByText("Analyse non effectuée")).toBeInTheDocument();
  });
});
