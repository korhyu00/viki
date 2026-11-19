"""IA en ligne (optionnelle) : ChatGPT, Claude, Gemini, Mistral, Groq, DeepSeek, OpenRouter,
ou tout serveur « compatible OpenAI » (LM Studio, llama.cpp server, vLLM…).

Rien ne part sur internet tant que l'utilisateur n'a pas choisi un de ces fournisseurs
et collé sa propre clé dans Réglages → Discussion.
"""
import json
import os
import ssl
import urllib.error
import urllib.request

# tarif : "local" (gratuit, sur ton PC), "sans_cle" (gratuit, en ligne, sans compte),
#         "gratuit" (clé gratuite, avec un quota par jour), "payant" (clé + crédit)
FOURNISSEURS = {
    "ollama": {"court": "Ollama", "tarif": "local", "type": "ollama",
               "info": "sur ton PC — gratuit, sans clé, privé"},
    "perso": {"court": "LM Studio / autre serveur", "tarif": "local", "type": "openai",
              "url": "http://localhost:1234/v1", "modele": "", "cle_url": "",
              "info": "LM Studio, llama.cpp… — gratuit et sans clé s'il tourne sur ton PC"},
    "pollinations": {"court": "Pollinations", "tarif": "sans_cle", "type": "openai",
                     "url": "https://text.pollinations.ai/openai", "modele": "openai-fast",
                     "url_cle": "https://gen.pollinations.ai/v1", "modele_cle": "openai",
                     "cle_url": "https://enter.pollinations.ai", "sans_cle": True,
                     "info": "en ligne — gratuit SANS clé, mais lent (≈ 1 message / 15 s) et expérimental"},
    "gemini": {"court": "Gemini", "tarif": "gratuit", "type": "openai",
               "url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "modele": "gemini-3.6-flash", "cle_url": "https://aistudio.google.com/apikey",
               "info": "Google — clé gratuite (quota par jour), payant au-delà"},
    "groq": {"court": "Groq", "tarif": "gratuit", "type": "openai", "url": "https://api.groq.com/openai/v1",
             "modele": "openai/gpt-oss-120b", "cle_url": "https://console.groq.com/keys",
             "info": "très rapide — clé gratuite (quota par jour)"},
    "mistral": {"court": "Mistral", "tarif": "gratuit", "type": "openai", "url": "https://api.mistral.ai/v1",
                "modele": "mistral-small-latest", "cle_url": "https://console.mistral.ai/api-keys",
                "info": "français — clé gratuite (offre Free, quota), payant au-delà"},
    "openrouter": {"court": "OpenRouter", "tarif": "gratuit", "type": "openai",
                   "url": "https://openrouter.ai/api/v1", "modele": "google/gemma-4-31b-it:free",
                   "cle_url": "https://openrouter.ai/keys",
                   "info": "des centaines de modèles — ceux en « :free » sont gratuits (≈ 50 messages/jour)"},
    "openai": {"court": "ChatGPT", "tarif": "payant", "type": "openai", "url": "https://api.openai.com/v1",
               "modele": "gpt-5.4-mini", "cle_url": "https://platform.openai.com/api-keys",
               "info": "OpenAI — payant (crédit à acheter)"},
    "anthropic": {"court": "Claude", "tarif": "payant", "type": "anthropic", "url": "https://api.anthropic.com/v1",
                  "modele": "claude-haiku-5-5", "cle_url": "https://platform.claude.com/settings/keys",
                  "info": "Anthropic — payant (crédit à acheter)"},
    "deepseek": {"court": "DeepSeek", "tarif": "payant", "type": "openai", "url": "https://api.deepseek.com/v1",
                 "modele": "deepseek-chat", "cle_url": "https://platform.deepseek.com/api_keys",
                 "info": "payant, mais très bon marché"},
}
TARIFS = {"local": "💻 Sur ton PC", "sans_cle": "🆓 Gratuit sans clé", "gratuit": "🆓 Gratuit avec clé",
          "payant": "💳 Payant"}
for _f in FOURNISSEURS.values():
    _f["nom"] = f"{TARIFS[_f['tarif']].split(' ', 1)[0]} {_f['court']} — {_f['info']}"

