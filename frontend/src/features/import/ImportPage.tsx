import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, CheckCircle2, FileText, FileUp, Loader2, RotateCcw } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ApiError,
  importApi,
  type ApplyReport,
  type ImportDecisions,
  type ImportReview,
} from "@/services/api/candidateApi";
import { formatCategory } from "../candidate/format";
import { profileQuery, useProfile } from "../candidate/hooks";
import { sectionConfig } from "../candidate/sectionConfig";
import {
  buildDecisions,
  incompleteChoices,
  initialChoices,
  ITEM_SECTION_KEYS,
  problemsByProposal,
  type Choices,
} from "./decisions";
import { ProblemList, STATUS_LABELS } from "./parts";
import { ReviewStep } from "./ReviewStep";

type Step = "upload" | "extracting" | "review" | "summary" | "done";
const STEPS: { key: Step; label: string }[] = [
  { key: "upload", label: "Dépôt" },
  { key: "extracting", label: "Extraction" },
  { key: "review", label: "Vérification" },
  { key: "summary", label: "Récapitulatif" },
  { key: "done", label: "Terminé" },
];
const MAX_BYTES = 10 * 1024 * 1024;

const errorProblems = (e: unknown) =>
  e instanceof ApiError
    ? e.problems
    : [e instanceof Error ? e.message : "Une erreur est survenue."];

function formatStamp(value: string | null) {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
}

function Stepper({ step }: { step: Step }) {
  const current = STEPS.findIndex((s) => s.key === step);
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      {STEPS.map((s, i) => (
        <li key={s.key} className="flex items-center gap-2">
          <span
            className={cn(
              "flex size-5 items-center justify-center rounded-full text-[10px] font-semibold",
              i < current && "bg-primary/15 text-primary",
              i === current && "bg-primary text-primary-foreground",
              i > current && "bg-muted text-muted-foreground",
            )}
          >
            {i + 1}
          </span>
          <span
            className={cn(i === current ? "font-medium text-foreground" : "text-muted-foreground")}
          >
            {s.label}
          </span>
          {i < STEPS.length - 1 && <span className="mx-1 h-px w-4 bg-border" />}
        </li>
      ))}
    </ol>
  );
}

/** Name of an extracted experience, education or project, as shown to the user. */
function itemName(review: ImportReview, proposalId: string) {
  for (const section of ITEM_SECTION_KEYS) {
    const p = review[section].find((x) => x.proposal_id === proposalId);
    if (p)
      return String(
        p.data["title"] ?? p.data["name"] ?? p.data["degree"] ?? p.data["school"] ?? proposalId,
      );
  }
  return undefined;
}

