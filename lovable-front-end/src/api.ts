/**
 * Client API unique — tous les appels vers l'agent local + mode démo.
 * URL de base : VITE_API_URL (défaut http://localhost:8000).
 */

// ---------- Types ----------
export type AppStatus =
  | "running"
  | "action_required"
  | "questions"
  | "ready"
  | "error"
  | "submitted"
  | "abandoned";

export type StepStatus = "pending" | "running" | "done" | "action_required" | "error";

export interface Step {
  key: string;
  label: string;
  status: StepStatus;
  detail: string | null;
}

export interface KeyPoint {
  point: string;
  quote: string;
}

export interface Offer {
  company: string | null;
  job_title: string | null;
  location: string | null;
  contract_type: string | null;
  job_level: string | null;
  summary: string | null;
  key_points: KeyPoint[];
  must_have: string[];
  nice_to_have: string[];
  practical_info: string[];
}

export interface Question {
  number: number;
  field: string;
  kind: "text" | "choice" | "checkbox" | "other";
  options: string[];
  reason: string;
  answered: boolean;
}

export interface ChatMessage {
  role: "agent" | "user";
  text: string;
  time: string;
}

export interface Application {
  id: string;
  url: string;
  status: AppStatus;
  message: string | null;
  steps: Step[];
  offer: Offer | null;
  questions: Question[];
  chat: ChatMessage[];
  cv: null | { pdf_ready: boolean; verification_issues: string[] };
  strengths: string[];
  gaps: string[];
  answers_filled: { field: string; value: string }[];
  manual: { field: string; reason: string }[];
}

