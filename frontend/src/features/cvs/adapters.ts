// Adapters between the backend contract (services/api/cvTypes.ts) and the "Mes CV" components.
// No data is invented here: everything is derived from what FastAPI returns or from the candidate profile.

import type { CandidateProfile } from "@/services/api/types";
import type {
  CompletedAnalysis,
  CvDocument,
  CvEducation,
  CvExperience,
  CvLayout,
  CvProject,
  CvTask,
  Requirement,
  RequirementStatus,
} from "@/services/api/cvTypes";
import { leadSentences, splitSentences, taskText } from "./format";

// ---------- Selection and clickable zones ----------

/** Sections of the editor; "languages" is a tab of its own but shares the "skills" zone of the PDF. */
export type CvSectionKey =
  "profile" | "experiences" | "education" | "projects" | "skills" | "languages" | "interests";
export type ItemSection = "experiences" | "education" | "projects";

export interface CvSelection {
  section: CvSectionKey;
  /** Index of the selected entry in its list (experiences, education, projects). */
  index?: number | undefined;
}

/** One clickable zone of the PDF preview. Coordinates are normalized (0-1), origin top-left. */
export interface LayoutZone {
  id: string;
  section: CvSectionKey;
  index?: number | undefined;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

const LAYOUT_SECTIONS: Record<string, CvSectionKey> = {
  profile: "profile",
  experiences: "experiences",
  education: "education",
  projects: "projects",
  skills: "skills",
  interests: "interests",
};

/** layout.json regions -> zones. Item zones come after their section: they are on top and win the click. */
export function layoutZones(layout: CvLayout | null | undefined): LayoutZone[] {
  return (layout?.regions ?? []).flatMap((region) => {
    const [sectionKey, rawIndex] = region.key.split("/");
    const section = LAYOUT_SECTIONS[sectionKey ?? ""];
    if (!section) return [];
    const index = rawIndex !== undefined ? Number(rawIndex) : undefined;
    return [
      {
        id: index !== undefined ? `item:${section}/${index}` : `section:${section}`,
        section,
        index,
        page: region.page,
        x: region.left,
        y: region.top,
        width: region.right - region.left,
        height: region.bottom - region.top,
      },
    ];
  });
}

/** `items` with the element at `from` moved to `to` (reordering skills in the editor). */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved as T);
  return next;
}

// ---------- Editor / PDF split ----------

/** The editor takes 30 to 65 % of the split, and never less than EDITOR_MIN_PX. */
export const EDITOR_MIN_PERCENT = 30;
export const EDITOR_MAX_PERCENT = 65;
/** Seven section tabs on two lines at most, usable fields: measured in Chromium (tabs ≈ 581 px). */
export const EDITOR_MIN_PX = 360;

/**
 * Minimum size of the editor panel, in percent of the split of `width` pixels: 30 %, raised to keep
 * EDITOR_MIN_PX on small screens (sidebar open), never above the maximum. Unknown width: 30 %.
 */
export function editorMinPercent(width: number): number {
  if (!(width > 0)) return EDITOR_MIN_PERCENT;
  const floor = Math.ceil((EDITOR_MIN_PX / width) * 100);
  return Math.min(EDITOR_MAX_PERCENT, Math.max(EDITOR_MIN_PERCENT, floor));
}

/** Zone highlighted for the current selection (the languages share the skills zone). */
export function zoneIdFor(selection: CvSelection): string {
  const section = selection.section === "languages" ? "skills" : selection.section;
  return selection.index !== undefined
    ? `item:${section}/${selection.index}`
    : `section:${section}`;
}

// ---------- Generation steps (cv/pipeline.py) ----------

export const GENERATION_STEPS = [
  { key: "read_offer", label: "Lecture de l'offre" },
  { key: "analyze_offer", label: "Analyse de l'offre" },
  { key: "write_cv", label: "Rédaction du CV" },
  { key: "verify_cv", label: "Vérification contre le profil" },
  { key: "compile", label: "Compilation du PDF" },
  { key: "analyze_fit", label: "Analyse de correspondance" },
] as const;

const STEP_INDEX: Record<string, number> = {
  read_offer: 0,
  analyze_offer: 1,
  offer_analyzed: 1,
  write_cv: 2,
  verify_cv: 3,
  correct_cv: 3,
  verified: 3,
  compile: 4,
  analyze_fit: 5,
};