/** Human-readable lines for the summary step. */
function describe(review: ImportReview, decisions: ImportDecisions) {
  const adds: string[] = [];
  const updates: string[] = [];
  let skips = 0;
  const label = (section: string) =>
    sectionConfig[section as keyof typeof sectionConfig]?.singular ?? section;
  // Corrections sent with a decision (overrides), shown in the summary
  const overridesOf = (d: unknown) =>
    ((d as { overrides?: Record<string, string | string[]> } | undefined)?.overrides ??
      {}) as Record<string, string | string[]>;
  const correctedNote = (d: unknown) => {
    const fields = Object.keys(overridesOf(d));
    return fields.length
      ? ` — corrigé : ${fields.map((f) => f.replace(/_/g, " ")).join(", ")}`
      : "";
  };

  for (const section of ITEM_SECTION_KEYS)
    for (const p of review[section]) {
      const d = decisions[p.proposal_id];
      const o = overridesOf(d);
      const name = String(
        o["title"] ?? o["name"] ?? itemName(review, p.proposal_id) ?? p.proposal_id,
      );
      if (d?.action === "add") adds.push(`${label(section)} · ${name}${correctedNote(d)}`);
      else if (d?.action === "update" && "fields" in d)
        updates.push(
          `${label(section)} · ${name} — reprend : ${d.fields.map((f) => f.replace(/_/g, " ")).join(", ")}${correctedNote(d)}`,
        );
      else skips++;
    }
  for (const s of review.skills) {
    const d = decisions[s.proposal_id];
    const category = (d as { category?: string } | undefined)?.category ?? s.category;
    const skill = overridesOf(d)["skill"] ?? s.skill;
    if (d?.action === "add")
      adds.push(`compétence · ${String(skill)} (${formatCategory(category)})${correctedNote(d)}`);
    else skips++;
  }
  for (const l of review.languages) {
    const d = decisions[l.proposal_id];
    const level = d && "level" in d && d.level ? d.level : l.level;
    const language = overridesOf(d)["language"] ?? l.language;
    if (d?.action === "add")
      adds.push(`langue · ${String(language)} (${level})${correctedNote(d)}`);
    else if (d?.action === "update")
      updates.push(`langue · ${l.matches[0]?.language ?? l.language} — niveau : ${level}`);
    else skips++;
  }
  for (const i of review.interests) {
    const d = decisions[i.proposal_id];
    const interest = String(overridesOf(d)["interest"] ?? i.interest);
    if (d?.action === "add") adds.push(`centre d'intérêt · ${interest}${correctedNote(d)}`);
    else if (d?.action === "update" && "target" in d)
      updates.push(`centre d'intérêt · « ${d.target} » devient « ${interest} »${correctedNote(d)}`);
    else skips++;
  }
  const personal = decisions["personal"];
  if (personal?.action === "update" && "fields" in personal)
    updates.push(`coordonnées — ${personal.fields.join(", ")}${correctedNote(personal)}`);
  return { adds, updates, skips };
}

