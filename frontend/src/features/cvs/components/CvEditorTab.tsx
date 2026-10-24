import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useBlocker } from "@tanstack/react-router";
import {
  Check,
  FileX2,
  ListChecks,
  Loader2,
  Lock,
  MessageSquare,
  Pencil,
  RefreshCw,
  Save,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ConfirmDialog, EmptyState } from "@/features/candidate/components/common";
import { profileQuery } from "@/features/candidate/hooks";
import { ApiError, cvApi } from "@/services/api/cvApi";
import type { CvDocument, CvSummary, CvUpdateResult } from "@/services/api/cvTypes";
import {
  EDITOR_MAX_PERCENT,
  cleanDocument,
  editorMinPercent,
  layoutZones,
  zoneIdFor,
  type CvLocation,
  type CvSelection,
  type ItemSection,
  type LayoutZone,
} from "../adapters";
import { cvDetailQuery, cvLayoutQuery, cvListQuery, errorMessage } from "../hooks";
import { CvAssistantPanel } from "./CvAssistantPanel";
import { CvCheckPanel, type CheckFocus } from "./CvCheckPanel";
import { CvEditorPanel } from "./CvEditorPanel";
import { PdfPreview } from "./PdfPreview";

/** Minimum size of the editor panel (percent of the split) for the measured width of the split. */
function useEditorMinSize(group: HTMLDivElement | null): number {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!group || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setWidth(group.offsetWidth));
    observer.observe(group);
    return () => observer.disconnect();
  }, [group]);
  return editorMinPercent(width);
}

