// User choices on an import review, and their translation into the decisions accepted by
// candidate/apply_import.py. No comparison or saving logic here: statuses, matches and
// differences come from the backend (review_import.py), which also validates the decisions.

import { formatCategory } from "../candidate/format";
import type {
  CandidateProfile,
  ImportDecisions,
  ImportReview,
  ItemMatch,
  ItemProposal,
  Overrides,
  ProposalStatus,
} from "@/services/api/types";

export type ItemSectionKey = "experiences" | "projects" | "education";
export const ITEM_SECTION_KEYS: ItemSectionKey[] = ["experiences", "education", "projects"];

/** Fields used by review_import.py to detect duplicates: correcting them may change the status. */
export const MATCH_FIELDS: Record<ItemSectionKey, string[]> = {
  experiences: ["company", "title"],
  projects: ["name"],
  education: ["school", "degree"],
};

export type CorrectedValue = string | string[];

/** Name field of each kind (manager.ITEM_KINDS id_from), checked by apply_import after a correction. */
export const NAME_FIELD: Record<ItemSectionKey, string> = {
  experiences: "company",
  projects: "name",
  education: "school",
};

export interface ItemChoice {
  action: "add" | "update" | "skip";
  addFields: string[]; // fields taken from the extraction when adding
  allowDuplicate: boolean;
  target: number; // index in proposal.matches when updating
  updateFields: string[]; // fields taken from the extraction when updating
  allowLessPrecise: boolean;
  corrections: Record<string, CorrectedValue>; // user corrections, sent only on apply
}
export interface SkillChoice {
  action: "add" | "skip";
  category: string; // existing category, or a new one (createCategory)
  createCategory: boolean;
  allowDuplicate: boolean;
  correction: string | null; // corrected skill name
}
export interface LanguageChoice {
  action: "add" | "update" | "skip";
  level: string;
  allowDuplicate: boolean;
  correction: string | null; // corrected language name (when adding)
}
export interface InterestChoice {
  action: "add" | "update" | "skip";
  target: string; // existing interest replaced by the extracted one
  allowDuplicate: boolean;
  correction: string | null; // corrected interest
}
export interface PersonalChoice {
  fields: string[];
  allowLessPrecise: boolean;
  corrections: Record<string, string>;
}

export interface Choices {
  items: Record<string, ItemChoice>;
  skills: Record<string, SkillChoice>;
  languages: Record<string, LanguageChoice>;
  interests: Record<string, InterestChoice>;
  personal: PersonalChoice;
}

const isNew = (status: ProposalStatus) => status === "new";

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const trimmed = (v: CorrectedValue) =>
  Array.isArray(v) ? v.map((x) => x.trim()).filter(Boolean) : v.trim();
const isEmpty = (v: CorrectedValue) => (Array.isArray(v) ? v.length === 0 : v === "");

/** Corrections of the taken fields that really differ from the extraction (nothing else is sent). */
function overridesFor(
  corrections: Record<string, CorrectedValue>,
  taken: string[],
  extracted: Record<string, unknown>,
): Overrides | undefined {
  const out: Overrides = {};
  for (const [field, value] of Object.entries(corrections)) {
    const v = trimmed(value);
    if (taken.includes(field) && !same(v, extracted[field])) out[field] = v;
  }
  return Object.keys(out).length ? out : undefined;
}

/** A corrected name, if it differs from the extracted one. */
function nameOverride(correction: string | null, extracted: string): string | undefined {
  const v = correction?.trim();
  return v && v !== extracted ? v : undefined;
}

/**
 * Corrections that may make the duplicate status of the review outdated
 * (the status was computed on the extracted value).
 */
export function correctedMatchFields(
  section: ItemSectionKey,
  choice: ItemChoice,
  proposal: ItemProposal,
) {
  const taken = choice.action === "update" ? choice.updateFields : choice.addFields;
  const overrides = overridesFor(choice.corrections, taken, proposal.data) ?? {};
  return MATCH_FIELDS[section].filter((f) => f in overrides);
}

/** Fields proposed by default for an update: missing in the profile or new list values, never uncertain ones. */
export function defaultUpdateFields(
  proposal: ItemProposal,
  match: ItemMatch | undefined,
): string[] {
  if (!match) return [];
  return Object.entries(match.differences)
    .filter(
      ([field, diff]) => diff.change !== "different" && !proposal.uncertain_fields.includes(field),
    )
    .map(([field]) => field);
}

