import { Briefcase, FolderGit2, GraduationCap, type LucideIcon } from "lucide-react";

import type { Education, Experience, ItemSection, Project, SectionItem } from "@/services/api/types";
import { formatRange } from "./format";

export type FieldType = "text" | "textarea" | "date" | "list" | "tags" | "priority" | "url";

export interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  required?: boolean | undefined;
  placeholder?: string | undefined;
}

export interface CardSummary {
  title: string;
  subtitle?: string | undefined;
  meta: string[];
  description?: string | undefined;
  tags: string[];
}

export interface SectionConfig {
  label: string;
  singular: string;
  addLabel: string;
  backLabel: string;
  emptyTitle: string;
  emptyText: string;
  createdMessage: string;
  updatedMessage: string;
  deletedMessage: string;
  icon: LucideIcon;
  fields: FieldDef[];
  summary: (item: SectionItem) => CardSummary;
}

const sharedRichFields: FieldDef[] = [
  { key: "context", label: "Contexte", type: "textarea", placeholder: "Environnement, équipe, enjeux…" },
  { key: "description", label: "Description", type: "textarea" },
  { key: "responsibilities", label: "Missions", type: "list", placeholder: "Décrire une mission" },
  { key: "achievements", label: "Réalisations", type: "list", placeholder: "Résultat concret, chiffré si possible" },
  { key: "skills", label: "Compétences", type: "tags", placeholder: "Ajouter une compétence puis Entrée" },
];

const dates: FieldDef[] = [
  { key: "start_date", label: "Date de début", type: "date", placeholder: "AAAA ou AAAA-MM" },
  { key: "end_date", label: "Date de fin", type: "date", placeholder: "AAAA ou AAAA-MM" },
];

export const sectionConfig: Record<ItemSection, SectionConfig> = {
  experiences: {
    label: "Expériences",
    singular: "expérience",
    addLabel: "Ajouter une expérience",
    backLabel: "Retour aux expériences",
    emptyTitle: "Aucune expérience pour le moment",
    emptyText: "Ajoutez vos expériences professionnelles, stages ou missions bénévoles.",
    createdMessage: "Expérience ajoutée",
    updatedMessage: "Expérience mise à jour",
    deletedMessage: "Expérience supprimée",
    icon: Briefcase,
    fields: [
      { key: "title", label: "Poste", type: "text", required: true, placeholder: "Ex. Data Scientist" },
      { key: "company", label: "Entreprise", type: "text", required: true },
      ...dates,
      { key: "location", label: "Lieu", type: "text", placeholder: "Ville, pays" },
      ...sharedRichFields,
      { key: "priority", label: "Priorité", type: "priority" },
      { key: "tags", label: "Tags", type: "tags", placeholder: "Ajouter un tag puis Entrée" },
    ],
    summary: (item) => {
      const e = item as Experience;
      return {
        title: e.title,
        subtitle: e.company,
        meta: [e.location, formatRange(e.start_date, e.end_date)].filter(Boolean) as string[],
        tags: e.skills ?? [],
      };
    },
  },
  education: {
    label: "Formations",
    singular: "formation",
    addLabel: "Ajouter une formation",
    backLabel: "Retour aux formations",
    emptyTitle: "Aucune formation pour le moment",
    emptyText: "Ajoutez vos diplômes, échanges universitaires et certifications.",
    createdMessage: "Formation ajoutée",
    updatedMessage: "Formation mise à jour",
    deletedMessage: "Formation supprimée",
    icon: GraduationCap,
    fields: [
      { key: "school", label: "École", type: "text", required: true },
      { key: "degree", label: "Diplôme", type: "text" },
      { key: "specialization", label: "Spécialisation", type: "text" },
      ...dates,
      { key: "location", label: "Lieu", type: "text", placeholder: "Ville, pays" },
      { key: "details", label: "Détails", type: "list", placeholder: "Cours, mention, projet…" },
    ],
    summary: (item) => {
      const e = item as Education;
      return {
        title: e.degree || e.school,
        subtitle: e.degree ? e.school : undefined,
        description: e.specialization,
        meta: [e.location, formatRange(e.start_date, e.end_date, "En cours")].filter(Boolean) as string[],
        tags: [],
      };
    },
  },
  projects: {
    label: "Projets",
    singular: "projet",
    addLabel: "Ajouter un projet",
    backLabel: "Retour aux projets",
    emptyTitle: "Aucun projet pour le moment",
    emptyText: "Mettez en avant vos projets personnels, académiques ou open source.",
    createdMessage: "Projet ajouté",
    updatedMessage: "Projet mis à jour",
    deletedMessage: "Projet supprimé",
    icon: FolderGit2,
    fields: [
      { key: "name", label: "Nom du projet", type: "text", required: true },
      ...dates,
      ...sharedRichFields,
      { key: "github_url", label: "Lien GitHub", type: "url", placeholder: "https://github.com/…" },
      { key: "priority", label: "Priorité", type: "priority" },
      { key: "tags", label: "Tags", type: "tags", placeholder: "Ajouter un tag puis Entrée" },
    ],
    summary: (item) => {
      const p = item as Project;
      return {
        title: p.name,
        description: p.description,
        meta: [formatRange(p.start_date, p.end_date, "En cours")].filter(Boolean) as string[],
        tags: p.skills ?? [],
      };
    },
  },
};

export const ITEM_SECTIONS = Object.keys(sectionConfig) as ItemSection[];

export function isItemSection(v: string): v is ItemSection {
  return v in sectionConfig;
}
