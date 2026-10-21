import type { Priority } from "@/services/api/types";

const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

/** Formats "2026" or "2026-02" (no day required). */
export function formatDate(d?: string) {
  if (!d) return "";
  const [y, m] = d.split("-");
  if (!m) return y;
  return `${MONTHS[Number(m) - 1] ?? m} ${y}`;
}

export function formatRange(start?: string, end?: string, ongoingLabel = "Présent") {
  if (!start && !end) return "";
  if (!end) return `${formatDate(start)} — ${ongoingLabel}`;
  if (!start) return formatDate(end);
  return `${formatDate(start)} — ${formatDate(end)}`;
}

export const DATE_PATTERN = /^\d{4}(-(0[1-9]|1[0-2]))?$/;

export const PRIORITY_LABELS: Record<Priority, string> = {
  high: "Haute",
  medium: "Moyenne",
  low: "Basse",
};

/** Skill category key as stored in the profile ("machine_learning") -> "Machine learning". */
export function formatCategory(key: string) {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function initials(first?: string, last?: string) {
  return `${first?.[0] ?? ""}${last?.[0] ?? ""}`.toUpperCase() || "?";
}
