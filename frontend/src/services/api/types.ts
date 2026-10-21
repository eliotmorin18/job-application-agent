// Data contract shared with the Python backend. Keys are snake_case on purpose.

export type Priority = "high" | "medium" | "low";

export interface Personal {
  first_name?: string | undefined;
  last_name?: string | undefined;
  email?: string | undefined;
  phone?: string | undefined;
  city?: string | undefined;
  country?: string | undefined;
  address?: string | undefined;
  postal_code?: string | undefined;
  linkedin?: string | undefined;
  github?: string | undefined;
  birth_date?: string | undefined;
  nationality?: string | undefined;
  gender?: string | undefined;
}

export interface Career {
  academic_status?: string | undefined;
  employment_status?: string | undefined;
  graduation_date?: string | undefined;
}

export interface Education {
  id?: string | undefined;
  school: string;
  degree?: string | undefined;
  specialization?: string | undefined;
  start_date?: string | undefined;
  end_date?: string | undefined;
  location?: string | undefined;
  details?: string[] | undefined;
}

export interface Experience {
  id: string;
  company: string;
  title: string;
  start_date?: string | undefined;
  end_date?: string | undefined;
  location?: string | undefined;
  context?: string | undefined;
  description?: string | undefined;
  responsibilities?: string[] | undefined;
  achievements?: string[] | undefined;
  skills?: string[] | undefined;
  priority?: Priority | undefined;
  tags?: string[] | undefined;
}

export interface Project {
  id: string;
  name: string;
  start_date?: string | undefined;
  end_date?: string | undefined;
  context?: string | undefined;
  description?: string | undefined;
  responsibilities?: string[] | undefined;
  achievements?: string[] | undefined;
  skills?: string[] | undefined;
  github_url?: string | undefined;
  priority?: Priority | undefined;
  tags?: string[] | undefined;
}

export interface Language {
  language: string;
  level: string;
}

export interface Preferences {
  target_roles?: string[] | undefined;
  preferred_locations?: string[] | undefined;
  employment_types?: string[] | undefined;
}

export interface CandidateProfile {
  personal: Personal;
  career: Career;
  education: Education[];
  experiences: Experience[];
  projects: Project[];
  skills: Record<string, string[]>;
  languages: Language[];
  interests: string[];
  preferences: Preferences;
}

export type ItemSection = "experiences" | "education" | "projects";

export interface SectionItemMap {
  experiences: Experience;
  education: Education;
  projects: Project;
}

export type SectionItem = SectionItemMap[ItemSection];
export type PreferenceCategory = keyof Preferences;

/** Contract implemented by the mock today and by an HTTP client (FastAPI) later. */
export interface CandidateApi {
  getProfile(): Promise<CandidateProfile>;

  addItem<S extends ItemSection>(
    section: S,
    data: Omit<SectionItemMap[S], "id">,
  ): Promise<SectionItemMap[S]>;
  updateItem<S extends ItemSection>(
    section: S,
    id: string,
    changes: Partial<SectionItemMap[S]>,
  ): Promise<SectionItemMap[S]>;
  deleteItem(section: ItemSection, id: string): Promise<void>;

  updatePersonal(changes: Partial<Personal>): Promise<Personal>;
  updateCareer(changes: Partial<Career>): Promise<Career>;
  updatePreferences(changes: Partial<Preferences>): Promise<Preferences>;
  addPreference(category: PreferenceCategory, value: string): Promise<Preferences>;

  /** createCategory: create the category if it does not exist yet (otherwise refused). */
  addSkill(category: string, skill: string, createCategory?: boolean): Promise<void>;
  renameSkill(category: string, skill: string, newName: string): Promise<void>;
  deleteSkill(category: string, skill: string): Promise<void>;

  addLanguage(language: string, level: string): Promise<void>;
  updateLanguageLevel(language: string, level: string): Promise<void>;
  deleteLanguage(language: string): Promise<void>;

  addInterest(interest: string): Promise<void>;
  renameInterest(interest: string, newName: string): Promise<void>;
  deleteInterest(interest: string): Promise<void>;
}

/**
 * Stable key for a list item. Some legacy education entries have no id:
 * they are addressed by their position ("index-2") instead.
 */
export function getItemKey(item: { id?: string | undefined }, index: number): string {
  return item.id ?? `index-${index}`;
}

// ---------- CV import (mirror of candidate/review_import.py and candidate/apply_import.py) ----------

