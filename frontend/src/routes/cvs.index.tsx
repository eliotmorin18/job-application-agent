import { createFileRoute } from "@tanstack/react-router";

import { CvListPage } from "@/features/cvs/pages/CvListPage";

export const Route = createFileRoute("/cvs/")({
  head: () => ({
    meta: [
      { title: "Mes CV — Job Application Agent" },
      {
        name: "description",
        content:
          "Retrouvez les CV générés pour chaque candidature, avec leur analyse d'adéquation.",
      },
      { property: "og:title", content: "Mes CV — Job Application Agent" },
      {
        property: "og:description",
        content:
          "Retrouvez les CV générés pour chaque candidature, avec leur analyse d'adéquation.",
      },
    ],
  }),
  component: CvListPage,
});