/** Defaults: what is new is added (without uncertain fields), everything else is skipped. */
export function initialChoices(review: ImportReview): Choices {
  const items: Record<string, ItemChoice> = {};
  for (const section of ITEM_SECTION_KEYS) {
    for (const p of review[section]) {
      items[p.proposal_id] = {
        action: isNew(p.status) ? "add" : "skip",
        addFields: Object.keys(p.data).filter((f) => !p.uncertain_fields.includes(f)),
        allowDuplicate: false,
        target: 0,
        updateFields: defaultUpdateFields(p, p.matches[0]),
        allowLessPrecise: false,
        corrections: {},
      };
    }
  }

  const skills: Record<string, SkillChoice> = {};
  for (const s of review.skills)
    skills[s.proposal_id] = {
      action: isNew(s.status) ? "add" : "skip",
      category: s.category_in_profile ?? s.category,
      createCategory: s.category_in_profile === null,
      allowDuplicate: false,
      correction: null,
    };

  const languages: Record<string, LanguageChoice> = {};
  for (const l of review.languages)
    languages[l.proposal_id] = {
      action: isNew(l.status) ? "add" : "skip",
      level: l.level ?? "",
      allowDuplicate: false,
      correction: null,
    };

  const interests: Record<string, InterestChoice> = {};
  for (const i of review.interests)
    interests[i.proposal_id] = {
      action: isNew(i.status) ? "add" : "skip",
      target: i.matches[0] ?? "",
      allowDuplicate: false,
      correction: null,
    };

  return {
    items,
    skills,
    languages,
    interests,
    personal: {
      fields: review.personal
        .filter((p) => p.status === "missing_in_profile" && !p.uncertain)
        .map((p) => p.field),
      allowLessPrecise: false,
      corrections: {},
    },
  };
}

/** Choices that cannot be sent as they are (checked before calling the backend). */
export function incompleteChoices(
  review: ImportReview,
  choices: Choices,
  profile?: CandidateProfile | undefined,
): string[] {
  const problems: string[] = [];
  // A chosen action that apply_import.py would always refuse (never switched automatically)
  const unavailable = unavailableActions(review, choices, profile);
  const chosen: Record<string, string | undefined> = Object.fromEntries(
    [choices.skills, choices.languages, choices.interests].flatMap((group) =>
      Object.entries(group).map(([id, c]) => [id, c.action]),
    ),
  );
  for (const [id, u] of Object.entries(unavailable)) {
    const action = chosen[id];
    const reason = action === "add" ? u.add : action === "update" ? u.update : undefined;
    if (reason) problems.push(`${id} : ${reason}`);
  }
  for (const section of ITEM_SECTION_KEYS) {
    for (const p of review[section]) {
      const c = choices.items[p.proposal_id];
      if (c?.action === "add" && c.addFields.length === 0)
        problems.push(
          `${p.proposal_id} : coche au moins un champ à ajouter, ou ignore la proposition.`,
        );
      if (c?.action === "update" && c.updateFields.length === 0)
        problems.push(
          `${p.proposal_id} : coche au moins un champ à reprendre, ou ignore la proposition.`,
        );
      const taken =
        c?.action === "add" ? c.addFields : c?.action === "update" ? c.updateFields : [];
      for (const [field, value] of Object.entries(c?.corrections ?? {}))
        if (taken.includes(field) && isEmpty(trimmed(value)))
          problems.push(
            `${p.proposal_id} : la correction de « ${field} » est vide ; décoche plutôt ce champ.`,
          );
    }
  }
  for (const [field, value] of Object.entries(choices.personal.corrections))
    if (choices.personal.fields.includes(field) && !value.trim())
      problems.push(`personal : la correction de « ${field} » est vide ; décoche plutôt ce champ.`);
  const names: (readonly [string, { action: string; correction: string | null } | undefined])[] = [
    ...review.skills.map((s) => [s.proposal_id, choices.skills[s.proposal_id]] as const),
    ...review.languages.map((l) => [l.proposal_id, choices.languages[l.proposal_id]] as const),
    ...review.interests.map((i) => [i.proposal_id, choices.interests[i.proposal_id]] as const),
  ];
  for (const [id, c] of names)
    if (c && c.action !== "skip" && c.correction !== null && !c.correction.trim())
      problems.push(`${id} : la correction est vide.`);
  for (const l of review.languages) {
    const c = choices.languages[l.proposal_id];
    if (c && c.action !== "skip" && !c.level.trim())
      problems.push(`${l.proposal_id} : indique le niveau de « ${l.language} ».`);
  }
  return problems;
}

