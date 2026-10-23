// Presentational pieces of the « Vue d'ensemble » and « Entretien » tabs. Display only: texts come from analysis.json unchanged.

import {
  Briefcase,
  ChevronDown,
  FolderGit2,
  GraduationCap,
  Heart,
  Languages,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Evidence } from "@/services/api/cvTypes";

/**
 * Foldable section card, closed by default, whose header stays visible when folded (« Exigences
 * détaillées », sections of « Entretien »). Each section folds on its own, so several can be open at
 * once. Display only: no request on toggle.
 */
export function FoldableSection({
  icon: Icon,
  title,
  count,
  titleClassName = "text-base",
  children,
}: {
  icon: LucideIcon;
  title: string;
  count?: number | undefined;
  /** Size of the title (« text-base » by default; « Exigences détaillées » uses « text-lg »). */
  titleClassName?: string;
  children: ReactNode;
}) {
  return (
    <Collapsible asChild className="group/section">
      <section className="overflow-hidden rounded-xl border bg-card shadow-soft">
        <h3>
          <CollapsibleTrigger className="flex w-full items-center gap-3 px-4 py-4 text-left transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/40 sm:px-5">
            <Icon className="size-[18px] shrink-0 text-muted-foreground" />
            <span className={`flex-1 font-semibold tracking-tight ${titleClassName}`}>{title}</span>
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
  interest: Heart,
};

export /** Evidence labels (experience, project…), without duplicates: interview questions and preparation. */
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
