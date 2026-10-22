// Presentational pieces of the « Offre et adéquation » and « Préparation à l'entretien » tabs. Display only: texts come from analysis.json unchanged.

import {
  Briefcase,
  ChevronDown,
  FolderGit2,
  GraduationCap,
  Languages,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Evidence } from "@/services/api/cvTypes";

/** Foldable row with a chevron. Rows are meant to be stacked inside one bordered `divide-y` container. */
export function FoldableBlock({
  icon: Icon,
  title,
  count,
  defaultOpen = false,
  tone = "default",
  children,
}: {
  icon: LucideIcon;
  title: string;
  count?: number | undefined;
  defaultOpen?: boolean;
  /** "warning": discreet amber accent (points de vigilance), never an alarming colour. */
  tone?: "default" | "warning";
  children: ReactNode;
}) {
  return (
    <Collapsible defaultOpen={defaultOpen} className="group/fold">
      <CollapsibleTrigger className="flex w-full items-center gap-2.5 px-4 py-3 text-left text-sm font-medium transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
        <Icon
          className={`size-4 shrink-0 ${tone === "warning" ? "text-amber-600 dark:text-amber-400" : "text-primary"}`}
        />
        <span className="flex-1">{title}</span>
        {count !== undefined && (
          <span className="text-xs font-normal tabular-nums text-muted-foreground">{count}</span>
        )}
        <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-data-[state=open]/fold:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-4 pb-4">{children}</CollapsibleContent>
    </Collapsible>
  );
}

/**
 * Main section of the « Offre et adéquation » tab (level 1), closed by default: a card whose header
 * stays visible when folded. Larger and bolder than the FoldableBlock rows (level 2) it may contain.
 * Each section folds on its own, so several can be open at once. Display only: no request on toggle.
 */
export function FoldableSection({
  icon: Icon,
  title,
  count,
  children,
}: {
  icon: LucideIcon;
  title: string;
  count?: number | undefined;
  children: ReactNode;
}) {
  return (
    <Collapsible asChild className="group/section">
      <section className="overflow-hidden rounded-xl border bg-card shadow-soft">
        <h3>
          <CollapsibleTrigger className="flex w-full items-center gap-3 px-4 py-4 text-left transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/40 sm:px-5">
            <Icon className="size-[18px] shrink-0 text-muted-foreground" />
            <span className="flex-1 text-base font-semibold tracking-tight">{title}</span>
            {count !== undefined && (
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium tabular-nums text-muted-foreground">
                {count}
              </span>
            )}
            <ChevronDown className="size-5 shrink-0 text-muted-foreground transition-transform duration-200 group-data-[state=open]/section:rotate-180" />
          </CollapsibleTrigger>
        </h3>
        <CollapsibleContent className="px-4 pb-5 pt-1 sm:px-5">{children}</CollapsibleContent>
      </section>
    </Collapsible>
  );
}

/**
 * Explanation clamped to three lines, with « Lire la suite » only when the text is really cut
 * (measured, so it follows the card width on desktop and mobile). Nothing is ever hidden for good.
 */
export function Expandable({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const [clipped, setClipped] = useState(false);
  const ref = useRef<HTMLParagraphElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || open) return;
    const measure = () => setClipped(el.scrollHeight > el.clientHeight + 1);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [text, open]);

  if (!text) return null;
  return (
    <div>
      <p
        ref={ref}
        className={`text-sm leading-relaxed text-muted-foreground ${open ? "" : "line-clamp-3"}`}
      >
        {text}
      </p>
      {(clipped || open) && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="mt-1 text-xs font-medium text-primary hover:underline"
        >
          {open ? "Réduire" : "Lire la suite"}
        </button>
      )}
    </div>
  );
}

// Very light accents only: a thin left border and the icon, never the whole background.
const CARD_BORDER = {
  strength: "border-l-emerald-500/50",
  weakness: "border-l-amber-500/50",
} as const;
const CARD_ICON = {
  strength: "text-emerald-600 dark:text-emerald-400",
  weakness: "text-amber-600 dark:text-amber-400",
} as const;

/** Same card for strengths and weaknesses: only the discreet accent colour differs. */
export function InsightCard({
  tone,
  icon: Icon,
  title,
  explanation,
  footer,
}: {
  tone: "strength" | "weakness";
  icon: LucideIcon;
  title: string;
  explanation: string;
  footer?: ReactNode;
}) {
  return (
    <article
      className={`flex flex-col gap-2 rounded-lg border border-l-2 bg-background p-4 ${CARD_BORDER[tone]}`}
    >
      <h4 className="flex items-start gap-2 text-sm font-medium leading-snug">
        <Icon className={`mt-0.5 size-4 shrink-0 ${CARD_ICON[tone]}`} />
        {title}
      </h4>
      <Expandable text={explanation} />
      {footer && <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1">{footer}</div>}
    </article>
  );
}

export function MetaBadge({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <Badge
      variant="outline"
      className={`max-w-full whitespace-normal font-normal text-muted-foreground ${className}`}
    >
      {children}
    </Badge>
  );
}

const EVIDENCE_ICONS: Record<Evidence["type"], LucideIcon> = {
  experience: Briefcase,
  project: FolderGit2,
  education: GraduationCap,
  skill: Sparkles,
  language: Languages,
};

export /** Evidence labels (experience, project…), without duplicates: strengths and interview questions. */
function EvidenceBadges({ evidence }: { evidence: Evidence[] }) {
  const unique = [...new Map(evidence.filter((e) => e.label).map((e) => [e.label, e])).values()];
  return unique.map((e) => {
    const Icon = EVIDENCE_ICONS[e.type] ?? Sparkles;
    return (
      <MetaBadge key={e.label} className="gap-1">
        <Icon className="size-3 shrink-0" />
        {e.label}
      </MetaBadge>
    );
  });
}