/** Decisions in the exact format of apply_import.py: only supported options, false/empty ones omitted. */
export function buildDecisions(review: ImportReview, choices: Choices): ImportDecisions {
  const decisions: ImportDecisions = {};

  for (const section of ITEM_SECTION_KEYS) {
    for (const p of review[section]) {
      const c = choices.items[p.proposal_id];
      if (!c || c.action === "skip") {
        decisions[p.proposal_id] = { action: "skip" };
      } else if (c.action === "add") {
        const overrides = overridesFor(c.corrections, c.addFields, p.data);
        // Confirmation shown for a duplicate, or when a correction may have made the status outdated
        const confirmable = !isNew(p.status) || correctedMatchFields(section, c, p).length > 0;
        decisions[p.proposal_id] = {
          action: "add",
          fields: c.addFields,
          ...(confirmable && c.allowDuplicate ? { allow_duplicate: true } : {}),
          ...(overrides ? { overrides } : {}),
        };
      } else {
        const match = p.matches[c.target];
        const overrides = overridesFor(c.corrections, c.updateFields, p.data);
        decisions[p.proposal_id] = {
          action: "update",
          fields: c.updateFields,
          ...(match?.id ? { target_id: match.id } : { target_position: match?.position ?? 0 }),
          ...(c.allowLessPrecise ? { allow_less_precise: true } : {}),
          ...(overrides ? { overrides } : {}),
        };
      }
    }
  }

  for (const s of review.skills) {
    const c = choices.skills[s.proposal_id];
    const skill = c && nameOverride(c.correction, s.skill);
    decisions[s.proposal_id] =
      !c || c.action === "skip"
        ? { action: "skip" }
        : {
            action: "add",
            category: c.category,
            ...(c.createCategory ? { create_category: true } : {}),
            ...(c.allowDuplicate ? { allow_duplicate: true } : {}),
            ...(skill ? { overrides: { skill } } : {}),
          };
  }

  for (const l of review.languages) {
    const c = choices.languages[l.proposal_id];
    const level = c?.level.trim();
    const language = c && nameOverride(c.correction, l.language);
    if (!c || c.action === "skip") decisions[l.proposal_id] = { action: "skip" };
    else if (c.action === "add")
      decisions[l.proposal_id] = {
        action: "add",
        ...(level ? { level } : {}),
        ...((!isNew(l.status) || language) && c.allowDuplicate ? { allow_duplicate: true } : {}),
        ...(language ? { overrides: { language } } : {}),
      };
    else decisions[l.proposal_id] = { action: "update", ...(level ? { level } : {}) };
  }

  for (const i of review.interests) {
    const c = choices.interests[i.proposal_id];
    const interest = c && nameOverride(c.correction, i.interest);
    const overrides = interest ? { overrides: { interest } } : {};
    if (!c || c.action === "skip") decisions[i.proposal_id] = { action: "skip" };
    else if (c.action === "add")
      decisions[i.proposal_id] = {
        action: "add",
        ...((!isNew(i.status) || interest) && c.allowDuplicate ? { allow_duplicate: true } : {}),
        ...overrides,
      };
    else decisions[i.proposal_id] = { action: "update", target: c.target, ...overrides };
  }

  if (choices.personal.fields.length) {
    const extracted = Object.fromEntries(review.personal.map((p) => [p.field, p.extracted]));
    const overrides = overridesFor(
      choices.personal.corrections,
      choices.personal.fields,
      extracted,
    );
    decisions["personal"] = {
      action: "update",
      fields: choices.personal.fields,
      ...(choices.personal.allowLessPrecise ? { allow_less_precise: true } : {}),
      ...(overrides ? { overrides } : {}),
    };
  }

  return decisions;
}

/** Backend problems start with "<proposal_id> : " — used to show each one on its card. */
export function problemsByProposal(problems: string[]): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const problem of problems) {
    const match = /^([a-z]+-\d+|personal) : (.*)$/s.exec(problem);
    const key = match?.[1] ?? "_general";
    (out[key] ??= []).push(match?.[2] ?? problem);
  }
  return out;
}

// ---------- Actions that apply_import.py always refuses ----------
// Only the refusals that hold even with allow_duplicate. Everything else (confirmable duplicates,
// dates, URLs...) is left to the backend, which stays the final authority.

/**
 * Same normalization as `_norm` in candidate/review_import.py (manager._slug): accents, case,
 * spaces and punctuation ignored. « Télécom SudParis » -> « telecom sudparis ».
 */
export function norm(text: unknown): string {
  const ascii = String(text ?? "")
    .normalize("NFKD")
    .replace(/[^\u0020-\u007e]/g, "") // like encode("ascii", "ignore"); only [a-z0-9] is kept below
    .toLowerCase();
  return (ascii.match(/[a-z0-9]+/g) ?? []).join(" ");
}

/**
 * Same as `_skill_norm` in candidate/review_import.py: like `norm`, but « + » and « # » count,
 * so « C », « C++ » and « C# » are three skills. Only used for skill names.
 */
