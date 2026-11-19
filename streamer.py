"""Mode streamer : Viki lit le chat Twitch d'une chaîne et réagit à certains messages.

Lecture seule et anonyme (pas besoin de compte ni de jeton) : connexion IRC à irc.chat.twitch.tv avec un
pseudo « justinfan », comme le lecteur de chat intégré. Internet est utilisé seulement quand le mode est
lancé. Elle n'écrit jamais dans le chat : elle répond dans sa bulle (que tes spectateurs voient à l'écran).
"""
import random
import re
import socket
import ssl
import threading
import time

HOST, PORT = "irc.chat.twitch.tv", 6697
LINK = re.compile(r"(https?://|www\.|\.(com|fr|net|org|gg|tv|io|ly)\b)", re.I)
NOTICE = re.compile(r"^@(?P<tags>\S+) :\S+ USERNOTICE #(?P<chan>\S+)(?: :(?P<msg>.*))?$")
PRIV = re.compile(r"^(?:@(?P<tags>\S+) )?:(?P<user>[^!\s]+)!\S+ PRIVMSG #(?P<chan>\S+) :(?P<msg>.*)$")


def parse(line):
    """Une ligne IRC -> (pseudo affiché, message) ou None."""
    m = PRIV.match(line.rstrip("\r\n"))
    if not m:
        return None
    user = m.group("user")
    tags = m.group("tags") or ""
    for t in tags.split(";"):
        if t.startswith("display-name=") and len(t) > 13:
            user = t[13:].replace("\\s", " ")
    return user, m.group("msg").strip()


def _tags(raw):
    out = {}
    for t in (raw or "").split(";"):
        k, _, v = t.partition("=")
        out[k] = v.replace("\\s", " ").replace("\\:", ";").replace("\\\\", "\\")
    return out


def parse_event(line):
    """Abonnement, réabonnement, abonnement offert, raid ou bits -> (genre, pseudo, détail) ou None."""
    line = line.rstrip("\r\n")
    m = NOTICE.match(line)
    if m:
        t = _tags(m.group("tags"))
        kind = t.get("msg-id", "")
        user = t.get("display-name") or t.get("login") or "quelqu'un"
        if kind in ("sub", "resub"):
            mois = t.get("msg-param-cumulative-months", "") or t.get("msg-param-months", "")
            return ("resub" if kind == "resub" else "sub", user, mois)
        if kind == "subgift":
            return ("gift", user, t.get("msg-param-recipient-display-name", ""))
        if kind == "submysterygift":
            return ("gifts", user, t.get("msg-param-mass-gift-count", "1"))
        if kind == "raid":
            return ("raid", t.get("msg-param-displayName") or user, t.get("msg-param-viewerCount", ""))
        return None
    m = PRIV.match(line)
    if m and m.group("tags"):
        t = _tags(m.group("tags"))
        if t.get("bits", "").isdigit():
            return ("bits", t.get("display-name") or m.group("user"), t["bits"])
        if t.get("first-msg") == "1":
            return ("premier", t.get("display-name") or m.group("user"), "")
    return None


ALERT_LINES = {
    "sub": ["Merci {u} pour l'abonnement ! Bienvenue dans la famille ! 💖", "{u} s'abonne ! Trop gentil, merci !"],
    "resub": ["{u} se réabonne, {d} mois déjà ! Merci pour ta fidélité ! 💖", "Merci {u} pour ces {d} mois !"],
    "gift": ["{u} offre un abonnement à {d} ! Quelle générosité !", "Merci {u} pour le cadeau à {d} ! 🎁"],
    "gifts": ["{u} offre {d} abonnements ! Incroyable, merci ! 🎁", "Pluie de cadeaux ! Merci {u} pour les {d} abos !"],
    "raid": ["Raid de {u} avec {d} personnes ! Bienvenue à tous ! 🎉", "Oh, un raid ! Merci {u}, salut tout le monde !"],
    "bits": ["Merci {u} pour les {d} bits ! ✨", "{d} bits de {u} ! Merci beaucoup !"],
    "premier": ["Bienvenue {u}, c'est ton premier message ici ! 👋", "Oh, un nouveau ! Salut {u} !"],
}


def alert_text(ev):
    import random as _r
    kind, user, d = ev
    t = _r.choice(ALERT_LINES.get(kind, ["Merci {u} !"]))
    if not d:
        t = t.replace(", {d} mois déjà", "").replace("ces {d} mois", "ton soutien").replace(" avec {d} personnes", "")
    return t.replace("{u}", user).replace("{d}", str(d))


def channel_of(text):
    """« https://twitch.tv/Pseudo », « @pseudo » ou « pseudo » -> « pseudo »."""
    t = (text or "").strip().rstrip("/")
    t = re.sub(r"^.*twitch\.tv/", "", t, flags=re.I)
    return re.sub(r"[^a-zA-Z0-9_]", "", t.lstrip("@#")).lower()


def interesting(user, msg, names=(), bots=("nightbot", "streamelements", "streamlabs", "moobot", "fossabot")):
    """Score d'un message : 0 = ignoré. Les questions et les messages qui la nomment passent devant."""
    if not msg or user.lower() in bots or msg.startswith("!") or LINK.search(msg):
        return 0
    if len(msg) > 220 or len(msg) < 2:
        return 0
    low = msg.lower()
    s = 1
    if any(n and n.lower() in low for n in names):
        s += 5
    if "?" in msg:
        s += 2
    if re.search(r"\b(salut|bonjour|coucou|hello|hi|yo|bonsoir|cc)\b", low):
        s += 1
    return s


class Chat:
    """Fil qui lit le chat. on_message(pseudo, message) est appelé depuis le fil : à relayer à l'interface."""

    def __init__(self, channel, on_message, on_state=None, on_event=None):
        self.channel = channel_of(channel)
        self.on_message, self.on_state = on_message, on_state or (lambda s: None)
        self.on_event = on_event
        self.stop = False
        self.sock = None
        self.th = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.th.start()
        return self

    def close(self):
        self.stop = True
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

    def _run(self):
        delay = 2
        while not self.stop:
            try:
                raw = socket.create_connection((HOST, PORT), timeout=20)
                self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
                self.sock.settimeout(360)
                nick = f"justinfan{random.randint(10000, 99999)}"
                self.sock.sendall(f"CAP REQ :twitch.tv/tags twitch.tv/commands\r\nPASS SCHMOOPIIE\r\nNICK {nick}\r\n"
                                  f"JOIN #{self.channel}\r\n".encode())
                self.on_state("connecte")
                delay = 2
                buf = b""
                while not self.stop:
                    data = self.sock.recv(4096)
                    if not data:
                        raise ConnectionError("fermé")
                    buf += data
                    while b"\r\n" in buf:
                        line, buf = buf.split(b"\r\n", 1)
                        text = line.decode("utf-8", "replace")
                        if text.startswith("PING"):
                            self.sock.sendall(("PONG" + text[4:] + "\r\n").encode())
                            continue
                        if self.on_event:
                            ev = parse_event(text)
                            if ev:
                                self.on_event(ev)
                                if ev[0] not in ("bits", "premier"):
                                    continue
                        p = parse(text)
                        if p:
                            self.on_message(*p)
            except Exception as e:
                if self.stop:
                    break
                self.on_state(f"erreur:{str(e)[:80]}")
                time.sleep(delay)
                delay = min(60, delay * 2)
        self.on_state("arrete")
