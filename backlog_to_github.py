#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backlog_to_github.py – Crée un backlog Scrum dans GitHub (issues + GitHub Project) à partir d'un CSV.

Ce que fait le script (relançable sans créer de doublons) :
  1. labels   : type (epic / user story / tâche), priorité, epic
  2. jalons   : un milestone par sprint (dates et objectif lus dans sprints.csv, facultatif)
  3. issues   : une issue par epic, user story et tâche, avec description et critères d'acceptation en cases à cocher
  4. hiérarchie : tâches en sous-issues de leur US, US en sous-issues de leur epic
  5. projet   : un GitHub Project (v2) lié au dépôt, avec les champs Points, Priorité, Sprint, Itération, Type d'élément,
                Epic, Responsable et le Status (Todo / In Progress / Done) ; les éléments « Terminé » sont fermés
  6. vues     : Sprint en cours, Sprint suivant, Backlog priorisé, Roadmap, Plan des sprints, Product Backlog,
                et une vue par responsable
  7. visibilité publique du projet si --public (lien à fournir pour la soutenance)

Prérequis : GitHub CLI (https://cli.github.com) connecté avec le droit « project » :
    gh auth login
    gh auth refresh -s project
Aucun jeton n'est lu ni écrit par ce script : l'authentification reste gérée par gh.

Exemples :
    python3 backlog_to_github.py --repo mon-compte/catasterre --csv backlog-github.csv --sprints sprints.csv --dry-run
    python3 backlog_to_github.py --repo mon-compte/catasterre --csv backlog-github.csv --sprints sprints.csv --public
"""
import argparse, csv, datetime as dt, json, os, subprocess, sys, time

TYPE_LABELS = {"Epic": ("type: epic", "5B2C9F"), "US": ("type: user story", "B13BA0"), "Tâche": ("type: tâche", "C5B4E3")}
PRIO_COLORS = ["B60205", "D93F0B", "FBCA04", "0E8A16", "BFD4F2", "CCCCCC"]
STATUS_MAP = {"backlog": "Todo", "a faire": "Todo", "à faire": "Todo", "todo": "Todo", "en cours": "In Progress",
              "in progress": "In Progress", "terminé": "Done", "termine": "Done", "done": "Done"}

DRY = False
TYPE_FIELD = "Type d'élément"   # « Type » est réservé par GitHub dans les projets d'organisation
ITERATION_FIELD = "Itération"


def log(msg): print(msg, flush=True)


def gh(*args, input_text=None, parse=False, allow_fail=False):
    """Exécute une commande gh. En --dry-run, affiche la commande et ne fait rien."""
    cmd = ["gh", *args]
    if DRY:
        log("  [dry-run] " + " ".join(a if " " not in a else repr(a) for a in cmd))
        return {} if parse else ""
    for attempt in range(3):
        r = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout) if parse and r.stdout.strip() else (r.stdout.strip() if not parse else {})
        if "rate limit" in r.stderr.lower() or "secondary" in r.stderr.lower():
            log("  limite de débit GitHub, pause de 60 s…"); time.sleep(60); continue
        break
    if allow_fail:
        log(f"  (ignoré) {' '.join(cmd[:4])}… : {r.stderr.strip()[:200]}")
        return None
    sys.exit(f"Échec : {' '.join(cmd)}\n{r.stderr.strip()}")


def graphql(query, **variables):
    """Requête GraphQL via gh (variables passées en JSON). En --dry-run, affiche la requête et ne fait rien."""
    if DRY:
        log("  [dry-run] graphql " + " ".join(query.split())[:110] + "…"); return {}
    for attempt in range(3):
        r = subprocess.run(["gh", "api", "graphql", "--input", "-"], capture_output=True, text=True,
                           input=json.dumps({"query": query, "variables": variables}))
        out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
        if r.returncode == 0 and not out.get("errors"):
            return out.get("data", {})
        if "rate limit" in (r.stderr + r.stdout).lower():
            log("  limite de débit GitHub, pause de 60 s…"); time.sleep(60); continue
        break
    sys.exit(f"Échec GraphQL : {' '.join(query.split())[:120]}\n{r.stdout.strip()[:400]} {r.stderr.strip()[:200]}")


def filter_key(field_name):
    """Nom d'un champ tel qu'il s'écrit dans un filtre de vue : « Type d'élément » → type-d'élément."""
    return field_name.lower().replace(" ", "-")


def sprint_duration(info):
    """Durée de l'itération en jours, du lundi de début au dimanche qui suit la date de fin."""
    d, f = dt.date.fromisoformat(info["Debut"]), dt.date.fromisoformat(info["Fin"])
    return (f - d).days + 1 + (6 - f.weekday())


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096); f.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f, delimiter=delim)]
    return [r for r in rows if r.get("ID") and r.get("Titre")]


