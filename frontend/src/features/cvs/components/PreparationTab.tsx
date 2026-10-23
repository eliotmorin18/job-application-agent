// « Entretien » tab: the deep interview preparation (preparation.json), generated once on
// demand. Display only: texts come from the backend unchanged. Without a preparation, only a short
// presentation and the « Générer ma préparation » button are shown.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Briefcase,
  Building2,
  ExternalLink,
  GraduationCap,
  Loader2,
  MessageSquare,
  RefreshCw,
  Sparkles,
  Target,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/features/candidate/components/common";
import {
  cvApi,
  type CompanyFact,
  type CompanyFactTopic,
  type CompanySource,
  type CvSummary,
  type Preparation,
} from "@/services/api/cvApi";
import { STATUS_CLASSES, STATUS_LABELS } from "../analysisLabels";
import { sourceDate } from "../format";
import { cvAnalysisQuery, cvPreparationQuery, errorMessage, useCvTask } from "../hooks";
import { FoldableSection, MetaBadge } from "./AnalysisParts";
import { InterviewQuestions } from "./InterviewQuestions";

const TOPIC_LABELS: Record<CompanyFactTopic, string> = {
  activity: "Activités",
  products: "Produits et services",
  clients: "Clients",
  positioning: "Positionnement",
  sector: "Secteur",
  competitors: "Concurrents",
  news: "Actualités",
};

const RESEARCH_NOTICES: Partial<Record<Preparation["company"]["research_status"], string>> = {
  skipped: "L'offre ne précise pas le nom de l'entreprise : aucune recherche n'a été faite.",
  unavailable:
    "La recherche sur l'entreprise n'a pas pu être faite : seules les informations de l'offre sont affichées.",
  ambiguous:
    "Plusieurs entreprises correspondent à ce nom : aucune information externe n'a été retenue.",
  not_found: "Aucune information fiable n'a été trouvée sur cette entreprise.",
};

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-3 text-sm leading-relaxed">
          <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/60" />
          {item}
        </li>
      ))}
    </ul>
  );
}

function Card({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <div className="space-y-2 rounded-lg bg-muted/40 p-4">
      <p className="text-sm font-medium leading-relaxed">{title}</p>
      {children}
    </div>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return <p className="text-sm leading-relaxed text-muted-foreground">{children}</p>;
}

function SourceLink({ source }: { source: CompanySource }) {
  const date = sourceDate(source.published_at);
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
    >
      <ExternalLink className="size-3" />
      {source.title}
      {date && <span className="text-muted-foreground">· {date}</span>}
      {source.official && <span className="text-muted-foreground">· site officiel</span>}
    </a>
  );
}

function CompanySection({ company }: { company: Preparation["company"] }) {
  const sources = new Map(company.sources.map((s) => [s.id, s]));
  const fromOffer = company.facts.filter((f) => f.origin === "offer");
  const fromWeb = company.facts.filter((f) => f.origin === "web");
  const topics = [...new Set(fromWeb.map((f) => f.topic))];
  const notice =
    RESEARCH_NOTICES[company.research_status] ??
    (fromWeb.length === 0 ? "Aucune information externe vérifiable n'a été retenue." : null);

  const fact = (f: CompanyFact) => (
    <li key={f.id} className="space-y-1">
      <p className="text-sm leading-relaxed">{f.text}</p>
      {f.interview_use && <Muted>{f.interview_use}</Muted>}
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {f.source_ids.map((id) => {
          const source = sources.get(id);
          return source ? <SourceLink key={id} source={source} /> : null;
        })}
      </div>
    </li>
  );

  return (
    <div className="space-y-4">
      {fromOffer.length > 0 && (
        <Card title="D'après l'offre">
          {fromOffer.map((f) => (
            <Muted key={f.id}>{f.text}</Muted>
          ))}
        </Card>
      )}
      {topics.map((topic) => (
        <div key={topic} className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {TOPIC_LABELS[topic] ?? topic}
          </h4>
          <ul className="space-y-3">{fromWeb.filter((f) => f.topic === topic).map(fact)}</ul>
        </div>
      ))}
      {notice && <Muted>{[notice, company.note].filter(Boolean).join(" ")}</Muted>}
      {fromWeb.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Informations issues de pages web consultées lors de la recherche : vérifiez-les avant de
          les citer en entretien.
        </p>
      )}
    </div>
  );
}

