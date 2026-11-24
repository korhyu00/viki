"""Outils pour développeurs : surveillance de ports, suivi automatique du terminal, GitHub / GitLab,
notes de code par projet, temps passé par projet et statistiques de la semaine.

Tout est local, sauf GitHub / GitLab (seulement si tu les actives, avec ton propre jeton).
"""
import datetime
import json
import os
import re
import socket
import subprocess
import shutil
import time
import urllib.request
from pathlib import Path

STATE_FILE = None        # fixé par compagnon.py : ~/.config/viki/dev.json (chmod 600 : contient le jeton)


# ------------------------------------------------------------------ état
def load():
    try:
        s = json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    except Exception:
        s = {}
    s.setdefault("ports", [])
    s.setdefault("notes", {})
    s.setdefault("temps", {})
    s.setdefault("forge", {"actif": False, "service": "github", "jeton": "", "url": "https://gitlab.com",
                           "intervalle": 10, "vu": ""})
    return s


def save(s):
    tmp = str(STATE_FILE) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


# ------------------------------------------------------------------ ports
def port_up(port, timeout=0.6):
    for host, fam in (("127.0.0.1", socket.AF_INET), ("::1", socket.AF_INET6)):
        try:
            with socket.socket(fam, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                if s.connect_ex((host, int(port))) == 0:
                    return True
        except Exception:
            pass
    return False


def add_port(s, port, nom=""):
    port = int(port)
    s["ports"] = [p for p in s["ports"] if int(p["port"]) != port] + [{"port": port, "nom": nom.strip()}]
    save(s)


def remove_port(s, port):
    s["ports"] = [p for p in s["ports"] if int(p["port"]) != int(port)]
    save(s)


def port_label(p):
    """« ton serveur « site » (port 3000) » / « ton serveur du port 3000 »"""
    nom = re.sub(r"^(le|la|les|l'|mon|ma|mes|du|de la|de l')\s*", "", (p.get("nom") or "").strip(), flags=re.I)
    return f"ton serveur « {nom} » (port {p['port']})" if nom else f"ton serveur du port {p['port']}"


# ------------------------------------------------------------------ suivi automatique du terminal
HOOK_START = "# >>> viki : suivi du terminal >>>"
HOOK_END = "# <<< viki : suivi du terminal <<<"
_SKIP = ("vim*|nvim*|vi\\ *|nano*|micro*|emacs*|less*|more*|man\\ *|ssh*|mosh*|top|htop*|btop*|watch*|"
         "tail\\ -f*|journalctl\\ -f*|python|python3|ipython*|node|bash|zsh|fish|sudo\\ -i|sudo\\ su*|tmux*|"
         "screen*|mpv*|vlc*|ncdu*|ranger*|yazi*|lazygit*|nvtop*|viki*|git\\ log*|git\\ diff*|docker\\ attach*")
BASH_HOOK = f"""{HOOK_START}
# Prévient Viki quand une commande de plus de ${{VIKI_SEUIL:-60}} s se termine (retire ce bloc pour arrêter).
__viki_t0=0; __viki_ok=0
__viki_pre() {{ [ "$__viki_ok" = 1 ] || return; __viki_ok=0; __viki_t0=$((SECONDS+1)); __viki_cmd=$BASH_COMMAND; }}
__viki_post() {{ local c=$?; if [ "$__viki_t0" != 0 ]; then local d=$((SECONDS+1-__viki_t0))
  case "$__viki_cmd" in {_SKIP}) ;; *) [ $d -ge ${{VIKI_SEUIL:-60}} ] && command -v viki >/dev/null && \\
  (viki fini "$c" "$d" "$__viki_cmd" >/dev/null 2>&1 &) ;; esac; fi; __viki_t0=0; }}
__viki_arm() {{ __viki_ok=1; }}
trap '__viki_pre' DEBUG
PROMPT_COMMAND="__viki_post${{PROMPT_COMMAND:+;$PROMPT_COMMAND}};__viki_arm"
{HOOK_END}
"""
ZSH_HOOK = f"""{HOOK_START}
# Prévient Viki quand une commande de plus de ${{VIKI_SEUIL:-60}} s se termine (retire ce bloc pour arrêter).
autoload -Uz add-zsh-hook
__viki_pre() {{ __viki_t0=$SECONDS; __viki_cmd=$1 }}
__viki_post() {{ local c=$?; if [[ -n $__viki_t0 ]]; then local d=$((SECONDS-__viki_t0))
  case "$__viki_cmd" in {_SKIP}) ;; *) (( d >= ${{VIKI_SEUIL:-60}} )) && (( $+commands[viki] )) && \\
  (viki fini "$c" "$d" "$__viki_cmd" >/dev/null 2>&1 &!) ;; esac; fi; unset __viki_t0 }}
add-zsh-hook preexec __viki_pre
add-zsh-hook precmd __viki_post
{HOOK_END}
"""
FISH_HOOK = f"""{HOOK_START}
function __viki_post --on-event fish_postexec
    set -l c $status
    set -q VIKI_SEUIL; or set -l VIKI_SEUIL 60
    if test (math "$CMD_DURATION / 1000") -ge $VIKI_SEUIL; and type -q viki
        switch $argv[1]
            case 'vim*' 'nvim*' 'nano*' 'less*' 'man *' 'ssh*' 'htop*' 'btop*' 'top' 'tmux*' 'viki*'
            case '*'
                viki fini $c (math "$CMD_DURATION / 1000") "$argv[1]" >/dev/null 2>&1 &
                disown
        end
    end
end
{HOOK_END}
"""


def _rc_files():
    h = Path.home()
    return [(h / ".bashrc", BASH_HOOK), (h / ".zshrc", ZSH_HOOK),
            (h / ".config" / "fish" / "conf.d" / "viki.fish", FISH_HOOK)]


def _strip(txt):
    return re.sub(re.escape(HOOK_START) + r".*?" + re.escape(HOOK_END) + r"\n?", "", txt, flags=re.S)


def hook_installed():
    return any(f.exists() and HOOK_START in f.read_text(errors="ignore") for f, _ in _rc_files())


def install_hook(seuil=60):
    """Ajoute le bloc à ~/.bashrc, ~/.zshrc (s'il existe) et fish (s'il est installé). -> fichiers modifiés"""
    done = []
    for f, block in _rc_files():
        block = block.replace("VIKI_SEUIL:-60", f"VIKI_SEUIL:-{int(seuil)}").replace(
            "set -l VIKI_SEUIL 60", f"set -l VIKI_SEUIL {int(seuil)}")
        if f.name == ".zshrc" and not f.exists() and not shutil.which("zsh"):
            continue
        if f.suffix == ".fish" and not shutil.which("fish"):
            continue
        if f.name == ".bashrc" and not f.exists() and not shutil.which("bash"):
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        old = f.read_text(errors="ignore") if f.exists() else ""
        if f.exists() and not (f.parent / (f.name + ".avant-viki")).exists():
            (f.parent / (f.name + ".avant-viki")).write_text(old, encoding="utf-8")
        f.write_text(_strip(old).rstrip("\n") + ("\n\n" if old.strip() else "") + block)
        done.append(str(f))
    return done


def uninstall_hook():
    done = []
    for f, _ in _rc_files():
        if f.exists() and HOOK_START in f.read_text(errors="ignore"):
            if f.suffix == ".fish":
                f.unlink()
            else:
                f.write_text(_strip(f.read_text(errors="ignore")))
            done.append(str(f))
    return done


# ------------------------------------------------------------------ git
def git(p, *a, timeout=20):
    exe = shutil.which("git")
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "-C", str(p)] + list(a), capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def name_of(p):
    return Path(p).name


