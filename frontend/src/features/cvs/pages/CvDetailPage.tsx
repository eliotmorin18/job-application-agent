import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  ArrowLeft,
  CalendarDays,
  Download,
  ExternalLink,
  Loader2,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfirmDialog } from "@/features/candidate/components/common";
import { ApiError, cvApi } from "@/services/api/cvApi";
import { AnalysisTab } from "../components/AnalysisTab";
import { CvEditorTab } from "../components/CvEditorTab";
import { applicationTitle, formatTimestamp } from "../format";
import { cvListQuery, errorMessage, useCvList } from "../hooks";

/** `?tab=` values: « Offre et adéquation », « Préparation à l'entretien », « CV » (older links keep working). */
export const CV_DETAIL_TABS = ["analyse", "preparation", "edition"] as const;
export type CvDetailTab = (typeof CV_DETAIL_TABS)[number];

/** [value, label, short label shown on narrow screens where the three full labels do not fit]. */
const TABS: [CvDetailTab, string, string][] = [
  ["analyse", "Offre et adéquation", "Offre"],
  ["preparation", "Préparation à l'entretien", "Entretien"],
  ["edition", "CV", "CV"],
];

const TAB_TRIGGER =
  "relative flex-none rounded-none border-0 bg-transparent px-3 pb-3 pt-1.5 text-muted-foreground shadow-none after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:bg-transparent hover:text-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-[state=active]:after:bg-primary";

function BackLink() {
  return (
    <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground">
      <Link to="/cvs">
        <ArrowLeft className="size-4" />
        Retour à Mes candidatures
      </Link>
    </Button>
  );
}

export function CvDetailPage({ cvId, tab }: { cvId: string; tab: CvDetailTab }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  // The header comes from GET /api/cvs: it also exists for CVs created before cv.json (whose detail answers 409).
  const { data: cvs, isLoading, error, refetch, isFetching } = useCvList();
  const cv = cvs?.find((item) => item.id === cvId);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const setTab = (t: string) =>
    navigate({
      to: "/cvs/$cvId",
      params: { cvId },
      search: { tab: t as CvDetailTab },
      replace: true,
    });

  const backToList = async () => {
    qc.removeQueries({ queryKey: ["cvs", cvId] });
    await qc.invalidateQueries({ queryKey: cvListQuery.queryKey, exact: true });
    await navigate({ to: "/cvs" });
  };

  const deleteCv = async () => {
    setDeleting(true);
    try {
      await cvApi.deleteCv(cvId);
      toast.success("Candidature supprimée");
      await backToList();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        toast.info("Cette candidature avait déjà été supprimée.");
        await backToList();
      } else {
        toast.error(errorMessage(e));
      }
    } finally {
      setDeleting(false);
    }
  };

  if (isLoading)
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-8">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="mt-6 h-96 w-full rounded-xl" />
      </div>
    );

  if (error || !cv)
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-8">
        <BackLink />
        <div className="mt-10 flex flex-col items-center gap-4 text-center text-sm text-muted-foreground">
          <p>
            {error ? errorMessage(error) : "Cette candidature n'existe pas ou a été supprimée."}
          </p>
          {error && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => void refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={`size-4 ${isFetching ? "animate-spin" : ""}`} />
              Réessayer
            </Button>
          )}
        </div>
      </div>
    );

  const title = applicationTitle(cv);
  const pdfName = `CV_${(cv.company || cv.id).replace(/[^\p{L}\p{N}]+/gu, "_")}.pdf`;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-8 sm:py-10">
      <BackLink />

      <header className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {cv.company && <p className="mt-1 text-base text-muted-foreground">{cv.company}</p>}
          <p className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
            <CalendarDays className="size-3" />
            {cv.created_at === null
              ? formatTimestamp(cv.created_at)
              : `Préparée le ${formatTimestamp(cv.created_at)}`}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {cv.source_url && (
            <Button asChild variant="outline" size="sm">
              <a href={cv.source_url} target="_blank" rel="noreferrer noopener">
                <ExternalLink className="size-4" />
                Voir l'offre
              </a>
            </Button>
          )}
          {cv.has_pdf ? (
            <Button asChild size="sm">
              <a href={cvApi.pdfUrl(cv.id, cv.updated_at)} download={pdfName}>
                <Download className="size-4" />
                Télécharger le CV
              </a>
            </Button>
          ) : (
            <Button size="sm" disabled title="Ce CV n'a pas de PDF compilé">
              <Download className="size-4" />
              Télécharger le CV
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="text-destructive hover:text-destructive"
            disabled={deleting}
            onClick={() => setDeleteOpen(true)}
          >
            {deleting ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
            Supprimer
          </Button>
        </div>
      </header>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Supprimer cette candidature ?"
        description={`La candidature « ${title} »${cv.company ? ` (${cv.company})` : ""} sera définitivement supprimée : l'offre enregistrée, son analyse, le CV et son PDF.`}
        confirmLabel="Supprimer la candidature"
        onConfirm={() => void deleteCv()}
      />

      <Tabs value={tab} onValueChange={setTab} className="mt-6">
        <TabsList className="h-auto w-full justify-start gap-1 rounded-none border-b bg-transparent p-0">
          {TABS.map(([value, label, shortLabel]) => (
            <TabsTrigger key={value} value={value} className={TAB_TRIGGER}>
              <span className="sm:hidden">{shortLabel}</span>
              <span className="hidden sm:inline">{label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="analyse" className="mt-6">
          <AnalysisTab cv={cv} view="offre" />
        </TabsContent>
        <TabsContent value="preparation" className="mt-6">
          <AnalysisTab cv={cv} view="preparation" />
        </TabsContent>
        <TabsContent value="edition" className="mt-6">
          <CvEditorTab cv={cv} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
