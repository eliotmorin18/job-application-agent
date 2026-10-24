import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { moveItem } from "@/features/cvs/adapters";
import { SortableTagInput } from "@/features/cvs/components/SortableTagInput";

const TAGS = ["Python", "SQL", "Docker", "Spark", "Git"];

/**
 * jsdom has no layout: tags are laid out three per row, 80 × 24 px, in DOM order —
 * Python SQL Docker / Spark Git — so a drag can cross from one line to the next.
 */
beforeAll(() => {
  const original = Element.prototype.getBoundingClientRect;
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    if (!this.getAttribute("aria-roledescription")?.endsWith(" déplaçable"))
      return original.call(this);
    const tags = [...this.parentElement!.querySelectorAll('[aria-roledescription$=" déplaçable"]')];
    const i = tags.indexOf(this);
    const left = (i % 3) * 80;
    const top = Math.floor(i / 3) * 24;
    return {
      x: left,
      y: top,
      left,
      top,
      width: 80,
      height: 24,
      right: left + 80,
      bottom: top + 24,
      toJSON: () => ({}),
    };
  });
  if (!("PointerEvent" in window))
    (window as unknown as { PointerEvent: typeof MouseEvent }).PointerEvent = MouseEvent;
});

afterEach(() => vi.clearAllMocks());

function Harness({
  onChange,
  initial = TAGS,
  interests = false,
}: {
  onChange: (v: string[]) => void;
  initial?: string[];
  interests?: boolean;
}) {
  const [value, setValue] = useState(initial);
  const onValue = (next: string[]) => {
    setValue(next);
    onChange(next);
  };
  return interests ? (
    <SortableTagInput
      value={value}
      label="Centres d'intérêt"
      itemName="centre d'intérêt"
      addLabel="Ajouter un centre d'intérêt"
      onChange={onValue}
    />
  ) : (
    <SortableTagInput value={value} label="Langages" onChange={onValue} />
  );
}

const tag = (name: string) => screen.getByRole("group", { name });
const order = () => screen.getAllByRole("group").map((g) => g.getAttribute("aria-label"));

/** Presses `name`, moves the pointer to (x, y) in two steps, releases. */
function drag(name: string, x: number, y: number) {
  const el = tag(name);
  const box = el.getBoundingClientRect();
  fireEvent.pointerDown(el, {
    button: 0,
    pointerId: 1,
    clientX: box.left + 10,
    clientY: box.top + 10,
  });
  fireEvent.pointerMove(el, { pointerId: 1, clientX: box.left + 20, clientY: box.top + 10 });
  fireEvent.pointerMove(el, { pointerId: 1, clientX: x, clientY: y });
  fireEvent.pointerUp(el, { pointerId: 1, clientX: x, clientY: y });
}

describe("moveItem", () => {
  it("moves one element and keeps the others in order", () => {
    expect(moveItem(TAGS, 0, 4)).toEqual(["SQL", "Docker", "Spark", "Git", "Python"]);
    expect(moveItem(TAGS, 4, 0)).toEqual(["Git", "Python", "SQL", "Docker", "Spark"]);
    expect(moveItem(TAGS, 1, 1)).toEqual(TAGS);
  });
});