def last_activity(p):
    """Dernière modification d'un fichier du projet (fichiers modifiés / nouveaux, ou index git)."""
    newest = 0.0
    try:
        newest = (Path(p) / ".git" / "index").stat().st_mtime
    except Exception:
        pass
    for rel in git(p, "ls-files", "-m", "-o", "--exclude-standard").splitlines()[:400]:
        try:
            newest = max(newest, (Path(p) / rel).stat().st_mtime)
        except Exception:
            pass
    return newest


def active_project(projets):
    best = max(((last_activity(p), p) for p in projets if Path(p).is_dir()), default=(0, None))
    return best[1]


def note_time(s, projets, step_min=5):
    """Appelé toutes les 5 min : chaque projet modifié pendant ce temps gagne 5 min de « code »."""
    now = time.time()
    today = datetime.date.today().isoformat()
    day = s["temps"].setdefault(today, {})
    hit = []
    for p in projets:
        if Path(p).is_dir() and now - last_activity(p) < step_min * 60 + 30:
            day[name_of(p)] = day.get(name_of(p), 0) + step_min
            hit.append(name_of(p))
    limit = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    for d in [d for d in s["temps"] if d < limit]:
        del s["temps"][d]
    if hit:
        save(s)
    return hit


def minutes(s, days=1):
    start = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
    tot = {}
    for d, projs in s["temps"].items():
        if d >= start:
            for k, v in projs.items():
                tot[k] = tot.get(k, 0) + v
    return tot


def fmt_min(m):
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d}"


def todo_count(p):
    out = git(p, "grep", "-c", "-I", "-E", r"\b(TODO|FIXME|XXX)\b")
    return sum(int(l.rsplit(":", 1)[1]) for l in out.splitlines() if ":" in l and l.rsplit(":", 1)[1].isdigit())


def week_stats(s, projets):
    """Les 7 derniers jours : commits, lignes, temps, par projet."""
    out = []
    mins = minutes(s, 7)
    for p in projets:
        if not Path(p).is_dir():
            continue
        email = git(p, "config", "user.email")
        args = ["log", "--since=7.days", "--no-merges", "--shortstat", "--format=tformat:@@"]
        if email:
            args.append(f"--author={email}")
        log = git(p, *args, timeout=40)
        commits = log.count("@@")
        plus = sum(int(x) for x in re.findall(r"(\d+) insertions?", log))
        moins = sum(int(x) for x in re.findall(r"(\d+) deletions?", log))
        m = mins.get(name_of(p), 0)
        if commits or m:
            out.append({"projet": name_of(p), "commits": commits, "plus": plus, "moins": moins, "minutes": m})
    return sorted(out, key=lambda x: (-x["minutes"], -x["commits"]))


