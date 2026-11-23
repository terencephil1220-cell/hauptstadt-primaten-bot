# hauptstadt-primaten-bot

Der Discord-Server „Hauptstadt Primaten" als Konfiguration.

- `server.json` – beschreibt Kategorien, Kanäle und Forum-Tags
- `discord_setup.py` – gleicht den Server mit `server.json` ab (legt an / aktualisiert, löscht nie)
- `.github/workflows/discord-sync.yml` – läuft automatisch bei jeder Änderung auf `main`

Voraussetzung: Repository-Secret `DISCORD_BOT_TOKEN`, Bot mit Berechtigung „Kanäle verwalten“.

## Testserver spiegeln
`mirror_server.py` kopiert den Aufbau (Rollen, Kategorien, Kanäle, Tags, Kanal-Rechte) von `source` nach `target`
aus `mirror.json`. Die Quelle wird nur gelesen, auf dem Ziel wird nie gelöscht. Start: bei Änderung oder „Run workflow“.
Bot braucht auf dem Testserver Administrator.
