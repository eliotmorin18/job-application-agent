import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Award,
  Briefcase,
  CircleCheck,
  CircleDashed,
  CircleHelp,
  ClipboardList,
  Cpu,
  GraduationCap,
  Lightbulb,
  ListChecks,
  Loader2,
  MessageSquare,
  Puzzle,
  RefreshCw,
  ScanSearch,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, SectionCard, TagList } from "@/features/candidate/components/common";
import {
  cvApi,
  type CompletedAnalysis,
  type CvSummary,
  type RequirementStatus,
} from "@/services/api/cvApi";
import { STATUS_CLASSES, STATUS_LABELS } from "../analysisLabels";
import { taskText } from "../format";
import { cvAnalysisQuery, cvListQuery, errorMessage, useCvTask } from "../hooks";
import {
  EvidenceBadges,
  FoldableBlock,
  FoldableSection,
  InsightCard,
  MetaBadge,
} from "./AnalysisParts";
import { InterviewQuestions } from "./InterviewQuestions";

type WeaknessKind = "missing" | "not_documented" | "partial";

const WEAKNESS_LABELS: Record<WeaknessKind, string> = {
  missing: "Non remplie",
  not_documented: "Non documentée",
  partial: "Partiellement remplie",
};

// Soft tones only (amber family), never an alarming red inside the weakness cards.
const WEAKNESS_BADGES: Record<WeaknessKind, string> = {
  partial: "bg-priority-medium text-priority-medium-foreground",
  not_documented: "bg-muted text-muted-foreground",
  missing: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
};

function BulletList({ items, muted = false }: { items: string[]; muted?: boolean }) {
  return (
    <ul className="space-y-2">
      {items.map((m, i) => (
        <li
          key={i}
          className={`flex gap-3 text-sm leading-relaxed ${muted ? "text-muted-foreground" : ""}`}
        >
          {muted ? (
            <CircleDashed className="mt-0.5 size-3.5 shrink-0" />
          ) : (
            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/60" />
          )}
          {m}
        </li>
      ))}
    </ul>
  );
}

