import { createFileRoute } from "@tanstack/react-router";

import { CV_DETAIL_TABS, CvDetailPage, type CvDetailTab } from "@/features/cvs/pages/CvDetailPage";

export const Route = createFileRoute("/cvs/$cvId")({
  validateSearch: (search: Record<string, unknown>): { tab: CvDetailTab } => ({
    tab: CV_DETAIL_TABS.includes(search["tab"] as CvDetailTab)
      ? (search["tab"] as CvDetailTab)
      : "analyse",
  }),
  head: () => ({
    meta: [
      { title: "Candidature — Job Application Agent" },
      {
        name: "description",
        content: "Analysez l'adéquation de l'offre et retouchez le CV généré.",
      },
      { property: "og:title", content: "Candidature — Job Application Agent" },
      {
        property: "og:description",
        content: "Analysez l'adéquation de l'offre et retouchez le CV généré.",
      },
    ],
  }),
  component: CvDetailRoute,
});

function CvDetailRoute() {
  const { cvId } = Route.useParams();
  const { tab } = Route.useSearch();
  return <CvDetailPage cvId={cvId} tab={tab} />;
}
