import { mockCandidate } from "@/data/mockCandidate";
import type { CandidateApi, CandidateProfile, ItemSection, SectionItem } from "./types";

// In-memory store: a page reload resets everything.
let db: CandidateProfile = structuredClone(mockCandidate);

const delay = (ms = 180) => new Promise((r) => setTimeout(r, ms));
const clone = <T>(v: T): T => structuredClone(v);

const prefixes: Record<ItemSection, string> = {
  experiences: "exp",
  education: "edu",
  projects: "prj",
};

function generateId(section: ItemSection) {
  return `${prefixes[section]}_${Math.random().toString(16).slice(2, 8)}`;
}

function list(section: ItemSection): SectionItem[] {
  return db[section] as SectionItem[];
}

function findIndex(section: ItemSection, id: string) {
  const idx = list(section).findIndex((item, i) => (item.id ?? `index-${i}`) === id);
  if (idx === -1) throw new Error("Élément introuvable.");
  return idx;
}

function requireText(value: string, label: string) {
  const v = value.trim();
  if (!v) throw new Error(`${label} ne peut pas être vide.`);
  return v;
}

export const mockCandidateApi: CandidateApi = {
  async getProfile() {
    await delay(250);
    return clone(db);
  },

  async addItem(section, data) {
    await delay();
    const item = { ...clone(data), id: generateId(section) };
    (list(section) as unknown[]).unshift(item);
    return clone(item) as never;
  },

  async updateItem(section, id, changes) {
    await delay();
    const idx = findIndex(section, id);
    const current = list(section)[idx]!;
    const { id: _ignored, ...rest } = changes as { id?: string };
    const updated = { ...current, ...clone(rest), id: current.id } as SectionItem;
    if (updated.id === undefined) delete (updated as { id?: string }).id;
    list(section)[idx] = updated;
    return clone(updated) as never;
  },

  async deleteItem(section, id) {
    await delay();
    list(section).splice(findIndex(section, id), 1);
  },

  async updatePersonal(changes) {
    await delay();
    db.personal = { ...db.personal, ...clone(changes) };
    return clone(db.personal);
  },

  async updateCareer(changes) {
    await delay();
    db.career = { ...db.career, ...clone(changes) };
    return clone(db.career);
  },

  async updatePreferences(changes) {
    await delay();
    db.preferences = { ...db.preferences, ...clone(changes) };
    return clone(db.preferences);
  },

  async addPreference(category, value) {
    await delay();
    const v = requireText(value, "La valeur");
    const current = db.preferences[category] ?? [];
    if (current.includes(v)) throw new Error("Cette valeur existe déjà.");
    db.preferences = { ...db.preferences, [category]: [...current, v] };
    return clone(db.preferences);
  },

  async addSkill(category, skill) {
    await delay();
    const cat = requireText(category, "La catégorie");
    const s = requireText(skill, "La compétence");
    const current = db.skills[cat] ?? [];
    if (current.includes(s)) throw new Error("Cette compétence existe déjà dans la catégorie.");
    db.skills = { ...db.skills, [cat]: [...current, s] };
  },

  async renameSkill(category, skill, newName) {
    await delay();
    const n = requireText(newName, "La compétence");
    const current = db.skills[category];
    if (!current?.includes(skill)) throw new Error("Compétence introuvable.");
    if (n !== skill && current.includes(n)) throw new Error("Cette compétence existe déjà.");
    db.skills = { ...db.skills, [category]: current.map((s) => (s === skill ? n : s)) };
  },

  async deleteSkill(category, skill) {
    await delay();
    const remaining = (db.skills[category] ?? []).filter((s) => s !== skill);
    const next = { ...db.skills };
    if (remaining.length) next[category] = remaining;
    else delete next[category];
    db.skills = next;
  },

  async addLanguage(language, level) {
    await delay();
    const l = requireText(language, "La langue");
    if (db.languages.some((x) => x.language.toLowerCase() === l.toLowerCase()))
      throw new Error("Cette langue existe déjà.");
    db.languages = [...db.languages, { language: l, level }];
  },

  async updateLanguageLevel(language, level) {
    await delay();
    db.languages = db.languages.map((x) => (x.language === language ? { ...x, level } : x));
  },

  async deleteLanguage(language) {
    await delay();
    db.languages = db.languages.filter((x) => x.language !== language);
  },

  async addInterest(interest) {
    await delay();
    const i = requireText(interest, "Le centre d'intérêt");
    if (db.interests.includes(i)) throw new Error("Ce centre d'intérêt existe déjà.");
    db.interests = [...db.interests, i];
  },

  async renameInterest(interest, newName) {
    await delay();
    const n = requireText(newName, "Le centre d'intérêt");
    db.interests = db.interests.map((x) => (x === interest ? n : x));
  },

  async deleteInterest(interest) {
    await delay();
    db.interests = db.interests.filter((x) => x !== interest);
  },
};

/** Test helper: restore the initial demo data. */
export function resetMockCandidate() {
  db = structuredClone(mockCandidate);
}
