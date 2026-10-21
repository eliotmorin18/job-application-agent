import { describe, expect, it } from "vitest";

import {
  buildDecisions,
  categoryKey,
  correctedMatchFields,
  correctedNameMatches,
  incompleteChoices,
  initialChoices,
  norm,
  problemsByProposal,
  skillInProfile,
  skillNorm,
  unavailableActions,
} from "@/features/import/decisions";
import type { CandidateProfile, ImportReview } from "@/services/api/types";

// Options accepted by candidate/apply_import.py (OPTIONS), per kind of proposal and action
const ALLOWED: Record<string, string[]> = {
  "item:add": ["fields", "allow_duplicate", "overrides"],
  "item:update": [
    "target_id",
    "target_position",
    "fields",
    "clear",
    "allow_less_precise",
    "overrides",
  ],
  "skills:add": ["category", "create_category", "allow_duplicate", "overrides"],
  "languages:add": ["level", "allow_duplicate", "overrides"],
  "languages:update": ["level"],
  "interests:add": ["allow_duplicate", "overrides"],
  "interests:update": ["target", "overrides"],
  "personal:update": ["fields", "allow_less_precise", "overrides"],
};

const review: ImportReview = {
  import_id: "cv-1",
  source: { source_pdf: "cv.pdf", extracted_at: "2026-10-20T17:45:40" },
  warnings: [],
  personal: [
    {
      field: "phone",
      extracted: "+33 6",
      current: null,
      status: "missing_in_profile",
      uncertain: false,
    },
    {
      field: "city",
      extracted: "Paris",
      current: null,
      status: "missing_in_profile",
      uncertain: true,
    },
    { field: "email", extracted: "a@b.c", current: "a@b.c", status: "same", uncertain: false },
  ],
  experiences: [
    {
      proposal_id: "experiences-1",
      status: "new",
      data: { company: "Acme", title: "Dev", start_date: "2024" },
      uncertain_fields: ["start_date"],
      matches: [],
    },
    {
      proposal_id: "experiences-2",
      status: "probable_duplicate",
      data: { company: "Geo", title: "CTO", skills: ["Python"] },
      uncertain_fields: [],
      matches: [
        {
          id: "geo",
          position: 1,
          level: "probable_duplicate",
          score: 1,
          reasons: ["même nom"],
          existing: { id: "geo", company: "Geo", title: "CTO" },
          differences: {
            skills: { extracted: ["Python"], current: null, change: "missing_in_profile" },
          },
        },
      ],
    },
  ],
  projects: [],
  education: [
    {
      proposal_id: "education-1",
      status: "probable_duplicate",
      data: { school: "Lycée", details: ["Maths"] },
      uncertain_fields: [],
      matches: [
        {
          id: null,
          position: 3,
          level: "probable_duplicate",
          score: 1,
          reasons: ["même nom"],
          existing: { school: "Lycée" },
          differences: {
            details: { extracted: ["Maths"], current: null, change: "missing_in_profile" },
          },
        },
      ],
    },
  ],
  skills: [
    {
      proposal_id: "skills-1",
      category: "devops",
      skill: "Docker",
      category_in_profile: null,
      status: "new",
      matches: [],
    },
    {
      proposal_id: "skills-2",
      category: "programming",
      skill: "Python",
      category_in_profile: "programming",
      status: "duplicate",
      matches: [{ category: "programming", skill: "Python" }],
    },
  ],
  languages: [
    { proposal_id: "languages-1", language: "German", level: null, status: "new", matches: [] },
    {
      proposal_id: "languages-2",
      language: "Anglais",
      level: "C1",
      status: "duplicate",
      matches: [{ language: "English", level: "Fluent" }],
      level_differs: true,
    },
  ],
  interests: [
    {
      proposal_id: "interests-1",
      interest: "Course à pied",
      status: "duplicate",
      matches: ["Running"],
    },
  ],
  summary: { new: 3, duplicate: 3, probable_duplicate: 2 },
};

function kindOf(id: string) {
  if (id === "personal") return "personal";
  const section = id.split("-")[0]!;
  return ["experiences", "projects", "education"].includes(section) ? "item" : section;
}

