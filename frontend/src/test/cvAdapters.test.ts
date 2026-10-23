import { describe, expect, it } from "vitest";

import {
  attentionPoints,
  cleanDocument,
  exampleTasks,
  jobBrief,
  educationKeys,
  formatDates,
  generationSteps,
  keySkills,
  layoutZones,
  mainMissions,
  requirementLines,
  visibleRequirements,
  profileEntries,
  shortLocation,
  slug,
  zoneIdFor,
} from "@/features/cvs/adapters";
import {
  analysisFixture,
  documentFixture,
  layoutFixture,
  profileFixture,
  task,
} from "./fixtures/cvFixtures";
import type { Requirement } from "@/services/api/cvTypes";

describe("layout.json -> clickable zones", () => {
  it("converts normalized regions to zones and ignores unknown keys", () => {
    const zones = layoutZones(layoutFixture());
    expect(zones.map((z) => z.id)).toEqual([
      "section:profile",
      "section:experiences",
      "item:experiences/0",
      "item:experiences/1",
      "section:skills",
    ]);
    const item = zones[2]!;
    expect(item).toMatchObject({ section: "experiences", index: 0, page: 1, x: 0.05, y: 0.17 });
    expect(item.width).toBeCloseTo(0.9);
    expect(item.height).toBeCloseTo(0.13);
  });

  it("returns no zone without layout (CV created before the markers)", () => {
    expect(layoutZones(null)).toEqual([]);
    expect(layoutZones(undefined)).toEqual([]);
  });

  it("maps a selection to its zone; languages share the skills zone", () => {
    expect(zoneIdFor({ section: "experiences", index: 1 })).toBe("item:experiences/1");
    expect(zoneIdFor({ section: "experiences" })).toBe("section:experiences");
    expect(zoneIdFor({ section: "languages" })).toBe("section:skills");
  });
});

describe("generation steps", () => {
  it("marks previous steps done and the current one active", () => {
    const states = generationSteps(task({ step: "verify_cv" })).map((s) => s.state);
    expect(states).toEqual(["done", "done", "done", "active", "pending", "pending"]);
  });

  it("keeps the correction inside the verification step", () => {
    expect(generationSteps(task({ step: "correct_cv" }))[3]!.state).toBe("active");
    expect(generationSteps(task({ step: "verified" }))[3]!.state).toBe("active");
  });

  it("marks the failing step as failed", () => {
    const states = generationSteps(task({ status: "failed", step: "compile" })).map((s) => s.state);
    expect(states).toEqual(["done", "done", "done", "done", "failed", "pending"]);
  });

  it("shows nothing done while the task is pending, everything once completed", () => {
    expect(
      generationSteps(task({ status: "pending", step: "pending" })).every(
        (s) => s.state === "pending",
      ),
    ).toBe(true);
    expect(
      generationSteps(task({ status: "completed", step: "done" })).every((s) => s.state === "done"),
    ).toBe(true);
  });
});

describe("entries added from the profile (same as cv/document.py)", () => {
  // Reference values computed with candidate.manager._slug and cv.render (Python).
  it.each([
    ["École Supérieure Fictive", "ecole-superieure-fictive"],
    [
      "Institut Imaginaire de Lyon – École Supérieure Fictive",
      "institut-imaginaire-de-lyon-ecole-superieure-fictive",
    ],
    [
      "Université de Nulle-Part – Faculté d'Informatique",
      "universite-de-nulle-part-faculte-d-informatique",
    ],
    ["Søren & Co", "sren-co"],
    ["Œuvre 2025", "uvre-2025"],
    ["a\tb", "a-b"],
    ["", ""],
  ])("slug(%j) = %j", (text, expected) => {
    expect(slug(text)).toBe(expected);
  });

  it("formats dates and locations like the LaTeX renderer", () => {
    expect(formatDates("2024-06", "2025-02")).toBe("2024–2025");
    expect(formatDates("2026-02", "2026-08")).toBe("2026");
    expect(formatDates("2026", undefined)).toBe("2026");
    expect(formatDates(undefined, "2025")).toBe("2025");
    expect(formatDates(undefined, undefined)).toBe("");
    expect(shortLocation("Paris, France")).toBe("Paris");
    expect(shortLocation(undefined)).toBe("");
  });

  it("gives education entries without id the same key as the backend", () => {
    expect(educationKeys(profileFixture())).toEqual([
      "telecom-fictive-2",
      "telecom-fictive-3",
      "lycee",
      "formation",
    ]);
  });

  it("builds the same entries as cv/document.entry_from_profile", () => {
    const profile = profileFixture();
    expect(profileEntries("experiences", profile).map((c) => c.entry)).toEqual([
      {
        source_id: "exp-a",
        title: "Stagiaire data",
        organization: "Société A",
        context: null,
        location: "Lyon",
        dates: "2025",
        bullets: ["Pipeline Spark fictif."],
      },
    ]);
    expect(profileEntries("projects", profile).map((c) => c.entry)).toEqual([
      {
        source_id: "telecom-fictive",
        name: "Projet clash d'id",
        link: { url: "https://github.com/alex/p", label: "GitHub" },
        bullets: [],
      },
      { source_id: "proj-b", name: "Projet B", link: null, bullets: [] },
    ]);
    expect(profileEntries("education", profile).map((c) => c.entry)).toEqual([
      {
        source_id: "telecom-fictive-2",
        institution: "Télécom Fictive",
        location: "Paris",
        dates: "2023–2026",
        bullets: ["Data"],
      },
      {
        source_id: "telecom-fictive-3",
        institution: "Télécom Fictive",
        location: "Oslo",
        dates: "2025",
        bullets: [],
      },
      { source_id: "lycee", institution: "Lycée Fictif", location: "", dates: "", bullets: [] },
      { source_id: "formation", institution: "", location: "", dates: "", bullets: [] },
    ]);
  });
});