export type StepState = "pending" | "active" | "done" | "failed";

/** State of each generation step, from the task returned by GET /api/cvs/tasks/{id}. */
export function generationSteps(task: CvTask | undefined) {
  const current =
    task?.status === "completed" ? GENERATION_STEPS.length : (STEP_INDEX[task?.step ?? ""] ?? -1);
  return GENERATION_STEPS.map((step, index) => {
    let state: StepState = "pending";
    if (index < current) state = "done";
    else if (index === current)
      state =
        task?.status === "failed" ? "failed" : task?.status === "running" ? "active" : "pending";
    return { ...step, state };
  });
}

// ---------- Adding an entry from the candidate profile (same as cv/document.py) ----------

/** Same as candidate/manager._slug: « École Supérieure Fictive » -> « ecole-superieure-fictive ». */
export function slug(text: string): string {
  const ascii = text
    .replace(/\s/g, " ")
    .normalize("NFKD")
    .replace(/[^\x20-\x7e]/g, "")
    .toLowerCase();
  return (ascii.match(/[a-z0-9]+/g) ?? []).join("-");
}

/** Same as cv/render.format_dates: years only, « 2024–2025 », « 2026 ». */
export function formatDates(start?: string | null, end?: string | null): string {
  const s = String(start ?? "").slice(0, 4);
  const e = String(end ?? "").slice(0, 4);
  return s && e && s !== e ? `${s}–${e}` : s || e;
}

/** Same as cv/render.short_location: « Paris, France » -> « Paris ». */
export function shortLocation(location?: string | null): string {
  return String(location ?? "")
    .split(",")[0]!
    .trim();
}

/**
 * Same as cv/document.education_keys: the education id, or for entries without id the key
 * manager.assign_missing_ids() would give (slug of the school, made unique). The profile is not changed.
 */
export function educationKeys(profile: CandidateProfile): string[] {
  const existing = new Set(
    [...profile.experiences, ...profile.projects, ...profile.education]
      .map((item) => item.id)
      .filter((id): id is string => !!id),
  );
  return profile.education.map((item) => {
    if (item.id) return item.id;
    const base = slug(String(item.school ?? "")) || "formation";
    let key = base;
    for (let n = 2; existing.has(key); n++) key = `${base}-${n}`;
    existing.add(key);
    return key;
  });
}

const clean = (values?: string[]) => (values ?? []).map((v) => v.trim()).filter(Boolean);

/** Entries of the profile that can be added to the CV (same content as cv/document.entry_from_profile). */
export function profileEntries(section: ItemSection, profile: CandidateProfile) {
  if (section === "experiences")
    return profile.experiences.map((e): { label: string; detail: string; entry: CvExperience } => ({
      label: e.title,
      detail: [e.company, formatDates(e.start_date, e.end_date)].filter(Boolean).join(" · "),
      entry: {
        source_id: e.id,
        title: e.title ?? "",
        organization: e.company ?? "",
        context: null,
        location: shortLocation(e.location),
        dates: formatDates(e.start_date, e.end_date),
        bullets: clean(e.responsibilities),
      },
    }));
  if (section === "education") {
    const keys = educationKeys(profile);
    return profile.education.map((e, i): { label: string; detail: string; entry: CvEducation } => ({
      label: e.degree || e.school,
      detail: [e.school, formatDates(e.start_date, e.end_date)].filter(Boolean).join(" · "),
      entry: {
        source_id: keys[i]!,
        institution: e.school ?? "",
        location: shortLocation(e.location),
        dates: formatDates(e.start_date, e.end_date),
        bullets: clean(e.details),
      },
    }));
  }
  return profile.projects.map((p): { label: string; detail: string; entry: CvProject } => ({
    label: p.name,
    detail: formatDates(p.start_date, p.end_date),
    entry: {
      source_id: p.id,
      name: p.name ?? "",
      link: p.github_url?.trim() ? { url: p.github_url.trim(), label: "GitHub" } : null,
      bullets: clean(p.responsibilities),
    },
  }));
}

// ---------- Before saving ----------