export function skillNorm(text: unknown): string {
  const ascii = String(text ?? "")
    .normalize("NFKD")
    .replace(/[^\u0020-\u007e]/g, "")
    .toLowerCase();
  return (ascii.match(/[a-z0-9+#]+/g) ?? []).join(" ");
}

/** Same as manager._category_key: « Machine Learning » -> « machine_learning ». */
export const categoryKey = (text: string) => norm(text).replace(/ /g, "_");

/** Same as manager._same (used to rename an interest): only case and surrounding spaces ignored. */
const sameText = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

const effective = (correction: string | null, extracted: string) => correction?.trim() || extracted;

/** Skill already in some category of the profile (adding it elsewhere needs allow_duplicate). */
export function skillInProfile(profile: CandidateProfile | undefined, skill: string): boolean {
  return Object.values(profile?.skills ?? {}).some((values) =>
    (values ?? []).some((v) => skillNorm(v) === skillNorm(skill)),
  );
}

export interface Unavailable {
  add?: string | undefined;
  update?: string | undefined;
}

/**
 * Per proposal, the actions apply_import.py would refuse whatever the confirmation, with the reason.
 * Checked on the effective value (corrected or extracted) against the current profile, and in the
 * same order as the backend for duplicates within the same import (the first proposal wins).
 */
export function unavailableActions(
  review: ImportReview,
  choices: Choices,
  profile: CandidateProfile | undefined,
): Record<string, Unavailable> {
  const out: Record<string, Unavailable> = {};
  if (!profile) return out;
  const batch = new Set<string>();

  for (const s of review.skills) {
    const c = choices.skills[s.proposal_id];
    if (!c) continue;
    const skill = effective(c.correction, s.skill);
    const target = Object.keys(profile.skills).find(
      (k) => categoryKey(k) === categoryKey(c.category),
    );
    const elsewhere = skillInProfile(profile, skill);
    const key = `${categoryKey(c.category)}|${skillNorm(skill)}`;
    if (target && (profile.skills[target] ?? []).some((v) => skillNorm(v) === skillNorm(skill)))
      out[s.proposal_id] = {
        add: `« ${skill} » est déjà dans la catégorie « ${formatCategory(target)} » : choisis une autre catégorie ou ignore-la.`,
      };
    else if (batch.has(key))
      out[s.proposal_id] = {
        add: `« ${skill} » est déjà ajoutée dans cette catégorie par une autre proposition de cet import.`,
      };
    else if (c.action === "add" && (target || c.createCategory) && (!elsewhere || c.allowDuplicate))
      batch.add(key);
  }

  batch.clear();
  for (const l of review.languages) {
    const c = choices.languages[l.proposal_id];
    if (!c) continue;
    const language = effective(c.correction, l.language);
    if (profile.languages.some((k) => norm(k.language) === norm(language)))
      out[l.proposal_id] = {
        add:
          `« ${language} » est déjà dans ton profil` +
          (l.matches.length ? " : utilise « Mettre à jour le niveau »." : "."),
      };
    else if (batch.has(norm(language)))
      out[l.proposal_id] = {
        add: `« ${language} » est déjà ajoutée par une autre proposition de cet import.`,
      };
    else if (
      c.action === "add" &&
      (l.status !== "duplicate" || c.allowDuplicate) &&
      (c.level.trim() || l.level)
    )
      batch.add(norm(language));
  }

  batch.clear();
  for (const i of review.interests) {
    const c = choices.interests[i.proposal_id];
    if (!c) continue;
    const interest = effective(c.correction, i.interest);
    const u: Unavailable = {};
    if (profile.interests.some((k) => norm(k) === norm(interest)))
      u.add = `« ${interest} » est déjà dans tes centres d'intérêt.`;
    else if (batch.has(norm(interest)))
      u.add = `« ${interest} » est déjà ajouté par une autre proposition de cet import.`;
    else if (c.action === "add" && (i.status === "new" || c.allowDuplicate))
      batch.add(norm(interest));

    // Renaming: manager.rename_interest refuses a name already present at another position
    const targetPosition = profile.interests.findIndex((k) => sameText(k, c.target));
    const taken = profile.interests.findIndex((k) => sameText(k, interest));
    if (targetPosition !== -1 && taken !== -1 && taken !== targetPosition)
      u.update = `« ${interest} » est déjà dans tes centres d'intérêt : impossible de renommer « ${c.target} » ainsi.`;
    if (u.add || u.update) out[i.proposal_id] = u;
  }

  return out;
}

/**
 * Elements of the profile whose name is exactly the corrected one (same rule as
 * apply_import._corrected_name_exists): adding is still possible, but only with a confirmation.
 */
export function correctedNameMatches(
  section: ItemSectionKey,
  choice: ItemChoice,
  proposal: ItemProposal,
  profile: CandidateProfile | undefined,
): string[] {
  const field = NAME_FIELD[section];
  if (!profile || choice.action !== "add") return [];
  const overrides = overridesFor(choice.corrections, choice.addFields, proposal.data) ?? {};
  const name = overrides[field];
  if (typeof name !== "string") return [];
  return (profile[section] as unknown as Record<string, unknown>[])
    .filter((item) => norm(item[field]) === norm(name))
    .map((item) => String(item[field]));
}