describe("cleanDocument", () => {
  it("removes empty lines left by the editor and keeps source_id", () => {
    const doc = documentFixture();
    doc.experiences[0]!.bullets.push("  ");
    doc.experiences[0]!.context = "  ";
    doc.header.contacts.push({ type: "phone", value: " " });
    doc.skills.push({ label: "Vide", items: [] });
    doc.languages.push({ name: "", level: "" });
    doc.interests.push("");
    doc.projects[0]!.link = { url: " ", label: "GitHub" };

    const cleaned = cleanDocument(doc);
    expect(cleaned.experiences[0]).toMatchObject({
      source_id: "exp-a",
      context: null,
      bullets: ["Pipeline Spark fictif."],
    });
    expect(cleaned.header.contacts.map((c) => c.type)).toEqual(["email", "github"]);
    expect(cleaned.skills).toEqual([{ label: "Langages", items: ["Python", "SQL"] }]);
    expect(cleaned.languages).toEqual([{ name: "Anglais", level: "C1" }]);
    expect(cleaned.interests).toEqual(["Escalade"]);
    expect(cleaned.projects[0]!.link).toBeNull();
    expect(Object.keys(cleaned).sort()).toEqual(Object.keys(documentFixture()).sort());
  });
});

describe("keySkills", () => {
  const withSkills = (
    technologies: string[],
    skills: string[],
    requirements: [string, "high" | "normal"][] = [],
  ) => {
    const analysis = analysisFixture();
    analysis.overview.technologies = technologies;
    analysis.overview.skills_sought = skills;
    analysis.requirements = requirements.map(([text, importance], i) => ({
      ...analysis.requirements[0]!,
      id: `r${i}`,
      text,
      importance,
    }));
    return analysis;
  };

  it("keeps up to six short technical keywords, without duplicates, sentences or personal qualities", () => {
    const analysis = withSkills(
      ["Python", " PyTorch ", "Computer Vision"],
      [
        "pytorch",
        "Bonne maîtrise de Python en production",
        "Rigueur",
        "Curiosité",
        "Esprit d'équipe",
        "Mathématiques (statistiques, optimisation)",
        "SQL",
        "",
        "Docker",
        "Git",
        "Linux",
      ],
    );
    expect(keySkills(analysis)).toEqual([
      "Python",
      "PyTorch",
      "Computer Vision",
      "SQL",
      "Docker",
      "Git",
    ]);
    expect(keySkills(analysis, 3)).toEqual(["Python", "PyTorch", "Computer Vision"]);
  });

  it("shows alternatives once and prefers the precise keyword, essential requirements first", () => {
    const analysis = withSkills(
      ["Python", "PyTorch", "TensorFlow"],
      ["Machine Learning / Deep Learning", "Deep Learning", "Computer Vision", "Rigueur"],
      [
        ["Bonne maîtrise de Python", "normal"],
        ["Expérience pratique en Deep Learning avec PyTorch ou TensorFlow", "high"],
        ["Solides bases en Machine Learning/Deep Learning", "high"],
      ],
    );
    expect(keySkills(analysis)).toEqual([
      "PyTorch ou TensorFlow",
      "Machine Learning / Deep Learning",
      "Python",
      "Computer Vision",
    ]);
  });
});

