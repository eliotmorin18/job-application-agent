import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useBlocker } from "@tanstack/react-router";
import { FileX2, Loader2, Lock, RefreshCw, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfirmDialog, EmptyState } from "@/features/candidate/components/common";
import { profileQuery } from "@/features/candidate/hooks";
import { ApiError, cvApi } from "@/services/api/cvApi";
import type { CvDocument, CvSummary } from "@/services/api/cvTypes";
import {
  cleanDocument,
  layoutZones,
  zoneIdFor,
  type CvSelection,
  type ItemSection,
  type LayoutZone,
} from "../adapters";
import { cvDetailQuery, cvLayoutQuery, cvListQuery, errorMessage } from "../hooks";
import { CvEditorPanel } from "./CvEditorPanel";
import { PdfPreview } from "./PdfPreview";

const isItemSection = (section: string): section is ItemSection =>
  section === "experiences" || section === "education" || section === "projects";

/**
 * Same entry in another version of the document (the PDF shows the saved version, the editor the draft):
 * entries are matched by source_id, so a click on the PDF still selects the right entry after a reorder.
 */
function translate(selection: CvSelection, from: CvDocument, to: CvDocument): CvSelection {
  const { section, index } = selection;
  if (!isItemSection(section) || index === undefined) return selection;
  const sourceId = from[section][index]?.source_id;
  const target = to[section].findIndex((entry) => entry.source_id === sourceId);
  return target >= 0 ? { section, index: target } : { section };
}

/** PDF preview of a CV that cannot be edited (created before cv.json, or not loadable). */
function ReadOnlyPreview({ cv, reason }: { cv: CvSummary; reason: string }) {
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2.5 rounded-xl border bg-card px-4 py-3 text-sm shadow-soft">
        <Lock className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <p className="text-muted-foreground">{reason}</p>
      </div>
      {cv.has_pdf ? (
        <div className="h-[calc(100vh-17rem)] min-h-[28rem]">
          <PdfPreview
            pdfUrl={cvApi.pdfUrl(cv.id, cv.updated_at)}
            zones={[]}
            selectedZoneId={null}
            onSelectZone={() => undefined}
          />
        </div>
      ) : (
        <EmptyState icon={FileX2} title="Aucun PDF" text="Ce CV n'a pas de PDF compilé." />
      )}
    </div>
  );
}

