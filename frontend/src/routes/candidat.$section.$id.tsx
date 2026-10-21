import { createFileRoute, notFound } from "@tanstack/react-router";

import { ItemDetailPage } from "@/features/candidate/pages/ItemDetailPage";
import { isItemSection } from "@/features/candidate/sectionConfig";

export const Route = createFileRoute("/candidat/$section/$id")({
  beforeLoad: ({ params }) => {
    if (!isItemSection(params.section)) throw notFound();
  },
  head: () => ({
    meta: [
      { title: "Détail du profil — Job Application Agent" },
      { name: "description", content: "Consultez et modifiez un élément de votre profil candidat." },
      { property: "og:title", content: "Détail du profil — Job Application Agent" },
      { property: "og:description", content: "Consultez et modifiez un élément de votre profil candidat." },
    ],
  }),
  component: DetailRoute,
});

function DetailRoute() {
  const { section, id } = Route.useParams();
  if (!isItemSection(section)) return null;
  return <ItemDetailPage section={section} id={id} />;
}
