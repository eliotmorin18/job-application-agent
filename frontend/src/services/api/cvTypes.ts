// Data contract of "Mes CV", mirroring the FastAPI backend exactly (api/cvs.py, cv/document.py,
// cv/analysis.py, cv/layout.py). Keys are snake_case on purpose. Never edit these shapes to fit the UI:
// UI-only shapes (clickable zones, selection) are derived from them in features/cvs/adapters.ts.

import type { Language } from "./types";

// ---------- GET /api/cvs ----------

export type AnalysisStatus = "completed" | "failed" | "missing" | "running";

/** One saved application (a folder of cv/applications/). */
export interface CvSummary {
  id: string;
  company: string | null;
  role: string | null;
  job_title: string | null;
  language: string | null;
  source_url: string | null;
  /** false for CVs created before cv.json: PDF only, not editable. */
  editable: boolean;
  has_pdf: boolean;
  has_layout: boolean;
  pages: number | null;
  fits_one_page: boolean | null;
  verification_issues: number;
  analysis_status: AnalysisStatus;
  fit_score: number | null;
  fit_level: string | null;
  /** Generation date (Unix seconds, UTC); null for an old CV whose real creation date is unknown. */
  created_at: number | null;
  /** Last saved edit (Unix seconds, UTC); also versions the PDF URL. */
  updated_at: number;
}

// ---------- cv.json (cv/document.py, schema_version 1) ----------

export type ContactType = "email" | "phone" | "linkedin" | "github";

export interface CvExperience {
  source_id: string;
  title: string;
  organization: string;
  context: string | null;
  location: string;
  dates: string;
  bullets: string[];
}

export interface CvEducation {
  source_id: string;
  institution: string;
  location: string;
  dates: string;
  bullets: string[];
}

export interface CvProject {
  source_id: string;
  name: string;
  link: { url: string; label: string } | null;
  bullets: string[];
}

export interface CvSkillGroup {
  label: string;
  items: string[];
}

export interface CvLanguage {
  name: string;
  level: string;
}

export interface CvDocument {
  schema_version: number;
  language: "fr" | "en";
  company: string;
  role: string;
  header: { name: string; contacts: { type: ContactType; value: string }[]; summary: string };
  experiences: CvExperience[];
  education: CvEducation[];
  projects: CvProject[];
  skills: CvSkillGroup[];
  languages: CvLanguage[];
  interests: string[];
  gaps: string[];
}

export interface VerificationIssue {
  section: string;
  cv_text: string;
  problem: string;
}

/** GET /api/cvs/{cv_id} */
export interface CvDetail {
  cv: CvSummary;
  document: CvDocument;
  verification_issues: VerificationIssue[];
}

/** PUT /api/cvs/{cv_id} */
export interface CvUpdateResult {
  cv: CvSummary;
  document: CvDocument;
  pages: number;
  fits_one_page: boolean;
  has_layout: boolean;
}

// ---------- analysis.json (cv/analysis.py) ----------

export type RequirementStatus = "met" | "partial" | "not_documented" | "missing";

export interface Evidence {
  type: "experience" | "project" | "education" | "skill" | "language";
  id: string;
  label: string;
  justification: string;
}

export interface Requirement {
  id: string;
  text: string;
  category: "required" | "preferred";
  source: string;
  parent_id: string | null;
  parent_text: string | null;
  duplicate_of: string | null;
  importance: "high" | "normal";
  weight: number;
  status: RequirementStatus;
  explanation: string;
  evidence: Evidence[];
}

export type RecommendationCategory = "cv" | "interview" | "learning" | "obstacle";

