import { describe, expect, it } from "vitest";

import {
  cleanDocument,
  educationKeys,
  formatDates,
  generationSteps,
  layoutZones,
  profileEntries,
  shortLocation,
  slug,
  zoneIdFor,
} from "@/features/cvs/adapters";
import { documentFixture, layoutFixture, profileFixture, task } from "./fixtures/cvFixtures";

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