describe("mainMissions", () => {
  it("keeps the first missions as written, skipping a step repeated in other words", () => {
    const missions = [
      "Concevoir des pipelines de données pour l'équipe produit",
      "Concevoir et maintenir des pipelines de données",
      "  ",
      "Former les utilisateurs aux tableaux de bord",
      "Documenter les flux",
      "Assurer une veille technologique",
      "Participer aux rituels agiles",
    ];
    expect(mainMissions(missions)).toEqual([
      "Concevoir des pipelines de données pour l'équipe produit",
      "Former les utilisateurs aux tableaux de bord",
      "Documenter les flux",
      "Assurer une veille technologique",
    ]);
    expect(mainMissions(["Coder", "Coder"], 4)).toEqual(["Coder"]);
  });
});

describe("exampleTasks", () => {
  it("keeps two illustrations that do not repeat a mission, without their opening", () => {
    const tasks = [
      "Par exemple, tu pourrais documenter les flux de données",
      "Tu pourrais aussi écrire un job Spark de nettoyage",
      "Préparer une démonstration pour un client",
      "Animer un atelier",
    ];
    expect(exampleTasks(tasks, ["Documenter les flux de données de l'équipe"])).toEqual([
      "Écrire un job Spark de nettoyage",
      "Préparer une démonstration pour un client",
    ]);
  });
});

describe("jobBrief", () => {
  it("keeps one sentence for the company and two for the job, without repeating the company", () => {
    expect(
      jobBrief(
        "Fictive Corp édite des logiciels de paie pour les PME. Le stagiaire construit des pipelines. Objectif : fiabiliser les données. Contexte.",
        "Fictive Corp édite des logiciels de paie pour les PME. Elle compte 200 salariés.",
      ),
    ).toEqual({
      company: "",
      job: "Fictive Corp édite des logiciels de paie pour les PME. Le stagiaire construit des pipelines.",
    });
    expect(
      jobBrief(
        "Le stagiaire construit des pipelines. Objectif : fiabiliser les données. Contexte.",
        "Fictive Corp édite des logiciels de paie pour les PME. Elle compte 200 salariés.",
      ),
    ).toEqual({
      company: "Fictive Corp édite des logiciels de paie pour les PME.",
      job: "Le stagiaire construit des pipelines. Objectif : fiabiliser les données.",
    });
  });

  it("hides an « activity » that only describes the job, and never guesses one", () => {
    const summary =
      "Stage dans l'équipe Computer Vision qui produit les données de tracking des joueurs à partir de la vidéo des matchs.";
    expect(
      jobBrief(
        summary,
        "Stage au sein de l'équipe Computer Vision qui génère la donnée de tracking des joueurs à partir de la vidéo du match.",
      ),
    ).toEqual({ company: "", job: summary });
    expect(jobBrief("Rôle. Objectif. Contexte.", null)).toEqual({
      company: "",
      job: "Rôle. Objectif.",
    });
    expect(jobBrief("", undefined)).toEqual({ company: "", job: "" });
  });
});

describe("visibleRequirements", () => {
  it("shows equivalent requirements once, keeping distinct criteria and statuses", () => {
    const analysis = analysisFixture();
    const base = analysis.requirements[0]!;
    analysis.requirements = [
      {
        ...base,
        id: "req-5",
        text: "Expérience pratique en Deep Learning avec PyTorch ou TensorFlow, via des projets ou des stages",
        status: "met",
      },
      { ...base, id: "req-8", text: "Diplôme d'ingénieur", duplicate_of: "req-1" },
      { ...base, id: "req-9a", text: "Moins de 6 mois", parent_id: "req-9" },
      {
        ...base,
        id: "req-9b",
        text: "expérience pratique en Deep Learning (PyTorch ou TensorFlow) via des projets ou des stages",
        parent_id: "req-9",
        status: "partial",
      },
      { ...base, id: "req-10", text: "Python ou SQL" },
      { ...base, id: "req-11", text: "Python et SQL" },
    ];
    const visible = visibleRequirements(analysis);
    expect(visible.map((r) => [r.id, r.status])).toEqual([
      ["req-5", "met"],
      ["req-9a", "met"],
      ["req-10", "met"],
      ["req-11", "met"],
    ]);
  });

  it("never hides a required requirement behind a preferred one", () => {
    const analysis = analysisFixture();
    const base = analysis.requirements[0]!;
    analysis.requirements = [
      { ...base, id: "a", text: "Docker", category: "preferred" },
      { ...base, id: "b", text: "Docker", category: "required" },
    ];
    expect(visibleRequirements(analysis).map((r) => r.id)).toEqual(["a", "b"]);
  });
});