function PreparationView({ preparation: p, cvId }: { preparation: Preparation; cvId: string }) {
  const { data: analysis } = useQuery(cvAnalysisQuery(cvId));
  const requirements = analysis?.status === "completed" ? analysis.requirements : [];
  const questionNumber = new Map(p.questions.map((q, i) => [q.id, i + 1]));

  return (
    <div className="space-y-4">
      <FoldableSection icon={Building2} title="Comprendre l'entreprise">
        <CompanySection company={p.company} />
      </FoldableSection>

      <FoldableSection icon={Target} title="Priorités de préparation" count={p.priorities.length}>
        {p.priorities.length > 0 ? (
          <ol className="space-y-3">
            {p.priorities.map((item, i) => (
              <li key={i}>
                <Card title={`${i + 1}. ${item.title}`}>
                  <Muted>{item.why}</Muted>
                  {item.actions.length > 0 && <Bullets items={item.actions} />}
                </Card>
              </li>
            ))}
          </ol>
        ) : (
          <Muted>Aucune priorité particulière n'a été retenue.</Muted>
        )}
      </FoldableSection>

      <FoldableSection icon={MessageSquare} title="Questions probables" count={p.questions.length}>
        {p.questions.length > 0 ? (
          <InterviewQuestions questions={p.questions} requirements={requirements} />
        ) : (
          <Muted>Aucune question n'a été retenue.</Muted>
        )}
      </FoldableSection>

      <FoldableSection
        icon={GraduationCap}
        title="Connaissances à approfondir"
        count={p.knowledge.length}
      >
        {p.knowledge.length > 0 ? (
          <div className="space-y-3">
            {p.knowledge.map((item, i) => (
              <Card key={i} title={item.topic}>
                {item.why && <Muted>{item.why}</Muted>}
                <p className="text-sm leading-relaxed">{item.explanation}</p>
                {item.check_points.length > 0 && <Bullets items={item.check_points} />}
              </Card>
            ))}
          </div>
        ) : (
          <Muted>Aucune notion particulière à réviser n'a été identifiée.</Muted>
        )}
      </FoldableSection>

      <FoldableSection icon={Briefcase} title="Expériences à préparer" count={p.experiences.length}>
        {p.experiences.length > 0 ? (
          <div className="space-y-3">
            {p.experiences.map((item, i) => (
              <Card key={i} title={item.evidence.label}>
                {item.angle && <Muted>{item.angle}</Muted>}
                <Bullets items={item.key_points} />
                {item.question_ids.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <span className="text-xs text-muted-foreground">Utile pour :</span>
                    {item.question_ids.map((id) => (
                      <MetaBadge key={id}>Question {questionNumber.get(id) ?? "?"}</MetaBadge>
                    ))}
                  </div>
                )}
              </Card>
            ))}
          </div>
        ) : (
          <Muted>Aucune expérience à préparer n'a été retenue.</Muted>
        )}
      </FoldableSection>

      <FoldableSection icon={AlertTriangle} title="Points de vigilance" count={p.vigilance.length}>
        {p.vigilance.length > 0 ? (
          <div className="space-y-3">
            {p.vigilance.map((item, i) => (
              <Card
                key={i}
                title={
                  <span className="flex flex-wrap items-center gap-2">
                    {item.concern}
                    {item.kind !== "other" && (
                      <Badge
                        className={`border-transparent font-normal ${STATUS_CLASSES[item.kind]}`}
                      >
                        {STATUS_LABELS[item.kind]}
                      </Badge>
                    )}
                  </span>
                }
              >
                {item.how_to_address.length > 0 && <Bullets items={item.how_to_address} />}
              </Card>
            ))}
          </div>
        ) : (
          <Muted>Aucun point de vigilance particulier n'a été identifié.</Muted>
        )}
      </FoldableSection>
    </div>
  );
}