_CTX = None


def _ssl_ctx():
    """Certificats : ceux du système, où qu'ils soient selon la distribution."""
    global _CTX
    if _CTX is None:
        _CTX = ssl.create_default_context()
        if not os.environ.get("SSL_CERT_FILE"):
            for f in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
                      "/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/ca-bundle.pem",
                      "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem"):
                if os.path.exists(f):
                    try:
                        _CTX.load_verify_locations(f)
                    except Exception:
                        pass
                    break
    return _CTX


SETTINGS_FILE = None          # fixé par compagnon.py (~/.config/compagnon/ia_en_ligne.json)


def load_settings():
    try:
        return json.loads(open(SETTINGS_FILE, encoding="utf-8").read())
    except Exception:
        return {"fournisseur": "ollama", "api": {}}


def save_settings(s):
    """Fichier lisible seulement par l'utilisateur (il contient les clés)."""
    tmp = str(SETTINGS_FILE) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SETTINGS_FILE)
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except OSError:
        pass


def conf_from(s=None, pid=None):
    """Réglages du fournisseur choisi (dict utilisable par les fonctions ci-dessous)."""
    s = s or load_settings()
    pid = pid or s.get("fournisseur", "ollama")
    if pid not in FOURNISSEURS:
        pid = "ollama"
    base = FOURNISSEURS[pid]
    perso = s.get("api", {}).get(pid, {})
    cle = perso.get("cle", "").strip()
    url, modele = base.get("url", ""), base.get("modele", "")
    if cle and base.get("url_cle"):              # Pollinations avec clé : nouvelle adresse, tous les modèles
        url, modele = base["url_cle"], base.get("modele_cle", modele)
    anonyme = bool(base.get("sans_cle") and not cle)
    return {"id": pid, "type": base["type"], "nom": base["court"], "tarif": base["tarif"],
            "url": (perso.get("url") or url).rstrip("/"), "cle": cle,
            "modele": perso.get("modele") or modele,
            "anonyme": anonyme}


def is_remote(s=None):
    return (s or load_settings()).get("fournisseur", "ollama") != "ollama"


def ready(conf):
    if conf["type"] == "ollama":
        return False
    if conf["id"] == "perso" or FOURNISSEURS[conf["id"]].get("sans_cle"):
        return bool(conf["url"] and conf["modele"])
    return bool(conf["cle"] and conf["modele"])


def _headers(conf):
    h = {"Content-Type": "application/json", "User-Agent": "Viki"}
    if conf["type"] == "anthropic":
        h["x-api-key"] = conf["cle"]
        h["anthropic-version"] = "2023-06-01"
    elif conf["cle"]:
        h["Authorization"] = "Bearer " + conf["cle"]
    if conf["id"] == "openrouter":
        h["X-Title"] = "Viki"
    return h


def _anthropic_body(conf, messages, max_tokens, stream):
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    conv = []
    for m in messages:
        if m["role"] not in ("user", "assistant") or not str(m.get("content", "")).strip():
            continue
        if m.get("images"):                                   # images (lecture de bulles de manga…)
            conv.append({"role": m["role"], "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b}}
                for b in m["images"]] + [{"type": "text", "text": m["content"]}]})
        elif conv and conv[-1]["role"] == m["role"] and isinstance(conv[-1]["content"], str):
            conv[-1]["content"] += "\n" + m["content"]         # deux messages du même côté : on fusionne
        else:
            conv.append({"role": m["role"], "content": m["content"]})
    while conv and conv[0]["role"] != "user":
        conv.pop(0)
    body = {"model": conf["modele"], "max_tokens": max_tokens, "messages": conv or
            [{"role": "user", "content": "Bonjour"}]}
    if system:
        body["system"] = system
    if stream:
        body["stream"] = True
    return body


def _openai_content(m):
    if not m.get("images"):
        return m["content"]
    return [{"type": "text", "text": m["content"]}] + [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}} for b in m["images"]]


def _openai_body(conf, messages, stream):
    body = {"model": conf["modele"],
            "messages": [{"role": m["role"], "content": _openai_content(m)} for m in messages]}
    if stream:
        body["stream"] = True
    return body


