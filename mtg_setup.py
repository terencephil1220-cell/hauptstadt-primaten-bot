#!/usr/bin/env python3
"""
Aufbau fuer "Magic Talks and Games" (Hauptsitz) aus mtg.json.

- Rollen: Team, Level-Stufen, Eigenschafts-Rollen (Format x Haeufigkeit)
- Kategorien, Text-, Forum- und Sprachkanaele inkl. Tags und Rechten
- Platzhalter-Regeln in #regeln
- Community-Kanaele (Regeln/Updates) und Onboarding-Pflichtfragen

Legt an oder aktualisiert, loescht nie. Benoetigt DISCORD_BOT_TOKEN, Bot mit Administrator.
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://discord.com/api/v10"
TYPES = {"text": 0, "voice": 2, "category": 4, "forum": 15}
REQUIRE_TAG = 1 << 4
PERMS = {
    "ADMINISTRATOR": 1 << 3, "KICK_MEMBERS": 1 << 1, "VIEW_CHANNEL": 1 << 10,
    "SEND_MESSAGES": 1 << 11, "MANAGE_MESSAGES": 1 << 13, "MUTE_MEMBERS": 1 << 22,
    "MOVE_MEMBERS": 1 << 24, "MANAGE_THREADS": 1 << 34, "CREATE_PUBLIC_THREADS": 1 << 35,
    "SEND_MESSAGES_IN_THREADS": 1 << 38, "MODERATE_MEMBERS": 1 << 40,
}
READONLY_DENY = PERMS["SEND_MESSAGES"] | PERMS["CREATE_PUBLIC_THREADS"] | PERMS["SEND_MESSAGES_IN_THREADS"]
WARNINGS = []


class DiscordError(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code = code


def api(method, path, body=None, retry=True):
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        sys.exit("Fehler: Secret DISCORD_BOT_TOKEN ist nicht gesetzt.")
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                 "User-Agent": "DiscordBot (hauptstadt-primaten-bot, 2.0)"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if e.code == 429 and retry:
            wait = json.loads(detail).get("retry_after", 2)
            time.sleep(float(wait) + 0.5)
            return api(method, path, body, retry=False)
        raise DiscordError(e.code, detail)


def snowflake():
    return str(((int(time.time() * 1000) - 1420070400000) << 22) | random.getrandbits(22))


def color(hexstr):
    return int(hexstr.lstrip("#"), 16) if hexstr else 0


def warn(msg):
    print(f"  ⚠️  {msg}")
    WARNINGS.append(msg)


def main():
    cfg = json.loads(Path(__file__).with_name("mtg.json").read_text(encoding="utf-8"))
    gid = cfg["guild_id"]
    try:
        guild = api("GET", f"/guilds/{gid}")
    except DiscordError as e:
        sys.exit(f"Server {gid} nicht erreichbar ({e}). Ist der Bot eingeladen?")
    print(f"=== {guild['name']} ({gid}) ===")
    community = "COMMUNITY" in guild.get("features", [])
    print(f"Community aktiv: {'ja' if community else 'NEIN'}")

    roles = sync_roles(cfg, gid)
    channels = sync_channels(cfg, gid, roles)
    post_rules(cfg, channels)
    if community:
        set_community_channels(cfg, gid, channels)
        sync_onboarding(cfg, gid, roles, channels)
    else:
        warn("Community ist nicht aktiv - Onboarding/Regelkanal uebersprungen. Community einschalten und Workflow neu starten.")

    print("\nFertig!" if not WARNINGS else f"\nFertig mit {len(WARNINGS)} Hinweis(en):")
    for w in WARNINGS:
        print(f" - {w}")


# ---------------- Rollen ----------------
def sync_roles(cfg, gid):
    print("\n-- Rollen --")
    existing = {r["name"].lower(): r for r in api("GET", f"/guilds/{gid}/roles")}
    wanted = []
    for r in cfg["staff_roles"]:
        perms = sum(PERMS[p] for p in r["perms"])
        wanted.append({"name": r["name"], "permissions": str(perms), "color": color(r.get("color")),
                       "hoist": r.get("hoist", False), "mentionable": True})
    for r in cfg["level_roles"]:
        wanted.append({"name": r["name"], "permissions": "0", "color": color(r.get("color")),
                       "hoist": True, "mentionable": False})
    for fmt in cfg["formats"]:
        for freq, _ in cfg["frequencies"]:
            wanted.append({"name": f"{fmt} · {freq}", "permissions": "0", "color": 0,
                           "hoist": False, "mentionable": True})

    result = {}
    for w in wanted:
        found = existing.get(w["name"].lower())
        try:
            if found:
                result[w["name"]] = api("PATCH", f"/guilds/{gid}/roles/{found['id']}", w)
                print(f"  Rolle '{w['name']}' aktualisiert.")
            else:
                result[w["name"]] = api("POST", f"/guilds/{gid}/roles", w)
                print(f"  Rolle '{w['name']}' angelegt.")
        except DiscordError as e:
            if found:
                result[w["name"]] = found
            warn(f"Rolle '{w['name']}': {e}")
    return result


# ---------------- Kanaele ----------------
def sync_channels(cfg, gid, roles):
    print("\n-- Kanaele --")
    existing = api("GET", f"/guilds/{gid}/channels")
    staff_ids = [roles[r["name"]]["id"] for r in cfg["staff_roles"] if r["name"] in roles]

    def find(name, ctype, parent=None):
        for c in existing:
            if c["name"].lower() == name.lower() and c["type"] == ctype:
                if parent is None or c.get("parent_id") == parent:
                    return c
        return None

    def overwrites(private=False, readonly=False):
        ow = []
        if private:
            ow.append({"id": gid, "type": 0, "allow": "0", "deny": str(PERMS["VIEW_CHANNEL"])})
            ow += [{"id": rid, "type": 0, "allow": str(PERMS["VIEW_CHANNEL"] | PERMS["SEND_MESSAGES"]), "deny": "0"} for rid in staff_ids]
        elif readonly:
            ow.append({"id": gid, "type": 0, "allow": "0", "deny": str(READONLY_DENY)})
            ow += [{"id": rid, "type": 0, "allow": str(PERMS["SEND_MESSAGES"]), "deny": "0"} for rid in staff_ids]
        return ow

    by_name = {}
    for cat_cfg in cfg["categories"]:
        private = cat_cfg.get("private", False)
        cat = find(cat_cfg["name"], TYPES["category"])
        payload = {"name": cat_cfg["name"], "permission_overwrites": overwrites(private=private)}
        try:
            if cat:
                cat = api("PATCH", f"/channels/{cat['id']}", payload)
                print(f"Kategorie '{cat_cfg['name']}' vorhanden.")
            else:
                cat = api("POST", f"/guilds/{gid}/channels", {**payload, "type": TYPES["category"]})
                existing.append(cat)
                print(f"Kategorie '{cat_cfg['name']}' angelegt.")
        except DiscordError as e:
            warn(f"Kategorie '{cat_cfg['name']}': {e}")
            continue

        for ch in cat_cfg.get("channels", []):
            ctype = TYPES[ch.get("type", "text")]
            payload = {"name": ch["name"], "parent_id": cat["id"],
                       "permission_overwrites": overwrites(private=private, readonly=ch.get("readonly", False))}
            if ctype != TYPES["voice"]:
                payload["topic"] = ch.get("topic", "")
            found = find(ch["name"], ctype)
            if ctype == TYPES["forum"]:
                payload["flags"] = REQUIRE_TAG if ch.get("require_tag") else 0
                old = {t["name"]: t for t in (found or {}).get("available_tags", [])}
                payload["available_tags"] = [
                    {"name": n, "emoji_name": e, "moderated": False, **({"id": old[n]["id"]} if n in old else {})}
                    for n, e in ch.get("tags", [])]
            try:
                if found:
                    obj = api("PATCH", f"/channels/{found['id']}", payload)
                    print(f"  #{ch['name']} aktualisiert.")
                else:
                    obj = api("POST", f"/guilds/{gid}/channels", {**payload, "type": ctype})
                    existing.append(obj)
                    print(f"  #{ch['name']} angelegt.")
                by_name[ch["name"].lower()] = obj
            except DiscordError as e:
                warn(f"Kanal #{ch['name']}: {e}")
    return by_name


def post_rules(cfg, channels):
    ch = channels.get("regeln")
    if not ch:
        return
    me = api("GET", "/users/@me")
    msgs = api("GET", f"/channels/{ch['id']}/messages?limit=20")
    mine = [m for m in msgs if m["author"]["id"] == me["id"]]
    try:
        if mine:
            api("PATCH", f"/channels/{ch['id']}/messages/{mine[-1]['id']}", {"content": cfg["rules_text"]})
            print("\nRegeln in #regeln aktualisiert.")
        else:
            api("POST", f"/channels/{ch['id']}/messages", {"content": cfg["rules_text"]})
            print("\nPlatzhalter-Regeln in #regeln gepostet.")
    except DiscordError as e:
        warn(f"Regel-Nachricht: {e}")


def set_community_channels(cfg, gid, channels):
    cc = cfg["community_channels"]
    body = {}
    if cc["rules"] in channels:
        body["rules_channel_id"] = channels[cc["rules"]]["id"]
    if cc["updates"] in channels:
        body["public_updates_channel_id"] = channels[cc["updates"]]["id"]
    try:
        api("PATCH", f"/guilds/{gid}", body)
        print("Regel- und Update-Kanal fuer Community gesetzt.")
    except DiscordError as e:
        warn(f"Community-Kanaele: {e}")


# ---------------- Onboarding ----------------
def sync_onboarding(cfg, gid, roles, channels):
    print("\n-- Onboarding --")
    try:
        current = api("GET", f"/guilds/{gid}/onboarding")
    except DiscordError:
        current = {"prompts": []}
    old_prompts = {p["title"]: p for p in current.get("prompts", [])}
    fallback = channels.get("allgemein", {}).get("id")

    # Eine Frage pro Haeufigkeit (oft/normal/weniger), Mehrfachauswahl ueber alle Formate.
    # Discord erlaubt nur wenige Fragen, so bleiben alle Format x Haeufigkeit-Rollen erhalten.
    def build():
        prompts = []
        for freq, emoji in cfg["frequencies"]:
            title = f"Was spielst du {freq.upper()}? {emoji}"
            old = old_prompts.get(title, {})
            old_opts = {o["title"]: o for o in old.get("options", [])}
            opts = []
            for fmt in cfg["formats"]:
                role = roles.get(f"{fmt} · {freq}")
                opts.append({"id": old_opts.get(fmt, {}).get("id", snowflake()), "title": fmt,
                             "role_ids": [role["id"]] if role else [], "channel_ids": []})
            t = "Nichts davon"
            opts.append({"id": old_opts.get(t, {}).get("id", snowflake()), "title": t, "emoji_name": "➖",
                         "role_ids": [], "channel_ids": [fallback] if fallback else []})
            prompts.append({"id": old.get("id", snowflake()), "type": 0, "title": title, "options": opts,
                            "single_select": False, "required": True, "in_onboarding": True})
        return prompts

    defaults = [channels[n]["id"] for n in cfg["onboarding_default_channels"] if n in channels]
    for enabled in (True, False):
        body = {"prompts": build(), "default_channel_ids": defaults, "enabled": enabled, "mode": 0}
        try:
            api("PUT", f"/guilds/{gid}/onboarding", body)
            print(f"  {len(body['prompts'])} Pflichtfragen gespeichert, Onboarding {'AKTIV' if enabled else 'gespeichert, aber noch AUS'}.")
            if not enabled:
                warn("Onboarding konnte nicht automatisch aktiviert werden - in Server-Einstellungen > Onboarding einschalten.")
            return
        except DiscordError as e:
            print(f"  Versuch (enabled={enabled}) fehlgeschlagen: {e}")
    warn("Onboarding konnte nicht gespeichert werden (siehe Fehler oben).")


if __name__ == "__main__":
    main()