export type ProposalStatus = "new" | "duplicate" | "probable_duplicate" | "possible_duplicate";

export interface FieldDifference {
  extracted: unknown;
  current: unknown;
  change: "missing_in_profile" | "different" | "new_values";
  new_values?: string[] | undefined;
}

export interface ItemMatch {
  id: string | null;
  position: number;
  level: "probable_duplicate" | "possible_duplicate";
  score: number;
  reasons: string[];
  existing: Record<string, unknown>;
  differences: Record<string, FieldDifference>;
}

export interface ItemProposal {
  proposal_id: string;
  status: ProposalStatus;
  data: Record<string, string | string[]>;
  uncertain_fields: string[];
  matches: ItemMatch[];
}

export interface PersonalReview {
  field: string;
  extracted: string;
  current: string | null;
  status: "same" | "different" | "missing_in_profile";
  uncertain: boolean;
}

export interface SkillProposal {
  proposal_id: string;
  category: string;
  skill: string;
  category_in_profile: string | null;
  status: ProposalStatus;
  matches: { category: string; skill: string }[];
  note?: string | undefined;
}

export interface LanguageProposal {
  proposal_id: string;
  language: string;
  level: string | null;
  status: ProposalStatus;
  matches: Language[];
  note?: string | undefined;
  level_differs?: boolean | undefined;
}

export interface InterestProposal {
  proposal_id: string;
  interest: string;
  status: ProposalStatus;
  matches: string[];
}

export interface ImportReview {
  import_id: string;
  source: { source_pdf: string | null; extracted_at: string | null };
  warnings: string[];
  personal: PersonalReview[];
  experiences: ItemProposal[];
  projects: ItemProposal[];
  education: ItemProposal[];
  skills: SkillProposal[];
  languages: LanguageProposal[];
  interests: InterestProposal[];
  summary: Partial<Record<ProposalStatus, number>>;
}

export interface ImportSummary {
  import_id: string;
  source_pdf: string | null;
  extracted_at: string | null;
}

// Decisions: exactly the options accepted by apply_import.py (OPTIONS). Anything else is refused.
// `overrides`: values corrected by the user, replacing the extracted ones (only sent when there are some).
export type Overrides = Record<string, string | string[]>;
export type SkipDecision = { action: "skip" };
export type ItemDecision =
  | SkipDecision
  | { action: "add"; fields?: string[]; allow_duplicate?: boolean; overrides?: Overrides }
  | {
      action: "update";
      fields: string[];
      target_id?: string;
      target_position?: number;
      clear?: string[];
      allow_less_precise?: boolean;
      overrides?: Overrides;
    };
export type SkillDecision =
  | SkipDecision
  | {
      action: "add";
      category?: string;
      create_category?: boolean;
      allow_duplicate?: boolean;
      overrides?: { skill: string };
    };
export type LanguageDecision =
  | SkipDecision
  | { action: "add"; level?: string; allow_duplicate?: boolean; overrides?: { language: string } }
  | { action: "update"; level?: string };
export type InterestDecision =
  | SkipDecision
  | { action: "add"; allow_duplicate?: boolean; overrides?: { interest: string } }
  | { action: "update"; target: string; overrides?: { interest: string } };
export type PersonalDecision =
  | SkipDecision
  | { action: "update"; fields: string[]; allow_less_precise?: boolean; overrides?: Overrides };

export type ImportDecisions = Record<
  string,
  ItemDecision | SkillDecision | LanguageDecision | InterestDecision | PersonalDecision
>;

export interface ApplyReportEntry {
  proposal_id: string;
  section: string;
  id?: string | null | undefined;
  value?: string | undefined;
  new_value?: string | undefined;
  category?: string | undefined;
  level?: string | undefined;
  fields?: string[] | undefined;
  corrected?: string[] | undefined;
  reason?: string | undefined;
}

export interface ApplyReport {
  added: ApplyReportEntry[];
  updated: ApplyReportEntry[];
  skipped: ApplyReportEntry[];
}

/** CV import: the backend extracts (Claude), compares and saves. The frontend only shows and decides. */
export interface ImportApi {
  listImports(): Promise<ImportSummary[]>;
  importCv(file: File): Promise<ImportReview>;
  getReview(importId: string): Promise<ImportReview>;
  applyImport(importId: string, decisions: ImportDecisions): Promise<ApplyReport>;
}
