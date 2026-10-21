import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: "/candidat", search: { tab: "experiences" } });
  },
  head: () => ({
    meta: [
      { title: "Job Application Agent" },
      { name: "description", content: "Gérez votre profil candidat et préparez des candidatures sur mesure." },
      { property: "og:title", content: "Job Application Agent" },
      { property: "og:description", content: "Gérez votre profil candidat et préparez des candidatures sur mesure." },
    ],
  }),
});