describe("import decisions", () => {
  it("defaults: new items added without uncertain fields, duplicates skipped", () => {
    const choices = initialChoices(review);
    expect(choices.items["experiences-1"]).toMatchObject({
      action: "add",
      addFields: ["company", "title"],
    });
    expect(choices.items["experiences-2"]?.action).toBe("skip");
    expect(choices.skills["skills-1"]).toMatchObject({
      action: "add",
      category: "devops",
      createCategory: true,
    });
    expect(choices.personal.fields).toEqual(["phone"]);
  });

  it("only sends options supported by apply_import.py", () => {
    const choices = initialChoices(review);
    choices.items["experiences-2"]!.action = "update";
    choices.items["education-1"]!.action = "update";
    choices.languages["languages-1"]!.level = "B1";
    choices.languages["languages-2"]!.action = "update";
    choices.interests["interests-1"]!.action = "update";
    choices.skills["skills-2"] = {
      action: "add",
      category: "tools",
      createCategory: false,
      allowDuplicate: true,
      correction: null,
    };

    const decisions = buildDecisions(review, choices);
    for (const [id, decision] of Object.entries(decisions)) {
      const { action, ...options } = decision as { action: string };
      if (action === "skip") continue;
      const allowed = ALLOWED[`${kindOf(id)}:${action}`];
      expect(allowed, `${id} ${action}`).toBeDefined();
      for (const key of Object.keys(options)) expect(allowed).toContain(key);
      for (const value of Object.values(options))
        expect(value === false || value === undefined).toBe(false);
    }

    expect(decisions["experiences-2"]).toEqual({
      action: "update",
      fields: ["skills"],
      target_id: "geo",
    });
    expect(decisions["education-1"]).toEqual({
      action: "update",
      fields: ["details"],
      target_position: 3,
    });
    expect(decisions["skills-1"]).toEqual({
      action: "add",
      category: "devops",
      create_category: true,
    });
    expect(decisions["languages-1"]).toEqual({ action: "add", level: "B1" });
    expect(decisions["languages-2"]).toEqual({ action: "update", level: "C1" });
    expect(decisions["interests-1"]).toEqual({ action: "update", target: "Running" });
    expect(decisions["personal"]).toEqual({ action: "update", fields: ["phone"] });
  });

  it("flags choices that cannot be sent", () => {
    const choices = initialChoices(review);
    choices.items["experiences-1"]!.addFields = [];
    const problems = incompleteChoices(review, choices);
    expect(problems.some((p) => p.startsWith("experiences-1 : "))).toBe(true);
    expect(problems.some((p) => p.startsWith("languages-1 : "))).toBe(true); // German without level
  });

  it("dispatches backend problems to their proposal", () => {
    const grouped = problemsByProposal([
      "skills-2 : déjà présente.",
      "personal : moins précis.",
      "autre erreur",
    ]);
    expect(grouped).toEqual({
      "skills-2": ["déjà présente."],
      personal: ["moins précis."],
      _general: ["autre erreur"],
    });
  });

  it("sends no overrides when nothing was corrected", () => {
    const decisions = buildDecisions(review, initialChoices(review));
    for (const decision of Object.values(decisions))
      expect(decision).not.toHaveProperty("overrides");
  });

  it("sends corrected values of the taken fields only, trimmed", () => {
    const choices = initialChoices(review);
    const exp = choices.items["experiences-1"]!;
    exp.addFields = ["company", "title", "start_date"];
    exp.corrections = {
      company: "  Acme SA ",
      title: "Dev", // same as extracted: not sent
      start_date: "2024-03",
      location: "Lyon", // field not taken: not sent
    };
    const update = choices.items["experiences-2"]!;
    update.action = "update";
    update.updateFields = ["skills"];
    update.corrections = { skills: ["Python", " ", "PyTorch"] };
    choices.personal.corrections = { phone: "+33 7 00 00 00 00", city: "Lyon" };

    const decisions = buildDecisions(review, choices);
    expect(decisions["experiences-1"]).toEqual({
      action: "add",
      fields: ["company", "title", "start_date"],
      overrides: { company: "Acme SA", start_date: "2024-03" },
    });
    expect(decisions["experiences-1"]).not.toHaveProperty("allow_duplicate");
    expect(decisions["experiences-2"]).toEqual({
      action: "update",
      fields: ["skills"],
      target_id: "geo",
      overrides: { skills: ["Python", "PyTorch"] },
    });
    expect(decisions["personal"]).toEqual({
      action: "update",
      fields: ["phone"],
      overrides: { phone: "+33 7 00 00 00 00" },
    });
  });

  it("sends corrected names of skills, languages and interests", () => {
    const choices = initialChoices(review);
    choices.skills["skills-1"]!.correction = "Docker Compose";
    choices.languages["languages-1"]!.correction = "Allemand";
    choices.languages["languages-1"]!.level = "B1";
    choices.languages["languages-2"]!.action = "update";
    choices.languages["languages-2"]!.correction = "English"; // not sent for an update
    choices.interests["interests-1"]!.action = "update";
    choices.interests["interests-1"]!.correction = "Trail";

    const decisions = buildDecisions(review, choices);
    expect(decisions["skills-1"]).toEqual({
      action: "add",
      category: "devops",
      create_category: true,
      overrides: { skill: "Docker Compose" },
    });
    expect(decisions["languages-1"]).toEqual({
      action: "add",
      level: "B1",
      overrides: { language: "Allemand" },
    });
    expect(decisions["languages-2"]).toEqual({ action: "update", level: "C1" });
    expect(decisions["interests-1"]).toEqual({
      action: "update",
      target: "Running",
      overrides: { interest: "Trail" },
    });
  });

  it("flags empty corrections before sending", () => {
    const choices = initialChoices(review);
    choices.items["experiences-1"]!.corrections = { company: "  " };
    choices.personal.corrections = { phone: "" };
    choices.interests["interests-1"]!.action = "add";
    choices.interests["interests-1"]!.correction = " ";
    const problems = incompleteChoices(review, choices);
    expect(problems.some((p) => p.startsWith("experiences-1 : la correction"))).toBe(true);
    expect(problems.some((p) => p.startsWith("personal : la correction"))).toBe(true);
    expect(problems.some((p) => p.startsWith("interests-1 : la correction"))).toBe(true);
  });

  it("a corrected name makes the duplicate status uncertain and allows confirming", () => {
    const choices = initialChoices(review);
    const exp = choices.items["experiences-1"]!; // status "new"
    expect(correctedMatchFields("experiences", exp, review.experiences[0]!)).toEqual([]);
    exp.corrections = { company: "Geo" };
    exp.allowDuplicate = true;
    expect(correctedMatchFields("experiences", exp, review.experiences[0]!)).toEqual(["company"]);
    expect(buildDecisions(review, choices)["experiences-1"]).toMatchObject({
      allow_duplicate: true,
      overrides: { company: "Geo" },
    });
  });
});

