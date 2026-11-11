# CLAUDE.md

Repères pour reprendre ce projet (humain ou Claude Code).

## Contexte

Projet P10 de la formation OpenClassrooms (application CATASTERRE). Le backlog Scrum du projet est tenu dans **GitHub Projects**, et non dans Notion, Jira ou Trello. Il est généré à partir d'un CSV par `backlog_to_github.py`.

- Dépôt cible des issues : `ARCHI-M2026/P10` (privé, organisation ARCHI-M2026)
- Projet : « CATASTERRE – Sprint Backlog », https://github.com/orgs/ARCHI-M2026/projects/1 (privé pour l'instant ; à passer en public pour le livrable)
- Modèle de vues repris : https://github.com/users/laurentcoufinal/projects/6

## Fichiers

| Fichier | Rôle |
|---|---|
| `backlog_to_github.py` | Script principal : CSV → labels, jalons, issues, sous-issues, projet, champs, vues (7 étapes) |
| `backlog-github.csv` | Backlog réel : 58 éléments (4 epics, 13 US, 41 tâches) |
| `sprints.csv` | Sprints S1 à S6 : dates et objectifs |
| `modele-backlog.csv` | Exemple minimal du format CSV attendu |
| `.backlog_state.json` | Mémoire des issues déjà créées (URL, id d'élément du projet). Permet la relance sans doublon. Ne contient aucun secret. Le supprimer revient à tout recréer. |
| `README.md` | Mode d'emploi complet |

## Commandes

```bash
# Prérequis : gh connecté avec le droit project
gh auth status            # doit lister le scope 'project'
gh auth refresh -s project

# Simulation (ne crée rien)
python3 backlog_to_github.py --repo ARCHI-M2026/P10 --csv backlog-github.csv --sprints sprints.csv --dry-run

# Création ou mise à jour (relançable)
python3 backlog_to_github.py --repo ARCHI-M2026/P10 --csv backlog-github.csv --sprints sprints.csv \
        --project-title "CATASTERRE – Sprint Backlog"
# ajouter --public pour rendre le projet visible avec le lien
```

Le passage complet sur 58 éléments prend plus de 10 minutes : le script fait des pauses pour respecter les limites de l'API GitHub.

## Pièges rencontrés (et corrigés)

- **Python 3.11** : une f-string avec des guillemets imbriqués (accepté seulement à partir de Python 3.12) faisait planter le script. La ligne a été réécrite ; le script doit rester compatible avec Python 3.9.
- **Champ « Type » réservé** dans les projets d'organisation (il existe déjà pour les *issue types*). Le champ du script s'appelle donc `Type d'élément` (constante `TYPE_FIELD`).
- **Filtres de vue** : dans un filtre, les espaces d'un nom de champ deviennent des tirets et les accents sont conservés : `type-d'élément:US`, `itération:@current`. Pour tester un filtre sans l'interface : `items(query: "...")` en GraphQL sur le projet.
- **Itération** : on peut désormais la créer par l'API (`createProjectV2Field`, `dataType: ITERATION`), ce que `gh project field-create` ne sait pas faire. Durée : du lundi de début au dimanche qui suit la date de fin.
- **Vues** : `createProjectV2View` / `updateProjectV2View` gèrent le nom, la disposition, le filtre et les colonnes visibles, mais **pas** le regroupement ni le tri. Une vue Roadmap refuse la liste de colonnes.
- **Vues existantes** : le script ne touche jamais une vue déjà présente, qu'il la retrouve par son nom ou par son filtre (si elle a été renommée, comme « Moi » → « Florian »). Les réglages faits à la main sont ainsi conservés.
- **Issue #42** : la fermeture a renvoyé une erreur au second passage, parce qu'elle était déjà fermée. Ce n'est pas un problème.

## Réglages manuels restants dans le projet

1. « Sprint suivant » et « Backlog priorisé » : *Group by* → Priorité.
2. « Plan des sprints » : *Group by* → Itération, puis *Sum* sur Points.
3. « Roadmap » : *Date fields* → Itération.
4. Passer le projet en public pour le livrable (réglages du projet, ou relancer avec `--public`).

## Règles

- Ne jamais mettre de jeton, de mot de passe ou d'identifiant d'infrastructure dans les CSV : les issues sont lisibles par tous ceux qui ont accès au dépôt.
- Toujours lancer `--dry-run` avant une exécution réelle sur un nouveau dépôt.
