"""Outils développeur (suite) : relecture avant commit, message de commit, explication d'un échec de CI,
conteneurs Docker, pense-bête de commandes, export du temps par projet, failles des dépendances (OSV.dev),
mode « canard en plastique ».
"""
import csv
import datetime
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

# ================================================================== relecture avant commit
SECRETS = [
    (r"AKIA[0-9A-Z]{16}", "clé AWS"),
    (r"ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}", "jeton GitHub"),
    (r"glpat-[A-Za-z0-9_-]{20,}", "jeton GitLab"),
    (r"sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}", "clé d'API (OpenAI / Anthropic…)"),
    (r"hf_[A-Za-z0-9]{30,}", "jeton Hugging Face"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "jeton Slack"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", "clé privée"),
    (r"(?i)\b(?:password|passwd|mot_de_passe|secret|api_?key|token)\s*[:=]\s*['\"][^'\"\s]{6,}['\"]",
     "mot de passe ou clé écrit en dur"),
]
DEBUG = [(r"\bconsole\.log\(", "console.log"), (r"^\s*print\(", "print()"), (r"\bdebugger;", "debugger"),
         (r"\bdbg!\(", "dbg!"), (r"\bbreakpoint\(\)", "breakpoint()"), (r"\bvar_dump\(", "var_dump"),
         (r"\bpdb\.set_trace\(\)", "pdb.set_trace")]


def git(p, *a, timeout=30):
    try:
        r = subprocess.run(["git", "-C", str(p)] + list(a), capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def current_diff(p):
    """Ce qui va partir dans le commit (indexé), sinon toutes les modifications."""
    d = git(p, "diff", "--cached", "--no-color", "-U2")
    staged = bool(d.strip())
    if not staged:
        d = git(p, "diff", "--no-color", "-U2")
    return d, staged


def scan_diff(diff):
    """Problèmes évidents dans les lignes ajoutées -> [texte]."""
    out = []
    fichier = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            fichier = line[6:] if line.startswith("+++ b/") else line[4:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        add = line[1:]
        for pat, lab in SECRETS:
            if re.search(pat, add):
                out.append(f"🚨 {fichier} : {lab} ! Ne le commite pas (et change-le s'il a déjà été poussé).")
                break
        for pat, lab in DEBUG:
            if re.search(pat, add) and not fichier.endswith((".md", ".txt")):
                out.append(f"🔎 {fichier} : {lab} oublié ? → {add.strip()[:70]}")
                break
        if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", add):
            out.append(f"📝 {fichier} : {add.strip()[:80]}")
        if re.search(r"^(<<<<<<<|=======|>>>>>>>)( |$)", add):
            out.append(f"⚠️ {fichier} : marqueur de conflit de fusion laissé dans le code !")
    return out[:40]


def review_prompt(diff):
    return [{"role": "system", "content": "Tu es une développeuse senior bienveillante. Tu relis un diff avant commit."},
            {"role": "user", "content": "Relis ce diff. Liste seulement les vrais problèmes probables (bugs, oublis, "
             "cas limites, sécurité, noms trompeurs), du plus grave au moins grave, avec le fichier et une phrase "
             "d'explication. S'il n'y a rien d'important, dis-le simplement. En français, sans réécrire tout le code."
             "\n\n```diff\n" + diff[:14000] + "\n```"}]


def commit_prompt(diff, style=""):
    return [{"role": "system", "content": "Tu écris des messages de commit git clairs."},
            {"role": "user", "content": "Écris UN message de commit pour ce diff : une première ligne de moins de 70 "
             "caractères à l'impératif" + (" au format Conventional Commits (feat:, fix:, docs:…)" if style == "cc"
                                          else "") +
             ", puis si utile une ligne vide et 2 à 4 puces courtes. Langue : celle des commits récents du projet. "
             "Réponds seulement avec le message.\n\n```diff\n" + diff[:12000] + "\n```"}]


def recent_commits(p, n=8):
    return git(p, "log", f"-{n}", "--format=%s").strip()


# ================================================================== CI : dernier échec et son journal
def remote_of(p):
    url = git(p, "remote", "get-url", "origin").strip()
    m = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?$", url)
    if m:
        return "github", f"{m.group(1)}/{m.group(2)}", ""
    m = re.search(r"^(?:https?://|git@)([^/:]+)[:/](.+?)(?:\.git)?$", url)
    if m:
        return "gitlab", m.group(2), m.group(1)
    return None, None, None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _req(url, headers, raw=False, timeout=30):
    """GET ; les redirections (journaux GitHub → stockage) sont suivies SANS renvoyer le jeton."""
    req = urllib.request.Request(url, headers=dict(headers, **{"User-Agent": "Viki"}))
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
            with urllib.request.urlopen(urllib.request.Request(e.headers["Location"],
                                                               headers={"User-Agent": "Viki"}),
                                        timeout=timeout) as r:
                data = r.read()
        else:
            raise
    return data.decode("utf-8", "replace") if raw else json.loads(data)


def last_ci_failure(p, forge):
    """-> (titre, extrait du journal) du dernier échec de CI du projet, ou None."""
    kind, repo, host = remote_of(p)
    tok = (forge or {}).get("jeton", "")
    if not kind or not tok:
        return None
    if kind == "github":
        h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
        runs = _req(f"https://api.github.com/repos/{repo}/actions/runs?status=failure&per_page=1", h)["workflow_runs"]
        if not runs:
            return None
        run = runs[0]
        jobs = _req(run["jobs_url"], h)["jobs"]
        bad = next((j for j in jobs if j.get("conclusion") == "failure"), None)
        if not bad:
            return run["name"], ""
        log = _req(f"https://api.github.com/repos/{repo}/actions/jobs/{bad['id']}/logs", h, raw=True)
        step = next((s["name"] for s in bad.get("steps", []) if s.get("conclusion") == "failure"), "")
        return f"{run['name']} — {bad['name']}" + (f" (étape « {step} »)" if step else ""), "\n".join(
            log.splitlines()[-160:])
    base = (forge.get("url") or f"https://{host}").rstrip("/")
    h = {"PRIVATE-TOKEN": tok}
    pid = urllib.request.quote(repo, safe="")
    pipes = _req(f"{base}/api/v4/projects/{pid}/pipelines?status=failed&per_page=1", h)
    if not pipes:
        return None
    jobs = _req(f"{base}/api/v4/projects/{pid}/pipelines/{pipes[0]['id']}/jobs?scope[]=failed", h)
    if not jobs:
        return f"pipeline {pipes[0]['id']}", ""
    log = _req(f"{base}/api/v4/projects/{pid}/jobs/{jobs[0]['id']}/trace", h, raw=True)
    log = re.sub(r"\x1b\[[0-9;]*m", "", log)
    return f"pipeline {pipes[0]['id']} — {jobs[0]['name']}", "\n".join(log.splitlines()[-160:])


def ci_prompt(title, log):
    return ("Voici la fin du journal d'un échec de CI (" + title + "). Explique en français, simplement : 1) ce qui a "
            "échoué, 2) la cause la plus probable, 3) quoi faire pour corriger (commandes si utile). Court.\n\n"
            + log[-9000:])


# ================================================================== Docker / Podman
def docker_cmd():
    for exe in ("docker", "podman"):
        if shutil.which(exe):
            return exe
    return None


def containers():
    exe = docker_cmd()
    if not exe:
        raise RuntimeError("Docker (ou Podman) n'est pas installé")
    r = subprocess.run([exe, "ps", "-a", "--format", "{{json .}}"], capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        msg = r.stderr.strip()
        if "permission denied" in msg.lower():
            raise RuntimeError("pas le droit de parler à Docker : ajoute-toi au groupe « docker » "
                               "(sudo usermod -aG docker $USER, puis reconnecte-toi)")
        raise RuntimeError(msg[:160] or "Docker ne répond pas (le service est-il lancé ?)")
    out = []
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        status = d.get("Status", "") or d.get("State", "")
        etat = ("💥 planté" if re.search(r"Exited \((?!0\))", status) or "unhealthy" in status else
                "🔁 redémarre en boucle" if "Restarting" in status else
                "✅ tourne" if status.startswith("Up") or d.get("State") == "running" else "⏹️ arrêté")
        out.append({"id": d.get("ID", "")[:12], "nom": d.get("Names", ""), "image": d.get("Image", ""),
                    "statut": status, "etat": etat, "ports": d.get("Ports", "")})
    return out


def container_action(cid, action):
    exe = docker_cmd()
    r = subprocess.run([exe, action, cid], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])


def container_logs(cid, n=80):
    exe = docker_cmd()
    r = subprocess.run([exe, "logs", "--tail", str(n), cid], capture_output=True, text=True, timeout=20)
    return (r.stdout + r.stderr)[-8000:]


# ================================================================== pense-bête de commandes
COMMANDES = [
    (r"annul\w* (?:le )?dernier commit|defaire (?:le )?dernier commit",
     "git reset --soft HEAD~1", "annule le dernier commit mais garde tes modifications (prêtes à recommiter). "
     "Si tu l'as déjà poussé, préfère « git revert HEAD »."),
    (r"modifi\w* (?:le )?(?:message|dernier commit)|corriger le message",
     "git commit --amend", "modifie le dernier commit (message ou fichiers ajoutés). À éviter s'il est déjà poussé."),
    (r"annul\w* (?:les )?modif\w* (?:d'?un|du) fichier|restaurer un fichier",
     "git restore chemin/du/fichier", "remet le fichier comme au dernier commit (tes changements sont perdus)."),
    (r"(?:retirer|enlever|desindexer) .*(?:du commit|de l'?index)|unstage",
     "git restore --staged chemin/du/fichier", "retire le fichier du prochain commit, sans perdre tes modifs."),
    (r"nouvelle branche|creer une branche", "git switch -c nom-de-branche", "crée une branche et va dessus."),
    (r"changer de branche|aller sur (?:une|la) branche", "git switch nom-de-branche", "va sur une autre branche."),
    (r"supprimer une branche", "git branch -d nom (locale) · git push origin --delete nom (distante)",
     "« -D » au lieu de « -d » force la suppression d'une branche pas fusionnée."),
    (r"mettre de cote|stash|ranger (?:mes )?modif", "git stash   puis   git stash pop",
     "met tes modifications de côté, puis les ressort."),
    (r"voir l'?historique|log (?:joli|graph)", "git log --oneline --graph --all", "l'historique en arbre, compact."),
    (r"qui a (?:ecrit|modifie) (?:cette|la) ligne|blame", "git blame chemin/du/fichier",
     "montre qui a modifié chaque ligne et dans quel commit."),
    (r"recuperer (?:les )?(?:changements|modifs)|mettre a jour (?:ma )?branche|pull",
     "git pull --rebase", "récupère le travail des autres et rejoue tes commits par-dessus."),
    (r"conflit", "git status  →  corrige les fichiers  →  git add fichier  →  git rebase --continue (ou git commit)",
     "les zones <<<<<<< ======= >>>>>>> montrent les deux versions : garde la bonne puis supprime les marqueurs."),
    (r"retrouver un commit perdu|reflog", "git reflog", "liste tout ce que HEAD a pointé : on retrouve presque tout."),
    (r"ignorer un fichier deja suivi", "git rm --cached fichier  puis ajoute-le au .gitignore",
     "Git arrête de le suivre sans le supprimer de ton disque."),
    (r"quel processus .*port|qui (?:utilise|occupe) le port", "ss -ltnp | grep :PORT",
     "montre quel programme écoute sur ce port."),
    (r"tuer un processus|arreter un processus", "kill PID   (ou   pkill -f nom)", "« kill -9 PID » si il résiste."),
    (r"place (?:sur le|du) disque|espace disque", "df -h   ·   du -sh * | sort -h", "espace libre, puis ce qui prend "
     "de la place dans le dossier."),
    (r"chercher (?:du texte|un mot) dans (?:des|les) fichiers|grep", "grep -rn \"texte\" .   (ou   rg \"texte\")",
     "cherche partout dans le dossier, avec les numéros de ligne."),
    (r"trouver un fichier|chercher un fichier", "find . -iname \"*nom*\"", "cherche un fichier par son nom."),
    (r"permission|chmod|rendre executable", "chmod +x script.sh", "rend un script exécutable."),
    (r"environnement virtuel|venv", "python -m venv .venv  puis  source .venv/bin/activate",
     "un Python isolé pour le projet."),
    (r"mettre a jour (?:le systeme|arch|les paquets)", "sudo pacman -Syu", "met tout le système à jour (Arch)."),
    (r"journal du systeme|logs? d'?un service|journalctl", "journalctl -u nom-du-service -e   ·   journalctl -b -p err",
     "les messages d'un service, ou les erreurs depuis le démarrage."),
    (r"docker.*(?:nettoyer|place)|nettoyer docker", "docker system prune", "supprime conteneurs arrêtés, images et "
     "réseaux inutilisés (ajoute -a pour les images non utilisées)."),
    (r"compresser|archive tar|tar\b", "tar czf archive.tar.gz dossier/   ·   tar xzf archive.tar.gz",
     "créer puis extraire une archive."),
    (r"ssh.*cle|cle ssh|generer une cle", "ssh-keygen -t ed25519 -C \"toi@exemple.fr\"",
     "crée une paire de clés ; la publique est dans ~/.ssh/id_ed25519.pub."),
]


def cheat(question):
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", question.lower()) if unicodedata.category(c) != "Mn")
    for pat, cmd, why in COMMANDES:
        if re.search(pat, t):
            return f"« {cmd} » : {why}"
    return None


def is_how_to(text):
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return bool(re.search(r"\b(comment (?:on |je |faire pour |tu )|quelle commande|c'?est quoi la commande)", t)) and \
        bool(re.search(r"\b(git|commit|branche|port|processus|disque|fichier|docker|ssh|terminal|commande|linux|"
                       r"systeme|paquet|venv|grep|chmod|journal|tar|stash|conflit|reflog|blame)\b", t))


# ================================================================== temps par projet : export
def time_rows(state, days=30):
    start = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
    rows = []
    for d in sorted(state.get("temps", {})):
        if d >= start:
            for proj, m in sorted(state["temps"][d].items()):
                rows.append((d, proj, m))
    return rows


def export_csv(state, path, days=30, taux=0.0):
    rows = time_rows(state, days)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["date", "projet", "minutes", "heures"] + (["montant (€)"] if taux else []))
        tot = {}
        for d, p, m in rows:
            h = round(m / 60, 2)
            w.writerow([d, p, m, str(h).replace(".", ",")] + ([str(round(h * taux, 2)).replace(".", ",")] if taux
                                                              else []))
            tot[p] = tot.get(p, 0) + m
        w.writerow([])
        for p, m in sorted(tot.items(), key=lambda kv: -kv[1]):
            h = round(m / 60, 2)
            w.writerow(["TOTAL", p, m, str(h).replace(".", ",")] + ([str(round(h * taux, 2)).replace(".", ",")]
                                                                    if taux else []))
    return len(rows)


# ================================================================== failles des dépendances (OSV.dev)
def _clean_ver(v):
    m = re.search(r"\d+(?:\.\d+){0,3}[\w.-]*", str(v or ""))
    return m.group(0) if m else ""


def find_deps(p):
    """-> [(écosystème, nom, version)] à partir des fichiers du projet (versions exactes si possible)."""
    p = Path(p)
    deps = []
    lock = p / "package-lock.json"
    if lock.exists():
        try:
            d = json.loads(lock.read_text(encoding="utf-8"))
            for k, v in (d.get("packages") or {}).items():
                if k.startswith("node_modules/") and v.get("version") and "/node_modules/" not in k:
                    deps.append(("npm", k[len("node_modules/"):], v["version"]))
        except Exception:
            pass
    elif (p / "package.json").exists():
        try:
            d = json.loads((p / "package.json").read_text(encoding="utf-8"))
            for sec in ("dependencies", "devDependencies"):
                for n, v in (d.get(sec) or {}).items():
                    if _clean_ver(v):
                        deps.append(("npm", n, _clean_ver(v)))
        except Exception:
            pass
    for req in [p / "requirements.txt"] + sorted(p.glob("requirements*.txt")):
        if req.exists():
            for line in req.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.match(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*==\s*([^\s;#]+)", line)
                if m:
                    deps.append(("PyPI", re.sub(r"\[.*\]", "", m.group(1)), m.group(2)))
    cl = p / "Cargo.lock"
    if cl.exists():
        for m in re.finditer(r'name = "([^"]+)"\nversion = "([^"]+)"', cl.read_text(encoding="utf-8", errors="ignore")):
            deps.append(("crates.io", m.group(1), m.group(2)))
    gs = p / "go.sum"
    if gs.exists():
        seen = set()
        for line in gs.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split()
            if len(parts) >= 2 and not parts[1].endswith("/go.mod"):
                k = (parts[0], parts[1].lstrip("v"))
                if k not in seen:
                    seen.add(k)
                    deps.append(("Go", parts[0], parts[1].lstrip("v")))
    uniq = list(dict.fromkeys(deps))
    return uniq[:900]


def audit(deps):
    """Interroge OSV.dev (base publique des failles, sans compte) -> [{"paquet", "version", "failles": [...]}]."""
    out = []
    for i in range(0, len(deps), 300):
        chunk = deps[i:i + 300]
        body = {"queries": [{"package": {"name": n, "ecosystem": e}, "version": v} for e, n, v in chunk]}
        req = urllib.request.Request("https://api.osv.dev/v1/querybatch", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "Viki"})
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.loads(r.read())
        for (e, n, v), item in zip(chunk, res.get("results", [])):
            vulns = item.get("vulns") or []
            if vulns:
                out.append({"ecosysteme": e, "paquet": n, "version": v, "failles": [x["id"] for x in vulns][:6]})
    return out


def audit_text(project, deps, found):
    if not deps:
        return f"{project} : je n'ai trouvé aucun fichier de dépendances (package-lock.json, requirements.txt, " \
               "Cargo.lock, go.sum)."
    if not found:
        return f"✅ {project} : {len(deps)} dépendances vérifiées, aucune faille connue."
    lines = [f"⚠️ {f['paquet']} {f['version']} ({f['ecosysteme']}) : {', '.join(f['failles'])}" for f in found]
    conseil = {"npm": "npm audit fix (ou mets à jour le paquet)", "PyPI": "pip install -U paquet puis mets à jour "
               "requirements.txt", "crates.io": "cargo update -p paquet", "Go": "go get paquet@latest && go mod tidy"}
    eco = sorted({f["ecosysteme"] for f in found})
    return (f"{project} : {len(found)} dépendance(s) avec des failles connues sur {len(deps)} :\n\n" +
            "\n".join(lines) + "\n\nQue faire : " + " ; ".join(conseil.get(e, "mets à jour le paquet") for e in eco) +
            ".\nDétail de chaque faille : https://osv.dev/vulnerability/<identifiant>")


# ================================================================== canard en plastique
DUCK = (" MODE CANARD EN PLASTIQUE : l'utilisateur t'explique un bug de programmation. Ne donne PAS la solution. "
        "Pose une seule question courte à la fois pour l'aider à trouver lui-même (qu'attendais-tu ? que se "
        "passe-t-il vraiment ? qu'as-tu déjà vérifié ? quelle est la dernière chose qui a changé ? peux-tu "
        "reproduire avec moins de code ?). Encourage-le. Si il trouve, félicite-le.")
