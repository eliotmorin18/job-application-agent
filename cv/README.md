# CV — génération LaTeX

Génère un CV en LaTeX, adapté à une offre d'emploi, à partir de
`profile/private/candidate.yaml` (source de vérité) et de l'analyse de
l'offre. Le pipeline complet est décrit dans le [README principal](../README.md) ;
cette page détaille le template et la compilation.

## Structure

```
cv/
├── cli.py                 # point d'entrée : python -m cv.cli "<URL>" (offre → CV PDF)
├── pipeline.py            # le pipeline complet, utilisé par la CLI et par l'API (api/cvs.py)
├── generate.py            # Claude choisit les éléments du profil et rédige le contenu (JSON)
├── verify.py              # Claude vérifie le contenu du CV contre le profil
├── document.py            # CV structuré (cv.json) : schéma, construction, validation, sauvegarde
├── render.py              # cv.json -> les six sections LaTeX du template
├── layout.py              # zones cliquables du PDF (build/layout.json)
├── build_cv.py            # écrit le dossier du CV + compile (appelé par cli.py)
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
        ├── cv.json           # contenu du CV : la référence (sections/*.tex en sont calculées)
        ├── sections/*.tex
        ├── build/            # généré par latexmk (dont le PDF et layout.json)
        ├── offer.json        # offre analysée
        └── selection.json    # choix de Claude + vérification
```

`build_cv.py` copie `template/` dans `applications/<company>-<role>/`
(avec un suffixe `-2`, `-3`… si le dossier existe déjà), renomme `main.tex`,
enregistre `cv.json` et remplace les fichiers de `sections/` par ceux calculés
à partir de `cv.json` par `render.py`.

## Du JSON au LaTeX

Claude ne produit plus de LaTeX : il renvoie le contenu du CV (résumé, éléments
choisis avec leur `source_id`, puces, compétences, langues, centres d'intérêt).
`document.py` y ajoute ce qui vient du profil — nom, contacts, dates (années :
« 2024–2025 »), lieux courts (« Paris ») et liens GitHub — enregistré comme
instantané dans `cv.json`. Les formations sans `id` dans le profil reçoivent un
identifiant calculé à partir de l'école (le même que donnerait
`manager.assign_missing_ids()`), sans modifier le profil.

`render.py` convertit `cv.json` avec les macros du template et écrit les titres
de section dans la langue du CV. Tout le texte est échappé (`& % $ # _ { } ~ ^ \
< > |`, « » → “ ”, € → EUR) ; la seule mise en forme permise est `**gras**`.
Une liste vide masque la section dans le PDF.

Pour modifier un CV : changer `cv.json` (ajouter, retirer, réordonner des
éléments ou des puces), puis `build_cv.rebuild_cv(<dossier>)` réécrit les
sections et recompile. Les CV créés avant `cv.json` ne sont pas concernés.

Le nom du fichier `.tex` pilote le nom du PDF compilé (latexmk compile
`<nom>.tex` en `<nom>.pdf`) : `<Prénom>_<Nom>_Candidature_<Entreprise>_<Poste>.tex`
→ `<Prénom>_<Nom>_Candidature_<Entreprise>_<Poste>.pdf`. Le prénom et le nom
viennent de `personal.first_name` / `personal.last_name` du profil.

`cv/reference/` et `cv/applications/` sont dans `.gitignore` : tout ce qui
contient des données personnelles reste strictement local. Seul
`cv/template/` (aucune donnée perso) est versionné.

## Zones cliquables (futur éditeur)

Des marqueurs invisibles `\cvanchor{clé}` (définis dans `template/main.tex`, placés par
`render.py` dans le nom, les titres de section et l'en-tête de chaque élément) notent leur
page et leur position pendant la compilation (pdfTeX, fichier `build/<nom>.cvpos`). Ils
n'affichent rien et n'occupent aucune place : le PDF est identique au point près.

Après chaque compilation réussie, `compile_cv` écrit `build/layout.json` (via `layout.py`) :
une zone par section et par élément, en coordonnées normalisées (0 à 1, origine en haut à
gauche), avec sa page et la partie de `cv.json` qu'elle représente :

| Clé | Partie de `cv.json` |
|---|---|
| `profile` | `header` (nom, contacts, résumé) |
| `experiences`, `experiences/0`… | `experiences`, `experiences[0]`… |
| `education`, `education/0`… | `education`, `education[0]`… |
| `projects`, `projects/0`… | `projects`, `projects[0]`… |
| `skills` | `skills` et `languages` |
| `interests` | `interests` |

Une section vide n'a pas de zone ; une zone coupée par un saut de page donne une zone par
page. Un clic sur un élément l'emporte sur sa section (`layout.region_at`). L'ancien
`layout.json` est supprimé avant chaque compilation : un échec n'en laisse jamais
d'obsolète. Les CV créés avant les marqueurs se compilent comme avant, sans `layout.json`.

## Style

Classe `article`, mise en page compacte façon "one-page resume" :
`titlesec`, `fontawesome5`, `tabularx`, `enumitem`, macros perso
(`\resumeItem`, `\resumeItemPlain`, `\resumeItemListStart/End`...) définies
dans `template/main.tex`. Pas de photo (CV professionnel international).

Les fichiers `sections/*.tex` du template ne sont plus envoyés à Claude : ils
restent des exemples de la mise en page reproduite par `render.py`.

Les fichiers `.tex` de `cv/reference/` (sous-dossiers compris) sont envoyés à
Claude comme exemples de style et de ton uniquement, jamais comme
source d'informations sur le candidat. Sans ce dossier, le CV est généré à
partir du template seul.

## Compilation

`build_cv.py` lance, dans le dossier du CV :

```bash
latexmk -pdf -interaction=nonstopmode -file-line-error -outdir=build <nom>.tex
```

puis lit le nombre de pages dans le journal LaTeX (`build/<nom>.log`) :
`cli.py` affiche un avertissement si le CV dépasse une page.

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
