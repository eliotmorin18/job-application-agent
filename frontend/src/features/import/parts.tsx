import { AlertTriangle, Ban } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import type { ProposalStatus } from "@/services/api/types";
import { sectionConfig } from "../candidate/sectionConfig";

const STATUS: Record<ProposalStatus, { label: string; className: string }> = {
  new: {
    label: "Nouveau",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  },
  probable_duplicate: {
    label: "Doublon probable",
    className: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200",
  },
  possible_duplicate: {
    label: "Doublon possible",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  },
  duplicate: { label: "Déjà présent", className: "bg-muted text-muted-foreground" },
};

export function StatusBadge({ status }: { status: ProposalStatus }) {
  const s = STATUS[status];
  return <Badge className={cn("border-0 font-medium shadow-none", s.className)}>{s.label}</Badge>;
}

export const STATUS_LABELS = Object.fromEntries(
  Object.entries(STATUS).map(([k, v]) => [k, v.label]),
) as Record<ProposalStatus, string>;

export function Uncertain() {
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-700 dark:text-amber-300"
      title="À vérifier : l'extraction n'est pas sûre de cette valeur"
    >
      <AlertTriangle className="size-3" />À vérifier
    </span>
  );
}

const PERSONAL_LABELS: Record<string, string> = {
  first_name: "Prénom",
  last_name: "Nom",
  email: "E-mail",
  phone: "Téléphone",
  birth_date: "Date de naissance",
  gender: "Genre",
  nationality: "Nationalité",
  address: "Adresse",
  postal_code: "Code postal",
  city: "Ville",
  country: "Pays",
  linkedin: "LinkedIn",
  github: "GitHub",
};

const ITEM_LABELS: Record<string, string> = Object.fromEntries(
  Object.values(sectionConfig).flatMap((c) => c.fields.map((f) => [f.key, f.label])),
);

export const fieldLabel = (field: string) => ITEM_LABELS[field] ?? PERSONAL_LABELS[field] ?? field;

/** A text or a list of texts, as extracted or stored. */
export function Value({ value, muted }: { value: unknown; muted?: boolean | undefined }) {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && !value.length)
  )
    return <span className="text-muted-foreground/60">—</span>;
  if (Array.isArray(value))
    return (
      <ul className={cn("space-y-1", muted && "text-muted-foreground")}>
        {value.map((v, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-2 size-1 shrink-0 rounded-full bg-primary/60" />
            <span>{String(v)}</span>
          </li>
        ))}
      </ul>
    );
  return (
    <span className={cn("whitespace-pre-line", muted && "text-muted-foreground")}>
      {String(value)}
    </span>
  );
}

/** Segmented control: Ajouter / Mettre à jour / Ignorer (only the actions possible for this proposal). */
export function ActionToggle<A extends string>({
  value,
  options,
  onChange,
}: {
  value: A;
  options: {
    value: A;
    label: string;
    disabled?: boolean | undefined;
    title?: string | undefined;
  }[];
  onChange: (v: A) => void;
}) {
  return (
    <div className="inline-flex shrink-0 rounded-lg border bg-muted/40 p-0.5" role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          disabled={o.disabled}
          title={o.title}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40",
            value === o.value
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function CheckLine({
  checked,
  onChange,
  disabled,
  children,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean | undefined;
  children: ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-2 text-sm",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <Checkbox
        className="mt-0.5"
        checked={checked}
        disabled={disabled}
        onCheckedChange={(c) => onChange(c === true)}
      />
      <span className="min-w-0">{children}</span>
    </label>
  );
}

export function ProblemList({ problems }: { problems?: string[] | undefined }) {
  if (!problems?.length) return null;
  return (
    <ul className="mt-3 space-y-1 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
      {problems.map((p, i) => (
        <li key={i}>{p}</li>
      ))}
    </ul>
  );
}

/**
 * Why an action is not available (apply_import.py would refuse it whatever the confirmation).
 * If the user already chose it, it is shown as a problem; the choice is never changed for them.
 */
export function UnavailableNote({
  reason,
  selected,
  action,
}: {
  reason?: string | undefined;
  selected: boolean;
  action: string;
}) {
  if (!reason) return null;
  return (
    <p
      className={cn(
        "mt-1 flex items-start gap-1.5 text-xs",
        selected ? "text-destructive" : "text-muted-foreground",
      )}
    >
      <Ban className="mt-0.5 size-3 shrink-0" />
      <span>
        {selected ? `Action impossible : ${reason}` : `${action} indisponible : ${reason}`}
      </span>
    </p>
  );
}
