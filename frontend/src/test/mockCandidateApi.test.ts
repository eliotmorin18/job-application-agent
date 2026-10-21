import { beforeEach, describe, expect, it } from "vitest";

import { mockCandidateApi as api, resetMockCandidate } from "@/services/api/mockCandidateApi";

describe("mockCandidateApi", () => {
  beforeEach(() => resetMockCandidate());

  it("generates an id for new experiences", async () => {
    const created = await api.addItem("experiences", { company: "Acme", title: "Dev" });
    expect(created.id).toMatch(/^exp_/);
  });

  it("addresses legacy education entries without id by position", async () => {
    await api.updateItem("education", "index-1", { degree: "Erasmus" });
    const p = await api.getProfile();
    expect(p.education[1]?.degree).toBe("Erasmus");
    expect(p.education[1]?.id).toBeUndefined();
  });

  it("removes a skill category when its last skill is deleted", async () => {
    await api.addSkill("Cloud", "AWS");
    await api.deleteSkill("Cloud", "AWS");
    expect((await api.getProfile()).skills["Cloud"]).toBeUndefined();
  });

  it("rejects a duplicate language", async () => {
    await expect(api.addLanguage("français", "C1")).rejects.toThrow();
  });
});
