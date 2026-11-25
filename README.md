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

## Magic Talks and Games (Hauptsitz)
`mtg.json` + `mtg_setup.py` bauen den Server „Magic Talks and Games“ auf: Team-Rollen (Admin, Judges, Magic-Helfer),
Level-Rollen (Zauberlehrling → Erzmagier, vergeben durch Lurkr), 24 Eigenschafts-Rollen (Format × oft/normal/weniger),
Kategorien/Foren/Tabletop-Simulator-Bereich, Platzhalter-Regeln und 8 Onboarding-Pflichtfragen.
Workflow: `.github/workflows/mtg-setup.yml` (bei Änderung oder „Run workflow“). Löscht nie etwas.
