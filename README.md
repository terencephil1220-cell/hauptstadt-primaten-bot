# hauptstadt-primaten-bot

Der Discord-Server „Hauptstadt Primaten" als Konfiguration.

- `server.json` – beschreibt Kategorien, Kanäle und Forum-Tags
- `discord_setup.py` – gleicht den Server mit `server.json` ab (legt an / aktualisiert, löscht nie)
- `.github/workflows/discord-sync.yml` – läuft automatisch bei jeder Änderung auf `main`

Voraussetzung: Repository-Secret `DISCORD_BOT_TOKEN`, Bot mit Berechtigung „Kanäle verwalten“.

## Link-Bilder
`link_images.py` läuft alle 10 Minuten (Workflow „Link-Bilder“). Enthält ein neuer Post in #decks oder #karten einen
Archidekt-, Moxfield- oder Scryfall-Link, postet der Bot das Vorschaubild als Anhang und blendet die Link-Vorschau aus.
Zusätzliche Bot-Rechte: Nachrichtenverlauf lesen, Nachrichten in Threads senden, Dateien anhängen, Nachrichten verwalten.
