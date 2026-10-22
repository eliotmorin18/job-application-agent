import { createFileRoute } from "@tanstack/react-router";

import { CvListPage } from "@/features/cvs/pages/CvListPage";

export const Route = createFileRoute("/cvs/")({
  head: () => ({
    meta: [
      { title: "Mes candidatures — Job Application Agent" },
      {
        name: "description",
        content:
          "Préparez une candidature pour chaque offre : analyse du poste, préparation à l'entretien et CV adapté.",
      },
      { property: "og:title", content: "Mes candidatures — Job Application Agent" },
      {
        property: "og:description",
        content:
          "Préparez une candidature pour chaque offre : analyse du poste, préparation à l'entretien et CV adapté.",
      },
    ],
  }),
  component: CvListPage,
});
