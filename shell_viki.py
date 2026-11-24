"""💻 Le raccourci Alt+E dans ton terminal : tu tapes une commande, Alt+E, et Viki te l'explique AVANT que tu
appuies sur Entrée (en rouge si elle est dangereuse). Quelques lignes marquées « Viki » dans ta config de shell
(bash, zsh) ou un petit fichier pour fish ; « retirer » les enlève."""
import os
import re
from pathlib import Path

import touches

DEBUT, FIN = "# >>> viki : Alt+E explique la commande >>>", "# <<< viki <<<"
HOME = Path.home()
if os.path.exists("/.flatpak-info"):        # dans le Flatpak, XDG_CONFIG_HOME est celui de la boîte
    FISH = HOME / ".config" / "fish" / "conf.d" / "viki.fish"
else:
    FISH = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "fish" / "conf.d" / "viki.fish"
# ce que le shell écrit pour Viki : le dossier courant, et les commandes qui échouent (rien d'autre)
FIC = "$HOME/.local/share/viki"


BASH_SUIVI = r"""_viki_n=$(HISTTIMEFORMAT= history 1 | awk '{print $1}')
_viki_apres() { local c=$? n; n=$(HISTTIMEFORMAT= history 1 | awk '{print $1}')
  mkdir -p "$HOME/.local/share/viki"; printf '%s' "$PWD" > "$HOME/.local/share/viki/dossier" 2>/dev/null
  if [ "$n" != "$_viki_n" ] && [ $c -ne 0 ] && [ $c -ne 130 ] && [ $c -ne 148 ]; then
    printf '%s\t%s\t%s\n' "$c" "$(HISTTIMEFORMAT= history 1 | sed 's/^ *[0-9]* *//')" "$PWD" >> "$HOME/.local/share/viki/terminal"
  fi; _viki_n=$n; return $c; }
case ";$PROMPT_COMMAND;" in *";_viki_apres;"*) ;; *) PROMPT_COMMAND="_viki_apres${PROMPT_COMMAND:+;$PROMPT_COMMAND}";; esac"""
ZSH_SUIVI = r"""_viki_avant() { _viki_lance=1 }
_viki_apres() { local c=$?; mkdir -p "$HOME/.local/share/viki"; print -r -- "$PWD" >| "$HOME/.local/share/viki/dossier"
  if [[ -n $_viki_lance && $c -ne 0 && $c -ne 130 && $c -ne 148 ]]; then
    print -r -- "$c"$'\t'"$(fc -ln -1)"$'\t'"$PWD" >> "$HOME/.local/share/viki/terminal"; fi; unset _viki_lance }
autoload -Uz add-zsh-hook; add-zsh-hook preexec _viki_avant; add-zsh-hook precmd _viki_apres"""
FISH_SUIVI = r"""function _viki_apres --on-event fish_postexec
    set -l c $status
    mkdir -p $HOME/.local/share/viki; echo $PWD > $HOME/.local/share/viki/dossier
    if test -n "$argv"; and test $c -ne 0; and test $c -ne 130; and test $c -ne 148
        printf '%s\t%s\t%s\n' $c "$argv" $PWD >> $HOME/.local/share/viki/terminal
    end
end"""


def _bloc(shell):
    v = touches.lanceur()
    if shell == "bash":
        corps = (f'_viki_explique() {{ {v} explique "$READLINE_LINE"; }}\n'
                 """bind -x '"\\ee": _viki_explique' 2>/dev/null\n""" + BASH_SUIVI)
    else:
        corps = (f"viki-explique() {{ {v} explique \"$BUFFER\" </dev/null; zle reset-prompt }}\n"
                 "zle -N viki-explique\nbindkey '^[e' viki-explique\n" + ZSH_SUIVI)
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
                        f"    commandline -f repaint\nend\nbind \\ee _viki_explique\n{FISH_SUIVI}\n{FIN}\n",
                        encoding="utf-8")
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
