#!/usr/bin/env python3
"""
Discord-Server-Setup fuer "Hauptstadt Primaten".

Liest server.json und sorgt dafuer, dass alle dort beschriebenen
Kategorien und Kanaele existieren. Bestehende Kanaele (gleicher Name +
Typ) werden aktualisiert, nichts wird geloescht.

Benoetigt: Umgebungsvariable DISCORD_BOT_TOKEN, Bot mit "Kanaele verwalten".
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://discord.com/api/v10"
REQUIRE_TAG = 1 << 4
TYPES = {"text": 0, "category": 4, "forum": 15}


def api(method, path, body=None):
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        sys.exit("Fehler: Secret DISCORD_BOT_TOKEN ist nicht gesetzt.")
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (hauptstadt-primaten-bot, 1.1)",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        hints = {
            401: "Token ungueltig - im Developer Portal neu erzeugen und Secret aktualisieren.",
            403: "Bot fehlt die Berechtigung 'Kanaele verwalten' oder ist nicht auf dem Server.",
            404: "Server nicht gefunden - stimmt guild_id in server.json?",
        }
        sys.exit(f"Discord-Fehler {e.code}: {detail}\nHinweis: {hints.get(e.code, '-')}")


def main():
    cfg = json.loads(Path(__file__).with_name("server.json").read_text(encoding="utf-8"))
    gid = cfg["guild_id"]
    existing = api("GET", f"/guilds/{gid}/channels")

    def find(name, ctype, parent=None):
        for c in existing:
            if c["name"].lower() == name.lower() and c["type"] == ctype:
                if parent is None or c.get("parent_id") == parent:
                    return c
        return None

    for cat_cfg in cfg["categories"]:
        cat = find(cat_cfg["name"], TYPES["category"])
        if cat:
            print(f"Kategorie '{cat_cfg['name']}' vorhanden.")
        else:
            cat = api("POST", f"/guilds/{gid}/channels", {"name": cat_cfg["name"], "type": TYPES["category"]})
            existing.append(cat)
            print(f"Kategorie '{cat_cfg['name']}' angelegt.")

        for ch in cat_cfg.get("channels", []):
            ctype = TYPES[ch.get("type", "text")]
            payload = {"name": ch["name"], "parent_id": cat["id"], "topic": ch.get("topic", "")}
            if ctype == TYPES["forum"]:
                payload["flags"] = REQUIRE_TAG if ch.get("require_tag") else 0
                found = find(ch["name"], ctype)
                old_tags = {t["name"]: t for t in (found or {}).get("available_tags", [])}
                tags = []
                for name, emoji in ch.get("tags", []):
                    tag = {"name": name, "emoji_name": emoji, "moderated": False}
                    if name in old_tags:  # ID behalten, damit bestehende Posts ihren Tag behalten
                        tag["id"] = old_tags[name]["id"]
                    tags.append(tag)
                payload["available_tags"] = tags
            else:
                found = find(ch["name"], ctype)

            if found:
                api("PATCH", f"/channels/{found['id']}", payload)
                print(f"  #{ch['name']} aktualisiert.")
            else:
                payload["type"] = ctype
                new = api("POST", f"/guilds/{gid}/channels", payload)
                existing.append(new)
                print(f"  #{ch['name']} angelegt.")

    print("\nFertig!")


if __name__ == "__main__":
    main()