export function CvEditorTab({ cv }: { cv: CvSummary }) {
  const qc = useQueryClient();
  const detail = useQuery({ ...cvDetailQuery(cv.id), enabled: cv.editable });
  const saved = detail.data?.document;
  const version = cv.updated_at;
  // The layout is fetched for the PDF version shown: never the zones of a previous compilation.
  const layoutQuery = useQuery({
    ...cvLayoutQuery(cv.id, version),
    enabled: cv.editable && cv.has_layout && !!saved,
  });
  const profile = useQuery({ ...profileQuery, enabled: cv.editable });

  const [draft, setDraft] = useState<CvDocument | null>(null);
  const [selection, setSelection] = useState<CvSelection>({ section: "profile" });
  const [saving, setSaving] = useState(false);

  // (Re)initialize the local draft when the CV is loaded or another CV is opened.
  useEffect(() => {
    setDraft(saved ? structuredClone(saved) : null);
    setSelection({ section: "profile" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cv.id, !!saved]);

  const dirty = !!saved && !!draft && JSON.stringify(draft) !== JSON.stringify(saved);

  const { proceed, reset, status } = useBlocker({
    shouldBlockFn: () => dirty,
    withResolver: true,
    enableBeforeUnload: () => dirty,
  });

  const zones = useMemo(() => layoutZones(layoutQuery.data), [layoutQuery.data]);

  if (!cv.editable)
    return (
      <ReadOnlyPreview
        cv={cv}
        reason="Ce CV a été créé avant le format modifiable (cv.json) : seul son PDF est consultable. Préparez une nouvelle candidature pour cette offre afin de pouvoir retoucher son CV."
      />
    );

  if (detail.error)
    return detail.error instanceof ApiError && detail.error.status === 409 ? (
      <ReadOnlyPreview cv={cv} reason={errorMessage(detail.error)} />
    ) : (
      <EmptyState
        icon={FileX2}
        title="Impossible de charger le CV"
        text={errorMessage(detail.error)}
        action={
          <Button variant="outline" onClick={() => void detail.refetch()}>
            <RefreshCw className="size-4" />
            Réessayer
          </Button>
        }
      />
    );

  if (!saved || !draft)
    return (
      <div className="grid gap-6 lg:grid-cols-[2fr_3fr]">
        <Skeleton className="h-[32rem] w-full rounded-xl" />
        <Skeleton className="hidden h-[32rem] w-full rounded-xl lg:block" />
      </div>
    );

  const save = async () => {
    setSaving(true);
    try {
      const result = await cvApi.updateCv(cv.id, cleanDocument(draft));
      // New summary (new updated_at => new PDF URL and new layout key), new saved document.
      qc.setQueryData(cvListQuery.queryKey, (list: CvSummary[] | undefined) =>
        list?.map((item) => (item.id === cv.id ? result.cv : item)),
      );
      qc.setQueryData(cvDetailQuery(cv.id).queryKey, (old) =>
        old ? { ...old, cv: result.cv, document: result.document } : old,
      );
      setDraft(structuredClone(result.document));
      setSelection((current) => translate(current, draft, result.document));
      void qc.invalidateQueries({ queryKey: cvListQuery.queryKey, exact: true });
      // A version longer than one page is refused by the backend (422): the previous PDF is kept.
      toast.success("CV enregistré — le PDF a été recompilé.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404)
        toast.error("Ce CV n'existe plus : il a peut-être été supprimé.");
      else toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  // The PDF shows the saved version: translate selections between saved and draft entries.
  const selectedZoneId = zoneIdFor(translate(selection, draft, saved));
  const onSelectZone = (zone: LayoutZone) =>
    setSelection(translate({ section: zone.section, index: zone.index }, saved, draft));

  const panel = (
    <CvEditorPanel
      draft={draft}
      onChange={setDraft}
      selection={selection}
      onSelect={setSelection}
      profile={profile.data}
      profileError={profile.error ? errorMessage(profile.error) : null}
    />
  );
  const preview = cv.has_pdf ? (
    <PdfPreview
      pdfUrl={cvApi.pdfUrl(cv.id, version)}
      zones={layoutQuery.isFetching ? [] : zones}
      selectedZoneId={selectedZoneId}
      onSelectZone={onSelectZone}
      busy={saving ? "Recompilation du PDF…" : null}
      note={
        dirty
          ? "Dernière version enregistrée"
          : cv.has_layout
            ? null
            : "Zones cliquables après le prochain enregistrement"
      }
    />
  ) : (
    <EmptyState
      icon={FileX2}
      title="Aucun PDF"
      text="Ce CV n'a pas de PDF compilé : enregistrez-le pour le compiler."
    />
  );

  const saveBar = (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card px-4 py-2.5 shadow-soft">
      {saving ? (
        <span className="text-xs text-muted-foreground">
          Enregistrement et recompilation en cours…
        </span>
      ) : dirty ? (
        <Badge className="bg-priority-medium font-normal text-priority-medium-foreground">
          Modifications non enregistrées
        </Badge>
      ) : (
        <span className="text-xs text-muted-foreground">
          Toutes les modifications sont enregistrées.
        </span>
      )}
      <div className="flex gap-2">
        {dirty && !saving && (
          <Button size="sm" variant="ghost" onClick={() => setDraft(structuredClone(saved))}>
            Annuler les modifications
          </Button>
        )}
        <Button size="sm" disabled={!dirty || saving} onClick={() => void save()}>
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          Enregistrer les modifications
        </Button>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      {saveBar}

      {/* Desktop: 40 / 60 split */}
      <div className="hidden gap-6 lg:grid lg:grid-cols-[2fr_3fr]">
        <div className="h-[calc(100vh-17rem)] min-h-[28rem]">{panel}</div>
        <div className="h-[calc(100vh-17rem)] min-h-[28rem]">{preview}</div>
      </div>

      {/* Mobile / tablet: stacked with tabs */}
      <Tabs defaultValue="edition" className="lg:hidden">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="edition">Édition</TabsTrigger>
          <TabsTrigger value="apercu">Aperçu</TabsTrigger>
        </TabsList>
        <TabsContent value="edition" className="mt-4">
          <div className="h-[32rem]">{panel}</div>
        </TabsContent>
        <TabsContent value="apercu" className="mt-4">
          <div className="h-[32rem]">{preview}</div>
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={status === "blocked"}
        onOpenChange={(open) => {
          if (!open) reset?.();
        }}
        title="Modifications non enregistrées"
        description="Vous avez modifié ce CV sans enregistrer. Si vous quittez maintenant, vos changements seront perdus."
        confirmLabel="Quitter sans enregistrer"
        onConfirm={() => proceed?.()}
      />
    </div>
  );
}
