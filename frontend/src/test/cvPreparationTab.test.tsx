import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PreparationTab } from "@/features/cvs/components/PreparationTab";
import { sourceDate } from "@/features/cvs/format";
import type { Preparation } from "@/services/api/cvTypes";
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

const BASE = "/api/cvs/fictive-corp-data-engineer";
const NOT_FOUND: [number, unknown] = [
  404,
  { detail: { message: "Préparation non disponible", problems: ["aucune préparation"] } },
];

const preparationFixture = (): Preparation => ({
  schema_version: 1,
  status: "completed",
  generated_at: "2026-10-22T11:00:00",
  profile_fingerprint: "abc",
  analysis_generated_at: "2026-10-20T10:00:00",
  company: {
    name: "Fictive Corp",
    research_status: "done",
    official_website: "https://fictive.example.com",
    note: "",
    facts: [
      {
        id: "o1",
        topic: "activity",
        origin: "offer",
        text: "Équipe data d'un éditeur fictif.",
        interview_use: "",
        source_ids: [],
      },
      {
        id: "w1",
        topic: "news",
        origin: "web",
        text: "Fictive Corp a lancé une offre cloud fictive.",
        interview_use: "Demander l'impact sur les pipelines.",
        source_ids: ["s1"],
      },
    ],
    sources: [
      {
        id: "s1",
        url: "https://fictive.example.com/news/cloud",
        title: "Communiqué Fictive",
        official: true,
        published_at: "2026-03",
        accessed_at: "2026-10-22",
        access: "fetched",
      },
    ],
    warnings: [],
  },
  priorities: [
    {
      title: "Pipelines en production",
      why: "Exigence essentielle de l'offre.",
      actions: ["Préparer un récit de 2 minutes sur le pipeline Spark."],
      requirement_ids: ["req-1"],
      fact_ids: [],
    },
  ],
  questions: [
    {
      id: "q1",
      origin: "preparation",
      kind: "motivation",
      question: "Pourquoi Fictive Corp ?",
      purpose: "Motivation.",
      answer_guidance: ["Relier l'offre cloud au poste."],
      evidence: [],
      topics_to_review: [],
      requirement_ids: [],
      fact_ids: ["w1"],
    },
  ],
  knowledge: [
    {
      topic: "Kafka",
      why: "« Connaissance de Kafka »",
      explanation: "Journal distribué : topics, partitions, groupes de consommateurs.",
      check_points: ["Savoir expliquer une partition."],
      requirement_ids: ["req-2"],
    },
  ],
  experiences: [
    {
      evidence: { type: "experience", id: "exp-a", label: "Stagiaire data — Société A" },
      angle: "Pipeline proche des missions.",
      key_points: ["Pipeline Spark fictif."],
      question_ids: ["q1"],
      requirement_ids: [],
    },
  ],
  vigilance: [
    {
      kind: "not_documented",
      requirement_ids: ["req-2"],
      concern: "Kafka n'apparaît pas dans le profil.",
      how_to_address: ["N'en parler que si vous l'avez réellement utilisé."],
    },
  ],
  warnings: [],
});

