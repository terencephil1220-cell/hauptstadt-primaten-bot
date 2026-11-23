#!/usr/bin/env python3
"""
Cardtalks-Setup fuer den Discord-Server "Hauptstadt Primaten".

Legt an:
  - Kategorie "Cardtalks"
  - Forum "decks"  (Pflicht-Tag: Bracket 1-5, farbig per Emoji)
  - Forum "karten" (Pflicht-Tag: Game Changer, OP, Combo Piece, Infinity Piece)

Voraussetzung: Der Bot ist auf dem Server und hat die Berechtigung
"Kanaele verwalten" (Manage Channels).

Start (Token NICHT ins Skript schreiben, nur als Umgebungsvariable):
  Windows (PowerShell):  $env:DISCORD_BOT_TOKEN="DEIN_TOKEN"; python cardtalks_setup.py
  macOS/Linux:           DISCORD_BOT_TOKEN="DEIN_TOKEN" python3 cardtalks_setup.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

GUILD_ID = "1209501038739193887"
API = "https://discord.com/api/v10"
REQUIRE_TAG = 1 << 4  # Forum-Flag: Beim Posten muss ein Tag gewaehlt werden

DECK_TAGS = [
    ("Bracket 1", "🟢"),
    ("Bracket 2", "🔵"),
    ("Bracket 3", "🟡"),
    ("Bracket 4", "🟠"),
    ("Bracket 5", "🔴"),
]
KARTEN_TAGS = [
    ("Game Changer", "⭐"),
    ("OP", "💥"),
    ("Combo Piece", "🧩"),
    ("Infinity Piece", "♾️"),
]


def api(method, path, body=None):
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        sys.exit("Fehler: Umgebungsvariable DISCORD_BOT_TOKEN ist nicht gesetzt.")
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (cardtalks-setup, 1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        hints = {
            401: "Token ungueltig - im Developer Portal neu erzeugen.",
            403: "Bot fehlt die Berechtigung 'Kanaele verwalten' oder ist nicht auf dem Server.",
            404: "Server nicht gefunden - stimmt die Server-ID?",
        }
        sys.exit(f"Discord-Fehler {e.code}: {detail}\nHinweis: {hints.get(e.code, '-')}")


def tags(pairs):
    return [{"name": n, "emoji_name": e, "moderated": False} for n, e in pairs]


def main():
    existing = api("GET", f"/guilds/{GUILD_ID}/channels")
    by_name = {(c["name"].lower(), c["type"]): c for c in existing}

    cat = by_name.get(("cardtalks", 4))
    if cat:
        print(f"Kategorie 'Cardtalks' existiert schon ({cat['id']}) - wird verwendet.")
    else:
        cat = api("POST", f"/guilds/{GUILD_ID}/channels", {"name": "Cardtalks", "type": 4})
        print(f"Kategorie 'Cardtalks' angelegt ({cat['id']}).")

    forums = [
        ("decks", "Stell dein Deck vor und diskutiere es. Bitte beim Posten ein Bracket (1-5) waehlen.", DECK_TAGS),
        ("karten", "Sprecht ueber einzelne Karten. Bitte beim Posten eine Eigenschaft waehlen.", KARTEN_TAGS),
    ]
    for name, topic, tag_pairs in forums:
        payload = {
            "name": name,
            "type": 15,  # Forum-Kanal
            "parent_id": cat["id"],
            "topic": topic,
            "available_tags": tags(tag_pairs),
            "flags": REQUIRE_TAG,
        }
        found = by_name.get((name, 15))
        if found:
            payload.pop("type")
            api("PATCH", f"/channels/{found['id']}", payload)
            print(f"Forum '{name}' existierte schon - Tags/Einstellungen aktualisiert.")
        else:
            ch = api("POST", f"/guilds/{GUILD_ID}/channels", payload)
            print(f"Forum '{name}' angelegt ({ch['id']}).")

    print("\nFertig! Schau in Discord unter 'Cardtalks' nach.")


if __name__ == "__main__":
    main()
