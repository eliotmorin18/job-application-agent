# CV — génération LaTeX

Génère un CV en LaTeX, adapté à une offre d'emploi, à partir de
`profile/private/candidate.yaml` (source de vérité) et de l'analyse de
l'offre. Le pipeline complet est décrit dans le [README principal](../README.md) ;
cette page détaille le template et la compilation.

## Structure

```
cv/
├── *.py                   # modules Python : voir « Project structure » dans le README principal
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
        ├── selection.json    # choix de Claude + vérification
        ├── analysis.json     # analyse de correspondance offre / profil (si faite)
        └── metadata.json     # dates de création et de modification (CV créés après son ajout)
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

Pour modifier un CV : l'éditeur « Mes CV » (`PUT /api/cvs/{cv_id}`) enregistre le
`cv.json` modifié, puis `build_cv.rebuild_cv(<dossier>)` réécrit les sections et
recompile. Les CV créés avant `cv.json` ne sont pas modifiables.

Le nom du fichier `.tex` pilote le nom du PDF compilé (latexmk compile
`<nom>.tex` en `<nom>.pdf`) : `<Prénom>_<Nom>_Candidature_<Entreprise>_<Poste>.tex`
→ `<Prénom>_<Nom>_Candidature_<Entreprise>_<Poste>.pdf`. Le prénom et le nom
viennent de `personal.first_name` / `personal.last_name` du profil.

`cv/reference/` et `cv/applications/` sont dans `.gitignore` : tout ce qui
contient des données personnelles reste strictement local. Seul
`cv/template/` (aucune donnée perso) est versionné.

## Zones cliquables (éditeur « Mes CV »)

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

## Analyse de correspondance (analysis.json)

Après la compilation, le pipeline analyse la correspondance entre l'offre et le profil
(`analysis.py`, un appel à Claude séparé de la génération, en français) et l'enregistre dans
`analysis.json`. Un échec est enregistré comme une analyse `failed` : le CV n'est jamais perdu.
Pour un CV créé avant cette fonctionnalité, l'analyse se demande à la main
(`POST /api/cvs/{cv_id}/analysis`) ; ouvrir un CV ne lance jamais Claude.

- **Offre** expliquée simplement : résumé, missions, technologies, tâches possibles (présentées
  comme des exemples), glossaire des termes de l'offre.
- **Exigences** : la liste vient d'`offer.json` (indispensables : `must_have`, formation,
  expérience, langues ; appréciées : `nice_to_have`). Claude évalue chacune —
  `met`, `partial`, `not_documented` (le profil n'en dit rien) ou `missing` (le profil montre
  qu'elle n'est pas remplie) — avec ses preuves. Une exigence composée (« Python et SQL ») peut
  être séparée si c'est sans ambiguïté, en gardant le lien avec l'exigence d'origine.
- **Preuves** : chaque preuve cite un élément du profil (`id` d'expérience ou de projet,
  identifiant de formation, compétence, langue) ; une correspondance sémantique est permise
  si elle est justifiée, mais l'élément doit exister : sinon la preuve est retirée, et une
  exigence couverte sans preuve valide devient « non documentée ».
- **Points forts, points faibles et recommandations** (CV, entretien, notions à approfondir,
  obstacles), et **questions d'entretien possibles** (`interview_questions`, même appel à
  Claude, preuves vérifiées ; absentes des analyses enregistrées avant leur ajout).

**Score** (`fit_score.py`, déterministe) : crédit 1 (couverte), 0,5 (partielle), 0 (non
documentée ou non remplie) ; poids 2 pour une exigence liée à un point clé de l'offre, sinon 1
(une exigence séparée partage son poids, un doublon ne compte pas) ;
score = 100 × (0,80 × indispensables + 0,20 × appréciées). Pas de plafond : une exigence
indispensable non remplie donne un avertissement. Le score vaut `null` si l'offre donne trop
peu d'exigences (moins de 3, ou aucune indispensable). C'est une estimation de l'adéquation
aux critères de l'annonce, pas une probabilité d'être recruté. Il n'est pas affiché dans l'interface.

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