def _endpoint(conf):
    return conf["url"] + ("/messages" if conf["type"] == "anthropic" else "/chat/completions")


def explain_error(e):
    """Message clair en français pour une erreur d'API."""
    if isinstance(e, urllib.error.HTTPError):
        detail = ""
        try:
            data = json.loads(e.read().decode("utf-8", "ignore"))
            err = data.get("error", data)
            detail = err.get("message", "") if isinstance(err, dict) else str(err)
        except Exception:
            pass
        code = e.code
        if code in (401, 403):
            msg = "clé refusée (vérifie qu'elle est bien copiée en entier)"
        elif code == 402 or (code == 429 and "quota" in detail.lower()):
            msg = "plus de crédit sur ce compte (il faut recharger ou passer à une offre payante)"
        elif code == 429:
            msg = ("trop de demandes d'un coup, réessaie dans un instant (les offres gratuites limitent "
                   "le nombre de messages)")
        elif code == 404:
            msg = "modèle introuvable (choisis-en un avec « Lister les modèles »)"
        elif code == 400:
            msg = "demande refusée"
        else:
            msg = f"erreur {code} du serveur"
        return msg + (f" — {detail[:200]}" if detail else "")
    if isinstance(e, urllib.error.URLError):
        return "pas de connexion au serveur (internet coupé ou adresse fausse)"
    return str(e)[:200]


def request(conf, messages, timeout=120, max_tokens=2048):
    """Réponse complète (texte)."""
    if conf["type"] == "anthropic":
        body = _anthropic_body(conf, messages, max_tokens, False)
    else:
        body = _openai_body(conf, messages, False)
    req = urllib.request.Request(_endpoint(conf), data=json.dumps(body).encode(), headers=_headers(conf))
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
        data = json.load(r)
    if conf["type"] == "anthropic":
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()


def stream(conf, messages, timeout=180, max_tokens=1024):
    """Réponse au fil de l'eau : génère (morceau, fini)."""
    if conf.get("anonyme"):                     # service sans clé : réponse d'un bloc, plus fiable
        yield request(conf, messages, timeout=timeout), False
        yield "", True
        return
    if conf["type"] == "anthropic":
        body = _anthropic_body(conf, messages, max_tokens, True)
    else:
        body = _openai_body(conf, messages, True)
    req = urllib.request.Request(_endpoint(conf), data=json.dumps(body).encode(), headers=_headers(conf))
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
        for raw in r:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            if conf["type"] == "anthropic":
                t = obj.get("type")
                if t == "content_block_delta":
                    yield (obj.get("delta") or {}).get("text", ""), False
                elif t == "message_stop":
                    break
                elif t == "error":
                    raise RuntimeError((obj.get("error") or {}).get("message", "erreur"))
            else:
                ch = (obj.get("choices") or [{}])[0]
                piece = (ch.get("delta") or {}).get("content") or ""
                if piece:
                    yield piece, False
                if ch.get("finish_reason"):
                    break
    yield "", True


def list_models(conf, timeout=20):
    req = urllib.request.Request(conf["url"] + "/models", headers=_headers(conf))
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
        data = json.load(r)
    ids = [m.get("id", "") for m in data.get("data", data.get("models", [])) if isinstance(m, dict)]
    ids = [i.replace("models/", "") for i in ids if i]
    bad = ("embed", "whisper", "tts", "dall-e", "image", "audio", "moderation", "transcribe",
           "realtime", "search", "rerank", "veo", "imagen", "lyria")
    ids = sorted({i for i in ids if not any(b in i.lower() for b in bad)})
    if conf["id"] == "openrouter":               # les gratuits d'abord
        ids.sort(key=lambda i: (not i.endswith(":free"), i))
    return ids


def test(conf):
    """(True, réponse) ou (False, explication)."""
    try:
        txt = request(conf, [{"role": "user", "content": "Dis juste « ok »."}], timeout=40, max_tokens=20)
        return True, txt or "ok"
    except Exception as e:
        return False, explain_error(e)


def extract_json(text):
    """Le JSON d'une réponse (les IA en ligne l'entourent parfois de ```json …```)."""
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(text[a:b + 1])
        except ValueError:
            pass
    return {}
