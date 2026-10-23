// « Vue d'ensemble » tab of an application: the job and the company (left), the candidate's profile for
// this job (right), then the detailed requirements, folded. Display only: texts come from analysis.json
// (and from preparation.json for the company activity, when it exists) unchanged; nothing calls Claude
// here except the explicit « Analyser » / « Relancer l'analyse » buttons.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CircleCheck,
  CircleDashed,
  CircleHelp,
  ChevronRight,
  ClipboardList,
  Loader2,
  RefreshCw,
  ScanSearch,
} from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Badge, badgeVariants } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/features/candidate/components/common";
import { cn } from "@/lib/utils";
import {
  cvApi,
  type CompletedAnalysis,
  type CvSummary,
  type Evidence,
  type Requirement,
  type RequirementStatus,
} from "@/services/api/cvApi";
import {
  attentionPoints,
  exampleTasks,
  firstSentence,
  jobBrief,
  keySkills,
  mainMissions,
  requirementLines,
  type PartsRelation,
  type RequirementGroup,
  type RequirementLine,
  type AttentionPoint,
} from "../adapters";
import { STATUS_CLASSES, STATUS_LABELS } from "../analysisLabels";
import {
  cvAnalysisQuery,
  cvListQuery,
  cvPreparationQuery,
  errorMessage,
  useCvTask,
} from "../hooks";
import { FoldableSection } from "./AnalysisParts";

/** What the main view shows: the essentials; the full lists stay in the data and in the detail. */
const SHOWN = { missions: 4, tasks: 2, skills: 6, strengths: 3 } as const;

const ATTENTION_LABELS: Record<AttentionPoint["status"], string> = {
  missing: "non remplie",
  partial: "partiellement remplie",
  not_documented: "non documentée dans votre profil, à confirmer",
};

/** Follows the analysis task started from this tab (GET /api/cvs/tasks/{id}). */
function AnalysisProgress({
  taskId,
  onFinished,
}: {
  taskId: string;
  onFinished: (error: string | null) => void;
}) {
  const { data: task, error } = useCvTask(taskId);
  const reported = useRef(false);

  useEffect(() => {
    if (reported.current || !(task?.status === "completed" || task?.status === "failed" || error))
      return;
    reported.current = true;
    if (task?.status === "completed") onFinished(null);
    else if (task?.status === "failed")
      onFinished(
        [task.error?.message, ...(task.error?.problems ?? [])].filter(Boolean).join(" ") ||
          "L'analyse a échoué.",
      );
    else if (error) onFinished(errorMessage(error));
  }, [task?.status, task?.error, error, onFinished]);

  return (
    <RunningCard
      label={
        task?.status === "pending" ? "Analyse en attente…" : "Analyse de correspondance en cours…"
      }
    />
  );
}

function RunningCard({ label }: { label: string }) {
  return (
    <div className="rounded-xl border bg-card p-6 shadow-soft">
      <p className="flex items-center gap-2 text-sm font-medium">
        <Loader2 className="size-4 animate-spin text-primary" />
        {label}
      </p>
      <p className="mt-2 text-sm text-muted-foreground">
        L'offre est comparée à votre profil candidat. Cela peut prendre une à deux minutes ; le CV
        n'est pas modifié.
      </p>
    </div>
  );
}

// ---------- Layout pieces ----------