function ProgressCard({ label }: { label: string }) {
  return (
    <div className="rounded-xl border bg-card p-6 shadow-soft">
      <p className="flex items-center gap-2 text-sm font-medium">
        <Loader2 className="size-4 animate-spin text-primary" />
        {label}
      </p>
      <p className="mt-2 text-sm text-muted-foreground">
        Recherche sur l'entreprise puis rédaction de la préparation. Cela peut prendre quelques
        minutes ; le CV et l'analyse ne sont pas modifiés.
      </p>
    </div>
  );
}

/** Follows the preparation task started from this tab (GET /api/cvs/tasks/{id}). */
function PreparationProgress({
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
        [task.error?.message, ...(task.error?.problems ?? [])].filter(Boolean).join(" : ") ||
          "La préparation a échoué.",
      );
    else if (error) onFinished(errorMessage(error));
  }, [task?.status, task?.error, error, onFinished]);

  const label =
    task?.status === "running" && task.step !== "pending"
      ? `${task.step_label}…`
      : "Préparation en attente…";
  return <ProgressCard label={label} />;
}

export function PreparationTab({ cv }: { cv: CvSummary }) {
  const qc = useQueryClient();
  const [taskId, setTaskId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [taskError, setTaskError] = useState<string | null>(null);
  const {
    data: preparation,
    isLoading,
    error,
    refetch,
  } = useQuery({
    ...cvPreparationQuery(cv.id),
    // A preparation started elsewhere (another tab) is followed until it ends.
    refetchInterval: (query) => (!taskId && query.state.data?.running ? 2000 : false),
  });

  const start = async () => {
    setStarting(true);
    setTaskError(null);
    try {
      const { task_id } = await cvApi.startPreparation(cv.id);
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
      toast.error("La préparation a échoué.");
    } else {
      toast.success("Préparation enregistrée.");
    }
    await qc.invalidateQueries({ queryKey: cvPreparationQuery(cv.id).queryKey });
  };

  if (taskId) return <PreparationProgress taskId={taskId} onFinished={(f) => void onFinished(f)} />;

  if (isLoading) return <Skeleton className="h-40 w-full rounded-xl" />;

  if (error)
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Impossible de charger la préparation"
        text={errorMessage(error)}
        action={
          <Button variant="outline" onClick={() => void refetch()}>
            <RefreshCw className="size-4" />
            Réessayer
          </Button>
        }
      />
    );

  if (preparation?.running) return <ProgressCard label="Préparation en cours…" />;

  if (preparation) return <PreparationView preparation={preparation} cvId={cv.id} />;

  const analysisReady = cv.analysis_status === "completed";
  return (
    <div className="space-y-4">
      <div className="rounded-xl border bg-card p-5 shadow-soft sm:p-6">
        <h3 className="flex items-center gap-2 text-base font-semibold tracking-tight">
          <Sparkles className="size-[18px] text-primary" />
          Préparation approfondie
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Une préparation personnalisée pour cet entretien : l'entreprise (avec ses sources), vos
          priorités, les questions probables, les notions à revoir, les expériences à raconter et
          les points de vigilance. Elle s'appuie sur l'offre, votre profil, le CV et l'analyse, et
          reste enregistrée avec la candidature.
        </p>
        {taskError && (
          <p className="mt-3 flex items-start gap-2 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            La dernière génération a échoué : {taskError}
          </p>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button onClick={() => void start()} disabled={starting || !analysisReady}>
            {starting ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            Générer ma préparation
          </Button>
          {!analysisReady && (
            <span className="text-xs text-muted-foreground">
              Disponible une fois l'analyse d'adéquation terminée (onglet « Vue d'ensemble »).
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
