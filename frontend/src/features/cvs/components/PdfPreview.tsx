import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  FileText,
  Loader2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { LayoutZone } from "../adapters";
import "./pdfTextLayer.css";

const ZONE_LABELS: Record<string, string> = {
  profile: "le profil",
  experiences: "les expériences",
  education: "la formation",
  projects: "les projets",
  skills: "les compétences et langues",
  interests: "les centres d'intérêt",
};

function zoneLabel(zone: LayoutZone): string {
  const label = ZONE_LABELS[zone.section] ?? zone.section;
  return zone.index !== undefined
    ? `Sélectionner l'élément ${zone.index + 1} dans ${label}`
    : `Sélectionner ${label}`;
}

const MIN_SCALE = 0.6;
const MAX_SCALE = 2;
const SCALE_STEP = 0.15;
/** Largest zoom chosen automatically when the page is fitted to the width of the preview. */
const MAX_FIT_SCALE = 1.5;
/** Horizontal padding of the scroll area (p-4 on both sides). */
const PREVIEW_PADDING = 32;

function PdfPageView({
  doc,
  pageNumber,
  scale,
  zones,
  selectedZoneId,
  onSelectZone,
  pageRef,
  textSelectable,
}: {
  doc: PDFDocumentProxy;
  pageNumber: number;
  scale: number;
  zones: LayoutZone[];
  selectedZoneId: string | null;
  onSelectZone: (zone: LayoutZone) => void;
  pageRef: (el: HTMLDivElement | null) => void;
  textSelectable: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);

  // Selectable text (pdf.js TextLayer) over the canvas, only when asked: no zone is shown then.
  useEffect(() => {
    const container = textRef.current;
    if (!textSelectable || !container) return;
    let cancelled = false;
    let layer: { cancel: () => void } | null = null;
    (async () => {
      const [{ TextLayer }, page] = await Promise.all([
        import("pdfjs-dist"),
        doc.getPage(pageNumber),
      ]);
      if (cancelled) return;
      container.replaceChildren();
      const textLayer = new TextLayer({
        textContentSource: page.streamTextContent(),
        container,
        viewport: page.getViewport({ scale }),
      });
      layer = textLayer;
      await textLayer.render();
    })().catch(() => {
      // a cancelled or replaced rendering: the canvas is still shown, only the selection is missing
    });
    return () => {
      cancelled = true;
      layer?.cancel();
    };
  }, [doc, pageNumber, scale, textSelectable]);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let renderTask: { cancel: () => void; promise: Promise<unknown> } | null = null;
    (async () => {
      const page = await doc.getPage(pageNumber);
      const dpr = window.devicePixelRatio || 1;
      const viewport = page.getViewport({ scale: scale * dpr });
      const canvas = canvasRef.current;
      if (!canvas || cancelled) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      canvas.style.width = `${viewport.width / dpr}px`;
      canvas.style.height = `${viewport.height / dpr}px`;
      setSize({ w: viewport.width / dpr, h: viewport.height / dpr });
      renderTask = page.render({ canvas, canvasContext: canvas.getContext("2d")!, viewport });
      try {
        await renderTask.promise;
      } catch {
        // cancelled renders throw — safe to ignore
      }
    })().catch(() => {
      // the document was replaced by a newer version (destroyed) while this page was loading
    });
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [doc, pageNumber, scale]);

  return (
    <div
      ref={pageRef}
      className="relative mx-auto bg-white shadow-lift"
      style={
        {
          width: size?.w,
          height: size?.h,
          // Read by the text layer (pdf.js): CSS pixels per PDF point, no rounding
          "--total-scale-factor": scale,
          "--scale-round-x": "1px",
          "--scale-round-y": "1px",
        } as CSSProperties
      }
    >
      <canvas ref={canvasRef} className="block" />
      {textSelectable && (
        <div ref={textRef} className="cv-pdf-text-layer" data-testid="pdf-text-layer" />
      )}
      {size &&
        zones.map((zone, index) => {
          const selected = zone.id === selectedZoneId;
          return (
            <button
              // Une section peut avoir plusieurs zones (titre, contenu, pages) avec le même id
              key={`${zone.id}-${zone.page}-${index}`}
              type="button"
              aria-label={zoneLabel(zone)}
              data-zone={zone.id}
              onClick={() => onSelectZone(zone)}
              // Light marks: an outline and a faint tint, so the text underneath stays readable
              className={`absolute rounded-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 ${
                selected
                  ? "bg-primary/5 ring-2 ring-primary/60"
                  : "hover:bg-primary/5 hover:ring-1 hover:ring-primary/30"
              }`}
              style={{
                left: `${zone.x * 100}%`,
                top: `${zone.y * 100}%`,
                width: `${zone.width * 100}%`,
                height: `${zone.height * 100}%`,
              }}
            />
          );
        })}
    </div>
  );
}

/**
 * Renders the compiled PDF with pdf.js and the clickable zones of layout.json on top. Zones are positioned in
 * percentages of each page, so they follow zoom and scroll. A new `pdfUrl` (new version) clears the previous
 * rendering first: an old PDF is never shown as the current one.
 */
