import type { RequirementStatus } from "@/services/api/cvTypes";

/** Labels and soft colours of a requirement status (requirements detail, interview questions). */
export const STATUS_LABELS: Record<RequirementStatus, string> = {
  met: "Remplie",
  partial: "Partiellement remplie",
  not_documented: "Non documentée",
  missing: "Non remplie",
};

export const STATUS_CLASSES: Record<RequirementStatus, string> = {
  met: "bg-accent text-accent-foreground",
  partial: "bg-priority-medium text-priority-medium-foreground",
  not_documented: "bg-muted text-muted-foreground",
  missing: "bg-destructive/10 text-destructive",
};
