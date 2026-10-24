import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { CvEditorTab } from "@/features/cvs/components/CvEditorTab";
import { PdfPreview } from "@/features/cvs/components/PdfPreview";
import type { CompletedAnalysis, CvDocument, Evidence } from "@/services/api/cvTypes";
import {
  analysisFixture,
  documentFixture,
  layoutFixture,
  profileFixture,
  summary,
} from "./fixtures/cvFixtures";

// pdf.js is replaced by a one-page A4 document: the preview logic runs, nothing is drawn.
const pdf = vi.hoisted(() => {
  const page = {
    getViewport: ({ scale }: { scale: number }) => ({ width: 595 * scale, height: 842 * scale }),
    render: () => ({ promise: Promise.resolve(), cancel: () => undefined }),
  };
  return {
    getDocument: vi.fn(() => ({
      promise: Promise.resolve({ numPages: 1, getPage: async () => page }),
      destroy: async () => undefined,
    })),
  };
});
vi.mock("pdfjs-dist", () => ({ GlobalWorkerOptions: {}, getDocument: pdf.getDocument }));
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({ default: "pdf.worker.js" }));
// Leaving with unsaved changes is guarded by the router: not under test here.
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
  useBlocker: () => ({ proceed: undefined, reset: undefined, status: "idle" }),
}));

const CV = "/api/cvs/fictive-corp-data-engineer";

/** Fake FastAPI backend: `routes` maps "METHOD /path" to [status, body]; requests are recorded. */
function fakeBackend(routes: Record<string, [number, unknown]>) {
  const calls: { key: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const key = `${init.method ?? "GET"} ${url}`;
      calls.push({ key, body: init.body ? JSON.parse(String(init.body)) : undefined });
      const [status, body] = routes[key] ?? [
        500,
        { detail: { message: "Route inattendue", problems: [key] } },
      ];
      return new Response(JSON.stringify(body), { status });
    }),
  );
  return calls;
}

const backend = (extra: Record<string, [number, unknown]> = {}) =>
  fakeBackend({
    [`GET ${CV}`]: [200, { cv: summary(), document: documentFixture(), verification_issues: [] }],
    [`GET ${CV}/layout`]: [200, layoutFixture()],
    "GET /api/profile": [200, profileFixture()],
    ...extra,
  });

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CvEditorTab cv={summary()} />
    </QueryClientProvider>,
  );
}

/** The desktop editor (the mobile layout renders a second editor, sharing the same draft). */
async function editor() {
  const [tabs] = await screen.findAllByRole("tablist", { name: "Sections du CV" });
  return within(tabs!.parentElement!);
}

// jsdom has no layout: every element measures 1000 × 600 px, and ResizeObserver (used by the split
// panels and the preview) reports that size once.
class FakeResizeObserver {
  constructor(private callback: ResizeObserverCallback) {}
  observe(target: Element) {
    // Like a browser: the first notification comes after the element is registered
    setTimeout(() => {
      const rect = target.getBoundingClientRect();
      this.callback(
        [
          {
            target,
            contentRect: rect,
            borderBoxSize: [{ inlineSize: rect.width, blockSize: rect.height }],
          },
        ] as never,
        this as never,
      );
    });
  }
  unobserve() {}
  disconnect() {}
}

/** DOMRect, used by the split panels, is missing from jsdom. */
class FakeDOMRect {
  constructor(
    public x = 0,
    public y = 0,
    public width = 0,
    public height = 0,
  ) {}
  get left() {
    return this.x;
  }
  get top() {
    return this.y;
  }
  get right() {
    return this.x + this.width;
  }
  get bottom() {
    return this.y + this.height;
  }
  toJSON() {
    return {};
  }
}

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as never;
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get: () => 1000,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get: () => 600,
  });
  Element.prototype.getBoundingClientRect = function () {
    return {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 1000,
      bottom: 600,
      width: 1000,
      height: 600,
      toJSON: () => ({}),
    };
  };
});

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("DOMRect", FakeDOMRect);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  pdf.getDocument.mockClear();
});