// ---------- Actions that apply_import.py always refuses ----------

// Values computed with Python: candidate.review_import._norm / candidate.manager._category_key
const PYTHON_NORM: Record<string, string> = {
  Python: "python",
  "  PyTorch  ": "pytorch",
  "Télécom SudParis": "telecom sudparis",
  ÉCHECS: "echecs",
  "C++": "c",
  "C#": "c",
  "Node.js": "node js",
  "scikit-learn": "scikit learn",
  "Scikit Learn": "scikit learn",
  "CI/CD": "ci cd",
  "Course à pied": "course a pied",
  Français: "francais",
  "Machine   Learning": "machine learning",
  machine_learning: "machine learning",
  Œuvre: "uvre",
  naïve: "naive",
  Straße: "strae",
  "L'Oréal": "l oreal",
  "": "",
  "1er Prix": "1er prix",
};
// candidate.review_import._skill_norm (same table as in tests/test_apply_import.py)
const PYTHON_SKILL_NORM: Record<string, string> = {
  C: "c",
  "C++": "c++",
  "C#": "c#",
  "c++ ": "c++",
  "  PYTHON ": "python",
  Python: "python",
  "F#": "f#",
  "Node.js": "node js",
  "scikit-learn": "scikit learn",
  "Scikit Learn": "scikit learn",
  ".NET": "net",
  "CI/CD": "ci cd",
  Télécom: "telecom",
  "Machine   Learning": "machine learning",
  "": "",
};
const PYTHON_CATEGORY_KEY: Record<string, string> = {
  "Machine Learning": "machine_learning",
  machine_learning: "machine_learning",
  "Computer-Vision": "computer_vision",
  "Données & IA": "donnees_ia",
};

