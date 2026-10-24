// Tags that can be reordered (mouse, touch, keyboard), plus the usual add / remove: the skills of a
// group and the interests of the CV editor.
// Same look as TagInput (features/candidate/components/common.tsx), which stays unchanged elsewhere.
// No dependency: pointer events cover mouse and touch; the order is the order of `value`.

import { GripVertical, X } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { Badge } from "@/components/ui/badge";
import { moveItem } from "../adapters";

/** Distance (px) the pointer must travel before a press becomes a drag: a click stays a click. */
const DRAG_THRESHOLD = 4;

/**
 * Index where the dragged tag goes for a pointer at (x, y): the number of other tags before the
 * pointer in reading order (rows first, then left to right), so it also works across wrapped lines.
 */
function dropIndex(others: DOMRect[], x: number, y: number): number {
  return others.filter(
    (r) => r.bottom <= y || (r.top <= y && y < r.bottom && r.left + r.width / 2 < x),
  ).length;
}

export function SortableTagInput({
  value,
  onChange,
  placeholder,
  label,
  itemName = "compétence",
  addLabel = `Ajouter une compétence à « ${label} »`,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  /** Name of the group, for the keyboard instructions and announcements. */
  label: string;
  /** What one tag is, for assistive technologies: "compétence", "centre d'intérêt". */
  itemName?: string;
  /** Label of the input that adds a tag. */
  addLabel?: string;
}) {
  const [draft, setDraft] = useState("");
  // Pointer drag in progress: the order shown follows the pointer, `value` changes on release.
  const [drag, setDrag] = useState<{ from: number; to: number } | null>(null);
  // Keyboard move in progress: the tag lifted with Space and its order before the move.
  const [lifted, setLifted] = useState<{ tag: string; original: string[] } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  // Latest props and drag, for the window listeners of a pointer gesture
  const latest = useRef({ value, onChange });
  latest.current = { value, onChange };
  const dragRef = useRef<{ from: number; to: number } | null>(null);
  const stopGesture = useRef<(() => void) | null>(null);
  const tagRefs = useRef(new Map<string, HTMLDivElement>());
  const refocus = useRef<string | null>(null);

  const shown = drag ? moveItem(value, drag.from, drag.to) : value;
  const position = (tag: string, list = value) => `${list.indexOf(tag) + 1} sur ${list.length}`;

  // A gesture still running when the component goes away is stopped (no listener left behind).
  useEffect(() => () => stopGesture.current?.(), []);

  // A moved tag gets its focus back (the browser drops it when the node moves in the DOM).
  useEffect(() => {
    if (!refocus.current) return;
    tagRefs.current.get(refocus.current)?.focus();
    refocus.current = null;
  }, [value]);

  const add = () => {
    const v = draft.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setDraft("");
  };
  const onInputKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add();
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };

  const moveTo = (tag: string, to: number) => {
    const from = value.indexOf(tag);
    const target = Math.max(0, Math.min(value.length - 1, to));
    if (target === from) return;
    const next = moveItem(value, from, target);
    refocus.current = tag;
    onChange(next);
    setAnnouncement(`${tag} : position ${position(tag, next)}.`);
  };

  const onTagKey = (e: KeyboardEvent<HTMLDivElement>, tag: string) => {
    if (e.target !== e.currentTarget) return; // the remove button handles its own keys
    const index = value.indexOf(tag);
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      if (lifted?.tag === tag) {
        setLifted(null);
        setAnnouncement(`Dépôt de ${tag} en position ${position(tag)}.`);
      } else {
        setLifted({ tag, original: value });
        setAnnouncement(
          `Saisie de ${tag}, position ${position(tag)}. Flèches pour déplacer, Espace pour déposer, Échap pour annuler.`,
        );
      }
      return;
    }
    if (e.key === "Escape" && lifted?.tag === tag) {
      e.preventDefault();
      refocus.current = tag;
      onChange(lifted.original);
      setLifted(null);
      setAnnouncement(
        `Déplacement annulé : ${tag} reste en position ${position(tag, lifted.original)}.`,
      );
      return;
    }
    const step =
      e.key === "ArrowLeft" || e.key === "ArrowUp"
        ? -1
        : e.key === "ArrowRight" || e.key === "ArrowDown"
          ? 1
          : 0;
    if (lifted?.tag === tag) {
      if (step || e.key === "Home" || e.key === "End") e.preventDefault();
      if (step) moveTo(tag, index + step);
      else if (e.key === "Home") moveTo(tag, 0);
      else if (e.key === "End") moveTo(tag, value.length - 1);
    } else if (step) {
      // Not lifted: the arrows move the focus between the tags
      e.preventDefault();
      tagRefs.current.get(value[Math.max(0, Math.min(value.length - 1, index + step))]!)?.focus();
    }
  };

  const setDragState = (next: { from: number; to: number } | null) => {
    dragRef.current = next;
    setDrag(next);
  };

  /**
   * A pointer gesture on a tag (mouse, pen or touch). Moves and the release are followed on the
   * window: the tag node moves in the DOM while dragging, and the release may happen anywhere.
   */
  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>, tag: string) => {
    if (e.button !== 0 || (e.target as Element).closest("button")) return; // × keeps its click
    stopGesture.current?.();
    const start = { x: e.clientX, y: e.clientY };
    const from = latest.current.value.indexOf(tag);

    const move = (ev: PointerEvent) => {
      if (!dragRef.current) {
        if (Math.hypot(ev.clientX - start.x, ev.clientY - start.y) < DRAG_THRESHOLD) return;
        setLifted(null);
      }
      const current = latest.current.value;
      const order = dragRef.current ? moveItem(current, from, dragRef.current.to) : current;
      const others = order
        .filter((t) => t !== tag)
        .map((t) => tagRefs.current.get(t)?.getBoundingClientRect())
        .filter((r): r is DOMRect => !!r);
      setDragState({ from, to: dropIndex(others, ev.clientX, ev.clientY) });
    };
    const finish = (commit: boolean) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      stopGesture.current = null;
      const done = dragRef.current;
      setDragState(null);
      if (commit && done && done.to !== done.from) {
        const next = moveItem(latest.current.value, done.from, done.to);
        latest.current.onChange(next);
        setAnnouncement(`${tag} : nouvelle position ${next.indexOf(tag) + 1} sur ${next.length}.`);
      }
    };
    const onUp = () => finish(true);
    const onCancel = () => finish(false);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    stopGesture.current = onCancel;
  };

  const draggedTag = drag ? value[drag.from] : lifted?.tag;
  const instructionsId = `${label}-sort-help`.replace(/\s+/g, "-");

  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2 py-1.5 focus-within:ring-2 focus-within:ring-ring/40">
      <p id={instructionsId} className="sr-only">
        Espace pour saisir un élément, flèches pour le déplacer dans « {label} », Espace pour le
        déposer, Échap pour annuler.
      </p>
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
      {shown.map((t) => (
        <div
          key={t}
          ref={(el) => {
            if (el) tagRefs.current.set(t, el);
            else tagRefs.current.delete(t);
          }}
          tabIndex={0}
          role="group"
          aria-roledescription={`${itemName} déplaçable`}
          aria-label={t}
          aria-describedby={instructionsId}
          data-dragging={t === draggedTag || undefined}
          onKeyDown={(e) => onTagKey(e, t)}
          onPointerDown={(e) => onPointerDown(e, t)}
          onBlur={() => {
            if (lifted?.tag === t && !refocus.current) setLifted(null);
          }}
          className="cursor-grab touch-none rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 data-[dragging]:cursor-grabbing"
        >
          <Badge
            variant="secondary"
            className={`gap-0.5 pl-1 pr-1 font-normal ${
              t === draggedTag ? "opacity-70 ring-1 ring-primary" : ""
            }`}
          >
            <GripVertical aria-hidden className="size-3 opacity-40" />
            {t}
            <button
              type="button"
              aria-label={`Retirer ${t}`}
              onClick={() => onChange(value.filter((x) => x !== t))}
              className="ml-0.5 rounded-sm opacity-60 hover:opacity-100"
            >
              <X className="size-3" />
            </button>
          </Badge>
        </div>
      ))}
      <input
        value={draft}
        aria-label={addLabel}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onInputKey}
        onBlur={add}
        placeholder={value.length ? "" : placeholder}
        className="min-w-[8rem] flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
      />
    </div>
  );
}
