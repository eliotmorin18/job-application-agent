import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InterviewQuestions } from "@/features/cvs/components/InterviewQuestions";
import { OverviewTab } from "@/features/cvs/components/OverviewTab";
import type { CompletedAnalysis } from "@/services/api/cvTypes";
import { analysisFixture, summary, task } from "./fixtures/cvFixtures";

/** Fake FastAPI backend: `routes` maps "METHOD /path" to [status, body] (a list = successive answers). */
function fakeBackend(routes: Record<string, [number, unknown] | [number, unknown][]>) {
  const calls: string[] = [];
  // No deep interview preparation unless a test says otherwise (read only, never generated here).
  routes = {
    [`GET ${PREPARATION}`]: [
      404,
      { detail: { message: "Préparation non disponible", problems: [] } },
    ],
    ...routes,
  };
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
      <OverviewTab cv={cv} />
    </QueryClientProvider>,
  );
}

const ANALYSIS = "/api/cvs/fictive-corp-data-engineer/analysis";
const PREPARATION = "/api/cvs/fictive-corp-data-engineer/preparation";

const column = (title: string) => screen.getByRole("region", { name: title }) as HTMLElement;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("OverviewTab", () => {
  it("shows the job and the profile side by side, without the fit score", async () => {
    const calls = fakeBackend({
      [`GET ${ANALYSIS}`]: [200, { ...analysisFixture(), running: false }],
    });
    const { container } = renderTab();
    await screen.findByRole("heading", { name: "Le poste et l'entreprise" });

    const job = within(column("Le poste et l'entreprise"));
    expect(job.getByText("Le poste en bref")).toBeVisible();
    // No company activity without a preparation that kept one from the offer: never guessed
    expect(job.queryByText("L'entreprise")).not.toBeInTheDocument();
    expect(job.getByText("Construire des pipelines de données fictifs.")).toBeVisible();
    expect(job.getByText("Concevoir des flux de données")).toBeVisible();
    expect(job.getByText("Écrire un job Spark")).toBeVisible();
    expect(job.getByText("Exemples de tâches possibles")).toBeVisible();
    expect(job.getByText("Spark")).toBeVisible();
    expect(job.getByText("SQL")).toBeVisible();
    // The offer link lives in the page header only
    expect(job.queryByRole("link")).not.toBeInTheDocument();
    // The "plain explanation" overlaps the examples: not repeated in the main view
    expect(job.queryByText(/Vous déplacez et nettoyez/)).not.toBeInTheDocument();

    const profile = within(column("Mon profil pour ce poste"));
    expect(profile.getByText("Python en production")).toBeVisible();
    expect(profile.getByText("Stage data.")).toBeVisible();
    // Evidence references stay in the requirements detail, not in the main view
    expect(profile.queryByText(/Appuyé sur/)).not.toBeInTheDocument();
    expect(profile.queryByText("Stagiaire data")).not.toBeInTheDocument();
    // Kafka is only "preferred": it stays in the requirements detail, not in the attention points
    expect(profile.queryByText("Points d'attention")).not.toBeInTheDocument();
    expect(profile.queryByText(/Connaissance de Kafka/)).not.toBeInTheDocument();

    expect(container.textContent).not.toMatch(/73|score|adéquation\s*:/i);
    // Reading only: the analysis and the (absent) preparation, nothing is generated
    expect([...calls].sort()).toEqual([`GET ${ANALYSIS}`, `GET ${PREPARATION}`]);
  });

  it("groups the requirements, one line each, the detail opening under the line", async () => {
    const analysis = analysisFixture();
    const base = analysis.requirements[0]!;
    const rigour = "Rigueur dans l'évaluation (choix des métriques, analyse des erreurs)";
    analysis.requirements = [
      {
        ...base,
        id: "r1",
        source: "must_have",
        importance: "high",
        explanation: "Utilisé en stage. Plusieurs pipelines.",
      },
      {
        ...base,
        id: "r5a",
        text: "Rigueur dans l'évaluation (choix des métriques)",
        source: "must_have",
        importance: "high",
        parent_id: "r5",
        parent_text: rigour,
        explanation: "Métriques choisies en projet.",
        evidence: [],
      },
      {
        ...base,
        id: "r5b",
        text: "Rigueur dans l'évaluation (analyse des erreurs)",
        source: "must_have",
        importance: "high",
        parent_id: "r5",
        parent_text: rigour,
        status: "not_documented",
        explanation: "Pas mentionnée dans le profil.",
        evidence: [],
      },
      {
        ...base,
        id: "r3",
        text: "Bac+5 en informatique",
        source: "education",
        importance: "normal",
        explanation: "",
        evidence: [],
      },
      {
        ...analysis.requirements[1]!,
        source: "nice_to_have",
        explanation: "Rien dans le profil. Aucun projet de streaming.",
      },
    ];
    const calls = fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();
    const trigger = await screen.findByRole("button", { name: /Exigences détaillées\s*4/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Maîtrise de Python")).not.toBeInTheDocument();
    const requestsBefore = calls.length;
    fireEvent.click(trigger);

    // Counters: one per line, the parts are not counted twice
    expect(screen.getByText("2 remplies · 1 non remplie · 1 à plusieurs statuts")).toBeVisible();
    // Obligatoires, then Essentielles, then Souhaitées
    const headings = screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent);
    expect(headings).toEqual(["Obligatoires", "Essentielles", "Souhaitées"]);
    const essential = screen.getByText("Essentielles").closest("div")!;
    expect(within(essential).getByText("Maîtrise de Python")).toBeVisible();
    expect(within(essential).getByText(rigour)).toBeVisible();
    // A split requirement is one line; without a reliable overall status, its statuses are counted
    expect(within(essential).getByText("1 remplie · 1 non documentée")).toBeVisible();
    // Closed lines show no justification
    expect(screen.getByText("Rien dans le profil. Aucun projet de streaming.")).not.toBeVisible();
    expect(within(essential).getByText("Pas mentionnée dans le profil.")).not.toBeVisible();

    // The detail opens right under the line: each criterion with its own status, one line at a time
    const rigourRow = screen.getByRole("button", {
      name: new RegExp("Rigueur dans l'évaluation \\(choix des métriques, analyse"),
    });
    expect(rigourRow.tagName).toBe("BUTTON"); // Enter / Space natively
    rigourRow.focus();
    expect(rigourRow).toHaveFocus();
    fireEvent.click(rigourRow);
    expect(rigourRow).toHaveAttribute("aria-expanded", "true");
    const detail = document.getElementById(rigourRow.getAttribute("aria-controls")!)!;
    expect(rigourRow.closest("li")).toContainElement(detail);
    expect(
      within(detail).getByText("Rigueur dans l'évaluation (analyse des erreurs)"),
    ).toBeVisible();
    expect(within(detail).getByText("Non documentée")).toBeVisible();
    expect(within(detail).getByText("Pas mentionnée dans le profil.")).toBeVisible();
    expect(within(detail).getByText("Remplie")).toBeVisible();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    const python = screen.getByRole("button", { name: /Maîtrise de Python/ });
    fireEvent.click(python);
    expect(rigourRow).toHaveAttribute("aria-expanded", "false");
    expect(detail).not.toBeVisible();
    const pythonDetail = document.getElementById(python.getAttribute("aria-controls")!)!;
    expect(within(pythonDetail).getByText("Utilisé en stage. Plusieurs pipelines.")).toBeVisible();
    expect(within(pythonDetail).getByText(/Dans ton profil/)).toHaveTextContent(
      "Dans ton profil : Stagiaire data",
    );
    fireEvent.click(python);
    expect(python).toHaveAttribute("aria-expanded", "false");
    // A line without any detail is not a button
    expect(screen.queryByRole("button", { name: /Bac\+5/ })).not.toBeInTheDocument();
    expect(calls.length).toBe(requestsBefore);
  });

  it("explains alternatives in the detail and settles them without artificial gaps", async () => {
    const analysis = analysisFixture();
    const text = "Expérience en détection, tracking ou calibration de caméra";
    const base = { ...analysis.requirements[1]!, parent_id: "r9", parent_text: text, evidence: [] };
    analysis.requirements = [
      analysis.requirements[0]!,
      { ...base, id: "r9a", text: "Expérience en détection", status: "met" },
      { ...base, id: "r9b", text: "Expérience en tracking", status: "not_documented" },
      { ...base, id: "r9c", text: "Expérience en calibration de caméra", status: "not_documented" },
    ];
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: /Exigences détaillées\s*2/ }));
    const row = screen.getByRole("button", { name: new RegExp(text) });
    expect(within(row).getByText("Remplie")).toBeVisible();
    for (const hidden of screen.queryAllByText(/non documentée/i)) expect(hidden).not.toBeVisible();
    fireEvent.click(row);
    expect(screen.getByText(/un seul peut suffire/)).toBeVisible();
    expect(screen.getAllByText("Non documentée")).toHaveLength(2);
  });

  it("shows equivalent requirements once in older analyses, without changing their status", async () => {
    const analysis = analysisFixture();
    analysis.requirements.push({
      ...analysis.requirements[0]!,
      id: "r1b",
      text: "maîtrise de Python",
      parent_id: "r9",
      status: "partial",
    });
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: /Exigences détaillées\s*2/ }));
    expect(screen.getAllByText(/Maîtrise de Python/i)).toHaveLength(1);
    expect(screen.queryByText("Partiellement remplie")).not.toBeInTheDocument();
  });

  it("never shows the technical diagnostics of the analysis", async () => {
    const analysis = analysisFixture();
    analysis.warnings = ["Preuve ignorée : experience « exp-z » n'existe pas dans le profil."];
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    const { container } = renderTab();
    await screen.findByText("Python en production");
    fireEvent.click(screen.getByRole("button", { name: /Exigences détaillées/ }));
    expect(container.textContent).not.toMatch(/Preuve ignorée/);
  });

  it("shows only real attention points, keeping not met, partial and undocumented distinct", async () => {
    const analysis = analysisFixture();
    const base = analysis.requirements[1]!;
    analysis.requirements.push(
      {
        ...base,
        id: "r3",
        text: "Permis de travail",
        category: "required",
        importance: "high",
        status: "missing",
        explanation: "Non mentionné.",
      },
      {
        ...base,
        id: "r4",
        text: "Maîtrise d'Airflow",
        category: "required",
        importance: "high",
        status: "partial",
        explanation: "Utilisé une fois. Sans production.",
      },
      {
        ...base,
        id: "r5",
        text: "Docker",
        category: "required",
        importance: "high",
        status: "not_documented",
        explanation: "",
      },
    );
    analysis.weaknesses.push({
      requirement_id: "r3",
      text: "Permis de travail",
      category: "required",
      kind: "missing",
      explanation: "L'offre exige un permis de travail. Le profil n'en parle pas.",
    });
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();
    await screen.findByText("Points d'attention");
    const profile = within(column("Mon profil pour ce poste"));
    expect(profile.getByText("Permis de travail")).toBeVisible();
    expect(profile.getByText(/— non remplie/)).toBeVisible();
    expect(profile.getByText("L'offre exige un permis de travail.")).toBeVisible();
    expect(profile.queryByText(/Le profil n'en parle pas/)).not.toBeInTheDocument();
    expect(profile.getByText("Maîtrise d'Airflow")).toBeVisible();
    expect(profile.getByText(/— partiellement remplie/)).toBeVisible();
    // Two points at most: the undocumented one is only an uncertainty, shown last
    expect(profile.queryByText("Docker")).not.toBeInTheDocument();
  });

  it("presents an undocumented essential requirement as something to confirm", async () => {
    const analysis = analysisFixture();
    analysis.requirements.push({
      ...analysis.requirements[1]!,
      id: "r3",
      text: "Docker",
      category: "required",
      importance: "high",
      status: "not_documented",
      explanation: "Le profil ne le mentionne pas.",
    });
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();
    await screen.findByText("Points d'attention");
    const profile = within(column("Mon profil pour ce poste"));
    expect(profile.getByText(/non documentée dans votre profil, à confirmer/)).toBeVisible();
    expect(profile.queryByText(/non remplie/)).not.toBeInTheDocument();
  });

  it("shows the essentials first and the complete lists on demand", async () => {
    const analysis = analysisFixture();
    analysis.overview.summary = "Première phrase. Deuxième phrase. Troisième phrase.";
    analysis.overview.missions = [
      "Mission un",
      "Mission deux",
      "Mission trois",
      "Mission quatre",
      "Mission cinq",
    ];
    analysis.overview.possible_tasks = [
      "Par exemple, tu pourrais écrire un job Spark",
      "Tu pourrais aussi documenter les flux",
      "Revue de code hebdomadaire",
    ];
    analysis.overview.technologies = ["Spark", "Kafka", "dbt", "Airflow", "Docker"];
    analysis.overview.skills_sought = [
      "SQL",
      "spark",
      "Python",
      "Esprit d'équipe et sens du service",
    ];
    analysis.strengths = ["A", "B", "C", "D"].map((t) => ({
      ...analysis.strengths[0]!,
      title: `Atout ${t}`,
      explanation: `Raison ${t}. Détail ${t}.`,
    }));
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();
    await screen.findByText("Première phrase. Deuxième phrase.");
    const job = within(column("Le poste et l'entreprise"));
    expect(job.queryByText(/Troisième phrase/)).not.toBeInTheDocument();

    expect(job.getByText("Mission quatre")).toBeVisible();
    expect(job.queryByText("Mission cinq")).not.toBeInTheDocument();
    fireEvent.click(job.getByRole("button", { name: "Voir toutes les missions (5)" }));
    expect(job.getByText("Mission cinq")).toBeVisible();

    expect(job.getByText("Écrire un job Spark")).toBeVisible();
    expect(job.getByText("Documenter les flux")).toBeVisible();
    expect(job.queryByText("Revue de code hebdomadaire")).not.toBeInTheDocument();
    expect(job.queryByText(/tu pourrais/i)).not.toBeInTheDocument();

    // Six short keywords: the one of an essential requirement (« Maîtrise de Python ») first;
    // "spark" is "Spark", sentences are left to the requirements detail
    expect(job.getAllByText(/^(Python|Spark|Kafka|dbt|Airflow|Docker)$/)).toHaveLength(6);
    expect(job.queryByText("SQL")).not.toBeInTheDocument();
    expect(job.queryByText(/Esprit d'équipe/)).not.toBeInTheDocument();

    // Three strengths, each with a single sentence and no « Lire la suite »
    const profile = within(column("Mon profil pour ce poste"));
    expect(profile.getByText("Atout C")).toBeVisible();
    expect(profile.getByText("Raison C.")).toBeVisible();
    expect(profile.queryByText(/Détail/)).not.toBeInTheDocument();
    expect(profile.queryByText("Atout D")).not.toBeInTheDocument();
    expect(profile.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows what the company does from the offer, in one sentence, apart from the job", async () => {
    const analysis = analysisFixture();
    analysis.offer.company_activity =
      "Fictive Corp édite des logiciels de paie. Elle a 200 salariés.";
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab();
    const job = within(await screen.findByRole("region", { name: "Le poste et l'entreprise" }));
    expect(job.getByText("L'entreprise")).toBeVisible();
    expect(job.getByText("Fictive Corp édite des logiciels de paie.")).toBeVisible();
    expect(job.queryByText(/200 salariés/)).not.toBeInTheDocument();
    expect(job.getByText("Construire des pipelines de données fictifs.")).toBeVisible();
  });

  it("shows the company activity in one sentence when the preparation kept it from the offer", async () => {
    const fact = { topic: "activity", text: "", interview_use: "", source_ids: [] };
    fakeBackend({
      [`GET ${ANALYSIS}`]: [200, { ...analysisFixture(), running: false }],
      [`GET ${PREPARATION}`]: [
        200,
        {
          running: false,
          company: {
            facts: [
              { ...fact, id: "f1", origin: "web", text: "Activité trouvée sur le web." },
              {
                ...fact,
                id: "f2",
                origin: "offer",
                text: "Éditeur fictif de logiciels de paie. Fondé en 2001.",
              },
            ],
          },
        },
      ],
    });
    renderTab();
    expect(await screen.findByText("Éditeur fictif de logiciels de paie.")).toBeVisible();
    expect(screen.getByText("L'entreprise")).toBeVisible();
    expect(screen.queryByText(/Fondé en 2001/)).not.toBeInTheDocument();
    expect(screen.getByText("Construire des pipelines de données fictifs.")).toBeVisible();
    expect(screen.queryByText(/Activité trouvée sur le web/)).not.toBeInTheDocument();
  });

  it("never shows the interview advice or questions of older analyses", async () => {
    const analysis: CompletedAnalysis = {
      ...analysisFixture(),
      interview_questions: [
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
    expect(await screen.findByText("Python en production")).toBeInTheDocument();
    expect(screen.queryByText("Préparer un exemple de pipeline.")).not.toBeInTheDocument();
    expect(screen.queryByText("Pourquoi ce poste de data engineer ?")).not.toBeInTheDocument();
  });

  it("handles an analysis without strengths, attention points or optional parts", async () => {
    const analysis = analysisFixture();
    analysis.strengths = [];
    analysis.weaknesses = [];
    analysis.overview.summary = "";
    analysis.overview.missions = [];
    analysis.overview.possible_tasks = [];
    analysis.overview.technologies = [];
    analysis.overview.skills_sought = [];
    fakeBackend({ [`GET ${ANALYSIS}`]: [200, { ...analysis, running: false }] });
    renderTab(summary({ source_url: null }));
    expect(await screen.findByText(/n'a pas identifié d'atout particulier/)).toBeInTheDocument();
    for (const title of [
      "L'entreprise",
      "Le poste en bref",
      "Missions principales",
      "Exemples de tâches possibles",
      "Compétences clés",
      "Points d'attention",
    ])
      expect(screen.queryByText(title)).not.toBeInTheDocument();
  });

  it("shows the interview questions folded, with their details on click", async () => {
    const analysis: CompletedAnalysis = {
      ...analysisFixture(),
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
    // Component shared with the deep preparation (PreparationTab)
    render(
      <InterviewQuestions
        questions={analysis.interview_questions!}
        requirements={analysis.requirements}
      />,
    );

    // Questions are visible, details folded
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
    expect(screen.getByText("Stagiaire data")).toBeVisible(); // evidence of the question
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
