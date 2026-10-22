import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  CalendarDays,
  ChevronRight,
  FileText,
  Files,
  Lock,
  RefreshCw,
  Sparkles,
  WifiOff,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/features/candidate/components/common";
import type { CvSummary } from "@/services/api/cvTypes";
import { GenerateCvDialog } from "../components/GenerateCvDialog";
import { cvTitle, formatTimestamp } from "../format";
import { cvAnalysisQuery, errorMessage, useCvList } from "../hooks";

/** Short summary of the offer, only when an analysis has been saved for this CV (never invented). */
function JobSummary({ cv }: { cv: CvSummary }) {
  const { data } = useQuery({
    ...cvAnalysisQuery(cv.id),
    enabled: cv.analysis_status === "completed",
  });
  if (data?.status !== "completed" || !data.overview.summary) return null;
  return (
    <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
      {data.overview.summary}
    </p>
  );
}

export function CvListPage() {
  const { data: cvs, isLoading, error, refetch, isFetching } = useCvList();
  const [generateOpen, setGenerateOpen] = useState(false);

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-8 sm:py-10">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Mes CV</h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            Retrouvez les CV générés pour chaque candidature, avec leur analyse d'adéquation.
          </p>
        </div>
        <Button className="shrink-0" onClick={() => setGenerateOpen(true)}>
          <Sparkles className="size-4" />
          Générer un CV
        </Button>
      </div>

      <div className="mt-8">
        {error ? (
          <EmptyState
            icon={WifiOff}
            title="Impossible de charger vos CV"
            text={errorMessage(error)}
            action={
              <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
                <RefreshCw className={`size-4 ${isFetching ? "animate-spin" : ""}`} />
                Réessayer
              </Button>
            }
          />
        ) : isLoading || !cvs ? (
          <div className="grid gap-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-28 w-full rounded-xl" />
            ))}
          </div>
        ) : cvs.length === 0 ? (
          <EmptyState
            icon={Files}
            title="Aucun CV enregistré"
            text="Générez votre premier CV adapté à une offre d'emploi en collant simplement son URL."
            action={
              <Button onClick={() => setGenerateOpen(true)}>
                <Sparkles className="size-4" />
                Générer un CV
              </Button>
            }
          />
        ) : (
          <div className="grid gap-3">
            {cvs.map((cv, i) => (
              <Link
                key={cv.id}
                to="/cvs/$cvId"
                params={{ cvId: cv.id }}
                search={{ tab: "analyse" }}
                className="group flex animate-fade-up items-start gap-3.5 rounded-xl border bg-card p-4 shadow-soft transition-all hover:border-primary/30 hover:shadow-lift sm:px-5"
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                  <FileText className="size-[18px]" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-medium leading-snug group-hover:text-primary">
                      {cvTitle(cv)}
                    </h3>
                    {!cv.editable && (
                      <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
                        <Lock className="size-3" />
                        PDF uniquement
                      </Badge>
                    )}
                  </div>
                  {cv.company && <p className="text-sm text-muted-foreground">{cv.company}</p>}
                  <JobSummary cv={cv} />
                  <p className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <CalendarDays className="size-3" />
                    {formatTimestamp(cv.created_at)}
                  </p>
                </div>
                <ChevronRight className="mt-2 size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </Link>
            ))}
          </div>
        )}
      </div>

      <GenerateCvDialog open={generateOpen} onOpenChange={setGenerateOpen} />
    </div>
  );
}
