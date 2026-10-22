// Adapters between the backend contract (services/api/cvTypes.ts) and the "Mes CV" components.
// No data is invented here: everything is derived from what FastAPI returns or from the candidate profile.

import type { CandidateProfile } from "@/services/api/types";
import type {
  CvDocument,
  CvEducation,
  CvExperience,
  CvLayout,
  CvProject,
  CvTask,
} from "@/services/api/cvTypes";

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