export interface CompletedAnalysis {
  schema_version: number;
  status: "completed";
  generated_at: string;
  profile_fingerprint: string;
  offer: {
    company: string | null;
    job_title: string | null;
    location: string | null;
    contract_type: string | null;
    source_url: string | null;
  };
  overview: {
    summary: string;
    missions: string[];
    technologies: string[];
    skills_sought: string[];
    plain_explanation: string;
    possible_tasks: string[];
    glossary: { term: string; explanation: string }[];
  };
  requirements: Requirement[];
  strengths: {
    title: string;
    explanation: string;
    evidence: Evidence[];
    requirement_ids: string[];
  }[];
  weaknesses: {
    requirement_id: string;
    text: string;
    category: "required" | "preferred";
    kind: "missing" | "not_documented" | "partial";
    explanation: string;
  }[];
  /** Computed in Python. Not displayed in the interface (product choice). */
  score: { value: number | null; level: string | null; [key: string]: unknown };
  recommendations: { category: RecommendationCategory; text: string; requirement_ids: string[] }[];
  /** Absent from analyses saved before the interview questions: never regenerated automatically. */
  interview_questions?: InterviewQuestion[];
  warnings: string[];
}

export type InterviewQuestionKind = "technical" | "experience" | "gap" | "motivation";

/** A question a recruiter could ask (a possibility to prepare, not a prediction). */
export interface InterviewQuestion {
  kind: InterviewQuestionKind;
  question: string;
  purpose: string;
  answer_guidance: string[];
  /** Profile elements to mention, checked against the profile by the backend. */
  evidence: Evidence[];
  topics_to_review: string[];
  requirement_ids: string[];
}

export interface FailedAnalysis {
  schema_version: number;
  status: "failed";
  generated_at: string;
  error: { message: string; problems: string[] };
}

/** GET /api/cvs/{cv_id}/analysis (`running`: an analysis task is in progress for this CV). */
export type CvAnalysis = (CompletedAnalysis | FailedAnalysis) & { running: boolean };

// ---------- layout.json (cv/layout.py) ----------

export interface LayoutRegion {
  /** "profile", "experiences", "experiences/0", "skills"… */
  key: string;
  level: "section" | "item";
  json: (string | number)[];
  page: number; // 1-based
  top: number; // normalized 0-1, origin top-left
  bottom: number;
  left: number;
  right: number;
}

export interface CvLayout {
  version: number;
  pages: number;
  pdf?: string;
  page_size_pt: { width: number; height: number };
  regions: LayoutRegion[];
}

// ---------- Tasks (GET /api/cvs/tasks/{task_id}) ----------

export type TaskStatus = "pending" | "running" | "completed" | "failed";

export interface CvTask {
  task_id: string;
  kind: "generation" | "analysis";
  status: TaskStatus;
  /** Current step of cv/pipeline.py (read_offer, analyze_offer, write_cv, verify_cv, correct_cv, verified, compile, analyze_fit, done). */
  step: string;
  step_label: string;
  url: string | null;
  cv_id: string | null;
  error: { message: string; problems: string[] } | null;
  result: Record<string, unknown> | null;
  created_at: number;
  updated_at: number;
}

/** Every "Mes CV" call goes through this contract (implemented with HTTP in cvApi.ts). */
export interface CvApi {
  listCvs(): Promise<CvSummary[]>;
  /** Rejects with ApiError 409 for CVs created before cv.json. */
  getCv(id: string): Promise<CvDetail>;
  /** null when the CV has no analysis yet (404). */
  getAnalysis(id: string): Promise<CvAnalysis | null>;
  /** null when the CV has no clickable zones (404: created before the markers). */
  getLayout(id: string): Promise<CvLayout | null>;
  /** URL of the PDF; `version` changes after each recompilation (no stale PDF). */
  pdfUrl(id: string, version?: number): string;
  updateCv(id: string, document: CvDocument): Promise<CvUpdateResult>;
  deleteCv(id: string): Promise<void>;
  startGeneration(url: string): Promise<{ task_id: string }>;
  startAnalysis(id: string): Promise<{ task_id: string }>;
  getTask(taskId: string): Promise<CvTask>;
}

export type { Language };