def body_for(r, children):
    out = []
    if r.get("Description"): out += [r["Description"], ""]
    crit = [c.strip(" •-\t") for c in r.get("Criteres", "").replace("|", "\n").splitlines() if c.strip(" •-\t")]
    if crit:
        out += ["### Critères d'acceptation", *[f"- [ ] {c}" for c in crit], ""]
    meta = [("Type", r.get("Type")), ("Epic", r.get("Epic")), ("Parent", r.get("Parent")), ("Points", r.get("Points")),
            ("Priorité", r.get("Priorite")), ("Sprint", r.get("Sprint")), ("Responsable", r.get("Responsable"))]
    out += ["### Pilotage", "| Champ | Valeur |", "|---|---|", *[f"| {k} | {v} |" for k, v in meta if v], ""]
    if children:
        out += ["### Éléments rattachés", *[f"- {c}" for c in children], ""]
    out.append(f"<!-- backlog-id: {r['ID']} -->")
    return "\n".join(out)


def main():
    global DRY
    p = argparse.ArgumentParser(description="Backlog CSV → issues + GitHub Project")
    p.add_argument("--repo", required=True, help="propriétaire/dépôt (le dépôt doit exister)")
    p.add_argument("--csv", required=True, help="backlog : ID,Type,Titre,Parent,Epic,Description,Criteres,Points,Priorite,Sprint,Responsable,Etat")
    p.add_argument("--sprints", help="facultatif : Sprint,Debut,Fin,Objectif (dates AAAA-MM-JJ)")
    p.add_argument("--project-title", default="Sprint Backlog", help="titre du GitHub Project")
    p.add_argument("--assignees", help="facultatif : JSON {\"Dimitry\": \"login-github\", …} pour assigner les issues")
    p.add_argument("--public", action="store_true", help="rendre le projet public (lien partageable)")
    p.add_argument("--dry-run", action="store_true", help="affiche les commandes sans rien créer")
    p.add_argument("--state", default=".backlog_state.json", help="mémoire des issues créées (relance sans doublon)")
    a = p.parse_args()
    DRY = a.dry_run
    owner = a.repo.split("/")[0]

    rows = read_csv(a.csv)
    ids = {r["ID"] for r in rows}
    for r in rows:
        if r.get("Type") not in TYPE_LABELS: sys.exit(f"{r['ID']} : Type doit valoir Epic, US ou Tâche")
        if r.get("Parent") and r["Parent"] not in ids: sys.exit(f"{r['ID']} : parent {r['Parent']} introuvable")
    sprints = read_csv_sprints(a.sprints) if a.sprints else {}
    assignees = json.load(open(a.assignees, encoding="utf-8")) if a.assignees else {}
    state = json.load(open(a.state, encoding="utf-8")) if os.path.exists(a.state) and not DRY else {}
    save = (lambda: json.dump(state, open(a.state, "w", encoding="utf-8"), indent=1, ensure_ascii=False)) if not DRY else (lambda: None)

    if not DRY:
        gh("auth", "status")
        gh("repo", "view", a.repo, "--json", "name", parse=True)
    counts = ', '.join(str(sum(r['Type'] == t for r in rows)) + ' ' + t for t in TYPE_LABELS)
    log(f"Backlog : {len(rows)} éléments ({counts})")

    # 1. labels -----------------------------------------------------------------------------------------
    log("1/7 Labels")
    rank = {"Must": 0, "Should": 1, "Could": 2, "Won't": 3}
    prios = sorted(dict.fromkeys(r["Priorite"] for r in rows if r.get("Priorite")), key=lambda x: rank.get(x, 9))
    epics = list(dict.fromkeys(r["Epic"] for r in rows if r.get("Epic")))
    for name, color in TYPE_LABELS.values():
        gh("label", "create", name, "--color", color, "--force", "--repo", a.repo)
    for k, pr in enumerate(prios):
        color = {"Must": "B60205", "Should": "FBCA04", "Could": "0E8A16", "Won't": "CCCCCC"}.get(pr, PRIO_COLORS[min(k, 5)])
        gh("label", "create", f"priorité: {pr}", "--color", color, "--force", "--repo", a.repo)
    for e in epics:
        gh("label", "create", f"epic: {e}"[:50], "--color", "EDE7F6", "--force", "--repo", a.repo)

    # 2. milestones -------------------------------------------------------------------------------------
    log("2/7 Jalons (sprints)")
    sprint_names = list(dict.fromkeys([*sprints.keys(), *[r["Sprint"] for r in rows if r.get("Sprint")]]))
    existing = {m["title"] for m in (gh("api", f"repos/{a.repo}/milestones?state=all&per_page=100", parse=True) or [])} if not DRY else set()
    for s in sprint_names:
        if s in existing: continue
        args = ["api", f"repos/{a.repo}/milestones", "-f", f"title={s}"]
        info = sprints.get(s, {})
        if info.get("Objectif") or info.get("Debut"):
            args += ["-f", f"description=Objectif : {info.get('Objectif', '')} ({info.get('Debut', '')} → {info.get('Fin', '')})"]
        if info.get("Fin"): args += ["-f", f"due_on={info['Fin']}T18:00:00Z"]
        gh(*args, parse=True)

    # 3. issues -----------------------------------------------------------------------------------------
    log("3/7 Issues")
    children = {}
    for r in rows:
        if r.get("Parent"): children.setdefault(r["Parent"], []).append(f'{r["ID"]} – {r["Titre"]}')
    order = {"Epic": 0, "US": 1, "Tâche": 2}
    for r in sorted(rows, key=lambda r: order[r["Type"]]):
        if r["ID"] in state.get("issues", {}):
            continue
        title = f'[{r["ID"]}] {r["Titre"]}'
        labels = [TYPE_LABELS[r["Type"]][0]]
        if r.get("Priorite"): labels.append(f'priorité: {r["Priorite"]}')
        if r.get("Epic"): labels.append(f'epic: {r["Epic"]}'[:50])
        args = ["issue", "create", "--repo", a.repo, "--title", title, "--body-file", "-"]
        for l in labels: args += ["--label", l]
        if r.get("Sprint"): args += ["--milestone", r["Sprint"]]
        for person in [x.strip() for x in r.get("Responsable", "").split(",") if x.strip()]:
            if person in assignees: args += ["--assignee", assignees[person]]
        url = gh(*args, input_text=body_for(r, children.get(r["ID"])))
        url = url.splitlines()[-1] if url else f"https://github.com/{a.repo}/issues/<{r['ID']}>"
        log(f"  {title} → {url}")
        state.setdefault("issues", {})[r["ID"]] = {"url": url}
        save(); time.sleep(0 if DRY else 0.8)   # évite la limite de débit secondaire de GitHub

    # 4. sous-issues ------------------------------------------------------------------------------------
    log("4/7 Hiérarchie epic → US → tâche (sous-issues)")
    for r in rows:
        if not r.get("Parent") or state.get("issues", {}).get(r["ID"], {}).get("linked"): continue
        parent_url, child_url = state.get("issues", {}).get(r["Parent"], {}).get("url"), state.get("issues", {}).get(r["ID"], {}).get("url")
        if DRY:
            log(f"  [dry-run] sous-issue {r['ID']} → {r['Parent']}"); continue
        pid = gh("issue", "view", parent_url, "--json", "id", parse=True)["id"]
        cid = gh("issue", "view", child_url, "--json", "id", parse=True)["id"]
        ok = gh("api", "graphql", "-H", "GraphQL-Features: sub_issues", "-f",
                "query=mutation($p:ID!,$c:ID!){addSubIssue(input:{issueId:$p,subIssueId:$c}){issue{number}}}",
                "-f", f"p={pid}", "-f", f"c={cid}", allow_fail=True)
        if ok is not None:
            state["issues"][r["ID"]]["linked"] = True; save()

    # 5. projet -----------------------------------------------------------------------------------------
    log("5/7 GitHub Project")
    if DRY:
        proj = {"number": "<N>", "id": "<PROJECT_ID>", "url": f"https://github.com/users/{owner}/projects/<N>"}
        gh("project", "create", "--owner", owner, "--title", a.project_title, "--format", "json")
    else:
        found = [x for x in gh("project", "list", "--owner", owner, "--format", "json", "--limit", "100", parse=True).get("projects", [])
                 if x["title"] == a.project_title]
        proj = found[0] if found else gh("project", "create", "--owner", owner, "--title", a.project_title, "--format", "json", parse=True)
    num = str(proj["number"])
    gh("project", "link", num, "--owner", owner, "--repo", a.repo, allow_fail=True)
    sprints_opts = sprint_names or ["Backlog"]
    wanted = {"Points": ("NUMBER", None), "Priorité": ("SINGLE_SELECT", prios), "Sprint": ("SINGLE_SELECT", sprints_opts),
              TYPE_FIELD: ("SINGLE_SELECT", list(TYPE_LABELS)), "Epic": ("SINGLE_SELECT", epics), "Responsable": ("TEXT", None)}
    fields = {} if DRY else {f["name"]: f for f in gh("project", "field-list", num, "--owner", owner, "--format", "json", "--limit", "50", parse=True)["fields"]}
    for name, (dtype, opts) in wanted.items():
        if name in fields or (dtype == "SINGLE_SELECT" and not opts): continue
        args = ["project", "field-create", num, "--owner", owner, "--name", name, "--data-type", dtype, "--format", "json"]
        if opts: args += ["--single-select-options", ",".join(o.replace(",", " ") for o in opts)]
        gh(*args, parse=True)
    # Champ Itération (vrai champ de sprint GitHub, permet les filtres @current / @next) : seulement si les dates sont connues
    dated = [s for s in sprint_names if sprints.get(s, {}).get("Debut") and sprints[s].get("Fin")]
    if dated and ITERATION_FIELD not in fields:
        its = [{"title": s, "startDate": sprints[s]["Debut"], "duration": sprint_duration(sprints[s])} for s in dated]
        graphql("""mutation($i:CreateProjectV2FieldInput!){createProjectV2Field(input:$i){projectV2Field{... on ProjectV2FieldCommon{id}}}}""",
                i={"projectId": proj["id"], "dataType": "ITERATION", "name": ITERATION_FIELD,
                   "iterationConfiguration": {"startDate": its[0]["startDate"], "duration": its[0]["duration"], "iterations": its}})
    iterations = {}
    if not DRY:
        fields = {f["name"]: f for f in gh("project", "field-list", num, "--owner", owner, "--format", "json", "--limit", "50", parse=True)["fields"]}
        d = graphql("""query($p:ID!){node(id:$p){... on ProjectV2{field(name:"%s"){... on ProjectV2IterationField{
                       configuration{iterations{id title} completedIterations{id title}}}}}}}""" % ITERATION_FIELD, p=proj["id"])
        conf = ((d.get("node") or {}).get("field") or {}).get("configuration") or {}
        iterations = {i["title"]: i["id"] for i in conf.get("iterations", []) + conf.get("completedIterations", [])}

    def set_field(item, name, value):
        if not value: return
        if DRY:
            log(f"  [dry-run] champ {name} = {value}"); return
        f = fields.get(name)
        if not f: return
        base = ["project", "item-edit", "--id", item, "--project-id", proj["id"], "--field-id", f["id"]]
        if name == ITERATION_FIELD:
            if value in iterations: gh(*base, "--iteration-id", iterations[value], allow_fail=True)
        elif f["type"] == "ProjectV2SingleSelectField":
            opt = next((o["id"] for o in f.get("options", []) if o["name"] == value.replace(",", " ")), None)
            if opt: gh(*base, "--single-select-option-id", opt, allow_fail=True)
            else: log(f"  option « {value} » absente du champ {name}")
        elif name == "Points":
            gh(*base, "--number", value.replace(",", "."), allow_fail=True)
        else:
            gh(*base, "--text", value, allow_fail=True)

    for r in rows:
        st = state["issues"][r["ID"]] if not DRY else {"url": "<url>"}
        if st.get("item") and not DRY:
            # élément déjà ajouté lors d'un passage précédent : ne complète que l'Itération si elle manque
            if r.get("Sprint") in iterations and not st.get("iteration"):
                set_field(st["item"], ITERATION_FIELD, r["Sprint"]); st["iteration"] = True; save()
            continue
        item = gh("project", "item-add", num, "--owner", owner, "--url", st["url"], "--format", "json", parse=True).get("id", "<ITEM>")
        status = STATUS_MAP.get(r.get("Etat", "").lower(), "Todo")
        for name, value in [("Points", r.get("Points")), ("Priorité", r.get("Priorite")), ("Sprint", r.get("Sprint")),
                            (ITERATION_FIELD, r.get("Sprint") if dated else None),
                            (TYPE_FIELD, r["Type"]), ("Epic", r.get("Epic")), ("Responsable", r.get("Responsable")), ("Status", status)]:
            set_field(item, name, value)
        if status == "Done":
            gh("issue", "close", st["url"], "--reason", "completed", allow_fail=True)
        if not DRY:
            st["item"] = item; st["iteration"] = r.get("Sprint") in iterations; save(); time.sleep(0.3)

    # 6. vues -------------------------------------------------------------------------------------------
    log("6/7 Vues du projet")
    people = list(dict.fromkeys(x.strip() for r in rows for x in r.get("Responsable", "").split(",") if x.strip()))
    sprint_filter = f"{filter_key(ITERATION_FIELD)}:@current" if dated else (f"{filter_key('Sprint')}:{sprint_names[0]}" if sprint_names else "")
    next_filter = f"{filter_key(ITERATION_FIELD)}:@next" if dated else (f"{filter_key('Sprint')}:{sprint_names[1]}" if len(sprint_names) > 1 else "")
    sprint_col = ITERATION_FIELD if dated else "Sprint"
    board = ["Title", "Responsable", "Sub-issues progress", "Priorité", "Points", TYPE_FIELD, "Epic"]
    table = ["Title", "Status", "Responsable", "Sub-issues progress", "Priorité", "Points", sprint_col, TYPE_FIELD, "Epic"]
    person = ["Title", "Status", sprint_col, "Priorité", "Points", "Sub-issues progress"]
    views = [  # (nom, mise en page, filtre, colonnes affichées ; None = réglage par défaut)
        ("Sprint en cours", "BOARD_LAYOUT", sprint_filter, board),
        ("Sprint suivant", "BOARD_LAYOUT", next_filter, board),
        ("Backlog priorisé", "BOARD_LAYOUT", "", board + [sprint_col]),
        ("Roadmap", "ROADMAP_LAYOUT", "", None),          # une roadmap n'accepte pas de liste de colonnes
        ("Plan des sprints", "TABLE_LAYOUT", "", table),
        ("Product Backlog", "TABLE_LAYOUT", f"{filter_key(TYPE_FIELD)}:US", table),
        *[(p, "TABLE_LAYOUT", f'{filter_key("Responsable")}:*{p}*' if " " not in p else f'{filter_key("Responsable")}:"*{p}*"', person)
          for p in people],
    ]
    existing_views, by_filter = {}, {}
    if not DRY:
        d = graphql("query($p:ID!){node(id:$p){... on ProjectV2{views(first:50){nodes{id name filter}}}}}", p=proj["id"])
        existing_views = {v["name"]: v["id"] for v in d["node"]["views"]["nodes"]}
        by_filter = {v["filter"]: (v["id"], v["name"]) for v in d["node"]["views"]["nodes"] if v.get("filter")}
    for k, (name, layout, flt, cols) in enumerate(views):
        conf = {"visibleFieldIds": [fields[c]["id"] for c in cols if c in fields]} if cols and not DRY else None
        extra = {"configuration": conf} if conf else {}
        found = existing_views.get(name) or (by_filter[flt][0] if flt in by_filter else None)  # même nom, ou même filtre si renommée
        if found:                                 # déjà en place : on n'y touche plus, pour garder les réglages faits à la main
            log(f"  {name} : déjà présente"); continue
        vid = None
        if k == 0:
            vid = existing_views.pop("View 1", None)  # renomme la vue par défaut d'un projet neuf
        if not vid:
            d = graphql("mutation($i:CreateProjectV2ViewInput!){createProjectV2View(input:$i){projectV2View{id}}}",
                        i={"projectId": proj["id"], "name": name, "layout": layout, **extra})
            vid = (d.get("createProjectV2View") or {}).get("projectV2View", {}).get("id", "<VIEW>")
        graphql("mutation($i:UpdateProjectV2ViewInput!){updateProjectV2View(input:$i){projectV2View{id}}}",
                i={"viewId": vid, "name": name, "layout": layout, "filter": flt, **extra})
        log(f"  {name} ({layout.split('_')[0].lower()}){' – filtre ' + flt if flt else ''}")

    # 7. visibilité --------------------------------------------------------------------------------------
    log("7/7 Visibilité")
    if a.public:
        gh("project", "edit", num, "--owner", owner, "--visibility", "PUBLIC")
    log(f"\nTerminé. Projet : {proj.get('url')}")
    log("À régler à la main (l'API ne gère ni le regroupement ni le tri des vues) : « Sprint suivant » et « Backlog priorisé » "
        f"groupés par Priorité, « Plan des sprints » groupé par {sprint_col} avec somme des Points, "
        f"« Roadmap » sur le champ de dates {sprint_col}. Voir README.")


def read_csv_sprints(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048); f.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        return {r["Sprint"].strip(): {k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f, delimiter=delim) if r.get("Sprint")}


if __name__ == "__main__":
    main()
