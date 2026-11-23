# hauptstadt-primaten-bot

Der Discord-Server „Hauptstadt Primaten" als Konfiguration.

- `server.json` – beschreibt Kategorien, Kanäle und Forum-Tags
- `discord_setup.py` – gleicht den Server mit `server.json` ab (legt an / aktualisiert, löscht nie)
- `.github/workflows/discord-sync.yml` – läuft automatisch bei jeder Änderung auf `main`

Voraussetzung: Repository-Secret `DISCORD_BOT_TOKEN`, Bot mit Berechtigung „Kanäle verwalten“.
