import { describe, expect, it } from "vitest";

import { cvTitle, formatTimestamp, taskText } from "@/features/cvs/format";

describe("formatTimestamp", () => {
  it("formats a creation date (Unix seconds, UTC) in French", () => {
    expect(formatTimestamp(1792663200)).toBe("22 oct. 2026"); // 2026-10-22T10:00:00Z
  });

  it("shows « Date inconnue » for an old CV without a reliable creation date", () => {
    expect(formatTimestamp(null)).toBe("Date inconnue");
    expect(formatTimestamp(undefined)).toBe("Date inconnue");
    expect(formatTimestamp(Number.NaN)).toBe("Date inconnue");
  });
});

describe("cvTitle", () => {
  it("falls back from the role to the job title, then to the folder name", () => {
    expect(cvTitle({ id: "dossier", role: "Data Engineer", job_title: "Stage" })).toBe(
      "Data Engineer",
    );
    expect(cvTitle({ id: "dossier", role: null, job_title: "Stage" })).toBe("Stage");
    expect(cvTitle({ id: "dossier", role: null, job_title: null })).toBe("dossier");
  });
});

describe("taskText (display only)", () => {
  it.each([
    [
      "Par exemple, tu pourrais dépouiller la presse spécialisée",
      "Dépouiller la presse spécialisée",
    ],
    ["par exemple : tu pourrais également préparer des slides", "Préparer des slides"],
    ["Tu pourrais construire un mapping des acteurs", "Construire un mapping des acteurs"],
    ["Par exemple, vous pourriez échanger avec les filiales", "Échanger avec les filiales"],
    ["For example, you could write a report", "Write a report"],
    ["Par exemple, analyser des brevets", "Analyser des brevets"],
  ])("%j -> %j", (input, expected) => {
    expect(taskText(input)).toBe(expected);
  });

  it("leaves a task without that opening unchanged", () => {
    expect(taskText("Revue de code hebdomadaire")).toBe("Revue de code hebdomadaire");
    expect(taskText("  Tu peux aussi lire  ")).toBe("Tu peux aussi lire");
    expect(taskText("Par exemple,")).toBe("Par exemple,");
  });
});