function renderTab(cv = summary()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PreparationTab cv={cv} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("PreparationTab", () => {
  it("shows a saved preparation in six folded sections, without any generation", async () => {
    const calls = fakeBackend({
      [`GET ${BASE}/preparation`]: [200, { ...preparationFixture(), running: false }],
      [`GET ${BASE}/analysis`]: [200, { ...analysisFixture(), running: false }],
    });
    renderTab();
    const titles = [
      "Comprendre l'entreprise",
      "Priorités de préparation",
      "Questions probables",
      "Connaissances à approfondir",
      "Expériences à préparer",
      "Points de vigilance",
    ];
    for (const title of titles) {
      const trigger = await screen.findByRole("button", { name: new RegExp(title) });
      expect(trigger).toHaveAttribute("aria-expanded", "false");
      fireEvent.click(trigger);
    }
    expect(screen.getByText("Fictive Corp a lancé une offre cloud fictive.")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Communiqué Fictive/ });
    expect(link).toHaveAttribute("href", "https://fictive.example.com/news/cloud");
    expect(link).toHaveTextContent("mars 2026");
    expect(link).toHaveTextContent("site officiel");
    expect(screen.getByText("Équipe data d'un éditeur fictif.")).toBeInTheDocument();
    expect(screen.getByText("Pourquoi Fictive Corp ?")).toBeInTheDocument();
    expect(screen.getByText(/topics, partitions/)).toBeInTheDocument();
    expect(screen.getByText("Question 1")).toBeInTheDocument();
    expect(screen.getByText("Non documentée")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Générer ma préparation/ }),
    ).not.toBeInTheDocument();
    expect(calls.filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("shows only the presentation and the button, then follows the generation", async () => {
    const calls = fakeBackend({
      [`GET ${BASE}/preparation`]: [NOT_FOUND, [200, { ...preparationFixture(), running: false }]],
      [`GET ${BASE}/analysis`]: [200, { ...analysisFixture(), running: false }],
      [`POST ${BASE}/preparation`]: [202, { task_id: "t7", status: "pending" }],
      "GET /api/cvs/tasks/t7": [
        200,
        task({ task_id: "t7", kind: "preparation", status: "completed", step: "done" }),
      ],
    });
    renderTab();
    const button = await screen.findByRole("button", { name: /Générer ma préparation/ });
    // Neither the advice nor the questions of the analysis: only the presentation and the button
    expect(
      screen.getByText(/Une préparation personnalisée pour cet entretien/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Préparer un exemple de pipeline.")).not.toBeInTheDocument();
    expect(screen.queryByText("Préparer ma candidature")).not.toBeInTheDocument();
    expect(calls.filter((c) => c.startsWith("POST"))).toEqual([]);
    expect(calls).not.toContain(`GET ${BASE}/analysis`);

    fireEvent.click(button);
    expect(
      await screen.findByRole("button", { name: /Comprendre l'entreprise/ }),
    ).toBeInTheDocument();
    expect(calls).toContain(`POST ${BASE}/preparation`);
    expect(calls).toContain("GET /api/cvs/tasks/t7");
  });

  it("keeps the button and shows the error when the generation fails", async () => {
    fakeBackend({
      [`GET ${BASE}/preparation`]: NOT_FOUND,
      [`GET ${BASE}/analysis`]: [200, { ...analysisFixture(), running: false }],
      [`POST ${BASE}/preparation`]: [202, { task_id: "t8", status: "pending" }],
      "GET /api/cvs/tasks/t8": [
        200,
        task({
          task_id: "t8",
          kind: "preparation",
          status: "failed",
          error: { message: "La préparation a échoué", problems: ["Claude n'a pas répondu."] },
        }),
      ],
    });
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: /Générer ma préparation/ }));
    expect(await screen.findByText(/Claude n'a pas répondu/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Générer ma préparation/ })).toBeEnabled();
  });

  it("waits for a completed analysis before offering the generation", async () => {
    fakeBackend({
      [`GET ${BASE}/preparation`]: NOT_FOUND,
      [`GET ${BASE}/analysis`]: NOT_FOUND,
    });
    renderTab(summary({ analysis_status: "missing" }));
    expect(await screen.findByRole("button", { name: /Générer ma préparation/ })).toBeDisabled();
    expect(screen.getByText(/une fois l'analyse d'adéquation terminée/)).toBeInTheDocument();
  });

  it("formats source dates", () => {
    expect(sourceDate("2026-03")).toBe("mars 2026");
    expect(sourceDate("2026-03-05")).toBe("5 mars 2026");
    expect(sourceDate(null)).toBeNull();
    expect(sourceDate("2026-13")).toBeNull();
  });
});
