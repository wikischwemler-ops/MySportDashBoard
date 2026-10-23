"""Entscheidet, ob der geplante Lauf jetzt stattfinden soll (Ziel: 0 Uhr deutsche Zeit).
GitHub-Zeitpläne laufen in UTC. Der Workflow ist für 22:07 und 23:07 UTC geplant:
  Sommerzeit (UTC+2): 22:07 UTC = 0:07 Uhr  → läuft
  Winterzeit (UTC+1): 23:07 UTC = 0:07 Uhr  → läuft
Manuell gestartete Läufe laufen immer."""
import datetime as dt, os
from zoneinfo import ZoneInfo
ev = os.environ.get("GITHUB_EVENT_NAME", "")
cron = os.environ.get("SCHEDULE", "")
offset_h = int(dt.datetime.now(ZoneInfo("Europe/Berlin")).utcoffset().total_seconds() // 3600)
if ev != "schedule":
    run = True
else:
    run = (cron.startswith("7 22") and offset_h == 2) or (cron.startswith("7 23") and offset_h == 1)
print(f"Ereignis={ev} Zeitplan='{cron}' Berlin=UTC+{offset_h} → run={str(run).lower()}")
with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
    f.write(f"run={'true' if run else 'false'}\n")