export function ImportPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: profile } = useProfile();
  const previous = useQuery({ queryKey: ["imports"], queryFn: () => importApi.listImports() });

  const [step, setStep] = useState<Step>("upload");
  const [fileName, setFileName] = useState("");
  const [uploadProblems, setUploadProblems] = useState<string[]>([]);
  const [review, setReview] = useState<ImportReview | null>(null);
  const [choices, setChoices] = useState<Choices | null>(null);
  const [problems, setProblems] = useState<Record<string, string[]>>({});
  const [applying, setApplying] = useState(false);
  const [report, setReport] = useState<ApplyReport | null>(null);
  const [dragging, setDragging] = useState(false);
  const attempt = useRef(0);
  const input = useRef<HTMLInputElement>(null);

  const open = (r: ImportReview) => {
    setReview(r);
    setChoices(initialChoices(r));
    setProblems({});
    setStep("review");
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf")
      return setUploadProblems(["Le fichier doit être un PDF."]);
    if (file.size > MAX_BYTES) return setUploadProblems(["Le fichier dépasse 10 Mo."]);

    const current = ++attempt.current;
    setUploadProblems([]);
    setFileName(file.name);
    setStep("extracting");
    try {
      const r = await importApi.importCv(file);
      if (current !== attempt.current) return; // cancelled meanwhile
      void queryClient.invalidateQueries({ queryKey: ["imports"] });
      open(r);
    } catch (e) {
      if (current !== attempt.current) return;
      setUploadProblems(errorProblems(e));
      setStep("upload");
    }
  };

  const resume = async (importId: string) => {
    setUploadProblems([]);
    try {
      open(await importApi.getReview(importId));
    } catch (e) {
      setUploadProblems(errorProblems(e));
    }
  };

  const toSummary = () => {
    if (!review || !choices) return;
    const local = incompleteChoices(review, choices, profile);
    if (local.length) {
      setProblems(problemsByProposal(local));
      return scrollToProblem(local);
    }
    setProblems({});
    setStep("summary");
    window.scrollTo({ top: 0 });
  };

  const apply = async () => {
    if (!review || !choices) return;
    setApplying(true);
    try {
      setReport(await importApi.applyImport(review.import_id, buildDecisions(review, choices)));
      await queryClient.invalidateQueries({ queryKey: profileQuery.queryKey });
      setStep("done");
    } catch (e) {
      const list = errorProblems(e);
      setProblems(problemsByProposal(list));
      setStep("review");
      scrollToProblem(list);
    } finally {
      setApplying(false);
    }
  };

  const scrollToProblem = (list: string[]) => {
    const first = Object.keys(problemsByProposal(list)).find((k) => k !== "_general");
    setTimeout(() => {
      const el = first ? document.getElementById(`proposal-${first}`) : null;
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
      else window.scrollTo({ top: 0, behavior: "smooth" });
    }, 50);
  };

  const restart = () => {
    attempt.current++;
    setReview(null);
    setChoices(null);
    setReport(null);
    setProblems({});
    setStep("upload");
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void upload(e.dataTransfer.files[0]);
  };

  const summary = review && choices ? describe(review, buildDecisions(review, choices)) : null;
  const changes = report
    ? [
        ...report.added.map((e) => ({ ...e, kind: "Ajouté" })),
        ...report.updated.map((e) => ({ ...e, kind: "Mis à jour" })),
      ]
    : [];

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-8 sm:py-10">
      <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground">
        <Link to="/candidat" search={{ tab: "experiences" }}>
          <ArrowLeft className="size-4" />
          Retour au profil
        </Link>
      </Button>

      <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Importer un CV</h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            Les informations de ton CV sont extraites puis comparées à ton profil. Rien n'est
            enregistré sans ta validation.
          </p>
        </div>
        <Stepper step={step} />
      </div>

      <div className="mt-8">
        {step === "upload" && (
          <div className="space-y-6">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                "flex flex-col items-center justify-center rounded-xl border-2 border-dashed bg-card px-6 py-14 text-center transition-colors",
                dragging ? "border-primary bg-accent/40" : "border-border",
              )}
            >
              <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
                <FileUp className="size-5" />
              </div>
              <p className="text-sm font-medium">Glisse ton CV ici</p>
              <p className="mt-1 text-xs text-muted-foreground">PDF uniquement, 10 Mo maximum</p>
              <Button className="mt-5" onClick={() => input.current?.click()}>
                Choisir un PDF
              </Button>
              <input
                ref={input}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={(e) => {
                  void upload(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
              <p className="mt-5 max-w-md text-xs text-muted-foreground">
                Le texte du PDF est analysé par le backend local. Les CV scannés (images) ne sont
                pas pris en charge.
              </p>
            </div>
            <ProblemList problems={uploadProblems} />

            {(previous.data?.length ?? 0) > 0 && (
              <section className="rounded-xl border bg-card p-5 shadow-soft">
                <h2 className="text-sm font-semibold">Imports précédents</h2>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Reprendre une extraction déjà faite, sans relancer l'analyse.
                </p>
                <ul className="mt-3 divide-y">
                  {previous.data?.map((imp) => (
                    <li
                      key={imp.import_id}
                      className="flex items-center justify-between gap-3 py-2.5"
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        <FileText className="size-4 shrink-0 text-muted-foreground" />
                        <div className="min-w-0">
                          <p className="truncate text-sm">{imp.source_pdf ?? imp.import_id}</p>
                          <p className="text-xs text-muted-foreground">
                            {formatStamp(imp.extracted_at)}
                          </p>
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void resume(imp.import_id)}
                      >
                        Reprendre
                      </Button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}

        {step === "extracting" && (
          <div className="flex flex-col items-center rounded-xl border bg-card px-6 py-16 text-center shadow-soft">
            <Loader2 className="size-8 animate-spin text-primary" />
            <p className="mt-5 text-sm font-medium">Analyse de « {fileName} »</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Lecture du PDF, extraction des informations puis comparaison avec ton profil.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Cela peut prendre une à trois minutes.
            </p>
            <Button variant="ghost" className="mt-6" onClick={restart}>
              Annuler
            </Button>
            <p className="text-xs text-muted-foreground">
              L'analyse se termine en arrière-plan : tu pourras la reprendre dans « Imports
              précédents ».
            </p>
          </div>
        )}

        {step === "review" && review && choices && (
          <div className="space-y-6">
            <div className="flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-soft sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{review.source.source_pdf}</p>
                <p className="text-xs text-muted-foreground">
                  Extrait le {formatStamp(review.source.extracted_at)} ·{" "}
                  {Object.entries(review.summary)
                    .map(
                      ([status, n]) =>
                        `${n} ${STATUS_LABELS[status as keyof typeof STATUS_LABELS].toLowerCase()}`,
                    )
                    .join(" · ")}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setChoices(initialChoices(review))}
              >
                <RotateCcw className="size-3.5" />
                Choix par défaut
              </Button>
            </div>

            <ReviewStep
              review={review}
              choices={choices}
              update={(fn) => setChoices((c) => (c ? fn(c) : c))}
              problems={problems}
              categories={Object.keys(profile?.skills ?? {})}
              profile={profile}
            />

            <div className="sticky bottom-0 -mx-4 flex justify-between gap-2 border-t bg-background/90 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-xl sm:border">
              <Button variant="ghost" onClick={restart}>
                Annuler l'import
              </Button>
              <Button onClick={toSummary}>Continuer</Button>
            </div>
          </div>
        )}

        {step === "summary" && summary && (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-3">
              {[
                { title: "Ajouts", lines: summary.adds },
                { title: "Mises à jour", lines: summary.updates },
              ].map((col) => (
                <section
                  key={col.title}
                  className="rounded-xl border bg-card p-5 shadow-soft md:col-span-1"
                >
                  <h2 className="text-sm font-semibold">
                    {col.title}{" "}
                    <span className="font-normal text-muted-foreground">({col.lines.length})</span>
                  </h2>
                  {col.lines.length ? (
                    <ul className="mt-3 space-y-1.5 text-sm">
                      {col.lines.map((l, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/60" />
                          <span>{l}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-3 text-sm text-muted-foreground">Aucun.</p>
                  )}
                </section>
              ))}
              <section className="rounded-xl border bg-card p-5 shadow-soft">
                <h2 className="text-sm font-semibold">
                  Ignorés{" "}
                  <span className="font-normal text-muted-foreground">({summary.skips})</span>
                </h2>
                <p className="mt-3 text-sm text-muted-foreground">
                  Ces propositions ne modifieront pas ton profil.
                </p>
              </section>
            </div>
            <div className="flex justify-between gap-2">
              <Button variant="ghost" onClick={() => setStep("review")}>
                <ArrowLeft className="size-4" />
                Revenir à la vérification
              </Button>
              <Button
                onClick={() => void apply()}
                disabled={applying || (!summary.adds.length && !summary.updates.length)}
              >
                {applying ? "Enregistrement…" : "Appliquer au profil"}
              </Button>
            </div>
          </div>
        )}

        {step === "done" && report && (
          <div className="space-y-6">
            <div className="flex flex-col items-center rounded-xl border bg-card px-6 py-10 text-center shadow-soft">
              <CheckCircle2 className="size-9 text-primary" />
              <p className="mt-4 text-base font-semibold">Profil mis à jour</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {report.added.length} ajout(s), {report.updated.length} mise(s) à jour,{" "}
                {report.skipped.length} proposition(s) ignorée(s).
              </p>
            </div>
            {changes.length > 0 && (
              <ul className="divide-y rounded-xl border bg-card shadow-soft">
                {changes.map((e) => {
                  const itemSection = ITEM_SECTION_KEYS.find((s) => s === e.section);
                  return (
                    <li
                      key={`${e.kind}-${e.proposal_id}`}
                      className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm"
                    >
                      <span>
                        <span className="text-xs text-muted-foreground">{e.kind} · </span>
                        {e.value ??
                          (review && itemName(review, e.proposal_id)) ??
                          e.id ??
                          e.proposal_id}
                        {e.new_value && ` → ${e.new_value}`}
                      </span>
                      {itemSection && e.id && (
                        <Button asChild size="sm" variant="ghost">
                          <Link
                            to="/candidat/$section/$id"
                            params={{ section: itemSection, id: e.id }}
                          >
                            Voir
                          </Link>
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="flex justify-between gap-2">
              <Button variant="ghost" onClick={restart}>
                Importer un autre CV
              </Button>
              <Button onClick={() => navigate({ to: "/candidat", search: { tab: "experiences" } })}>
                Voir mon profil
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