/** Empty lines left in the editor are removed (cv.json does not accept empty bullets or items). */
export function cleanDocument(doc: CvDocument): CvDocument {
  const bullets = <T extends { bullets: string[] }>(entry: T): T => ({
    ...entry,
    bullets: clean(entry.bullets),
  });
  return {
    ...doc,
    header: {
      ...doc.header,
      contacts: doc.header.contacts
        .filter((c) => c.value.trim())
        .map((c) => ({ ...c, value: c.value.trim() })),
    },
    experiences: doc.experiences.map((e) => ({
      ...bullets(e),
      context: e.context?.trim() ? e.context : null,
    })),
    education: doc.education.map(bullets),
    projects: doc.projects.map((p) => ({
      ...bullets(p),
      link: p.link?.url.trim() ? p.link : null,
    })),
    skills: doc.skills
      .map((group) => ({ label: group.label, items: clean(group.items) }))
      // An empty group is not shown in the PDF and is refused by cv.json: it is simply dropped.
      .filter((group) => group.items.length),
    languages: doc.languages.filter((l) => l.name.trim() || l.level.trim()),
    interests: clean(doc.interests),
  };
}

// ---------- « Vue d'ensemble » (analysis.json) ----------
// Selection only: texts are shown as saved (never rewritten), the full lists stay reachable.

const STOP_WORDS = new Set(
  "avec pour dans leur leurs selon afin ainsi entre etre tous toute toutes plus vous nous votre notre cette ces sont from with that this your their into".split(
    " ",
  ),
);

/** Lower case, without accents, single spaces, « a/b » written « a / b ». */
function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/\s*\/\s*/g, " / ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Significant words of a text (lower case, without accents, at least four letters). */
function contentWords(text: string): Set<string> {
  const words = normalize(text).split(/[^\p{L}\p{N}]+/u);
  return new Set(words.filter((w) => w.length >= 4 && !STOP_WORDS.has(w)));
}

/** Share of the significant words of `a` that also appear in `b` (0 when `a` has none). */
function coveredBy(a: Set<string>, b: Set<string>): number {
  if (a.size === 0) return 0;
  return [...a].filter((w) => b.has(w)).length / a.size;
}

/**
 * The first `max` missions of the offer, skipping a mission whose significant words are mostly
 * (70 %) those of a mission already kept: the same step written twice is shown once. Nothing is merged
 * or reworded; « Voir toutes les missions » shows the complete list.
 */
export function mainMissions(missions: string[], max = 4): string[] {
  const kept: { text: string; words: Set<string> }[] = [];
  for (const text of missions.map((m) => m.trim()).filter(Boolean)) {
    const words = contentWords(text);
    if (kept.some((k) => k.text === text || coveredBy(words, k.words) >= 0.7)) continue;
    kept.push({ text, words });
    if (kept.length === max) break;
  }
  return kept.map((k) => k.text);
}

/**
 * Up to `max` example tasks (without their "Par exemple, tu pourrais…" opening) that do not repeat
 * a shown mission: a task whose significant words mostly (60 %) belong to one mission is skipped.
 */
export function exampleTasks(tasks: string[], missions: string[], max = 2): string[] {
  const missionWords = missions.map(contentWords);
  return tasks
    .map(taskText)
    .filter(Boolean)
    .filter((t) => {
      const words = contentWords(t);
      return !missionWords.some((m) => coveredBy(words, m) >= 0.6);
    })
    .slice(0, max);
}

// Personal qualities, not technical skills (the analysis does not assess them either).
const GENERAL_QUALITIES = new Set([
  "rigueur",
  "curiosite",
  "autonomie",
  "creativite",
  "adaptabilite",
  "organisation",
  "motivation",
  "dynamisme",
  "proactivite",
  "polyvalence",
  "perseverance",
  "ponctualite",
  "communication",
  "leadership",
  "travail en equipe",
  "rigor",
  "rigour",
  "curiosity",
  "autonomy",
  "creativity",
  "adaptability",
  "teamwork",
  "team player",
  "proactivity",
]);
const QUALITY_PREFIXES = ["esprit ", "sens ", "capacite ", "gout ", "envie ", "ability to "];

/** A real technical keyword: short (three words per « / » side), not a sentence, list or quality. */
function isKeyword(text: string): boolean {
  const key = normalize(text);
  return (
    text.length <= 40 &&
    key.split(" / ").every((side) => side.split(" ").length <= 3) &&
    !/[.;:!?]$|[,;]/.test(text) &&
    !GENERAL_QUALITIES.has(key) &&
    !QUALITY_PREFIXES.some((p) => key.startsWith(p))
  );
}