def week_text(stats):
    if not stats:
        return "Pas de code cette semaine dans tes projets suivis… repos bien mérité ?"
    tot_c = sum(x["commits"] for x in stats)
    tot_m = sum(x["minutes"] for x in stats)
    parts = [f"{x['projet']} : {x['commits']} commit{'s' if x['commits'] > 1 else ''}"
             + (f", {fmt_min(x['minutes'])}" if x["minutes"] else "") for x in stats[:4]]
    return (f"Ta semaine de code : {tot_c} commit{'s' if tot_c > 1 else ''}"
            + (f" et environ {fmt_min(tot_m)} de travail" if tot_m else "") + ". " + " ; ".join(parts) + ".")


# ------------------------------------------------------------------ notes de code
def add_note(s, projet, texte):
    s["notes"].setdefault(projet, []).append({"texte": texte.strip(), "date": time.strftime("%d/%m/%Y")})
    save(s)


def remove_note(s, projet, i):
    lst = s["notes"].get(projet, [])
    if 0 <= i < len(lst):
        lst.pop(i)
        if not lst:
            s["notes"].pop(projet, None)
        save(s)


def notes_text(s):
    lines = []
    for proj, lst in s["notes"].items():
        for i, n in enumerate(lst, 1):
            lines.append(f"[{proj}] {i}. {n['texte']}  ({n['date']})")
    return lines


# ------------------------------------------------------------------ GitHub / GitLab
RAISONS = {"review_requested": "on te demande une relecture", "ci_activity": "résultat de la CI",
           "mention": "on t'a mentionné", "team_mention": "ton équipe est mentionnée", "assign": "on te l'a assigné",
           "author": "activité sur ta contribution", "comment": "nouveau commentaire",
           "state_change": "changement d'état", "security_alert": "alerte de sécurité",
           "subscribed": "nouvelle activité", "manual": "nouvelle activité",
           "build_failed": "la CI a échoué ❌", "approval_required": "approbation demandée",
           "mentioned": "on t'a mentionné", "directly_addressed": "on s'adresse à toi", "assigned": "on te l'a assigné",
           "marked": "à faire", "unmergeable": "conflit de fusion", "merge_train_removed": "retiré du train de fusion",
           "member_access_requested": "demande d'accès"}


def _ssl():
    try:
        import ia_api
        return ia_api._ssl_ctx()
    except Exception:
        import ssl
        return ssl.create_default_context()


def _get(url, headers, timeout=20):
    req = urllib.request.Request(url, headers=dict(headers, **{"User-Agent": "Viki"}))
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
        return json.loads(r.read().decode("utf-8"))


def _gh_headers(tok):
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def forge_test(f):
    try:
        if f.get("service") == "gitlab":
            u = _get(f["url"].rstrip("/") + "/api/v4/user", {"PRIVATE-TOKEN": f["jeton"]})
            return True, u.get("username", "?")
        u = _get("https://api.github.com/user", _gh_headers(f["jeton"]))
        return True, u.get("login", "?")
    except Exception as e:
        t = str(e)
        if "401" in t:
            return False, "jeton refusé (401) : vérifie-le ou crée-en un nouveau"
        return False, t[:160]


def forge_check(s):
    """Nouveautés depuis la dernière fois : [{"titre", "projet", "raison", "lien"}]."""
    f = s["forge"]
    out = []
    if f.get("service") == "gitlab":
        base = f["url"].rstrip("/")
        todos = _get(base + "/api/v4/todos?state=pending&per_page=30", {"PRIVATE-TOKEN": f["jeton"]})
        vu = int(f.get("vu") or 0)
        first = not f.get("vu")
        for t in todos:
            if int(t.get("id", 0)) > vu:
                out.append({"titre": (t.get("target") or {}).get("title", t.get("body", ""))[:120],
                            "projet": (t.get("project") or {}).get("path_with_namespace", ""),
                            "raison": RAISONS.get(t.get("action_name", ""), t.get("action_name", "")),
                            "lien": t.get("target_url", "")})
        if todos:
            f["vu"] = str(max(int(t.get("id", 0)) for t in todos))
        save(s)
        return [] if first else out
    since = f.get("vu") or ""
    url = "https://api.github.com/notifications?per_page=30" + (f"&since={since}" if since else "")
    notes = _get(url, _gh_headers(f["jeton"]))
    f["vu"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save(s)
    if not since:                       # premier passage : on ne déballe pas tout l'arriéré
        return []
    for n in notes:
        subj = n.get("subject") or {}
        api = subj.get("url") or ""
        lien = re.sub(r"https://api\.github\.com/repos/", "https://github.com/", api).replace("/pulls/", "/pull/")
        out.append({"titre": subj.get("title", "")[:120], "projet": (n.get("repository") or {}).get("full_name", ""),
                    "raison": RAISONS.get(n.get("reason", ""), n.get("reason", "")), "lien": lien})
    return out