export function PdfPreview({
  pdfUrl,
  zones,
  selectedZoneId,
  onSelectZone,
  busy = null,
  note = null,
  textSelectable = false,
}: {
  pdfUrl: string;
  zones: LayoutZone[];
  selectedZoneId: string | null;
  onSelectZone: (zone: LayoutZone) => void;
  /** Shown over the preview while the PDF is being recompiled. */
  busy?: string | null;
  /** Shown in the toolbar (e.g. "Dernière version enregistrée" when the draft differs). */
  note?: string | null;
  /** Reader mode: selectable, copyable text and no clickable zone (« Assistant IA »). */
  textSelectable?: boolean;
}) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  // The page is fitted to the width of the preview (on load, and when the preview is resized) until
  // the user zooms: from then on the scale is the user's and is kept, also for a new version.
  const userZoomed = useRef(false);
  const pageWidth = useRef(0);

  const fitToWidth = useCallback(() => {
    const available = (scrollRef.current?.clientWidth ?? 0) - PREVIEW_PADDING;
    if (userZoomed.current || !pageWidth.current || available <= 0) return;
    setScale(
      Math.min(MAX_FIT_SCALE, Math.max(MIN_SCALE, +(available / pageWidth.current).toFixed(2))),
    );
  }, []);

  // Resizing the preview (split handle, window) refits the page, once the size has settled.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const observer = new ResizeObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(fitToWidth, 120);
    });
    observer.observe(el);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
    };
  }, [fitToWidth]);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: { destroy: () => Promise<void> } | null = null;
    setDoc(null);
    setLoadError(null);
    setCurrentPage(1);
    (async () => {
      // pdfjs-dist v6 relies on Map.prototype.getOrInsertComputed (very recent).
      type GetOrInsert = (key: unknown, fn: (k: unknown) => unknown) => unknown;
      const proto = Map.prototype as unknown as { getOrInsertComputed?: GetOrInsert };
      if (!proto.getOrInsertComputed) {
        proto.getOrInsertComputed = function (this: Map<unknown, unknown>, key, fn) {
          if (!this.has(key)) this.set(key, fn(key));
          return this.get(key);
        };
      }
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
      if (cancelled) return;
      const task = pdfjs.getDocument({ url: pdfUrl });
      loadingTask = task;
      const loaded = await task.promise;
      if (cancelled) return;
      if (!pageWidth.current) {
        const page = await loaded.getPage(1);
        if (cancelled) return;
        pageWidth.current = page.getViewport({ scale: 1 }).width;
      }
      fitToWidth();
      setDoc(loaded);
    })().catch((error: unknown) => {
      if (cancelled) return;
      const status = (error as { status?: number } | null)?.status;
      setLoadError(
        status === 404
          ? "Le PDF de ce CV est introuvable."
          : "Impossible d'afficher le PDF. Vérifiez que l'API locale est lancée, puis rechargez la page.",
      );
    });
    return () => {
      cancelled = true;
      void loadingTask?.destroy(); // frees the worker document of this version
    };
  }, [pdfUrl, fitToWidth]);

  const pageCount = doc?.numPages ?? 0;

  // A selection made in the editor brings its zone into view.
  useEffect(() => {
    if (!doc || !selectedZoneId) return;
    const target = scrollRef.current?.querySelector(`[data-zone="${CSS.escape(selectedZoneId)}"]`);
    target?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [doc, selectedZoneId]);

  const goToPage = (n: number) => {
    const target = Math.min(Math.max(n, 1), pageCount);
    setCurrentPage(target);
    pageRefs.current[target - 1]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border bg-card shadow-soft">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <span className="flex min-w-0 items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <FileText className="size-3.5 shrink-0" />
          <span className="truncate">Aperçu PDF{note ? ` · ${note}` : ""}</span>
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            aria-label="Zoom arrière"
            disabled={scale <= MIN_SCALE}
            onClick={() => {
              userZoomed.current = true;
              setScale((s) => Math.max(MIN_SCALE, +(s - SCALE_STEP).toFixed(2)));
            }}
          >
            <ZoomOut className="size-3.5" />
          </Button>
          <span className="w-11 text-center text-xs tabular-nums text-muted-foreground">
            {Math.round(scale * 100)} %
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            aria-label="Zoom avant"
            disabled={scale >= MAX_SCALE}
            onClick={() => {
              userZoomed.current = true;
              setScale((s) => Math.min(MAX_SCALE, +(s + SCALE_STEP).toFixed(2)));
            }}
          >
            <ZoomIn className="size-3.5" />
          </Button>
          <span className="mx-1 h-4 w-px bg-border" />
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            aria-label="Page précédente"
            disabled={currentPage <= 1}
            onClick={() => goToPage(currentPage - 1)}
          >
            <ChevronLeft className="size-3.5" />
          </Button>
          <span className="text-xs tabular-nums text-muted-foreground">
            {currentPage} / {pageCount || "…"}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            aria-label="Page suivante"
            disabled={currentPage >= pageCount}
            onClick={() => goToPage(currentPage + 1)}
          >
            <ChevronRight className="size-3.5" />
          </Button>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        <div ref={scrollRef} className="h-full overflow-auto bg-muted/40 p-4">
          {loadError ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
              <AlertTriangle className="size-5 text-destructive" />
              <p className="max-w-xs">{loadError}</p>
            </div>
          ) : !doc ? (
            <Skeleton className="mx-auto aspect-[1/1.414] w-full max-w-lg rounded-none" />
          ) : (
            <div className="space-y-4">
              {Array.from({ length: pageCount }, (_, i) => (
                <PdfPageView
                  key={i + 1}
                  doc={doc}
                  pageNumber={i + 1}
                  scale={scale}
                  zones={busy || textSelectable ? [] : zones.filter((z) => z.page === i + 1)}
                  textSelectable={textSelectable}
                  selectedZoneId={selectedZoneId}
                  onSelectZone={onSelectZone}
                  pageRef={(el) => {
                    pageRefs.current[i] = el;
                  }}
                />
              ))}
            </div>
          )}
        </div>
        {busy && (
          <div className="absolute inset-0 flex items-start justify-center bg-background/60 pt-16 backdrop-blur-[1px]">
            <span className="flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-xs font-medium shadow-soft">
              <Loader2 className="size-3.5 animate-spin" />
              {busy}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
