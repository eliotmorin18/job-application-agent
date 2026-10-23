import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Download, ExternalLink, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfirmDialog } from "@/features/candidate/components/common";
import { ApiError, cvApi } from "@/services/api/cvApi";
import { CvEditorTab } from "../components/CvEditorTab";
import { OverviewTab } from "../components/OverviewTab";
import { PreparationTab } from "../components/PreparationTab";
import { applicationTitle, formatTimestamp } from "../format";
import { cvAnalysisQuery, cvListQuery, errorMessage, useCvList } from "../hooks";

/** `?tab=` values: « Vue d'ensemble », « CV », « Entretien » (values unchanged so older links keep working). */
export const CV_DETAIL_TABS = ["analyse", "edition", "preparation"] as const;
export type CvDetailTab = (typeof CV_DETAIL_TABS)[number];

const TABS: [CvDetailTab, string][] = [
  ["analyse", "Vue d'ensemble"],
  ["edition", "CV"],
  ["preparation", "Entretien"],
];

const TAB_TRIGGER =
  "relative flex-none rounded-none border-0 bg-transparent px-3 pb-3 pt-1.5 text-muted-foreground shadow-none after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:bg-transparent hover:text-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-[state=active]:after:bg-primary";

function BackLink() {
  return (
    <Button asChild variant="ghost" size="sm" className="-ml-2 h-7 px-2 text-muted-foreground">
      <Link to="/cvs">
        <ArrowLeft className="size-4" />
        Mes candidatures
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
  // Practical details (location, contract) of the saved analysis: same cached query as the
  // « Vue d'ensemble » tab, absent for applications without analysis.
  const { data: analysis } = useQuery(cvAnalysisQuery(cvId));
  const offer = analysis?.status === "completed" ? analysis.offer : null;

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
      <div className="mx-auto w-full max-w-[88rem] px-4 py-8 sm:px-8">
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

  const details = [
    cv.company,
    offer?.location,
    offer?.contract_type,
    cv.created_at === null ? null : `Préparée le ${formatTimestamp(cv.created_at)}`,
  ].filter(Boolean);

  return (
    <div className="mx-auto w-full max-w-[88rem] px-4 py-5 sm:px-8 sm:py-6">
      <BackLink />

      <header className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
          {details.length > 0 && (
            <p className="mt-1 text-sm text-muted-foreground">
              {details.map((d, i) => (
                <span
                  key={i}
                  className={i === 0 && cv.company ? "font-medium text-foreground/80" : ""}
                >
                  {i > 0 && <span aria-hidden> · </span>}
                  {d}
                </span>
              ))}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
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
          {cv.source_url && (
            <Button asChild variant="outline" size="sm">
              <a href={cv.source_url} target="_blank" rel="noreferrer noopener">
                <ExternalLink className="size-4" />
                Voir l'offre
              </a>
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
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

      <Tabs value={tab} onValueChange={setTab} className="mt-4">
        <TabsList className="h-auto w-full justify-start gap-1 rounded-none border-b bg-transparent p-0">
          {TABS.map(([value, label]) => (
            <TabsTrigger key={value} value={value} className={TAB_TRIGGER}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="analyse" className="mt-5">
          <OverviewTab cv={cv} />
        </TabsContent>
        <TabsContent value="edition" className="mt-5">
          <CvEditorTab cv={cv} />
        </TabsContent>
        {/* Long texts: the « Entretien » tab keeps its former width so lines stay readable. */}
        <TabsContent value="preparation" className="mt-5 max-w-6xl">
          <PreparationTab cv={cv} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
