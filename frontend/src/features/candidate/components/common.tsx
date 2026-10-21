import { Check, Pencil, Plus, Trash2, X, type LucideIcon } from "lucide-react";
import { useState, type KeyboardEvent, type ReactNode } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export function TagList({ tags, max, variant = "secondary" }: { tags?: string[] | undefined; max?: number | undefined; variant?: "secondary" | "outline" | undefined }) {
  if (!tags?.length) return null;
  const shown = max ? tags.slice(0, max) : tags;
  const rest = tags.length - shown.length;
  return (
    <div className="flex flex-wrap gap-1.5">
      {shown.map((t) => (
        <Badge key={t} variant={variant} className="font-normal">
          {t}
        </Badge>
      ))}
      {rest > 0 && (
        <Badge variant="outline" className="font-normal text-muted-foreground">
          +{rest}
        </Badge>
      )}
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  text,
  action,
}: {
  icon: LucideIcon;
  title: string;
  text: string;
  action?: ReactNode | undefined;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed bg-card px-6 py-14 text-center">
      <div className="mb-4 flex size-11 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <Icon className="size-5" />
      </div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-muted-foreground">{text}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Supprimer",
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string | undefined;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Annuler</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** "+ Ajouter" chip that turns into an input. */
export function InlineAdd({
  label,
  placeholder,
  onAdd,
}: {
  label: string;
  placeholder?: string | undefined;
  onAdd: (value: string) => Promise<unknown> | void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");

  const submit = async () => {
    const v = value.trim();
    if (!v) return setEditing(false);
    await onAdd(v);
    setValue("");
  };

  if (!editing)
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="inline-flex h-6 items-center gap-1 rounded-md border border-dashed px-2 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
      >
        <Plus className="size-3" />
        {label}
      </button>
    );

  return (
    <div className="flex items-center gap-1">
      <Input
        autoFocus
        value={value}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") setEditing(false);
        }}
        className="h-7 w-44 text-xs"
      />
      <Button size="icon" variant="ghost" className="size-7" onClick={submit} aria-label="Valider">
        <Check className="size-3.5" />
      </Button>
      <Button size="icon" variant="ghost" className="size-7" onClick={() => setEditing(false)} aria-label="Annuler">
        <X className="size-3.5" />
      </Button>
    </div>
  );
}

/** Tag that opens a small popover to rename or delete it. */
export function EditableTag({
  value,
  onRename,
  onDelete,
}: {
  value: string;
  onRename: (newName: string) => Promise<unknown> | void;
  onDelete: () => Promise<unknown> | void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);

  const save = async () => {
    if (draft.trim() && draft.trim() !== value) await onRename(draft.trim());
    setOpen(false);
  };

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) setDraft(value);
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className="group inline-flex h-6 items-center gap-1 rounded-md bg-secondary px-2 text-xs text-secondary-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          {value}
          <Pencil className="size-2.5 opacity-0 transition-opacity group-hover:opacity-60" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-3" align="start">
        <p className="mb-2 text-xs font-medium text-muted-foreground">Renommer</p>
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
          className="h-8"
        />
        <div className="mt-3 flex justify-between">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-destructive hover:text-destructive"
            onClick={async () => {
              setOpen(false);
              await onDelete();
            }}
          >
            <Trash2 className="size-3.5" />
            Supprimer
          </Button>
          <Button size="sm" className="h-7" onClick={save}>
            Enregistrer
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** Removable tags + input (Enter or comma to add). */
export function TagInput({
  value,
  onChange,
  placeholder,
  id,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string | undefined;
  id?: string | undefined;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add();
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2 py-1.5 focus-within:ring-2 focus-within:ring-ring/40">
      {value.map((t) => (
        <Badge key={t} variant="secondary" className="gap-1 pr-1 font-normal">
          {t}
          <button
            type="button"
            aria-label={`Retirer ${t}`}
            onClick={() => onChange(value.filter((x) => x !== t))}
            className="rounded-sm opacity-60 hover:opacity-100"
          >
            <X className="size-3" />
          </button>
        </Badge>
      ))}
      <input
        id={id}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        onBlur={add}
        placeholder={value.length ? "" : placeholder}
        className="min-w-[8rem] flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
      />
    </div>
  );
}

/** Editable list of individual lines. */
export function ListEditor({
  value,
  onChange,
  placeholder,
  addLabel = "Ajouter une ligne",
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string | undefined;
  addLabel?: string | undefined;
}) {
  return (
    <div className="space-y-2">
      {value.map((line, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="size-1.5 shrink-0 rounded-full bg-primary/50" />
          <Input
            value={line}
            placeholder={placeholder}
            onChange={(e) => onChange(value.map((l, j) => (j === i ? e.target.value : l)))}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const next = [...value];
                next.splice(i + 1, 0, "");
                onChange(next);
              }
            }}
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="shrink-0 text-muted-foreground"
            aria-label="Supprimer la ligne"
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            <X className="size-4" />
          </Button>
        </div>
      ))}
      <Button type="button" variant="ghost" size="sm" className="text-primary" onClick={() => onChange([...value, ""])}>
        <Plus className="size-4" />
        {addLabel}
      </Button>
    </div>
  );
}

export function SectionCard({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string | undefined;
  action?: ReactNode | undefined;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border bg-card p-5 shadow-soft">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
