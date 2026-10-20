# CV — génération LaTeX

Génère un CV en LaTeX, adapté à une offre d'emploi, à partir de
`profile/private/candidate.yaml` (source de vérité) et de l'analyse de
l'offre. Le pipeline complet est décrit dans le [README principal](../README.md) ;
cette page détaille le template et la compilation.

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
├── reference/              # facultatif — anciens CV (.tex) servant de modèles de style — PAS VERSIONNÉ
└── applications/           # un sous-dossier par CV généré — PAS VERSIONNÉ (données perso)
    └── <company>-<role>/
        ├── <Prénom>_<Nom>_Candidature_<Company>_<Role>.tex
        ├── sections/*.tex
        ├── build/            # généré par latexmk (dont le PDF)
        ├── offer.json        # offre analysée
        └── selection.json    # choix de Claude + vérification
```

`build_cv.py` copie `template/` dans `applications/<company>-<role>/`
(avec un suffixe `-2`, `-3`… si le dossier existe déjà), renomme `main.tex`
et remplace les fichiers de `sections/` par ceux générés par Claude.

Le nom du fichier `.tex` pilote le nom du PDF compilé (latexmk compile
`<nom>.tex` en `<nom>.pdf`) : `<Prénom>_<Nom>_Candidature_<Entreprise>_<Poste>.tex`
→ `<Prénom>_<Nom>_Candidature_<Entreprise>_<Poste>.pdf`. Le prénom et le nom
viennent de `personal.first_name` / `personal.last_name` du profil.

`cv/reference/` et `cv/applications/` sont dans `.gitignore` : tout ce qui
contient des données personnelles reste strictement local. Seul
`cv/template/` (aucune donnée perso) est versionné.

## Style

Classe `article`, mise en page compacte façon "one-page resume" :
`titlesec`, `fontawesome5`, `tabularx`, `enumitem`, macros perso
(`\resumeItem`, `\resumeItemPlain`, `\resumeItemListStart/End`...) définies
dans `template/main.tex`. Pas de photo (CV professionnel international).

Les fichiers `.tex` de `cv/reference/` (sous-dossiers compris) sont envoyés à
Claude comme exemples de style et de mise en page uniquement, jamais comme
source d'informations sur le candidat. Sans ce dossier, le CV est généré à
partir du template seul.

## Compilation

`build_cv.py` lance, dans le dossier du CV :

```bash
latexmk -pdf -interaction=nonstopmode -file-line-error -outdir=build <nom>.tex
```

puis lit le nombre de pages dans le journal LaTeX (`build/<nom>.log`) :
`main.py` affiche un avertissement si le CV dépasse une page.

### Recompiler après une retouche à la main

```bash
cd cv/applications/<company>-<role>
latexmk -pdf -interaction=nonstopmode -file-line-error -synctex=1 -outdir=build <Prénom>_<Nom>_Candidature_<Entreprise>_<Poste>.tex
```

Dans VS Code (extension **LaTeX Workshop**), la compilation se relance
automatiquement à chaque sauvegarde d'un `.tex` (`.vscode/settings.json`).

Pour nettoyer les fichiers auxiliaires :
```bash
latexmk -c -outdir=build <Prénom>_<Nom>_Candidature_<Entreprise>_<Poste>.tex
```
