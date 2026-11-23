"""💻 Le raccourci Alt+E dans ton terminal : tu tapes une commande, Alt+E, et Viki te l'explique AVANT que tu
appuies sur Entrée (en rouge si elle est dangereuse). Quelques lignes marquées « Viki » dans ta config de shell
(bash, zsh) ou un petit fichier pour fish ; « retirer » les enlève."""
import os
import re
from pathlib import Path

import touches

DEBUT, FIN = "# >>> viki : Alt+E explique la commande >>>", "# <<< viki <<<"
HOME = Path.home()
FISH = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "fish" / "conf.d" / "viki.fish"


def _bloc(shell):
    v = touches.lanceur()
    if shell == "bash":
        corps = (f'_viki_explique() {{ {v} explique "$READLINE_LINE"; }}\n'
                 """bind -x '"\\ee": _viki_explique' 2>/dev/null""")
    else:
        corps = (f"viki-explique() {{ {v} explique \"$BUFFER\" </dev/null; zle reset-prompt }}\n"
                 "zle -N viki-explique\nbindkey '^[e' viki-explique")
    return f"\n{DEBUT}\n{corps}\n{FIN}\n"


def _sans_bloc(texte):
    return re.sub(r"\n?" + re.escape(DEBUT) + r".*?" + re.escape(FIN) + r"\n?", "\n", texte, flags=re.S)


def installer():
    faits = []
    for shell, rc in (("bash", HOME / ".bashrc"), ("zsh", HOME / ".zshrc")):
        if rc.exists():
            t = _sans_bloc(rc.read_text(encoding="utf-8", errors="ignore"))
            rc.write_text(t.rstrip("\n") + "\n" + _bloc(shell), encoding="utf-8")
            faits.append(shell)
    if FISH.parent.parent.exists():
        FISH.parent.mkdir(parents=True, exist_ok=True)
        FISH.write_text(f"{DEBUT}\nfunction _viki_explique\n    {touches.lanceur()} explique (commandline)\n"
                        f"    commandline -f repaint\nend\nbind \\ee _viki_explique\n{FIN}\n", encoding="utf-8")
        faits.append("fish")
    return faits


def retirer():
    for rc in (HOME / ".bashrc", HOME / ".zshrc"):
        if rc.exists():
            t = rc.read_text(encoding="utf-8", errors="ignore")
            if DEBUT in t:
                rc.write_text(_sans_bloc(t).rstrip("\n") + "\n", encoding="utf-8")
    try:
        FISH.unlink()
    except OSError:
        pass


def installe():
    for rc in (HOME / ".bashrc", HOME / ".zshrc"):
        try:
            if DEBUT in rc.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            pass
    return FISH.exists()