function EmptyLine({ children }: { children: string }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

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

export type AnalysisView = "offre" | "preparation";

/**
 * Fit analysis of an application. The same component (one query, same loading/missing/failed states)
 * backs two tabs: "offre" (understanding the job, strengths, weaknesses, requirements) and
 * "preparation" (interview advice, possible questions, skills to deepen, points of vigilance).
 */
export function AnalysisTab({ cv, view = "offre" }: { cv: CvSummary; view?: AnalysisView }) {
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
      <div className="space-y-4">
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
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
          text="Aucune analyse d'adéquation n'est enregistrée pour cette candidature. Lancez-la pour obtenir les points forts, les points faibles et les recommandations. Le CV ne sera pas modifié."
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

  const a: CompletedAnalysis = analysis;
  // "cv" recommendations (« Améliorer le CV ») are kept in analysis.json but not shown: the CV is already tailored.
  const byCategory = (category: "interview" | "learning" | "obstacle") =>
    a.recommendations.filter((r) => r.category === category);
  const interview = byCategory("interview");
  const questions = a.interview_questions ?? []; // absent from analyses saved before this feature
  const learning = byCategory("learning");
  const obstacles = byCategory("obstacle");
  const requirements = a.requirements.filter((r) => !r.duplicate_of);
  const skills = [...new Set([...a.overview.technologies, ...a.overview.skills_sought])];
  const hasPreparation =
    interview.length + questions.length + learning.length + obstacles.length > 0;
  const hasDetails =
    a.overview.missions.length > 0 || skills.length > 0 || a.overview.possible_tasks.length > 0;

  return (
    <div className="space-y-4">
      {failureNotice}

      {view === "offre" ? (
        <>
          {/* B. Comprendre le poste */}
          <FoldableSection icon={Briefcase} title="Comprendre le poste">
            <div className="space-y-4">
              {a.overview.summary && (
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {a.overview.summary}
                </p>
              )}
              {a.overview.plain_explanation && (
                <div className="rounded-lg bg-accent/50 p-4">
                  <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-accent-foreground">
                    <Lightbulb className="size-3.5" />
                    En pratique
                  </p>
                  <p className="text-sm leading-relaxed">{a.overview.plain_explanation}</p>
                </div>
              )}

              {hasDetails && (
                <div className="divide-y overflow-hidden rounded-lg border">
                  {a.overview.missions.length > 0 && (
                    <FoldableBlock
                      icon={ListChecks}
                      title="Missions principales"
                      count={a.overview.missions.length}
                      defaultOpen
                    >
                      <BulletList items={a.overview.missions} />
                    </FoldableBlock>
                  )}
                  {skills.length > 0 && (
                    <FoldableBlock
                      icon={Cpu}
                      title="Technologies et compétences recherchées"
                      count={skills.length}
                    >
                      <TagList tags={skills} />
                    </FoldableBlock>
                  )}
                  {a.overview.possible_tasks.length > 0 && (
                    <FoldableBlock
                      icon={CircleHelp}
                      title="Exemples de tâches possibles"
                      count={a.overview.possible_tasks.length}
                    >
                      <p className="mb-2.5 text-xs text-muted-foreground">
                        À titre d'exemple, ce poste pourrait vous amener à :
                      </p>
                      <BulletList items={a.overview.possible_tasks.map(taskText)} muted />
                    </FoldableBlock>
                  )}
                </div>
              )}
            </div>
          </FoldableSection>

          {/* C. Points forts */}
          <FoldableSection icon={Award} title="Mes points forts" count={a.strengths.length}>
            {a.strengths.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2">
                {a.strengths.map((s, i) => (
                  <InsightCard
                    key={i}
                    tone="strength"
                    icon={CircleCheck}
                    title={s.title}
                    explanation={s.explanation}
                    footer={s.evidence.length > 0 && <EvidenceBadges evidence={s.evidence} />}
                  />
                ))}
              </div>
            ) : (
              <EmptyLine>Aucun point fort n'a été identifié dans cette analyse.</EmptyLine>
            )}
          </FoldableSection>

          {/* D. Points faibles */}
          <FoldableSection icon={Puzzle} title="Mes points faibles" count={a.weaknesses.length}>
            {a.weaknesses.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2">
                {a.weaknesses.map((w, i) => (
                  <InsightCard
                    key={i}
                    tone="weakness"
                    icon={AlertTriangle}
                    title={w.text}
                    explanation={w.explanation}
                    footer={
                      <>
                        <Badge
                          className={`border-transparent font-normal ${WEAKNESS_BADGES[w.kind]}`}
                        >
                          {WEAKNESS_LABELS[w.kind]}
                        </Badge>
                        {w.category === "preferred" && <MetaBadge>Exigence souhaitée</MetaBadge>}
                      </>
                    }
                  />
                ))}
              </div>
            ) : (
              <EmptyLine>Aucun point faible n'a été identifié dans cette analyse.</EmptyLine>
            )}
          </FoldableSection>

          {/* E. Détail des exigences */}
          {requirements.length > 0 && (
            <FoldableSection
              icon={ClipboardList}
              title="Détail des exigences"
              count={requirements.length}
            >
              <ul className="divide-y">
                {requirements.map((r) => (
                  <li
                    key={r.id}
                    className="flex flex-col gap-1.5 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{r.text}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">{r.explanation}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {r.category === "required"
                          ? r.importance === "high"
                            ? "Essentielle"
                            : "Obligatoire"
                          : "Souhaitée"}
                      </span>
                      <Badge
                        className={`border-transparent font-normal ${STATUS_CLASSES[r.status]}`}
                      >
                        {STATUS_LABELS[r.status]}
                      </Badge>
                    </div>
                  </li>
                ))}
              </ul>
            </FoldableSection>
          )}
        </>
      ) : hasPreparation ? (
        // F. Préparer ma candidature (the "cv" recommendations are not shown)
        <SectionCard title="Préparer ma candidature">
          <div className="divide-y overflow-hidden rounded-lg border">
            {interview.length + questions.length > 0 && (
              <FoldableBlock
                icon={MessageSquare}
                title="Préparer l'entretien"
                count={interview.length + questions.length}
                defaultOpen
              >
                <div className="space-y-4">
                  {interview.length > 0 && (
                    <div className="rounded-lg bg-muted/40 p-4">
                      <BulletList items={interview.map((r) => r.text)} />
                    </div>
                  )}
                  <InterviewQuestions questions={questions} requirements={a.requirements} />
                </div>
              </FoldableBlock>
            )}
            {learning.length > 0 && (
              <FoldableBlock
                icon={GraduationCap}
                title="Compétences à approfondir"
                count={learning.length}
                defaultOpen
              >
                <div className={`grid gap-2.5 ${learning.length > 1 ? "md:grid-cols-2" : ""}`}>
                  {learning.map((r, i) => (
                    <p
                      key={i}
                      className="rounded-lg bg-muted/40 p-3.5 text-sm leading-relaxed text-foreground/90"
                    >
                      {r.text}
                    </p>
                  ))}
                </div>
              </FoldableBlock>
            )}
            {obstacles.length > 0 && (
              <FoldableBlock
                icon={AlertTriangle}
                title="Points de vigilance"
                count={obstacles.length}
                tone="warning"
                defaultOpen
              >
                <div className="space-y-2.5 rounded-lg border-l-2 border-l-amber-500/50 bg-amber-500/5 p-4">
                  <BulletList items={obstacles.map((r) => r.text)} />
                </div>
              </FoldableBlock>
            )}
          </div>
        </SectionCard>
      ) : (
        <EmptyState
          icon={MessageSquare}
          title="Aucun conseil de préparation"
          text="Cette analyse ne contient pas de conseils ni de questions pour l'entretien. Vous pouvez relancer l'analyse pour les obtenir."
        />
      )}

      {view === "offre" && a.warnings.length > 0 && (
        <p className="px-1 text-xs text-muted-foreground">{a.warnings.join(" ")}</p>
      )}

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
