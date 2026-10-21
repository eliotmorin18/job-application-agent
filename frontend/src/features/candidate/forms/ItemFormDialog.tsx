import { useEffect, useState, type FormEvent } from "react";

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
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { ItemSection, SectionItem } from "@/services/api/types";
import { ListEditor, TagInput } from "../components/common";
import { DATE_PATTERN, PRIORITY_LABELS } from "../format";
import { sectionConfig, type FieldDef } from "../sectionConfig";

type Values = Record<string, string | string[] | undefined>;

function toValues(fields: FieldDef[], item?: SectionItem): Values {
  const src = (item ?? {}) as Record<string, unknown>;
  const v: Values = {};
  for (const f of fields) {
    const raw = src[f.key];
    v[f.key] = f.type === "list" || f.type === "tags" ? [...((raw as string[]) ?? [])] : ((raw as string) ?? "");
  }
  return v;
}

/** Trims values; empty strings / lists become undefined (field absent). */
function clean(fields: FieldDef[], values: Values) {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const raw = values[f.key];
    if (Array.isArray(raw)) {
      const arr = raw.map((s) => s.trim()).filter(Boolean);
      out[f.key] = arr.length ? arr : undefined;
    } else {
      const s = (raw ?? "").trim();
      out[f.key] = s || undefined;
    }
  }
  return out;
}

function validate(fields: FieldDef[], values: Values) {
  const errors: Record<string, string> = {};
  for (const f of fields) {
    const raw = values[f.key];
    const s = typeof raw === "string" ? raw.trim() : "";
    if (f.required && !s) errors[f.key] = "Ce champ est obligatoire.";
    if (f.type === "date" && s && !DATE_PATTERN.test(s)) errors[f.key] = "Format attendu : AAAA ou AAAA-MM.";
    if (f.type === "url" && s && !/^https?:\/\//.test(s)) errors[f.key] = "L'adresse doit commencer par https://";
  }
  const start = values["start_date"] as string, end = values["end_date"] as string;
  if (start && end && DATE_PATTERN.test(start) && DATE_PATTERN.test(end)) {
    const n = Math.min(start.length, end.length);
    if (end.slice(0, n) < start.slice(0, n)) errors["end_date"] = "La date de fin précède la date de début.";
  }
  return errors;
}

const FULL_WIDTH = new Set(["textarea", "list", "tags", "url"]);

export function ItemFormDialog({
  section,
  open,
  onOpenChange,
  item,
  onSubmit,
}: {
  section: ItemSection;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  item?: SectionItem | undefined;
  onSubmit: (data: Record<string, unknown>) => Promise<boolean>;
}) {
  const config = sectionConfig[section];
  const [values, setValues] = useState<Values>(() => toValues(config.fields, item));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setValues(toValues(config.fields, item));
      setErrors({});
    }
  }, [open, item, config.fields]);

  const set = (key: string, v: string | string[]) => {
    setValues((prev) => ({ ...prev, [key]: v }));
    if (errors[key]) setErrors(({ [key]: _, ...rest }) => rest);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const errs = validate(config.fields, values);
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSaving(true);
    const ok = await onSubmit(clean(config.fields, values));
    setSaving(false);
    if (ok) onOpenChange(false);
  };

  const isEdit = Boolean(item);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] flex-col gap-0 p-0 sm:max-w-2xl">
        <DialogHeader className="border-b px-6 py-5">
          <DialogTitle>{isEdit ? `Modifier : ${config.label.toLowerCase().replace(/s$/, "")}` : config.addLabel}</DialogTitle>
          <DialogDescription>
            Les champs marqués d'un astérisque sont obligatoires. Les autres peuvent être complétés plus tard.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <div className="grid flex-1 grid-cols-1 gap-x-4 gap-y-5 overflow-y-auto px-6 py-5 sm:grid-cols-2">
            {config.fields.map((f) => {
              const id = `field-${f.key}`;
              const val = values[f.key];
              return (
                <div key={f.key} className={FULL_WIDTH.has(f.type) ? "sm:col-span-2" : undefined}>
                  <Label htmlFor={id} className="mb-1.5 block text-xs font-medium text-muted-foreground">
                    {f.label}
                    {f.required && <span className="text-destructive"> *</span>}
                  </Label>
                  {f.type === "textarea" ? (
                    <Textarea id={id} rows={3} value={val as string} placeholder={f.placeholder} onChange={(e) => set(f.key, e.target.value)} />
                  ) : f.type === "list" ? (
                    <ListEditor value={val as string[]} onChange={(v) => set(f.key, v)} placeholder={f.placeholder} />
                  ) : f.type === "tags" ? (
                    <TagInput id={id} value={val as string[]} onChange={(v) => set(f.key, v)} placeholder={f.placeholder} />
                  ) : f.type === "priority" ? (
                    <Select value={(val as string) || "none"} onValueChange={(v) => set(f.key, v === "none" ? "" : v)}>
                      <SelectTrigger id={id}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">Non définie</SelectItem>
                        {Object.entries(PRIORITY_LABELS).map(([k, l]) => (
                          <SelectItem key={k} value={k}>
                            {l}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      id={id}
                      value={val as string}
                      placeholder={f.placeholder}
                      inputMode={f.type === "date" ? "numeric" : undefined}
                      aria-invalid={Boolean(errors[f.key])}
                      onChange={(e) => set(f.key, e.target.value)}
                    />
                  )}
                  {errors[f.key] && <p className="mt-1 text-xs text-destructive">{errors[f.key]}</p>}
                </div>
              );
            })}
          </div>
          <DialogFooter className="border-t px-6 py-4">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Annuler
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Enregistrement…" : "Enregistrer"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
