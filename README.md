# Backlog Scrum dans GitHub Projects (à partir d'un CSV)

Le script `backlog_to_github.py` crée un backlog Scrum complet dans GitHub à partir d'un fichier CSV. C'est une alternative à Notion, Jira ou Trello.

Il crée :

- les **issues** : une par epic, par user story et par tâche, avec les critères d'acceptation en cases à cocher ;
- la **hiérarchie** epic → US → tâche, en sous-issues ;
- les **labels** : type d'élément, priorité, epic ;
- un **jalon par sprint**, avec son objectif et sa date de fin ;
- un **GitHub Project** lié au dépôt, avec les champs Points, Priorité, Sprint, Itération, Type d'élément, Epic, Responsable et Status ;
- les **vues** du projet : sprint en cours, sprint suivant, backlog priorisé, roadmap, plan des sprints, product backlog et une vue par responsable ;
- un **lien public** vers le projet, si vous passez l'option `--public`.

Le script peut être relancé sans créer de doublons : il mémorise ce qu'il a déjà créé dans `.backlog_state.json`.

## 1. Prérequis

- Python 3.9 ou plus récent (bibliothèque standard uniquement).
- [GitHub CLI](https://cli.github.com), connecté avec le droit « project » :

```bash
gh auth login
gh auth refresh -s project
```

- Un dépôt GitHub existant, par exemple : `gh repo create mon-compte/catasterre --private`.

Le script ne lit ni n'écrit aucun jeton : l'authentification est entièrement gérée par `gh`.

## 2. Fichiers d'entrée

### `backlog.csv` (obligatoire)

Séparateur virgule ou point-virgule (un export Excel en français fonctionne tel quel). Encodage UTF-8.

| Colonne | Contenu | Exemple |
|---|---|---|
| ID | Identifiant unique | `E1`, `US3`, `T3.2` |
| Type | `Epic`, `US` ou `Tâche` | `Tâche` |
| Titre | Intitulé court | `Corriger les contrastes` |
| Parent | ID de l'élément parent : l'epic pour une US, l'US pour une tâche | `US3` |
| Epic | ID de l'epic, sert au label et au champ Epic | `E1` |
| Description | Texte libre ; pour une US, « En tant que… je veux… afin de… » | |
| Criteres | Critères d'acceptation séparés par `\|` ou par des retours à la ligne | `Score ≥ 90 \| Navigation clavier` |
| Points | Story points | `3` |
| Priorite | Valeur libre : MoSCoW, Haute/Basse… | `Must` |
| Sprint | Nom du sprint (jalon) | `S3` |
| Responsable | Prénoms séparés par des virgules | `Dimitry, Jorge` |
| Etat | `Backlog`, `A faire`, `En cours` ou `Terminé` | `A faire` |

Les éléments « Terminé » sont fermés et passent en *Done*. « En cours » passe en *In Progress*. Tout le reste est en *Todo*.

### `sprints.csv` (facultatif)

Colonnes `Sprint,Debut,Fin,Objectif`, avec les dates au format `AAAA-MM-JJ`. Le script en tire la description et l'échéance de chaque jalon, ainsi que le champ **Itération** du projet (chaque itération va du lundi de début au dimanche qui suit la date de fin). Sans ce fichier, il n'y a pas de champ Itération et les vues de sprint filtrent sur le champ Sprint.

### `assignees.json` (facultatif)

Pour assigner les issues à de vrais comptes GitHub : `{"Dimitry": "login-dimitry", "Rachida": "login-rachida"}`.

## 3. Exécution

```bash
# 1) Simulation : affiche toutes les commandes, ne crée rien
python3 backlog_to_github.py --repo mon-compte/catasterre --csv backlog-github.csv --sprints sprints.csv --dry-run

# 2) Création réelle, projet public (lien à joindre au livrable)
python3 backlog_to_github.py --repo mon-compte/catasterre --csv backlog-github.csv --sprints sprints.csv \
        --project-title "CATASTERRE – Sprint Backlog" --public
```

Comptez quelques minutes pour une cinquantaine d'éléments. Le script marque une pause entre les créations pour respecter les limites de l'API GitHub.

## 4. Vues du projet

Le script crée ces vues :

| Vue | Disposition | Filtre |
|---|---|---|
| Sprint en cours | Board | `itération:@current` |
| Sprint suivant | Board | `itération:@next` |
| Backlog priorisé | Board | aucun |
| Roadmap | Roadmap | aucun |
| Plan des sprints | Table | aucun |
| Product Backlog | Table | `type-d'élément:US` |
| Une vue par responsable | Table | `responsable:*Prénom*` |

Une vue déjà présente (même nom, ou même filtre si vous l'avez renommée) n'est jamais modifiée : vos réglages manuels sont conservés à chaque relance.

L'API ne permet pas de régler le regroupement ni le tri. Il reste donc à faire à la main (environ 2 minutes) :

1. **Sprint suivant** et **Backlog priorisé** : *Group by* → Priorité.
2. **Plan des sprints** : *Group by* → Itération, puis *Sum* sur Points.
3. **Roadmap** : *Date fields* → Itération.

Pour suivre la progression, activez aussi **Insights** (graphiques de burnup et de répartition par champ).

## 5. Lien public pour le livrable

Avec `--public`, le projet est visible par toute personne qui a le lien. Le dépôt peut rester privé. Récupérez l'URL affichée en fin d'exécution (`https://github.com/users/<compte>/projects/<n>`) et collez-la dans le PDF demandé.

## 6. Limites et conseils

- **Sprints** : chaque sprint existe à trois endroits : un jalon (milestone) sur l'issue, le champ *Sprint* (liste) et le champ *Itération* du projet, qui permet les filtres `@current` et `@next`.
- **Noms de champs** : « Type » est réservé par GitHub dans les projets d'organisation, d'où « Type d'élément ». Dans un filtre, les espaces d'un nom de champ deviennent des tirets : `type-d'élément:US`.
- **Sous-issues** : si votre compte ou votre organisation ne les a pas, l'étape est ignorée. La hiérarchie reste lisible dans la section « Éléments rattachés » de chaque issue.
- **Relance après erreur** : relancez simplement la même commande ; les éléments déjà créés sont sautés.
- **Repartir de zéro** : supprimez `.backlog_state.json`, ainsi que les issues et le projet dans GitHub.
- **Secrets** : n'écrivez jamais de jeton, de mot de passe ou d'identifiant d'infrastructure dans le CSV : les issues sont visibles par toute personne qui a accès au dépôt.
