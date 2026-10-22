import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Download, ExternalLink, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfirmDialog } from "@/features/candidate/components/common";
import { ApiError, cvApi } from "@/services/api/cvApi";
import { AnalysisTab } from "../components/AnalysisTab";
import { CvEditorTab } from "../components/CvEditorTab";
import { cvTitle } from "../format";
import { cvListQuery, errorMessage, useCvList } from "../hooks";

export const CV_DETAIL_TABS = ["analyse", "edition"] as const;
export type CvDetailTab = (typeof CV_DETAIL_TABS)[number];

function BackLink() {
  return (
    <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground">
      <Link to="/cvs">
        <ArrowLeft className="size-4" />
        Retour à Mes CV
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
      toast.success("CV supprimé");
      await backToList();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        toast.info("Ce CV avait déjà été supprimé.");
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

  const title = cvTitle(cv);
  const pdfName = `CV_${(cv.company || cv.id).replace(/[^\p{L}\p{N}]+/gu, "_")}.pdf`;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-8 sm:py-10">
      <BackLink />

      <header className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {cv.company && <p className="mt-1 text-base text-muted-foreground">{cv.company}</p>}
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
                Télécharger le PDF
              </a>
            </Button>
          ) : (
            <Button size="sm" disabled title="Ce CV n'a pas de PDF compilé">
              <Download className="size-4" />
              Télécharger le PDF
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
        title="Supprimer ce CV ?"
        description={`Le CV généré pour « ${title} »${cv.company ? ` (${cv.company})` : ""}, son PDF, son analyse et l'offre enregistrée seront définitivement supprimés.`}
        confirmLabel="Supprimer le CV"
        onConfirm={() => void deleteCv()}
      />

      <Tabs value={tab} onValueChange={setTab} className="mt-6">
        <TabsList className="h-auto w-full justify-start gap-1 rounded-none border-b bg-transparent p-0">
          <TabsTrigger
            value="analyse"
            className="relative flex-none rounded-none border-0 bg-transparent px-3 pb-3 pt-1.5 text-muted-foreground shadow-none after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:bg-transparent hover:text-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-[state=active]:after:bg-primary"
          >
            Analyse de l'offre
          </TabsTrigger>
          <TabsTrigger
            value="edition"
            className="relative flex-none rounded-none border-0 bg-transparent px-3 pb-3 pt-1.5 text-muted-foreground shadow-none after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:bg-transparent hover:text-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-[state=active]:after:bg-primary"
          >
            Éditer le CV
          </TabsTrigger>
        </TabsList>

        <TabsContent value="analyse" className="mt-6">
          <AnalysisTab cv={cv} />
        </TabsContent>
        <TabsContent value="edition" className="mt-6">
          <CvEditorTab cv={cv} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
