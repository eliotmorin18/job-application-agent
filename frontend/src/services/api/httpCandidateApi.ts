import { request, segment } from "./httpClient";
import type { CandidateApi, ImportApi } from "./types";

/**
 * In the forms, an emptied field is `undefined`, which JSON.stringify would drop.
 * The backend expects `null` to clear a field, so keys are kept with `null`.
 */
function withNulls(changes: object): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(changes).map(([key, value]) => [key, value === undefined ? null : value]),
  );
}

export const httpCandidateApi: CandidateApi = {
  getProfile: () => request("GET", "/profile"),

  addItem: (section, data) => request<never>("POST", `/profile/${section}`, data),
  updateItem: (section, id, changes) =>
    request<never>("PATCH", `/profile/${section}/${segment(id)}`, withNulls(changes)),
  async deleteItem(section, id) {
    await request("DELETE", `/profile/${section}/${segment(id)}`);
  },

  updatePersonal: (changes) => request("PATCH", "/personal", withNulls(changes)),
  updateCareer: (changes) => request("PATCH", "/career", withNulls(changes)),
  updatePreferences: (changes) => request("PATCH", "/preferences", withNulls(changes)),
  addPreference: (category, value) =>
    request("POST", `/preferences/${segment(category)}`, { value }),

  async addSkill(category, skill, createCategory) {
    await request("POST", "/skills", {
      category,
      skill,
      ...(createCategory ? { create_category: true } : {}),
    });
  },
  async renameSkill(category, skill, newName) {
    await request("PATCH", `/skills/${segment(category)}/${segment(skill)}`, { new_name: newName });
  },
  async deleteSkill(category, skill) {
    await request("DELETE", `/skills/${segment(category)}/${segment(skill)}`);
  },

  async addLanguage(language, level) {
    await request("POST", "/languages", { language, level });
  },
  async updateLanguageLevel(language, level) {
    await request("PATCH", `/languages/${segment(language)}`, { level });
  },
  async deleteLanguage(language) {
    await request("DELETE", `/languages/${segment(language)}`);
  },

  async addInterest(interest) {
    await request("POST", "/interests", { interest });
  },
  async renameInterest(interest, newName) {
    await request("PATCH", `/interests/${segment(interest)}`, { new_name: newName });
  },
  async deleteInterest(interest) {
    await request("DELETE", `/interests/${segment(interest)}`);
  },
};

export const httpImportApi: ImportApi = {
  listImports: () => request("GET", "/imports"),
  importCv(file) {
    const form = new FormData();
    form.append("file", file);
    return request("POST", "/imports", form);
  },
  getReview: (importId) => request("GET", `/imports/${segment(importId)}/review`),
  applyImport: (importId, decisions) =>
    request("POST", `/imports/${segment(importId)}/apply`, { decisions }),
};
