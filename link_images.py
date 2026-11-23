#!/usr/bin/env python3
"""
Link-Bilder-Bot fuer "Hauptstadt Primaten".

Laeuft regelmaessig per GitHub Actions und:
  1. sucht neue Posts in den Foren aus IMAGE_FORUMS (server.json -> "image_forums")
  2. findet darin Links zu Archidekt, Moxfield oder Scryfall
  3. laedt das Vorschaubild der Seite und postet es als echten Anhang in den Post
  4. blendet danach die aufgeklappte Link-Vorschau des Original-Posts aus

Bereits bearbeitete Posts erkennt der Bot an seiner eigenen Bild-Antwort.
Benoetigt: DISCORD_BOT_TOKEN; Bot-Rechte: Kanaele ansehen, Nachrichtenverlauf lesen,
Nachrichten in Threads senden, Dateien anhaengen, Nachrichten verwalten.
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

API = "https://discord.com/api/v10"
MAX_AGE = timedelta(days=3)          # nur Posts der letzten 3 Tage pruefen
SUPPRESS_EMBEDS = 1 << 2
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
LINK_RE = re.compile(
    r"https?://(?:www\.)?(archidekt\.com/decks/\d+[^\s>)]*|moxfield\.com/decks/[\w-]+[^\s>)]*"
    r"|scryfall\.com/card/[\w-]+/[\w★-]+[^\s>)]*)",
    re.IGNORECASE,
)

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
if not TOKEN:
    sys.exit("Fehler: Secret DISCORD_BOT_TOKEN ist nicht gesetzt.")
DISCORD = requests.Session()
DISCORD.headers.update({"Authorization": f"Bot {TOKEN}",
                        "User-Agent": "DiscordBot (hauptstadt-primaten-bot, 1.2)"})
WEB = requests.Session()
WEB.headers.update({"User-Agent": BROWSER_UA, "Accept-Language": "de,en;q=0.8"})


def dc(method, path, **kw):
    """Discord-API-Aufruf mit einfacher Rate-Limit-Behandlung."""
    for _ in range(3):
        r = DISCORD.request(method, API + path, timeout=30, **kw)
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 1)) + 0.5)
            continue
        return r
    return r


def snowflake_time(sid):
    return datetime.fromtimestamp(((int(sid) >> 22) + 1420070400000) / 1000, tz=timezone.utc)


# ---------- Bildquellen ----------

def og_image(url):
    """Liest og:image / twitter:image aus der Seite."""
    r = WEB.get(url, timeout=20)
    r.raise_for_status()
    for prop in ("og:image", "twitter:image", "og:image:url"):
        m = re.search(
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)', r.text, re.I
        ) or re.search(
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']', r.text, re.I
        )
        if m:
            return html.unescape(m.group(1))
    return None


def scryfall_image(url):
    parts = urlparse(url).path.strip("/").split("/")  # card/<set>/<nummer>/<name>
    if len(parts) < 3:
        return None
    r = requests.get(
        f"https://api.scryfall.com/cards/{parts[1]}/{parts[2]}",
        headers={"User-Agent": "HauptstadtPrimatenBot/1.2", "Accept": "application/json"},
        timeout=20,
    )
    r.raise_for_status()
    card = r.json()
    uris = card.get("image_uris") or (card.get("card_faces") or [{}])[0].get("image_uris") or {}
    return uris.get("large") or uris.get("normal")


def archidekt_image(url):
    m = re.search(r"/decks/(\d+)", url)
    if m:
        try:
            r = WEB.get(f"https://archidekt.com/api/decks/{m.group(1)}/", timeout=20)
            if r.ok:
                feat = r.json().get("featured")
                if feat:
                    return feat
        except (requests.RequestException, ValueError):
            pass
    return og_image(url)


def image_for(url):
    host = urlparse(url).netloc.lower()
    if "scryfall.com" in host:
        return scryfall_image(url)
    if "archidekt.com" in host:
        return archidekt_image(url)
    return og_image(url)  # Moxfield


def download(img_url):
    r = WEB.get(img_url, timeout=30)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    if not ctype.startswith("image/"):
        raise ValueError(f"kein Bild ({ctype})")
    ext = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(ctype, "jpg")
    return r.content, ctype, ext


# ---------- Ablauf ----------

def main():
    cfg = json.loads(Path(__file__).with_name("server.json").read_text(encoding="utf-8"))
    gid = cfg["guild_id"]
    wanted = {n.lower() for n in cfg.get("image_forums", [])}

    me = dc("GET", "/users/@me").json()["id"]
    channels = dc("GET", f"/guilds/{gid}/channels")
    if channels.status_code != 200:
        sys.exit(f"Discord-Fehler {channels.status_code}: {channels.text}")
    forum_ids = {c["id"]: c["name"] for c in channels.json() if c["type"] == 15 and c["name"].lower() in wanted}
    if not forum_ids:
        sys.exit(f"Keine passenden Foren gefunden ({', '.join(wanted)}).")

    threads = dc("GET", f"/guilds/{gid}/threads/active").json().get("threads", [])
    cutoff = datetime.now(timezone.utc) - MAX_AGE
    done = 0
    for t in threads:
        if t.get("parent_id") not in forum_ids or snowflake_time(t["id"]) < cutoff:
            continue
        msgs = dc("GET", f"/channels/{t['id']}/messages", params={"limit": 50})
        if msgs.status_code != 200:
            print(f"  ! {t['name']}: Nachrichten nicht lesbar ({msgs.status_code})")
            continue
        msgs = msgs.json()
        if any(m["author"]["id"] == me and m.get("attachments") for m in msgs):
            continue  # schon bearbeitet
        starter = next((m for m in msgs if m["id"] == t["id"]), None)
        if not starter:
            continue
        links = [m.group(0) for m in LINK_RE.finditer(starter.get("content", ""))]
        if not links:
            continue

        files, sources = [], []
        for i, link in enumerate(dict.fromkeys(links)):
            if len(files) >= 4:
                break
            try:
                img = image_for(link)
                if not img:
                    print(f"  ! {link}: kein Vorschaubild gefunden")
                    continue
                data, ctype, ext = download(img)
                files.append((f"files[{len(files)}]", (f"vorschau_{i + 1}.{ext}", data, ctype)))
                sources.append(urlparse(link).netloc.replace("www.", ""))
            except Exception as e:  # eine kaputte Seite soll den Lauf nicht stoppen
                print(f"  ! {link}: {e}")
        if not files:
            continue

        payload = {"content": f"🖼️ Vorschau von {', '.join(dict.fromkeys(sources))}",
                   "message_reference": {"message_id": starter["id"], "fail_if_not_exists": False},
                   "allowed_mentions": {"parse": []}}
        r = dc("POST", f"/channels/{t['id']}/messages",
               data={"payload_json": json.dumps(payload)}, files=files)
        if r.status_code not in (200, 201):
            print(f"  ! {t['name']}: Upload fehlgeschlagen ({r.status_code}) {r.text}")
            continue
        done += 1
        print(f"  ✓ {forum_ids[t['parent_id']]} / {t['name']}: {len(files)} Bild(er)")

        # aufgeklappte Link-Vorschau im Original-Post ausblenden
        s = dc("PATCH", f"/channels/{t['id']}/messages/{starter['id']}",
               json={"flags": (starter.get("flags") or 0) | SUPPRESS_EMBEDS})
        if s.status_code != 200:
            print(f"    (Vorschau nicht ausgeblendet: {s.status_code} - Bot braucht 'Nachrichten verwalten')")

    print(f"\nFertig: {done} Post(s) mit Bild versehen.")


if __name__ == "__main__":
    main()
