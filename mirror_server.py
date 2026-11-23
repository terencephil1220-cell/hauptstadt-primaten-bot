#!/usr/bin/env python3
"""
Spiegelt den AUFBAU eines Discord-Servers (Quelle) auf einen Test-Server (Ziel).

Kopiert:  Rollen (Name, Farbe, Rechte, Anzeige), Kategorien, Kanaele, Forum-Tags,
          Beschreibungen, Reihenfolge und Rollen-Rechte pro Kanal.
Kopiert NICHT: Nachrichten, Mitglieder, Bots/Integrationsrollen, Webhooks.

Sicherheitsregeln:
  - Die Quelle wird nur gelesen, nie veraendert.
  - Auf dem Ziel wird nie etwas geloescht; vorhandenes (gleicher Name) wird aktualisiert.
  - Quelle und Ziel muessen eindeutig gefunden werden und verschieden sein, sonst Abbruch.

Konfiguration: mirror.json   |   Token: DISCORD_BOT_TOKEN
Bot braucht auf dem ZIEL-Server Administrator, auf der QUELLE nur "Kanaele ansehen".
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

API = "https://discord.com/api/v10"
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
if not TOKEN:
    sys.exit("Fehler: Secret DISCORD_BOT_TOKEN ist nicht gesetzt.")
S = requests.Session()
S.headers.update({"Authorization": f"Bot {TOKEN}", "User-Agent": "DiscordBot (hauptstadt-primaten-bot, 1.3)"})

CATEGORY, TEXT, VOICE, ANNOUNCE, STAGE, FORUM, MEDIA = 4, 0, 2, 5, 13, 15, 16
COMMUNITY_ONLY = {ANNOUNCE: TEXT, STAGE: VOICE, MEDIA: FORUM}
CH_FIELDS = ["topic", "nsfw", "rate_limit_per_user", "bitrate", "user_limit",
             "default_auto_archive_duration", "default_sort_order", "default_forum_layout",
             "default_thread_rate_limit_per_user", "flags"]
warnings = []


PROTECTED_IDS = set()  # Server + deren Kanaele/Rollen: nur Lesezugriff erlaubt


def dc(method, path, **kw):
    if method != "GET" and any(pid in path for pid in PROTECTED_IDS):
        sys.exit(f"SPERRE: Schreibzugriff auf geschuetzten Server verweigert ({method} {path}). Nichts geaendert.")
    for _ in range(5):
        r = S.request(method, API + path, timeout=30, **kw)
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 1)) + 0.3)
            continue
        return r
    return r


def ok(r, what):
    if r.status_code in (200, 201, 204):
        return r.json() if r.content else {}
    warnings.append(f"{what}: {r.status_code} {r.text[:200]}")
    print(f"  ! {what}: {r.status_code} {r.text[:200]}")
    return None


def find_guild(guilds, wanted, label):
    if str(wanted).isdigit():
        hits = [g for g in guilds if g["id"] == str(wanted)]
    else:
        exact = [g for g in guilds if g["name"].lower() == wanted.lower()]
        hits = exact or [g for g in guilds if wanted.lower() in g["name"].lower()]
    if len(hits) != 1:
        names = "\n".join(f"   - {g['name']} ({g['id']})" for g in guilds)
        sys.exit(f"{label} '{wanted}' nicht eindeutig gefunden ({len(hits)} Treffer).\n"
                 f"Server, auf denen der Bot ist:\n{names}\n-> In mirror.json den genauen Namen oder die ID eintragen.")
    return hits[0]


def main():
    cfg = json.loads(Path(__file__).with_name("mirror.json").read_text(encoding="utf-8"))
    guilds = dc("GET", "/users/@me/guilds").json()
    src = find_guild(guilds, cfg["source"], "Quelle")
    dst = find_guild(guilds, cfg["target"], "Ziel")
    if src["id"] == dst["id"]:
        sys.exit("Abbruch: Quelle und Ziel sind derselbe Server.")
    for p in cfg.get("protected", []) + [cfg["source"]]:
        g = find_guild(guilds, p, "Geschuetzt")
        if g["id"] == dst["id"]:
            sys.exit(f"Abbruch: Ziel '{dst['name']}' ist als geschuetzt markiert.")
        PROTECTED_IDS.add(g["id"])
        for c in dc("GET", f"/guilds/{g['id']}/channels").json():
            PROTECTED_IDS.add(c["id"])
        for r in dc("GET", f"/guilds/{g['id']}/roles").json():
            PROTECTED_IDS.add(r["id"])
    print(f"Schreibschutz aktiv fuer: {', '.join(cfg.get('protected', []))}")
    print(f"Quelle: {src['name']} ({src['id']})  ->  Ziel: {dst['name']} ({dst['id']})\n")

    # ---------- Rollen ----------
    print("Rollen:")
    s_roles = sorted(dc("GET", f"/guilds/{src['id']}/roles").json(), key=lambda r: r["position"])
    d_roles = dc("GET", f"/guilds/{dst['id']}/roles").json()
    d_by_name = {r["name"].lower(): r for r in d_roles if not r.get("managed")}
    role_map = {src["id"]: dst["id"]}  # @everyone
    for r in s_roles:
        if r.get("managed"):
            continue  # Bot-/Integrationsrollen
        body = {"name": r["name"], "permissions": r["permissions"], "color": r["color"],
                "hoist": r["hoist"], "mentionable": r["mentionable"]}
        if r["id"] == src["id"]:
            body = {"permissions": r["permissions"]}
            res = ok(dc("PATCH", f"/guilds/{dst['id']}/roles/{dst['id']}", json=body), "@everyone")
            print("  = @everyone Rechte übernommen" if res is not None else "")
            continue
        existing = d_by_name.get(r["name"].lower())
        if existing:
            res = ok(dc("PATCH", f"/guilds/{dst['id']}/roles/{existing['id']}", json=body), f"Rolle {r['name']}")
            if res:
                role_map[r["id"]] = existing["id"]
                print(f"  = {r['name']}")
        else:
            res = ok(dc("POST", f"/guilds/{dst['id']}/roles", json=body), f"Rolle {r['name']}")
            if res:
                role_map[r["id"]] = res["id"]
                print(f"  + {r['name']}")
    # Reihenfolge wie in der Quelle (best effort)
    order = [{"id": role_map[r["id"]], "position": i}
             for i, r in enumerate(s_roles) if r["id"] in role_map and r["id"] != src["id"]]
    if order:
        ok(dc("PATCH", f"/guilds/{dst['id']}/roles", json=order), "Rollen-Reihenfolge")

    def overwrites(ch):
        out = []
        for o in ch.get("permission_overwrites", []):
            if o["type"] == 0 and o["id"] in role_map:  # nur Rollen, keine Einzelpersonen
                out.append({"id": role_map[o["id"]], "type": 0, "allow": o["allow"], "deny": o["deny"]})
        return out

    # ---------- Kanaele ----------
    s_ch = sorted(dc("GET", f"/guilds/{src['id']}/channels").json(), key=lambda c: (c["type"] != CATEGORY, c["position"]))
    d_ch = dc("GET", f"/guilds/{dst['id']}/channels").json()
    ch_map = {}

    def find_dst(name, ctype, parent):
        for c in d_ch:
            if c["name"].lower() == name.lower() and c["type"] == ctype and c.get("parent_id") == parent:
                return c
        return None

    print("\nKanäle:")
    for c in s_ch:
        if c["type"] not in (CATEGORY, TEXT, VOICE, ANNOUNCE, STAGE, FORUM, MEDIA):
            continue
        parent = ch_map.get(c.get("parent_id"))
        body = {"name": c["name"], "position": c["position"], "permission_overwrites": overwrites(c)}
        if c["type"] != CATEGORY:
            body["parent_id"] = parent
        for f in CH_FIELDS:
            if c.get(f) is not None:
                body[f] = c[f]
        if c["type"] in (FORUM, MEDIA):
            body["available_tags"] = [
                {"name": t["name"], "moderated": t.get("moderated", False),
                 **({"emoji_name": t["emoji_name"]} if t.get("emoji_name") else {})}
                for t in c.get("available_tags", [])
            ]
            if c.get("default_reaction_emoji") and c["default_reaction_emoji"].get("emoji_name"):
                body["default_reaction_emoji"] = {"emoji_name": c["default_reaction_emoji"]["emoji_name"]}

        ctype = c["type"]
        existing = find_dst(c["name"], ctype, parent) or (
            find_dst(c["name"], COMMUNITY_ONLY[ctype], parent) if ctype in COMMUNITY_ONLY else None)
        label = ("📁 " if ctype == CATEGORY else "   #") + c["name"]
        if existing:
            old = {t["name"]: t["id"] for t in existing.get("available_tags", [])}
            for t in body.get("available_tags", []):
                if t["name"] in old:
                    t["id"] = old[t["name"]]
            res = ok(dc("PATCH", f"/channels/{existing['id']}", json=body), label.strip())
            if res:
                ch_map[c["id"]] = existing["id"]
                print(f"  = {label}")
            continue
        res = dc("POST", f"/guilds/{dst['id']}/channels", json={**body, "type": ctype})
        if res.status_code == 400 and ctype in COMMUNITY_ONLY:
            # Ankuendigungs-/Stage-/Medien-Kanaele gehen nur auf Community-Servern
            fallback = COMMUNITY_ONLY[ctype]
            res = dc("POST", f"/guilds/{dst['id']}/channels", json={**body, "type": fallback})
            if res.status_code in (200, 201):
                warnings.append(f"#{c['name']}: als normaler Kanal angelegt (Ziel ist kein Community-Server)")
        made = ok(res, label.strip())
        if made:
            ch_map[c["id"]] = made["id"]
            d_ch.append(made)
            print(f"  + {label}")

    print(f"\nFertig: {len(role_map) - 1} Rollen, {len(ch_map)} Kanäle/Kategorien abgeglichen.")
    if warnings:
        print(f"\n{len(warnings)} Hinweis(e):")
        for w in warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