describe("requirementLines", () => {
  type Spec = Partial<Requirement> & Pick<Requirement, "id" | "text">;
  const analysisWith = (specs: Spec[]) => {
    const analysis = analysisFixture();
    const base: Requirement = {
      ...analysis.requirements[0]!,
      category: "required",
      source: "must_have",
      importance: "normal",
      status: "met",
      parent_id: null,
      parent_text: null,
      duplicate_of: null,
      evidence: [],
    };
    analysis.requirements = specs.map((spec) => ({ ...base, ...spec }));
    return analysis;
  };
  const part = (
    id: string,
    text: string,
    parent: string,
    parentText: string,
    extra: Partial<Requirement> = {},
  ): Spec => ({
    id,
    text,
    parent_id: parent,
    parent_text: parentText,
    ...extra,
  });

  it("gathers the parts of a requirement in one line, each part keeping its own status", () => {
    const maths = "Solides bases en mathématiques (statistiques, optimisation)";
    const lines = requirementLines(
      analysisWith([
        part("r1a", "Solides bases en mathématiques (statistiques)", "r1", maths, {
          importance: "high",
        }),
        part("r1b", "Solides bases en mathématiques (optimisation)", "r1", maths, {
          importance: "high",
        }),
        { id: "r2", text: "Bonne maîtrise de Python" },
      ]),
    );
    expect(lines.map((l) => [l.id, l.text, l.group, l.status, l.parts.length])).toEqual([
      ["r2", "Bonne maîtrise de Python", "required", "met", 1],
      ["r1", maths, "essential", "met", 2],
    ]);
  });

  it("settles alternatives (or) by the best part, without artificial gaps", () => {
    const detection =
      "Expérience en détection, tracking, re-identification ou calibration de caméra";
    const [line] = requirementLines(
      analysisWith([
        part("r1a", "Expérience en détection", "r1", detection, { category: "preferred" }),
        part("r1b", "Expérience en tracking", "r1", detection, {
          category: "preferred",
          status: "not_documented",
        }),
        part("r1c", "Expérience en re-identification", "r1", detection, {
          category: "preferred",
          status: "partial",
        }),
        part("r1d", "Expérience en calibration de caméra", "r1", detection, {
          category: "preferred",
          status: "missing",
        }),
      ]),
    );
    expect([line!.relation, line!.status, line!.group]).toEqual(["or", "met", "preferred"]);
    expect(line!.parts.map((p) => p.status)).toEqual([
      "met",
      "not_documented",
      "partial",
      "missing",
    ]);
  });

  it("keeps the worst only when all criteria are needed (and) and one is not met", () => {
    const both = "Python et SQL";
    const andMissing = requirementLines(
      analysisWith([
        part("r1a", "Python", "r1", both),
        part("r1b", "SQL", "r1", both, { status: "missing" }),
      ]),
    )[0]!;
    expect([andMissing.relation, andMissing.status]).toEqual(["and", "missing"]);
    const andUndocumented = requirementLines(
      analysisWith([
        part("r1a", "Python", "r1", both),
        part("r1b", "SQL", "r1", both, { status: "not_documented" }),
      ]),
    )[0]!;
    // « non documentée » never becomes « non remplie »: no overall status, the parts keep theirs
    expect([andUndocumented.relation, andUndocumented.status]).toEqual(["and", null]);
  });

  it("does not interpret a comma: an uncertain relation keeps the statuses of the parts", () => {
    const rigour =
      "Rigueur dans l'évaluation des résultats (choix des métriques, analyse des erreurs)";
    const [line] = requirementLines(
      analysisWith([
        part("r1a", "Rigueur dans l'évaluation des résultats (choix des métriques)", "r1", rigour),
        part("r1b", "Rigueur dans l'évaluation des résultats (analyse des erreurs)", "r1", rigour, {
          status: "not_documented",
        }),
      ]),
    );
    expect([line!.relation, line!.status]).toEqual(["unknown", null]);
    // An « ou » inside a part is not the link between the parts
    const studies =
      "Étudiant en dernière année d'école d'ingénieur ou de master, spécialisation Computer Vision";
    const [education] = requirementLines(
      analysisWith([
        part("r2a", "Étudiant en dernière année d'école d'ingénieur ou de master", "r2", studies, {
          status: "missing",
        }),
        part("r2b", "spécialisation Computer Vision", "r2", studies),
      ]),
    );
    expect([education!.relation, education!.status]).toEqual(["unknown", null]);
  });

  it("orders obligatoires, essentielles and souhaitées, a condition staying obligatoire", () => {
    const lines = requirementLines(
      analysisWith([
        {
          id: "r1",
          text: "Souhaité",
          category: "preferred",
          source: "nice_to_have",
          importance: "high",
        },
        { id: "r2", text: "Compétence clé", importance: "high" },
        { id: "r3", text: "Bac+5", source: "education", importance: "high" },
        { id: "r4", text: "Compétence demandée" },
        { id: "r5", text: "Anglais courant", source: "languages" },
      ]),
    );
    expect(lines.map((l) => [l.id, l.group])).toEqual([
      ["r3", "required"],
      ["r4", "required"],
      ["r5", "required"],
      ["r2", "essential"],
      ["r1", "preferred"],
    ]);
  });

  it("reads older analyses: duplicates hidden, a lone part shown as itself, no parent text", () => {
    const lines = requirementLines(
      analysisWith([
        { id: "r1", text: "Expérience pratique en Deep Learning avec PyTorch ou TensorFlow" },
        part("r2a", "Moins de 6 mois", "r2", "Moins de 6 mois ; expérience…", {
          duplicate_of: "r1",
        }),
        part("r3a", "expérience pratique en Deep Learning (PyTorch ou TensorFlow)", "r3", "x"),
        part("r4a", "Docker", "r4", ""),
        part("r4b", "Kubernetes", "r4", ""),
        { id: "r5", text: "Python", source: undefined as unknown as string },
      ]),
    );
    expect(lines.map((l) => [l.id, l.text, l.status])).toEqual([
      ["r1", "Expérience pratique en Deep Learning avec PyTorch ou TensorFlow", "met"],
      ["r4", "Docker, Kubernetes", "met"],
      ["r5", "Python", "met"],
    ]);
  });
});

