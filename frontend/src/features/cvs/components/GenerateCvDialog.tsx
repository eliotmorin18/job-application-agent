import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  ArrowRight,
  Check,
  CircleDashed,
  Info,
  Link2,
  Loader2,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cvApi, type CvTask } from "@/services/api/cvApi";
import { generationSteps } from "../adapters";
import { cvListQuery, errorMessage, useCvTask } from "../hooks";

/** Notes about a finished generation, from the task result (the fit score is deliberately not shown). */
function resultNotes(task: CvTask): string[] {
  const result = (task.result ?? {}) as {
    page_adjustments?: string[];
    verification_issues?: number;
    analysis_status?: string;
  };
  const notes: string[] = [];
  if (result.page_adjustments?.length)
    notes.push(`Pour tenir sur une page : ${result.page_adjustments.join(" ")}`);
  if (result.verification_issues)
    notes.push(
      `${result.verification_issues} point${result.verification_issues > 1 ? "s" : ""} signalé${result.verification_issues > 1 ? "s" : ""} par la vérification : relisez le CV avant de l'envoyer.`,
    );
  if (result.analysis_status === "failed")
    notes.push(
      "L'analyse de correspondance a échoué : le CV est prêt, et vous pourrez relancer l'analyse depuis l'onglet « Vue d'ensemble ».",
    );
  return notes;
}

export function GenerateCvDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const [url, setUrl] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const { data: task, error: pollError } = useCvTask(taskId);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const notified = useRef<string | null>(null);

  const finished = task?.status === "completed" || task?.status === "failed" || !!pollError;
  const running = taskId !== null && !finished;

  // The list is refreshed as soon as the generation ends (even if the dialog was closed meanwhile).
  useEffect(() => {
    if (!taskId || !finished || notified.current === taskId) return;
    notified.current = taskId;
    void qc.invalidateQueries({ queryKey: cvListQuery.queryKey, exact: true });
    if (!open) {
      if (task?.status === "completed") toast.success("Candidature préparée.");
      else toast.error("La préparation de la candidature a échoué.");
    }
  }, [taskId, finished, task?.status, open, qc]);

  const reset = () => {
    setUrl("");
    setTaskId(null);
    setStartError(null);
  };

  const close = (o: boolean) => {
    // A running generation keeps going on the server: its progress is kept and shown again on reopening.
    if (!o && !running) reset();
    onOpenChange(o);
  };

  const start = async () => {
    const trimmed = url.trim();
    if (!trimmed || starting) return;
    setStarting(true);
    setStartError(null);
    try {
      const { task_id } = await cvApi.startGeneration(trimmed);
      setTaskId(task_id);
    } catch (e) {
      setStartError(errorMessage(e));
    } finally {
      setStarting(false);
    }
  };

  const openCv = () => {
    const cvId = task?.cv_id;
    if (!cvId) return;
    close(false);
    reset();
    void navigate({ to: "/cvs/$cvId", params: { cvId }, search: { tab: "analyse" } });
  };

  const steps = generationSteps(task);
  const failure =
    task?.status === "failed"
      ? [task.error?.message, ...(task.error?.problems ?? [])].filter(Boolean).join(" ") ||
        "La préparation a échoué."
      : pollError
        ? errorMessage(pollError)
        : null;

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="mb-2 flex size-11 items-center justify-center rounded-full bg-accent text-accent-foreground">
            <Sparkles className="size-5" />
          </div>
          <DialogTitle>Préparer une candidature</DialogTitle>
          <DialogDescription>
            Collez l'URL d'une offre d'emploi : l'offre sera analysée et un CV adapté sera rédigé à
            partir de votre profil.
          </DialogDescription>
        </DialogHeader>

        {taskId === null ? (
          <>
            <div className="flex items-center gap-2">
              <Link2 className="size-4 shrink-0 text-muted-foreground" />
              <Input
                autoFocus
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void start()}
                placeholder="https://…"
                inputMode="url"
                aria-label="URL de l'offre d'emploi"
                disabled={starting}
              />
            </div>
            {startError && (
              <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                {startError}
              </p>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => close(false)}>
                Annuler
              </Button>
              <Button onClick={() => void start()} disabled={!url.trim() || starting}>
                {starting && <Loader2 className="size-4 animate-spin" />}
                Lancer la préparation
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <ul className="space-y-2.5 py-1">
              {steps.map((step) => (
                <li
                  key={step.key}
                  className="flex items-center gap-2.5 text-sm"
                  data-state={step.state}
                >
                  {step.state === "done" ? (
                    <span className="flex size-5 items-center justify-center rounded-full bg-accent text-accent-foreground">
                      <Check className="size-3" />
                    </span>
                  ) : step.state === "active" ? (
                    <Loader2 className="size-5 animate-spin text-primary" />
                  ) : step.state === "failed" ? (
                    <span className="flex size-5 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                      <X className="size-3" />
                    </span>
                  ) : (
                    <CircleDashed className="size-5 text-muted-foreground/50" />
                  )}
                  <span className={step.state === "pending" ? "text-muted-foreground/60" : ""}>
                    {step.state === "active" && task?.step === "correct_cv"
                      ? task.step_label
                      : step.label}
                  </span>
                </li>
              ))}
            </ul>

            {(!task || task.status === "pending") && !failure && (
              <p className="text-sm text-muted-foreground">En attente du démarrage…</p>
            )}
            {running && task?.status === "running" && (
              <p className="text-xs text-muted-foreground">
                Cela prend généralement quelques minutes. Vous pouvez fermer cette fenêtre : la
                préparation continue.
              </p>
            )}

            {failure && (
              <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                {failure}
              </p>
            )}

            {task?.status === "completed" &&
              resultNotes(task).map((note) => (
                <p
                  key={note}
                  className="flex gap-2 rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground"
                >
                  <Info className="mt-0.5 size-4 shrink-0" />
                  {note}
                </p>
              ))}

            <DialogFooter>
              {failure && (
                <Button variant="outline" onClick={() => setTaskId(null)}>
                  <RotateCcw className="size-4" />
                  Réessayer
                </Button>
              )}
              {task?.status === "completed" && task.cv_id && (
                <Button onClick={openCv}>
                  Ouvrir la candidature
                  <ArrowRight className="size-4" />
                </Button>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
