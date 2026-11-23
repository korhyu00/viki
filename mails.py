"""Mails : Viki relève ta boîte (IMAP), te prévient des nouveaux messages et peut te les lire.

- Rien n'est marqué comme lu sans que tu le demandes (lecture en « aperçu »).
- Le mot de passe d'application est gardé sur ton PC, dans un fichier lisible par toi seul.
- Outlook / Hotmail : Microsoft n'accepte plus les mots de passe pour IMAP (connexion OAuth obligatoire),
  ils ne sont donc pas pris en charge ici.
"""
import datetime
import email
import email.header
import email.utils
import imaplib
import json
import os
import re
import ssl
from pathlib import Path

FOURNISSEURS = {
    "gmail": ("Gmail", "imap.gmail.com", 993,
              "Mot de passe d'application obligatoire : active la validation en deux étapes, puis crée-le sur "
              "myaccount.google.com/apppasswords.", "https://myaccount.google.com/apppasswords",
              "https://mail.google.com"),
    "yahoo": ("Yahoo", "imap.mail.yahoo.com", 993, "Mot de passe d'application (Sécurité du compte Yahoo).",
              "https://login.yahoo.com/account/security", "https://mail.yahoo.com"),
    "icloud": ("iCloud", "imap.mail.me.com", 993, "Mot de passe pour app (appleid.apple.com → Connexion et "
               "sécurité).", "https://account.apple.com", "https://www.icloud.com/mail"),
    "fastmail": ("Fastmail", "imap.fastmail.com", 993, "Mot de passe d'application (Réglages → Confidentialité "
                 "et sécurité).", "https://app.fastmail.com/settings/security/apps", "https://app.fastmail.com"),
    "gmx": ("GMX", "imap.gmx.com", 993, "Active l'accès IMAP dans les réglages GMX.", "", "https://www.gmx.com"),
    "orange": ("Orange", "imap.orange.fr", 993, "Ton mot de passe Orange (ou mot de passe d'application).", "",
               "https://messagerie.orange.fr"),
    "free": ("Free", "imap.free.fr", 993, "Ton mot de passe de messagerie Free.", "", "https://webmail.free.fr"),
    "laposte": ("La Poste", "imap.laposte.net", 993, "Active « logiciels de messagerie » dans tes réglages.", "",
                "https://www.laposte.net"),
    "sfr": ("SFR", "imap.sfr.fr", 993, "Ton mot de passe SFR mail.", "", "https://webmail.sfr.fr"),
    "proton": ("Proton (Bridge)", "127.0.0.1", 1143, "Il faut Proton Mail Bridge lancé sur ton PC ; utilise le "
               "mot de passe donné par le Bridge.", "https://proton.me/mail/bridge", "https://mail.proton.me"),
    "autre": ("Autre (IMAP)", "", 993, "Serveur IMAP de ton fournisseur (souvent imap.<domaine>).", "", ""),
}

SETTINGS_FILE = None          # fixé par compagnon.py : ~/.config/viki/mail.json


def load():
    try:
        return json.loads(Path(SETTINGS_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {"actif": False, "fournisseur": "gmail", "adresse": "", "mdp": "", "serveur": "", "port": 993,
                "intervalle": 5, "notif": True, "vu": -1}


def save(s):
    tmp = str(SETTINGS_FILE) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SETTINGS_FILE)
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except OSError:
        pass


def server_of(s):
    f = FOURNISSEURS.get(s.get("fournisseur", "autre"), FOURNISSEURS["autre"])
    return (s.get("serveur") or f[1]).strip(), int(s.get("port") or f[2])


def _decode(h):
    if not h:
        return ""
    out = []
    for part, enc in email.header.decode_header(h):
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", "replace"))
            except LookupError:
                out.append(part.decode("utf-8", "replace"))
        else:
            out.append(part)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _sender(h):
    name, addr = email.utils.parseaddr(_decode(h))
    return name or addr or "quelqu'un", addr


def _body_text(msg, limit=8000):
    """Texte d'un message (partie texte, sinon HTML nettoyé)."""
    parts = msg.walk() if msg.is_multipart() else [msg]
    html = ""
    for p in parts:
        ct = p.get_content_type()
        if p.get_content_disposition() == "attachment":
            continue
        try:
            payload = p.get_payload(decode=True)
        except Exception:
            payload = None
        if not payload:
            continue
        cs = p.get_content_charset() or "utf-8"
        try:
            txt = payload.decode(cs, "replace")
        except LookupError:
            txt = payload.decode("utf-8", "replace")
        if ct == "text/plain":
            return re.sub(r"\n{3,}", "\n\n", txt).strip()[:limit]
        if ct == "text/html" and not html:
            html = txt
    if html:
        import html as _h
        html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
        html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", html)
        txt = _h.unescape(re.sub(r"<[^>]+>", " ", html))
        return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", txt)).strip()[:limit]
    return ""


def connect(s, timeout=25):
    host, port = server_of(s)
    if not host:
        raise ValueError("serveur IMAP manquant")
    if port == 993:
        im = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=timeout)
    else:
        im = imaplib.IMAP4(host, port, timeout=timeout)
        try:
            im.starttls(ssl_context=ssl.create_default_context())
        except Exception:
            if host not in ("127.0.0.1", "localhost"):
                raise
    im.login(s.get("adresse", ""), s.get("mdp", ""))
    return im