/**
 * Up to `max` technical keywords of the job (display only, analysis.json unchanged): technologies and
 * skills sought, without personal qualities, duplicates or a general term when a more precise one
 * contains it (« Deep Learning » inside « Machine Learning / Deep Learning »); two keywords the offer
 * gives as alternatives become one (« PyTorch ou TensorFlow »). Keywords of essential requirements
 * come first, then those of required ones.
 */
export function keySkills(analysis: CompletedAnalysis, max = 6): string[] {
  const { overview } = analysis;
  const requirements = visibleRequirements(analysis);
  const sources = [...requirements.map((r) => r.text), ...overview.skills_sought].map(normalize);

  const seen = new Set<string>();
  let keywords = [...overview.technologies, ...overview.skills_sought]
    .map((s) => s.trim())
    .filter((s) => {
      const key = normalize(s);
      if (!s || !isKeyword(s) || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  const words = (k: string) =>
    new Set(
      normalize(k)
        .split(/[^\p{L}\p{N}+#]+/u)
        .filter(Boolean),
    );
  keywords = keywords.filter((k) => {
    const own = words(k);
    return !keywords.some((other) => {
      const larger = words(other);
      return other !== k && larger.size > own.size && [...own].every((w) => larger.has(w));
    });
  });

  // « A ou B », « A or B », « A / B » in the offer: one keyword
  const merged: string[] = [];
  const absorbed = new Set<string>();
  for (const k of keywords) {
    if (absorbed.has(k)) continue;
    const partner = keywords.find(
      (other) =>
        other !== k &&
        !absorbed.has(other) &&
        [" ou ", " or ", " / "].some((link) =>
          sources.some(
            (text) =>
              text.includes(normalize(k) + link + normalize(other)) ||
              text.includes(normalize(other) + link + normalize(k)),
          ),
        ),
    );
    if (partner) absorbed.add(partner);
    merged.push(partner ? `${k} ou ${partner}` : k);
  }

  const rank = (k: string) => {
    const parts = k.split(" ou ").map(normalize);
    const inText = (r: Requirement) => parts.some((p) => normalize(r.text).includes(p));
    if (requirements.some((r) => r.category === "required" && r.importance === "high" && inText(r)))
      return 0;
    return requirements.some((r) => r.category === "required" && inText(r)) ? 1 : 2;
  };
  return merged
    .map((k, i) => ({ k, i, rank: rank(k) }))
    .sort((a, b) => a.rank - b.rank || a.i - b.i)
    .slice(0, max)
    .map((x) => x.k);
}

/**
 * « L'entreprise » and « Le poste en bref »: the first sentence of the company activity (empty when
 * unknown, never guessed, and dropped when it mostly repeats the job summary: it then describes the
 * job, not the company), then the first two summary sentences that do not repeat it.
 */
export function jobBrief(
  summary: string,
  activity: string | null | undefined,
): { company: string; job: string } {
  const summaryWords = contentWords(summary);
  const first = activity ? firstSentence(activity) : "";
  const company = coveredBy(contentWords(first), summaryWords) >= 0.5 ? "" : first;
  const companyWords = contentWords(company);
  const job = splitSentences(summary)
    .filter((s) => coveredBy(contentWords(s), companyWords) < 0.6)
    .slice(0, 2)
    .join(" ");
  return { company, job };
}

// Link words ignored when comparing two criteria (as cv/analysis.py does for new analyses).
const LINK_WORDS = new Set(
  "de du des la le les l d et en a au aux un une avec of the and for in at via with".split(" "),
);

/** Words of a text, in order (lower case, without accents or punctuation; « C++ », « C# » kept). */
function wordList(text: string): string[] {
  return normalize(text)
    .split(/[^\p{L}\p{N}+#]+/u)
    .filter(Boolean);
}

/** Same criterion: the same words in the same order, link words aside (« avec PyTorch » = « (PyTorch) »). */
function criterionKey(text: string): string {
  return wordList(text)
    .filter((w) => !LINK_WORDS.has(w))
    .join(" ");
}

/**
 * The requirements (and parts) to show, each once: without those the analysis marks as duplicates,
 * nor (older analyses) one that repeats an earlier one word for word. A required requirement is never
 * hidden behind a preferred one. Statuses are never changed.
 */
export function visibleRequirements(analysis: CompletedAnalysis): Requirement[] {
  const seen = new Map<string, Requirement>();
  return analysis.requirements.filter((r) => {
    if (r.duplicate_of) return false;
    const key = criterionKey(r.text);
    const earlier = seen.get(key);
    if (earlier && !(r.category === "required" && earlier.category === "preferred")) return false;
    if (key && !earlier) seen.set(key, r);
    return true;
  });
}

// ---------- Requirement lines (« Exigences détaillées ») ----------

/** « Obligatoires »: conditions and prerequisites; « Essentielles »: core skills; « Souhaitées ». */
export type RequirementGroup = "required" | "essential" | "preferred";

/** How the parts of a split requirement combine, as the offer states it; "unknown" when it does not. */
export type PartsRelation = "and" | "or" | "unknown";

export interface RequirementLine {
  /** The requirement id of the offer (the parent id of split parts). */
  id: string;
  /** The requirement as the offer writes it (the parent text of split parts). */
  text: string;
  group: RequirementGroup;
  /** The assessed criteria: one, or the parts of a split requirement (each with its own status). */
  parts: Requirement[];
  relation: PartsRelation | null;
  /** Overall status when it can be established reliably, otherwise null (the parts keep theirs). */
  status: RequirementStatus | null;
}

const STATUS_RANK: RequirementStatus[] = ["met", "partial", "not_documented", "missing"];
const GROUP_ORDER: RequirementGroup[] = ["required", "essential", "preferred"];

/**
 * A requirement of the offer stays « obligatoire » when it is a condition (education, experience,
 * languages) or a required skill of normal importance, even if it is also stressed; a required skill
 * the offer stresses (importance « high ») is « essentielle »; the others are « souhaitées ».
 */
function groupOf(parts: Requirement[]): RequirementGroup {
  const first = parts[0]!;
  if (first.category === "preferred") return "preferred";
  const skill = (first.source ?? "must_have") === "must_have";
  return skill && parts.some((p) => p.importance === "high") ? "essential" : "required";
}

/**
 * The link the offer writes just before the last part (« détection, tracking ou calibration »: or;
 * « Python et SQL »: and). A comma or anything else is not interpreted: "unknown".
 */
function relationOf(parentText: string, parts: Requirement[]): PartsRelation {
  const others = new Set(parts.slice(0, -1).flatMap((p) => wordList(p.text)));
  const first = wordList(parts[parts.length - 1]!.text).find((w) => !others.has(w));
  if (!first) return "unknown";
  const parent = normalize(parentText);
  const escaped = first.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`(^|[^\\p{L}\\p{N}])${escaped}(?![\\p{L}\\p{N}])`, "u").exec(parent);
  if (!match) return "unknown";
  const before = parent.slice(0, match.index + match[1]!.length);
  if (/(^|\s)(ou|or)\s*$/.test(before)) return "or";
  if (/(^|\s)(et|and|&)\s*$/.test(before)) return "and";
  return "unknown";
}

/**
 * Overall status of a split requirement, only when it is reliable: the same status for every part;
 * for alternatives (or), the best one (an undocumented alternative is not a gap when another is met);
 * for criteria that are all needed (and), « non remplie » when one is not met. Otherwise null.
 */
function overallStatus(
  parts: Requirement[],
  relation: PartsRelation | null,
): RequirementStatus | null {
  const ranks = parts.map((p) => STATUS_RANK.indexOf(p.status));
  if (new Set(ranks).size === 1) return parts[0]!.status;
  if (relation === "or") return STATUS_RANK[Math.min(...ranks)]!;
  if (relation === "and" && parts.some((p) => p.status === "missing")) return "missing";
  return null;
}

/**
 * The lines of « Exigences détaillées »: one per requirement of the offer (split parts gathered under
 * it, in their order), « Obligatoires » first, then « Essentielles », then « Souhaitées ». Display
 * only: analysis.json is not changed and no status is re-assessed.
 */
export function requirementLines(analysis: CompletedAnalysis): RequirementLine[] {
  const byId = new Map<string, Requirement[]>();
  for (const r of visibleRequirements(analysis)) {
    const key = r.parent_id || r.id;
    byId.set(key, [...(byId.get(key) ?? []), r]);
  }
  const lines = [...byId.entries()].map(([id, parts]): RequirementLine => {
    const split = parts.length > 1;
    const relation = split ? relationOf(parts[0]!.parent_text ?? "", parts) : null;
    return {
      id,
      text: split ? parts[0]!.parent_text || parts.map((p) => p.text).join(", ") : parts[0]!.text,
      group: groupOf(parts),
      parts,
      relation,
      status: overallStatus(parts, relation),
    };
  });
  return lines
    .map((line, i) => ({ line, i }))
    .sort(
      (a, b) => GROUP_ORDER.indexOf(a.line.group) - GROUP_ORDER.indexOf(b.line.group) || a.i - b.i,
    )
    .map(({ line }) => line);
}

/** The first sentence of a text (strengths, attention points): the rest stays in the detail. */
export function firstSentence(text: string): string {
  return leadSentences(text, 1).lead;
}

export interface AttentionPoint {
  id: string;
  text: string;
  /** The status is shown as is: "not met", "partially met" and "not documented" stay distinct. */
  status: Exclude<RequirementStatus, "met">;
  explanation: string;
}

/**
 * At most `max` attention points among the required requirements: not met (essential ones first),
 * then essential ones only partially met, then essential ones the profile does not document (an
 * uncertainty to clarify, not a certain weakness). A requirement with a reliable overall status counts
 * once (an alternative that is met settles it); otherwise its parts count one by one. Preferred
 * requirements stay in the detail.
 */
export function attentionPoints(analysis: CompletedAnalysis, max = 2): AttentionPoint[] {
  const explanation = (parts: Requirement[], status: RequirementStatus) => {
    const part = parts.find((p) => p.status === status) ?? parts[0]!;
    return (
      analysis.weaknesses.find((w) => w.requirement_id === part.id)?.explanation || part.explanation
    );
  };
  const candidates = requirementLines(analysis)
    .filter((line) => line.group !== "preferred")
    .flatMap((line) =>
      line.status
        ? [{ id: line.id, text: line.text, status: line.status, parts: line.parts }]
        : line.parts.map((p) => ({ id: p.id, text: p.text, status: p.status, parts: [p] })),
    )
    .map((c) => ({ ...c, essential: c.parts.some((p) => p.importance === "high") }));
  const ordered = [
    ...candidates.filter((c) => c.status === "missing" && c.essential),
    ...candidates.filter((c) => c.status === "missing" && !c.essential),
    ...candidates.filter((c) => c.status === "partial" && c.essential),
    ...candidates.filter((c) => c.status === "not_documented" && c.essential),
  ];
  return ordered.slice(0, max).map((c) => ({
    id: c.id,
    text: c.text,
    status: c.status as AttentionPoint["status"],
    explanation: firstSentence(explanation(c.parts, c.status)),
  }));
}

// ---------- « Vérifier » (onglet CV) ----------
// Is what the offer looks for visible in the CV? Local and deterministic: the terms of the offer are
// searched word for word in cv.json, and the profile elements the analysis cites as evidence are
// matched with the CV entries by their source_id. Nothing is re-assessed, nothing is written.

/** « Présent »: a precise term is in the CV; « À vérifier »: only an evidence entry is; else « Non mentionné ». */
export type CvCheckState = "present" | "uncertain" | "absent";

export interface CvLocation {
  selection: CvSelection;
  /** "Expérience · Stagiaire data", "Compétences · Langages"… */
  label: string;
}

export interface CvCheck {
  id: string;
  /** The requirement as the offer writes it. */
  text: string;
  state: CvCheckState;
  /** Terms of the offer (or cited profile elements) found in the CV, word for word. */
  terms: string[];
  /** Terms of the offer that were looked for and not found (criteria that are all needed). */
  missing: string[];
  /** Where in the CV: the entries holding the terms, or the evidence entries (state "uncertain"). */
  locations: CvLocation[];
}

// Conditions that a CV does not argue (status, diploma, duration, eligibility) and spoken languages
// (always listed in the CV): left out of the check, they stay in « Exigences détaillées ». Whole words
// only (« Large Language Models » is not a spoken language).
const NOT_ARGUED = [
  "convention",
  "etudiant",
  "etudiante",
  "derniere annee",
  "diplome",
  "diplomee",
  "bac+3",
  "bac+4",
  "bac+5",
  "permis",
  "nationalite",
  "titre de sejour",
  "visa",
  "autorisation de travail",
  "work permit",
  "eligible",
  "eligibilite",
  "eligibility",
  "disponible",
  "disponibilite",
  "duree",
  "mois",
  "months",
  "ans d'experience",
  "annees d'experience",
  "years of experience",
  "anglais",
  "anglophone",
  "francais",
  "francophone",
  "english",
  "french",
  "langue",
  "langues",
];

/** One searchable part of the CV, with where it is. */
interface CvPassage {
  location: CvLocation;
  text: string;
}

function cvPassages(doc: CvDocument): CvPassage[] {
  const join = (...parts: (string | null | undefined)[]) => parts.filter(Boolean).join(" \n ");
  return [
    {
      location: { selection: { section: "profile" }, label: "Profil · résumé" },
      text: doc.header.summary,
    },
    ...doc.experiences.map((e, index) => ({
      location: {
        selection: { section: "experiences" as const, index },
        label: `Expérience · ${[e.title, e.organization].filter(Boolean).join(" — ")}`,
      },
      text: join(e.title, e.organization, e.context, ...e.bullets),
    })),
    ...doc.projects.map((p, index) => ({
      location: { selection: { section: "projects" as const, index }, label: `Projet · ${p.name}` },
      text: join(p.name, ...p.bullets),
    })),
    ...doc.education.map((e, index) => ({
      location: {
        selection: { section: "education" as const, index },
        label: `Formation · ${e.institution}`,
      },
      text: join(e.institution, ...e.bullets),
    })),
    ...doc.skills.map((g) => ({
      location: { selection: { section: "skills" as const }, label: `Compétences · ${g.label}` },
      text: join(g.label, ...g.items),
    })),
    {
      location: { selection: { section: "languages" }, label: "Langues" },
      text: join(...doc.languages.map((l) => l.name)),
    },
    {
      location: { selection: { section: "interests" }, label: "Centres d'intérêt" },
      text: join(...doc.interests),
    },
  ];
}

/** Whole-word (or whole-phrase) presence of `term` in `text`, case and accents ignored. */
function mentions(text: string, term: string): boolean {
  const t = normalize(term);
  if (t.length < 2) return false;
  const escaped = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^\\p{L}\\p{N}+#])${escaped}($|[^\\p{L}\\p{N}+#])`, "u").test(
    normalize(text),
  );
}

function uniqueTerms(terms: string[]): string[] {
  const seen = new Set<string>();
  return terms.filter((t) => {
    const key = normalize(t);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * Terms to look for in the CV for one requirement: `named`, the technologies and skills of the offer
 * that the requirement names; `cited`, the skills / interests / languages of the profile that the
 * analysis cites as its evidence (« Intérêt pour le sport » → « Football »).
 */
function searchTerms(
  analysis: CompletedAnalysis,
  line: RequirementLine,
): { named: string[]; cited: string[] } {
  const vocabulary = [...analysis.overview.technologies, ...analysis.overview.skills_sought]
    .flatMap((s) => s.split(/\s+\/\s+/))
    .map((s) => s.trim())
    .filter((s) => s && isKeyword(s));
  const named = uniqueTerms(vocabulary.filter((term) => mentions(line.text, term)));
  const cited = uniqueTerms(
    line.parts
      .flatMap((p) => p.evidence)
      .filter((e) => e.type === "skill" || e.type === "interest" || e.type === "language")
      .map((e) => e.label),
  ).filter((t) => !named.some((n) => normalize(n) === normalize(t)));
  return { named, cited };
}

/** CV entries (by source_id) that the analysis cites as evidence for the requirement. */
function evidenceLocations(
  line: RequirementLine,
  doc: CvDocument,
  passages: CvPassage[],
): CvLocation[] {
  const sections = {
    experience: "experiences",
    project: "projects",
    education: "education",
  } as const;
  return line.parts
    .flatMap((p) => p.evidence)
    .flatMap((e) => {
      const section = sections[e.type as keyof typeof sections];
      if (!section) return [];
      const index = doc[section].findIndex((entry) => entry.source_id === e.id);
      if (index < 0) return [];
      const passage = passages.find(
        (p) => p.location.selection.section === section && p.location.selection.index === index,
      );
      return passage ? [passage.location] : [];
    });
}

const SECTION_RANK: CvSectionKey[] = [
  "experiences",
  "projects",
  "profile",
  "education",
  "skills",
  "languages",
  "interests",
];

function uniqueLocations(locations: CvLocation[]): CvLocation[] {
  const seen = new Set<string>();
  return locations
    .filter((l) => {
      const key = `${l.selection.section}/${l.selection.index ?? ""}/${l.label}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort(
      (a, b) =>
        SECTION_RANK.indexOf(a.selection.section) - SECTION_RANK.indexOf(b.selection.section),
    );
}

const CHECK_ORDER: RequirementGroup[] = ["essential", "required", "preferred"];

/**
 * The named terms of a requirement, grouped as the offer writes them: terms enumerated one after the
 * other (« a, b ou c », « a / b ») are alternatives when the last link is « ou », « or » or « / »;
 * any other term stands alone (all needed). Only explicit links are read: nothing is guessed.
 */
function termGroups(text: string, named: string[]): string[][] {
  const t = normalize(text);
  const placed = named
    .map((term) => ({ term, at: t.indexOf(normalize(term)), length: normalize(term).length }))
    .filter((p) => p.at >= 0)
    .sort((a, b) => a.at - b.at);
  const groups: string[][] = [];
  let chain: typeof placed = [];
  let alternative = false;
  const close = () => {
    if (alternative) groups.push(chain.map((p) => p.term));
    else groups.push(...chain.map((p) => [p.term]));
    chain = [];
    alternative = false;
  };
  for (const p of placed) {
    const last = chain[chain.length - 1];
    const link = last ? t.slice(last.at + last.length, p.at) : null;
    if (last && link !== null && /^(\s*,\s*|\s+(ou|or)\s+|\s*\/\s*)$/.test(link)) {
      alternative = /^\s+(ou|or)\s+$|^\s*\/\s*$/.test(link);
      chain.push(p);
    } else {
      if (chain.length) close();
      chain = [p];
    }
  }
  if (chain.length) close();
  return groups;
}

/**
 * Up to `max` requirements of the offer worth arguing in the CV, essential ones first: only those the
 * profile documents (met or partially met), so that « Non mentionné » always means « your profile
 * shows it, your CV does not », never « you lack it ». Conditions and spoken languages are left out.
 *
 * « Présent »: the terms of the offer are in the CV (one is enough for alternatives written with
 * « ou »), or — when the offer names no precise term — a profile element cited as evidence is.
 * « À vérifier »: only some of the terms, only a cited element in other words, or only an entry the
 * analysis cites. « Non mentionné »: none of these.
 */
export function cvChecks(analysis: CompletedAnalysis, doc: CvDocument, max = 6): CvCheck[] {
  const passages = cvPassages(doc);
  const where = (terms: string[]) =>
    uniqueLocations(
      passages.filter((p) => terms.some((t) => mentions(p.text, t))).map((p) => p.location),
    );
  return requirementLines(analysis)
    .filter((line) => line.parts.some((p) => p.status === "met" || p.status === "partial"))
    .filter((line) => {
      const sources = new Set(line.parts.map((p) => p.source));
      return (
        !NOT_ARGUED.some((w) => mentions(line.text, w)) &&
        !["education", "experience", "languages"].some((s) => sources.has(s))
      );
    })
    .map((line, i) => ({ line, i }))
    .sort(
      (a, b) => CHECK_ORDER.indexOf(a.line.group) - CHECK_ORDER.indexOf(b.line.group) || a.i - b.i,
    )
    .slice(0, max)
    .map(({ line }): CvCheck => {
      const { named, cited } = searchTerms(analysis, line);
      const inCv = (t: string) => passages.some((p) => mentions(p.text, t));
      const foundNamed = named.filter(inCv);
      const foundCited = cited.filter(inCv);
      const base = { id: line.id, text: line.text };
      if (foundNamed.length > 0) {
        // Split parts given as alternatives: one is enough; otherwise each group of terms needs one
        const unmet =
          line.relation === "or"
            ? []
            : termGroups(line.text, named).filter((group) => !group.some(inCv));
        return {
          ...base,
          state: unmet.length === 0 ? "present" : "uncertain",
          terms: foundNamed,
          missing: unmet.map((group) => group.join(" ou ")),
          locations: where(foundNamed),
        };
      }
      if (foundCited.length > 0)
        return {
          ...base,
          state: named.length === 0 ? "present" : "uncertain",
          terms: foundCited,
          missing: named,
          locations: where(foundCited),
        };
      const cv = uniqueLocations(evidenceLocations(line, doc, passages));
      return {
        ...base,
        state: cv.length > 0 ? "uncertain" : "absent",
        terms: [],
        missing: named,
        locations: cv,
      };
    });
}