// ---------- Mode démo (store) ----------
// Jamais mémorisé : à chaque ouverture, on repart en mode réel.
let demoMode = false;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function isDemoMode() {
  return demoMode;
}
export function setDemoMode(on: boolean) {
  demoMode = on;
  emit();
}
export function subscribeDemoMode(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

// ---------- Joignabilité de l'agent local ----------
let reachable = true;
export function isReachable() {
  return reachable;
}
function setReachable(v: boolean) {
  if (reachable !== v) {
    reachable = v;
    emit();
  }
}

// ---------- HTTP ----------
export const API_URL: string =
  (import.meta.env["VITE_API_URL"] as string | undefined) ?? "http://127.0.0.1:8000";

export class NetworkError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T | null> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new NetworkError("L'agent local ne répond pas.");
  }
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Erreur ${res.status}`);
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : null;
}

/** Appel réel (ou simulation si le mode démo est activé manuellement). */
async function call<T>(real: () => Promise<T>, demo: () => T): Promise<T> {
  if (demoMode) return demo();
  try {
    const r = await real();
    setReachable(true);
    return r;
  } catch (e) {
    if (e instanceof NetworkError) setReachable(false);
    throw e;
  }
}

/** Message d'erreur court, lisible. */
export function errorMessage(e: unknown): string {
  if (e instanceof NetworkError) return "L'agent local ne répond pas.";
  if (e instanceof Error && e.message) return e.message;
  return "Quelque chose s'est mal passé.";
}

const post = (path: string, body?: unknown) =>
  request<unknown>(path, body ? { method: "POST", body: JSON.stringify(body) } : { method: "POST" });

export const api = {
  createApplication: (url: string) =>
    call(
      async () => (await request<{ id: string }>("/api/applications", {
        method: "POST",
        body: JSON.stringify({ url }),
      }))!,
      () => demo.create(url),
    ),
  getCurrent: () =>
    call(() => request<Application>("/api/applications/current"), () => demo.get()),
  continue: () => call(() => post("/api/applications/current/continue"), () => demo.continue()),
  retry: () => call(() => post("/api/applications/current/retry"), () => demo.retry()),
  sendAnswers: (text: string) =>
    call(() => post("/api/applications/current/answers", { text }), () => demo.answers(text)),
  focusChrome: () => call(() => post("/api/applications/current/focus-chrome"), () => null),
  markSubmitted: () =>
    call(() => post("/api/applications/current/submitted"), () => demo.setStatus("submitted")),
  abandon: () =>
    call(() => post("/api/applications/current/abandon"), () => demo.setStatus("abandoned")),
  cvUrl: () => (demoMode ? demo.pdfUrl() : `${API_URL}/api/applications/current/cv.pdf`),
};

// ---------- Simulation démo ----------
const STEP_LABELS: [string, string][] = [
  ["read_offer", "Lecture de l'offre"],
  ["analyze_offer", "Analyse de l'offre"],
  ["write_cv", "Rédaction du CV"],
  ["verify_cv", "Vérification du CV"],
  ["pdf", "Génération du PDF"],
  ["fill_form", "Remplissage du formulaire"],
  ["your_answers", "Tes réponses"],
  ["fill_answers", "Remplissage de tes réponses"],
  ["ready", "Prêt à envoyer"],
];
const STEP_DETAILS: Record<string, string> = {
  read_offer: "Page de l'offre chargée, 1 240 mots extraits.",
  analyze_offer: "Airbus — Stage IA, optimisation de la production.",
  write_cv: "CV adapté : 3 expériences mises en avant.",
  verify_cv: "Relecture terminée, 1 point à vérifier.",
  pdf: "CV exporté en PDF (1 page).",
  fill_form: "12 champs remplis sur 15.",
  your_answers: "Réponses intégrées.",
  fill_answers: "3 champs complétés.",
  ready: "Tout est prêt, il ne reste qu'à envoyer.",
};

const DEMO_OFFER: Offer = {
  company: "Airbus",
  job_title: "Stage IA – Optimisation de la production",
  location: "Toulouse (Blagnac)",
  contract_type: "Stage — 6 mois",
  job_level: "Bac+5",
  summary:
    "Au sein de l'équipe Digital Manufacturing, tu développes des modèles de machine learning pour anticiper les goulots d'étranglement sur les lignes d'assemblage A320 et proposer des plannings optimisés.",
  key_points: [
    { point: "Données réelles de production", quote: "Accès aux données capteurs des lignes FAL A320." },
    { point: "Mise en production attendue", quote: "Le modèle sera déployé auprès des chefs d'équipe." },
    { point: "Équipe pluridisciplinaire", quote: "Data scientists, ingénieurs méthodes et opérateurs." },
  ],
  must_have: ["Python", "Machine learning (scikit-learn, PyTorch)", "SQL", "Anglais professionnel"],
  nice_to_have: ["Recherche opérationnelle", "Docker", "Expérience industrielle"],
  practical_info: [
    "Début : février 2027",
    "Gratification : 1 400 € brut / mois",
    "Télétravail : 1 jour par semaine",
    "Restaurant d'entreprise sur site",
  ],
};

const DEMO_QUESTIONS: Question[] = [
  {
    number: 1,
    field: "Date de disponibilité",
    kind: "text",
    options: [],
    reason: "Je ne trouve pas cette information dans ton profil.",
    answered: false,
  },
  {
    number: 2,
    field: "Comment as-tu connu cette offre ?",
    kind: "choice",
    options: ["LinkedIn", "Site Airbus", "École", "Salon", "Autre"],
    reason: "Question personnelle, je préfère te demander.",
    answered: false,
  },
  {
    number: 3,
    field: "Pourquoi Airbus ? (500 caractères max)",
    kind: "text",
    options: [],
    reason: "Je peux proposer un texte, mais ta motivation doit venir de toi.",
    answered: false,
  },
];

interface DemoState {
  url: string;
  created: number;
  phase: "steps" | "action" | "after_action" | "questions" | "reading1" | "followup" | "reading2" | "finishing" | "ready";
  phaseStart: number;
  finalStatus: "submitted" | "abandoned" | null;
  chat: ChatMessage[];
  answered: boolean[];
}

const STEP_MS = 2400;
const STORE = "candidature-demo-state";
const now = () => Date.now();
const hhmm = () => new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

function load(): DemoState | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORE);
  return raw ? (JSON.parse(raw) as DemoState) : null;
}
function save(s: DemoState | null) {
  if (s) window.localStorage.setItem(STORE, JSON.stringify(s));
  else window.localStorage.removeItem(STORE);
}

function advance(s: DemoState): DemoState {
  const t = now() - s.phaseStart;
  if (s.phase === "steps" && t > STEP_MS * 5.5) {
    s.phase = "action";
    s.phaseStart = now();
  } else if (s.phase === "after_action" && t > STEP_MS) {
    s.phase = "questions";
    s.phaseStart = now();
    s.chat.push({
      role: "agent",
      text: "J'ai rempli presque tout le formulaire. Il me manque 3 réponses que toi seul peux donner. Tu peux tout écrire d'un coup, en vrac, je trierai.",
      time: hhmm(),
    });
  } else if (s.phase === "reading1" && t > 3000) {
    s.phase = "followup";
    s.phaseStart = now();
    s.answered = [true, true, false];
    s.chat.push({
      role: "agent",
      text: "Merci, c'est noté pour la disponibilité et la source. Pour « Pourquoi Airbus ? », tu veux que je parte de ton projet de fin d'études sur la maintenance prédictive, ou tu as une autre raison en tête ?",
      time: hhmm(),
    });
  } else if (s.phase === "reading2" && t > 3000) {
    s.phase = "finishing";
    s.phaseStart = now();
    s.answered = [true, true, true];
    s.chat.push({
      role: "agent",
      text: "Parfait, j'ai rédigé un texte de 470 caractères à partir de ça. Je remplis les derniers champs.",
      time: hhmm(),
    });
  } else if (s.phase === "finishing" && t > STEP_MS * 1.6) {
    s.phase = "ready";
    s.phaseStart = now();
  }
  return s;
}

function buildSteps(s: DemoState): Step[] {
  const t = now() - s.phaseStart;
  return STEP_LABELS.map(([key, label], i) => {
    let status: StepStatus = "pending";
    let detail: string | null = null;
    const done = () => {
      status = "done";
      detail = STEP_DETAILS[key] ?? null;
    };
    switch (s.phase) {
      case "steps": {
        const cur = Math.floor(t / STEP_MS);
        if (i < cur) done();
        else if (i === cur) status = "running";
        break;
      }
      case "action":
        if (i < 5) done();
        else if (i === 5) {
          status = "action_required";
          detail = "Crée un compte sur le portail Airbus Careers dans l'onglet Chrome ouvert, puis clique sur « C'est fait ».";
        }
        break;
      case "after_action":
        if (i < 5) done();
        else if (i === 5) status = "running";
        break;
      case "questions":
      case "reading1":
      case "followup":
      case "reading2":
        if (i < 6) done();
        else if (i === 6) {
          status = "running";
          detail = "En attente de tes réponses.";
        }
        break;
      case "finishing":
        if (i < 7) done();
        else if (i === 7) status = "running";
        break;
      case "ready":
        done();
        break;
    }
    return { key, label, status, detail };
  });
}

function toApplication(s: DemoState): Application {
  const steps = buildSteps(s);
  const offerKnown = steps[1]?.status === "done";
  const ready = s.phase === "ready";
  const statusMap: Record<DemoState["phase"], AppStatus> = {
    steps: "running",
    action: "action_required",
    after_action: "running",
    questions: "questions",
    reading1: "questions",
    followup: "questions",
    reading2: "questions",
    finishing: "running",
    ready: "ready",
  };
  const inQuestions = ["questions", "reading1", "followup", "reading2", "finishing", "ready"].includes(s.phase);
  return {
    id: "demo-1",
    url: s.url,
    status: s.finalStatus ?? statusMap[s.phase],
    message: s.phase === "action" ? "Action requise : crée ton compte candidat." : null,
    steps,
    offer: offerKnown ? DEMO_OFFER : null,
    questions: inQuestions ? DEMO_QUESTIONS.map((q, i) => ({ ...q, answered: !!s.answered[i] })) : [],
    chat: s.chat,
    cv: steps[4]?.status === "done"
      ? { pdf_ready: true, verification_issues: ["La date de fin de ton stage chez Thales (août 2025) n'apparaît pas sur LinkedIn : vérifie qu'elle est juste."] }
      : null,
    strengths: ready
      ? [
          "Projet de fin d'études en maintenance prédictive, très proche du sujet",
          "Python et PyTorch utilisés en stage chez Thales",
          "Anglais C1 (TOEIC 945)",
        ]
      : [],
    gaps: ready
      ? ["Pas d'expérience en recherche opérationnelle", "Docker seulement vu en cours"]
      : [],
    answers_filled: ready
      ? [
          { field: "Nom", value: "Camille Martin" },
          { field: "École", value: "INSA Toulouse — Génie mathématique" },
          { field: "Date de disponibilité", value: "2 février 2027" },
          { field: "Comment as-tu connu cette offre ?", value: "LinkedIn" },
          {
            field: "Pourquoi Airbus ?",
            value:
              "Mon projet de fin d'études portait sur la maintenance prédictive de machines-outils. Travailler sur des données de production réelles à l'échelle de l'A320, et voir un modèle utilisé au quotidien par les équipes, est exactement ce que je cherche.",
          },
        ]
      : [],
    manual: ready
      ? [{ field: "Lettre de recommandation", reason: "Fichier à joindre toi-même, je ne l'ai pas trouvé sur ton ordinateur." }]
      : [],
  };
}

let pdfBlobUrl: string | null = null;

const demo = {
  create(url: string) {
    save({
      url,
      created: now(),
      phase: "steps",
      phaseStart: now(),
      finalStatus: null,
      chat: [],
      answered: [false, false, false],
    });
    return { id: "demo-1" };
  },
  get(): Application | null {
    const s = load();
    if (!s) return null;
    const next = advance(s);
    save(next);
    return toApplication(next);
  },
  continue() {
    const s = load();
    if (s && s.phase === "action") {
      s.phase = "after_action";
      s.phaseStart = now();
      save(s);
    }
    return null;
  },
  retry() {
    return null;
  },
  answers(text: string) {
    const s = load();
    if (!s) return null;
    s.chat.push({ role: "user", text, time: hhmm() });
    if (s.phase === "questions") s.phase = "reading1";
    else if (s.phase === "followup") s.phase = "reading2";
    s.phaseStart = now();
    save(s);
    return null;
  },
  setStatus(st: "submitted" | "abandoned") {
    const s = load();
    if (s) {
      s.finalStatus = st;
      save(s);
    }
    return null;
  },
  pdfUrl() {
    if (!pdfBlobUrl && typeof window !== "undefined") {
      pdfBlobUrl = URL.createObjectURL(new Blob([buildSamplePdf()], { type: "application/pdf" }));
    }
    return pdfBlobUrl ?? "";
  },
};

/** PDF d'exemple minimal, généré à la volée. */
function buildSamplePdf(): string {
  const esc = (t: string) => t.replace(/[()\\]/g, (c) => "\\" + c);
  const lines: [number, number, string][] = [
    [22, 760, "Camille Martin"],
    [11, 740, "Ingenieure data - INSA Toulouse, Genie mathematique"],
    [10, 724, "camille.martin@example.fr  -  06 12 34 56 78  -  Toulouse"],
    [13, 690, "Experiences"],
    [11, 670, "Stage Data Scientist - Thales Alenia Space (2025, 6 mois)"],
    [10, 655, "Detection d'anomalies sur donnees de tests satellites (PyTorch)."],
    [11, 630, "Projet de fin d'etudes - Maintenance predictive"],
    [10, 615, "Prediction de pannes de machines-outils, gain de 18 % de disponibilite."],
    [13, 580, "Competences"],
    [10, 560, "Python, PyTorch, scikit-learn, SQL, pandas, Git, notions de Docker"],
    [13, 525, "Langues"],
    [10, 505, "Francais (natif), Anglais C1 - TOEIC 945"],
  ];
  const content = lines
    .map(([size, y, t]) => `BT /F1 ${size} Tf 60 ${y} Td (${esc(t)}) Tj ET`)
    .join("\n");
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objs.forEach((o, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  offsets.forEach((o) => (out += `${String(o).padStart(10, "0")} 00000 n \n`));
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return out;
}