def explain(e):
    t = str(e)
    m = re.fullmatch(r"\s*b(['\"])(.*)\1\s*", t, re.S)          # b'[ALERT] …' -> [ALERT] …
    if m:
        t = m.group(2)
    low = t.lower()
    if "application-specific password" in low or "app password" in low or "185833" in low:
        return ("Gmail refuse ton mot de passe habituel : il faut un « mot de passe d'application ». "
                "1) Active la validation en 2 étapes sur ton compte Google. "
                "2) Va sur myaccount.google.com/apppasswords, crée un mot de passe nommé « Viki ». "
                "3) Colle les 16 lettres (sans espaces) à la place de ton mot de passe ici.")
    if "web login required" in low or "please log in via your web browser" in low:
        return ("ton fournisseur bloque la connexion : connecte-toi une fois à ton webmail depuis ton navigateur, "
                "vérifie que l'accès IMAP est activé dans ses réglages, puis réessaie.")
    if "authenticationfailed" in low or "invalid credentials" in low or "login failed" in low or "auth" in low:
        return ("connexion refusée : vérifie l'adresse et le mot de passe d'application (pas ton mot de passe "
                "habituel pour Gmail, Yahoo, iCloud…)")
    if "timed out" in low or "getaddrinfo" in low or "name or service" in low or "refused" in low:
        return "serveur injoignable (internet coupé, ou mauvaise adresse de serveur)"
    return t[:200]


def test(s):
    try:
        im = connect(s)
        typ, data = im.select("INBOX", readonly=True)
        n = int(data[0]) if typ == "OK" and data and data[0] else 0
        im.logout()
        return True, n
    except Exception as e:
        return False, explain(e)


def unread(s, limit=20, since_uid=0, body=False):
    """Messages non lus (du plus récent au plus ancien) : liste de dict
    {uid, de, adresse, sujet, date, texte}. Ne les marque PAS comme lus."""
    im = connect(s)
    try:
        im.select("INBOX", readonly=True)
        typ, data = im.uid("search", None, "UNSEEN")
        uids = [int(u) for u in (data[0].split() if typ == "OK" and data and data[0] else [])]
        uids = [u for u in uids if u > since_uid]
        uids = sorted(uids, reverse=True)[:limit]
        out = []
        for u in uids:
            what = "(BODY.PEEK[]<0.120000>)" if body else "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
            typ, msgdata = im.uid("fetch", str(u), what)
            raw = next((x[1] for x in msgdata or [] if isinstance(x, tuple)), b"")
            msg = email.message_from_bytes(raw or b"")
            name, addr = _sender(msg.get("From"))
            try:
                dt = email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
            except Exception:
                dt = None
            out.append({"uid": u, "de": name, "adresse": addr, "sujet": _decode(msg.get("Subject")) or "(sans sujet)",
                        "date": dt.astimezone().strftime("%d/%m %H:%M") if dt else "",
                        "texte": _body_text(msg) if body else ""})
        return out
    finally:
        try:
            im.logout()
        except Exception:
            pass


def mark_read(s, uid):
    im = connect(s)
    try:
        im.select("INBOX")
        im.uid("store", str(uid), "+FLAGS", "(\\Seen)")
    finally:
        try:
            im.logout()
        except Exception:
            pass


def max_uid(s):
    """UID le plus haut de la boîte : au premier lancement, on ne notifie pas tout l'arriéré."""
    im = connect(s)
    try:
        im.select("INBOX", readonly=True)
        typ, data = im.uid("search", None, "ALL")
        uids = [int(u) for u in (data[0].split() if typ == "OK" and data and data[0] else [])]
        return max(uids) if uids else 0
    finally:
        try:
            im.logout()
        except Exception:
            pass