describe("attentionPoints", () => {
  const withRequirements = (
    statuses: [string, "required" | "preferred", "high" | "normal", string][],
  ) => {
    const analysis = analysisFixture();
    const base = analysis.requirements[1]!;
    analysis.requirements = statuses.map(([id, category, importance, status]) => ({
      ...base,
      id,
      category,
      importance,
      text: `Critère ${id.repeat(3)}`,
      status: status as Requirement["status"],
      explanation: `Explication ${id}. Détail ${id}.`,
    }));
    analysis.weaknesses = [];
    return analysis;
  };

  it("orders real obstacles: not met, then essential partial, then essential undocumented", () => {
    const analysis = withRequirements([
      ["a", "required", "high", "not_documented"],
      ["b", "required", "high", "partial"],
      ["c", "required", "normal", "missing"],
      ["d", "required", "high", "missing"],
      ["e", "preferred", "high", "missing"],
    ]);
    analysis.weaknesses = [
      {
        requirement_id: "d",
        text: "",
        category: "required",
        kind: "missing",
        explanation: "Faiblesse d. Suite.",
      },
    ];
    expect(attentionPoints(analysis, 5).map((p) => [p.id, p.status, p.explanation])).toEqual([
      ["d", "missing", "Faiblesse d."],
      ["c", "missing", "Explication c."],
      ["b", "partial", "Explication b."],
      ["a", "not_documented", "Explication a."],
    ]);
    expect(attentionPoints(analysis).map((p) => p.id)).toEqual(["d", "c"]);
  });

  it("never reports an alternative when another one answers the requirement", () => {
    const analysis = analysisFixture();
    const base = {
      ...analysis.requirements[0]!,
      category: "required" as const,
      source: "must_have",
      importance: "high" as const,
    };
    const text = "Python ou Java";
    analysis.requirements = [
      { ...base, id: "r1a", text: "Python", parent_id: "r1", parent_text: text, status: "met" },
      {
        ...base,
        id: "r1b",
        text: "Java",
        parent_id: "r1",
        parent_text: text,
        status: "not_documented",
      },
    ];
    expect(attentionPoints(analysis)).toEqual([]);
    analysis.requirements[0]!.status = "missing";
    analysis.requirements[1]!.status = "missing";
    expect(attentionPoints(analysis).map((p) => [p.id, p.text, p.status])).toEqual([
      ["r1", text, "missing"],
    ]);
  });

  it("never turns a normal undocumented or partial requirement, or a duplicate, into an attention point", () => {
    const analysis = withRequirements([
      ["a", "required", "normal", "not_documented"],
      ["b", "required", "normal", "partial"],
      ["c", "required", "high", "met"],
    ]);
    analysis.requirements.push({
      ...analysis.requirements[0]!,
      id: "z",
      importance: "high",
      status: "missing",
      duplicate_of: "c",
    });
    expect(attentionPoints(analysis)).toEqual([]);
  });
});