function Column({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="rounded-xl border bg-card p-4 shadow-soft sm:p-5">
      <h2 id={id} className="text-base font-semibold tracking-tight">
        {title}
      </h2>
      <div className="mt-3 space-y-4">{children}</div>
    </section>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function TextToggle({
  open,
  onToggle,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="mt-1 text-xs font-medium text-primary hover:underline"
    >
      {children}
    </button>
  );
}

function Bullets({ items, muted = false }: { items: string[]; muted?: boolean }) {
  return (
    <ul className="space-y-1">
      {items.map((item, i) => (
        <li
          key={i}
          className={`flex gap-2.5 text-sm leading-relaxed ${muted ? "text-muted-foreground" : ""}`}
        >
          {muted ? (
            <CircleDashed className="mt-1 size-3.5 shrink-0" />
          ) : (
            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/60" />
          )}
          {item}
        </li>
      ))}
    </ul>
  );
}

/** Profile references of an opened requirement: discreet labels, the justification on hover. */
function EvidenceLabels({ evidence }: { evidence: Evidence[] }) {
  const unique = [...new Map(evidence.filter((e) => e.label).map((e) => [e.label, e])).values()];
  if (unique.length === 0) return null;
  return (
    <p className="text-xs text-muted-foreground">
      Dans ton profil :{" "}
      {unique.map((e, i) => (
        <span key={e.label} title={e.justification || undefined}>
          {i > 0 && " · "}
          {e.label}
        </span>
      ))}
    </p>
  );
}

// ---------- Left column: the job and the company ----------

function JobColumn({
  analysis,
  activity,
}: {
  analysis: CompletedAnalysis;
  activity: string | null;
}) {
  const { overview } = analysis;
  const brief = jobBrief(overview.summary, activity);
  const [allMissions, setAllMissions] = useState(false);
  const missions = mainMissions(overview.missions, SHOWN.missions);
  const hasMoreMissions = overview.missions.filter((m) => m.trim()).length > missions.length;
  const tasks = exampleTasks(overview.possible_tasks, missions, SHOWN.tasks);
  const skills = keySkills(analysis, SHOWN.skills);

  return (
    <Column title="Le poste et l'entreprise">
      {brief.company && (
        <Block title="L'entreprise">
          <p className="text-sm leading-relaxed">{brief.company}</p>
        </Block>
      )}

      {brief.job && (
        <Block title="Le poste en bref">
          <p className="text-sm leading-relaxed">{brief.job}</p>
        </Block>
      )}

      {missions.length > 0 && (
        <Block title="Missions principales">
          <Bullets items={allMissions ? overview.missions : missions} />
          {hasMoreMissions && (
            <TextToggle open={allMissions} onToggle={() => setAllMissions((o) => !o)}>
              {allMissions
                ? "Afficher les missions principales"
                : `Voir toutes les missions (${overview.missions.length})`}
            </TextToggle>
          )}
        </Block>
      )}

      {tasks.length > 0 && (
        <Block title="Exemples de tâches possibles">
          <Bullets items={tasks} muted />
        </Block>
      )}

      {skills.length > 0 && (
        <Block title="Compétences clés">
          <div className="flex flex-wrap gap-1.5">
            {skills.map((s) => (
              <Badge key={s} variant="secondary" className="font-normal">
                {s}
              </Badge>
            ))}
          </div>
        </Block>
      )}
    </Column>
  );
}

// ---------- Right column: my profile for this job ----------

function AttentionIcon({ status }: { status: AttentionPoint["status"] }) {
  return status === "not_documented" ? (
    <CircleHelp className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
  ) : (
    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
  );
}

function ProfileColumn({ analysis }: { analysis: CompletedAnalysis }) {
  const strengths = analysis.strengths.slice(0, SHOWN.strengths);
  const attention = attentionPoints(analysis);

  return (
    <Column title="Mon profil pour ce poste">
      <Block title="À mettre en avant">
        {strengths.length > 0 ? (
          <ul className="space-y-2.5">
            {strengths.map((s, i) => (
              <li key={i} className="flex gap-2.5">
                <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <div className="min-w-0">
                  <p className="text-sm font-medium leading-snug">{s.title}</p>
                  {s.explanation && (
                    <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">
                      {firstSentence(s.explanation)}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            L'analyse n'a pas identifié d'atout particulier : consultez les exigences détaillées
            ci-dessous.
          </p>
        )}
      </Block>

      {attention.length > 0 && (
        <Block title="Points d'attention">
          <ul className="space-y-2.5">
            {attention.map(({ id, text, status, explanation }) => (
              <li key={id} className="flex gap-2.5">
                <AttentionIcon status={status} />
                <div className="min-w-0">
                  <p className="text-sm font-medium leading-snug">
                    {text}
                    <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                      — {ATTENTION_LABELS[status]}
                    </span>
                  </p>
                  {explanation && (
                    <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">
                      {explanation}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Block>
      )}
    </Column>
  );
}

// ---------- Detailed requirements (one folded section, one line per requirement of the offer) ----------

const STATUS_ORDER: RequirementStatus[] = ["met", "partial", "not_documented", "missing"];

const COUNT_LABELS: Record<RequirementStatus, [string, string]> = {
  met: ["remplie", "remplies"],
  partial: ["partiellement remplie", "partiellement remplies"],
  not_documented: ["non documentée", "non documentées"],
  missing: ["non remplie", "non remplies"],
};

const GROUPS: [RequirementGroup, string][] = [
  ["required", "Obligatoires"],
  ["essential", "Essentielles"],
  ["preferred", "Souhaitées"],
];

const RELATION_NOTES: Record<PartsRelation, string | null> = {
  or: "L'offre demande l'un de ces éléments : un seul peut suffire.",
  and: "L'offre demande chacun de ces éléments.",
  unknown: null,
};

/** "2 remplies · 1 non documentée": statuses counted without merging them. */
function countText(statuses: RequirementStatus[]): string {
  return STATUS_ORDER.map((status) => {
    const n = statuses.filter((s) => s === status).length;
    return n > 0 ? `${n} ${COUNT_LABELS[status][n > 1 ? 1 : 0]}` : null;
  })
    .filter(Boolean)
    .join(" · ");
}

function StatusBadge({ status }: { status: RequirementStatus }) {
  return (
    <span
      className={cn(
        badgeVariants({ variant: "outline" }),
        "shrink-0 border-transparent font-normal",
        STATUS_CLASSES[status],
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

/** A criterion in an opened line: its text and status (split parts), its justification, its references. */
function Criterion({ r, withTitle }: { r: Requirement; withTitle: boolean }) {
  return (
    <div className="space-y-0.5">
      {withTitle && (
        <p className="flex items-start justify-between gap-3 text-[13px] font-medium">
          <span>{r.text}</span>
          <StatusBadge status={r.status} />
        </p>
      )}
      {r.explanation && (
        <p className="text-[13px] leading-relaxed text-muted-foreground">{r.explanation}</p>
      )}
      <EvidenceLabels evidence={r.evidence} />
    </div>
  );
}

/**
 * One line per requirement of the offer: its text and its overall status when it is reliable
 * (otherwise the statuses of its criteria, counted). A click (or Enter / Space) opens, right below
 * the line, its criteria with their own status, justification and profile references.
 */
function RequirementRow({
  line,
  open,
  onToggle,
}: {
  line: RequirementLine;
  open: boolean;
  onToggle: () => void;
}) {
  const detailId = useId();
  const split = line.parts.length > 1;
  const note = line.relation ? RELATION_NOTES[line.relation] : null;
  const hasDetail =
    split || line.parts.some((p) => p.explanation || p.evidence.some((e) => e.label));
  const content = (
    <span className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <span className="text-sm font-medium">{line.text}</span>
      {line.status ? (
        <StatusBadge status={line.status} />
      ) : (
        <span className="shrink-0 text-xs text-muted-foreground">
          {countText(line.parts.map((p) => p.status))}
        </span>
      )}
    </span>
  );

  if (!hasDetail)
    return (
      <li className="flex gap-2 py-1.5">
        <span className="size-3.5 shrink-0" />
        {content}
      </li>
    );
  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={detailId}
        className="-mx-2 flex w-[calc(100%+1rem)] gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
      >
        <ChevronRight
          className={`mt-0.5 size-3.5 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-90" : ""}`}
        />
        {content}
      </button>
      <div id={detailId} hidden={!open} className="space-y-2 pb-2.5 pl-[1.375rem]">
        {note && <p className="text-[13px] text-muted-foreground">{note}</p>}
        {line.parts.map((p) => (
          <Criterion key={p.id} r={p} withTitle={split} />
        ))}
      </div>
    </li>
  );
}

function RequirementsDetail({ lines }: { lines: RequirementLine[] }) {
  // One requirement open at a time: the list stays short to read.
  const [openId, setOpenId] = useState<string | null>(null);
  const known = lines.flatMap((l) => (l.status ? [l.status] : []));
  const mixed = lines.length - known.length;
  const counts = [countText(known), mixed > 0 ? `${mixed} à plusieurs statuts` : ""].filter(
    Boolean,
  );

  return (
    <FoldableSection
      icon={ClipboardList}
      title="Exigences détaillées"
      count={lines.length}
      titleClassName="text-lg"
    >
      <p className="text-xs text-muted-foreground">{counts.join(" · ")}</p>
      {GROUPS.map(([group, title]) => {
        const items = lines.filter((l) => l.group === group);
        if (items.length === 0) return null;
        return (
          <div key={group} className="mt-5">
            <h4 className="text-[15px] font-semibold text-foreground">{title}</h4>
            <ul className="mt-1 divide-y">
              {items.map((line) => (
                <RequirementRow
                  key={line.id}
                  line={line}
                  open={openId === line.id}
                  onToggle={() => setOpenId((id) => (id === line.id ? null : line.id))}
                />
              ))}
            </ul>
          </div>
        );
      })}
    </FoldableSection>
  );
}

// ---------- Tab ----------

/**
 * « Vue d'ensemble » of an application. Interview preparation lives in its own tab (PreparationTab):
 * the recommendations and questions of older analyses are not shown here, nor is the fit score.
 */
export function OverviewTab({ cv }: { cv: CvSummary }) {
  const qc = useQueryClient();
  const [taskId, setTaskId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [taskError, setTaskError] = useState<string | null>(null);
  const {
    data: analysis,
    isLoading,
    error,
    refetch,
  } = useQuery({
    ...cvAnalysisQuery(cv.id),
    // An analysis started elsewhere (generation, another tab) is followed until it ends.
    refetchInterval: (query) => (!taskId && query.state.data?.running ? 2000 : false),
  });
  // Optional enrichment: the company activity stated in the offer, kept by the interview preparation
  // when it was made. Reading it never calls Claude; its errors are shown in the « Entretien » tab.
  const { data: preparation } = useQuery(cvPreparationQuery(cv.id));
  const activityFromPreparation =
    preparation?.company.facts.find((f) => f.topic === "activity" && f.origin === "offer")?.text ??
    null;

  const startAnalysis = async () => {
    setStarting(true);
    setTaskError(null);
    try {
      const { task_id } = await cvApi.startAnalysis(cv.id);
      setTaskId(task_id);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setStarting(false);
    }
  };

  const onFinished = async (failure: string | null) => {
    setTaskId(null);
    if (failure) {
      setTaskError(failure);
      toast.error("L'analyse a échoué.");
    } else {
      toast.success("Analyse terminée.");
    }
    await Promise.all([
      qc.invalidateQueries({ queryKey: cvAnalysisQuery(cv.id).queryKey }),
      qc.invalidateQueries({ queryKey: cvListQuery.queryKey, exact: true }),
    ]);
  };

  const launchButton = (label: string) => (
    <Button onClick={() => void startAnalysis()} disabled={starting}>
      {starting ? <Loader2 className="size-4 animate-spin" /> : <ScanSearch className="size-4" />}
      {label}
    </Button>
  );

  if (taskId) return <AnalysisProgress taskId={taskId} onFinished={(f) => void onFinished(f)} />;

  if (isLoading)
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-80 w-full rounded-xl" />
        <Skeleton className="h-80 w-full rounded-xl" />
      </div>
    );

  if (error)
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Impossible de charger l'analyse"
        text={errorMessage(error)}
        action={
          <Button variant="outline" onClick={() => void refetch()}>
            <RefreshCw className="size-4" />
            Réessayer
          </Button>
        }
      />
    );

  if (analysis?.running) return <RunningCard label="Analyse de correspondance en cours…" />;

  const failureNotice = taskError && (
    <div className="flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
      <p>
        La dernière analyse a échoué : {taskError}
        {analysis?.status === "completed" && " L'analyse précédente est conservée ci-dessous."}
      </p>
    </div>
  );

  if (!analysis)
    return (
      <div className="space-y-4">
        {failureNotice}
        <EmptyState
          icon={ScanSearch}
          title="Analyse non effectuée"
          text="Aucune analyse n'est enregistrée pour cette candidature. Lancez-la pour comprendre le poste et voir ce qui, dans votre profil, est à mettre en avant. Le CV ne sera pas modifié."
          action={launchButton(taskError ? "Relancer l'analyse" : "Analyser cette candidature")}
        />
      </div>
    );

  if (analysis.status === "failed")
    return (
      <div className="space-y-4">
        {failureNotice}
        <EmptyState
          icon={AlertTriangle}
          title="L'analyse a échoué"
          text={[analysis.error.message, ...analysis.error.problems].filter(Boolean).join(" ")}
          action={launchButton("Relancer l'analyse")}
        />
      </div>
    );

  const lines = requirementLines(analysis);
  // What the company does: from the offer (newer analyses), else from the deep preparation when it
  // kept one from the offer. Never guessed; jobBrief drops it when it only repeats the job.
  const activity = analysis.offer.company_activity || activityFromPreparation;

  return (
    <div className="space-y-4">
      {failureNotice}

      <div className="grid items-start gap-4 lg:grid-cols-2 lg:gap-5">
        <JobColumn analysis={analysis} activity={activity} />
        <ProfileColumn analysis={analysis} />
      </div>

      {lines.length > 0 && <RequirementsDetail lines={lines} />}

      {/* analysis.warnings are technical diagnostics (ignored evidence, duplicates): kept in the file, not shown. */}
      <div className="flex justify-end">
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          disabled={starting}
          onClick={() => void startAnalysis()}
        >
          {starting ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
          Relancer l'analyse
        </Button>
      </div>
    </div>
  );
}
