# CV — génération LaTeX

Génère un CV en LaTeX, adapté à une offre d'emploi, à partir de
`profile/private/candidate.yaml` (source de vérité) et de l'analyse de
l'offre (sortie de `main.py` / `llm/analyze_job.py`).

## Structure

```
cv/
├── build_cv.py            # écrit les sections générées + compile (appelé par main.py)
├── template/              # squelette LaTeX générique (versionné sur git)
│   ├── main.tex                      # préambule, packages, macros, assemblage
│   └── sections/
│       ├── heading.tex
│       ├── experience.tex
│       ├── education.tex
│       ├── projects.tex
│       ├── technical-skills.tex
│       └── interests.tex
├── reference/              # CVs de référence — PAS VERSIONNÉ (données perso / pas les nôtres)
│   ├── <CV externe>.pdf    # style d'origine, pas nos données
│   ├── CV_anglais/         # ancien CV généraliste anglais (tex + pdf)
│   ├── CV_fr/              # ancien CV généraliste français (tex + pdf)
│   └── harmattan/          # 3 variantes déjà tailorées par rôle (tex + pdf)
│       ├── computer-vision/
│       ├── data-engineering/
│       └── product-operations/
└── applications/            # un sous-dossier par candidature — PAS VERSIONNÉ (données perso)
    └── <company>-<role>/
        ├── Eliot_Morin_Candidature_<Company>_<Role>.tex
        ├── sections/*.tex
        ├── build/            # généré par latexmk
        ├── offer.json        # offre analysée
        └── selection.json    # choix de Claude + vérification
```

Le nom du fichier `.tex` pilote le nom du PDF compilé (latexmk compile
`<nom>.tex` en `<nom>.pdf`). Par convention : `Eliot_Morin_Candidature_<Entreprise>_<Poste>.tex`
→ `Eliot_Morin_Candidature_<Entreprise>_<Poste>.pdf` (jamais `main.pdf`).

`cv/reference/` et `cv/applications/` sont dans `.gitignore` : le repo est
public, donc tout ce qui contient des données personnelles (CV réels
générés, PDF d'exemple qui n'est pas le nôtre) reste strictement local.
Seul `cv/template/` (aucune donnée perso) est versionné.

## Style

Classe `article`, mise en page compacte façon "one-page resume" :
`titlesec`, `fontawesome5`, `tabularx`, `enumitem`, macros perso
(`\resumeItem`, `\resumeItemPlain`, `\resumeItemListStart/End`...) définies
dans `template/main.tex`. Pas de photo (CV professionnel international).

## Workflow

Tout est automatique, une seule commande depuis la racine du projet :

```bash
python main.py "<URL de l'offre>"
```

1. **Lecture** de la page de l'offre (`browser/read_job.py`).
2. **Analyse** de l'offre par Claude → JSON structuré (`llm/analyze_job.py`).
3. **Rédaction** du CV par Claude (`llm/generate_cv.py`), à partir de
   l'offre, de `profile/private/candidate.yaml` (seule source de vérité),
   de `cv/template/` et des CVs de `cv/reference/` (pour le style
   uniquement). Claude choisit au plus `application_rules.max_cv_experiences`
   expériences et `max_cv_projects` projets.
4. **Vérification** (`llm/verify_cv.py`) : un second appel à Claude, qui ne
   voit pas l'offre, relit chaque phrase du CV et signale tout ce qui n'est
   pas dans `candidate.yaml`. Si besoin, le CV est réécrit (2 fois max) ;
   s'il reste des problèmes, ils sont affichés en gros dans le terminal.
5. **Création et compilation** (`cv/build_cv.py`) : copie de `cv/template/`
   dans `cv/applications/<company>-<role>/`, écriture des sections, puis
   compilation avec `latexmk`.

Résultat dans `cv/applications/<company>-<role>/` :
- `build/Eliot_Morin_Candidature_<Entreprise>_<Poste>.pdf` : le CV
- `offer.json` : l'offre analysée
- `selection.json` : expériences/projets choisis, points de l'offre non
  couverts par le profil (`gaps`), problèmes restants de la vérification

Relire le CV avant de l'envoyer reste indispensable.

### Recompiler après une retouche à la main

```bash
cd cv/applications/<company>-<role>
latexmk -pdf -interaction=nonstopmode -file-line-error -synctex=1 -outdir=build Eliot_Morin_Candidature_<Entreprise>_<Poste>.tex
```

Dans VS Code (extension **LaTeX Workshop**, requise), la compilation se
relance automatiquement à chaque sauvegarde d'un `.tex`
(`.vscode/settings.json`).

Pour nettoyer les fichiers auxiliaires :
```bash
latexmk -c -outdir=build Eliot_Morin_Candidature_<Entreprise>_<Poste>.tex
```
