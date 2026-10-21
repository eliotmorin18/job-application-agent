import { createFileRoute } from "@tanstack/react-router";

import { ImportPage } from "@/features/import/ImportPage";

export const Route = createFileRoute("/candidat/import")({
  head: () => ({
    meta: [
      { title: "Importer un CV — Job Application Agent" },
      {
        name: "description",
        content: "Importez un CV PDF et choisissez les informations à ajouter à votre profil.",
      },
    ],
  }),
  component: ImportPage,
});