describe("CvEditorTab", () => {
  it("navigates between the seven sections on one line, with the keyboard too", async () => {
    backend();
    renderEditor();
    const panel = await editor();
    const tabs = panel.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual([
      "Profil",
      "Expériences2",
      "Formation1",
      "Projets1",
      "Compétences1",
      "Langues1",
      "Intérêts1",
    ]);
    // The tabs wrap with the width of the editor panel: never cut nor scrolled out of view
    expect(panel.getByRole("tablist")).toHaveClass("flex-wrap");
    expect(panel.getByRole("tablist")).not.toHaveClass("overflow-x-auto");
    // Only the selected section is in the Tab order (WAI-ARIA tabs)
    expect(tabs.map((t) => t.tabIndex)).toEqual([0, -1, -1, -1, -1, -1, -1]);

    fireEvent.click(tabs[1]!);
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    expect(panel.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", tabs[1]!.id);
    expect(panel.getByText("Stagiaire data")).toBeInTheDocument();

    fireEvent.keyDown(tabs[1]!, { key: "ArrowRight" });
    expect(tabs[2]).toHaveAttribute("aria-selected", "true");
    expect(tabs[2]).toHaveFocus();
    expect(panel.getByText("École Fictive")).toBeInTheDocument();
    fireEvent.keyDown(tabs[2]!, { key: "End" });
    expect(tabs[6]).toHaveFocus();
    fireEvent.keyDown(tabs[6]!, { key: "ArrowRight" });
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabs[0]!, { key: "ArrowLeft" });
    expect(tabs[6]).toHaveAttribute("aria-selected", "true");
  });

  it("enables « Enregistrer » only with changes, then saves them", async () => {
    const saved: CvDocument = { ...documentFixture() };
    saved.header = { ...saved.header, name: "Alex Nouveau" };
    const calls = backend({
      [`PUT ${CV}`]: [
        200,
        {
          cv: summary({ updated_at: 1792000300 }),
          document: saved,
          pages: 1,
          fits_one_page: true,
          has_layout: true,
        },
      ],
    });
    vi.spyOn(toast, "success").mockImplementation(() => "");
    renderEditor();
    const panel = await editor();
    const button = panel.getByRole("button", { name: "Enregistrer" });
    expect(button).toBeDisabled();
    expect(panel.getByRole("status")).toHaveTextContent("Enregistré");

    const name = panel.getByDisplayValue("Alex Exemple");
    fireEvent.change(name, { target: { value: "Alex Nouveau" } });
    expect(button).toBeEnabled();
    expect(panel.getByRole("status")).toHaveTextContent("Modifications non enregistrées");

    // « Annuler » goes back to the saved version
    fireEvent.click(panel.getByRole("button", { name: "Annuler" }));
    expect(panel.getByDisplayValue("Alex Exemple")).toBeInTheDocument();
    expect(button).toBeDisabled();

    fireEvent.change(panel.getByDisplayValue("Alex Exemple"), {
      target: { value: "Alex Nouveau" },
    });
    fireEvent.click(button);
    await waitFor(() => expect(panel.getByRole("status")).toHaveTextContent("Enregistré"));
    expect(button).toBeDisabled();
    const put = calls.find((c) => c.key === `PUT ${CV}`)!;
    expect((put.body as CvDocument).header.name).toBe("Alex Nouveau");
    expect(toast.success).toHaveBeenCalledWith("CV enregistré — le PDF a été recompilé.");
  });

  it("keeps the previous CV and the draft when saving fails (one page at most)", async () => {
    backend({
      [`PUT ${CV}`]: [
        422,
        { detail: { message: "Le CV dépasse une page", problems: ["2 pages après compilation"] } },
      ],
    });
    const error = vi.spyOn(toast, "error").mockImplementation(() => "");
    renderEditor();
    const panel = await editor();
    await waitFor(() => expect(pdf.getDocument).toHaveBeenCalledTimes(1));
    fireEvent.change(panel.getByDisplayValue("Alex Exemple"), {
      target: { value: "Alex Trop Long" },
    });
    fireEvent.click(panel.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => expect(error).toHaveBeenCalled());
    expect(String(error.mock.calls[0]![0])).toMatch(/Le CV dépasse une page/);
    expect(panel.getByDisplayValue("Alex Trop Long")).toBeInTheDocument();
    expect(panel.getByRole("status")).toHaveTextContent("Modifications non enregistrées");
    expect(panel.getByRole("button", { name: "Enregistrer" })).toBeEnabled();
    // The saved PDF is still the one shown: no new version was loaded
    expect(pdf.getDocument).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Dernière version enregistrée/)).toBeInTheDocument();
  });

  it("selects the matching entry when a zone of the PDF is clicked, and back", async () => {
    backend();
    renderEditor();
    const panel = await editor();
    const zone = await screen.findByRole("button", {
      name: "Sélectionner l'élément 2 dans les expériences",
    });
    fireEvent.click(zone);
    expect(panel.getByRole("tab", { name: /Expériences/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(panel.getByDisplayValue("Assistant")).toBeInTheDocument();
    // The selected zone is outlined lightly (no opaque fill over the text)
    expect(zone).toHaveClass("ring-2");
    expect(zone).not.toHaveClass("bg-primary/15");

    fireEvent.click(panel.getByRole("tab", { name: /Compétences/ }));
    const skills = screen.getByRole("button", { name: "Sélectionner les compétences et langues" });
    expect(skills).toHaveClass("ring-2");
    expect(zone).not.toHaveClass("ring-2");
  });

  it("shows the contacts right under the name and the summary, editable and removable", async () => {
    backend();
    renderEditor();
    const panel = await editor();
    const name = panel.getByDisplayValue("Alex Exemple");
    const summaryField = panel.getByDisplayValue(/Étudiant fictif/);
    const email = panel.getByRole("textbox", { name: "Email" });
    const github = panel.getByRole("textbox", { name: "GitHub" });
    expect(email).toHaveValue("alex@example.com");
    expect(github).toHaveValue("https://github.com/alex-exemple");
    // Order: Nom, Résumé, Coordonnées; nothing to unfold
    expect(
      name.compareDocumentPosition(summaryField) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      summaryField.compareDocumentPosition(email) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(panel.queryByRole("button", { name: /Coordonnées/ })).not.toBeInTheDocument();

    fireEvent.change(email, { target: { value: "alex@exemple.fr" } });
    expect(panel.getByRole("status")).toHaveTextContent("Modifications non enregistrées");
    fireEvent.click(panel.getByRole("button", { name: "Retirer GitHub" }));
    expect(panel.queryByRole("textbox", { name: "GitHub" })).not.toBeInTheDocument();
    expect(panel.getByRole("textbox", { name: "Email" })).toHaveValue("alex@exemple.fr");
  });

  it("keeps « Enregistrer » at the top of the editor, above the scrolling fields", async () => {
    backend();
    renderEditor();
    const panel = await editor();
    const save = panel.getByRole("button", { name: "Enregistrer" });
    const fields = panel.getByRole("tabpanel");
    // Before the section tabs and outside the scrolling area
    expect(
      save.compareDocumentPosition(panel.getByRole("tablist")) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(fields).toHaveClass("overflow-y-auto");
    expect(fields).not.toContainElement(save);
    expect(save).toBeDisabled();
  });

  it("splits editor and preview 40 / 60 with a focusable, labelled resize handle", async () => {
    backend();
    renderEditor();
    await editor();
    // Dragging, the keyboard (arrows, Home, End, Enter), the 30-65 % limits and the double-click reset
    // come from react-resizable-panels (ARIA separator); jsdom has no layout to run them, so only the
    // configuration is checked here: to try in the browser.
    const handle = screen.getByRole("separator", { name: "Redimensionner l'éditeur et l'aperçu" });
    expect(handle).toHaveAttribute("tabindex", "0");
    expect(handle).toHaveAttribute("title", expect.stringMatching(/double-clic/));
    const editorPanel = document.getElementById("cv-editor")!;
    const previewPanel = document.getElementById("cv-preview")!;
    expect(editorPanel).toContainElement(
      screen.getAllByRole("tablist", { name: "Sections du CV" })[0]!,
    );
    expect(previewPanel).toContainElement(screen.getAllByText(/Aperçu PDF/)[0]!);
    await waitFor(() => expect(editorPanel.style.flexGrow).toBe("40"));
    expect(previewPanel.style.flexGrow).toBe("60");

    // The PDF stays interactive inside its panel
    const zone = await within(previewPanel).findByRole("button", {
      name: "Sélectionner l'élément 1 dans les expériences",
    });
    fireEvent.click(zone);
    expect(zone).toHaveClass("ring-2");
  });

  it("stacks editor and preview behind two tabs below the desktop breakpoint, without the handle", async () => {
    backend();
    renderEditor();
    await editor();
    const desktop = screen.getByRole("separator").closest(".lg\\:block");
    expect(desktop).toHaveClass("hidden", "lg:block");
    const mobile = screen.getByRole("tab", { name: "Édition" }).closest(".lg\\:hidden");
    expect(mobile).not.toBeNull();
    expect(within(mobile as HTMLElement).queryByRole("separator")).not.toBeInTheDocument();
    // Desktop preview + mobile editor: one preview toolbar so far
    expect(screen.getAllByText(/Aperçu PDF/)).toHaveLength(1);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Aperçu" }));
    await waitFor(() => expect(screen.getAllByText(/Aperçu PDF/)).toHaveLength(2));
  });

  it("saves the new order of a skill group, other groups untouched, and shows it after a reload", async () => {
    const document: CvDocument = {
      ...documentFixture(),
      skills: [
        { label: "Langages", items: ["Python", "SQL", "Scala"] },
        { label: "Outils", items: ["Docker", "Git"] },
      ],
    };
    const reordered: CvDocument = {
      ...document,
      skills: [{ label: "Langages", items: ["Scala", "Python", "SQL"] }, document.skills[1]!],
    };
    const calls = backend({
      [`GET ${CV}`]: [200, { cv: summary(), document, verification_issues: [] }],
      [`PUT ${CV}`]: [
        200,
        { cv: summary(), document: reordered, pages: 1, fits_one_page: true, has_layout: true },
      ],
    });
    vi.spyOn(toast, "success").mockImplementation(() => "");
    const { unmount } = renderEditor();
    const panel = await editor();
    fireEvent.click(panel.getByRole("tab", { name: /Compétences/ }));
    const groups = () =>
      panel.getAllByRole("group").filter((g) => g.getAttribute("aria-roledescription"));
    const scala = panel.getByRole("group", { name: "Scala" });
    scala.focus();
    fireEvent.keyDown(scala, { key: " " });
    fireEvent.keyDown(scala, { key: "Home" });
    fireEvent.keyDown(scala, { key: " " });
    expect(groups().map((g) => g.getAttribute("aria-label"))).toEqual([
      "Scala",
      "Python",
      "SQL",
      "Docker",
      "Git",
    ]);
    expect(panel.getByRole("status")).toHaveTextContent("Modifications non enregistrées");

    fireEvent.click(panel.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(panel.getByRole("status")).toHaveTextContent("Enregistré"));
    const put = calls.find((c) => c.key === `PUT ${CV}`)!;
    expect((put.body as CvDocument).skills).toEqual(reordered.skills);

    // Reload: the saved order comes back from the backend as it is
    unmount();
    backend({
      [`GET ${CV}`]: [200, { cv: summary(), document: reordered, verification_issues: [] }],
    });
    renderEditor();
    const reloaded = await editor();
    fireEvent.click(reloaded.getByRole("tab", { name: /Compétences/ }));
    expect(
      reloaded
        .getAllByRole("group")
        .filter((g) => g.getAttribute("aria-roledescription"))
        .map((g) => g.getAttribute("aria-label")),
    ).toEqual(["Scala", "Python", "SQL", "Docker", "Git"]);
  });
});

describe("PdfPreview", () => {
  it("fits the page to the width of the preview, then keeps the user's zoom", async () => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(727);
    const props = { zones: [], selectedZoneId: null, onSelectZone: () => undefined };
    const { rerender } = render(<PdfPreview pdfUrl="/cv.pdf?v=1" {...props} />);
    // (727 - 32) / 595 = 1.17
    expect(await screen.findByText("117 %")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Zoom arrière" }));
    expect(screen.getByText("102 %")).toBeInTheDocument();
    // A new version (after a save) keeps the chosen zoom
    rerender(<PdfPreview pdfUrl="/cv.pdf?v=2" {...props} />);
    await waitFor(() => expect(pdf.getDocument).toHaveBeenCalledTimes(2));
    expect(screen.getByText("102 %")).toBeInTheDocument();
  });
});

describe("CvEditorTab — centres d'intérêt", () => {
  it("saves the new order of the interests, skills untouched, and shows it after a reload", async () => {
    const document: CvDocument = {
      ...documentFixture(),
      interests: ["Escalade", "Tennis", "Échecs"],
    };
    const reordered: CvDocument = { ...document, interests: ["Échecs", "Escalade", "Tennis"] };
    const calls = backend({
      [`GET ${CV}`]: [200, { cv: summary(), document, verification_issues: [] }],
      [`PUT ${CV}`]: [
        200,
        { cv: summary(), document: reordered, pages: 1, fits_one_page: true, has_layout: true },
      ],
    });
    vi.spyOn(toast, "success").mockImplementation(() => "");
    const { unmount } = renderEditor();
    const panel = await editor();
    fireEvent.click(panel.getByRole("tab", { name: /Intérêts/ }));
    const interests = (scope: typeof panel) =>
      scope
        .getAllByRole("group")
        .filter((g) => g.getAttribute("aria-roledescription") === "centre d'intérêt déplaçable")
        .map((g) => g.getAttribute("aria-label"));
    const chess = panel.getByRole("group", { name: "Échecs" });
    chess.focus();
    fireEvent.keyDown(chess, { key: "Enter" });
    fireEvent.keyDown(chess, { key: "Home" });
    fireEvent.keyDown(chess, { key: "Enter" });
    expect(interests(panel)).toEqual(["Échecs", "Escalade", "Tennis"]);

    fireEvent.click(panel.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(panel.getByRole("status")).toHaveTextContent("Enregistré"));
    const body = calls.find((c) => c.key === `PUT ${CV}`)!.body as CvDocument;
    expect(body.interests).toEqual(["Échecs", "Escalade", "Tennis"]);
    expect(body.skills).toEqual(document.skills);

    unmount();
    backend({
      [`GET ${CV}`]: [200, { cv: summary(), document: reordered, verification_issues: [] }],
    });
    renderEditor();
    const reloaded = await editor();
    fireEvent.click(reloaded.getByRole("tab", { name: /Intérêts/ }));
    expect(interests(reloaded)).toEqual(["Échecs", "Escalade", "Tennis"]);
  });
});

// ---------- « Vérifier » ----------

/** Fictional analysis linked to documentFixture() (exp-a mentions Spark, exp-b « Assistant »). */
function checkAnalysis(): CompletedAnalysis {
  const analysis = analysisFixture();
  const base = analysis.requirements[0]!;
  const cite = (type: Evidence["type"], id: string): Evidence => ({
    type,
    id,
    label: id,
    justification: "",
  });
  analysis.overview.technologies = ["Spark", "Docker"];
  analysis.overview.skills_sought = [];
  analysis.requirements = [
    {
      ...base,
      id: "r1",
      text: "Maîtrise de Spark",
      source: "must_have",
      importance: "high",
      status: "met",
      evidence: [cite("experience", "exp-a")],
    },
    {
      ...base,
      id: "r2",
      text: "Tableaux de bord pour les équipes",
      source: "must_have",
      importance: "high",
      status: "met",
      evidence: [cite("experience", "exp-b")],
    },
    {
      ...base,
      id: "r3",
      text: "Pratique de l'escalade",
      category: "preferred",
      source: "nice_to_have",
      importance: "normal",
      status: "met",
      evidence: [cite("interest", "Escalade")],
    },
    {
      ...base,
      id: "r4",
      text: "Expérience avec Docker",
      source: "must_have",
      importance: "normal",
      status: "partial",
      evidence: [cite("project", "proj-z")],
    },
    {
      ...base,
      id: "r5",
      text: "Connaissance de Kafka",
      source: "must_have",
      importance: "high",
      status: "not_documented",
      evidence: [],
    },
    {
      ...base,
      id: "r6",
      text: "Étudiant en dernière année",
      source: "must_have",
      importance: "normal",
      status: "met",
      evidence: [],
    },
  ];
  return analysis;
}

const desktopLeft = () => within(document.getElementById("cv-editor")!);

describe("CvEditorTab — « Vérifier »", () => {
  it("switches between « Modifier » and « Vérifier » without losing unsaved changes", async () => {
    backend({ [`GET ${CV}/analysis`]: [200, { ...checkAnalysis(), running: false }] });
    renderEditor();
    const panel = await editor();
    const left = desktopLeft();
    expect(left.getByRole("radio", { name: "Modifier" })).toHaveAttribute("data-state", "on");
    fireEvent.change(panel.getByDisplayValue("Alex Exemple"), {
      target: { value: "Alex Modifié" },
    });

    fireEvent.click(left.getByRole("radio", { name: "Vérifier" }));
    expect(await left.findByRole("region", { name: "Vérifier le CV" })).toBeVisible();
    expect(left.queryByRole("tablist", { name: "Sections du CV" })).not.toBeInTheDocument();
    expect(left.getByText(/version en cours de modification/)).toBeInTheDocument();
    // The PDF stays in its panel, interactive
    expect(
      within(document.getElementById("cv-preview")!).getAllByRole("button").length,
    ).toBeGreaterThan(0);

    fireEvent.click(left.getByRole("radio", { name: "Modifier" }));
    const back = await editor();
    expect(back.getByDisplayValue("Alex Modifié")).toBeInTheDocument();
    expect(back.getByRole("status")).toHaveTextContent("Modifications non enregistrées");
    expect(back.getByRole("button", { name: "Enregistrer" })).toBeEnabled();
  });

  it("lists the offer's points with their state, without conditions or undocumented ones", async () => {
    backend({ [`GET ${CV}/analysis`]: [200, { ...checkAnalysis(), running: false }] });
    renderEditor();
    await editor();
    fireEvent.click(desktopLeft().getByRole("radio", { name: "Vérifier" }));
    const check = within(await desktopLeft().findByRole("region", { name: "Vérifier le CV" }));
    const items = await check.findAllByRole("button", { expanded: false });
    expect(items.map((b) => b.textContent)).toEqual([
      expect.stringMatching(/^Maîtrise de SparkPrésentTrouvé : Spark/),
      expect.stringMatching(/^Tableaux de bord pour les équipesÀ vérifierUn élément cité/),
      expect.stringMatching(
        /^Expérience avec DockerNon mentionnéTon profil le documente.*Non trouvé : Docker/,
      ),
      expect.stringMatching(/^Pratique de l'escaladePrésentTrouvé : Escalade/),
    ]);
    expect(check.queryByText(/Kafka/)).not.toBeInTheDocument();
    expect(check.queryByText(/Étudiant/)).not.toBeInTheDocument();
    expect(check.getByText(/ne veut pas dire que la compétence manque/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/score/i);
  });

  it("highlights the section of a point in the PDF, then opens it in the editor on request", async () => {
    backend({ [`GET ${CV}/analysis`]: [200, { ...checkAnalysis(), running: false }] });
    renderEditor();
    await editor();
    const zone = await screen.findByRole("button", {
      name: "Sélectionner l'élément 1 dans les expériences",
    });
    fireEvent.click(desktopLeft().getByRole("radio", { name: "Vérifier" }));
    const check = within(await desktopLeft().findByRole("region", { name: "Vérifier le CV" }));
    const spark = await check.findByRole("button", { name: /^Maîtrise de Spark/ });
    expect(zone).not.toHaveClass("ring-2");
    fireEvent.click(spark);
    expect(spark).toHaveAttribute("aria-expanded", "true");
    expect(zone).toHaveClass("ring-2");
    expect(
      check.getByText(
        /Section surlignée dans l'aperçu \(l'emplacement de la section, pas du mot\)/,
      ),
    ).toBeInTheDocument();
    expect(
      check.getByRole("button", { name: "Expérience · Stagiaire data — Société A" }),
    ).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(check.getByRole("button", { name: "Modifier cette section" }));
    const panel = await editor();
    expect(desktopLeft().getByRole("radio", { name: "Modifier" })).toHaveAttribute(
      "data-state",
      "on",
    );
    expect(panel.getByRole("tab", { name: /Expériences/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(panel.getByDisplayValue("Stagiaire data")).toBeInTheDocument();
  });

  it("opens and closes a point like an accordion, removing its highlight, keeping the draft", async () => {
    backend({ [`GET ${CV}/analysis`]: [200, { ...checkAnalysis(), running: false }] });
    renderEditor();
    const panel = await editor();
    fireEvent.change(panel.getByDisplayValue("Alex Exemple"), {
      target: { value: "Alex Modifié" },
    });
    const first = await screen.findByRole("button", {
      name: "Sélectionner l'élément 1 dans les expériences",
    });
    const second = screen.getByRole("button", {
      name: "Sélectionner l'élément 2 dans les expériences",
    });
    fireEvent.click(desktopLeft().getByRole("radio", { name: "Vérifier" }));
    const check = within(await desktopLeft().findByRole("region", { name: "Vérifier le CV" }));
    const spark = await check.findByRole("button", { name: /^Maîtrise de Spark/ });
    const dashboards = check.getByRole("button", { name: /^Tableaux de bord/ });
    const edit = () => check.queryAllByRole("button", { name: "Modifier cette section" });

    // First click: open, with its details under it and its highlight
    fireEvent.click(spark);
    expect(spark).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById(spark.getAttribute("aria-controls")!)).toBeInTheDocument();
    expect(edit()).toHaveLength(1);
    expect(first).toHaveClass("ring-2");

    // Another point: the previous one closes, the new one opens
    fireEvent.click(dashboards);
    expect(spark).toHaveAttribute("aria-expanded", "false");
    expect(dashboards).toHaveAttribute("aria-expanded", "true");
    expect(edit()).toHaveLength(1);
    expect(first).not.toHaveClass("ring-2");
    expect(second).toHaveClass("ring-2");

    // Same point again: closed, nothing highlighted any more
    fireEvent.click(dashboards);
    expect(dashboards).toHaveAttribute("aria-expanded", "false");
    expect(edit()).toHaveLength(0);
    expect(document.getElementById("cv-preview")!.querySelector(".ring-2")).toBeNull();

    // The PDF stays interactive and the draft is intact
    fireEvent.click(first);
    const back = await editor();
    expect(back.getByDisplayValue("Stagiaire data")).toBeInTheDocument();
    fireEvent.click(back.getByRole("tab", { name: "Profil" }));
    expect(back.getByDisplayValue("Alex Modifié")).toBeInTheDocument();
    expect(back.getByRole("status")).toHaveTextContent("Modifications non enregistrées");
  });

  it("highlights nothing when the place of a point is not known in the PDF", async () => {
    backend({ [`GET ${CV}/analysis`]: [200, { ...checkAnalysis(), running: false }] });
    renderEditor();
    await editor();
    await screen.findByRole("button", { name: "Sélectionner l'élément 1 dans les expériences" });
    fireEvent.click(desktopLeft().getByRole("radio", { name: "Vérifier" }));
    const check = within(await desktopLeft().findByRole("region", { name: "Vérifier le CV" }));
    // The interests have no zone in layout.json; Docker is not in the CV at all
    fireEvent.click(await check.findByRole("button", { name: /^Pratique de l'escalade/ }));
    expect(check.getByText("Emplacement non identifié dans l'aperçu.")).toBeInTheDocument();
    const preview = document.getElementById("cv-preview")!;
    expect(preview.querySelector(".ring-2")).toBeNull();
    fireEvent.click(check.getByRole("button", { name: /^Expérience avec Docker/ }));
    expect(check.getByText("Emplacement non identifié dans l'aperçu.")).toBeInTheDocument();
    expect(check.queryByRole("button", { name: "Modifier cette section" })).not.toBeInTheDocument();
    expect(preview.querySelector(".ring-2")).toBeNull();
  });

  it("opens the editor on the part clicked in the PDF, from « Vérifier » too", async () => {
    backend({ [`GET ${CV}/analysis`]: [200, { ...checkAnalysis(), running: false }] });
    renderEditor();
    await editor();
    fireEvent.click(desktopLeft().getByRole("radio", { name: "Vérifier" }));
    await desktopLeft().findByRole("region", { name: "Vérifier le CV" });
    fireEvent.click(
      await screen.findByRole("button", { name: "Sélectionner l'élément 2 dans les expériences" }),
    );
    const panel = await editor();
    expect(panel.getByDisplayValue("Assistant")).toBeInTheDocument();
  });

  it("explains when the analysis of the offer is not available, without starting it", async () => {
    const calls = backend({
      [`GET ${CV}/analysis`]: [
        404,
        { detail: { message: "Analyse non disponible", problems: [] } },
      ],
    });
    renderEditor();
    await editor();
    fireEvent.click(desktopLeft().getByRole("radio", { name: "Vérifier" }));
    expect(
      await desktopLeft().findByText(/Lance-la depuis l'onglet « Vue d'ensemble »/),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.key.startsWith("POST"))).toBe(false);
    expect(calls.some((c) => c.key.startsWith("PUT"))).toBe(false);
  });

  it("offers the same switch on small screens, in the « Édition » tab", async () => {
    backend({ [`GET ${CV}/analysis`]: [200, { ...checkAnalysis(), running: false }] });
    renderEditor();
    await editor();
    const mobile = within(
      screen.getByRole("tab", { name: "Édition" }).closest(".lg\\:hidden") as HTMLElement,
    );
    fireEvent.click(mobile.getByRole("radio", { name: "Vérifier" }));
    expect(await mobile.findByRole("region", { name: "Vérifier le CV" })).toBeInTheDocument();
    expect(mobile.getByRole("tab", { name: "Aperçu" })).toBeInTheDocument();
  });
});
