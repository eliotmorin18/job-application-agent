"""
Données fictives partagées par les tests du CV structuré (profil d'exemple John Doe).
Pas un module de test : aucun test n'y est lancé.
"""

import copy

from candidate.profile import EXAMPLE_PATH, load_profile


def example_profile():
    return load_profile(EXAMPLE_PATH)


# Réponse de Claude telle que CLAUDE_SCHEMA l'impose (taille réaliste pour un CV d'une page)
_DRAFT = {
    "company": "Acme Robotics",
    "role": "Stage Vision par Ordinateur",
    "language": "fr",
    "summary": "Jeune diplômé en informatique et IA, avec une expérience de **vision par ordinateur** "
               "appliquée à des images réelles (détection, segmentation). Curieux et rigoureux, "
               "intéressé par la robotique.",
    "experiences": [
        {"source_id": "example-research-company", "title": "Stagiaire Vision par Ordinateur",
         "organization": "Example Research Company", "context": "Recherche appliquée",
         "bullets": ["Évaluation d'architectures de détection d'objets (YOLO) et constitution de jeux de données annotés.",
                     "Amélioration du mAP de 0,61 à 0,74 sur le jeu de test interne ; 2 000 images annotées réutilisées par l'équipe."]},
        {"source_id": "example-software-company", "title": "Stagiaire Développeur Logiciel",
         "organization": "Example Software Company", "context": None,
         "bullets": ["Intégration d'une API de LLM et de workflows d'appel d'outils dans une plateforme existante.",
                     "Assistant adopté par l'équipe support pour ses opérations quotidiennes."]},
    ],
    "education": [
        {"source_id": "example-engineering-school", "institution": "Example Engineering School",
         "bullets": ["Diplôme d'ingénieur (niveau Master), spécialisation Informatique et Intelligence Artificielle.",
                     "**Matières principales :** Machine Learning, Computer Vision, Data Science, Optimisation."]},
        {"source_id": "example-university", "institution": "Example University",
         "bullets": ["Échange académique : Computer Vision, bio-informatique, analyse topologique des données."]},
    ],
    "projects": [
        {"source_id": "multi-agent-system", "name": "Système Multi-Agents Autonome",
         "bullets": ["Conception et simulation d'une stratégie de coordination d'agents avec décision prédictive.",
                     "Interception de tous les attaquants dans les scénarios simulés 3 contre 5."]},
        {"source_id": "face-recognition", "name": "Pipeline de Reconnaissance Faciale",
         "bullets": ["Détection de visages, comparaison de descripteurs visuels et identification : 92 % en Rank-1."]},
    ],
    "skills": [
        {"label": "Programmation", "items": ["Python", "SQL", "Bash", "Julia"]},
        {"label": "Vision par ordinateur", "items": ["YOLO", "OpenCV", "Détection d'objets", "Segmentation"]},
        {"label": "Machine Learning", "items": ["PyTorch", "Scikit-learn", "Transformers"]},
        {"label": "Outils", "items": ["Git", "Docker", "Linux", "Jupyter"]},
    ],
    "languages": [{"name": "Français", "level": "langue maternelle"}, {"name": "Anglais", "level": "courant"},
                  {"name": "Espagnol", "level": "notions"}],
    "interests": ["Tennis", "Football", "Course à pied", "Guitare"],
    "gaps": ["Pas d'expérience en robotique industrielle."],
}


def fake_draft() -> dict:
    return copy.deepcopy(_DRAFT)
