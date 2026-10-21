// Manual corrections of extracted values. They only live in the page state and are sent
// as `overrides` when the user applies the import (never saved before).

import { AlertTriangle, Check, Pencil, Undo2 } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ListEditor, TagInput } from "../candidate/components/common";
import { sectionConfig, type FieldType } from "../candidate/sectionConfig";
import type { CorrectedValue, ItemSectionKey } from "./decisions";
import { Value } from "./parts";

/** Editor type of a field, from the Lovable form definitions (personal fields are plain text). */
export function fieldType(section: ItemSectionKey | "personal", field: string): FieldType {
  if (section === "personal") return "text";
  return sectionConfig[section].fields.find((f) => f.key === field)?.type ?? "text";
}

const asList = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : v ? [String(v)] : []);
const asText = (v: unknown): string =>
  Array.isArray(v) ? v.join(", ") : v == null ? "" : String(v);

export function CorrectedBadge() {
  return (
    <Badge className="border-0 bg-primary/10 font-medium text-primary shadow-none">Corrigé</Badge>
  );
}

function Editor({
  type,
  value,
  onChange,
  placeholder,
}: {
  type: FieldType;
  value: CorrectedValue;
  onChange: (v: CorrectedValue) => void;
  placeholder?: string | undefined;
}) {
  if (type === "list") return <ListEditor value={asList(value)} onChange={onChange} />;
  if (type === "tags")
    return <TagInput value={asList(value)} onChange={onChange} placeholder="Ajouter puis Entrée" />;
  if (type === "textarea")
    return <Textarea rows={3} value={asText(value)} onChange={(e) => onChange(e.target.value)} />;
  return (
    <Input
      className="h-8"
      value={asText(value)}
      placeholder={placeholder ?? (type === "date" ? "AAAA ou AAAA-MM" : undefined)}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

/**
 * An extracted value with a « Corriger » action. Editing writes the correction in the page
 * state (`onChange`); « Annuler la correction » goes back to the extracted value.
 */
export function CorrectableValue({
  type,
  extracted,
  correction,
  onChange,
  onReset,
  display,
}: {
  type: FieldType;
  extracted: unknown;
  correction: CorrectedValue | undefined;
  onChange: (v: CorrectedValue) => void;
  onReset: () => void;
  display?: ReactNode | undefined; // custom display of the extracted value
}) {
  const [editing, setEditing] = useState(false);
  const corrected = correction !== undefined;
  const isList = type === "list" || type === "tags";

  if (editing)
    return (
      <div className="space-y-2">
        <Editor
          type={type}
          value={correction ?? (isList ? asList(extracted) : asText(extracted))}
          onChange={onChange}
        />
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7"
          onClick={() => setEditing(false)}
        >
          <Check className="size-3.5" />
          Terminer
        </Button>
      </div>
    );

  return (
    <div className="group flex items-start justify-between gap-2">
      <div className="min-w-0">
        {corrected ? <Value value={correction} /> : (display ?? <Value value={extracted} />)}
        {corrected && (
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <CorrectedBadge />
            <span className="line-through decoration-muted-foreground/50">
              {asText(extracted) || "—"}
            </span>
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center">
        {corrected && (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="size-7 text-muted-foreground"
            aria-label="Annuler la correction"
            title="Annuler la correction"
            onClick={onReset}
          >
            <Undo2 className="size-3.5" />
          </Button>
        )}
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="size-7 text-muted-foreground opacity-60 group-hover:opacity-100"
          aria-label="Corriger"
          title="Corriger"
          onClick={() => setEditing(true)}
        >
          <Pencil className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}

/** Inline correction of a name (skill, language, interest). */
export function CorrectableName({
  extracted,
  correction,
  onChange,
  onReset,
}: {
  extracted: string;
  correction: string | null;
  onChange: (v: string) => void;
  onReset: () => void;
}) {
  const [editing, setEditing] = useState(false);
  if (editing)
    return (
      <span className="inline-flex items-center gap-1">
        <Input
          autoFocus
          className="h-7 w-44 text-sm"
          value={correction ?? extracted}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => (e.key === "Enter" || e.key === "Escape") && setEditing(false)}
        />
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="size-7"
          aria-label="Terminer"
          onClick={() => setEditing(false)}
        >
          <Check className="size-3.5" />
        </Button>
      </span>
    );
  const corrected = correction !== null && correction !== extracted;
  return (
    <span className="group inline-flex items-center gap-1.5">
      <span className="text-sm font-medium">{corrected ? correction : extracted}</span>
      {corrected && (
        <>
          <span className="text-xs text-muted-foreground line-through">{extracted}</span>
          <CorrectedBadge />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="size-6 text-muted-foreground"
            aria-label="Annuler la correction"
            title="Annuler la correction"
            onClick={onReset}
          >
            <Undo2 className="size-3" />
          </Button>
        </>
      )}
      <Button
        type="button"
        size="icon"
        variant="ghost"
        className="size-6 text-muted-foreground opacity-60 group-hover:opacity-100"
        aria-label="Corriger"
        title="Corriger"
        onClick={() => setEditing(true)}
      >
        <Pencil className="size-3" />
      </Button>
    </span>
  );
}

/** The duplicate status was computed on the extracted value: after a correction it may be wrong. */
export function StatusMayChange({ what }: { what: string }) {
  return (
    <p className="mt-2 flex items-start gap-2 rounded-lg border border-amber-300/60 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
      <span>
        Le statut de doublon a été calculé avant ta correction ({what}) : il n'est peut-être plus
        exact. Vérifie que cet élément n'est pas déjà dans ton profil. Un nom identique à un élément
        existant sera refusé à l'enregistrement sans ta confirmation.
      </span>
    </p>
  );
}