const profile = {
  personal: { first_name: "Jane", last_name: "Doe" },
  career: {},
  education: [],
  experiences: [{ id: "geo", company: "Geo", title: "CTO" }],
  projects: [],
  skills: { programming: ["Python"], tools: ["Git"] },
  languages: [{ language: "English", level: "Fluent" }],
  interests: ["Running", "Tennis"],
  preferences: {},
} as CandidateProfile;

// Same review, with a second "docker" skill to test duplicates within one import
const batchReview: ImportReview = {
  ...review,
  skills: [
    ...review.skills,
    {
      proposal_id: "skills-3",
      category: "devops",
      skill: "docker",
      category_in_profile: null,
      status: "new",
      matches: [],
    },
  ],
};

describe("unavailable actions (refused by apply_import.py even with allow_duplicate)", () => {
  it("normalizes exactly like the Python backend", () => {
    for (const [text, expected] of Object.entries(PYTHON_NORM))
      expect(norm(text), text).toBe(expected);
    for (const [text, expected] of Object.entries(PYTHON_CATEGORY_KEY))
      expect(categoryKey(text), text).toBe(expected);
  });

  it("blocks a skill already in the chosen category, not in another one", () => {
    const choices = initialChoices(review);
    choices.skills["skills-2"]!.allowDuplicate = true; // Python, programming: refused anyway
    expect(unavailableActions(review, choices, profile)["skills-2"]?.add).toMatch(
      /déjà dans la catégorie « Programming »/,
    );
    choices.skills["skills-2"]!.category = "tools"; // another category: possible, with confirmation
    expect(unavailableActions(review, choices, profile)["skills-2"]).toBeUndefined();
    expect(skillInProfile(profile, "python")).toBe(true);
  });

  it("follows corrections instead of the old status", () => {
    const choices = initialChoices(review);
    const docker = choices.skills["skills-1"]!; // new, devops (new category)
    expect(unavailableActions(review, choices, profile)["skills-1"]).toBeUndefined();
    docker.correction = "PYTHON ";
    docker.category = "Programming";
    docker.createCategory = false;
    expect(unavailableActions(review, choices, profile)["skills-1"]?.add).toBeDefined();
    docker.correction = "Rust";
    expect(unavailableActions(review, choices, profile)["skills-1"]).toBeUndefined();

    const python = choices.skills["skills-2"]!; // "Déjà présent" in programming
    python.correction = "Julia";
    expect(unavailableActions(review, choices, profile)["skills-2"]).toBeUndefined();
  });

  it("blocks a language with the same name, not an equivalent one", () => {
    const choices = initialChoices(review);
    expect(unavailableActions(review, choices, profile)["languages-2"]).toBeUndefined(); // Anglais ≈ English
    choices.languages["languages-1"]!.correction = " english";
    expect(unavailableActions(review, choices, profile)["languages-1"]?.add).toMatch(
      /déjà dans ton profil/,
    );
  });

  it("blocks an identical interest and a rename onto another existing interest", () => {
    const choices = initialChoices(review);
    const run = choices.interests["interests-1"]!; // « Course à pied », close to Running
    expect(unavailableActions(review, choices, profile)["interests-1"]).toBeUndefined();
    run.correction = "TENNIS";
    expect(unavailableActions(review, choices, profile)["interests-1"]).toEqual({
      add: "« TENNIS » est déjà dans tes centres d'intérêt.",
      update:
        "« TENNIS » est déjà dans tes centres d'intérêt : impossible de renommer « Running » ainsi.",
    });
    run.correction = "running"; // only the case of the target changes: allowed by rename_interest
    expect(unavailableActions(review, choices, profile)["interests-1"]?.update).toBeUndefined();
  });

  it("blocks the same value twice in one import, and updates when another proposal changes", () => {
    const choices = initialChoices(batchReview); // Docker and docker, both added to devops
    expect(unavailableActions(batchReview, choices, profile)["skills-1"]).toBeUndefined();
    expect(unavailableActions(batchReview, choices, profile)["skills-3"]?.add).toMatch(
      /autre proposition de cet import/,
    );
    choices.skills["skills-1"]!.action = "skip"; // the first one is skipped: the second is possible
    expect(unavailableActions(batchReview, choices, profile)["skills-3"]).toBeUndefined();
    choices.skills["skills-1"]!.action = "add";
    choices.skills["skills-3"]!.category = "tools"; // other category: no conflict
    choices.skills["skills-3"]!.createCategory = false;
    expect(unavailableActions(batchReview, choices, profile)["skills-3"]).toBeUndefined();
  });

  it("a proposal refused for another reason does not block the next one (like the backend)", () => {
    const choices = initialChoices(batchReview);
    // First "docker" corrected to Python in tools without confirmation: refused by the backend before
    // being counted, so it does not reserve "python" in tools
    Object.assign(choices.skills["skills-1"]!, {
      correction: "Python",
      category: "tools",
      createCategory: false,
    });
    Object.assign(choices.skills["skills-3"]!, {
      correction: "python",
      category: "tools",
      createCategory: false,
    });
    expect(unavailableActions(batchReview, choices, profile)["skills-3"]).toBeUndefined();
    choices.skills["skills-1"]!.allowDuplicate = true;
    expect(unavailableActions(batchReview, choices, profile)["skills-3"]?.add).toBeDefined();
  });

  it("reports a chosen impossible action without changing the choice", () => {
    const choices = initialChoices(review);
    choices.languages["languages-1"]!.correction = "English";
    choices.languages["languages-1"]!.level = "B1";
    const problems = incompleteChoices(review, choices, profile);
    expect(problems).toContain("languages-1 : « English » est déjà dans ton profil.");
    expect(choices.languages["languages-1"]!.action).toBe("add");
    expect(incompleteChoices(review, choices)).not.toContain(problems[0]); // no profile: backend decides
  });

  it("names the existing element when a corrected item name matches it exactly", () => {
    const choices = initialChoices(review);
    const exp = choices.items["experiences-1"]!;
    expect(correctedNameMatches("experiences", exp, review.experiences[0]!, profile)).toEqual([]);
    exp.corrections = { company: " GEO" };
    expect(correctedNameMatches("experiences", exp, review.experiences[0]!, profile)).toEqual([
      "Geo",
    ]);
  });

  it("normalizes skill names like the Python backend: C, C++ and C# are distinct", () => {
    for (const [text, expected] of Object.entries(PYTHON_SKILL_NORM))
      expect(skillNorm(text), text).toBe(expected);
  });

  it("lets C, C++ and C# coexist in a category, but not a second C++", () => {
    const cReview: ImportReview = {
      ...review,
      skills: ["C#", "c++ ", "C++", "PYTHON"].map((skill, n) => ({
        proposal_id: `skills-${n + 1}`,
        category: "programming",
        skill,
        category_in_profile: "programming",
        status: "new" as const,
        matches: [],
      })),
    };
    const cProfile = { ...profile, skills: { programming: ["Python", "C"] } } as CandidateProfile;
    const choices = initialChoices(cReview);
    choices.skills["skills-4"]!.action = "add";
    const unavailable = unavailableActions(cReview, choices, cProfile);
    expect(unavailable["skills-1"]).toBeUndefined(); // C# next to C
    expect(unavailable["skills-2"]).toBeUndefined(); // first C++
    expect(unavailable["skills-3"]?.add).toMatch(/autre proposition de cet import/); // second C++
    expect(unavailable["skills-4"]?.add).toMatch(/« PYTHON » est déjà dans la catégorie/);

    const withCpp = { ...profile, skills: { programming: ["C", "C++"] } } as CandidateProfile;
    expect(unavailableActions(cReview, choices, withCpp)["skills-2"]?.add).toMatch(
      /déjà dans la catégorie/,
    );
    expect(unavailableActions(cReview, choices, withCpp)["skills-1"]).toBeUndefined();
  });
});
