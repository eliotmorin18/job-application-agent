// « Vérifier » mode of the CV tab: are the important points of the offer visible in the CV? Display only,
// computed locally from analysis.json and the CV being edited (adapters.cvChecks): no Claude call, no
// score, nothing written. Clicking a point highlights its section in the PDF; editing stays explicit.

import { useQuery } from "@tanstack/react-query";
import { useId } from "react";
import { AlertTriangle, Info, Loader2, MapPin, Pencil } from "lucide-react";

import { badgeVariants } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { CvDocument, CvSummary } from "@/services/api/cvTypes";
import { cvChecks, type CvCheck, type CvCheckState, type CvLocation } from "../adapters";
import { cvAnalysisQuery, errorMessage } from "../hooks";

const STATE_LABELS: Record<CvCheckState, string> = {
  present: "Présent",
  uncertain: "À vérifier",
  absent: "Non mentionné",
};

const STATE_CLASSES: Record<CvCheckState, string> = {
  present: "bg-accent text-accent-foreground",
  uncertain: "bg-priority-medium text-priority-medium-foreground",
  absent: "bg-muted text-muted-foreground",
};

/** Stable key of a location (checks are recomputed at each render). */
const locationKey = (l: CvLocation) =>
  `${l.selection.section}/${l.selection.index ?? ""}/${l.label}`;

/** What the point is focused on: the check and one of its CV locations. */
export interface CheckFocus {
  id: string;
  location: CvLocation | null;
}

function summaryLine(check: CvCheck): string {
  if (check.state === "absent") return "Ton profil le documente, mais le CV ne le mentionne pas.";
  if (check.terms.length === 0)
    return "Un élément cité par l'analyse figure dans le CV, sans les termes de l'offre.";
  return `Trouvé : ${check.terms.join(", ")}`;
}

function CheckItem({
  check,
  focus,
  hasZone,
  onFocus,
  onEdit,
}: {
  check: CvCheck;
  focus: CheckFocus | null;
  hasZone: (location: CvLocation) => boolean;
  /** null closes the open point (and its highlight in the PDF). */
  onFocus: (focus: CheckFocus | null) => void;
  onEdit: (location: CvLocation) => void;
}) {
  const detailId = useId();
  const selected = focus?.id === check.id;
  const location = selected ? focus.location : null;
  return (
    <li className="py-1">
      <button
        type="button"
        aria-expanded={selected}
        aria-controls={detailId}
        // Accordion: a second click closes the point; another point replaces it
        onClick={() =>
          onFocus(selected ? null : { id: check.id, location: check.locations[0] ?? null })
        }
        className={cn(
          "w-full rounded-md px-2.5 py-2 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
          selected && "bg-muted/50",
        )}
      >
        <span className="flex items-start justify-between gap-3">
          <span className="line-clamp-2 text-sm font-medium">{check.text}</span>
          <span
            className={cn(
              badgeVariants({ variant: "outline" }),
              "shrink-0 border-transparent font-normal",
              STATE_CLASSES[check.state],
            )}
          >
            {STATE_LABELS[check.state]}
          </span>
        </span>
        <span className="mt-0.5 block text-xs text-muted-foreground">{summaryLine(check)}</span>
        {check.missing.length > 0 && (
          <span className="block text-xs text-muted-foreground">
            Non trouvé : {check.missing.join(", ")}
          </span>
        )}
      </button>

      {selected && (
        <div id={detailId} className="space-y-1.5 px-2.5 pb-1 pt-1 text-xs">
          {check.locations.length > 0 ? (
            <ul className="flex flex-wrap gap-1">
              {check.locations.map((l) => (
                <li key={locationKey(l)}>
                  <button
                    type="button"
                    aria-pressed={!!location && locationKey(location) === locationKey(l)}
                    onClick={() => onFocus({ id: check.id, location: l })}
                    className={cn(
                      "rounded-md border px-2 py-0.5 transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
                      location &&
                        locationKey(location) === locationKey(l) &&
                        "border-primary/50 bg-accent/40",
                    )}
                  >
                    {l.label}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {location && hasZone(location) ? (
            <p className="flex items-center gap-1.5 text-muted-foreground">
              <MapPin className="size-3.5 shrink-0" />
              Section surlignée dans l'aperçu (l'emplacement de la section, pas du mot).
            </p>
          ) : (
            <p className="flex items-center gap-1.5 text-muted-foreground">
              <MapPin className="size-3.5 shrink-0" />
              Emplacement non identifié dans l'aperçu.
            </p>
          )}
          {location && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => onEdit(location)}
            >
              <Pencil className="size-3.5" />
              Modifier cette section
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

export function CvCheckPanel({
  cv,
  draft,
  dirty,
  focus,
  hasZone,
  onFocus,
  onEdit,
}: {
  cv: CvSummary;
  /** The CV being edited: the check follows unsaved changes too. */
  draft: CvDocument;
  dirty: boolean;
  focus: CheckFocus | null;
  hasZone: (location: CvLocation) => boolean;
  onFocus: (focus: CheckFocus | null) => void;
  onEdit: (location: CvLocation) => void;
}) {
  // The saved analysis is read (same cache as « Vue d'ensemble »); it is never started from here.
  const { data: analysis, isLoading, error } = useQuery(cvAnalysisQuery(cv.id));

  let body;
  if (isLoading)
    body = (
      <div className="space-y-2 p-3">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  else if (error)
    body = (
      <p className="flex items-start gap-2 p-4 text-sm text-muted-foreground">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
        {errorMessage(error)}
      </p>
    );
  else if (analysis?.running)
    body = (
      <p className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Analyse de l'offre en cours : la vérification sera disponible ensuite.
      </p>
    );
  else if (!analysis || analysis.status !== "completed")
    body = (
      <p className="p-4 text-sm text-muted-foreground">
        La vérification s'appuie sur l'analyse de l'offre, qui n'est pas disponible pour cette
        candidature. Lance-la depuis l'onglet « Vue d'ensemble ».
      </p>
    );
  else {
    const checks = cvChecks(analysis, draft);
    body =
      checks.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">
          Aucun point de l'offre à vérifier : l'analyse ne relie aucune exigence à ton profil.
        </p>
      ) : (
        <ul className="divide-y px-1.5 py-1">
          {checks.map((check) => (
            <CheckItem
              key={check.id}
              check={check}
              focus={focus}
              hasZone={hasZone}
              onFocus={onFocus}
              onEdit={onEdit}
            />
          ))}
        </ul>
      );
  }

  return (
    <section
      aria-label="Vérifier le CV"
      className="flex h-full flex-col rounded-xl border bg-card shadow-soft"
    >
      <div className="space-y-1 border-b px-4 py-2.5">
        <h3 className="text-sm font-semibold">Ce que l'offre recherche, dans ton CV</h3>
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <Info className="mt-0.5 size-3.5 shrink-0" />
          Les termes de l'offre sont recherchés tels quels dans le CV. « Non mentionné » ne veut pas
          dire que la compétence manque à ton profil.
        </p>
        {dirty && (
          <p className="text-xs text-muted-foreground">
            Vérification de la version en cours de modification ; l'aperçu montre la dernière
            version enregistrée.
          </p>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">{body}</div>
    </section>
  );
}