/** Left panel: « Modifier » (editor), « Vérifier » (check of the offer's points), « Assistant IA ». */
type Mode = "edit" | "check" | "assistant";

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
  // Left panel: the editor (« Modifier », default) or the check of the offer's points (« Vérifier »).
  // The draft lives here: switching never loses unsaved changes.
  const [mode, setMode] = useState<Mode>("edit");
  // The assistant is mounted the first time it is opened, then kept (typed text, scroll).
  const [assistantOpened, setAssistantOpened] = useState(false);
  const [checkFocus, setCheckFocus] = useState<CheckFocus | null>(null);
  const [splitGroup, setSplitGroup] = useState<HTMLDivElement | null>(null);
  const editorMinSize = useEditorMinSize(splitGroup);

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
      <div className="grid gap-5 lg:grid-cols-2">
        <Skeleton className="h-[32rem] w-full rounded-xl" />
        <Skeleton className="hidden h-[32rem] w-full rounded-xl lg:block" />
      </div>
    );

  /** A saved version (editor or assistant): new summary (new PDF URL and layout key), new document. */
  const applySaved = (result: CvUpdateResult, from: CvDocument) => {
    qc.setQueryData(cvListQuery.queryKey, (list: CvSummary[] | undefined) =>
      list?.map((item) => (item.id === cv.id ? result.cv : item)),
    );
    qc.setQueryData(cvDetailQuery(cv.id).queryKey, (old) =>
      old ? { ...old, cv: result.cv, document: result.document } : old,
    );
    setDraft(structuredClone(result.document));
    setSelection((current) => translate(current, from, result.document));
    void qc.invalidateQueries({ queryKey: cvListQuery.queryKey, exact: true });
  };

  const save = async () => {
    setSaving(true);
    try {
      const result = await cvApi.updateCv(cv.id, cleanDocument(draft));
      applySaved(result, draft);
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
  const zoneOf = (s: CvSelection) => zoneIdFor(translate(s, draft, saved));
  const editorZoneId = zoneOf(selection);
  // A location of the check is highlighted only when its zone exists in layout.json (else nothing).
  const hasZone = (location: CvLocation) =>
    zones.some((zone) => zone.id === zoneOf(location.selection));
  const checkZoneId =
    checkFocus?.location && hasZone(checkFocus.location)
      ? zoneOf(checkFocus.location.selection)
      : null;
  // « Assistant IA »: the PDF is a plain reader (selectable text to copy into the chat), no zone.
  const reader = mode === "assistant";
  const selectedZoneId = reader ? null : mode === "check" ? checkZoneId : editorZoneId;
  // PDF → editor in both modes: a click on a zone opens that part in the editor.
  const onSelectZone = (zone: LayoutZone) => {
    setMode("edit");
    setSelection(translate({ section: zone.section, index: zone.index }, saved, draft));
  };
  // « Modifier cette section »: back to the editor on that part (nothing is changed in the CV).
  const editLocation = (location: CvLocation) => {
    setSelection(location.selection);
    setMode("edit");
  };

  // Save controls at the top of the editor (they stay visible while the fields scroll): the state,
  // discreet, next to the button.
  const saveBar = (
    <div className="flex items-center justify-end gap-2 border-b px-3 py-2">
      <span
        role="status"
        className="mr-auto flex min-w-0 items-center gap-1.5 truncate text-xs text-muted-foreground"
      >
        {saving ? (
          <>
            <Loader2 className="size-3.5 shrink-0 animate-spin" />
            Enregistrement et recompilation…
          </>
        ) : dirty ? (
          <>
            <span className="size-2 shrink-0 rounded-full bg-priority-medium-foreground" />
            Modifications non enregistrées
          </>
        ) : (
          <>
            <Check className="size-3.5 shrink-0" />
            Enregistré
          </>
        )}
      </span>
      {dirty && !saving && (
        <Button
          size="sm"
          variant="ghost"
          className="h-8 shrink-0"
          onClick={() => setDraft(structuredClone(saved))}
        >
          Annuler
        </Button>
      )}
      <Button
        size="sm"
        className="h-8 shrink-0"
        disabled={!dirty || saving}
        onClick={() => void save()}
      >
        {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
        Enregistrer
      </Button>
    </div>
  );

  const panel = (
    <CvEditorPanel
      draft={draft}
      onChange={setDraft}
      selection={selection}
      onSelect={setSelection}
      profile={profile.data}
      profileError={profile.error ? errorMessage(profile.error) : null}
      toolbar={saveBar}
    />
  );
  const preview = cv.has_pdf ? (
    <PdfPreview
      pdfUrl={cvApi.pdfUrl(cv.id, version)}
      zones={layoutQuery.isFetching || reader ? [] : zones}
      selectedZoneId={selectedZoneId}
      onSelectZone={reader ? () => undefined : onSelectZone}
      textSelectable={reader}
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

  const modeSwitch = (
    <ToggleGroup
      type="single"
      size="sm"
      variant="outline"
      value={mode}
      onValueChange={(value) => {
        if (!value) return;
        setMode(value as Mode);
        if (value === "assistant") setAssistantOpened(true);
      }}
      aria-label="Contenu du panneau gauche"
      className="justify-start"
    >
      <ToggleGroupItem value="edit" className="h-7 gap-1.5 px-2.5 text-xs">
        <Pencil className="size-3.5" />
        Modifier
      </ToggleGroupItem>
      <ToggleGroupItem value="check" className="h-7 gap-1.5 px-2.5 text-xs">
        <ListChecks className="size-3.5" />
        Vérifier
      </ToggleGroupItem>
      <ToggleGroupItem value="assistant" className="h-7 gap-1.5 px-2.5 text-xs">
        <MessageSquare className="size-3.5" />
        Assistant IA
      </ToggleGroupItem>
    </ToggleGroup>
  );

  // The editor stays mounted (hidden) in « Vérifier »: its scroll and local state are kept too.
  const left = (
    <div className="flex h-full flex-col gap-2">
      {modeSwitch}
      <div className="min-h-0 flex-1">
        <div hidden={mode !== "edit"} className="h-full">
          {panel}
        </div>
        {mode === "check" && (
          <CvCheckPanel
            cv={cv}
            draft={draft}
            dirty={dirty}
            focus={checkFocus}
            hasZone={hasZone}
            onFocus={setCheckFocus}
            onEdit={editLocation}
          />
        )}
        {assistantOpened && (
          <div hidden={mode !== "assistant"} className="h-full">
            <CvAssistantPanel
              cv={cv}
              dirty={dirty}
              onSaved={(result) => {
                applySaved(result, saved);
                toast.success("CV enregistré par l'assistant — le PDF a été recompilé.");
              }}
            />
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div>
      {/* Desktop: editor / PDF split that the user can drag (mouse, touch, or the keyboard on the
          handle; a double-click resets it to 40 / 60) */}
      <div className="hidden h-[calc(100vh-14rem)] min-h-[28rem] lg:block">
        <ResizablePanelGroup orientation="horizontal" elementRef={setSplitGroup}>
          <ResizablePanel
            id="cv-editor"
            defaultSize="40"
            minSize={String(editorMinSize)}
            maxSize={String(EDITOR_MAX_PERCENT)}
          >
            {left}
          </ResizablePanel>
          <ResizableHandle
            withHandle
            aria-label="Redimensionner l'éditeur et l'aperçu"
            title="Glisser pour redimensionner · double-clic pour revenir à 40 / 60"
            className="mx-2 bg-transparent transition-colors hover:bg-border data-[separator=hover]:bg-border data-[separator=active]:bg-primary/40 [&>div]:opacity-60 [&>div]:transition-opacity hover:[&>div]:opacity-100"
          />
          <ResizablePanel id="cv-preview" defaultSize="60" minSize="35">
            {preview}
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {/* Mobile / tablet: stacked with tabs */}
      <Tabs defaultValue="edition" className="lg:hidden">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="edition">Édition</TabsTrigger>
          <TabsTrigger value="apercu">Aperçu</TabsTrigger>
        </TabsList>
        <TabsContent value="edition" className="mt-4">
          <div className="h-[36rem]">{left}</div>
        </TabsContent>
        <TabsContent value="apercu" className="mt-4">
          <div className="h-[36rem]">{preview}</div>
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