describe("SortableTagInput", () => {
  it("drags a skill to the end, to the start and to the middle, across lines", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    drag("Python", 200, 36); // second line, after Git
    expect(order()).toEqual(["SQL", "Docker", "Spark", "Git", "Python"]);

    drag("Git", 5, 5); // first line, before SQL
    expect(order()).toEqual(["Git", "SQL", "Docker", "Spark", "Python"]);

    drag("Docker", 100, 36); // second line, between Spark and Python
    expect(order()).toEqual(["Git", "SQL", "Spark", "Docker", "Python"]);
    expect(onChange).toHaveBeenCalledTimes(3);
    expect(screen.getByText("Docker : nouvelle position 4 sur 5.")).toBeInTheDocument();
  });

  it("ends a drag released outside the tags, and starts the next one from the right skill", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const java = tag("Python");
    fireEvent.pointerDown(java, { button: 0, pointerId: 1, clientX: 10, clientY: 10 });
    fireEvent.pointerMove(document.body, { pointerId: 1, clientX: 30, clientY: 10 });
    fireEvent.pointerMove(document.body, { pointerId: 1, clientX: 400, clientY: 36 });
    // Released past the last tag, on the container: not on any tag
    fireEvent.pointerUp(document.body, { pointerId: 1, clientX: 400, clientY: 36 });
    expect(order()).toEqual(["SQL", "Docker", "Spark", "Git", "Python"]);
    // The gesture is over: moving the pointer changes nothing
    fireEvent.pointerMove(document.body, { pointerId: 1, clientX: 5, clientY: 5 });
    expect(order()).toEqual(["SQL", "Docker", "Spark", "Git", "Python"]);
    // The next drag moves the skill that was pressed
    drag("Docker", 5, 5);
    expect(order()).toEqual(["Docker", "SQL", "Spark", "Git", "Python"]);
    expect(onChange).toHaveBeenCalledTimes(2);
  });

  it("previews the new order while dragging and changes the value only on release", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const el = tag("Python");
    fireEvent.pointerDown(el, { button: 0, pointerId: 1, clientX: 10, clientY: 10 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 230, clientY: 10 });
    expect(order()).toEqual(["SQL", "Docker", "Python", "Spark", "Git"]);
    expect(tag("Python")).toHaveAttribute("data-dragging", "true");
    expect(onChange).not.toHaveBeenCalled();
    // A cancelled gesture (e.g. a scroll taking over on touch) keeps the order
    fireEvent.pointerCancel(el, { pointerId: 1 });
    expect(order()).toEqual(TAGS);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("removes a skill with × without starting a drag, and ignores a simple click", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    // A click (or a tremble under the threshold) is not a move
    const el = tag("SQL");
    fireEvent.pointerDown(el, { button: 0, pointerId: 1, clientX: 90, clientY: 10 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 92, clientY: 11 });
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 92, clientY: 11 });
    expect(onChange).not.toHaveBeenCalled();

    const remove = screen.getByRole("button", { name: "Retirer Docker" });
    fireEvent.pointerDown(remove, { button: 0, pointerId: 2, clientX: 230, clientY: 10 });
    fireEvent.pointerMove(remove, { pointerId: 2, clientX: 10, clientY: 40 });
    fireEvent.pointerUp(remove, { pointerId: 2, clientX: 10, clientY: 40 });
    fireEvent.click(remove);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(order()).toEqual(["Python", "SQL", "Spark", "Git"]);
  });

  it("reorders with the keyboard: Space to lift, arrows / Home / End to move, Space to drop", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    // Arrows alone move the focus between the skills
    tag("SQL").focus();
    fireEvent.keyDown(tag("SQL"), { key: "ArrowRight" });
    expect(tag("Docker")).toHaveFocus();
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.keyDown(tag("Docker"), { key: " " });
    expect(screen.getByText(/Saisie de Docker, position 3 sur 5/)).toBeInTheDocument();
    fireEvent.keyDown(tag("Docker"), { key: "ArrowLeft" });
    expect(order()).toEqual(["Python", "Docker", "SQL", "Spark", "Git"]);
    expect(tag("Docker")).toHaveFocus();
    fireEvent.keyDown(tag("Docker"), { key: "Home" });
    expect(order()).toEqual(["Docker", "Python", "SQL", "Spark", "Git"]);
    fireEvent.keyDown(tag("Docker"), { key: "End" });
    expect(order()).toEqual(["Python", "SQL", "Spark", "Git", "Docker"]);
    fireEvent.keyDown(tag("Docker"), { key: " " });
    expect(screen.getByText("Dépôt de Docker en position 5 sur 5.")).toBeInTheDocument();
    // Dropped: the arrows move the focus again
    fireEvent.keyDown(tag("Docker"), { key: "ArrowLeft" });
    expect(tag("Git")).toHaveFocus();
    expect(order()).toEqual(["Python", "SQL", "Spark", "Git", "Docker"]);
  });

  it("cancels a keyboard move with Escape", () => {
    render(<Harness onChange={vi.fn()} />);
    tag("Spark").focus();
    fireEvent.keyDown(tag("Spark"), { key: "Enter" });
    fireEvent.keyDown(tag("Spark"), { key: "ArrowUp" });
    fireEvent.keyDown(tag("Spark"), { key: "ArrowUp" });
    expect(order()).toEqual(["Python", "Spark", "SQL", "Docker", "Git"]);
    fireEvent.keyDown(tag("Spark"), { key: "Escape" });
    expect(order()).toEqual(TAGS);
    expect(tag("Spark")).toHaveFocus();
    expect(
      screen.getByText(/Déplacement annulé : Spark reste en position 4 sur 5/),
    ).toBeInTheDocument();
  });

  it("keeps adding skills at the end", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const input = screen.getByRole("textbox", { name: "Ajouter une compétence à « Langages »" });
    fireEvent.change(input, { target: { value: "Rust" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(order()).toEqual([...TAGS, "Rust"]);
  });
});

describe("SortableTagInput — centres d'intérêt", () => {
  const INTERESTS = ["Football", "Tennis", "Escalade", "Guitare", "Échecs"];

  it("reorders interests to the start, the middle and the end, across lines", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} initial={INTERESTS} interests />);
    expect(tag("Football")).toHaveAttribute("aria-roledescription", "centre d'intérêt déplaçable");

    drag("Échecs", 5, 5); // second line -> first place
    expect(order()).toEqual(["Échecs", "Football", "Tennis", "Escalade", "Guitare"]);
    drag("Échecs", 100, 36); // -> middle of the second line (between Escalade and Guitare)
    expect(order()).toEqual(["Football", "Tennis", "Escalade", "Échecs", "Guitare"]);
    drag("Football", 200, 36); // first -> last
    expect(order()).toEqual(["Tennis", "Escalade", "Échecs", "Guitare", "Football"]);
    expect(onChange).toHaveBeenCalledTimes(3);
  });

  it("reorders interests with the keyboard, removes and adds without moving anything", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} initial={INTERESTS} interests />);
    tag("Escalade").focus();
    fireEvent.keyDown(tag("Escalade"), { key: " " });
    fireEvent.keyDown(tag("Escalade"), { key: "Home" });
    fireEvent.keyDown(tag("Escalade"), { key: " " });
    expect(order()).toEqual(["Escalade", "Football", "Tennis", "Guitare", "Échecs"]);
    expect(tag("Escalade")).toHaveFocus();

    const remove = screen.getByRole("button", { name: "Retirer Tennis" });
    fireEvent.pointerDown(remove, { button: 0, pointerId: 3, clientX: 10, clientY: 10 });
    fireEvent.pointerMove(remove, { pointerId: 3, clientX: 200, clientY: 40 });
    fireEvent.pointerUp(remove, { pointerId: 3, clientX: 200, clientY: 40 });
    fireEvent.click(remove);
    expect(order()).toEqual(["Escalade", "Football", "Guitare", "Échecs"]);

    const input = screen.getByRole("textbox", { name: "Ajouter un centre d'intérêt" });
    fireEvent.change(input, { target: { value: "Course à pied" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(order()).toEqual(["Escalade", "Football", "Guitare", "Échecs", "Course à pied"]);
  });
});
